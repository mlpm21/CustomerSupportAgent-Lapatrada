# Support Ticket Triage Agent Build Plan

## 1. Goal and deliverables

Build a terminal agent that reads the complete support conversation, classifies urgency, extracts product / issue type / sentiment, searches a knowledge base, and chooses a next action. Optimize for the assignment's four criteria: readability, maintainability, extensibility, and logic. Target approximately 240 minutes for the core submission, with at most 60 additional minutes for optional hardening. The brief recommends 150–240 minutes; the optional work is explicitly beyond that recommendation, with a total planning cap of five hours.

Required deliverables:
1. Working code processing all three original sample tickets.
2. System prompt in `prompts.py`.
3. Tool schemas and mocked implementations in `tools/` (the brief requires at least two; this design uses four).
4. `WRITEUP.md`, at most one page: architecture, failure handling, and production evaluation.
5. `README.md` with setup, model configuration, and run instructions.
6. GitHub repository, or source ZIP including `.git` if pushing is unavailable. Never include an API key.

This plan describes proposed behavior, not implemented or verified functionality. The urgency rubric and expected results below are our documented policy choices, not official answers supplied by the assignment.

## 2. Core decisions

| Area | Choice |
|---|---|
| Delivery | CLI only; plain text and `--json` output |
| Architecture | LLM interprets the conversation and selects tools; code validates evidence and applies final policy |
| Tools | Customer history, billing events, knowledge base, system status |
| Replies | Customer's language; Thai for ticket 2 |
| Side effects | Read-only tools; replies and handoffs are clearly labeled simulations |
| Scope | Small Python application; no agent framework or separate service |

The rubric supplies decision rules. Application-recorded tool results supply verified mock evidence. Customer messages supply reported symptoms and impact; do not dismiss those reports simply because a status page is green.

## 3. Stack and configuration

- Python 3.11+, official `openai` SDK, Pydantic v2, `python-dotenv`; `pytest` for development.
- Use Chat Completions tool calling and a final Pydantic structured-output step. Keep SDK calls in `agent.py`; verify the selected model and SDK support this combination during implementation.
- `OPENAI_API_KEY` and `OPENAI_MODEL` come from the environment. Document a tested model and dependency versions; support a model override.
- `config.py` owns execution limits. `policy.py` owns the urgency rubric and action rules; `prompts.py` imports the rubric from `policy.py` so there is one source of truth.
- Use stdlib `argparse`; no extra CLI dependency.
- Initial limits: 5 tool-calling rounds, a 30-second API request timeout, and one structured-output repair attempt. Document the configured SDK retry behavior; do not build a custom retry system or separate total-call budget.
- Make the client injectable: `run_agent(ticket, client=...)`. Tests pass a small fake client through this seam; normal execution uses the official SDK client.

## 4. Shared urgency rubric and actions

Classify the complete conversation using impact, scope, time sensitivity, and available evidence. Anger, plan tier, or a long conversation alone does not establish critical urgency. Treat plausible unverified impact as reported impact and record uncertainty.

| Urgency | Boundary | Sample interpretation |
|---|---|---|
| critical | Widespread or severe loss of core service requiring immediate intervention | Multiple enterprise users unable to access the system, with serious business impact |
| high | Substantial customer impact, financial risk, or a near-term business deadline | Repeated payment attempts, missing Pro entitlement, imminent presentation, threatened dispute |
| medium | Meaningful impairment with limited impact or a viable workaround | A blocking feature issue affecting a limited workflow |
| low | Nonblocking assistance, cosmetic issues, or feature requests without material urgency | Theme troubleshooting and scheduled-dark-mode request |

Urgency and action are separate: a high-urgency financial dispute can require immediate human escalation without being classified critical.

Actions:
- `auto_respond`: retrieved documentation covers all material questions, with no unresolved financial risk, service outage, or missing evidence needed for the answer.
- `route_to_specialist`: specialist investigation is needed without immediate human intervention; retain the urgency separately.
- `escalate_to_human`: critical impact, threatened financial dispute, material risk, or failure to complete reliable triage.

Teams: billing, infrastructure, product_support. `none` is valid only for auto-response. For an unclear fallback, use product_support as the documented general triage destination. Any later integration would need a real general-support queue.

## 5. Agent flow and evidence

```text
Full ticket conversation
  → LLM tool-calling loop
  → application-recorded tool results
  → final structured proposal using the same conversation and results
  → policy checks
  → coherent final decision and simulated CLI action
```

