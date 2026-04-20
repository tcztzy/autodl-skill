"""CLI command for querying AutoDL wallet balance."""

import argparse
from typing import Literal

from autodl.commands._common import (
    OutputFormat,
    add_format_argument,
    emit,
    exit_error,
    json_object,
    redirect_logs_to_stderr,
)
from autodl.types import JsonObject, JsonValue


def get_help() -> str:
    """Return command help text for argparse."""
    return "Query account balance."


def add_arguments(parser: argparse.ArgumentParser) -> None:
    """Register balance subcommand arguments.

    Args:
        parser: Subparser to mutate.
    """
    parser.add_argument("--raw", action="store_true", help="Include raw wallet data.")
    add_format_argument(parser)


def main(raw: bool = False, format: Literal["json", "text"] = "json") -> None:
    """Run the balance command.

    Args:
        raw: Whether to include raw wallet data.
        format: Output format.
    """
    redirect_logs_to_stderr()
    output_format: OutputFormat = format
    try:
        from autodl.client import client

        wallet = client.get_wallet_balance()
        payload = json_object(status="ok", balance=_normalize_balance(wallet))
        if raw:
            payload["raw"] = wallet
        emit(payload, output_format)
    except Exception as e:
        exit_error(e, output_format)


def _normalize_balance(raw: JsonObject) -> JsonObject:
    """Return balance fields with yuan values added.

    Args:
        raw: Wallet payload from AutoDL.

    Returns:
        Normalized balance object.
    """
    return json_object(
        assets_milli_yuan=_int(raw.get("assets", 0)),
        assets_yuan=_yuan(raw.get("assets", 0)),
        accumulate_milli_yuan=_int(raw.get("accumulate", 0)),
        accumulate_yuan=_yuan(raw.get("accumulate", 0)),
        voucher_milli_yuan=_int(raw.get("voucher_balance", 0)),
        voucher_yuan=_yuan(raw.get("voucher_balance", 0)),
    )


def _int(value: JsonValue | None) -> int:
    """Convert an API scalar to int.

    Args:
        value: API scalar.

    Returns:
        Integer value.
    """
    if isinstance(value, list | dict) or value is None:
        raise ValueError(f"Expected scalar amount, got {value!r}")
    return int(value)


def _yuan(value: JsonValue | None) -> float:
    """Convert milli-yuan to yuan.

    Args:
        value: Milli-yuan API scalar.

    Returns:
        Yuan amount.
    """
    return round(_int(value) / 1000, 3)
