# Copyright © 2026 Lapatrada Liawpairoj. All rights reserved.
# Provided for recruitment evaluation only. See LICENSE for terms.

"""Shared application data models.

Purpose:
    Define validated tickets, tool outcomes, proposals, runs, and final decisions.

Used with:
    Used by the agent, prompts, and tool registry.

Notes:
    Schema validation checks data shape; final decision policy is a separate responsibility.
"""

from enum import StrEnum
from typing import Literal, Self

from pydantic import BaseModel, Field, JsonValue, model_validator


class Urgency(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class Action(StrEnum):
    AUTO_RESPOND = "auto_respond"
    ROUTE_TO_SPECIALIST = "route_to_specialist"
    ESCALATE_TO_HUMAN = "escalate_to_human"


class Team(StrEnum):
    BILLING = "billing"
    INFRASTRUCTURE = "infrastructure"
    PRODUCT_SUPPORT = "product_support"
    NONE = "none"


class IssueType(StrEnum):
    BILLING = "billing"
    OUTAGE = "outage"
    BUG = "bug"
    HOW_TO = "how_to"
    FEATURE_REQUEST = "feature_request"
    ACCOUNT = "account"
    OTHER = "other"


class Sentiment(StrEnum):
    POSITIVE = "positive"
    NEUTRAL = "neutral"
    FRUSTRATED = "frustrated"
    ANGRY = "angry"


class Message(BaseModel):
    """Preserve original wording and time labels without inferred timestamps."""

    text: str = Field(min_length=1)
    relative_time: str = Field(min_length=1)
    role: Literal["customer", "agent"] | None = None


class Ticket(BaseModel):
    """Messages appear in their original chronological order."""

    id: str = Field(min_length=1)
    customer_id: str = Field(min_length=1)
    messages: list[Message] = Field(min_length=1)


class TriageResult(BaseModel):
    """Model proposal; final policy checks are applied separately."""

    urgency: Urgency
    product: str | None
    issue_type: IssueType
    sentiment: Sentiment
    language: str = Field(description="Customer language code, or 'unknown'.")
    action: Action
    team: Team
    secondary_tags: list[IssueType]
    summary: str = Field(description="Short decision explanation and evidence summary.")
    kb_article_ids: list[str]
    draft_reply: str


class ToolResult(BaseModel):
    """Recorded outcome; arguments are empty when argument validation fails."""

    call_id: str
    tool_name: str
    args: dict[str, JsonValue]
    status: Literal["success", "error"]
    data: JsonValue = None
    error_code: str | None = None

    @model_validator(mode="after")
    def validate_outcome(self) -> Self:
        """Reject tool outcomes that mix successful data with error information.

        Works with:
            Called automatically by Pydantic when execute_tool_call() or other callers construct a ToolResult.
        """
        if self.status == "success" and self.error_code is not None:
            raise ValueError("A successful tool result cannot have an error code.")
        if self.status == "error" and (not self.error_code or self.data is not None):
            raise ValueError("A tool error requires an error code and no data.")
        return self


class FinalDecision(BaseModel):
    """Consumer-facing fields, including failures with no model proposal."""

    proposal: TriageResult | None = None
    final_urgency: Urgency | None = None
    final_action: Action
    final_team: Team
    final_reply: str
    override_reasons: list[str] = Field(default_factory=list)
    status: Literal["completed", "failed"]


class AgentRun(BaseModel):
    """Proposal and observed tool outcomes, before final policy is applied."""

    proposal: TriageResult | None = None
    tool_results: list[ToolResult] = Field(default_factory=list)
    failure_reason: Literal["api_error", "refusal", "invalid_output"] | None = None
    tool_budget_exhausted: bool = Field(
        default=False, description="The model was still requesting tools when the round limit was reached.",
    )
