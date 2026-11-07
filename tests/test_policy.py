# Copyright © 2026 Lapatrada Liawpairoj. All rights reserved.
# Provided for recruitment evaluation only. See LICENSE for terms.

"""Final policy checks using real local tool evidence and hand-written proposals."""

import json
from pathlib import Path

import pytest

from models import AgentRun, Ticket, ToolResult, TriageResult
from policy import ENGLISH_ACK, THAI_ACK, apply_policy
from tools import execute_tool_call


def ticket(number=3):
    """Load one original sample as a validated Ticket.

    Works with:
        Used by evidence(), decide(), and policy test functions.
    """
    records = json.loads((Path(__file__).resolve().parents[1] / "data/tickets.json").read_text())
    return Ticket.model_validate(records[number - 1])


def proposal(**changes):
    """Build a valid hand-written proposal with optional field changes.

    Works with:
        Used by policy tests before decide() or apply_policy().
    """
    fields = dict(urgency="low", product=None, issue_type="how_to", sentiment="neutral",
                  language="en", action="auto_respond", team="none", secondary_tags=[],
                  summary="Relevant documentation found.", kb_article_ids=["dark-mode"],
                  draft_reply="Check the desktop version and update if needed.")
    return TriageResult(**(fields | changes))


def evidence(t, query="dark mode system default", extra=()):
    """Collect real local customer, KB, and optional domain tool results.

    Works with:
        Calls execute_tool_call(); results feed decide() and apply_policy().
    """
    calls = [("lookup_customer_history", {"customer_id": t.customer_id}),
             ("search_knowledge_base", {"query": query}), *extra]
    return [execute_tool_call(str(i), name, json.dumps(args), t.customer_id)
            for i, (name, args) in enumerate(calls)]


def decide(p, t=None, results=None):
    """Apply policy to a proposal with supplied or default real tool evidence.

    Works with:
        Uses ticket(), evidence(), and apply_policy(); called by policy test functions.
    """
    t = t or ticket()
    return apply_policy(t, AgentRun(proposal=p, tool_results=evidence(t) if results is None else results))


@pytest.mark.parametrize("number,urgency,kind,action,team,language,query,article,extra", [
    (1, "high", "billing", "escalate_to_human", "billing", "en", "pending charges", "pending-charges",
     [("get_billing_events", {"customer_id": "cust-001"})]),
    (2, "critical", "outage", "escalate_to_human", "infrastructure", "th", "HTTP 500", "http-500",
     [("check_system_status", {"region": "ap-southeast"})]),
    (3, "low", "how_to", "auto_respond", "none", "en", "dark mode system default", "dark-mode", []),
])
def test_base_decisions(number, urgency, kind, action, team, language, query, article, extra):
    """Verify all three expected sample decisions retain tailored drafts without overrides.

    Works with:
        Run by pytest; exercises apply_policy() with local builders or the fixed acknowledgment constants.
    """
    t = ticket(number)
    draft = "คำตอบที่ปรับตามปัญหาของคุณ" if language == "th" else "Tailored customer reply."
    p = proposal(urgency=urgency, issue_type=kind, action=action, team=team,
                 language=language, kb_article_ids=[article], draft_reply=draft)
    d = decide(p, t, evidence(t, query, extra))
    assert (d.final_urgency, d.final_action, d.final_team) == (urgency, action, team)
    assert d.final_reply == draft
    assert d.override_reasons == []
    assert d.status == "completed"


def test_critical_escalates_without_changing_urgency():
    """Verify critical urgency raises action while preserving urgency.

    Works with:
        Run by pytest; exercises apply_policy() with local builders or the fixed acknowledgment constants.
    """
    d = decide(proposal(urgency="critical"))
    assert d.final_action == "escalate_to_human"
    assert d.final_urgency == "critical"
    assert d.final_reply == ENGLISH_ACK
    assert any("Critical" in r for r in d.override_reasons)


