# Copyright © 2026 Lapatrada Liawpairoj. All rights reserved.
# Provided for recruitment evaluation only. See LICENSE for terms.

"""Real SDK and CLI integration against local-only HTTP response simulations.

No requests reach OpenAI. Scripted proposals exercise plumbing, not model quality.
"""

import json
from pathlib import Path

import httpx2
from openai import OpenAI
import pytest

import agent
import config
import main


SCENARIOS = [
    ("billing", "high", "escalate_to_human", "billing", "en", "pending charges", "pending-charges",
     "These recorded events are pending authorizations, not confirmed captured payments."),
    ("outage", "critical", "escalate_to_human", "infrastructure", "th", "HTTP 500", "http-500",
     "ได้รับข้อมูลปัญหาการเข้าใช้งานแล้ว พบข้อมูลสถานะที่ขัดแย้งกัน"),
    ("how_to", "low", "auto_respond", "none", "en", "dark mode system default", "dark-mode",
     "Check your desktop version and update if needed. Scheduled dark mode is not supported."),
]


def completion(message, finish_reason="stop"):
    """Wrap a scripted message in the API's JSON completion envelope.

    Works with:
        Used by simulated_api() to feed the real SDK's response parser.
    """
    return {"id": "offline-completion", "object": "chat.completion", "created": 0,
            "model": "offline-simulation", "choices": [
                {"index": 0, "finish_reason": finish_reason, "message": message}]}


def simulated_api(ticket_numbers):
    """Create an HTTP handler for tool collection and a structured proposal per ticket.

    Works with:
        handle() runs through MockTransport; test_cli_with_real_sdk() checks the CLI output.
    """
    pending = iter(ticket_numbers)
    state = {"stage": 0, "requests": [], "ticket": None, "calls": []}
    tickets = json.loads((Path(__file__).resolve().parents[1] / "data/tickets.json").read_text())

    def handle(request):
        """Inspect wire requests and return scripted JSON without opening a socket.

        Works with:
            Called by the real SDK via httpx2.MockTransport for both create() and parse().
        """
        assert request.url.host == "offline.invalid"
        body = json.loads(request.content)
        state["requests"].append(body)
        assert body["model"] == "offline-simulation"
        if state["stage"] == 0:
            number = next(pending)
            state["ticket"] = number
            customer = tickets[number - 1]["customer_id"]
            query = SCENARIOS[number - 1][5]
            operations = [("lookup_customer_history", {"customer_id": customer}),
                          ("search_knowledge_base", {"query": query})]
            if number == 1:
                operations.append(("get_billing_events", {"customer_id": customer}))
            if number == 2:
                operations.append(("check_system_status", {"region": "ap-southeast"}))
            assert len(body["tools"]) == 4
            calls = [{"id": f"call-{i}", "type": "function",
                      "function": {"name": name, "arguments": json.dumps(args)}}
                     for i, (name, args) in enumerate(operations)]
            state["calls"] = calls
            state["stage"] = 1
            return httpx2.Response(200, json=completion(
                {"role": "assistant", "content": None, "tool_calls": calls}, "tool_calls"))

        answers = [m for m in body["messages"] if m["role"] == "tool"]
        assert [m["tool_call_id"] for m in answers] == [c["id"] for c in state["calls"]]
        assert all(json.loads(m["content"])["status"] == "success" for m in answers)
        if state["stage"] == 1:
            state["stage"] = 2
            return httpx2.Response(200, json=completion({"role": "assistant", "content": "Evidence collected."}))

        assert "tools" not in body and "tool_choice" not in body
        schema = body["response_format"]["json_schema"]
        assert schema["strict"] is True
        assert set(schema["schema"]["required"]) == set(schema["schema"]["properties"])
        assert {"type": "null"} in schema["schema"]["properties"]["product"]["anyOf"]
        kind, urgency, action, team, language, _, article, draft = SCENARIOS[state["ticket"] - 1]
        proposal = dict(urgency=urgency, product=None, issue_type=kind, sentiment="neutral",
                        language=language, action=action, team=team,
                        secondary_tags=["feature_request"] if state["ticket"] == 3 else [],
                        summary="Scripted integration-test proposal, not a live model result.",
                        kb_article_ids=[article], draft_reply=draft)
        state["stage"] = 0
        return httpx2.Response(200, json=completion({"role": "assistant", "content": json.dumps(proposal)}))

    return handle, state


