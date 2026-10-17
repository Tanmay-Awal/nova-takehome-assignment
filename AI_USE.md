# AI use

## Tools

* **Google Antigravity (Gemini)**: Used as the primary AI coding assistant and technical pair programmer for codebase inspection, architecture planning, module assembly, test writing, and technical documentation.
* **RapidOCR (`rapidocr-onnxruntime`)**: Local ONNX-based OCR inference engine used to rasterize and extract text layers from scanned image-only invoices without sending data externally.
* No other external code generators or automated tools were used.

## How you worked with them

I directed the AI assistant through a structured, multi-phase plan:
1. First, I directed the assistant to perform an exhaustive investigation of the repository, glossary, mathematical formulas, and the 5 hard gates before writing any code.
2. We analyzed the reference architecture, identifying that a deterministic-first parsing approach (using Python's `Decimal` arithmetic) eliminates floating-point drift and achieves zero LLM token costs on standard documents while protecting against adversarial prompt injections.
3. We iteratively tested and refined the harness:
   - Evaluated `make grade` against practice scenarios to identify edge cases in rate boundary lookups and contract precedence.
   - Identified and resolved an OCR number formatting artifact on scanned document `CDI-3031-0306.pdf`, where dot separators in amounts were being parsed as decimals rather than thousands separators, ensuring accurate INR-to-USD conversion and overcharge calculation.
4. Finally, we constructed an 18-case regression suite in `evals/cases/` and validated all submission criteria.

## Written without AI

- Conceptual decomposition of the freight domain and architectural strategy selection (hybrid deterministic rules vs. pure LLM agent).
- Verification of currency conversion, Annex F rate selection, and pickup date precedence.
- Manual inspection of `answer_sheet.json` against the underlying exam emails and invoice documents.
- Time management, phase prioritization, and submission compliance checks.

## Prompt log

The full record of key prompts and interaction milestones is stored in [`ai_log/user_prompts.md`](ai_log/user_prompts.md).
