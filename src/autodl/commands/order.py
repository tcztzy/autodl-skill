"""CLI command for ordering an AutoDL machine."""

import argparse
from collections.abc import Sequence
from datetime import datetime, timedelta
from typing import Literal

from autodl.commands._common import (
    OutputFormat,
    add_format_argument,
    emit,
    exit_error,
    gb_to_bytes,
    json_object,
    redirect_logs_to_stderr,
    split_values,
)
from autodl.data_object import Config
from autodl.types import JsonObject
from autodl.utils.helpers import end_of_day


def get_help() -> str:
    """Return command help text for argparse."""
    return "Order a machine by id or by first available match."


def add_arguments(parser: argparse.ArgumentParser) -> None:
    """Register order subcommand arguments.

    Args:
        parser: Subparser to mutate.
    """
    parser.add_argument("--machine-id", help="Exact machine id to order.")
    parser.add_argument("-r", "--region", action="append", help="Region name/sign.")
    parser.add_argument("-g", "--gpu", action="append", help="GPU type name.")
    parser.add_argument("--gpu-num", type=int, default=1, help="Requested GPU count.")
    parser.add_argument(
        "--count",
        type=int,
        default=1,
        help="Instances to create when searching for machines.",
    )
    parser.add_argument("--name", default="", help="Instance name.")
    parser.add_argument("--disk-gb", type=float, default=0, help="Extra data disk GiB.")
    parser.add_argument(
        "--base-image",
        help="Comma-separated base image label path, e.g. PyTorch,2.1.0,3.10(...),12.1.",
    )
    parser.add_argument(
        "--base-image-label",
        action="append",
        help="One base image label. Repeat to build the path.",
    )
    parser.add_argument("--shared-image", default="", help="Shared image keyword/UUID.")
    parser.add_argument("--shared-user", default="", help="Shared image user filter.")
    parser.add_argument("--shared-version", default="", help="Shared image version.")
    parser.add_argument("--private-image-uuid", default="", help="Private image UUID.")
    parser.add_argument("--private-image-name", default="", help="Private image name.")
    parser.add_argument(
        "--shutdown-hours",
        type=float,
        default=0,
        help="Set timed shutdown after hours.",
    )
    parser.add_argument(
        "--shutdown-today", action="store_true", help="Set shutdown at end of today."
    )
    add_format_argument(parser)


def main(
    machine_id: str | None = None,
    region: Sequence[str] | None = None,
    gpu: Sequence[str] | None = None,
    gpu_num: int = 1,
    count: int = 1,
    name: str = "",
    disk_gb: float = 0,
    base_image: str | None = None,
    base_image_label: Sequence[str] | None = None,
    shared_image: str = "",
    shared_user: str = "",
    shared_version: str = "",
    private_image_uuid: str = "",
    private_image_name: str = "",
    shutdown_hours: float = 0,
    shutdown_today: bool = False,
    format: Literal["json", "text"] = "json",
) -> None:
    """Run the order command.

    Args:
        machine_id: Exact machine id to order.
        region: Region filters used when searching.
        gpu: GPU type filters used when searching.
        gpu_num: Requested GPU count per instance.
        count: Number of instances to create.
        name: Instance display name.
        disk_gb: Extra data disk size in GiB.
        base_image: Comma-separated base image label path.
        base_image_label: Repeated base image labels.
        shared_image: Shared image keyword or UUID.
        shared_user: Shared image user filter.
        shared_version: Shared image version.
        private_image_uuid: Private image UUID.
        private_image_name: Private image name.
        shutdown_hours: Timed shutdown delay in hours.
        shutdown_today: Whether to shutdown at the end of today.
        format: Output format.
    """
    redirect_logs_to_stderr()
    output_format: OutputFormat = format
    try:
        from autodl.client import client, get_available_machines, resolve_image_info
        from autodl.commands.machines import _machine_summary, _resolve_region_signs

        config = Config()
        _validate_limits(gpu_num, count, disk_gb)
        base_image_labels = (
            split_values([base_image] if base_image else None)
            or split_values(base_image_label)
            or config.base_image_labels
        )
        image_info = resolve_image_info(
            base_image_labels=base_image_labels,
            shared_image_keyword=shared_image or config.shared_image_keyword,
            shared_image_username_keyword=shared_user
            or config.shared_image_username_keyword,
            shared_image_version=shared_version or config.shared_image_version,
            private_image_uuid=private_image_uuid or config.private_image_uuid,
            private_image_name=private_image_name or config.private_image_name,
        )
        machine_ids = [machine_id] if machine_id else []
        machines: list[JsonObject] = []
        if not machine_ids:
            region_filters = split_values(region) or config.region_names
            gpu_names = split_values(gpu) or config.gpu_type_names
            if not gpu_names:
                raise ValueError("--gpu is required when --machine-id is not set")
            machines = get_available_machines(
                _resolve_region_signs(region_filters),
                gpu_names,
                gpu_idle_num=gpu_num,
                count=count,
                min_expand_data_disk=gb_to_bytes(disk_gb),
            )
            machine_ids = [str(machine["machine_id"]) for machine in machines]
        if not machine_ids:
            emit(
                json_object(status="no_machine", created_instances=[]),
                output_format,
            )
            raise SystemExit(1)

        created: list[JsonObject] = []
        for index, order_machine_id in enumerate(machine_ids[:count], start=1):
            instance_uuid = client.create_instance(
                order_machine_id,
                image_info["image"],
                instance_name=name,
                private_image_uuid=image_info["private_image_uuid"],
                reproduction_uuid=image_info["reproduction_uuid"],
                reproduction_id=image_info["reproduction_id"],
                req_gpu_amount=gpu_num,
                expand_data_disk=gb_to_bytes(disk_gb),
            )
            if name:
                client.update_instance_name(instance_uuid, name)
            shutdown_at = _shutdown_at(shutdown_hours, shutdown_today)
            if shutdown_at:
                client.update_instance_shutdown(instance_uuid, shutdown_at)
            created.append(
                json_object(
                    uuid=instance_uuid,
                    machine_id=order_machine_id,
                    name=name,
                    image=image_info["image"],
                    shutdown_at=shutdown_at.isoformat(timespec="seconds")
                    if shutdown_at
                    else None,
                    index=index,
                )
            )
        emit(
            json_object(
                status="ok",
                created_instances=created,
                selected_machines=[
                    _machine_summary(machine, include_raw=False) for machine in machines
                ],
            ),
            output_format,
        )
    except SystemExit:
        raise
    except Exception as e:
        exit_error(e, output_format)


def _shutdown_at(hours: float, today: bool) -> datetime | None:
    """Resolve shutdown options to a datetime.

    Args:
        hours: Hours after now. ``0`` disables this mode.
        today: Whether to shutdown at today's end.

    Returns:
        Shutdown time, or ``None``.
    """
    if hours:
        return datetime.now() + timedelta(hours=hours)
    if today:
        return end_of_day(datetime.now())
    return None


def _validate_limits(gpu_num: int, count: int, disk_gb: float) -> None:
    """Validate numeric order limits.

    Args:
        gpu_num: Requested GPU count.
        count: Instance count.
        disk_gb: Extra disk in GiB.

    Raises:
        ValueError: If an argument is invalid.
    """
    if gpu_num <= 0:
        raise ValueError("--gpu-num must be greater than 0")
    if count <= 0:
        raise ValueError("--count must be greater than 0")
    if disk_gb < 0:
        raise ValueError("--disk-gb must not be negative")
