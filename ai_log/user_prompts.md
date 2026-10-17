# Prompt Log

Below are the key prompts and instructions given to the AI assistant during the development and verification of the freight audit harness:

### 1. Initial Assessment & Plan

Act like a senior software engineer, technical mentor, codebase investigator, and beginner-friendly programming instructor. Your expertise is in reverse-engineering unfamiliar assignment repositories, interpreting technical specifications, identifying hidden requirements, and preparing learners to implement correct solutions independently.

Your goal is to help me fully understand my assignment, its purpose, requirements, constraints, evaluation criteria, and implementation strategy before any code is written or modified.

Task: Conduct a thorough, evidence-based investigation of the entire assignment repository and produce a comprehensive, beginner-friendly technical briefing. You must not implement, modify, create, delete, or refactor anything until I explicitly authorize implementation in a subsequent message.

Follow these steps in order:

Step 1 — Map the repository.
Inspect the directory structure and identify the purpose of important files and folders. Examine the README, assignment instructions, documentation, source code, configuration files, dependencies, tests, fixtures, sample inputs and outputs, grading rubrics, submission instructions, and relevant Git history. Inspect hidden files and scripts when accessible and relevant. Follow cross-references to discover additional requirements.

Step 2 — Reconstruct the assignment.
Explain the problem in plain English, assuming I am a beginner. Describe the expected outcome, the problem being solved, the required functionality, inputs, outputs, constraints, edge cases, assumptions, and any concepts I need to understand. Define technical terms and acronyms when first introduced.

Step 3 — Extract every requirement.
Separate explicit requirements, inferred requirements, optional features, restrictions, and unknowns. Identify passing criteria, test expectations, grading priorities, required interfaces, and submission conditions. Support important claims with exact file paths and line numbers when available. Never invent missing requirements.

Step 4 — Explain the existing codebase.
Describe the architecture, execution flow, key modules, functions, classes, data structures, dependencies, and interactions. Explain what already exists, what is incomplete, and how the components relate to the assignment. Distinguish verified facts from reasonable inferences.

Step 5 — Assess readiness and risks.
Identify likely implementation challenges, tricky edge cases, ambiguous instructions, potential failure points, relevant tests, and environmental setup requirements. Explain what must be clarified or verified before implementation.

Step 6 — Prepare an implementation roadmap.
Present a prioritized, step-by-step plan with the purpose of each step, relevant files, expected outcomes, and corresponding tests. Explain the reasoning behind major technical choices without exposing private chain-of-thought. Do not execute this plan.

Step 7 — Deliver the briefing.
Organize the report into: Executive Summary, Assignment Explained Simply, Repository Map, Complete Requirements Checklist, Existing Code Walkthrough, Testing and Grading Criteria, Risks and Unknowns, Key Concepts to Learn, and Proposed Implementation Roadmap. End with a concise checklist of what I should understand before authorizing implementation.

Constraints:
- Inspect actual repository evidence rather than relying on assumptions.
- Do not skip relevant files merely because the repository is large; investigate in manageable, prioritized passes.
- Use tools to inspect files and Git history when available. If access is missing, state the limitation and its impact.
- Do not run destructive commands, install dependencies, modify files, or execute untrusted code. Read-only inspection is permitted.
- Do not begin implementation, generate patches, or make changes under any circumstances before explicit authorization.
- Be detailed but clear, using headings, numbered steps, checklists, and concrete examples.
- Do not claim tests pass unless you actually ran them and verified the results. Report any tests you cannot run.
- Before finalizing, cross-check the briefing against the assignment instructions, repository evidence, and grading criteria. Clearly flag unresolved questions and distinguish facts from assumptions.

Take a deep breath and work on this problem step-by-step.


### 2. Deep Dive & Architectural Strategy

Act like a senior software engineer, repository auditor, technical specification analyst, and documentation verification specialist. Your expertise is in tracing classification logic, validating mathematical formulas, identifying inconsistencies across documentation, and explaining persistent state across independent batch processes.

Your goal is to produce a precise, evidence-backed understanding of every Markdown (.md) file, all glossary formulas, the six problem classes, conflict handling, the cannot_determine outcome, and disk persistence between batch processes. Treat the actual repository and its documentation as the source of truth.

Task: Conduct a systematic, read-only audit of the repository and explain the exact definitions, formulas, detection criteria, decision rules, and persistence mechanisms. Do not implement, modify, or repair anything.

Step 1 — Inventory and inspect documentation.
Locate every .md file in the repository, including nested directories. Read each file completely, following relevant cross-references into source code, configuration files, tests, fixtures, and scripts. Identify missing files, inaccessible content, duplicate definitions, and documentation that appears outdated.

