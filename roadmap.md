

Markdown

# Robust Input Normalizer (RIN) - Project Roadmap

## 0. Introduction & Guiding Principles

This document outlines the single-purpose, end-to-end roadmap for the Robust Input Normalizer (“RIN”) utility.

**Core Principles:**
* **Self-contained:** RIN will be developed as an independent module, initially residing in its own `rin/` directory.
* **Non-Intrusive:** It will not modify or directly depend on existing Code_Sling core logic (Reasoning/Parser/Injector code-paths) during its initial development and testing.
* **Portable:** The design aims for RIN to be easily integrable into any future pipeline once its effectiveness is proven.

**Out of Scope for MVP (Initial Version):**
* Advanced security considerations such as HTML escaping within markdown or preventing malicious code execution (RIN only manipulates text; execution is out of its scope).
* Streaming support for very large files (MVP targets typical chat transcript sizes).

## 1. Scope & Success Criteria

| Dimension            | MVP Target                                                                                                 |
| :------------------- | :--------------------------------------------------------------------------------------------------------- |
| Languages Supported  | Python only (accurate tag + pylint pass). Design is language-agnostic so new linters & tags plug in via config. |
| Accuracy             | ≥ 99% of code blocks in a messy chat are fenced with the correct language tag after one mini-model pass.     |
| Cost Ceiling         | ≤ 3¢ per 4k-token chat (mini-model price-point).                                                           |
| Runtime              | ≤ 500ms for a 6k-token transcript on a 4-core laptop (this target initially applies to core processing; linting of multiple/large blocks might require optimization like caching/parallelization or be considered separately if slow). |
| Interfaces           | CLI, Python API, and a thin pytest harness for regression.                                                 |
| Isolation            | No import from Code_Sling core; lives under `rin/`. Zero global state.                                     |
| Telemetry            | JSON log per run (`rin/logs/yyyymmdd-HHMMSS.json`).                                                          |

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
Key Flow Notes:

Only G1 (Lint/AST check) failure triggers the self-fix (Shot-1) mini-model.
The big-model fallback (FallbackBig) is invoked if Shot-0 (initial fencing) fails the Gate G0 (fence-parity check).
If Gate G1 (Lint/AST check) fails after a self-fix attempt via Shot-1 (Fixer), this results in a hard error, as per the decision in Section 9. No further fallback is attempted from this state in the MVP.
3. File / Package Layout
The RIN utility will be organized within its own directory structure:

rin/
├── __init__.py          # Makes `rin` a package, exports public API
├── formatter.py         # Handles segregation, tokenization, and reconstruction logic
├── model_client.py      # Thin asynchronous wrapper for mini-model and big-model API calls
├── validators.py        # Implements fence parity check, markdown-it AST walker, pylint runner, etc.
├── config.py            # Dataclass for configuration (model names, timeouts, language-to-linter map)
├── cli.py               # Entry point for the command-line interface (e.g., `python -m rin input.md > output.md`)
├── tests/
│   ├── __init__.py
│   ├── fixtures/        # Contains test input/output files for golden-file testing
│   │   └── (example_input.md, expected_output.md, etc.)
│   └── test_formatter.py  # Unit tests for formatter.py (and others like test_validators.py, etc.)
└── logs/                # Directory for storing telemetry JSON logs from each run
    └── (yyyymmdd-HHMMSS.json, etc.)
4. Public APIs
RIN will expose a primary Python function for programmatic use and return a detailed validation report.

Main Function:
Python

from rin import normalize_markdown, ValidationReport, RinConfig

# Example usage:
raw_markdown_text = """
Some text...
```python
print("hello")
More text
def example():
pass
And a final block

Bash

echo "done"
"""

config = RinConfig(
shot0_model="gpt-4o-mini",  # Or other suitable mini-model
shot1_model="gpt-4o-mini",  # For self-correction
big_model="gpt-4o",         # Fallback model
lint_languages={"python": "pylint"}, # Language to linter command mapping
# other config options like timeouts can be added here
)

try:
clean_md, report = normalize_markdown(raw_markdown_text, config=config)
print("Cleaned Markdown:\n", clean_md)
print("\nValidation Report:\n", report)
except Exception as e:
print(f"An error occurred: {e}")


### Validation Report Dataclass:

The `ValidationReport` (returned by `normalize_markdown` and also logged to a JSON file) will contain metadata about the normalization process:

