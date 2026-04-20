"""Shared command-line helpers."""

import argparse
import logging
import sys
from collections.abc import Sequence
from typing import Literal, Never, cast

from autodl.runtime import logger
from autodl.types import JsonObject
from autodl.utils.helpers import json_dumps

type OutputFormat = Literal["json", "text"]


def add_format_argument(parser: argparse.ArgumentParser) -> None:
    """Register the shared output-format argument.

    Args:
        parser: Subparser to mutate.
    """
    parser.add_argument(
        "--format",
        choices=["json", "text"],
        default="json",
        help="Output format. JSON is stable for agents.",
    )


def redirect_logs_to_stderr() -> None:
    """Keep stdout reserved for command output."""
    for handler in logger.handlers:
        if (
            isinstance(handler, logging.StreamHandler)
            and getattr(handler, "stream", None) is sys.stdout
        ):
            handler.stream = sys.stderr


def emit(payload: JsonObject, output_format: OutputFormat) -> None:
    """Write command output.

    Args:
        payload: JSON-serializable payload.
        output_format: Output format.
    """
    if output_format == "json":
        print(json_dumps(payload), flush=True)
    else:
        print(_text(payload), flush=True)


def exit_error(error: Exception, output_format: OutputFormat) -> Never:
    """Emit a structured error and exit.

    Args:
        error: Exception to report.
        output_format: Output format.

    Raises:
        SystemExit: Always exits with code 2.
    """
    emit(
        cast(
            JsonObject,
            {
                "status": "error",
                "error_type": type(error).__name__,
                "message": str(error),
            },
        ),
        output_format,
    )
    raise SystemExit(2)


def split_values(values: Sequence[str] | None) -> list[str]:
    """Split repeated or comma-separated CLI values.

    Args:
        values: Raw argparse values.

    Returns:
        Non-empty values with whitespace removed.
    """
    if not values:
        return []
    return [
        item.strip() for value in values for item in value.split(",") if item.strip()
    ]


def gb_to_bytes(value: float) -> int:
    """Convert GiB to bytes.

    Args:
        value: Size in GiB.

    Returns:
        Size in bytes.
    """
    return int(value * 1024 * 1024 * 1024)


def _text(payload: JsonObject) -> str:
    """Return a compact text representation.

    Args:
        payload: JSON-serializable payload.

    Returns:
        Human-readable text.
    """
    status = payload.get("status", "ok")
    message = payload.get("message")
    if isinstance(message, str) and message:
        return f"[{status}] {message}"
    return f"[{status}] {json_dumps(payload)}"


def json_object(**values: object) -> JsonObject:
    """Build a typed JSON object.

    Args:
        **values: JSON fields.

    Returns:
        JSON object.
    """
    return cast(JsonObject, dict(values))