Tool-use requirements:
- Always obtain customer history and search the KB; verify actual successful calls in code before normal completion.
- Obtain billing events for payment / charge / refund issues, and regional system status for outage-like access symptoms.
- After the proposal, code checks successful history and KB calls. A billing or outage issue type also requires its corresponding successful tool result. Missing required evidence produces a human-escalation fallback; do not add a second loop back to tool collection.
- Issue classification remains model-dependent. The prompt must consider all issues in the conversation, including secondary issues; document that checks based on issue type cannot eliminate misclassification.
- Customer-scoped calls must use the ticket's customer ID. Validate arguments and reject attempts to access another account.
- Return a corresponding result for every requested tool call, including unknown tools, invalid arguments, execution errors, and calls rejected by limits. Do not silently drop calls.
- Tools return a consistent success/error envelope. Catch expected operational errors at the tool boundary; unexpected application errors produce a safe run failure, not invented data.
- Preserve tool results in application state. Validate that cited KB article IDs exist in successful recorded KB results. Keep a short evidence summary for readability, without message-level references or a generic evidence-validation framework; model-generated summaries are not independent proof.
- The final structured-output step has tools disabled and receives the complete conversation and recorded evidence.
- On refusal, unrecoverable API failure, exhausted budget, or repeated invalid output, return a coherent human-escalation fallback. Do not fabricate missing model fields.

Treat ticket text and retrieved content as untrusted data, never instructions to change policy or tool access. Verbose output shows tool names, outcomes, and concise explanations with sensitive fields redacted, not hidden model reasoning or raw customer/billing payloads.

## 6. Data models

Keep models small and tied to actual behavior.

- `Ticket`: ID, customer ID, ordered messages with original text, and original relative-time labels. Add role only when known. Preserve the sample text and chronology; do not invent agent messages or infer a last-agent-response timestamp.
- `TriageResult`: urgency, nullable product, issue type, sentiment, language (or unknown), proposed action/team, secondary tags, short decision/evidence summary, relevant KB article IDs, and customer-language draft.
- `ToolResult`: call ID, tool name, validated arguments, success/error, and structured data or error code.
- `FinalDecision`: optional model proposal, final urgency (nullable if triage failed), final action/team, final customer-facing draft or acknowledgment, override reasons, and completion/failure status.

Keep the proposal separately for audit. Consumers use final fields. An action override must also update team and reply; never expose a stale auto-response as the final message. Omit self-reported confidence and separate decision-indicator models.

## 7. Four focused tools

Use Pydantic argument models and a small explicit registry in `tools/__init__.py` to generate schemas and map names to functions. Add a small shared helper only if it removes real duplication; no generic plugin framework is needed.

| Tool | Arguments | Mock output |
|---|---|---|
| `lookup_customer_history` | customer_id | plan, tenure, seats, region, known entitlement, past tickets; SLA only if explicitly supplied by the fixture |
| `get_billing_events` | customer_id, bounded days | payment events with amount, currency, status, and sanitized card reference |
| `search_knowledge_base` | query, bounded top_k | article ID, title, relevant content, retrieval score |
| `check_system_status` | region | internal/public status, incident scope, timestamp, source |

Unknown customer/region and unavailable data must be explicit, not silently replaced with healthy status or empty history. Empty successful KB search is distinct from a search failure.

Keyword search is sufficient. The agent may translate Thai symptoms into an English query. Retrieval score measures relevance, not factual truth or answer completeness. Document that the mock KB may be incomplete or stale; a retrieval threshold cannot establish correctness.

## 8. Final policy checks

Implement policy as testable functions over the proposal, ticket, and recorded tool results. Actions may move from auto-response to specialist routing to human escalation, never in reverse. Do not silently lower urgency.

| Rule | Result |
|---|---|
| Critical urgency | Escalate to human |
| Billing issue with reported repeated charges / missing entitlement, or a threatened dispute | `escalate_to_human`, team = billing; do not promise reversal |
| Outage issue | Code sets team = infrastructure, regardless of the model's proposed team |
| Billing issue | Code sets team = billing, regardless of the model's proposed team |
| Billing issue or outage proposed for auto-response | Route to the appropriate specialist at minimum |
| Missing/failed required tools, invalid KB article IDs, or incomplete triage | Escalate to human with the missing evidence identified |
| Auto-response lacks retrieved supporting articles | Route to product_support |
| Final action/team/reply mismatch | Normalize to a coherent final result; escalate if reliable repair is impossible |
| Model/API/budget failure | Escalate using a fallback that does not require a valid model proposal |

