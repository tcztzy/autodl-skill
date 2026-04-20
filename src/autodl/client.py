"""Client helpers for the AutoDL private HTTP API."""

import datetime
import logging
import os
import time
from collections.abc import Iterator, Sequence
from typing import TypedDict, cast

import httpx
from dotenv import load_dotenv
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from autodl.runtime import logger, save_api_response
from autodl.types import JsonObject, JsonValue
from autodl.utils.helpers import url_set_params

load_dotenv()

INSTANCE_RUNNING_STATUSES: list[str] = [
    "creating",
    "starting",
    "running",
    "re_initializing",
]


class ImageInfo(TypedDict):
    """Resolved image fields required by the AutoDL create-instance API."""

    image: str
    private_image_uuid: str
    reproduction_uuid: str
    reproduction_id: int


class FailedError(Exception):
    """Raised when the AutoDL API returns a non-success response."""


class AutoDL:
    """Thin HTTP client for AutoDL account, image, machine, and instance APIs."""

    def __init__(
        self,
        *,
        token: str | None = None,
        timeout: float | httpx.Timeout = 30,
        http_client: httpx.Client | None = None,
        api_host: str = "https://api.autodl.com",
        **kwargs: object,
    ) -> None:
        """Initialize the AutoDL API client.

        Args:
            token: Developer token. Defaults to the ``AUTODL_TOKEN`` environment variable.
            timeout: HTTPX timeout used when creating the default client.
            http_client: Preconfigured HTTP client.
            api_host: Base API host for relative API paths.
            **kwargs: Extra attributes to attach to the instance for compatibility.
        """
        self.api_host = api_host
        self.token = token or os.getenv("AUTODL_TOKEN", "")
        self.timeout = timeout
        self.http_client = http_client or httpx.Client(timeout=self.timeout)
        self.__dict__.update(kwargs)

    def create_instance(
        self,
        machine_id: str,
        image: str,
        instance_name: str = "",
        private_image_uuid: str = "",
        reproduction_uuid: str = "",
        reproduction_id: int = 0,
        req_gpu_amount: int = 1,
        expand_data_disk: int = 0,
        clone_instance_uuid: str | None = None,
        copy_data_disk_after_clone: bool = False,
        keep_src_user_service_address_after_clone: bool = True,
        **kwargs: JsonValue,
    ) -> str:
        """Create a pay-as-you-go instance or clone an existing instance.

        Args:
            machine_id: AutoDL machine id, for example ``"463e49a218"``.
            image: Runtime image name.
            instance_name: Display name for the new instance.
            private_image_uuid: Private image UUID when creating from a private image.
            reproduction_uuid: Shared image reproduction UUID.
            reproduction_id: Shared image reproduction id.
            req_gpu_amount: Requested GPU count.
            expand_data_disk: Extra data disk bytes.
            clone_instance_uuid: Source instance UUID when cloning.
            copy_data_disk_after_clone: Whether to copy the source data disk.
            keep_src_user_service_address_after_clone: Whether to keep source service addresses.
            **kwargs: Additional AutoDL order payload fields.

        Returns:
            New instance UUID.
        """
        api = "/api/v1/order/instance/create/payg"
        instance_info: JsonObject = {
            "machine_id": machine_id,
            "charge_type": "payg",
            "req_gpu_amount": req_gpu_amount,
            "image": image,
            "private_image_uuid": private_image_uuid,
            "reproduction_uuid": reproduction_uuid,
            "instance_name": instance_name,
            "expand_data_disk": expand_data_disk,
            "reproduction_id": reproduction_id,
        }
        price_info: JsonObject = {
            "coupon_id_list": [],
            "machine_id": machine_id,
            "charge_type": "payg",
            "duration": 1,
            "num": req_gpu_amount,
            "expand_data_disk": expand_data_disk,
        }
        body: JsonObject = {
            "instance_info": instance_info,
            "price_info": price_info,
            **kwargs,
        }
        if clone_instance_uuid:
            api = "/api/v1/order/instance/clone/payg"
            body["instance_uuid"] = clone_instance_uuid
            body["instance_info"] = {
                **instance_info,
                "copy_data_disk_after_clone": copy_data_disk_after_clone,
                "keep_src_user_service_address_after_clone": keep_src_user_service_address_after_clone,
            }
        return str(self.request(api, body=body))

    def update_instance_shutdown(
        self,
        instance_uuid: str,
        shutdown_at: datetime.datetime | datetime.date | str,
        **kwargs: JsonValue,
    ) -> None:
        """Set a timed shutdown for an instance.

        Args:
            instance_uuid: Instance UUID to update.
            shutdown_at: Shutdown time as a date, datetime, or AutoDL-formatted string.
            **kwargs: Additional AutoDL request payload fields.
        """
        api = "/api/v1/instance/timed/shutdown"
        body: JsonObject = {
            "instance_uuid": instance_uuid,
            "shutdown_at": (
                shutdown_at.strftime("%Y-%m-%d %H:%M")
                if isinstance(shutdown_at, (datetime.datetime, datetime.date))
                else shutdown_at
            ),
            **kwargs,
        }
        self.request(api, body=body)

    def update_instance_name(
        self, instance_uuid: str, instance_name: str, **kwargs: JsonValue
    ) -> None:
        """Update an instance display name.

        Args:
            instance_uuid: Instance UUID to update.
            instance_name: New display name.
            **kwargs: Additional AutoDL request payload fields.
        """
        api = "/api/v1/instance/name"
        body: JsonObject = {
            "instance_uuid": instance_uuid,
            "instance_name": instance_name,
            **kwargs,
        }
        self.request(api, body=body, method="PUT")

    def get_private_images(self, **kwargs: JsonValue) -> list[JsonObject]:
        """Fetch private images owned by the current AutoDL account.

        Args:
            **kwargs: Request payload fields supported by the AutoDL API.

        Returns:
            Private image records.
        """
        api = "/api/v1/image/private/get"
        body: JsonObject = {
            **kwargs,
        }
        return cast(list[JsonObject], self.request(api, body=body))

    def get_shared_images(
        self, reproduction_uuid: str = "", **kwargs: JsonValue
    ) -> list[JsonObject]:
        """Search shared CodeWithGPU images.

        Args:
            reproduction_uuid: Image keyword or reproduction UUID filter.
            **kwargs: Request payload fields supported by the AutoDL API.

        Returns:
            Shared image records with version metadata.
        """
        api = "/api/v1/image/codewithgpu/list"
        body: JsonObject = {
            "reproduction_uuid": reproduction_uuid,
            **kwargs,
        }
        return cast(list[JsonObject], self.request(api, body=body))

    def get_shared_image_detail(
        self,
        image_uuid: str,
        image_version: str,
        image_id: int,
        **kwargs: JsonValue,
    ) -> JsonObject:
        """Fetch a single shared image version.

        Args:
            image_uuid: Shared image UUID.
            image_version: Shared image version without the ``v`` prefix.
            image_id: Shared image id.
            **kwargs: Query parameters supported by the AutoDL API.

        Returns:
            Shared image detail containing the concrete runtime image.
        """
        api = "/api/v1/image/codewithgpu"
        params: JsonObject = {
            "reproduction_uuid": f"{image_uuid}:v{image_version}",
            "reproduction_id": image_id,
            **kwargs,
        }
        return cast(JsonObject, self.request(api, params=params, method="GET"))

    def get_base_images(self, **kwargs: JsonValue) -> list[JsonObject]:
        """Fetch the base image tree.

        Args:
            **kwargs: Request payload fields supported by the AutoDL API.

        Returns:
            Nested base image records.
        """
        api = "/api/v1/image/all"
        body: JsonObject = {
            **kwargs,
        }
        return cast(list[JsonObject], self.request(api, body=body))

    def get_wallet_balance(self) -> JsonObject:
        """Fetch the current account wallet balance.

        Returns:
            Wallet fields from AutoDL. Amounts are milli-yuan integers.
        """
        api = "/api/v1/dev/wallet/balance"
        return cast(JsonObject, self.request(api, body={}))

    def list_instance(
        self,
        status: str | list[str] | tuple[str, ...] | None = None,
        **kwargs: JsonValue,
    ) -> Iterator[JsonObject]:
        """Iterate over account instances.

        Args:
            status: Status or statuses, such as ``"running"``.
            **kwargs: Additional AutoDL list payload fields.

        Yields:
            Instance records.
        """
        api = "/api/v1/instance"
        statuses = (
            list(status)
            if isinstance(status, (list, tuple))
            else [status]
            if status
            else []
        )
        body: JsonObject = cast(
            JsonObject, {"page_size": 20, "status": statuses, **kwargs}
        )
        return self.list_request(api, body)

    def get_regions(self, **kwargs: JsonValue) -> list[JsonObject]:
        """Fetch available AutoDL regions.

        Args:
            **kwargs: Query parameters supported by the AutoDL frontend API.

        Returns:
            Region records.
        """
        api = "https://fe-config-backend.autodl.com/api/v1/autodl/region/tag"
        params: JsonObject = {
            **kwargs,
        }
        return cast(list[JsonObject], self.request(api, params=params, method="GET"))

    def get_region_gpu_types(
        self, region_sign_list: Sequence[str], **kwargs: JsonValue
    ) -> list[JsonObject]:
        """Fetch GPU type availability for regions.

        Args:
            region_sign_list: Region signs such as ``["beijing-A", "beijing-B"]``.
            **kwargs: Additional AutoDL request payload fields.

        Returns:
            GPU type records keyed by GPU model name.
        """
        api = "/api/v1/machine/region/gpu_type"
        body: JsonObject = {
            **kwargs,
            "region_sign_list": list(region_sign_list),
        }
        return cast(list[JsonObject], self.request(api, body=body))

    def list_machine(
        self,
        region_sign_list: Sequence[str],
        gpu_type_name: str | list[str] | tuple[str, ...],
        gpu_idle_num: int = 1,
        **kwargs: JsonValue,
    ) -> Iterator[JsonObject]:
        """Iterate over GPU machines matching region and GPU filters.

        Args:
            region_sign_list: Region signs such as ``["beijing-A", "beijing-B"]``.
            gpu_type_name: GPU type name or names.
            gpu_idle_num: Minimum idle GPU count requested from the API.
            **kwargs: Additional AutoDL list payload fields.

        Yields:
            Machine records. ``gpu_order_num`` indicates rentability.
        """
        api = "/api/v1/user/machine/list"
        gpu_type_names = (
            list(gpu_type_name)
            if isinstance(gpu_type_name, list | tuple)
            else [gpu_type_name]
        )
        body: JsonObject = cast(
            JsonObject,
            {
                "charge_type": "payg",
                "page_size": 20,
                "gpu_idle_num": gpu_idle_num,
                "region_sign_list": list(region_sign_list),
                "gpu_type_name": gpu_type_names,
                **kwargs,
            },
        )
        return self.list_request(api, body)

    def list_request(self, api: str, body: JsonObject) -> Iterator[JsonObject]:
        """Iterate over all pages from a paginated AutoDL API.

        Args:
            api: API path or absolute URL.
            body: Request JSON body. ``page_index`` is updated in place.

        Yields:
            Records from the paginated response list.
        """
        page_index = 1
        while True:
            body["page_index"] = page_index
            data = cast(JsonObject, self.request(api, body=body))
            for item in cast(list[JsonObject], data["list"]):
                yield item
            page_index += 1
            if page_index > int(cast(int, data["max_page"])):
                break
            time.sleep(0.2)

    @retry(
        reraise=True,
        retry=retry_if_exception_type(httpx.HTTPError),
        stop=stop_after_attempt(6),
        wait=wait_exponential(multiplier=5, exp_base=2),
        before_sleep=before_sleep_log(logger, logging.WARNING),
    )
    def request(
        self,
        api_url: str,
        params: JsonObject | None = None,
        method: str = "POST",
        body: JsonObject | None = None,
    ) -> JsonValue:
        """Send a request to AutoDL and return the response data field.

        Args:
            api_url: Relative API path or absolute URL.
            params: Query parameters.
            method: HTTP method.
            body: JSON request body.

        Returns:
            The ``data`` field from the AutoDL response.

        Raises:
            FailedError: If AutoDL returns a non-success code.
            httpx.HTTPError: If the HTTP client fails after retries.
        """
        url = api_url if api_url.startswith("https://") else f"{self.api_host}{api_url}"
        if params:
            url = url_set_params(url, **params)
        headers: dict[str, str] = {
            "Authorization": self.token,
            "Content-Type": "application/json",
        }
        logger.debug(url)
        logger.debug(method)
        logger.debug(body)
        response = self.http_client.request(method, url, json=body, headers=headers)
        save_api_response(
            method,
            url,
            response.content,
            content_type=response.headers.get("content-type"),
        )
        data = cast(JsonObject, response.json())
        if data["code"] not in ["Success", "OK"]:
            logger.error(data)
            raise FailedError(str(data["msg"]))
        else:
            logger.debug(data["data"])
            return data["data"]


