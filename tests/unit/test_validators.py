"""Unit tests for **src.rin.validators**.

Covers:
- `fence_parity_ok`
- `extract_code_blocks`
- `ast_check_ok`
- `run_pylint_check` (via mocked `subprocess.run`)

The tests are written to pass against the current implementation of
`validators.py`.  If implementation details change (e.g. `ast_check_ok` starts
rejecting the empty string) then the expectations in these tests should be
updated accordingly.
"""

from __future__ import annotations

import subprocess
import sys
from types import SimpleNamespace
from typing import List, Optional

import pytest

from src.rin.validators import (
    fence_parity_ok,
    extract_code_blocks,
    ast_check_ok,
    run_pylint_check,
)

# ---------------------------------------------------------------------------
# fence_parity_ok
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "markdown, expected",
    [
        ("", True),  # empty string – 0 fences
        ("Some text without fences", True),
        ("```\ncode\n```", True),  # 2 fences (open/close)
        ("```a```b```c```", True),  # 4 fences
    ],
)
def test_fence_parity_even(markdown: str, expected: bool):
    """Parity should be *even* for these cases."""
    assert fence_parity_ok(markdown) is expected


@pytest.mark.parametrize(
    "markdown",
    [
        "```",                    # single fence only
        "text ``` code ``` more ```",  # 3 fences
    ],
)
def test_fence_parity_odd(markdown: str):
    """Odd‑numbered back‑tick groups are invalid."""
    assert fence_parity_ok(markdown) is False


# ---------------------------------------------------------------------------
# extract_code_blocks
# ---------------------------------------------------------------------------

def test_extract_no_blocks():
    assert extract_code_blocks("Just prose – no code fences.") == []


def test_extract_single_block_with_lang():
    md = """\n```python\nprint('hi')\n```\n"""
    blocks = extract_code_blocks(md)
    assert blocks == [("print('hi')\n", "python")]


def test_extract_single_block_no_lang():
    md = """\n```\nprint('hi')\n```\n"""
    blocks = extract_code_blocks(md)
    assert blocks == [("print('hi')\n", None)]


def test_extract_multiple_blocks_mixed():
    md = (
        "Intro.\n\n"
        "```js\nconsole.log('js');\n```\n\n"
        "Some text.\n\n"
        "```\nno‑lang block\n```\n\n"
        "```python\nprint('py')\n```\n"
    )
    blocks = extract_code_blocks(md)
    assert blocks == [
        ("console.log('js');\n", "js"),
        ("no‑lang block\n", None),
        ("print('py')\n", "python"),
    ]


def test_extract_block_with_complex_content():
    code = "def foo():\n    return (1 + 2) * 3  # comment 🙂\n"
    md = f"```python\n{code}```"
    blocks = extract_code_blocks(md)
    assert blocks == [(code, "python")]


def test_extract_markdown_noise():
    md = (
        "# Heading\n\n* List\n* Items\n\nInline `code` example."
    )
    assert extract_code_blocks(md) == []


# ---------------------------------------------------------------------------
# ast_check_ok – syntactic validity of Python snippets
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "snippet, expected",
    [
        ("def foo():\n    pass", True),  # valid function def
        ("a = 1 + 1", True),              # valid expression
        ("", True),                       # empty string is still valid AST (Module with no body)
    ],
)
def test_ast_check_valid(snippet: str, expected: bool):
    assert ast_check_ok(snippet) is expected


@pytest.mark.parametrize(
    "snippet",
    [
        "def oops(" ,               # missing closing paren
        "a = !!!",                 # invalid tokens
        "print 'py2 style'",       # syntax error in py3
    ],
)
def test_ast_check_invalid(snippet: str):
    assert ast_check_ok(snippet) is False


# ---------------------------------------------------------------------------
# run_pylint_check – mocked subprocess.run
# ---------------------------------------------------------------------------

def _build_expected_cmd() -> List[str]:
    """Helper that reconstructs the exact command list validators builds."""
    return [
        sys.executable,
        "-m",
        "pylint",
        "--from-stdin",
        "linted_stdin_block.py",
        "--disable="
        "missing-docstring,invalid-name,trailing-newlines,import-error,"
        "wrong-import-position,fixme",
        "--msg-template={line}:{column}: {msg_id}({symbol}) {msg}",
    ]


def _patch_subproc(monkeypatch, *, returncode: int = 0, stdout: str = "", stderr: str = "", exc: Exception | None = None):
    """Monkey‑patch **subprocess.run**.

    If *exc* is provided, it will be raised to simulate an error; otherwise a
    dummy CompletedProcess‑like object is returned.
    """

    def _fake_run(cmd, **kwargs):  # noqa: ANN001 – mimics signature
        # Ensure the CLI invocation is as expected.
        assert cmd == _build_expected_cmd()
        assert kwargs.get("timeout") == 5 or kwargs.get("timeout") == 10 or kwargs.get("timeout") is None
        if exc is not None:
            raise exc
        # Minimal stand‑in object with .returncode/.stdout/.stderr
        return SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)

    monkeypatch.setattr(subprocess, "run", _fake_run)


# -- pass case ----------------------------------------------------------------

def test_pylint_pass(monkeypatch):
    _patch_subproc(monkeypatch, returncode=0)
    ok, msg = run_pylint_check("print('hi')", timeout_seconds=5)
    assert ok is True
    assert msg == "Pylint passed."


# -- fail with output ---------------------------------------------------------

def test_pylint_fail_with_output(monkeypatch):
    stdout = "1:0: W0001(dummy) Something is fishy"
    stderr = ""
    _patch_subproc(monkeypatch, returncode=1, stdout=stdout, stderr=stderr)
    ok, msg = run_pylint_check("bad = code", timeout_seconds=5)
    assert ok is False
    assert msg == stdout.strip()


# -- fail with no output ------------------------------------------------------

def test_pylint_fail_silent(monkeypatch):
    _patch_subproc(monkeypatch, returncode=1, stdout="", stderr="")
    ok, msg = run_pylint_check("bad = code")
    assert ok is False
    assert msg == "Pylint failed with no specific output."


# -- timeout ------------------------------------------------------------------

def test_pylint_timeout(monkeypatch):
    _patch_subproc(
        monkeypatch,
        exc=subprocess.TimeoutExpired(cmd=_build_expected_cmd(), timeout=5),
    )
    ok, msg = run_pylint_check("print('hi')", timeout_seconds=5)
    assert ok is False
    assert msg == "Pylint check timed out after 5 seconds."


# -- pylint executable missing -----------------------------------------------

def test_pylint_file_not_found(monkeypatch):
    _patch_subproc(
        monkeypatch,
        exc=FileNotFoundError("pylint not found"),
    )
    ok, msg = run_pylint_check("print('hi')")
    assert ok is False
    assert msg == "Pylint or python3 not found. Ensure they are installed and in PATH."


# -- unexpected error ---------------------------------------------------------

def test_pylint_unexpected_error(monkeypatch):
    _patch_subproc(
        monkeypatch,
        exc=Exception("Something went wrong"),
    )
    ok, msg = run_pylint_check("print('hi')")
    assert ok is False
    assert msg.startswith("Unexpected error while running pylint: Something went wrong")