@pytest.mark.parametrize("kind,urgency,expected,team,extra", [
    ("billing", "high", "escalate_to_human", "billing", [("get_billing_events", {"customer_id": "cust-001"})]),
    ("billing", "medium", "escalate_to_human", "billing", [("get_billing_events", {"customer_id": "cust-001"})]),
    ("outage", "medium", "route_to_specialist", "infrastructure", [("check_system_status", {"region": "ap-southeast"})]),
])
def test_financial_and_outage_routing(kind, urgency, expected, team, extra):
    """Verify financial-risk and outage routing with actual domain tool results.

    Works with:
        Run by pytest; exercises apply_policy() with local builders or the fixed acknowledgment constants.
    """
    t = ticket(2 if kind == "outage" else 1)
    d = decide(proposal(issue_type=kind, urgency=urgency), t, evidence(t, extra=extra))
    assert (d.final_action, d.final_team, d.final_urgency) == (expected, team, urgency)
    assert d.final_reply == ENGLISH_ACK


def billing_result(*events):
    """Build synthetic pending billing events for isolated repeat-charge edge cases.

    Works with:
        Used by repeated-charge tests alongside evidence() and decide().
    """
    data = {"events": [{"age_minutes": age, "amount": amount, "currency": "USD", "status": "pending_authorization",
                        "card_reference": "card ending 0000"} for age, amount in events], "source": "test"}
    return ToolResult(call_id="b", tool_name="get_billing_events", args={"customer_id": "cust-001"},
                      status="success", data=data)


@pytest.mark.parametrize("events,expected", [
    ([(60, 29.99)], "route_to_specialist"),
    ([(60, 29.99), (120, 9.99)], "route_to_specialist"),
    ([(60, 29.99), (60 + 31 * 1440, 29.99)], "route_to_specialist"),
    ([(60, 29.99), (120, 29.99)], "escalate_to_human"),
])
def test_repeated_charges_escalate_regardless_of_urgency(events, expected):
    """Verify repeat-charge amounts and time windows affect escalation independently of urgency.

    Works with:
        Run by pytest; exercises apply_policy() with local builders or the fixed acknowledgment constants.
    """
    t = ticket(1)
    d = decide(proposal(issue_type="billing", urgency="medium"), t, evidence(t) + [billing_result(*events)])
    assert (d.final_action, d.final_team) == (expected, "billing")
    assert any("Repeated" in r for r in d.override_reasons) == (expected == "escalate_to_human")


@pytest.mark.parametrize("kind,missing", [("billing", "get_billing_events"), ("outage", "check_system_status")])
@pytest.mark.parametrize("secondary", [False, True])
def test_missing_domain_evidence(kind, missing, secondary):
    """Verify missing billing or status evidence is detected for primary and secondary issues.

    Works with:
        Run by pytest; exercises apply_policy() with local builders or the fixed acknowledgment constants.
    """
    p = proposal(issue_type="how_to" if secondary else kind, secondary_tags=[kind] if secondary else [])
    d = decide(p)
    assert d.final_action == "escalate_to_human"
    assert any(missing in r for r in d.override_reasons)


@pytest.mark.parametrize("missing", ["lookup_customer_history", "search_knowledge_base"])
def test_missing_always_required_evidence(missing):
    """Verify customer history and KB success are required.

    Works with:
        Run by pytest; exercises apply_policy() with local builders or the fixed acknowledgment constants.
    """
    results = [r for r in evidence(ticket()) if r.tool_name != missing]
    d = decide(proposal(), results=results)
    assert d.final_action == "escalate_to_human"
    assert any(missing in r for r in d.override_reasons)


def test_invalid_article_id():
    """Verify uncited-in-results KB IDs cause escalation.

    Works with:
        Run by pytest; exercises apply_policy() with local builders or the fixed acknowledgment constants.
    """
    d = decide(proposal(kb_article_ids=["invented-article"]))
    assert d.final_action == "escalate_to_human"
    assert any("invented-article" in r for r in d.override_reasons)


def test_no_article_routes_to_product_support():
    """Verify an auto-response without KB IDs routes to product support.

    Works with:
        Run by pytest; exercises apply_policy() with local builders or the fixed acknowledgment constants.
    """
    d = decide(proposal(kb_article_ids=[]))
    assert (d.final_action, d.final_team) == ("route_to_specialist", "product_support")


