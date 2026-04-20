"""Pydantic data models for AutoDL runtime configuration."""

from pathlib import Path
from typing import Self, cast

from pydantic import BaseModel, Field, model_validator
from pydantic_settings import (
    BaseSettings,
    JsonConfigSettingsSource,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

from autodl.runtime import DATA_DIR
from autodl.types import JsonObject

CONFIG_FILE = Path(DATA_DIR) / "config.json"


class Config(BaseSettings):
    """Runtime configuration loaded from env, JSON files, and CLI overrides."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        env_prefix="AUTODL_",
        extra="ignore",
        json_file=CONFIG_FILE,
        json_file_encoding="utf-8",
        populate_by_name=True,
        validate_assignment=True,
    )

    region_names: list[str] = Field(default_factory=list)
    gpu_type_names: list[str] = Field(default_factory=list)
    gpu_idle_num: int = 1
    instance_num: int = 1
    base_image_labels: list[str] | None = None
    shared_image_keyword: str = ""
    shared_image_username_keyword: str = ""
    shared_image_version: str = ""
    private_image_uuid: str = ""
    private_image_name: str = ""
    expand_data_disk: int = 0
    clone_instances: list[JsonObject] = Field(default_factory=list)
    copy_data_disk_after_clone: bool = False
    keep_src_user_service_address_after_clone: bool = False
    shutdown_instance_after_hours: float = 0
    shutdown_instance_today: bool = True
    retry_interval_seconds: int = 30

    @model_validator(mode="before")
    @classmethod
    def normalize_config(cls, data: object) -> object:
        """Normalize legacy config keys before Pydantic validation.

        Args:
            data: Raw settings payload.

        Returns:
            Raw payload with ``expand_data_disk_gb`` converted to bytes.
        """
        if not isinstance(data, dict) or "expand_data_disk_gb" not in data:
            return data
        data = dict(data)
        expand_data_disk_gb = data.pop("expand_data_disk_gb")
        if expand_data_disk_gb is not None:
            data["expand_data_disk"] = int(float(expand_data_disk_gb) * 1073741824)
        return data

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """Declare settings source priority.

        Args:
            settings_cls: Settings class being initialized.
            init_settings: Values passed directly to the model.
            env_settings: Environment variable settings source.
            dotenv_settings: ``.env`` settings source.
            file_secret_settings: File secret settings source.

        Returns:
            Ordered settings sources.
        """
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            JsonConfigSettingsSource(settings_cls),
            file_secret_settings,
        )


class RegionList(BaseModel):
    """Cached region list enriched with GPU type availability."""

    regions: list[JsonObject] = Field(default_factory=list)

    @classmethod
    def fetch(cls) -> Self:
        """Fetch regions and their GPU type summaries from AutoDL.

        Returns:
            Region list model populated from the AutoDL APIs.
        """
        from autodl.client import client

        regions: list[JsonObject] = []
        for region in client.get_regions():
            region_signs = cast(list[str], region["region_sign"])
            regions.append(
                {
                    **region,
                    "gpu_types": [
                        {
                            "gpu_type": next(iter(gpu_type.keys())),
                            **cast(JsonObject, next(iter(gpu_type.values()))),
                        }
                        for gpu_type in client.get_region_gpu_types(region_signs)
                    ],
                }
            )
        return cls(regions=regions)
