# Copyright © 2026 Lapatrada Liawpairoj. All rights reserved.
# Provided for recruitment evaluation only. See LICENSE for terms.

"""Terminal interface for simulated support triage.

Purpose:
    Load sample tickets, run the agent, apply policy, and display final decisions.

Used with:
    agent.py, policy.py, models.py, and data/tickets.json.

Notes:
    Live mode requires credentials; --demo uses clearly labeled scripted proposals. Output never sends replies or handoffs.
    Verbose diagnostics omit tool payloads and appear on stderr.
"""

import argparse
import json
from pathlib import Path
import shutil
import sys
import textwrap

import config
from agent import CONFIGURATION_ERRORS, run_agent
from demo import DEMO_NOTICE, run_demo
from models import AgentRun, FinalDecision, Ticket
from policy import apply_policy

SIMULATION = "[SIMULATION] No reply was sent and no handoff was performed."


def tool_summary(run: AgentRun) -> list[dict[str, str | None]]:
    """Summarize tool names and outcomes without exposing result payloads.

    Works with:
        Called by print_decision() and main() for text and JSON output.
    """
    return [{"name": r.tool_name, "status": r.status, "error_code": r.error_code} for r in run.tool_results]


def print_decision(ticket: Ticket, run: AgentRun, decision: FinalDecision) -> None:
    """Print the final decision, proposal details, tool outcomes, and simulation notice.

    Works with:
        Called by main(); uses tool_summary() after apply_policy().
    """
    proposal = decision.proposal
    width = max(40, min(shutil.get_terminal_size(fallback=(92, 24)).columns, 100))

    def paragraph(text: str, prefix: str = "  ") -> None:
        """Wrap prose while preserving explicit paragraphs and long Unicode words.

        Works with:
            Local formatting helper for print_decision(); uses textwrap.fill().
        """
        for line in text.splitlines() or [""]:
            print(textwrap.fill(line, width=width, initial_indent=prefix,
                                subsequent_indent="  ", break_long_words=False,
                                break_on_hyphens=False))

    print("\n" + "=" * width)
    print(f"Ticket: {ticket.id}")
    print("=" * width)
    print("\nDECISION")
    print(f"  Urgency: {decision.final_urgency or 'unknown'}")
    print(f"  Action: {decision.final_action}")
    print(f"  Team: {decision.final_team}")
    print(f"  Status: {decision.status}")
    print()
    paragraph(proposal.summary if proposal else "No valid model proposal was available.", "  Summary: ")

    print("\nTICKET DETAILS")
    for label, value in (
        ("Product", (proposal.product or "unknown") if proposal else "unknown"),
        ("Issue type", proposal.issue_type if proposal else "unknown"),
        ("Sentiment", proposal.sentiment if proposal else "unknown"),
        ("Language", proposal.language if proposal else "unknown"),
        ("Secondary tags", ", ".join(proposal.secondary_tags) if proposal else ""),
    ):
        print(f"  {label}: {value or 'none'}")

    print("\nEVIDENCE")
    print("  Tools called:")
    for tool in tool_summary(run):
        outcome = tool['error_code'] or tool['status']
        print(f"    - {tool['name']}: {outcome}")
    if not run.tool_results:
        print("    - none")
    paragraph(", ".join(proposal.kb_article_ids) if proposal and proposal.kb_article_ids else "none",
              "  KB article IDs: ")

    print("\nPOLICY CHANGES")
    if decision.override_reasons:
        for reason in decision.override_reasons:
            paragraph(reason, "  - ")
    else:
        print("  None — proposed action, team, and reply were retained.")

    print("\nCUSTOMER REPLY")
    paragraph(decision.final_reply, "  Reply: ")
    print()
    print(SIMULATION)
    print("=" * width + "\n")


def print_verbose(ticket: Ticket, run: AgentRun, decision: FinalDecision) -> None:
    """Print allowlisted, shortened arguments and override reasons to stderr.

    Works with:
        Called by main() after run_agent() and apply_policy(); does not print raw tool payloads.
    """
    for result in run.tool_results:
        args = {
            key: str(value).replace("\n", " ").replace("\r", " ")[:100]
            for key, value in result.args.items() if key in {"customer_id", "query", "region"}
        }
        print(f"[{ticket.id}] {result.tool_name} {json.dumps(args, ensure_ascii=False)}: "
              f"{result.error_code or result.status}", file=sys.stderr)
    for reason in decision.override_reasons:
        print(f"[{ticket.id}] policy: {reason}", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    """Select sample tickets and produce text or JSON, handling configuration errors.

    Works with:
        Uses config.require_api_key(), run_agent(), apply_policy(), print_decision(), print_verbose(), and tool_summary().
    """
    parser = argparse.ArgumentParser(description="Support Ticket Triage Agent (simulation)")
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--all", action="store_true", help="Process all sample tickets")
    selection.add_argument("--ticket", choices=["1", "2", "3", "ticket-1", "ticket-2", "ticket-3"])
    parser.add_argument("--json", action="store_true", help="Emit machine-readable final decisions")
    parser.add_argument("--verbose", action="store_true", help="Show concise tool diagnostics on stderr")
    parser.add_argument("--demo", action="store_true", help="Show scripted sample decisions without an API key or LLM")
    args = parser.parse_args(argv)
    if not args.demo and not config.OPENAI_MODEL:
        print("Error: set OPENAI_MODEL in the environment or project .env.", file=sys.stderr)
        return 2

    if not args.demo:
        try:
            config.require_api_key()
        except ValueError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 2

    path = Path(__file__).resolve().parent / "data" / "tickets.json"
    tickets = [Ticket.model_validate(item) for item in json.loads(path.read_text(encoding="utf-8"))]

    if not args.all:
        ticket_id = args.ticket if args.ticket.startswith("ticket-") else f"ticket-{args.ticket}"
        tickets = [ticket for ticket in tickets if ticket.id == ticket_id]
    outputs = []

    try:
        for ticket in tickets:
            run = run_demo(ticket) if args.demo else run_agent(ticket)
            decision = apply_policy(ticket, run)

            if args.verbose:
                print_verbose(ticket, run, decision)

            if args.json:
                output = {**decision.model_dump(mode="json"), "tool_calls": tool_summary(run)}
                if args.demo:
                    output.update(mode="demo", notice=DEMO_NOTICE)
                outputs.append(output)

            else:
                if args.demo:
                    print(DEMO_NOTICE)
                print_decision(ticket, run, decision)

    except CONFIGURATION_ERRORS as exc:
        print(f"Error: OpenAI rejected the configured key or model ({type(exc).__name__}). "
              "Check OPENAI_API_KEY and OPENAI_MODEL.", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(outputs if args.all else outputs[0], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