@pytest.mark.parametrize("urgency", ["low", "medium", "high", "critical"])
def test_action_never_lowered_and_urgency_unchanged(urgency):
    """Verify policy never reduces a proposed human escalation or changes urgency.

    Works with:
        Run by pytest; exercises apply_policy() with local builders or the fixed acknowledgment constants.
    """
    d = decide(proposal(urgency=urgency, action="escalate_to_human", team="product_support"))
    assert d.final_action == "escalate_to_human"
    assert d.final_urgency == urgency
    assert d.override_reasons == []


@pytest.mark.parametrize("kind,team,extra", [
    ("billing", "billing", [("get_billing_events", {"customer_id": "cust-001"})]),
    ("outage", "infrastructure", [("check_system_status", {"region": "ap-southeast"})]),
])
def test_team_only_correction_keeps_draft(kind, team, extra):
    """Verify domain team corrections preserve the tailored reply.

    Works with:
        Run by pytest; exercises apply_policy() with local builders or the fixed acknowledgment constants.
    """
    t = ticket(2 if kind == "outage" else 1)
    p = proposal(issue_type=kind, action="escalate_to_human", team="product_support")
    d = decide(p, t, evidence(t, extra=extra))
    assert d.final_team == team and d.final_reply == p.draft_reply
    assert len(d.override_reasons) == 1 and "Team corrected" in d.override_reasons[0]


def test_none_team_and_empty_draft():
    """Verify non-auto team normalization and empty-draft replacement.

    Works with:
        Run by pytest; exercises apply_policy() with local builders or the fixed acknowledgment constants.
    """
    p = proposal(action="route_to_specialist", team="none")
    d = decide(p)
    assert d.final_team == "product_support" and d.final_reply == p.draft_reply
    empty = decide(proposal(draft_reply=" "))
    assert empty.final_reply == ENGLISH_ACK
    assert any("Empty draft" in r for r in empty.override_reasons)


@pytest.mark.parametrize("number,language,ack", [(1, "en", ENGLISH_ACK), (2, "th", THAI_ACK), (2, "unknown", THAI_ACK)])
@pytest.mark.parametrize("with_proposal", [False, True])
def test_failed_run(number, language, ack, with_proposal):
    """Verify run failures produce the proper safe English or Thai escalation.

    Works with:
        Run by pytest; exercises apply_policy() with local builders or the fixed acknowledgment constants.
    """
    p = proposal(language=language) if with_proposal else None
    d = apply_policy(ticket(number), AgentRun(proposal=p, failure_reason="api_error"))
    assert (d.final_action, d.final_team, d.final_urgency, d.status) == (
        "escalate_to_human", "product_support", None, "failed")
    assert d.final_reply == ack and "api_error" in d.override_reasons[0]


def test_no_proposal_is_a_failure():
    """Verify missing proposals produce a failed decision rather than fabricated fields.

    Works with:
        Run by pytest; exercises apply_policy() with local builders or the fixed acknowledgment constants.
    """
    d = apply_policy(ticket(1), AgentRun())
    assert d.status == "failed" and d.final_reply == ENGLISH_ACK
    assert "missing_proposal" in d.override_reasons[0]


def test_acknowledgments_do_not_make_promises():
    """Check fixed acknowledgments omit refund and compensation wording.

    Works with:
        Run by pytest; exercises apply_policy() with local builders or the fixed acknowledgment constants.
    """
    for ack in (ENGLISH_ACK, THAI_ACK):
        for phrase in ("refund", "credit", "reversal", "eta", "compensation", "คืนเงิน", "ชดเชย"):
            assert phrase not in ack.casefold()


def test_exhausted_tool_budget_blocks_auto_response():
    """Verify a budget flag alone blocks auto-response despite complete evidence.

    Works with:
        Run by pytest; exercises apply_policy() with local builders or the fixed acknowledgment constants.
    """
    t = ticket()
    d = apply_policy(t, AgentRun(proposal=proposal(), tool_results=evidence(t), tool_budget_exhausted=True))
    assert (d.final_action, d.final_team, d.status) == ("route_to_specialist", "product_support", "completed")
    assert any("Tool-round limit" in r for r in d.override_reasons)
    assert d.final_reply == ENGLISH_ACK


