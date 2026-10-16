# Prompt Log

Below are the key prompts and instructions given to the AI assistant during the development and verification of the freight audit harness:

### 1. Initial Assessment & Plan
"Thoroughly investigate the assignment repository, explain the entire problem and its requirements in beginner-friendly language, and prepare me to implement the solution. Do not start implementing anything until I explicitly authorize you. Inspect the README, assignment instructions, documentation, source code, configuration files, tests, grading rubric, passing criteria, examples, and relevant Git history."

### 2. Deep Dive & Architectural Strategy
"Verify all .md files and glossary formulas in detail. Map out the exact definitions and detection criteria for the 6 problem classes, conflicts, and cannot_determine. Outline how disk persistence works between batch processes."

### 3. Implementation & Testing
"Execute the implementation modularly across parsing, repricing, auditing, feedback, and gating. Test against the official grader using make grade and make sheet. Ensure all 5 hard gates are clear and that the exam answer sheet matches the key."

### 4. Custom Evaluation Suite
"Create a regression test suite under evals/cases/ covering edge cases such as prompt injection defense, one-off waiver boundaries, 3-letter invoice prefixes in AP registers, and pickup date period transitions. Verify with make eval."

### 5. Final Compliance & Validation
"Run make validate across the entire repository to confirm that all schema requirements, word limits, citation lookups, and report card checks pass with 100% compliance."
