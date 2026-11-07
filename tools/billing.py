# Copyright © 2026 Lapatrada Liawpairoj. All rights reserved.
# Provided for recruitment evaluation only. See LICENSE for terms.

"""Billing event lookup tool.

Purpose:
    Filter mock customer billing events by a bounded day window.

Used with:
    Reads nested events in data/customers.json; registered in tools/__init__.py.

Notes:
    Event ages are relative to the ticket snapshot. Pending authorizations are not captured payments.
"""

from pydantic import Field, JsonValue

from tools.common import ToolArgs, ToolError, get_customer

name = "get_billing_events"
description = "Read mock billing events within the last 1–90 days of the ticket snapshot."


class Args(ToolArgs):
    customer_id: str = Field(min_length=1)
    days: int = Field(default=30, ge=1, le=90)


def run(customer_id: str, days: int = 30) -> dict[str, JsonValue]:
    """Return known billing events within the requested snapshot-relative day window.

    Works with:
        Called through execute_tool_call(); uses common.get_customer() and raises ToolError for unavailable records.
    """

    events = get_customer(customer_id).get("billing_events")
    required = {"age_minutes", "amount", "currency", "status", "card_reference"}

    if not isinstance(events, list) or any(
        not isinstance(event, dict)
        or not required.issubset(event)
        or not isinstance(event["age_minutes"], (int, float))
        or event["age_minutes"] < 0
        or any(event[field] is None for field in required)
        for event in events
    ):

        raise ToolError("data_unavailable")
    return {
        "events": [event for event in events if event["age_minutes"] <= days * 1440],
        "source": "Synthetic billing fixture; ages are relative to the ticket snapshot.",
    }
