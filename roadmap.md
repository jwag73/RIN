Markdown

# Robust Input Normalizer (RIN) - Project Roadmap

## 0. Introduction & Guiding Principles

This document outlines the single-purpose, end-to-end roadmap for the Robust Input Normalizer (“RIN”) utility.

**Core Principles:**
* ✅ **Self-contained:** RIN will be developed as an independent module, initially residing in its own `rin/` directory.
* ✅ **Non-Intrusive:** It will not modify or directly depend on existing Code_Sling core logic (Reasoning/Parser/Injector code-paths) during its initial development and testing.
* ✅ **Portable:** The design aims for RIN to be easily integrable into any future pipeline once its effectiveness is proven.

**Out of Scope for MVP (Initial Version):**
* Advanced security considerations such as HTML escaping within markdown or preventing malicious code execution (RIN only manipulates text; execution is out of its scope).
* Streaming support for very large files (MVP targets typical chat transcript sizes).

## 1. Scope & Success Criteria

| Dimension            | MVP Target                                                                                                 |
| :------------------- | :--------------------------------------------------------------------------------------------------------- |
| Languages Supported  | ✅ Python only (accurate tag + pylint pass). Design is language-agnostic so new linters & tags plug in via config. |
| Accuracy             | Infrastructure built to measure; actual metric TBD with real model.                                        |
| Cost Ceiling         | Infrastructure built to estimate (if token counts available); actual metric TBD with real model.             |
| Runtime              | Infrastructure built to measure (`elapsed_ms` in report); actual metric TBD with real model and optimizations. |
| Interfaces           | ✅ CLI, ✅ Python API, and a thin pytest harness for regression. (pytest harness is pending full testing phase) |
| Isolation            | ✅ No import from Code_Sling core; lives under `rin/`. ✅ Zero global state.                |
| Telemetry            | ✅ JSON log per run (`rin/logs/yyyymmdd-HHMMSS.json`).                                      |

## 2. Architecture at a Glance

The RIN utility follows a sequential processing flow with validation gates and fallback mechanisms:

