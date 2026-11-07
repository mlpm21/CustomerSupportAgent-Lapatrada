## Architecture decisions and why

- **The LLM interprets; code checks.** The model reads the full multilingual conversation, chooses tools, and returns a Pydantic-validated proposal. Deterministic policy can raise the action from auto-response to specialist routing or human escalation, never lower it. Code assigns outage/billing teams. The trade-off is more human review; I would relax rules only with evaluation data.
- **Urgency and action are separate.** A high-risk billing dispute needs a human without necessarily being critical. A shared urgency rubric informs the prompt; policy checks the proposed urgency alongside recorded evidence.
- **Tools provide evidence.** Four read-only mocked tools supply history, billing, keyword KB search, and status. Customer scope, retrieved article IDs, and customer-region status are checked in code. Repeated charge-like events can escalate billing independently of urgency. A green public page does not disprove reported failures.
- **Small and extensible.** Flat modules and an explicit registry simplify adding tools. An injectable client and mocked HTTP transport support offline tests. Replies and handoffs are simulated; live-model verification remains pending.

## What could go wrong and how I'd handle it

- **Misclassification.** Policy cannot recover impact or secondary issues the model missed. Measure critical-ticket recall and retain human review for risky categories.
- **Unsupported promises.** The prompt prohibits refund and recovery-time promises. Changed actions, empty drafts, and failed runs use safe English/Thai acknowledgments; team-only corrections retain tailored drafts. Unchanged replies are not screened. Output screening and human review are future safeguards.
- **Prompt injection.** Ticket/KB content is delimited as untrusted. Read-only tools and customer-ID checks limit exposure but do not guarantee immunity.
- **Execution failures.** Expected tool errors become structured results. Missing required evidence, invalid citations, or failed runs require human escalation. API failures, refusals, and invalid output are recorded; rejected credentials/access/models stop the CLI. Tool rounds, request timeouts/retries, and output repair are bounded. Exhausted rounds still request a proposal but prohibit auto-response.
- **Conflicting or incomplete evidence.** Surface public/internal status conflicts and uncertainty. Keyword relevance does not prove answer coverage or freshness; production needs document review and sampled audits.
- **Language and privacy.** Review Thai replies manually. Fallbacks support only English/Thai. Diagnostic queries may contain PII; production needs redaction and restricted logs.

## How I'd evaluate this agent in production

Use a labeled historical golden set covering urgency, languages, billing, outages, and mixed questions. Track critical-ticket recall, unsafe auto-response rate, action agreement, tool correctness, human override rate, latency, and cost. Assess grounding, tone, language, and coverage through human review supported by a calibrated LLM judge. Rerun regressions after KB/model changes and monitor drift. Start in shadow mode; automate only demonstrated low-risk categories. Offline tests verify code behavior, not real-model quality.
