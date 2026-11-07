# Copyright © 2026 Lapatrada Liawpairoj. All rights reserved.
# Provided for recruitment evaluation only. See LICENSE for terms.

"""Shared triage policy definitions.

Purpose:
    Define the shared rubric and apply final decision checks.

Used with:
    prompts.py imports the rubric; main.py applies policy to AgentRun.

Notes:
    Checks use recorded tool evidence. No replies or handoffs are executed.
"""

from models import Action, AgentRun, FinalDecision, IssueType, Team, Ticket, TriageResult, Urgency

URGENCY_RUBRIC: str = """\
Classify the complete conversation using impact, scope, time sensitivity, and
available evidence. Anger, plan tier, or a long conversation alone does not
establish critical urgency. Treat plausible unverified impact as reported
impact and record uncertainty.

critical: Widespread or severe loss of core service requiring immediate intervention.
high: Substantial customer impact, financial risk, or a near-term business deadline.
medium: Meaningful impairment with limited impact or a viable workaround.
low: Nonblocking assistance, cosmetic issues, or feature requests without material urgency.

Urgency and action are separate: a high-urgency financial dispute can require
immediate human escalation without being classified critical.
"""

ACTION_DEFINITIONS: str = """\
auto_respond: Retrieved documentation covers all material questions, with no
unresolved financial risk, service outage, or missing evidence needed for the answer.
route_to_specialist: Specialist investigation is needed without immediate human
intervention; retain the urgency separately.
escalate_to_human: Critical impact, threatened financial dispute, material risk,
or failure to complete reliable triage.

Teams: billing, infrastructure, product_support. none is valid only for
auto-response. For an unclear fallback, use product_support as the documented
general triage destination. A real integration would need a general-support queue.
"""

ENGLISH_ACK = "Thank you for contacting us. We received your message, and it needs review by our support team."
THAI_ACK = "ขอบคุณที่ติดต่อเรา เราได้รับข้อความของคุณแล้ว และเรื่องนี้ต้องได้รับการตรวจสอบจากทีมสนับสนุนของเรา"
ACTION_ORDER = {Action.AUTO_RESPOND: 0, Action.ROUTE_TO_SPECIALIST: 1, Action.ESCALATE_TO_HUMAN: 2}
# Same-amount billing events this close together count as repeated charges, not routine renewals.
REPEATED_CHARGE_WINDOW_MINUTES = 24 * 60


def has_repeated_charges(run: AgentRun) -> bool:
    """Detect same-amount/currency pending or captured events within 24 hours.

    Works with:
        Called by apply_policy(); reads successful get_billing_events results in AgentRun.
    """
    for result in run.tool_results:
        if result.tool_name != "get_billing_events" or result.status != "success":
            continue
        events = result.data.get("events") if isinstance(result.data, dict) else None

        if not isinstance(events, list):
            continue
        ages: dict[tuple, list[float]] = {}

        for event in events:
            if (isinstance(event, dict)
                    and event.get("status") in {"pending_authorization", "captured"}
                    and isinstance(event.get("age_minutes"), (int, float))):
                ages.setdefault((event.get("amount"), event.get("currency")), []).append(event["age_minutes"])

        for values in ages.values():
            values.sort()
            if any(later - earlier <= REPEATED_CHARGE_WINDOW_MINUTES for earlier, later in zip(values, values[1:])):
                return True
    return False


def safe_acknowledgment(ticket: Ticket, proposal: TriageResult | None) -> str:
    """Choose a safe Thai or English acknowledgment from language or ticket text.

    Works with:
        Called by apply_policy() for failed runs, changed actions, or empty drafts.
    """
    language = proposal.language.casefold().strip() if proposal else "unknown"
    thai = language.startswith("th")

    if proposal is None or language == "unknown":
        thai = any("\u0e00" <= char <= "\u0e7f" for message in ticket.messages for char in message.text)
    return THAI_ACK if thai else ENGLISH_ACK