def get_available_machines(
    region_sign_list: Sequence[str],
    gpu_type_name: str | list[str] | tuple[str, ...],
    gpu_idle_num: int = 1,
    count: int | None = 10,
    min_expand_data_disk: int = 0,
    **kwargs: JsonValue,
) -> list[JsonObject]:
    """Find currently rentable machines matching GPU and disk constraints.

    Args:
        region_sign_list: Region signs to search.
        gpu_type_name: GPU type name or names.
        gpu_idle_num: Minimum idle and orderable GPU count.
        count: Maximum number of machines to return. ``None`` means unlimited.
        min_expand_data_disk: Minimum expandable data disk bytes.
        **kwargs: Additional AutoDL machine-list payload fields.

    Returns:
        Matching machine records.
    """
    gpu_type_names = (
        list(gpu_type_name)
        if isinstance(gpu_type_name, (list, tuple))
        else [gpu_type_name]
    )
    machines: list[JsonObject] = []
    for mch in client.list_machine(
        region_sign_list, gpu_type_names, gpu_idle_num, **kwargs
    ):
        if (
            int(cast(int, mch["gpu_idle_num"])) >= gpu_idle_num
            and int(cast(int, mch["gpu_order_num"])) >= gpu_idle_num
            and int(cast(int, mch["max_data_disk_expand_size"])) >= min_expand_data_disk
        ):
            machines.append(mch)
        if count is not None and len(machines) == count:
            break
    return machines


