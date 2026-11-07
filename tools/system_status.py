# Copyright © 2026 Lapatrada Liawpairoj. All rights reserved.
# Provided for recruitment evaluation only. See LICENSE for terms.

"""Regional system status lookup tool.

Purpose:
    Return a known region’s synthetic internal and public status snapshot.

Used with:
    Uses local STATUS constants; registered in tools/__init__.py.

Notes:
    No live telemetry is fetched. Ages are relative to the mock snapshot; unknown regions return an error.
"""

from copy import deepcopy

from pydantic import Field, JsonValue

from tools.common import ToolArgs, ToolError

name = "check_system_status"
description = "Read synthetic regional internal/public status. Known regions: ap-southeast, us-east, eu-west."

# Age is relative to the mock scenario snapshot, not the execution clock.
STATUS: dict[str, dict[str, JsonValue]] = {
    region: {
        "region": region,
        "internal_status": "degraded" if region == "ap-southeast" else "operational",
        "public_status": "operational",
        "incident_scope": "Gateway HTTP 500 errors affecting enterprise users in ap-southeast."

        if region == "ap-southeast" else "No active incident in this mock snapshot.",
        "internal_age_minutes": 0,
        "public_age_minutes": 0,
        "internal_source": "Synthetic internal incident snapshot",
        "public_source": "Synthetic public status snapshot (not fetched from a website)",
        "note": "All status facts and healthy comparison regions are synthetic; not live telemetry.",
    }
    for region in ("ap-southeast", "us-east", "eu-west")
}


class Args(ToolArgs):
    region: str = Field(min_length=1)

def run(region: str) -> dict[str, JsonValue]:
    """Return a copy of a known synthetic regional snapshot or raise region_not_found.

    Works with:
        Called through execute_tool_call(); reads STATUS and uses deepcopy().
    """

    if region not in STATUS:
        raise ToolError("region_not_found")
    return deepcopy(STATUS[region])
