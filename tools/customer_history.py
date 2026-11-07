# Copyright © 2026 Lapatrada Liawpairoj. All rights reserved.
# Provided for recruitment evaluation only. See LICENSE for terms.

"""Customer history lookup tool.

Purpose:
    Return mock customer attributes, support history, and labeled assumptions.

Used with:
    Reads data/customers.json through common.py; registered in tools/__init__.py.

Notes:
    Unknown attributes remain null. No external customer service is contacted.
"""

from pydantic import Field, JsonValue

from tools.common import ToolArgs, ToolError, get_customer

name = "lookup_customer_history"
description = "Look up mock plan, tenure, entitlement, region, and support history. Null means unknown."


class Args(ToolArgs):
    customer_id: str = Field(min_length=1)


def run(customer_id: str) -> dict[str, JsonValue]:
    """Return customer context and labeled assumptions while preserving unknowns.

    Works with:
        Called through execute_tool_call(); uses common.get_customer().
    """

    customer = get_customer(customer_id)

    fields = (
        "plan", "tenure_months", "seats", "region", "entitlement", "past_tickets",
        "usage", "upgrade_attempted", "synthetic_fields", "unknown_fields",
    )

    if any(field not in customer for field in fields):
        raise ToolError("data_unavailable")
    result = {field: customer[field] for field in fields}
    result["sla"] = customer.get("sla")

    for field in ("first_critical_issue", "region_label", "note"):

        if field in customer:
            result[field] = customer[field]
    result["source"] = "Mock customers.json; synthetic_fields lists added facts."
    return result
