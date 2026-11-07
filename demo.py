# Copyright © 2026 Lapatrada Liawpairoj. All rights reserved.
# Provided for recruitment evaluation only. See LICENSE for terms.

"""Scripted sample proposals for an explicitly labeled, API-free CLI demonstration.

Purpose:
    Show local tool evidence, final policy decisions, and example customer replies.

Used with:
    main.py calls run_demo(); normal agent.run_agent() never uses these scenarios.

Notes:
    This is not an AI classifier. Proposals apply only to the three supplied samples.
"""

import json

from models import AgentRun, Ticket, TriageResult
from tools import execute_tool_call

DEMO_NOTICE = "[DEMO — SIMULATED AI RESPONSE] Scripted proposal; no LLM or OpenAI API was used."

# Deliberately scripted examples, isolated from the real agent's decision flow.
SCENARIOS = {
    "ticket-1": {
        "queries": ["pending charges", "upgrade payment", "refund dispute"],
        "domain_tool": "get_billing_events",
        "proposal": dict(
            urgency="high", product=None, issue_type="billing", sentiment="angry", language="en",
            action="escalate_to_human", team="billing", secondary_tags=[],
            summary="Repeated pending authorizations and missing Pro entitlement, with a presentation deadline and threatened dispute, need billing review.",
            kb_article_ids=["pending-charges", "upgrade-payment", "billing-disputes"],
            draft_reply="I understand the urgency with your presentation in two hours. The records show three pending authorizations of $29.99, rather than confirmed captured payments, while Pro access remains inactive. This needs priority review by a billing specialist to investigate the payment attempts and missing access. The outcome and resolution time still need to be confirmed.",
        ),
    },
    "ticket-2": {
        "queries": ["HTTP 500 outage", "status internal incident"],
        "domain_tool": "check_system_status",
        "proposal": dict(
            urgency="critical", product=None, issue_type="outage", sentiment="frustrated", language="th",
            action="escalate_to_human", team="infrastructure", secondary_tags=[],
            summary="Multiple users cannot access the service before an important demo. Internal regional incident evidence conflicts with the operational public snapshot.",
            kb_article_ids=["http-500", "status-conflict"],
            draft_reply="เข้าใจว่าปัญหานี้กระทบหลายคนและการ demo กับลูกค้ารายสำคัญครับ ข้อมูลสถานะภายในของ region ap-southeast ระบุว่ามีปัญหา gateway error 500 ที่กระทบผู้ใช้ Enterprise ขณะที่ข้อมูลสถานะสาธารณะยังแสดงว่าปกติ สถานะสาธารณะจึงไม่ได้หมายความว่าปัญหาที่คุณพบไม่มีอยู่จริง กรณีนี้จำเป็นต้องให้ทีมโครงสร้างพื้นฐานตรวจสอบอย่างเร่งด่วน โดยยังยืนยันเวลาที่ระบบจะกลับมาใช้งานไม่ได้ครับ",
        ),
    },
    "ticket-3": {
        "queries": ["dark mode system default", "scheduled dark mode"],
        "domain_tool": None,
        "proposal": dict(
            urgency="low", product="Desktop app", issue_type="how_to", sentiment="neutral", language="en",
            action="auto_respond", team="none", secondary_tags=["feature_request"],
            summary="Nonblocking theme troubleshooting is documented; scheduling is a separate unsupported feature request. The installed version is unknown.",
            kb_article_ids=["dark-mode", "scheduled-dark-mode"],
            draft_reply="Open Settings > Appearance > Theme. The Dark option and System Default following your Mac's theme depend on a supported desktop app version. Please check your installed version against the current desktop release requirements; update if needed and restart, then select System Default while macOS is in dark mode. If the app remains light on a supported version, share the app version and symptoms with product support. Scheduled switching, such as at 6pm, is not currently supported; that is a feature request rather than an available setting.",
        ),
    },
}


def run_demo(ticket: Ticket) -> AgentRun:
    """Run actual local tools and return the selected sample's scripted proposal.

    Works with:
        Called only by main.main() with --demo; uses execute_tool_call(), then apply_policy() runs normally.
    """
    scenario = SCENARIOS[ticket.id]
    results = []

    def call(name: str, args: dict) -> None:
        """Record a real local tool outcome in demo execution order.

        Works with:
            Local helper for run_demo(); delegates to execute_tool_call().
        """
        results.append(execute_tool_call(f"demo-{len(results) + 1}", name, json.dumps(args), ticket.customer_id))

    call("lookup_customer_history", {"customer_id": ticket.customer_id})

    for query in scenario["queries"]:
        call("search_knowledge_base", {"query": query})

    if scenario["domain_tool"] == "get_billing_events":
        call("get_billing_events", {"customer_id": ticket.customer_id})

    elif scenario["domain_tool"] == "check_system_status":
        history = results[0]
        region = history.data.get("region") if history.status == "success" and isinstance(history.data, dict) else None
        call("check_system_status", {"region": region})
    return AgentRun(proposal=TriageResult.model_validate(scenario["proposal"]), tool_results=results)
