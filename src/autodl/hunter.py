"""Core GPU hunting workflow."""

from datetime import datetime, timedelta
from typing import Literal, TypedDict, cast, overload

from autodl.client import FailedError
from autodl.data_object import Config, RegionList
from autodl.runtime import logger
from autodl.types import JsonObject
from autodl.utils.helpers import end_of_day


class HuntResult(TypedDict):
    """Structured result emitted by a hunt attempt."""

    finished: bool
    running_instances: list[JsonObject]
    created_instances: list[JsonObject]


@overload
def try_to_create_instances(
    config: Config | None = None, *, details: Literal[False] = False
) -> bool:
    """Type overload for boolean-only hunt results."""
    ...


@overload
def try_to_create_instances(
    config: Config | None = None, *, details: Literal[True]
) -> HuntResult:
    """Type overload for detailed hunt results."""
    ...


def try_to_create_instances(
    config: Config | None = None, *, details: bool = False
) -> bool | HuntResult:
    """Try once to ensure the configured number of GPU instances exist.

    Args:
        config: Runtime hunt configuration. Defaults to ``Config()``.
        details: Whether to return a structured result instead of a boolean.

    Returns:
        ``True`` when the target instance count is satisfied, otherwise ``False``.
        When ``details`` is true, returns a ``HuntResult`` dictionary.
    """
    from autodl.client import (
        client,
        get_available_machines,
        get_running_instances,
        resolve_image_info,
    )

    # 加载数据和配置
    config = config or Config()
    region_list = RegionList.fetch()
    region_sign_list = [
        region_sign
        for region in region_list.regions
        if region["region_name"] in config.region_names
        for region_sign in cast(list[str], region["region_sign"])
    ]
    logger.debug(f"config: {config.model_dump()!r}")
    logger.debug(f"region_list: {region_list.model_dump()!r}")

    # 如果有克隆目标，确保使用同区域的机器
    region_clone_uuid_map: dict[str, str] = {}
    if config.clone_instances:
        region_clone_uuid_map = {
            str(i["region_sign"]): str(i["uuid"]) for i in config.clone_instances
        }
        if non_uuid_region_signs := list(
            set(region_sign_list) - set(region_clone_uuid_map.keys())
        ):
            logger.info(
                f"这些区域没有指定要克隆的实例：({non_uuid_region_signs})，创建实例时将不会克隆。"
                f" These regions do not specify an instance to be cloned: ({non_uuid_region_signs}) "
                f"and will not be cloned when the instance is created."
            )
    logger.debug(f"region_clone_uuid_map: {region_clone_uuid_map!r}")
    logger.debug(f"region_sign_list: {region_sign_list!r}")
    logger.info(
        f"尝试创建 {config.instance_num} 个实例..."
        f" Try to create {config.instance_num} instances..."
    )
    # 获取镜像
    image_info = resolve_image_info(
        base_image_labels=config.base_image_labels,
        shared_image_keyword=config.shared_image_keyword,
        shared_image_username_keyword=config.shared_image_username_keyword,
        shared_image_version=config.shared_image_version,
        private_image_uuid=config.private_image_uuid,
        private_image_name=config.private_image_name,
    )
    logger.debug(f"image_info: {image_info!r}")
    # 获取当前运行的实例
    instances = get_running_instances(
        region_names=config.region_names,
        gpu_type_names=config.gpu_type_names,
        image=image_info["image"],
        private_image_uuid=image_info["private_image_uuid"],
        reproduction_uuid=image_info["reproduction_uuid"],
        reproduction_id=image_info["reproduction_id"],
    )
    if len(instances) > 0:
        logger.info(
            f"{len(instances)} 个符合要求的实例已经在运行。"
            f" {len(instances)} requested instances are running."
        )
    instance_to_create_num = max(0, config.instance_num - len(instances))
    result: HuntResult = {
        "finished": False,
        "running_instances": [
            {
                "uuid": inst.get("uuid"),
                "region_name": inst.get("region_name"),
                "machine_alias": inst.get("machine_alias"),
                "gpu_name": inst.get("snapshot_gpu_alias_name"),
            }
            for inst in instances
        ],
        "created_instances": [],
    }
    logger.debug(f"instances: {instances!r}")
    logger.debug(f"instance_to_create_num: {instance_to_create_num!r}")
    # 检查是否需要创建实例
    if instance_to_create_num == 0:
        # 如果没有，就立刻完成
        result["finished"] = True
        return result if details else True
    else:
        # 如果需要，就创建实例
        # 寻找符合要求的机器
        machines = get_available_machines(
            region_sign_list,
            config.gpu_type_names,
            gpu_idle_num=config.gpu_idle_num,
            count=config.instance_num,
            min_expand_data_disk=config.expand_data_disk,
        )
        # 确保机器的数据盘扩容量足够
        logger.debug(f"machines: {machines!r}")
        # 检查是否有可用的机器
        if len(machines) == 0:
            # 如果没有就跳过
            logger.info("没有可用的 GPU 机器。 No available machine.")
        else:
            # 如果有符合要求的机器就创建实例
            for machine in machines[:instance_to_create_num]:
                try:
                    machine_id = str(machine["machine_id"])
                    machine_region_sign = str(machine["region_sign"])
                    # 创建实例
                    instance_uuid = client.create_instance(
                        machine_id,
                        image_info["image"],
                        private_image_uuid=image_info["private_image_uuid"],
                        reproduction_uuid=image_info["reproduction_uuid"],
                        reproduction_id=image_info["reproduction_id"],
                        req_gpu_amount=config.gpu_idle_num,
                        expand_data_disk=config.expand_data_disk,
                        clone_instance_uuid=region_clone_uuid_map.get(
                            machine_region_sign
                        ),
                        copy_data_disk_after_clone=config.copy_data_disk_after_clone,
                        keep_src_user_service_address_after_clone=config.keep_src_user_service_address_after_clone,
                    )
                    # 设置实例名称
                    client.update_instance_name(instance_uuid, "🎁🐒")
                    # 设置定时关机
                    shutdown_at: datetime | None = None
                    if config.shutdown_instance_after_hours:
                        shutdown_at = datetime.now() + timedelta(
                            hours=config.shutdown_instance_after_hours
                        )
                    elif config.shutdown_instance_today:
                        shutdown_at = end_of_day(datetime.now())
                    if shutdown_at:
                        logger.debug(
                            f"shutdown planned, instance_uuid: {instance_uuid!r}, shutdown_at: {shutdown_at!r}"
                        )
                        client.update_instance_shutdown(instance_uuid, shutdown_at)
                    instance_name = (
                        f"{machine['region_name']} / {machine['machine_alias']}"
                        f" ({machine['gpu_name']}, {instance_uuid})"
                    )
                    logger.info(
                        f"已创建实例：{instance_name}。"
                        f" Instance has been created: {instance_name}."
                    )
                    result["created_instances"].append(
                        {
                            "name": instance_name,
                            "uuid": instance_uuid,
                            "region_name": machine["region_name"],
                            "region_sign": machine_region_sign,
                            "machine_id": machine_id,
                            "machine_alias": machine["machine_alias"],
                            "gpu_name": machine["gpu_name"],
                        }
                    )
                except FailedError:
                    logger.error(
                        f"{machine['region_name']} {machine['machine_alias']} {machine['gpu_name']}"
                        f" ({machine['machine_id']})"
                    )
                    logger.error(
                        "使用以上机器创建实例时发生错误，跳过并继续..."
                        " An error occurred while creating the instance with the above machine,"
                        " skip and continue..."
                    )
            logger.debug(f"created_instances: {result['created_instances']!r}")
            # 检查是否完成
            if len(result["created_instances"]) == instance_to_create_num:
                # 创建的实例达到要求的数量后，完成
                logger.info(
                    f"{instance_to_create_num} 个实例创建完毕。"
                    f" {instance_to_create_num} requested instances are created."
                )
                result["finished"] = True
                return result if details else True
    return result if details else False
