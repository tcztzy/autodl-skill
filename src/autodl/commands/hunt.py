"""CLI command for hunting AutoDL GPU instances."""

import argparse
import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Literal, TypedDict, cast

from autodl.data_object import CONFIG_FILE, Config
from autodl.runtime import logger
from autodl.types import JsonObject
from autodl.utils.helpers import json_dumps


type OutputFormat = Literal["json", "jsonl", "text"]


class ConfigOverrides(TypedDict, total=False):
    """CLI and inline JSON overrides accepted by ``Config``."""

    region_names: list[str]
    gpu_type_names: list[str]
    gpu_idle_num: int
    instance_num: int
    base_image_labels: list[str] | None
    shared_image_keyword: str
    shared_image_username_keyword: str
    shared_image_version: str
    private_image_uuid: str
    private_image_name: str
    expand_data_disk: int
    clone_instances: list[JsonObject]
    copy_data_disk_after_clone: bool
    keep_src_user_service_address_after_clone: bool
    shutdown_instance_after_hours: float
    shutdown_instance_today: bool
    retry_interval_seconds: int


CONFIG_TEMPLATE: JsonObject = {
    "region_names": ["西北B区"],
    "gpu_type_names": ["RTX 4090"],
    "gpu_idle_num": 1,
    "instance_num": 1,
    "base_image_labels": ["PyTorch", "2.1.0", "3.10(ubuntu22.04)", "12.1"],
    "expand_data_disk_gb": 0,
    "shutdown_instance_today": True,
    "shutdown_instance_after_hours": 0,
    "retry_interval_seconds": 30,
}


def get_help() -> str:
    """Return command help text for argparse."""
    return "蹲守 GPU 并输出 agent-readable 事件。 Hunt GPUs for agents."


def add_arguments(parser: argparse.ArgumentParser) -> None:
    """Register hunt subcommand arguments.

    Args:
        parser: Subparser to mutate.
    """
    parser.add_argument(
        "-c",
        "--config",
        help="JSON config file. Fields follow Config in autodl/data_object.py.",
    )
    parser.add_argument(
        "--config-json",
        help="Inline JSON config. Overrides --config and saved config values.",
    )
    parser.add_argument(
        "--interval", type=int, help="Retry interval seconds. Minimum is 10."
    )
    parser.add_argument(
        "--loop", action="store_true", help="Keep scanning until finished."
    )
    parser.add_argument(
        "--max-attempts",
        type=int,
        default=0,
        help="Max loop attempts. 0 means unlimited.",
    )
    parser.add_argument(
        "--save-config",
        action="store_true",
        help="Persist merged config to runtime/data/config.json.",
    )
    parser.add_argument(
        "--template", action="store_true", help="Print a hunt config template and exit."
    )
    parser.add_argument(
        "--jsonl", action="store_true", help="Emit one JSON object per event."
    )
    parser.add_argument(
        "--format", choices=["json", "text"], default="json", help="Output format."
    )


def main(
    config: str | None = None,
    config_json: str | None = None,
    interval: int | None = None,
    loop: bool = False,
    max_attempts: int = 0,
    save_config: bool = False,
    template: bool = False,
    jsonl: bool = False,
    format: Literal["json", "text"] = "json",
) -> None:
    """Run the hunt command.

    Args:
        config: JSON config file path.
        config_json: Inline JSON config overrides.
        interval: Retry interval override in seconds.
        loop: Whether to keep retrying until finished.
        max_attempts: Maximum loop attempts. ``0`` means unlimited.
        save_config: Whether to persist the merged config.
        template: Whether to print the config template and exit.
        jsonl: Whether to emit newline-delimited JSON events.
        format: Output format for non-JSONL mode.
    """
    if template:
        print(json_dumps(CONFIG_TEMPLATE, indent=2))
        return

    output_format: OutputFormat = "jsonl" if jsonl else format
    for handler in logger.handlers:
        if (
            isinstance(handler, logging.StreamHandler)
            and getattr(handler, "stream", None) is sys.stdout
        ):
            handler.stream = sys.stderr
    try:
        overrides: ConfigOverrides = {}
        if config_json:
            overrides.update(cast(ConfigOverrides, json.loads(config_json)))
        if interval is not None:
            overrides["retry_interval_seconds"] = max(10, interval)

        config_class: type[Config] = Config
        if config:

            class HuntConfig(Config):
                """Config subclass that layers a user-provided JSON file."""

                model_config = {
                    **Config.model_config,
                    "json_file": [CONFIG_FILE, Path(config)],
                }

            config_class = HuntConfig

        runtime_config = config_class(**overrides)
        if save_config:
            CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
            CONFIG_FILE.write_text(
                json_dumps(runtime_config.model_dump(), indent=2), encoding="utf-8"
            )

        _validate_config(runtime_config)
        _run(runtime_config, loop, max_attempts, output_format)
    except Exception as e:
        _emit(
            cast(
                JsonObject,
                {"status": "error", "error_type": type(e).__name__, "message": str(e)},
            ),
            output_format,
        )
        raise SystemExit(2)


