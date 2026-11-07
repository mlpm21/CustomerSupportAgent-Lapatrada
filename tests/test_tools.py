# Copyright © 2026 Lapatrada Liawpairoj. All rights reserved.
# Provided for recruitment evaluation only. See LICENSE for terms.

"""Offline schemas, retrieval, fixture outcomes, and tool access boundaries."""

import json

import pytest

from tools import execute_tool_call, get_tool_schemas


def call(name, args, customer="cust-001"):
    """Execute a registry call with JSON arguments for offline checks.

    Works with:
        Used by tool tests; delegates to execute_tool_call().
    """
    return execute_tool_call("check", name, json.dumps(args), customer)


def test_schemas():
    """Check tool names, required parameters, and argument bounds.

    Works with:
        Run by pytest; exercises get_tool_schemas().
    """
    schemas = {s["function"]["name"]: s["function"]["parameters"] for s in get_tool_schemas()}
    assert set(schemas) == {"lookup_customer_history", "get_billing_events", "search_knowledge_base", "check_system_status"}
    for name, parameter in [("lookup_customer_history", "customer_id"), ("get_billing_events", "customer_id"),
                            ("search_knowledge_base", "query"), ("check_system_status", "region")]:
        assert schemas[name]["required"] == [parameter]
        assert schemas[name]["additionalProperties"] is False
    for name, field, low, high in [("get_billing_events", "days", 1, 90), ("search_knowledge_base", "top_k", 1, 5)]:
        prop = schemas[name]["properties"][field]
        assert (prop["minimum"], prop["maximum"]) == (low, high)


def test_billing_events():
    """Check the sample has three pending authorization events.

    Works with:
        Run by pytest; uses call() to exercise billing.run().
    """
    result = call("get_billing_events", {"customer_id": "cust-001"})
    assert result.status == "success"
    assert len(result.data["events"]) == 3
    assert all(e["status"] == "pending_authorization" and e["amount"] == 29.99 for e in result.data["events"])


def test_customer_region_and_status():
    """Check customer region mapping and conflicting internal/public snapshots.

    Works with:
        Run by pytest; uses call() for customer_history.run() and system_status.run().
    """
    history = call("lookup_customer_history", {"customer_id": "cust-002"}, "cust-002")
    assert history.data["region"] == "ap-southeast" and history.data["sla"] is None
    result = call("check_system_status", {"region": "ap-southeast"})
    assert result.data["internal_status"] == "degraded" and result.data["public_status"] == "operational"


@pytest.mark.parametrize("query,first", [("pending charges", "pending-charges"), ("dark mode system default", "dark-mode")])
def test_search_rankings(query, first):
    """Check relevant billing and dark-mode articles rank first.

    Works with:
        Run by pytest; uses call() to exercise knowledge_base.run().
    """
    result = call("search_knowledge_base", {"query": query})
    assert result.status == "success" and result.data[0]["id"] == first


@pytest.mark.parametrize("query", ["xyzzyflorbnonsense", "what how can you", "what is the weather today"])
def test_empty_search_is_success(query):
    """Check nonsense and filler queries return successful empty results.

    Works with:
        Run by pytest; uses call() to exercise knowledge_base.run().
    """
    result = call("search_knowledge_base", {"query": query})
    assert result.status == "success" and result.data == []


@pytest.mark.parametrize("name,args,customer,code", [
    ("unknown", {}, "cust-001", "unknown_tool"),
    ("get_billing_events", {"customer_id": "cust-001", "days": 0}, "cust-001", "invalid_arguments"),
    ("search_knowledge_base", {"query": "test", "top_k": 6}, "cust-001", "invalid_arguments"),
    ("lookup_customer_history", {"customer_id": "cust-002"}, "cust-001", "customer_scope_violation"),
    ("lookup_customer_history", {"customer_id": "unknown"}, "unknown", "customer_not_found"),
    ("check_system_status", {"region": "unknown"}, "cust-001", "region_not_found"),
    ("get_billing_events", {"customer_id": "cust-002"}, "cust-002", "data_unavailable"),
])
def test_expected_errors(name, args, customer, code):
    """Check expected argument, scope, lookup, and unavailable-data error codes.

    Works with:
        Run by pytest; uses call() to exercise execute_tool_call() and registered tools.
    """
    result = call(name, args, customer)
    assert result.status == "error" and result.error_code == code
    assert result.data is None
    if code == "invalid_arguments":
        assert result.args == {}


def test_malformed_arguments():
    """Check malformed JSON yields an argument error with empty validated arguments.

    Works with:
        Run by pytest; calls execute_tool_call() directly.
    """
    result = execute_tool_call("check", "lookup_customer_history", "not JSON", "cust-001")
    assert result.error_code == "invalid_arguments" and result.args == {}