def install_transport(monkeypatch, handler):
    """Keep the real SDK client while replacing only its HTTP transport.

    Works with:
        Patches agent.OpenAI's constructor for main.main(); real create()/parse() still run.
    """
    monkeypatch.setattr(config, "OPENAI_API_KEY", "offline-placeholder-not-a-secret")
    monkeypatch.setattr(config, "OPENAI_MODEL", "offline-simulation")

    def build_client(**kwargs):
        """Construct a real client with no sockets or retry backoff in these checks.

        Works with:
            Called by agent.run_agent(); injects the handler into OpenAI's HTTP client.
        """
        assert kwargs["timeout"] == config.API_TIMEOUT_SECONDS
        assert kwargs["max_retries"] == 2
        return OpenAI(**(kwargs | {"max_retries": 0}), base_url="https://offline.invalid/v1",
                      http_client=httpx2.Client(transport=httpx2.MockTransport(handler)))

    monkeypatch.setattr(agent, "OpenAI", build_client)


@pytest.mark.parametrize("json_output", [False, True])
def test_cli_with_real_sdk(monkeypatch, capsys, json_output):
    """Run all samples through real SDK parsing, local tools, policy, and CLI output.

    Works with:
        Uses simulated_api(), install_transport(), and main.main(); no real model is called.
    """
    handler, state = simulated_api([1, 2, 3])
    install_transport(monkeypatch, handler)
    args = ["--all", "--verbose"] + (["--json"] if json_output else [])
    assert main.main(args) == 0
    captured = capsys.readouterr()
    assert len(state["requests"]) == 9
    assert "get_billing_events" in captured.err and "check_system_status" in captured.err
    if json_output:
        decisions = json.loads(captured.out)
        for decision, scenario in zip(decisions, SCENARIOS):
            _, urgency, action, team, language, _, article, draft = scenario
            assert (decision["final_urgency"], decision["final_action"], decision["final_team"]) == (urgency, action, team)
            assert decision["final_reply"] == draft and decision["override_reasons"] == []
            assert decision["proposal"]["language"] == language
            assert decision["proposal"]["kb_article_ids"] == [article]
            assert all(t["status"] == "success" for t in decision["tool_calls"])
    else:
        assert captured.out.count(main.SIMULATION) == 3
        assert all(scenario[-1] in " ".join(captured.out.split()) for scenario in SCENARIOS)


@pytest.mark.parametrize("status,error_name", [
    (401, "AuthenticationError"), (403, "PermissionDeniedError"), (404, "NotFoundError"),
    (429, None), (500, None),
])
def test_http_errors_through_real_sdk(monkeypatch, capsys, status, error_name):
    """Verify real HTTP errors map to CLI configuration exits or safe escalations.

    Works with:
        Uses install_transport() and main.main(); SDK converts HTTP statuses into exceptions.
    """
    def handle(request):
        """Return a local error response for the SDK's status handling.

        Works with:
            Invoked by MockTransport installed through install_transport().
        """
        return httpx2.Response(status, json={"error": {"message": "Simulated HTTP error", "type": "test_error"}})

    install_transport(monkeypatch, handle)
    code = main.main(["--ticket", "1", "--json"])
    captured = capsys.readouterr()
    if error_name:
        assert code == 2 and error_name in captured.err and captured.out == ""
        assert "Traceback" not in captured.err
    else:
        assert code == 0
        decision = json.loads(captured.out)
        assert decision["status"] == "failed" and decision["final_action"] == "escalate_to_human"
        assert "api_error" in decision["override_reasons"][0]
