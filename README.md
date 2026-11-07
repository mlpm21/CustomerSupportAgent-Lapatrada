# Support Ticket Triage Agent

## Ownership and permitted use

Copyright © 2026 Lapatrada Liawpairoj. All rights reserved.
This project is provided for recruitment evaluation only. Commercial use,
redistribution, or incorporation into another product requires prior written
permission. See [LICENSE](LICENSE) for the full terms; third-party and
employer-provided materials retain their respective rights.

## Overview

A Python CLI that reads complete support conversations, classifies urgency,
extracts product / issue type / sentiment, searches documentation, and proposes an
auto-response, specialist route, or human escalation. Four read-only mocked tools
provide customer history, billing events, KB articles, and regional status.

**All replies and handoffs are simulated.** No messages are sent, accounts changed,
or queues updated. Live CLI mode requires OpenAI access. The optional --demo mode, tools, and tests run locally.

## Offline demonstration

After installing dependencies, inspect the full results without a key:

```bash
python main.py --all --demo
python main.py --ticket 2 --demo
python main.py --ticket 2 --demo --json
```

Demo mode uses hand-written sample proposals in `demo.py`, actual local tools, and
the normal policy checks. Every output explicitly identifies the AI response as
simulated; JSON includes `mode: demo` and a notice. It does not call a model or
classify new tickets. Normal runs without `--demo` still require a key and model.

Ticket 1’s scripted reply makes priority billing-specialist review explicit
without claiming a handoff occurred. Demo screenshots and internal planning /
verification notes are kept locally and are not part of the public repository.

## Real API setup

Python 3.11+ is required for `StrEnum` and `typing.Self`. The offline suite was
verified here on Python 3.15. Python 3.12 testing is reported by the project owner
but has not been independently rerun in this environment.

From the repository root, on macOS/Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

On Windows PowerShell, activate with `.venv\Scripts\Activate.ps1` and copy the
example with `Copy-Item .env.example .env`.

