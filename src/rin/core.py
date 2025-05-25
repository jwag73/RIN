"""rin.core
=========

High-level orchestration for the *RIN* (Re-Indent & Normalise) processing
pipeline.

The entry-point is :func:`normalize_markdown` which consumes raw markdown,
passes it through the *formatter* utilities, interacts with the language
models, validates the result and returns cleaned markdown plus a
:class:`~rin.report.ValidationReport` capturing metrics & diagnostics.

Each run writes its :class:`ValidationReport` to **logs/<run_id>.json** so that
batch telemetry can be analysed offline.
"""
from __future__ import annotations

import asyncio
import json
import sys
import time
from dataclasses import asdict
from pathlib import Path
from typing import Dict, List, Tuple

from .config import RinConfig
from .report import ValidationReport
from . import validators
from .model_client import ModelClient, ModelCommand
from .formatter import (
    FencedBlock,
    Token as FormatterToken,
    segregate_pre_fenced_blocks,
    tokenize_unfenced_text,
    reconstruct_markdown,
)

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _build_fenced_token_stream(
    original_pm_tokens: List[FormatterToken],
    model_commands: List[ModelCommand],
) -> List[FormatterToken]:
    """Inject new fence tokens into the stream according to *model_commands*."""
    commands_by_token: Dict[str, List[ModelCommand]] = {}
    for cmd in model_commands:
        commands_by_token.setdefault(cmd["token_id"], []).append(cmd)

    next_negative_id = -1
    result: List[FormatterToken] = []
    for tok in original_pm_tokens:
        str_id = f"{tok.id:05d}"
        for cmd in commands_by_token.get(str_id, []):
            if cmd["command"] == "INSERT_FENCE_START":
                lang = cmd.get("lang", "")
                text = f"\n```{lang}\n" if lang else "\n```\n"
                result.append(FormatterToken(next_negative_id, text))
                next_negative_id -= 1
            elif cmd["command"] == "INSERT_FENCE_END":
                result.append(FormatterToken(next_negative_id, "\n```\n"))
                next_negative_id -= 1
        result.append(tok)
    return result


aSYNC_LINT_LANGS_DEFAULT = {"python"}

async def _run_gate_g1_checks(
    markdown: str,
    config: RinConfig,
    report: ValidationReport,
) -> Tuple[bool, List[str]]:
    extracted = validators.extract_code_blocks(markdown)
    report.fenced_blocks_in_output = len(extracted)

    errors: List[str] = []
    lint_langs = getattr(config, "lint_languages", aSYNC_LINT_LANGS_DEFAULT)
    for idx, (code, lang) in enumerate(extracted, 1):
        if lang and lang.lower() in lint_langs:
            report.identified_python_blocks += 1
            ast_ok = validators.ast_check_ok(code)
            lint_ok, lint_msg = validators.run_pylint_check(code, timeout_seconds=10)
            if ast_ok and lint_ok:
                report.passed_linting_python_blocks += 1
            else:
                errors.append(
                    f"Block {idx}: AST={'OK' if ast_ok else 'FAIL'}; "
                    f"Lint={'OK' if lint_ok else 'FAIL'}. {lint_msg}"
                )
    return len(errors) == 0, errors