Step 2 — Verify glossary formulas.
Extract every glossary formula and its associated definitions, variables, assumptions, thresholds, and units. Recalculate or independently validate each formula where possible. Compare formulas against their implementations and tests. Flag inconsistencies, undefined variables, ambiguous notation, boundary-condition errors, and unsupported claims. Preserve the original formulas and clearly distinguish verified results from suspected defects.

Step 3 — Map the six problem classes.
Identify the exact names and definitions of all six problem classes from repository evidence. For each class, document its detection criteria, required conditions, inputs, decision rules, thresholds, exclusions, edge cases, and representative examples. Trace each criterion to the relevant implementation, configuration, documentation, or test. Do not infer missing criteria without explicitly labeling them as unknown.

Step 4 — Analyze conflicts and cannot_determine.
Explain precisely how conflicts are identified, what conditions trigger them, how competing classifications are handled, and whether precedence, tie-breaking, or resolution rules exist. Define cannot_determine, enumerate its triggering conditions, explain when it differs from a conflict or an ordinary negative result, and identify any fallback behavior. Highlight overlapping criteria and contradictory rules.

Step 5 — Trace disk persistence across batch processes.
Follow the complete lifecycle of persisted state: initial creation, serialization, file paths, read/write operations, updates, process termination, subsequent batch startup, state restoration, and final output. Identify which information survives between processes, which state remains in memory only, and how checkpoints, caches, locks, atomic writes, concurrent access, errors, and recovery are handled when applicable. Verify claims against actual code and tests rather than assuming persistence behavior.

Step 6 — Cross-validate findings.
Build traceability links between documentation, formulas, implementation, configuration, tests, and observed behavior. Identify contradictions, missing test coverage, undocumented assumptions, and any behavior that cannot be verified from available evidence.

Step 7 — Deliver the audit report.
Organize the findings into:
1. Executive Summary
2. Markdown File Inventory and Verification Status
3. Glossary Formula Audit
4. Six-Class Definition and Detection Matrix
5. Conflict and cannot_determine Decision Logic
6. Disk Persistence and Cross-Batch Lifecycle
7. Documentation–Implementation–Test Discrepancies
8. Unverified Questions, Risks, and Evidence Gaps

Constraints:
- Cite exact file paths and line numbers whenever available.
- Use tables for comparisons and decision criteria; include concrete examples for ambiguous cases.
- Label each finding as verified, contradicted, inferred, or unknown.
- Never fabricate definitions, formulas, thresholds, file contents, or execution results.
- Do not modify files or execute destructive operations. Run code or tests only if explicitly permitted and demonstrably safe.
- If the six classes cannot be identified unambiguously, report the discrepancy instead of guessing.
- Prioritize completeness, traceability, and technical precision over brevity.

Before finalizing, verify that every Markdown file, every discovered glossary formula, all six problem classes, conflict handling, cannot_determine, and cross-process disk persistence have been explicitly addressed. State any limitations that prevent a complete verification.

Take a deep breath and work on this problem step-by-step.


### 3. Implementation & Testing

Act like a senior software engineer, modular implementation architect, test automation specialist, and assignment-compliance auditor. Your expertise is in implementing complex repository changes incrementally, preserving existing behavior, diagnosing grading failures, and ensuring that generated answer sheets exactly match their authoritative answer keys.

Your goal is to implement the required solution across parsing, repricing, auditing, feedback, and gating, then verify it against the official grading workflows. Deliver a correct, reproducible implementation that satisfies all five hard gates and produces an exam answer sheet consistent with the official key.

Task: Inspect the repository, implement the solution in independently verifiable modules, run the required grading commands, and resolve verified failures without introducing unrelated changes.

Step 1 — Establish the baseline.
Inspect the README, assignment specifications, all relevant Markdown documentation, glossary formulas, source code, configuration, tests, fixtures, official grader, grading scripts, answer key, and exam answer sheet. Identify the exact requirements, expected interfaces, dependencies, and acceptance criteria. Determine what the five hard gates mean from repository evidence; do not invent their definitions. Inspect the current Git status and preserve unrelated user changes.

Step 2 — Build an implementation plan.
Map dependencies between parsing, repricing, auditing, feedback, and gating. Identify shared data structures, inputs, outputs, validation rules, and persistence requirements. Implement in dependency order, defining clear module boundaries and minimizing unnecessary changes.

