# Copyright © 2026 Lapatrada Liawpairoj. All rights reserved.
# Provided for recruitment evaluation only. See LICENSE for terms.

"""CLI configuration errors and bounded diagnostic output, without live calls."""

from types import SimpleNamespace as NS

import pytest
from openai import AuthenticationError, PermissionDeniedError, NotFoundError

import config
import main
from models import AgentRun, FinalDecision, Ticket, ToolResult, TriageResult


@pytest.mark.parametrize("missing", ["OPENAI_API_KEY", "OPENAI_MODEL"])
def test_missing_configuration(monkeypatch, capsys, missing):
    """Check missing key or model returns exit code 2 and one stderr line.

    Works with:
        Run by pytest; monkeypatches config and calls main.main().
    """
    monkeypatch.setattr(config, "OPENAI_API_KEY", "offline-placeholder")
    monkeypatch.setattr(config, "OPENAI_MODEL", "offline-model")
    monkeypatch.setattr(config, missing, "")
    assert main.main(["--ticket", "1"]) == 2
    captured = capsys.readouterr()
    assert captured.out == "" and len(captured.err.splitlines()) == 1
    assert missing in captured.err and "Traceback" not in captured.err


def test_verbose_query_is_flattened_and_truncated(capsys):
    """Check query diagnostics are shortened and exclude raw message/result payloads.

    Works with:
        Run by pytest; calls main.print_verbose().
    """
    t = Ticket(id="example", customer_id="cust-001", messages=[
        {"text": "private customer message", "relative_time": "now"}])
    query = "dark mode\n" + "x" * 110
    run = AgentRun(tool_results=[ToolResult(call_id="k", tool_name="search_knowledge_base",
        args={"query": query}, status="success", data=[{"card_reference": "card ending 4242"}])])
    decision = FinalDecision(final_action="escalate_to_human", final_team="product_support",
                             final_reply="Safe acknowledgment", status="failed")
    main.print_verbose(t, run, decision)
    output = capsys.readouterr().err
    assert query.replace("\n", " ")[:100] in output
    assert "x" * 101 not in output
    assert "private customer message" not in output and "card ending" not in output
    assert len(output.splitlines()) == 1


@pytest.mark.parametrize("error_type,code", [(AuthenticationError, 401), (PermissionDeniedError, 403), (NotFoundError, 404)])
def test_rejected_key_exits_with_configuration_error(monkeypatch, capsys, error_type, code):
    """Check rejected key/model/access errors stop the batch without a traceback.

    Works with:
        Run by pytest; replaces main.run_agent() with reject() and calls main.main().
    """
    monkeypatch.setattr(config, "OPENAI_API_KEY", "offline-placeholder")
    monkeypatch.setattr(config, "OPENAI_MODEL", "offline-model")

    def reject(ticket):
        """Raise the selected configuration error instead of making a live request.

        Works with:
            Injected by test_rejected_key_exits_with_configuration_error() as main.run_agent().
        """
        raise error_type("configuration rejected", response=NS(request=NS(), status_code=code, headers={}), body=None)

    monkeypatch.setattr(main, "run_agent", reject)
    assert main.main(["--all", "--json"]) == 2
    captured = capsys.readouterr()
    assert captured.out == "" and error_type.__name__ in captured.err and "Traceback" not in captured.err


def test_plain_output_shows_product_and_summary(capsys):
    """Check text output includes product, summary, and the unknown-product fallback.

    Works with:
        Run by pytest; calls main.print_decision().
    """

    t = Ticket(id="example", customer_id="cust-003", messages=[{"text": "Dark mode?", "relative_time": "now"}])
    p = TriageResult(urgency="low", product="Desktop app", issue_type="how_to", sentiment="neutral",
                     language="en", action="auto_respond", team="none", secondary_tags=[],
                     summary="Documented theme steps apply.", kb_article_ids=["dark-mode"], draft_reply="Reply.")
    decision = FinalDecision(proposal=p, final_urgency="low", final_action="auto_respond",
                             final_team="none", final_reply="Reply.", status="completed")
    main.print_decision(t, AgentRun(proposal=p), decision)
    out = capsys.readouterr().out

    assert "Product: Desktop app" in out and "Summary: Documented theme steps apply." in out
    main.print_decision(t, AgentRun(proposal=p.model_copy(update={"product": None})), decision.model_copy(
        update={"proposal": p.model_copy(update={"product": None})}))
    assert "Product: unknown" in capsys.readouterr().out


@pytest.mark.parametrize("json_output", [False, True])
def test_demo_works_without_credentials_or_agent(monkeypatch, capsys, json_output):
    """Verify demo decisions and replies are visible without creating an LLM client.

    Works with:
        Calls main.main() with --demo; run_demo() uses local tools and apply_policy().
    """
    import json

    monkeypatch.setattr(config, "OPENAI_API_KEY", "")
    monkeypatch.setattr(config, "OPENAI_MODEL", "")

    def reject_live_call(ticket):
        """Fail if demo accidentally enters the live-agent path.

        Works with:
            Installed as main.run_agent() by this test to enforce API-free execution.
        """
        pytest.fail("Demo must never call the live agent")

    monkeypatch.setattr(main, "run_agent", reject_live_call)
    args = ["--all", "--demo"] + (["--json"] if json_output else [])
    assert main.main(args) == 0
    output = capsys.readouterr().out
    if json_output:
        decisions = json.loads(output)
        assert [(d["final_urgency"], d["final_action"], d["final_team"]) for d in decisions] == [
            ("high", "escalate_to_human", "billing"),
            ("critical", "escalate_to_human", "infrastructure"),
            ("low", "auto_respond", "none"),
        ]
        assert all(d["mode"] == "demo" and "SIMULATED AI RESPONSE" in d["notice"] for d in decisions)
        assert all(d["override_reasons"] == [] for d in decisions)
        assert all(t["status"] == "success" for d in decisions for t in d["tool_calls"])
        assert decisions[1]["proposal"]["language"] == "th" and "ครับ" in decisions[1]["final_reply"]
    else:
        assert output.count("SIMULATED AI RESPONSE") == 3
        assert output.count(main.SIMULATION) == 3
        assert "Urgency: critical" in output and "Reply:" in output


def test_demo_single_ticket(monkeypatch, capsys):
    """Verify selecting one demo ticket retains valid, explicitly labeled JSON output.

    Works with:
        Calls main.main(), which selects the ticket before run_demo().
    """
    import json

    monkeypatch.setattr(config, "OPENAI_API_KEY", "")
    monkeypatch.setattr(config, "OPENAI_MODEL", "")
    assert main.main(["--ticket", "2", "--demo", "--json", "--verbose"]) == 0
    captured = capsys.readouterr()
    decision = json.loads(captured.out)
    assert isinstance(decision, dict) and decision["final_team"] == "infrastructure"
    assert decision["mode"] == "demo" and "check_system_status" in captured.err
