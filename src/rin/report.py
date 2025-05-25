"""rin.report
============

Data‑objects produced by the validation / normalisation pipeline.

Currently only :class:`ValidationReport` is defined.  It captures metrics and
status flags collected while processing a single markdown document.
"""
from __future__ import annotations

import datetime
import uuid
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class ValidationReport:
    """Report detailing the outcome of the RIN normalisation process."""

    # ---------------------------------------------------------------------
    # Meta / accounting
    # ---------------------------------------------------------------------
    run_id: str = field(
        default_factory=lambda: f"{datetime.datetime.utcnow().strftime('%Y%m%d-%H%M%S-%f')}-{uuid.uuid4().hex[:8]}"
    )
    elapsed_ms: float = 0.0
    cost_estimate_usd: Optional[float] = None

    # ---------------------------------------------------------------------
    # Size metrics
    # ---------------------------------------------------------------------
    input_char_length: int = 0
    output_char_length: int = 0

    # ---------------------------------------------------------------------
    # Fenced‑block counters
    # ---------------------------------------------------------------------
    fenced_blocks_in_input: int = 0
    fenced_blocks_in_output: int = 0
    identified_python_blocks: int = 0
    passed_linting_python_blocks: int = 0

    # ---------------------------------------------------------------------
    # Fence‑parity checkpoints
    # ---------------------------------------------------------------------
    fence_parity_ok_initial: Optional[bool] = None  # After Shot‑0 or first pass
    fence_parity_ok_after_fallback: Optional[bool] = (
        None  # After Big‑Model fallback (G0 path)
    )
    fence_parity_ok_after_fix: Optional[bool] = None  # After Shot‑1 self‑fix

    # ---------------------------------------------------------------------
    # Model usage / control‑flow flags
    # ---------------------------------------------------------------------
    shot0_model_used: Optional[str] = None
    shot1_model_used: Optional[str] = None
    big_model_used: Optional[str] = None

    self_fix_attempted: bool = False
    fallback_to_big_model_used: bool = False  # Specifically for G0 → Big‑Model

    # ---------------------------------------------------------------------
    # Outcome / error reporting
    # ---------------------------------------------------------------------
    errors: List[str] = field(default_factory=list)
    final_status_message: str = "Processing not yet complete."


__all__ = ["ValidationReport"]