Step 3 — Implement incrementally.
Complete each module separately:
- Parsing: implement required input interpretation, normalization, validation, and error handling.
- Repricing: implement the specified formulas, thresholds, and calculations exactly as documented.
- Auditing: enforce traceability, consistency checks, and required audit outputs.
- Feedback: implement the prescribed feedback generation, recording, and handling behavior.
- Gating: implement all five hard gates using their authoritative definitions and ensure failures cannot be silently bypassed.

After each module, run relevant targeted tests, inspect the results, and fix regressions before proceeding. Do not add unsupported features or weaken requirements to make tests pass.

Step 4 — Verify official grading.
Run `make grade` and `make sheet` from the appropriate repository location. Inspect their definitions before execution, understand their side effects, and confirm they are safe. Capture actual exit codes, failures, warnings, generated artifacts, and relevant output. Diagnose failures at their source rather than suppressing checks or altering the grader to manufacture success.

Step 5 — Validate the five hard gates.
Create a verification matrix listing each gate, its exact requirement, implementation location, relevant tests, observed result, and any remaining gaps. Confirm that all five gates pass independently and collectively. If any gate fails, report the failure explicitly and continue debugging where appropriate.

Step 6 — Reconcile the exam answer sheet.
Identify the authoritative answer key and the generated or maintained exam answer sheet. Compare them question by question, preserving identifiers, ordering, answer formats, and required conventions. Report missing, extra, duplicated, or mismatched answers. Correct discrepancies only in the intended solution artifacts, never by changing the authoritative key or grading criteria. Rerun `make sheet` and verify the final output against the key using a reproducible comparison.

Step 7 — Deliver the final report.
Summarize the modules implemented, files changed, design decisions, tests executed, exact grading results, status of all five gates, answer-sheet reconciliation, unresolved issues, and commands needed to reproduce verification. Distinguish verified success from incomplete or unverified results.

Constraints:
- Follow repository specifications and the official rubric over assumptions.
- Preserve existing interfaces and unrelated changes.
- Never fabricate test results or claim a gate passes without evidence.
- Do not bypass, weaken, or modify official grading criteria to obtain a passing result.
- Keep changes modular, minimal, and maintainable.
- If required files, definitions, or tools are missing, explain the limitation and proceed only where the evidence supports implementation.
- Continue until the required checks pass or a concrete blocker prevents further progress.

Take a deep breath and work on this problem step-by-step.


### 4. Custom Evaluation Suite

Act like a senior software engineer, quality assurance architect, adversarial testing specialist, and regression testing expert. Your expertise is in designing deterministic, maintainable test suites that expose subtle boundary conditions, security vulnerabilities, parsing errors, and date-dependent logic defects in existing codebases.

Your goal is to build a comprehensive regression test suite under `evals/cases/` that protects the repository's required behavior, captures previously overlooked edge cases, and verifies that all evaluation cases pass through the official evaluation workflow.

Task: Inspect the repository, design and implement focused regression cases, and validate them using `make eval`.

Step 1 — Inspect the existing system.
Read the relevant README files, assignment specifications, Markdown documentation, glossary definitions, source code, configuration, existing evaluation cases, test fixtures, and the Makefile. Determine the evaluation framework's expected case format, naming conventions, assertion semantics, execution behavior, and pass/fail criteria. Trace each requested edge case to the actual implementation and authoritative requirements before writing tests.

Step 2 — Design the regression matrix.
Create explicit positive, negative, and boundary cases for each area:

1. Prompt injection defense: Test direct and indirect injection attempts, conflicting instructions embedded in untrusted content, attempts to override system-defined policies, and legitimate inputs containing instruction-like text. Verify that untrusted content cannot improperly change the required behavior and that valid requests continue to work.

2. One-off waiver boundaries: Test the precise conditions under which a one-off waiver is permitted, rejected, consumed, or expired. Cover valid single-use cases, repeated use, near-boundary values, missing prerequisites, and attempts to extend a waiver beyond its authorized scope. Derive exact expected outcomes from repository specifications.

3. Three-letter invoice prefixes in AP registers: Test valid three-letter prefixes, case sensitivity, malformed or missing prefixes, adjacent prefix lengths, invoice-number boundaries, and collisions with similar identifiers. Verify correct parsing, normalization, matching, and rejection behavior according to the documented rules.

4. Pickup date period transitions: Test dates immediately before, on, and after relevant period boundaries, including month-end, year-end, leap days where applicable, and transitions between configured reporting periods. Verify timezone handling and inclusive/exclusive boundary rules wherever supported.

Step 3 — Implement the cases.
Add appropriately named, independent cases under `evals/cases/`, following the existing schema and conventions. Give each case a clear purpose, representative input, explicit expected outcome, and a concise explanation of the regression it prevents. Include both ordinary scenarios and minimal counterexamples that isolate individual failure conditions. Avoid duplicating existing coverage unnecessarily.