```mermaid
flowchart LR
    subgraph RIN
      A[Segregate pre-fenced blocks] --> B[Tokenise Unfenced Text + Enumerate Tokens]
      B --> C[Shot-0 Mini-Model: Generate INSERT_FENCE commands]
      C --> D[Reconstruct Markdown with new fences]
      D --> E[Gate G0: Fence Parity Check (Regex)]
      E --fail--> FallbackBig[Fallback: Call Big Model once] --> D
      E --pass--> F[Gate G1: Lint + AST Checks (e.g., pylint for Python)]
      F --fail--> Fixer[Shot-1 Mini-Model: Self-fix prompt with error context] --> D
      F --pass--> Out[Output: Clean, Tagged Markdown + ValidationReport JSON]
    end
✅ Key Flow Notes reflect the implemented logic in core.py.
Only G1 (Lint/AST check) failure triggers the self-fix (Shot-1) mini-model.
The big-model fallback (FallbackBig) is invoked if Shot-0 (initial fencing) fails the Gate G0 (fence-parity check).
If Gate G1 (Lint/AST check) fails after a self-fix attempt via Shot-1 (Fixer), this results in a hard error, as per the decision in Section 9. No further fallback is attempted from this state in the MVP.

3. File / Package Layout
The RIN utility will be organized within its own directory structure:

rin/
├── ✅ __init__.py          # Makes rin a package, exports public API
├── ✅ formatter.py         # Handles segregation, tokenization, and reconstruction logic (PM's implementation used)
├── ✅ model_client.py      # Thin asynchronous wrapper for mini-model and big-model API calls (implemented with mocks and prompt logic)
├── ✅ validators.py        # Implements fence parity check, markdown-it AST walker, pylint runner, etc. (implemented)
├── ✅ config.py            # Dataclass for configuration (model names, timeouts, language-to-linter map) (PM's implementation used)
├── ✅ cli.py               # Entry point for the command-line interface (e.g., python -m rin input.md > output.md) (implemented)
├── tests/                  # Structure exists, test_formatter.py was pre-existing.
│   ├── __init__.py
│   ├── fixtures/        # Structure exists
│   │   └── (example_input.md, expected_output.md, etc.)
│   └── test_formatter.py  # Unit tests for formatter.py (and others like test_validators.py, etc.) (pre-existing, more tests pending)
└── ✅ logs/                # Directory for storing telemetry JSON logs from each run (created by core.py if needed)
└── (yyyymmdd-HHMMSS.json, etc.)

(Note: We also created report.py for ValidationReport and core.py for normalize_markdown orchestration, which are logical implementations of the public API and processing flow).

4. Public APIs
RIN will expose a primary Python function for programmatic use and return a detailed validation report.

✅ Main Function: (Implemented and exposed via rin.__init__.py)

Python

from rin import normalize_markdown, ValidationReport, RinConfig
# ... example usage ...
✅ Validation Report Dataclass: (Implemented in rin.report.py with enhancements)

Python

from dataclasses import dataclass

@dataclass
class ValidationReport:
    run_id: str 
    input_char_length: int
    output_char_length: int
    fenced_blocks_in_input: int
    fenced_blocks_in_output: int
    identified_python_blocks: int 
    passed_linting_python_blocks: int 
    fence_parity_ok: bool # Note: Our report has more granular fence_parity fields
    shot0_model_used: str
    shot1_model_used: str | None
    big_model_used: str | None
    self_fix_attempted: bool
    fallback_to_big_model_used: bool 
    elapsed_ms: int # Note: Our report uses float for more precision
    cost_estimate_usd: float | None
    errors: list[str]
5. Core Algorithms
✅ 5.1 Segregation of Pre-Fenced Blocks (Implemented in formatter.py, used by core.py)
✅ 5.2 Tokenization of Unfenced Text (Implemented in formatter.py, used by core.py with ID adaptation)
✅ 5.3 Mini-Model Prompt (Shot-0 - Initial Fencing) (Implemented in model_client.py)
✅ 5.4 Reconstruction (Implemented in core.py using _build_fenced_token_stream helper and formatter.reconstruct_markdown)
✅ 5.5 Validators (Gate G0 & Gate G1) (Implemented in validators.py, orchestrated by core.py)
* ✅ Gate G0: Fence Parity Check
* ✅ Gate G1: Linting and AST Checks (for Python)
* ✅ run_pylint_check (Implemented)
* ✅ ast_check_ok (Implemented)
✅ 5.6 Self-Fix Prompt (Shot-1 - Linter/AST Failure) (Implemented in model_client.py, orchestrated by core.py)

6. Testing Strategy
(This section is largely future work, beyond initial setup and basic tests from PM)

Unit Tests: pytest -q Tokenizer, reconstructor logic, fence parity check, individual validator functions. (Some exist, more needed)
Golden File: pytest + fixture files End-to-end normalize_markdown function: diff of raw input vs. expected clean output for various scenarios in tests/fixtures/. (To be implemented)
Fuzzy Tests: Hypothesis (Python lib) Test normalize_markdown with randomly generated markdown-like input to ensure robustness. Target: ≥ 99% fence parity over 1,000 diverse cases. (To be implemented)
Integration: Manual CLI / API Test with problematic real-world chat transcripts. Ensure pylint returns 0 for Python blocks. (To be implemented)
CI Badge: The project's main README.md in the RIN repository should include a CI status badge (e.g., from GitHub Actions) once CI is set up. (To be implemented)
7. Incremental Delivery Timeline (Estimated)
✅ Week 0.5 (Sprint 1 Part 1):
✅ Setup project structure, __init__.py, basic config.py. (Largely pre-existing/confirmed)
✅ Implement formatter.py: segregate_pre_fenced_blocks and reconstruct_markdown (basic). (PM's work, integrated)
✅ Implement validators.py: fence_parity_ok. (PM's work, integrated and built upon)
Basic unit tests. (Partially pre-existing)
✅ Week 1 (Sprint 1 Part 2):
✅ Implement model_client.py (mocked, detailed prompts).
✅ Implement formatter.py: tokenize_unfenced_text. (PM's work, integrated)
✅ Integrate Shot-0 loop (mocked). (Done in core.py)
Unit tests for tokenizer, initial golden-file tests. (Pending)
✅ Week 1.5 (Sprint 2 Part 1):
✅ Integrate actual mini-model API calls in model_client.py. (Structure for async calls done; actual calls are currently mocked by design for this phase but can be swapped).
✅ Refine Shot-0 prompt. (Done in model_client.py)
✅ Implement validators.py: Python block extraction, pylint_ok (as run_pylint_check), ast_check_ok (Gate G1).
Fuzzy Tests: Start implementing Hypothesis fuzzy tests for tokenizer and reconstructor stability. (Pending)
✅ Week 2 (Sprint 2 Part 2):
✅ Implement Shot-1 self-fix logic (prompt, model call integration). (Done in model_client.py and core.py)
✅ Implement big-model fallback path for G0 failure. (Done in model_client.py and core.py)
✅ Week 2.5 (Sprint 3 Part 1):
✅ Develop cli.py wrapper.
✅ Implement JSON logging for ValidationReport.
Write basic documentation (README.md for RIN). (Pending)
Expand test coverage (more golden files, mature Hypothesis tests). (Pending)
Week 3 (Sprint 3 Part 2): (Pending)
Integration into Code_Sling: Via flag-gated call.
End-to-end testing within Code_Sling.
Final review and polish.
8. Extensibility Hooks
✅ rin.config.RinConfig.lint_languages: Add new languages/linters. (Used in core.py)
rin.formatter.TOKEN_RE: Replaceable tokenization strategy. (Defined in formatter.py; replaceable by modifying the module)
✅ rin.model_client.py: Pluggable backends (OpenAI, Claude, local models). (Designed for this; currently mocked)
✅ CLI Enhancements:
✅ --json flag for ValidationReport output.
✅ --config path/to/rin.toml: Allow CLI users to specify a TOML configuration file.
Concurrency for Linters: As noted in 5.5, linters for multiple blocks can be run concurrently for performance. (Not implemented yet)
9. Open Questions & Default Decisions
✅ Time-out for pylint per block?
Default: 10 seconds (configurable). (Used 10s default in validators.py, configurability via RinConfig is future if desired)
✅ Hard failure threshold – if self_fix_attempted still fails pylint?
Default: Hard error (raise an exception). (Implemented as early exit with error in report in core.py)