@pytest.mark.parametrize("statuses,currencies,expected", [
    (["failed", "failed"], ["USD", "USD"], "route_to_specialist"),
    (["captured", "refunded"], ["USD", "USD"], "route_to_specialist"),
    (["refunded", "refunded"], ["USD", "USD"], "route_to_specialist"),
    (["pending_authorization", "captured"], ["USD", "USD"], "escalate_to_human"),
    (["captured", "captured"], ["USD", "USD"], "escalate_to_human"),
    (["pending_authorization", "pending_authorization"], ["USD", "EUR"], "route_to_specialist"),
])

def test_repeated_charge_status_and_currency_filter(statuses, currencies, expected):
    """Verify failed/refunded events and different currencies do not trigger repeated-charge escalation.

    Works with:
        Run by pytest; exercises apply_policy() with local builders or the fixed acknowledgment constants.
    """

    t = ticket(1)
    result = billing_result((60, 29.99), (120, 29.99))

    for event, status, currency in zip(result.data["events"], statuses, currencies):
        event.update(status=status, currency=currency)
    d = decide(proposal(issue_type="billing", urgency="medium"), t, evidence(t) + [result])

    assert (d.final_action, d.final_team) == (expected, "billing")
    assert any("Repeated" in reason for reason in d.override_reasons) == (expected == "escalate_to_human")


@pytest.mark.parametrize("secondary", [False, True])
def test_wrong_region_status_is_not_outage_evidence(secondary):
    """Reject successful status calls for another region, including secondary outages.

    Works with:
        Uses evidence() and decide() to exercise apply_policy() with real tool results.
    """
    t = ticket(2)
    results = evidence(t, extra=[("check_system_status", {"region": "us-east"})])
    p = proposal(issue_type="how_to" if secondary else "outage",
                 secondary_tags=["outage"] if secondary else [],
                 action="route_to_specialist", team="infrastructure", language="th")
    d = decide(p, t, results)
    assert d.final_action == "escalate_to_human"
    assert any("check_system_status" in reason and "ap-southeast" in reason for reason in d.override_reasons)
    assert d.final_reply == THAI_ACK


def test_matching_customer_region_status_is_accepted():
    """Accept matching regional evidence even when an unrelated region was also checked.

    Works with:
        Uses real execute_tool_call() results via evidence(), then decide()/apply_policy().
    """
    t = ticket(2)
    results = evidence(t, extra=[("check_system_status", {"region": "us-east"}),
                                 ("check_system_status", {"region": "ap-southeast"})])
    p = proposal(issue_type="outage", action="route_to_specialist", team="infrastructure")
    d = decide(p, t, results)
    assert d.final_action == p.action and d.final_reply == p.draft_reply
    assert d.override_reasons == []


def test_unknown_customer_region_cannot_verify_outage_status():
    """Escalate when a status call succeeded but the customer's region is unknown.

    Works with:
        Calls evidence() for an unknown-region customer and decide()/apply_policy().
    """
    t = ticket(3)
    results = evidence(t, extra=[("check_system_status", {"region": "us-east"})])
    d = decide(proposal(issue_type="outage", action="route_to_specialist", team="infrastructure"), t, results)
    assert d.final_action == "escalate_to_human"
    assert any("Missing verified customer region" in reason for reason in d.override_reasons)


def test_status_region_payload_must_match_requested_region():
    """Reject mismatched regional payloads rather than treating tool success as proof.

    Works with:
        Starts with real evidence() results and checks apply_policy() through decide().
    """
    t = ticket(2)
    results = evidence(t, extra=[("check_system_status", {"region": "ap-southeast"})])
    results[-1].data["region"] = "us-east"
    d = decide(proposal(issue_type="outage", action="route_to_specialist", team="infrastructure"), t, results)
    assert d.final_action == "escalate_to_human"
    assert any("ap-southeast" in reason for reason in d.override_reasons)
