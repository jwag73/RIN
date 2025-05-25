"""Tests for src.rin.config.RinConfig.

These cover:
- Default instantiation values
- .as_dict() correctness and mutability
- Overridden constructor values
"""

import pytest

from src.rin.config import RinConfig


@pytest.mark.parametrize(
    "field, expected",
    [
        ("model_name", "gpt-4.1-nano"),
        ("max_tokens", 6000),
        ("temperature", 0.2),
        ("top_p", 1.0),
        ("stop_sequences", ["\n```", "\n\n"]),
        ("linter_map", {"python": "validate_python_code"}),
        ("api_timeout", 15.0),
        ("self_fix_timeout", 3.0),
        ("fence_parity_required", True),
        ("run_linter_gate", True),
        ("shot0_model", "gpt-4.1-nano"),
        ("shot1_model", "gpt-4.1-nano"),
        ("big_model", "gpt-4.1"),
    ],
)
def test_rin_config_defaults(field, expected):
    """Ensure default instantiation sets every attribute to the expected value."""
    cfg = RinConfig()
    assert getattr(cfg, field) == expected


def test_rin_config_as_dict():
    """`as_dict` returns a fresh dict mirroring the current state."""
    cfg = RinConfig()
    d = cfg.as_dict()

    # Correct type and key coverage
    assert isinstance(d, dict)
    assert set(d.keys()) == set(cfg.__dict__.keys())

    # Equality of values
    for k, v in cfg.__dict__.items():
        assert d[k] == v

    # Mutability check – change attr, dict should change on next call
    cfg.max_tokens = 1234
    assert cfg.as_dict()["max_tokens"] == 1234


def test_rin_config_overridden_values():
    """Custom constructor arguments override defaults while leaving others intact."""
    cfg = RinConfig(max_tokens=500, model_name="test_model")

    assert cfg.max_tokens == 500
    assert cfg.model_name == "test_model"

    # Spot‑check an unrelated default to ensure it remains untouched
    assert cfg.temperature == 0.2
