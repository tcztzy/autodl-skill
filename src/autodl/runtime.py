"""Runtime directories and process-wide logger."""

import datetime
import os
from pathlib import Path
from urllib.parse import unquote, urlparse

from autodl.utils.logging import get_logger

_SOURCE_ROOT: Path = Path(__file__).resolve().parents[1]
BASE_DIR: str = os.getenv(
    "AUTODL_BASE_DIR",
    str(_SOURCE_ROOT if (_SOURCE_ROOT / "pyproject.toml").exists() else Path.cwd()),
)
DATA_DIR: str = os.getenv("AUTODL_DATA_DIR", os.path.join(BASE_DIR, "runtime", "data"))
LOGS_DIR: str = os.getenv("AUTODL_LOGS_DIR", os.path.join(BASE_DIR, "runtime", "logs"))

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(LOGS_DIR, exist_ok=True)

logger = get_logger(__name__, LOGS_DIR)


def _path_segment(value: str) -> str:
    """Return a filesystem-safe path segment.

    Args:
        value: Raw URL path segment.

    Returns:
        Sanitized path segment.
    """
    segment = unquote(value).strip()
    return segment.replace(":", "_") or "_"


def _api_path_parts(path: str) -> list[str]:
    """Return storage path parts for an API URL path.

    Args:
        path: Parsed URL path.

    Returns:
        Path segments with a leading ``/api/v1`` prefix removed.
    """
    parts = [_path_segment(part) for part in path.split("/") if part]
    if parts[:2] == ["api", "v1"]:
        parts = parts[2:]
    return parts or ["_"]


def save_api_response(
    method: str, url: str, content: bytes, *, content_type: str | None = None
) -> Path:
    """Persist a raw API response using a URL-shaped runtime path.

    Args:
        method: HTTP method used for the request.
        url: Final request URL, including host and query string.
        content: Raw response bytes.
        content_type: Optional response content type.

    Returns:
        Path to the saved response file.
    """
    parsed = urlparse(url)
    parts = _api_path_parts(parsed.path)
    timestamp = datetime.datetime.now(datetime.UTC).strftime("%Y%m%dT%H%M%S.%fZ")
    extension = "json" if content_type and "json" in content_type.lower() else "txt"
    path = Path(DATA_DIR, *parts, f"{timestamp}.{extension}")
    path.parent.mkdir(parents=True, exist_ok=True)
    logger.debug("saving %s response to %s", method.upper(), path)
    path.write_bytes(content)
    return path