def get_running_instances(
    region_names: Sequence[str] | None = None,
    gpu_type_names: Sequence[str] | None = None,
    image: str | None = None,
    private_image_uuid: str | None = None,
    reproduction_uuid: str | None = None,
    reproduction_id: int | None = None,
) -> list[JsonObject]:
    """Return running instances that match optional filters.

    Args:
        region_names: Region names to include.
        gpu_type_names: GPU display names to include.
        image: Runtime image filter.
        private_image_uuid: Private image UUID filter.
        reproduction_uuid: Shared image reproduction UUID filter.
        reproduction_id: Shared image reproduction id filter.

    Returns:
        Matching running instance records.
    """

    def match(inst: JsonObject) -> bool:
        """Check whether an instance satisfies all active filters."""
        return (
            (region_names is None or inst["region_name"] in region_names)
            and (
                gpu_type_names is None
                or inst["snapshot_gpu_alias_name"] in gpu_type_names
            )
            and (image is None or inst["image"] == image)
            and (
                private_image_uuid is None
                or inst["private_image_uuid"] == private_image_uuid
            )
            and (
                reproduction_uuid is None
                or inst["reproduction_uuid"] == reproduction_uuid
            )
            and (reproduction_id is None or inst["reproduction_id"] == reproduction_id)
        )

    instances = [
        inst for inst in client.list_instance(INSTANCE_RUNNING_STATUSES) if match(inst)
    ]
    return instances


