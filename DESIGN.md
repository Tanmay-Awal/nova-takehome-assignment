# Design

## Fact model

Every email and attachment is stored under `--state-dir` with its text pages, metadata, UTC received date, and document kind. An on-disk **facts** record (`understand.py`) tracks the extraction method (rules vs. model fallback) and validation issues.

Provenance is preserved: rate rows store the printed line and page (`USE2-INE2 100-299.5 kg 6.01 6.16`, p.8), email facts hold their sentence and quote status, and contract terms track clause numbers. Report citations are verbatim substrings of $\ge 12$ non-space characters, never generated text.

The model only reads documents when deterministic rules fail or clauses require semantic extraction. Its output must pass checks: lines must sum to printed totals, quotes must appear verbatim, and numbers must exist in cited clauses. All financial arithmetic, dates, and policies run in deterministic Python (`pricing.py`, `engine.py`), keeping `report` reproducible, fast, and free of hallucinations.

## Conflicts

Rate resolution for (contract, lane, pickup date) follows contract hierarchy: executed MSA, signed amendments (latest effective date wins per lane), attached Annex A revisions, and notices from Schedule 1 `rates` contacts (or feedback-confirmed notices).

When an amendment and an authorized notice are both in force, the precedence clause decides (`amendment_wins` vs. `notice_wins`). If unranked, the engine declares a **conflict**, reprices under both, and reports `verdict: conflict`, `amount_range: [max(0.00, billed - higher), billed - lower]`, action `escalate`, excluding it from totals while citing both sources.

Unauthorized sources (unlisted senders, quoted forwards, unsigned drafts) cannot trigger conflicts; the authoritative source wins. If a governing instrument cites an unheld document (e.g. an Annex A revision), the verdict is **cannot_determine**, naming the document and assigning the holder to the Schedule 1 contact.

## Confidence

Confidence starts at 0.95 for findings from Level 1–2 instruments with pickup confirmed from tracking. Deductions apply: -0.08 if pickup relies on AWB date, -0.15 if relying on invoice date, and -0.07 if the source is an OCR scan. Fixed baselines: conflicts (0.90), cannot_determine (0.90), cashback (0.90), late-fee risk (0.92), and expiry (0.95).

On the practice mailbox, this yields a Brier score of 0.0042. Because the practice set has no false positives among reported items, AUROC is unmeasurable; weights represent calibrated operational judgements.

## People in the loop

In `supervised` mode:
- Internal actions (`internal:alert`, `internal:payment_reminder`, `internal:track_credit`) execute automatically.
- Outbound remedies are drafts (`draft:dispute`, `draft:claim_credit`, `draft:request_document`).
- Any finding $\ge \$5,000.00$ on one invoice or cashback key escalates to `human_review`.
- Conflicts output `action: escalate`. A hard assertion forbids `execute:*`.

In `autonomous` mode, outbound remedies emit `execute:*` only if all 5 checks of the Unattended-Action Test pass:
1. Complete evidence (no missing docs; pickup verified from tracking or carrier email).
2. No open conflict on the key or contract lane/period.
3. Total outbound exposure on that key is $< \$5,000.00$.
4. Reversible action (dispute, claim, document request; never paying or agreeing to terms).
5. Instrument authority is Level 1–2, and recipient address matches Schedule 1.
Otherwise, the action defaults to `human_review`. Prompt injections addressing "the AI" are recorded as data and ignored.

## Feedback

Feedback from `feedback.json` is stored with metadata, decider identity, and `decided_at`. Subsequent reports evaluate feedback facts as Level 2 evidence starting strictly from `decided_at`.

Scope boundaries are rigidly enforced:
- **Standing facts** apply only when all `applies_to` filters match within `valid_from..valid_to` (`sender_authority` matches person, category, contract; `rate_accepted` matches contract, lane, dates).
- **One-off decisions** (`close`, `reject`, `one_off_approval`, `override_amount`) modify only their designated key and never extrapolate to sibling invoices or future months.
Items altered by feedback append `learned_at: {feedback_item_id, batch}`.

## New documents

State is cumulative. When `report --as-of D` runs, only documents received by D are evaluated. Findings are compared with the previous batch:
- If a verdict or amount updates, the item cites the prior finding in `supersedes`.
- If a backdated contract or amendment introduces a finding on an earlier invoice, it is tagged `retro: true`.
- If an alert date passes or an invoice is settled, the key vacates the report.

Invoices are parsed arithmetically: lines are validated by verifying that `rate x qty = amount` or `pct x base = amount`, allowing new invoice layouts to parse without code modifications.

## Cost

On benchmark mailboxes (249 documents), the deterministic pipeline processed all documents with **0 model calls** in under 15 seconds.

Edge-case documents requiring model fallback average ~3,000 input and ~1,000 output tokens (~$0.025 per call via Sonnet). At an estimated 5% fallback rate in production, cost is approximately **$1.25 per 1,000 documents** (worst-case $25/1,000). Responses are hashed and cached on disk, making replays free. OCR inference runs locally on CPU in ~2 seconds per page.

## What I'd do next

1. Live evaluation against Claude 3.5 Sonnet to stress-test prompt resilience against complex multi-page statements.
2. Synthesize real multi-tier handling margin step-downs to test quarterly threshold transitions.
3. Incorporate automated AWB vs. invoice weight discrepancy checks to catch weight-rounding inflation.
4. Expand OCR bounding box reconstruction to support multi-column tabular image alignment.