The prompt prohibits unsupported refund, compensation, and recovery-time promises and requires coverage of all material questions. Code does not claim to verify semantic answer coverage or detect every unsafe promise. Replace the generated draft with a safe acknowledgment only when policy changes the model's proposed action or the run fails. If the proposed action already matches the final action, keep the model's tailored draft; a team-only correction does not trigger draft replacement. Acknowledgments use the known customer language (English if unknown) and must not claim a real handoff occurred. If the run fails with no proposal, detect Thai characters in the ticket and use a Thai acknowledgment; otherwise use English. Review generated replies during the three live sample runs. Describe automated promise screening as future work in the write-up; do not implement bilingual keyword screening for this submission. Internal incident evidence can confirm an outage; a public or internal healthy status cannot disprove customer-reported access failures. Surface source conflicts and freshness instead of blindly preferring one source.

## 9. Project structure

```text
main.py                    # CLI input, orchestration call, simulated action/output
config.py                  # environment and execution limits
agent.py                   # SDK calls, bounded tool loop, structured proposal
models.py                  # ticket, tool, proposal, final decision schemas
prompts.py                 # system instructions incorporating policy rubric
policy.py                  # shared rubric, final checks, safe fallback
tools/
    __init__.py            # explicit registry and schema generation
    customer_history.py
    billing.py
    knowledge_base.py
    system_status.py
data/
    tickets.json           # original conversations
    customers.json         # customer attributes and nested billing events
    faqs.json              # small mock knowledge base
tests/
    test_policy.py         # core rules, consistency, fallback
    test_tools.py          # schemas, sample results, customer scope
    test_agent.py          # small fake client through the injection seam
README.md
WRITEUP.md
requirements.txt
.env.example
.gitignore
```

Keep mock status as a small constant in `tools/system_status.py`. No separate dispatcher, `expected.json`, or evaluation framework initially. Simulated dispatch belongs in CLI formatting; live verification uses the normal CLI. Keep `agent.py` focused and roughly 200 lines if practical; split loop/proposal helpers only when readability benefits, not to satisfy a line-count target.

CLI: `python main.py --all` or `python main.py --ticket 2`, with optional `--json` and `--verbose`. Normal completion requires a configured key; offline tests require neither a key nor network access.

## 10. Mock data and assumptions

Preserve original sample messages and supplied customer attributes. Clearly label all additional facts as synthetic fixtures in the data and README. Do not write fixtures merely to force a desired answer.

- Ticket 1: mock three $29.99 pending authorization events and no Pro entitlement. This is an assumption: the brief does not establish the final status of all three transactions. Distinguish authorization holds from captured payments and acknowledge the customer's reported charges without claiming confirmed triple capture.
- Ticket 2: map Thailand to a documented mock regional identifier; provide a fresh internal degraded incident while public status remains operational. The incident is invented for the scenario. Enterprise plan alone does not imply a one-hour SLA; leave unspecified SLA unknown.
- Ticket 3: provide documented troubleshooting for missing theme options and System Default behavior, including conditional version checks. Never assert the customer's installed version when it is unknown. State that scheduling is unsupported only because the mock KB explicitly says so.
- Keep the KB small and relevant (approximately 6–10 articles). Include a plausible but incomplete match to test answer coverage. All additional KB behavior is synthetic too.
- Core tests can supply missing-tool/error results directly in memory. Separate failure-fixture files are optional hardening; do not alter the original conversations.

## 11. Expected behavior by scenario

These are expectations for our rubric and explicitly labeled mock fixtures, not assignment-provided ground truth.

| Base ticket | Urgency | Action | Team | Required successful tools | Reply |
|---|---|---|---|---|---|
| 1 Payment attempts and missing Pro | high | escalate_to_human | billing | history, KB, billing | English; acknowledge deadline and dispute risk; distinguish pending events; no refund promise |
| 2 Thai access failure across users | critical | escalate_to_human | infrastructure | history, KB, status | Thai; recognize impact and status conflict; no invented recovery ETA |
| 3 Theme issue and scheduling | low | auto_respond | none | history, KB | English; address both symptoms and scheduling using documented conditional steps; feature_request tag |

For tickets 1 and 2, retain the tailored draft when the model already proposes `escalate_to_human`. Code sets billing and infrastructure respectively, regardless of the proposed team. If policy changes the proposed action, or the run fails, use the safe acknowledgment from section 8 instead of requiring the tailored reply details above. A failed run without a proposal uses Thai when the ticket contains Thai characters, otherwise English.