def resolve_image_info(
    base_image_labels: Sequence[str] | None = None,
    shared_image_keyword: str | None = None,
    shared_image_username_keyword: str | None = None,
    shared_image_version: str | None = None,
    private_image_uuid: str | None = None,
    private_image_name: str | None = None,
) -> ImageInfo:
    """Resolve a configured image selector into create-instance image fields.

    Args:
        base_image_labels: Path through the AutoDL base-image tree.
        shared_image_keyword: Shared image keyword or reproduction UUID.
        shared_image_username_keyword: User name substring filter for shared images.
        shared_image_version: Shared image version prefix.
        private_image_uuid: Private image UUID selector.
        private_image_name: Private image name selector.

    Returns:
        Image fields accepted by ``create_instance``.

    Raises:
        ValueError: If the selector is invalid or no matching image exists.
    """

    def search_base_image(items: Sequence[JsonObject], label_index: int = 0) -> str:
        """Return the concrete image name at the selected base-image path."""
        if base_image_labels is None:
            raise ValueError("base_image_labels is required")
        if item := next(
            (i for i in items if i["label"] == base_image_labels[label_index]), None
        ):
            if isinstance(item["label_name"], dict):
                return str(item["label_name"]["i"])
            else:
                return search_base_image(
                    cast(list[JsonObject], item["children"]), label_index + 1
                )
        else:
            raise ValueError(
                f"Image label not found: {base_image_labels[label_index]!r} in items {items!r}"
            )

    image_info: ImageInfo = {
        "image": "",
        "private_image_uuid": "",
        "reproduction_uuid": "",
        "reproduction_id": 0,
    }
    if base_image_labels:
        image_info["image"] = search_base_image(client.get_base_images())
    elif shared_image_keyword:
        filtered_image = [
            i
            for i in client.get_shared_images(shared_image_keyword)
            if (
                not shared_image_username_keyword
                or shared_image_username_keyword.lower() in str(i["username"]).lower()
            )
        ]
        if len(filtered_image) == 0:
            raise ValueError(
                f"Image not found with keyword: {shared_image_keyword!r}"
                f" and {shared_image_username_keyword!r}"
            )
        image = filtered_image[0]
        version_info = cast(list[JsonObject], image["version_info"])
        filtered_versions = [
            v
            for v in version_info
            if (
                not shared_image_version
                or str(v["version"]).startswith(shared_image_version.strip("v"))
            )
        ]
        if len(filtered_versions) == 0:
            raise ValueError(f"Image not found with version: {shared_image_version!r}")
        image_version = str(filtered_versions[0]["version"])
        shared_image = client.get_shared_image_detail(
            str(image["uuid"]), image_version, int(cast(int, image["image_id"]))
        )
        image_info["image"] = str(shared_image["image"])
        image_info["reproduction_uuid"] = str(shared_image["entity_uuid"])
        image_info["reproduction_id"] = int(cast(int, shared_image["entity_id"]))
    elif private_image_uuid or private_image_name:
        filtered_image = [
            i
            for i in client.get_private_images()
            if (
                private_image_uuid
                and i["image_uuid"] == private_image_uuid
                or private_image_name
                and i["name"] == private_image_name
            )
        ]
        if len(filtered_image) == 0:
            raise ValueError(
                f"Image not found with uuid: {private_image_uuid!r}"
                f" or name: {private_image_name!r}"
            )
        private_image = filtered_image[0]
        image_info["image"] = str(private_image["read_layer_image_name"])
        image_info["private_image_uuid"] = str(private_image["image_uuid"])
    else:
        raise ValueError("Invalid parameters")
    return image_info


client: AutoDL = AutoDL()
