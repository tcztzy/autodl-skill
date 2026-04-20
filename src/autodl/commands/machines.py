"""CLI command for querying idle AutoDL machines."""

import argparse
from collections.abc import Sequence
from typing import Literal, cast

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
from autodl.data_object import Config, RegionList
from autodl.types import JsonObject, JsonValue

MACHINE_FIELDS: tuple[str, ...] = (
    "machine_id",
    "region_name",
    "region_sign",
    "machine_alias",
    "gpu_name",
    "gpu_idle_num",
    "gpu_order_num",
    "gpu_total_num",
    "cpu_num",
    "memory_size",
    "price",
    "max_data_disk_expand_size",
)


def get_help() -> str:
    """Return command help text for argparse."""
    return "List currently orderable machines."


def add_arguments(parser: argparse.ArgumentParser) -> None:
    """Register machines subcommand arguments.

    Args:
        parser: Subparser to mutate.
    """
    parser.add_argument("-r", "--region", action="append", help="Region name/sign.")
    parser.add_argument("-g", "--gpu", action="append", help="GPU type name.")
    parser.add_argument("--idle", type=int, default=1, help="Required idle GPU count.")
    parser.add_argument("--count", type=int, default=10, help="Max machines to return.")
    parser.add_argument(
        "--all",
        action="store_true",
        dest="all_matches",
        help="Return all matches.",
    )
    parser.add_argument(
        "--min-disk-gb",
        type=float,
        default=0,
        help="Minimum expandable data disk size in GiB.",
    )
    parser.add_argument("--raw", action="store_true", help="Include raw machine data.")
    add_format_argument(parser)


def main(
    region: Sequence[str] | None = None,
    gpu: Sequence[str] | None = None,
    idle: int = 1,
    count: int = 10,
    all_matches: bool = False,
    min_disk_gb: float = 0,
    raw: bool = False,
    format: Literal["json", "text"] = "json",
) -> None:
    """Run the machines command.

    Args:
        region: Region name or sign filters.
        gpu: GPU type filters.
        idle: Required idle GPU count.
        count: Maximum machines to return.
        all_matches: Whether to return all matches.
        min_disk_gb: Minimum expandable data disk size in GiB.
        raw: Whether to include raw machine records.
        format: Output format.
    """
    redirect_logs_to_stderr()
    output_format: OutputFormat = format
    try:
        from autodl.client import get_available_machines

        config = Config()
        _validate_limits(idle, count, min_disk_gb)
        region_filters = split_values(region) or config.region_names
        gpu_names = split_values(gpu) or config.gpu_type_names
        if not gpu_names:
            raise ValueError("--gpu is required when config has no gpu_type_names")
        region_signs = _resolve_region_signs(region_filters)
        machines = get_available_machines(
            region_signs,
            gpu_names,
            gpu_idle_num=idle,
            count=None if all_matches else count,
            min_expand_data_disk=gb_to_bytes(min_disk_gb),
        )
        emit(
            json_object(
                status="ok",
                query=json_object(
                    region=region_filters,
                    region_signs=region_signs,
                    gpu=gpu_names,
                    idle=idle,
                    count=None if all_matches else count,
                    min_disk_gb=min_disk_gb,
                ),
                machines=[
                    _machine_summary(machine, include_raw=raw) for machine in machines
                ],
            ),
            output_format,
        )
    except Exception as e:
        exit_error(e, output_format)


def _validate_limits(idle: int, count: int, min_disk_gb: float) -> None:
    """Validate numeric query limits.

    Args:
        idle: Required idle GPU count.
        count: Maximum matches.
        min_disk_gb: Minimum expandable data disk in GiB.

    Raises:
        ValueError: If an argument is invalid.
    """
    if idle <= 0:
        raise ValueError("--idle must be greater than 0")
    if count <= 0:
        raise ValueError("--count must be greater than 0")
    if min_disk_gb < 0:
        raise ValueError("--min-disk-gb must not be negative")


def _resolve_region_signs(region_filters: Sequence[str]) -> list[str]:
    """Resolve region names or signs into signs accepted by the machine API.

    Args:
        region_filters: Region names or signs. Empty means all visible regions.

    Returns:
        Region signs.

    Raises:
        ValueError: If a region filter is unknown.
    """
    regions = RegionList.fetch().regions
    if not region_filters:
        return [
            sign
            for region in regions
            for sign in cast(list[str], region["region_sign"])
        ]
    signs: list[str] = []
    unknown: list[str] = []
    for value in region_filters:
        matched = False
        for region in regions:
            region_signs = cast(list[str], region["region_sign"])
            if value == region["region_name"]:
                signs.extend(region_signs)
                matched = True
            elif value in region_signs:
                signs.append(value)
                matched = True
        if not matched:
            unknown.append(value)
    if unknown:
        raise ValueError(f"Unknown region: {', '.join(unknown)}")
    return list(dict.fromkeys(signs))


def _machine_summary(machine: JsonObject, *, include_raw: bool) -> JsonObject:
    """Return stable fields from a machine payload.

    Args:
        machine: Raw machine record.
        include_raw: Whether to include the raw record.

    Returns:
        Machine summary.
    """
    summary: JsonObject = {
        field: cast(JsonValue, machine[field])
        for field in MACHINE_FIELDS
        if field in machine
    }
    if include_raw:
        summary["raw"] = machine
    return summary
