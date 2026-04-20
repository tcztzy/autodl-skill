"""General-purpose JSON, URL, and datetime helpers."""

import datetime
import json

from autodl.types import JsonValue


def json_dumps(
    obj: object, *, indent: int | str | None = None, ensure_ascii: bool = False
) -> str:
    """Serialize an object as JSON with Unicode preserved by default.

    Args:
        obj: Object to serialize.
        indent: Indentation level for pretty-printed JSON.
        ensure_ascii: Whether non-ASCII characters should be escaped.

    Returns:
        JSON string.
    """
    return json.dumps(obj, indent=indent, ensure_ascii=ensure_ascii)


def url_set_params(url: str, **params: JsonValue) -> str:
    """Set non-null query parameters on a URL.

    Args:
        url: Source URL.
        **params: Query parameter values. Non-scalar values are JSON-encoded.

    Returns:
        URL with merged query parameters.
    """
    import urllib.parse as urlparse
    from urllib.parse import urlencode

    pr = urlparse.urlparse(url)
    query: dict[str, str] = dict(urlparse.parse_qsl(pr.query))
    for name, value in params.items():
        if value is not None:
            if type(value) in (str, int, float):
                query[name] = str(value)
            else:
                query[name] = json_dumps(value)
    prlist = list(pr)
    prlist[4] = urlencode(query)
    return urlparse.ParseResult(*prlist).geturl()


def end_of_day(d: datetime.date | datetime.datetime) -> datetime.datetime:
    """Return the last representable moment of a date's day.

    Args:
        d: Date or datetime to normalize.

    Returns:
        Datetime at 23:59:59.999999 on the same date.

    Raises:
        ValueError: If ``d`` is not a date or datetime.
    """
    if isinstance(d, datetime.date):
        return datetime.datetime.combine(
            d, datetime.time(hour=23, minute=59, second=59, microsecond=999999)
        )
    if isinstance(d, datetime.datetime):
        return d.replace(hour=23, minute=59, second=59, microsecond=999999)
    raise ValueError("Unsupported time type")