Create your own key in the [OpenAI API dashboard](https://platform.openai.com/api-keys)
and ensure the associated API project has available credits/billing and model access.
Keep the key local; do not send it to anyone or commit it.

Edit the local `.env`:

```dotenv
OPENAI_API_KEY=your-api-key
OPENAI_MODEL=gpt-5.4-mini
```

Suggested starting model: **`gpt-5.4-mini`**, subject to your API project's access.
The [official model documentation](https://developers.openai.com/api/docs/models/gpt-5.4-mini)
lists Chat Completions, function calling, and structured outputs as supported.
For a fixed version, use `gpt-5.4-mini-2026-03-17` if available to your project.
This is a documentation-based recommendation, **not a model live-tested with this
application**. Real-model behavior and latency remain unverified. You may choose
another accessible chat model supporting tool calling and structured output via
`client.chat.completions.parse`. The application reads `OPENAI_MODEL`; it has no
hardcoded model or fallback. Dependencies are pinned in
`requirements.txt`. No API key is committed; `.env` is Git-ignored. Environment
variables already set in the shell take precedence over `.env`. Live calls require
network access and may incur API charges. Installing dependencies also needs
package access; running the installed offline suite does not.

## Run with the real API

After configuring `.env`, activate the virtual environment and run from the
repository root. **Do not add `--demo`**: these commands call your selected
OpenAI model using your API key. The four tools still use local mock data, and
customer replies/handoffs remain simulated:

```bash
python main.py --all
python main.py --ticket 2
python main.py --ticket ticket-2 --json
python main.py --all --json --verbose
python main.py --help
```

Exactly one of `--all` or `--ticket` is required. Ticket selectors accept `1`, `2`,
`3`, or `ticket-1` through `ticket-3`. `--all` processes the samples sequentially.

Plain output groups related information into five sections:

- **Decision:** urgency, action, team, completion status, and summary.
- **Ticket details:** product, issue type, sentiment, language, and secondary tags.
- **Evidence:** tool outcomes and cited KB article IDs.
- **Policy changes:** actual overrides, or a note that the proposal was retained.
- **Customer reply:** wrapped reply text, followed by the simulation notice.

`completed` means triage finished, not that the customer’s issue was resolved.
`Product: unknown` means no product was established. Repeated KB calls represent
separate searches, and no policy changes means the proposal already met the rules.
`--json` emits one final-decision object with a tool-call summary for one ticket,
or a list for `--all`. The original proposal remains nested for audit; consumers
should use the `final_*` fields.

`--verbose` writes diagnostics to **stderr**, keeping JSON stdout parseable. It
allowlists customer ID, region, and search query arguments, flattens newlines, and
truncates each to 100 characters. It omits raw customer messages, tool/billing
payloads, card-reference fields, and hidden reasoning. This is field omission,
not general PII redaction: a model-generated query can still contain sensitive text.

Missing model/key configuration, or an API AuthenticationError, PermissionDeniedError,
or NotFoundError, prints a one-line stderr error and exits **2** without a traceback.
A rejected key, insufficient access, or unknown model stops the batch. A handled agent failure still prints a valid human-escalation
decision (`status: failed`) and exits **0**; inspect the decision status. Unexpected
application bugs propagate rather than being disguised as model failures.

## Tests

```bash
pytest -q
```

The 94 cases are fully offline: no real API key or external network requests.
Most agent tests use a scripted fake client; SDK integration tests use the real
OpenAI client with a local-only mock HTTP transport. No requests reach OpenAI.
They cover actual mock-tool results and schemas, retrieval rankings, access/error
boundaries, policy rules, draft retention, English/Thai acknowledgments, scripted
agent tool exchanges, refusal/API/output failures, tool-budget routing, and CLI configuration
and verbose formatting. Offline tests also work without a `.env` file.

Run just the real-SDK integration checks without API access:

```bash
pytest -q tests/test_sdk_integration.py
```

These checks exercise actual request serialization and response parsing for all
three scripted sample flows, text/JSON output, and simulated 401/403/404/429/500
responses. SDK retries are disabled inside these tests to avoid backoff delays;
production retry configuration is unchanged. The proposed decisions are scripted,
not generated by a real model.

These tests verify orchestration and deterministic rules, **not real-model
classification, language quality, answer coverage, or compliance with prompt rules**.

## How it works

```text
Full ticket conversation
  -> LLM tool-calling loop <-> read-only mock tools
  -> recorded tool results + final structured proposal (tools disabled)
  -> deterministic policy checks
  -> final decision + simulated CLI output
```

Urgency describes impact and time sensitivity; action describes what happens next.
For example, high-urgency billing risk can require human escalation without being
critical. The rubric and implemented policy live in [policy.py](policy.py);
[prompts.py](prompts.py) imports the rubric instead of duplicating it.

| Policy condition | Final behavior |
|---|---|
| Missing proposal or failed run | Human escalation, product_support, unknown urgency, safe acknowledgment |
| Missing successful history / KB call, or domain-specific billing / outage evidence | Human escalation |
| Outage status not verified for the region in customer history, or customer region unknown | Human escalation |
| Cited KB IDs absent from successful search results | Human escalation |
| Critical urgency, or high/critical billing issue | Human escalation |
| Billing issue with two same-amount, same-currency pending authorizations or captured payments within 24 hours | Human escalation; failed/refunded events do not count |
| Tool-round budget exhausted | Request a proposal from existing evidence; at least specialist routing, never auto-response |
| Billing/outage proposed for auto-response | At least specialist routing |
| Auto-response without cited KB IDs | At least specialist routing; product_support unless a domain team applies |
| Outage / billing among primary or secondary issue types | Code assigns infrastructure first, otherwise billing |
| Other non-auto action with team none | Code assigns product_support; auto-response always uses none |
| Action changed or draft empty | Safe acknowledgment; otherwise retain the tailored draft, including after team correction |

Actions only move upward: auto-response -> specialist -> human. Valid proposal
urgency is preserved. Override reasons record actual action/team/draft changes or
run failure; they are not a complete inventory of all matched rules. Missing
evidence escalates directly, without a second evidence-collection loop.

The agent allows 5 completion rounds for tool collection, a final structured call,
and one repair attempt. If tool rounds are exhausted, it still requests a structured
proposal and marks the run; policy prevents auto-response. Missing evidence still
requires escalation. Each request has a 30-second timeout and up to 2 SDK
retries for transient errors; these are not a 30-second overall run deadline.

## Project structure

```text
main.py                      CLI selection, output, diagnostics
agent.py                     Injectable client, bounded loop, structured proposal
demo.py                      Explicit scripted proposals for the three demo samples
config.py                    Environment and execution limits
models.py                    Pydantic schemas and enums
policy.py                    Shared rubric, final rules, safe acknowledgments
prompts.py                   System instructions and untrusted-ticket rendering
tools/__init__.py            Explicit registry, schemas, scoped execution
tools/common.py              Fixture loading, argument base, expected errors
tools/customer_history.py    Customer context lookup
tools/billing.py             Billing event lookup
tools/knowledge_base.py      Keyword FAQ retrieval
tools/system_status.py       Synthetic regional status snapshots
data/tickets.json            Original sample customer messages and time labels
data/customers.json          Customer attributes and synthetic billing events
data/faqs.json               Ten synthetic English FAQ articles
tests/test_policy.py         Policy and fallback checks with real tool evidence
tests/test_tools.py          Tool schemas, outcomes, retrieval, errors
tests/test_agent.py          Scripted fake-client orchestration checks
tests/test_cli.py            Configuration errors and verbose-output checks
tests/test_sdk_integration.py Real SDK, simulated HTTP, tools, policy, and CLI checks
pytest.ini                   Test discovery and root import path
requirements.txt             Pinned runtime and test dependencies
.env.example                 Empty key/model configuration template
.gitignore                   Secrets, local artifacts, private assignment docs
LICENSE                      Copyright and recruitment-evaluation terms
README.md                    Setup and reviewer guide
WRITEUP.md                   Architecture, risks, production evaluation
```

## Adding a tool

1. Add a module under `tools/` exporting `name`, `description`, a Pydantic `Args`
   model (reuse `ToolArgs`), and a read-only `run` function. Use `ToolError` for
   expected failures; return JSON-compatible data.
2. Import the module and add it to the explicit registry in `tools/__init__.py`.
   Schemas come from `Args`; execution validates arguments and customer scope.
3. Add clearly labeled fixture data when needed, using project-relative loading.

Add appropriate tests and update prompt/policy requirements if the new tool
changes which evidence is necessary for a decision.

## Mock data and assumptions

Customer wording, relative-time labels, plan, tenure, and explicitly supplied
customer attributes come from the assignment. No agent messages or absolute
timestamps were invented. Customer IDs are local identifiers.

- Ticket 1: three $29.99 USD **pending authorizations**, their relative ages and
  sanitized two-card references are synthetic tool evidence. They do not establish
  three captured payments. No Pro entitlement is the fixture assumption.
- Ticket 2: Thailand maps to mock region `ap-southeast`. The internal degraded
  gateway incident and operational public snapshot are invented. SLA is unknown;
  first critical issue does not imply no previous noncritical tickets.
- Ticket 3: daily usage and plan are supplied; installed app version and verified
  entitlement remain unknown. Conditional version/update guidance comes from the KB.
- All ten KB articles, their product behavior, and regional status snapshots are
  synthetic and labeled. Status ages and billing ages refer to the scenario
  snapshot, not the wall clock. Other explicitly modeled regions are synthetic too.
- Null customer attributes mean unknown. Unknown customers/regions and unavailable
  billing data produce errors rather than silently healthy or empty results.

Expected results below are our documented policy choices with these fixtures,
**not assignment-provided ground truth or observed live outputs**.

## Expected sample behavior

| Ticket | Urgency | Action | Team | Required tools | Reply expectations |
|---|---|---|---|---|---|
| 1 Payment attempts and missing Pro | high | escalate_to_human | billing | history, KB, billing | English; acknowledge deadline/dispute risk, distinguish pending events, no refund promise |
| 2 Thai multi-user access failure | critical | escalate_to_human | infrastructure | history, KB, status | Thai; acknowledge impact/status conflict, no recovery ETA |
| 3 Theme issue and scheduling | low | auto_respond | none | history, KB | English; conditional theme troubleshooting plus scheduling answer and feature_request tag |

These expectations assume sufficient successful tool evidence. Policy preserves
a tailored draft when the model already proposes the final action. An action
change or failed run produces the safe acknowledgment instead. Missing evidence
requires escalation; an uncited auto-response requires specialist routing.

## Live verification

**Not yet run.** No API key or model is configured and no real-model results are
claimed. A tested model name and actual per-ticket results should be recorded
after a live run; local verification notes are excluded from the public repository.

## Limitations

Classification and secondary-issue detection remain model-dependent. Code checks
successful tool usage and KB IDs, not semantic answer correctness. There is no
automated promise screening; the prompt prohibition cannot guarantee safe wording.
Keyword retrieval ignores common query stopwords but has no semantic search or
freshness validation. The model is instructed to use English search queries.

Tickets are processed individually; there is no incident correlation, persistence,
authentication, real integration, or actual dispatch. Prompt injection remains
possible despite untrusted-content boundaries and customer-scope checks. Drafts
request the customer's language, but safe acknowledgments support only English and
Thai. Diagnostic queries need stronger PII redaction before use with real data.
