"""CLI integration tests for src.rin.cli.main.

All tests patch filesystem, stdin/stdout, and normalize_markdown so that the
logic in *cli.py* can be exercised without touching disk or invoking the full
pipeline.
"""

from __future__ import annotations

import asyncio
import builtins
import sys
from types import SimpleNamespace
from pathlib import Path

import pytest

import src.rin.cli as cli
from src.rin.config import RinConfig


# ---------------------------------------------------------------------------
# Fixtures & helpers
# ---------------------------------------------------------------------------

def _dummy_report() -> object:
    """Return an object that passes through ``dataclasses.asdict`` after patch."""

    class DummyReport(SimpleNamespace):
        status: str = "ok"

    return DummyReport()


def _patch_normalize(monkeypatch, output: str = "CLEANED_MD"):
    """Patch ``cli.normalize_markdown`` to return deterministic output."""

    async def _fake_normalize(md: str, cfg: RinConfig):  # noqa: D401
        return output, _dummy_report()

    monkeypatch.setattr(cli, "normalize_markdown", _fake_normalize)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_stdin_to_stdout(monkeypatch, capsys):
    """No args → read from STDIN, write to STDOUT."""

    # Fake stdin content
    monkeypatch.setattr(sys, "stdin", SimpleNamespace(read=lambda: "RAW_MD"))

    # Patch normalize_markdown
    _patch_normalize(monkeypatch, output="CLEAN")

    # Also stub asdict so JSON path doesn’t choke
    monkeypatch.setattr(cli, "asdict", lambda rep: {"dummy": True})

    # Run
    asyncio.run(cli.main([]))

    captured = capsys.readouterr()
    assert captured.out == "CLEAN"  # stdout
    assert captured.err == ""  # no stderr


def test_file_input_file_output(monkeypatch):
    """Reads from input path and writes to output path."""

    input_path = Path("input.md")
    output_path = Path("output.md")

    # Patch Path.read_text and write_text selectively
    def fake_read_text(self, encoding="utf-8"):
        assert self == input_path  # right file
        return "RAW_MD"

    writes: dict[str, str] = {}

    def fake_write_text(self, data: str, encoding="utf-8"):
        assert self == output_path
        writes["data"] = data
        return None

    monkeypatch.setattr(Path, "read_text", fake_read_text)
    monkeypatch.setattr(Path, "write_text", fake_write_text)

    # Patch normalize_markdown
    _patch_normalize(monkeypatch, output="CLEAN")
    monkeypatch.setattr(cli, "asdict", lambda rep: {"dummy": True})

    asyncio.run(cli.main([str(input_path), "-o", str(output_path)]))

    assert writes["data"] == "CLEAN"


def test_input_missing_exits(monkeypatch, capsys):
    """Missing input file triggers exit 1."""

    input_path = Path("missing.md")

    def fake_read_text(self, encoding="utf-8"):
        raise FileNotFoundError()

    monkeypatch.setattr(Path, "read_text", fake_read_text)

    with pytest.raises(SystemExit) as exc:
        asyncio.run(cli.main([str(input_path)]))

    assert exc.value.code == 1
    err = capsys.readouterr().err
    assert "input file not found" in err.lower()


def test_config_load(monkeypatch):
    """Valid TOML config overrides defaults while reading from mocked STDIN."""

    toml_path = Path("cfg.toml")
    toml_text = """
max_tokens = 1234
temperature = 0.7
"""

    # TOML file contents
    monkeypatch.setattr(Path, "read_text", lambda self, encoding="utf-8": toml_text)

    # Provide dummy STDIN
    monkeypatch.setattr(sys, "stdin", SimpleNamespace(read=lambda: "RAW"))

    # Capture the config used by normalize_markdown
    cfg_holder: dict[str, RinConfig] = {}

    async def _fake_normalize(md: str, cfg: RinConfig):
        cfg_holder["cfg"] = cfg
        return "clean", _dummy_report()

    monkeypatch.setattr(cli, "normalize_markdown", _fake_normalize)
    monkeypatch.setattr(cli, "asdict", lambda rep: {"dummy": True})

    asyncio.run(cli.main(["--config", str(toml_path)]))

    cfg = cfg_holder["cfg"]
    assert cfg.max_tokens == 1234
    assert cfg.temperature == 0.7


def test_json_report(monkeypatch, capsys):
    """--json prints JSON representation of report to stderr."""

    # stdin
    monkeypatch.setattr(sys, "stdin", SimpleNamespace(read=lambda: "RAW"))

    _patch_normalize(monkeypatch, output="CLEAN")

    # Patch asdict to predictable dict
    monkeypatch.setattr(cli, "asdict", lambda rep: {"foo": 42})

    asyncio.run(cli.main(["--json"]))

    captured = capsys.readouterr()
    assert captured.out == "CLEAN"
    assert "{\n  \"foo\"" in captured.err  # pretty JSON


def test_output_write_error(monkeypatch, capsys):
    """Write exceptions surface as exit 1."""

    input_path = Path("input.md")
    output_path = Path("out.md")

    monkeypatch.setattr(Path, "read_text", lambda self, encoding="utf-8": "RAW")

    def fake_write_text(self, data: str, encoding="utf-8"):
        raise IOError("disk full")

    monkeypatch.setattr(Path, "write_text", fake_write_text)
    _patch_normalize(monkeypatch, output="CLEAN")
    monkeypatch.setattr(cli, "asdict", lambda rep: {"dummy": True})

    with pytest.raises(SystemExit) as exc:
        asyncio.run(cli.main([str(input_path), "-o", str(output_path)]))

    assert exc.value.code == 1
    err = capsys.readouterr().err
    assert "cannot write output" in err.lower()
