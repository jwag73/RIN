"""Unit‑tests for *rin.core.normalize_markdown*.

These tests monkey‑patch nearly every external dependency so that we can drive
*normalize_markdown* through its high‑level control‑flow branches without
invoking the heavy formatter, validator, or model‑client logic.

A minimal stub implementation strategy is used:
* **Formatter** utils return trivial values.
* **ModelClient** is replaced with an in‑memory async stub.
* **Validators** are patched to deterministic lambdas whose behaviour is
  parameterised per‑test.
* **Report saving** is suppressed to avoid filesystem writes.

The focus is exhaustive branch coverage – we validate that
``ValidationReport`` fields reflect each scenario.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any, List

import pytest

import rin.core as core

# ---------------------------------------------------------------------------
# Shared stubs & helpers
# ---------------------------------------------------------------------------

class DummyClient:  # Minimal async context‑manager replacement for ModelClient
    def __init__(self, *_: Any, **__: Any):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False  # propagate exceptions if any (none expected)

    #   The three request methods just echo an empty list – the core logic only
    #   cares that *some* iterable is returned.
    async def request_shot0(self, tokens):  # noqa: D401 – test stub
        return []

    async def request_big_model(self, tokens):  # noqa: D401 – test stub
        return []

    async def request_shot1(self, tokens, prev_cmds, error_ctx):  # noqa: D401 – test stub
        return []


# Formatter patchers – always return trivially transformed data so that the
# markdown value is predictable and unimportant for the tests.

def _patch_formatter(monkeypatch):
    monkeypatch.setattr(core, "segregate_pre_fenced_blocks", lambda md: (md, []))

    class _Tok(SimpleNamespace):  # Tiny object with `id` and `text` attributes
        def __init__(self, text: str):
            super().__init__(id=0, text=text)

    monkeypatch.setattr(core, "tokenize_unfenced_text", lambda txt: [_Tok(txt)])
    monkeypatch.setattr(core, "_build_fenced_token_stream", lambda toks, cmds: toks)
    monkeypatch.setattr(core, "reconstruct_markdown", lambda toks, blocks: "CLEANED")


# General config object – only the three *model* attributes are used by core.
_CFG = SimpleNamespace(shot0_model="s0", big_model="big", shot1_model="s1")


async def _run_pipeline(monkeypatch, *, parity_seq: List[bool], g1_seq: List[tuple]):
    """Execute *normalize_markdown* with patched deps.

    Parameters
    ----------
    parity_seq
        Sequential booleans returned by ``validators.fence_parity_ok``.
    g1_seq
        Sequential ``(ok: bool, errors: list[str])`` tuples returned by
        ``_run_gate_g1_checks``.
    """

    # --- Patch formatter & IO helpers --------------------------------
    _patch_formatter(monkeypatch)
    monkeypatch.setattr(core, "_save_report_to_json", lambda rep, log_dir="logs": None)

    # --- Patch ModelClient ------------------------------------------
    monkeypatch.setattr(core, "ModelClient", DummyClient)

    # --- Sequential parity stub -------------------------------------
    call_idx = {"i": 0}

    def _fake_parity(md: str):  # noqa: D401 – test stub
        i = call_idx["i"]
        call_idx["i"] += 1
        return parity_seq[min(i, len(parity_seq) - 1)]

    monkeypatch.setattr(core.validators, "fence_parity_ok", _fake_parity)

    # --- Sequential G1 stub -----------------------------------------
    g1_idx = {"i": 0}

    async def _fake_g1(md: str, cfg, rep):  # noqa: D401 – async stub
        i = g1_idx["i"]
        g1_idx["i"] += 1
        ok, errs = g1_seq[min(i, len(g1_seq) - 1)]
        return ok, list(errs)

    monkeypatch.setattr(core, "_run_gate_g1_checks", _fake_g1)

    # ----------------------------------------------------------------
    cleaned, report = await core.normalize_markdown("RAW", _CFG)
    return cleaned, report


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_success_path(monkeypatch):
    """All gates pass on first attempt."""

    _, report = await _run_pipeline(monkeypatch, parity_seq=[True], g1_seq=[(True, [])])

    assert report.final_status_message == "Success. All gates passed."
    assert report.shot0_model_used == "s0"
    assert not report.fallback_to_big_model_used
    assert not report.self_fix_attempted
    assert report.fence_parity_ok_initial


@pytest.mark.asyncio
async def test_g0_fallback_success(monkeypatch):
    """Initial parity fails → Big‑model fixes it; G1 passes."""

    _, report = await _run_pipeline(
        monkeypatch,
        parity_seq=[False, True],  # fail, then fixed by big model
        g1_seq=[(True, [])],
    )

    assert report.final_status_message == "Success. All gates passed."
    assert report.fallback_to_big_model_used
    assert report.big_model_used == "big"
    assert report.fence_parity_ok_initial is False
    assert report.fence_parity_ok_after_fallback is True


@pytest.mark.asyncio
async def test_g0_fallback_still_fails(monkeypatch):
    """Big‑model cannot repair parity → pipeline aborts."""

    _, report = await _run_pipeline(
        monkeypatch,
        parity_seq=[False, False],  # still broken
        g1_seq=[(True, [])],  # ignored
    )

    assert report.final_status_message == "G0 failed – unmatched fences."
    assert report.fence_parity_ok_after_fallback is False
    # Ensure we exited before attempting self‑fix
    assert not report.self_fix_attempted


@pytest.mark.asyncio
async def test_shot1_fix_success(monkeypatch):
    """G1 initially fails; Shot‑1 repairs both parity & lint."""

    _, report = await _run_pipeline(
        monkeypatch,
        parity_seq=[True, True],  # initial OK, still OK after fix
        g1_seq=[(False, ["lint err"]), (True, [])],  # fail then pass
    )

    assert report.self_fix_attempted
    assert report.shot1_model_used == "s1"
    assert report.final_status_message == "Success. All gates passed."
    assert report.fence_parity_ok_after_fix is True


@pytest.mark.asyncio
async def test_shot1_parity_breaks(monkeypatch):
    """Shot‑1 introduces parity error → abort with G0 post‑fix message."""

    _, report = await _run_pipeline(
        monkeypatch,
        parity_seq=[True, False],  # parity breaks after shot‑1
        g1_seq=[(False, ["lint err"]), (True, [])],
    )

    assert report.final_status_message == "G0 failed post-fix."
    assert report.self_fix_attempted
    assert report.fence_parity_ok_after_fix is False


@pytest.mark.asyncio
async def test_shot1_g1_still_fails(monkeypatch):
    """Shot‑1 keeps parity but G1 still fails → abort with G1 message."""

    _, report = await _run_pipeline(
        monkeypatch,
        parity_seq=[True, True],
        g1_seq=[(False, ["lint err"]), (False, ["still bad"])],
    )

    assert report.final_status_message == "G1 failed after Shot-1."
    assert report.self_fix_attempted
    assert report.errors[-1].startswith("still bad") or "lint" in "\n".join(report.errors)
