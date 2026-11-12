"""Input files (JSON or CSV) parsed into source rows. The item count of a contract comes
from here, in code, never from a model."""

import csv
import io
import json
from typing import Any

MAX_SOURCE_BYTES = 1024 * 1024


class SourceFileInvalid(ValueError):
    pass


def parse_rows(content: bytes, filename: str) -> list[dict[str, Any]]:
    """Rows of a `.json` file (an array of objects, or an object holding exactly one such
    array) or a `.csv` file with a header row."""
    if len(content) > MAX_SOURCE_BYTES:
        raise SourceFileInvalid("The file is larger than 1 MB.")
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise SourceFileInvalid("The file isn't UTF-8 text.") from None
    extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if extension == "json":
        rows = _json_rows(text)
    elif extension == "csv":
        rows = _csv_rows(text)
    else:
        raise SourceFileInvalid("Attach a .json or .csv file.")
    if not rows:
        raise SourceFileInvalid("The file has no rows.")
    return rows


def columns(rows: list[dict[str, Any]]) -> list[str]:
    """Column names in first-seen order."""
    return list(dict.fromkeys(key for row in rows for key in row))


def _json_rows(text: str) -> list[dict[str, Any]]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise SourceFileInvalid(f"The JSON isn't valid (line {exc.lineno}).") from None
    if isinstance(data, dict):
        lists = [value for value in data.values() if isinstance(value, list)]
        if len(lists) != 1:
            raise SourceFileInvalid("The JSON must be an array of objects.")
        data = lists[0]
    if not isinstance(data, list) or not all(isinstance(row, dict) for row in data):
        raise SourceFileInvalid("The JSON must be an array of objects.")
    return data


def _csv_rows(text: str) -> list[dict[str, Any]]:
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise SourceFileInvalid("The CSV has no header row.")
    rows = []
    for row in reader:
        if None in row:
            raise SourceFileInvalid(f"Row {reader.line_num} has more values than the header.")
        cleaned = {key.strip(): (value or "").strip() for key, value in row.items()}
        if any(cleaned.values()):
            rows.append(cleaned)
    return rows
