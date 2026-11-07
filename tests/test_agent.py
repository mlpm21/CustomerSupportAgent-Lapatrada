# Copyright © 2026 Lapatrada Liawpairoj. All rights reserved.
# Provided for recruitment evaluation only. See LICENSE for terms.

"""Scripted client checks; no real OpenAI client or network is used."""

from copy import deepcopy
import json
from types import SimpleNamespace as NS

import pytest
from openai import APIConnectionError, AuthenticationError, PermissionDeniedError, NotFoundError
from pydantic import ValidationError

import config
from agent import run_agent
from models import Ticket, TriageResult
from policy import ENGLISH_ACK, apply_policy


def ticket():
    """Build a small ticket for scripted agent tests.

    Works with:
        Used by the test functions when calling run_agent() or apply_policy().
    """
    return Ticket(id="example", customer_id="cust-001", messages=[
        {"text": "Please check the pending payment.", "relative_time": "just now"}])


def proposal():
    """Build a valid hand-written triage proposal.

    Works with:
        Used by response() callers and agent assertions to supply structured output.
    """
    return TriageResult(urgency="high", product=None, issue_type="billing", sentiment="frustrated",
                        language="en", action="escalate_to_human", team="billing", secondary_tags=[],
                        summary="Pending payment.", kb_article_ids=["pending-charges"], draft_reply="Tailored draft.")


def tool_call(call_id, name, args):
    """Build a fake function call with JSON arguments and a call ID.

    Works with:
        Used by agent tests to construct calls passed to response().
    """
    return NS(id=call_id, function=NS(name=name, arguments=json.dumps(args)))


def response(calls=(), parsed=None, refusal=None):
    """Build the completion/message shape consumed by the agent.

    Works with:
        Used by tests to script ScriptedClient.create() and parse() responses.
    """
    message = NS(content="Evidence collected.", tool_calls=list(calls), parsed=parsed, refusal=refusal)
    return NS(choices=[NS(message=message, finish_reason="tool_calls" if calls else "stop")])


class ScriptedClient:
    """Only implement the two completion methods used by agent.py."""

    def __init__(self, creates, parses=()):
        """Prepare scripted response iterators and the fake completion interface.

        Works with:
            Binds create() and parse(); tests inject this ScriptedClient into run_agent().
        """
        self.creates = iter(creates)
        self.parses = iter(parses)
        self.requests = []
        self.chat = NS(completions=NS(create=self.create, parse=self.parse))

    def take(self, method, items, kwargs):
        """Record a request and return or raise the next scripted item.

        Works with:
            Shared helper used by ScriptedClient.create() and parse().
        """
        self.requests.append((method, deepcopy(kwargs)))
        item = next(items)
        if isinstance(item, Exception):
            raise item
        return item

    def create(self, **kwargs):
        """Return the next scripted tool-collection response.

        Works with:
            Called by agent._collect_and_propose(); delegates to take().
        """
        return self.take("create", self.creates, kwargs)

    def parse(self, **kwargs):
        """Return the next scripted structured-output response.

        Works with:
            Called by agent._structured_proposal(); delegates to take().
        """
        return self.take("parse", self.parses, kwargs)


def test_successful_flow(monkeypatch):
    """Check ordered tool results, exact call answers, and structured output without credentials.

    Works with:
        Uses ScriptedClient and run_agent(); policy assertions also use apply_policy() where applicable.
    """
    monkeypatch.setattr(config, "OPENAI_API_KEY", "")
    monkeypatch.setattr(config, "OPENAI_MODEL", "")
    calls = [tool_call("h", "lookup_customer_history", {"customer_id": "cust-001"}),
             tool_call("k", "search_knowledge_base", {"query": "pending charges"})]
    client = ScriptedClient([response(calls), response()], [response(parsed=proposal())])
    result = run_agent(ticket(), client=client)
    assert result.failure_reason is None and result.proposal == proposal()
    assert [r.call_id for r in result.tool_results] == ["h", "k"]
    assert all(r.status == "success" for r in result.tool_results)
    final = client.requests[-1][1]
    answers = [m for m in final["messages"] if m["role"] == "tool"]
    assert [m["tool_call_id"] for m in answers] == ["h", "k"]
    assert [json.loads(m["content"])["call_id"] for m in answers] == ["h", "k"]
    assert final["response_format"] is TriageResult
    assert "tools" not in final and "tool_choice" not in final


def test_unknown_tool_still_answered():
    """Check that an unknown tool receives an error result and matching tool message.

    Works with:
        Uses ScriptedClient and run_agent(); policy assertions also use apply_policy() where applicable.
    """
    client = ScriptedClient([response([tool_call("u", "unknown", {})]), response()], [response(parsed=proposal())])
    result = run_agent(ticket(), client=client)
    assert result.tool_results[0].error_code == "unknown_tool"
    answer = next(m for m in client.requests[-1][1]["messages"] if m["role"] == "tool")
    assert answer["tool_call_id"] == "u" and json.loads(answer["content"])["error_code"] == "unknown_tool"