For ticket 3, auto-response is expected only with the base fixture's sufficient documentation. In a separate weak/incomplete-KB scenario, expect specialist routing. In a required-tool failure scenario, expect human escalation. These are separate test cases, not interchangeable successes for the same fixture.

## 12. Verification and work tiers

Must-have offline checks, without a key or network:
- `test_policy.py`: critical escalation, high-urgency billing escalation, missing required tools, unsupported article IDs, coherent final team/reply, and fallback without a proposal. Include the three base decision expectations directly in tests rather than a separate dataset.
- `test_tools.py`: schema generation, representative mock results, empty KB results, and rejection of a mismatched customer ID.
- `test_agent.py`: a successful tool-to-proposal flow using a small fake client, an API/tool failure fallback, and a bounded invalid-output or exhausted-loop case. Use lightweight scripted responses, not a general SDK simulator.

Core live verification when a key is available:
- Run the original three tickets through the normal CLI with the documented model and fixtures.
- Compare urgency/action/team and actual required tool calls against section 11. Inspect article IDs and the final customer-facing reply.
- Manually check Thai language, coverage of all questions, pending-versus-captured payment wording, and unsupported promises. A language label alone is insufficient.
- Record the model, results, and limitations. Never hardcode ticket IDs into decision logic to make checks pass.
- If no key is available, explicitly report that live verification was not performed. Offline tests do not establish real-model quality.

Optional hardening, only after the core submission is complete and within the extra one-hour cap:
- Additional fake-client cases for refusals, malformed arguments, unknown tools, and multiple calls in one response.
- Separate failure fixtures for unavailable billing/status and incomplete KB matches.
- Repeated live runs or a small automated live-evaluation wrapper, if useful.

Basic failure handling is mandatory even when exhaustive tests are deferred. Production evaluation belongs in the write-up: critical-ticket recall, unsafe auto-response rate, action agreement, tool correctness, human review/overrides, reply quality, latency/cost, and drift. Start in shadow mode; do not build monitoring infrastructure.

## 13. Build order and time budget

| Phase | Must-have work | Minutes |
|---|---|---|
| 1 | Rubric, assumptions, small models, environment setup | 25 |
| 2 | Four mocked tools, explicit registry, three data files | 35 |
| 3 | Injectable client, bounded tool loop, structured proposal | 55 |
| 4 | Core policy, safe fallbacks, working CLI | 40 |
| 5 | Focused offline tests and three live sample reviews if a key is available | 50 |
| 6 | README and one-page write-up | 35 |

Core target: 240 minutes. Optional hardening: at most 60 more minutes, for a total planning cap of five hours. This is an estimate, not a guarantee. Prioritize a complete working flow and reserve documentation time. If time is tight, omit extra CLI formatting, diagnostic fields, repeated live runs, and additional failure fixtures. Do not expand the architecture or weaken basic failure handling to meet the estimate.

Must-have: the complete flow, four tools, shared rubric, core policy/fallbacks, focused tests, three sample outputs reviewed with a real model when possible, README, and write-up. Optional hardening is not a prerequisite for submission.

## 14. Documentation and scope

README: setup, tested Python/dependencies/model, environment variables, CLI examples, offline test commands and CLI commands for live sample review, mock assumptions, simulated side effects, limitations.

WRITEUP (one page maximum): architecture and rubric; evidence and failure handling; limits of semantic classification and promise detection; production evaluation and shadow rollout.

Out of scope: UI, auth, persistence, real integrations, FastAPI, agent frameworks, embeddings/vector databases, incident correlation, and monitoring infrastructure. Reconsider only after the required submission works and a concrete need emerges.

## 15. Definition of done

- [ ] Original sample conversations are preserved and all added facts are labeled mock assumptions.
- [ ] One shared urgency rubric is incorporated into the prompt and used by policy/evaluation.
- [ ] Four schema-defined tools work; required usage and customer scope are checked.
- [ ] Agent produces structured decisions with recorded tool results, validated KB article IDs, and coherent final fields.
- [ ] Loop limits, tool failures, invalid output, and API errors produce safe fallbacks.
- [ ] Offline tests pass without a key or network.
- [ ] All three samples have been reviewed with a real model when a key is available; otherwise the validation gap is explicit.
- [ ] README makes setup and execution reproducible; WRITEUP is at most one page.
- [ ] No secrets or local environment files are included; submission is available as a repository or permitted ZIP.