def _save_report_to_json(report: ValidationReport, log_dir: str = "logs") -> None:
    """Serialise *report* to a pretty JSON file under *log_dir*."""
    try:
        Path(log_dir).mkdir(parents=True, exist_ok=True)
        filename = f"{report.run_id}.json"
        path = Path(log_dir) / filename
        path.write_text(json.dumps(asdict(report), indent=2), encoding="utf-8")
    except Exception as exc:  # pragma: no cover – logging must never break pipeline
        print(
            f"Warning: failed to save JSON report {filename}: {exc}",
            file=sys.stderr,
        )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def normalize_markdown(
    raw_markdown_text: str,
    config: RinConfig,
) -> Tuple[str, ValidationReport]:
    """Normalise *raw_markdown_text* according to the RIN pipeline."""
    report = ValidationReport()
    start_ts = time.perf_counter()

    current_md = raw_markdown_text  # In case of early catastrophic error.
    try:
        # ---------------- Stage 0: Segregate existing fences -------------
        text_with_placeholders, original_blocks = segregate_pre_fenced_blocks(
            current_md
        )
        report.fenced_blocks_in_input = len(original_blocks)

        # ---------------- Stage 1: Tokenise ------------------------------
        pm_tokens = tokenize_unfenced_text(text_with_placeholders)
        model_tokens = [(f"{t.id:05d}", t.text) for t in pm_tokens]

        # ---------------- Stage 2: Model interaction --------------------
        errors_g1: List[str] = []
        async with ModelClient(config) as client:
            shot0_commands = await client.request_shot0(model_tokens)
            report.shot0_model_used = config.shot0_model
            pm_tokens_with_fences = _build_fenced_token_stream(pm_tokens, shot0_commands)
            current_md = reconstruct_markdown(pm_tokens_with_fences, original_blocks)
            report.fence_parity_ok_initial = validators.fence_parity_ok(current_md)

            # ---------- G0 fallback -------------------------------------
            if not report.fence_parity_ok_initial:
                report.fallback_to_big_model_used = True
                big_commands = await client.request_big_model(model_tokens)
                report.big_model_used = config.big_model
                pm_tokens_with_fences = _build_fenced_token_stream(pm_tokens, big_commands)
                current_md = reconstruct_markdown(pm_tokens_with_fences, original_blocks)
                report.fence_parity_ok_after_fallback = validators.fence_parity_ok(
                    current_md
                )
                if not report.fence_parity_ok_after_fallback:
                    report.errors.append(
                        "Fence parity invalid after Big-Model fallback."
                    )
                    report.final_status_message = "G0 failed – unmatched fences."
                    return current_md, report

            # ---------- G1 lint / AST -----------------------------------
            g1_ok, errors_g1 = await _run_gate_g1_checks(current_md, config, report)

            if not g1_ok:
                report.self_fix_attempted = True
                prev_cmds = (
                    big_commands if report.fallback_to_big_model_used else shot0_commands
                )
                error_ctx = "\n".join(errors_g1)[:2048]
                shot1_cmds = await client.request_shot1(
                    model_tokens, prev_cmds, error_ctx
                )
                report.shot1_model_used = config.shot1_model
                pm_tokens_with_fences = _build_fenced_token_stream(pm_tokens, shot1_cmds)
                current_md = reconstruct_markdown(pm_tokens_with_fences, original_blocks)
                report.fence_parity_ok_after_fix = validators.fence_parity_ok(current_md)
                if not report.fence_parity_ok_after_fix:
                    report.errors.append("Fence parity invalid after Shot-1.")
                    report.final_status_message = "G0 failed post-fix."
                    return current_md, report
                g1_ok, errors_g1 = await _run_gate_g1_checks(current_md, config, report)
                if not g1_ok:
                    report.errors.extend(errors_g1)
                    report.final_status_message = "G1 failed after Shot-1."
                    return current_md, report

        # ---------------- Success --------------------------------------
        report.final_status_message = "Success. All gates passed."
    except Exception as exc:  # pragma: no cover – catch-all telemetry
        report.errors.append(f"Critical error: {exc}")
        report.final_status_message = "Critical error during processing."
    finally:
        report.output_char_length = len(current_md)
        report.elapsed_ms = (time.perf_counter() - start_ts) * 1000
        _save_report_to_json(report)

    return current_md, report


# ---------------------------------------------------------------------------
# Optional test harness
# ---------------------------------------------------------------------------

if __name__ == "__main__":  # pragma: no cover
    async def _main():  # type: ignore[misc]
        from .config import RinConfig  # local for smoke-test

        cfg = RinConfig(shot0_model="gpt-3.5-turbo", shot1_model="gpt-3.5-turbo", big_model="gpt-4o-mini")
        sample = "Here is code without a fence:\n\nprint('hi')\n"
        cleaned, rep = await normalize_markdown(sample, cfg)
        print(cleaned)
        print(json.dumps(asdict(rep), indent=2))

    asyncio.run(_main())
