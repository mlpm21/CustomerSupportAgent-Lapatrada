"""Shared triage policy definitions.

Purpose:
    Define the urgency rubric and available action meanings.

Used with:
    Imported by prompts.py so policy wording has one source of truth.

Notes:
    Currently contains text constants only. Final policy checks are planned for Phase 4.
"""

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