```python
from dataclasses import dataclass

@dataclass
class ValidationReport:
    run_id: str # Unique identifier for the run, e.g., yyyymmdd-HHMMSS-micros
    input_char_length: int
    output_char_length: int
    fenced_blocks_in_input: int
    fenced_blocks_in_output: int
    identified_python_blocks: int # Total Python blocks found by RIN
    passed_linting_python_blocks: int # Number of identified Python blocks that passed linting
    # failed_linting_python_blocks: int could be derived or added if needed
    fence_parity_ok: bool
    shot0_model_used: str
    shot1_model_used: str | None
    big_model_used: str | None
    self_fix_attempted: bool
    fallback_to_big_model_used: bool # Specifically for fallback from G0 failure
    elapsed_ms: int
    # Cost estimate requires the model client to expose prompt/response token counts; else leave None.
    cost_estimate_usd: float | None
    errors: list[str] # List of any critical errors encountered during processing
5. Core Algorithms
5.1 Segregation of Pre-Fenced Blocks
Objective: Identify and temporarily isolate code blocks that are already correctly fenced in the input markdown.
Method:
Use a regex pattern compatible with GitHub Flavored Markdown (GFM) to find code fences.
Example Multiline Regex (requires re.DOTALL or re.S flag in Python): ^\s{0,3}(?:>+\s*)?```(\w+)?\s*[\r\n](.*?[\r\n])```\s*[\r\n]?$
Simpler Start/End Fence Regex (likely initial implementation): ^\s{0,3}(?:>+\s*)?```(\w+)?\s*$
For each found block:
Store its content, language tag (if any), and original position.
Replace the block in the main text with a unique sentinel string (e.g., ⟦F_BLOCK_0⟧).
Note on Sentinel Collision: Ensure sentinels are unique and don't collide with existing text. Consider using UUID-based sentinels or an escaping mechanism if ⟦F_BLOCK_n⟧ patterns could naturally occur.
The remaining text (with sentinels) is passed to the tokenization stage.
5.2 Tokenization of Unfenced Text
Objective: Break down the non-fenced portions of the input text into a sequence of tokens with their original indices.
Method:
Define a regular expression for tokenization.
Python

import re
TOKEN_RE = re.compile(r'(\r\n|\r|\n)|([ \t]+)|([\w-]+)|([^\w\s])')
Apply TOKEN_RE.findall() or an equivalent iterative match to the unfenced text.
Enumerate tokens: Assign a unique, ordered ID to each token for the mini-model prompt (e.g., [00000]text_token).
5.3 Mini-Model Prompt (Shot-0 - Initial Fencing)
Objective: Instruct a small, fast language model to identify potential code blocks in the tokenized text and output commands to insert fences.

Prompt Structure:

System Prompt:

Plaintext

You are MarkdownFenceBot v1, an AI assistant specialized in identifying code blocks within a stream of text tokens and inserting appropriate language-specific fences. Your goal is to accurately demarcate code snippets.

Output ONLY a list of commands based on the rules below. Do not provide explanations or conversational text.
User Prompt:

Plaintext

TEXT (numbered tokens from input):
[00000]Some
[00001]text
[00002]...
[00003]def
[00004]my_function
[00005](
[00006]):
[00007]\n
[00008]  
[00009]  
[00010]print
[00011](
[00012]"hello"
[00013])
[00014]\n
[00015]More
[00016]text
[00017]...

OUTPUT RULES:
- To insert a fence start: INSERT_FENCE_START <token_id> <language_tag>
  (This command inserts a start fence *before* the token with ID <token_id>.)
- To insert a fence end: INSERT_FENCE_END <token_id>
  (This command inserts an end fence *before* the token with ID <token_id>.)

Supported language_tags: python, json, bash, javascript, typescript, java, csharp, cpp, go, rust, php, ruby, sql, html, css, text.
If unsure about the language, use 'text'.
Ensure every INSERT_FENCE_START has a corresponding INSERT_FENCE_END.
Return only one command per line.
5.4 Reconstruction
Objective: Rebuild the markdown document based on the mini-model's fencing commands and reinsert the original pre-fenced blocks.
Method:
Initialize an empty list for the new markdown content.
Iterate through the original numbered tokens.
If a token ID matches an INSERT_FENCE_START <id> <lang> command from the model, append \n```<lang>\n to the content.
If a token ID matches an INSERT_FENCE_END <id> command, append \n```\n to the content.
Append the current token's text.
After processing all tokens, replace the sentinel strings (e.g., ⟦F_BLOCK_i⟧) with their original, corresponding pre-fenced code blocks.
5.5 Validators (Gate G0 & Gate G1)
Gate G0: Fence Parity Check

Objective: Ensure an even number of triple-backtick fence markers.
Method:
Python

def fence_parity_ok(markdown_text: str) -> bool:
    return markdown_text.count("```") % 2 == 0
Gate G1: Linting and AST Checks (per language)

