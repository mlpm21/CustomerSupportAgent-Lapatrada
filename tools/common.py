"""Shared mock-data utilities.

Purpose:
    Resolve data paths, load JSON, look up customers, and define tool argument/error helpers.

Used with:
    Used by the tool modules; ToolError is handled by the registry.

Notes:
    Missing or unreadable fixtures produce data_unavailable. Paths do not depend on the working directory.
"""

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, JsonValue

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


class ToolArgs(BaseModel):
    """Reject unknown fields and implicit argument coercion."""

    model_config = ConfigDict(extra="forbid", strict=True)


class ToolError(Exception):
    """An expected lookup or fixture failure, exposed as an error code."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def load_data(filename: str) -> dict[str, JsonValue]:
    """Read a project-relative fixture or report unavailable data."""
    try:
        data = json.loads((DATA_DIR / filename).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ToolError("data_unavailable") from exc
    if not isinstance(data, dict):
        raise ToolError("data_unavailable")
    return data


def get_customer(customer_id: str) -> dict[str, JsonValue]:
    """Find a customer without treating missing fixture data as an empty account."""
    records = load_data("customers.json").get("customers")
    if not isinstance(records, list) or any(
        not isinstance(record, dict) or "id" not in record for record in records
    ):
        raise ToolError("data_unavailable")
    for record in records:
        if record["id"] == customer_id:
            return record
    raise ToolError("customer_not_found")