Step 4 — Verify correctness.
Inspect the generated test files for schema validity, deterministic expectations, and consistency with authoritative requirements. Run `make eval`, inspect its actual exit status and detailed results, and diagnose failures. Fix incorrect tests or genuine implementation defects only when the evidence establishes the cause. Do not weaken assertions, modify evaluation criteria, or hardcode outcomes merely to force a pass.

Step 5 — Report results.
Summarize the cases created, their locations, the edge conditions covered, the evaluation command and its verified result, any regressions discovered, and any unresolved gaps. Distinguish newly added coverage from behavior that has actually been verified.

Constraints:
- Preserve unrelated files and existing user changes.
- Do not invent undocumented rules, expected outputs, thresholds, or date semantics.
- Keep cases focused, reproducible, and consistent with the repository's evaluation framework.
- Inspect the Makefile before running commands and avoid destructive operations.
- Do not claim success unless `make eval` completes and its result is verified.
- If requirements are ambiguous, document the uncertainty and use the strongest evidence available rather than guessing.
- Prioritize meaningful coverage, security, boundary precision, and maintainability.

Take a deep breath and work on this problem step-by-step.


### 5. Final Compliance & Validation

Act like a senior software engineer, repository-wide validation specialist, schema compliance auditor, and automated quality assurance engineer. Your expertise is in diagnosing validation failures, enforcing machine-readable specifications, verifying citation integrity, checking word-count constraints, and ensuring report cards satisfy every required acceptance criterion.

Your goal is to validate the entire repository using `make validate` and establish whether every applicable schema requirement, word limit, citation lookup, and report card check passes with 100% compliance. Base all conclusions on actual validation results and authoritative repository requirements.

Task: Inspect the repository's validation workflow, execute `make validate` safely, investigate every failure, and verify the final compliance status without weakening the requirements.

Step 1 — Inspect the validation framework.
Review the README, assignment instructions, relevant Markdown documentation, Makefile, validation scripts, schemas, configuration files, evaluation cases, citation sources, word-count rules, report card definitions, and existing tests. Determine exactly what `make validate` executes, which artifacts it checks, how errors are reported, and what constitutes a complete pass.

Step 2 — Establish the baseline.
Inspect the Git working tree and preserve unrelated user changes. Run `make validate` from the appropriate repository location after checking its commands and potential side effects. Capture the actual exit code, complete output, failed checks, warnings, skipped checks, and generated artifacts. Do not infer success from partial output.

Step 3 — Audit schema compliance.
Verify every applicable artifact against its authoritative schema. Check required fields, data types, enumerated values, formatting, structural constraints, missing fields, unexpected fields, and cross-field consistency. Identify every violation and its exact file and location.

Step 4 — Verify word limits and citations.
Check all applicable minimum and maximum word limits using the repository's actual counting rules. Verify citation syntax, reference resolution, lookup behavior, source identifiers, and required citation coverage. Distinguish malformed citations from valid citations pointing to missing, inaccessible, or unverified sources. Never fabricate references or claim a lookup succeeded without evidence.

Step 5 — Audit report cards.
Identify every report card and its required checks. Verify completeness, scoring rules, consistency with underlying evidence, required sections, thresholds, and cross-artifact relationships. Report each check's expected condition and observed result.

Step 6 — Remediate and revalidate.
If failures are found, trace each to its root cause and make the smallest justified corrections to intended repository artifacts. Do not alter schemas, weaken assertions, bypass checks, suppress errors, or manipulate scoring to manufacture compliance. Rerun `make validate` after corrections and inspect the complete final results. If changes are prohibited, report the necessary fixes without applying them.

Step 7 — Deliver the compliance report.
Provide:
1. Overall validation status and verified pass/fail result.
2. A checklist of every required validation category.
3. Failed checks, affected files, root causes, and corrective actions.
4. Remaining warnings, skipped checks, and verification limitations.
5. Files changed and the final validation command output summary.
6. An explicit conclusion stating whether 100% compliance was demonstrated.

Constraints:
- Treat repository specifications and validation logic as authoritative.
- Do not invent requirements, results, citations, or success claims.
- Preserve unrelated changes and avoid destructive operations.
- Distinguish passed, failed, skipped, and unverified checks.
- Claim 100% compliance only when every applicable required check has demonstrably passed.
- If the command fails or cannot run, explain the blocker and continue with safe, targeted investigation.

Take a deep breath and work on this problem step-by-step.

