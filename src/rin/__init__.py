"""Robust Input Normalizer (RIN) package."""

from .config import RinConfig
from .report import ValidationReport
from .core import normalize_markdown # Ensure this was added in the previous step

__all__ = [
    "RinConfig",
    "normalize_markdown",
    "ValidationReport"
]