@pytest.mark.parametrize("during_parse", [False, True])
def test_api_error_becomes_safe_escalation(during_parse):
    """Check API failures in collection or parsing become a safe human escalation.

    Works with:
        Uses ScriptedClient and run_agent(); policy assertions also use apply_policy() where applicable.
    """
    error = APIConnectionError(request=NS())
    client = ScriptedClient([response()] if during_parse else [error], [error] if during_parse else [])
    result = run_agent(ticket(), client=client)
    assert result.failure_reason == "api_error"
    decision = apply_policy(ticket(), result)
    assert decision.final_action == "escalate_to_human" and decision.final_reply == ENGLISH_ACK
    assert decision.status == "failed"


def test_invalid_output_repair_limit():
    """Check invalid proposals stop after the configured number of repair attempts.

    Works with:
        Uses ScriptedClient and run_agent(); policy assertions also use apply_policy() where applicable.
    """
    try:
        TriageResult.model_validate({})
    except ValidationError as exc:
        error = exc
    attempts = config.MAX_STRUCTURED_OUTPUT_REPAIR_ATTEMPTS + 1
    client = ScriptedClient([response()], [error] * attempts)
    result = run_agent(ticket(), client=client)
    assert result.failure_reason == "invalid_output"
    parses = [kwargs for method, kwargs in client.requests if method == "parse"]
    assert len(parses) == attempts
    if attempts > 1:
        assert "validation_error" in parses[-1]["messages"][-1]["content"]


def test_exhausted_rounds_still_propose_but_block_auto_response():
    """Check exhausted rounds still propose and route complete evidence to a specialist.

    Works with:
        Uses ScriptedClient and run_agent(); policy assertions also use apply_policy() where applicable.
    """
    call = tool_call("repeat", "lookup_customer_history", {"customer_id": "cust-001"})
    auto = TriageResult.model_validate(proposal().model_dump() | {
        "urgency": "low", "issue_type": "how_to", "action": "auto_respond", "team": "none"})
    kb = tool_call("kb", "search_knowledge_base", {"query": "pending charges"})
    client = ScriptedClient([response([call, kb])] * config.MAX_TOOL_ROUNDS, [response(parsed=auto)])
    result = run_agent(ticket(), client=client)
    assert result.failure_reason is None and result.tool_budget_exhausted
    assert result.proposal == auto
    assert len(result.tool_results) == 2 * config.MAX_TOOL_ROUNDS
    assert [method for method, _ in client.requests] == ["create"] * config.MAX_TOOL_ROUNDS + ["parse"]
    decision = apply_policy(ticket(), result)
    assert decision.final_action == "route_to_specialist" and decision.status == "completed"
    assert any("Tool-round limit" in reason for reason in decision.override_reasons)
    assert not any("Missing" in reason or "Invalid KB" in reason for reason in decision.override_reasons)


@pytest.mark.parametrize("during_parse", [False, True])
@pytest.mark.parametrize("error_type,code", [(AuthenticationError, 401), (PermissionDeniedError, 403), (NotFoundError, 404)])
def test_configuration_errors_propagate(during_parse, error_type, code):
    """Check rejected credentials, permissions, and models propagate instead of becoming ticket failures.

    Works with:
        Uses ScriptedClient and run_agent(); policy assertions also use apply_policy() where applicable.
    """
    error = error_type("configuration rejected", response=NS(request=NS(), status_code=code, headers={}), body=None)
    client = ScriptedClient([response()] if during_parse else [error], [error] if during_parse else [])
    with pytest.raises(error_type):
        run_agent(ticket(), client=client)


@pytest.mark.parametrize("during_parse", [False, True])
def test_refusal(during_parse):
    """Check refusals during collection or parsing are recorded explicitly.

    Works with:
        Uses ScriptedClient and run_agent(); policy assertions also use apply_policy() where applicable.
    """

    refusal = response(refusal="Cannot comply.")
    client = ScriptedClient([response()] if during_parse else [refusal], [refusal] if during_parse else [])
    assert run_agent(ticket(), client=client).failure_reason == "refusal"


def test_unexpected_bug_propagates():
    """Check programming errors propagate instead of being hidden as API failures.

    Works with:
        Uses ScriptedClient and run_agent(); policy assertions also use apply_policy() where applicable.
    """

    client = ScriptedClient([RuntimeError("programming bug")])
    with pytest.raises(RuntimeError, match="programming bug"):
        run_agent(ticket(), client=client)
