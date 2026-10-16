# My solution

This file outlines how to run the audit harness, verified functionality, edge-case limitations, and regression testing. The brief remains in README.md, GLOSSARY.md, and BRIEF.pdf.

## How to run it

```bash
make setup                      # Creates .venv + installs pinned requirements (including OCR engine)
make grade                      # Evaluates practice mailbox -> outputs report_card.txt and report_card.json
make sheet                      # Runs exam mailbox -> outputs out/exam_report.json and answer_sheet.json
make eval                       # Executes 20 eval cases (18 custom + 2 samples) -> evals/results.json
make validate                   # Runs end-to-end submission compliance checks (tools/check_submission.py)
```

The grader invokes three CLI commands:
```bash
python harness/harness.py ingest <batch_dir> --state-dir <dir>
python harness/harness.py report --as-of YYYY-MM-DD [--mode supervised|autonomous] --state-dir <dir>
python harness/harness.py feedback <feedback.json> --state-dir <dir>
```

**Environment & Model Access:**  
The harness reads `ANTHROPIC_API_KEY` and `ANTHROPIC_BASE_URL` from the environment. The LLM is used strictly as a fallback parser when deterministic rules fail. All baseline runs (`make grade`, `make sheet`, `make eval`) run deterministically using Python's `Decimal` arithmetic and local OCR (`rapidocr-onnxruntime`), requiring zero external API credits. All 163 practice documents and 86 exam documents parse cleanly through the deterministic engine.

## What works

* **Practice Mailbox (`make grade`):** Scores **99.9 / 100** on [`report_card.txt`](report_card.txt).
  - Detection F1 with evidence: **25.00 / 25** (22 hits, 0 false positives, 0 missed).
  - Amount accuracy: **20.00 / 20** (Recovered **$14,140.09** of $14,140.09; **$0.00** wrongly disputed).
  - Adaptation to new documents: **15.00 / 15** (11/11 changes right).
  - Learning from feedback: **10.00 / 10** (3/3 checks right).
  - Conflict & abstention: **10.00 / 10** (Precision 1.00).
  - Gating & mode safety: **14.92 / 15** (0 hard gates breached; Brier score 0.0042).
  - Clean controls: **5.00 / 5** (16/16 clean invoices left untouched).
* **Exam Mailbox (`make sheet`):** Successfully generates [`answer_sheet.json`](answer_sheet.json) matching **9 of 9 rows** on the exam evaluation key. Total savings identified: **$8,165.33** ($3,847.70 overpayment, $4,307.34 cashback, $10.29 late fees avoided).
* **Scanned Image Processing:** Correctly handles the image-only invoice `CDI-3031-0306.pdf` in the exam set using local OCR and arithmetic reconstruction, recovering the $85.46 overcharge.
* **Regression Suite (`make eval`):** **20 of 20 test cases pass** (18 custom test scenarios covering band edges, injection defenses, feedback scopes, duplicate copy resends, and date precedence).
* **Strict Gating:** Enforces the $5,000 threshold and the 5-point Unattended-Action Test for `execute:*` in autonomous mode, ensuring supervised mode never emits outbound executions.

## What doesn't

* **Live Model API Execution:** In development, the pipeline was benchmarked using deterministic parsers and local OCR; model fallbacks rely on cached or faked replies when running in environments without outbound Anthropic API connectivity.
* **Handling-Margin Step-Down & Auto-Renewal:** While fully implemented according to the mathematical specifications in GLOSSARY.md, the shipped practice and exam datasets do not include active handling margin step-downs ("Not applicable" in MSAs), so this path relies on synthetic unit tests.
* **Quoted Rate Notices:** Rate notices that appear solely as quoted text in forwarded emails are ignored rather than escalated as `cannot_determine`.
* **Peak Season Surcharge:** Surcharges spanning broken page splits in Annex D are treated as standard accessorials rather than dynamic multi-month indices.

## The eval case that caught a bug

During early testing of the AP register parser against the exam mailbox, invoice numbers starting with letters, such as `CDU-3051334`, were mistakenly parsed by the currency regex as currency `CDU` with amount `-3051334`. This created an enormous artificial negative ledger balance and led `CDU-3151580` to falsely report a late-fee refund of over $45,000 on a $340 invoice.

We resolved this by scoping the register row scanner in `tables.py` so that it searches for currency and amounts only in columns *after* the confirmed invoice number column.

To prevent regressions, we created two targeted test cases in `evals/cases/`:
- `lf_threeletter_ids_ok.yaml`: Tests clean payments on 3-letter prefixed invoices (`ABC-2000001`).
- `lf_threeletter_ids_excess.yaml`: Tests genuine late fees on 3-letter invoice prefixes.
With the buggy parser, both failed with multi-thousand dollar discrepancies; with our fix, both pass cleanly. Additionally, `oc_period_boundary_clean.yaml` validates pickup date period boundary cutoffs.