def _run(
    config: Config, loop: bool, max_attempts: int, output_format: OutputFormat
) -> None:
    """Run one or more hunt attempts.

    Args:
        config: Validated runtime configuration.
        loop: Whether to retry until finished.
        max_attempts: Maximum loop attempts. ``0`` means unlimited.
        output_format: Event output format.
    """
    from autodl.hunter import try_to_create_instances

    attempt = 0
    while True:
        attempt += 1
        result = try_to_create_instances(config, details=True)
        finished = result["finished"]
        _emit(
            _event(
                "finished" if finished else "waiting",
                config,
                attempt,
                cast(JsonObject, result),
            ),
            output_format,
        )
        if finished or not loop:
            return
        if max_attempts and attempt >= max_attempts:
            _emit(
                _event("timeout", config, attempt, cast(JsonObject, result)),
                output_format,
            )
            raise SystemExit(1)
        time.sleep(config.retry_interval_seconds)


def _validate_config(config: Config) -> None:
    """Validate cross-field requirements not expressed by Pydantic.

    Args:
        config: Runtime configuration to validate.

    Raises:
        ValueError: If required hunt fields are missing or invalid.
    """
    errors: list[str] = []
    if not config.region_names:
        errors.append("region_names is required.")
    if not config.gpu_type_names:
        errors.append("gpu_type_names is required.")
    if not config.gpu_idle_num or config.gpu_idle_num <= 0:
        errors.append("gpu_idle_num must be greater than 0.")
    if not config.instance_num or config.instance_num <= 0:
        errors.append("instance_num must be greater than 0.")
    has_image = bool(
        config.base_image_labels
        or config.shared_image_keyword
        or config.private_image_uuid
        or config.private_image_name
    )
    if not has_image:
        errors.append(
            "one image selector is required: base_image_labels, shared_image_keyword, or private image."
        )
    if errors:
        raise ValueError("; ".join(errors))


def _event(
    status: str, config: Config, attempt: int, result: JsonObject | None = None
) -> JsonObject:
    """Build a structured event for stdout.

    Args:
        status: Event status such as ``waiting`` or ``finished``.
        config: Runtime configuration.
        attempt: Current attempt number.
        result: Hunt result payload.

    Returns:
        JSON-serializable event payload.
    """
    result = result or {}
    return cast(
        JsonObject,
        {
            "status": status,
            "attempt": attempt,
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "next_retry_seconds": config.retry_interval_seconds
            if status == "waiting"
            else None,
            "region_names": config.region_names,
            "gpu_type_names": config.gpu_type_names,
            "gpu_idle_num": config.gpu_idle_num,
            "instance_num": config.instance_num,
            "running_instances": result.get("running_instances", []),
            "created_instances": result.get("created_instances", []),
        },
    )


def _emit(event: JsonObject, output_format: OutputFormat) -> None:
    """Write an event to stdout.

    Args:
        event: JSON-serializable event payload.
        output_format: Output format.
    """
    if output_format in ("json", "jsonl"):
        print(json_dumps(event), flush=True)
    else:
        print(
            f"[{event['status']}] {event.get('message') or json_dumps(event)}",
            flush=True,
        )