Objective: Validate syntax and style for identified code blocks.
Method (Example for Python):
Extract code blocks for the target language (e.g., Python) from the reconstructed markdown using a markdown parser like markdown-it-py.
For each Python code block:
Run pylint (or flake8, or Python's ast.parse()).
Note on Performance: For multiple blocks, consider running linters concurrently (e.g., using concurrent.futures.ThreadPoolExecutor) to optimize wall-clock time. <!-- end list -->
Python

import subprocess
import ast

def run_pylint_check(code_block: str, timeout_seconds: int = 10) -> tuple[bool, str]:
    # (Implementation as previously defined)
    try:
        process = subprocess.run(
            ["pylint", "-", "--msg-template='{line}:{column}: {msg_id}({symbol}), {obj} {msg}'", "--load-plugins="],
            input=code_block, text=True, capture_output=True, timeout=timeout_seconds, check=False
        )
        if process.returncode == 0: return True, "Pylint passed."
        else: return False, (process.stdout.strip() + "\n" + process.stderr.strip()).strip()
    except subprocess.TimeoutExpired: return False, "Pylint check timed out."
    except FileNotFoundError: return False, "Pylint command not found."
    except Exception as e: return False, f"Error running pylint: {e}"


def ast_check_ok(code_block: str) -> bool:
    try: ast.parse(code_block); return True
    except SyntaxError: return False
5.6 Self-Fix Prompt (Shot-1 - Linter/AST Failure)
Objective: If Gate G1 fails, attempt to get the mini-model to correct its previous fencing commands.

Prompt Structure: (As previously defined, ensuring error message is clear)

System Prompt:

Plaintext

You are MarkdownFenceBot v1. Your previous attempt to insert fences resulted in code that failed validation.
Review the original text, your previous (failed) commands, and the error message.
Provide a COMPLETE, NEW list of `INSERT_FENCE_START` and `INSERT_FENCE_END` commands that will fix the error and correctly fence all code blocks.
Return only one command per line.
User Prompt: (Structure with original tokens, previous commands, and error message)

6. Testing Strategy
Layer	Tool / Method	Coverage Target
Unit Tests	pytest -q	Tokenizer, reconstructor logic, fence parity check, individual validator functions.
Golden File	pytest + fixture files	End-to-end normalize_markdown function: diff of raw input vs. expected clean output for various scenarios in tests/fixtures/.
Fuzzy Tests	Hypothesis (Python lib)	Test normalize_markdown with randomly generated markdown-like input to ensure robustness. Target: ≥ 99% fence parity over 1,000 diverse cases.
Integration	Manual CLI / API	Test with problematic real-world chat transcripts. Ensure pylint returns 0 for Python blocks.

Export to Sheets
CI Badge: The project's main README.md in the RIN repository should include a CI status badge (e.g., from GitHub Actions) once CI is set up.
7. Incremental Delivery Timeline (Estimated)
Week 0.5 (Sprint 1 Part 1):

Setup project structure, __init__.py, basic config.py.
Implement formatter.py: segregate_pre_fenced_blocks and reconstruct_markdown (basic).
Implement validators.py: fence_parity_ok.
Basic unit tests.
Week 1 (Sprint 1 Part 2):

Implement model_client.py (mocked).
Implement formatter.py: tokenize_unfenced_text.
Integrate Shot-0 loop (mocked).
Unit tests for tokenizer, initial golden-file tests.
Week 1.5 (Sprint 2 Part 1):

Integrate actual mini-model API calls in model_client.py.
Refine Shot-0 prompt.
Implement validators.py: Python block extraction, pylint_ok, ast_check_ok (Gate G1).
Fuzzy Tests: Start implementing Hypothesis fuzzy tests for tokenizer and reconstructor stability.
Week 2 (Sprint 2 Part 2):

Implement Shot-1 self-fix logic (prompt, model call integration).
Implement big-model fallback path for G0 failure.
Week 2.5 (Sprint 3 Part 1):

Develop cli.py wrapper.
Implement JSON logging for ValidationReport.
Write basic documentation (README.md for RIN).
Expand test coverage (more golden files, mature Hypothesis tests).
Week 3 (Sprint 3 Part 2):

Integration into Code_Sling: Via flag-gated call.
End-to-end testing within Code_Sling.
Final review and polish.
8. Extensibility Hooks
rin.config.RinConfig.lint_languages: Add new languages/linters.
rin.formatter.TOKEN_RE: Replaceable tokenization strategy.
rin.model_client.py: Pluggable backends (OpenAI, Claude, local models).
CLI Enhancements:
--json flag for ValidationReport output.
--config path/to/rin.toml: Allow CLI users to specify a TOML configuration file.
Concurrency for Linters: As noted in 5.5, linters for multiple blocks can be run concurrently for performance.
9. Open Questions & Default Decisions
Time-out for pylint per block?

Default: 10 seconds (configurable).
Hard failure threshold – if self_fix_attempted still fails pylint?

Default: Hard error (raise an exception).
<!-- end list -->