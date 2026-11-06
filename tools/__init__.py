"""Tool registry and execution boundary.

Purpose:
    Expose generated tool schemas, validate arguments, enforce customer scope, and record outcomes.

Used with:
    Registers the four tool modules and returns models.ToolResult to agent.py.

Notes:
    Expected failures become error results; unexpected programming errors can propagate.
"""

from pydantic import ValidationError

from models import ToolResult
from tools import billing, customer_history, knowledge_base, system_status
from tools.common import ToolError

TOOLS = {
    tool.name: tool
    for tool in (customer_history, billing, knowledge_base, system_status)
}


def get_tool_schemas() -> list[dict]:
    """Generate function-tool definitions from each registered argument model."""
    return [
        {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.Args.model_json_schema(),
            },
        }
        for tool in TOOLS.values()
    ]


def execute_tool_call(
    call_id: str, name: str, raw_arguments: str, ticket_customer_id: str
) -> ToolResult:
    """Return an outcome for every expected failure; let programming bugs surface."""
    tool = TOOLS.get(name)
    if tool is None:
        return ToolResult(call_id=call_id, tool_name=name, args={}, status="error", error_code="unknown_tool")
    try:
        args = tool.Args.model_validate_json(raw_arguments).model_dump(mode="json")
    except ValidationError:
        return ToolResult(call_id=call_id, tool_name=name, args={}, status="error", error_code="invalid_arguments")
    if "customer_id" in args and args["customer_id"] != ticket_customer_id:
        return ToolResult(call_id=call_id, tool_name=name, args=args, status="error", error_code="customer_scope_violation")
    try:
        data = tool.run(**args)
    except ToolError as exc:
        return ToolResult(call_id=call_id, tool_name=name, args=args, status="error", error_code=exc.code)
    return ToolResult(call_id=call_id, tool_name=name, args=args, status="success", data=data)
