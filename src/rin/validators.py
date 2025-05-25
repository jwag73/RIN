"""rin.validators
================

Utility helpers that validate markdown documents and the code blocks they
contain.  Functions are *pure* so they can be unit‑tested without I/O or
side‑effects (with the notable exception of :func:`run_pylint_check`, which
spawns a subprocess).

This module integrates Jules' richer implementation:

* Fenced‑code extraction via **markdown‑it‑py** rather than a fragile regex.
* AST validity and **pylint** quality checks for Python snippets.
* A lightweight *fence‑parity* helper that ensures markdown documents have a
  balanced number of triple‑backtick fences.

All public helpers are synchronous and return plain data so that higher‑level
async layers can call them freely without an event‑loop context.
"""
from __future__ import annotations

import ast
import subprocess
from typing import List, Tuple, Optional

from markdown_it import MarkdownIt

__all__ = [
    "extract_code_blocks",
    "run_pylint_check",
    "ast_check_ok",
    "fence_parity_ok",
]

# ---------------------------------------------------------------------------
# Code‑block handling
# ---------------------------------------------------------------------------

def extract_code_blocks(markdown_text: str) -> List[Tuple[str, Optional[str]]]:
    """Return the fenced code blocks found in *markdown_text*.

    Unlike a naive regex, this uses **markdown‑it‑py**'s CommonMark parser which
    handles nested structures, indentation quirks, and escaped back‑ticks.

    Parameters
    ----------
    markdown_text:
        A UTF‑8 string containing Markdown.

    Returns
    -------
    List[Tuple[str, Optional[str]]]
        ``code_content`` and the optional *language tag* (``None`` when no tag
        was provided).  The order matches the appearance in the document.
    """
    md = MarkdownIt()
    tokens = md.parse(markdown_text)

    code_blocks: List[Tuple[str, Optional[str]]] = []
    for tok in tokens:
        if tok.type == "fence":
            lang_tag: Optional[str] = tok.info.strip() if tok.info else None
            code_blocks.append((tok.content, lang_tag))
    return code_blocks


# ---------------------------------------------------------------------------
# Python‑specific checks
# ---------------------------------------------------------------------------

def run_pylint_check(code_block: str, timeout_seconds: int = 10) -> Tuple[bool, str]:
    """Run *pylint* on *code_block*.

    The snippet is piped to *pylint* via STDIN so no temporary file is written.

    Parameters
    ----------
    code_block:
        Raw Python source to be analysed.
    timeout_seconds:
        Abort the child process after this amount of seconds (default **10**).

    Returns
    -------
    Tuple[bool, str]
        ``True`` if *pylint* exited with status *0* ("everything OK"); the
        accompanying message is either "Pylint passed." or the linter output / an
        explanatory error string.
    """
    try:
        proc = subprocess.run(
            [
                "python3",
                "-m",
                "pylint",
                # Disable some warnings that are noisy in short snippets.
                "--disable="
                "missing-docstring,invalid-name,trailing-newlines,import-error,"
                "wrong-import-position,fixme",
                # Custom concise msg format to keep output on one line each.
                "--msg-template={line}:{column}: {msg_id}({symbol}) {msg}",
                "-",  # read code from STDIN
            ],
            input=code_block,
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
        )
        if proc.returncode == 0:
            return True, "Pylint passed."
        output = (proc.stdout.strip() + "\n" + proc.stderr.strip()).strip()
        return False, output or "Pylint failed with no specific output."
    except subprocess.TimeoutExpired:
        return False, f"Pylint check timed out after {timeout_seconds} seconds."
    except FileNotFoundError:
        return False, "Pylint or python3 not found. Ensure they are installed and in PATH."
    except Exception as exc:  # pragma: no cover ‑‑ guard unforeseen issues
        return False, f"Unexpected error while running pylint: {exc}"


def ast_check_ok(code_block: str) -> bool:
    """Return *True* if *code_block* compiles to a valid Python AST.

    The helper merely wraps :pyfunc:`ast.parse` and catches any exception,
    including :class:`SyntaxError`.  This is useful to quickly gate obviously
    broken snippets before invoking heavier tools like *pylint*.
    """
    try:
        ast.parse(code_block, mode="exec")
        return True
    except Exception:  # pragma: no cover – we deliberately swallow all errors
        return False


# ---------------------------------------------------------------------------
# Generic markdown helpers
# ---------------------------------------------------------------------------

def fence_parity_ok(markdown_text: str) -> bool:
    """Return *True* if the document has a balanced number of triple‑backticks.

    The check is intentionally simple –*just count* – because the heavier
    markdown parser already handles complex nuances.  Nevertheless, catching
    mismatched fences early avoids confusing downstream behaviour.
    """
    return markdown_text.count("```") % 2 == 0


# ---------------------------------------------------------------------------
# Stand‑alone smoke‑test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    SAMPLE_MD = (
        "This is some markdown.\n\n"
        "```python\nprint('hello world')\n```\n\n"
        "Regular text.\n\n"
        "```\nplain fenced block\n```\n"
    )

    print("Fence parity OK:", fence_parity_ok(SAMPLE_MD))

    blocks = extract_code_blocks(SAMPLE_MD)
    print("Extracted", len(blocks), "code blocks:")
    for idx, (code, lang) in enumerate(blocks, 1):
        print(f"  {idx}. lang={lang!r}, {len(code.splitlines())} lines")
        print(code)
        if lang == "python":
            print("    AST OK:", ast_check_ok(code))
            success, message = run_pylint_check(code)
            print("    Pylint:", "pass" if success else "fail")
            if not success:
                print("       ", message)