def apply_policy(ticket: Ticket, run: AgentRun) -> FinalDecision:
    """Apply evidence, action, team, and draft rules without lowering severity.

    Works with:
        Called by main.main(); uses has_repeated_charges(), require_action(), and safe_acknowledgment().
    """
    proposal = run.proposal
    if proposal is None or run.failure_reason is not None:
        return FinalDecision(
            proposal=proposal, final_urgency=None,
            final_action=Action.ESCALATE_TO_HUMAN, final_team=Team.PRODUCT_SUPPORT,
            final_reply=safe_acknowledgment(ticket, proposal),
            override_reasons=[f"Run failed: {run.failure_reason or 'missing_proposal'}"],
            status="failed",
        )

    action = proposal.action
    reasons: list[str] = []

    def require_action(minimum: Action, reason: str) -> None:
        """Raise the current action only when needed and record the resulting change.

        Works with:
            Local helper called by apply_policy() for evidence, urgency, billing, and budget rules.
        """
        nonlocal action
        if ACTION_ORDER[minimum] > ACTION_ORDER[action]:
            action = minimum
            reasons.append(reason)

    kinds = {proposal.issue_type, *proposal.secondary_tags}
    successful = {result.tool_name for result in run.tool_results if result.status == "success"}
    required = ["lookup_customer_history", "search_knowledge_base"]
    if IssueType.BILLING in kinds:
        required.append("get_billing_events")

    if IssueType.OUTAGE in kinds:
        required.append("check_system_status")
    for name in required:
        if name not in successful:
            require_action(Action.ESCALATE_TO_HUMAN, f"Missing successful tool: {name}")

    if IssueType.OUTAGE in kinds and "check_system_status" in successful:
        histories = [
            result for result in run.tool_results
            if result.tool_name == "lookup_customer_history" and result.status == "success"
            and result.args.get("customer_id") == ticket.customer_id
            and isinstance(result.data, dict)
        ]
        region = histories[-1].data.get("region") if histories else None
        if not isinstance(region, str) or not region.strip():
            require_action(Action.ESCALATE_TO_HUMAN, "Missing verified customer region for outage status")
        elif not any(
            result.tool_name == "check_system_status" and result.status == "success"
            and result.args.get("region") == region
            and isinstance(result.data, dict) and result.data.get("region") == region
            for result in run.tool_results
        ):
            require_action(Action.ESCALATE_TO_HUMAN, f"Missing successful check_system_status for customer region: {region}")

    retrieved_ids = {
        article["id"]
        for result in run.tool_results
        if result.tool_name == "search_knowledge_base" and result.status == "success"
        and isinstance(result.data, list)
        for article in result.data
        if isinstance(article, dict) and isinstance(article.get("id"), str)
    }

    invalid_ids = sorted(set(proposal.kb_article_ids) - retrieved_ids)
    if invalid_ids:
        require_action(Action.ESCALATE_TO_HUMAN, f"Invalid KB article IDs: {', '.join(invalid_ids)}")
    if proposal.urgency == Urgency.CRITICAL:
        require_action(Action.ESCALATE_TO_HUMAN, "Critical urgency requires human escalation")
    # High billing urgency represents financial risk, a deadline, or a threatened dispute in the rubric.
    if IssueType.BILLING in kinds and proposal.urgency in (Urgency.HIGH, Urgency.CRITICAL):
        require_action(Action.ESCALATE_TO_HUMAN, "High-risk billing issue requires human escalation")
    # Evidence-based check, independent of the model's urgency label.
    if IssueType.BILLING in kinds and has_repeated_charges(run):
        require_action(Action.ESCALATE_TO_HUMAN, "Repeated same-amount billing events require human escalation")
    if run.tool_budget_exhausted:
        require_action(Action.ROUTE_TO_SPECIALIST, "Tool-round limit reached; auto-response not allowed")
    if kinds & {IssueType.BILLING, IssueType.OUTAGE} and proposal.action == Action.AUTO_RESPOND:
        require_action(Action.ROUTE_TO_SPECIALIST, "Billing/outage cannot auto-respond")
    no_articles = proposal.action == Action.AUTO_RESPOND and not proposal.kb_article_ids
    if no_articles:
        require_action(Action.ROUTE_TO_SPECIALIST, "Auto-response has no supporting KB article IDs")

    # Domain ownership takes precedence; outage is checked before billing.
    if IssueType.OUTAGE in kinds:
        team = Team.INFRASTRUCTURE
    elif IssueType.BILLING in kinds:
        team = Team.BILLING
    elif no_articles or (action != Action.AUTO_RESPOND and proposal.team == Team.NONE):
        team = Team.PRODUCT_SUPPORT
    else:
        team = proposal.team
    if action == Action.AUTO_RESPOND:
        team = Team.NONE
    if team != proposal.team:
        reasons.append(f"Team corrected: {proposal.team.value} -> {team.value}")

    reply = proposal.draft_reply
    if action != proposal.action or not reply.strip():
        if not reply.strip():
            reasons.append("Empty draft replaced with safe acknowledgment")
        reply = safe_acknowledgment(ticket, proposal)
    return FinalDecision(
        proposal=proposal, final_urgency=proposal.urgency,
        final_action=action, final_team=team, final_reply=reply,
        override_reasons=reasons, status="completed",
    )
