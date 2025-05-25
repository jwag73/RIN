"""rin.cli
========

Command-line interface for the *RIN* normalisation pipeline.

Example::

    $ python -m rin.cli article.md -o article_clean.md --json 

If *article.md* is omitted RIN will read markdown from **STDIN** and write the
cleaned result to **STDOUT**.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import asdict, fields
from pathlib import Path
from typing import Any, Dict

import tomlkit

from .config import RinConfig
from .core import normalize_markdown
from .report import ValidationReport

__all__ = ["main"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_config_from_toml(path: Path) -> RinConfig:
    """Return a :class:`RinConfig` initialised from *path* (TOML)."""
    cfg = RinConfig()  # type: ignore[call-arg] – project may have defaults
    toml_data = tomlkit.parse(path.read_text(encoding="utf-8"))  # type: ignore[arg-type]

    # Only apply keys that actually exist on RinConfig to avoid surprises.
    valid_fields = {f.name for f in fields(cfg)}
    for key, val in toml_data.items():
        if key in valid_fields:
            setattr(cfg, key, val)
    return cfg


# ---------------------------------------------------------------------------
# Async entry-point
# ---------------------------------------------------------------------------

async def main(argv: list[str] | None = None) -> None:  # noqa: D401 – imperative mood
    """Parse *argv* and run the RIN pipeline.

    When *argv* is **None** ``sys.argv[1:]`` is used.
    """
    parser = argparse.ArgumentParser(prog="rin", description="RIN Markdown normaliser")

    parser.add_argument(
        "input",
        nargs="?",
        help="Path to input markdown file. Reads from STDIN when omitted.",
    )
    parser.add_argument(
        "-o",
        "--output",
        help="Path for cleaned markdown. Writes to STDOUT when omitted.",
    )
    parser.add_argument(
        "--config",
        metavar="TOML",
        help="Path to configuration TOML. Uses built-in defaults when omitted.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit ValidationReport as JSON to STDERR.",
    )

    args = parser.parse_args(argv)

    # ------------------------------------------------------------------
    # Read input markdown ------------------------------------------------
    # ------------------------------------------------------------------
    try:
        if args.input:
            raw_md = Path(args.input).read_text(encoding="utf-8")
        else:
            raw_md = sys.stdin.read()
    except FileNotFoundError:
        print(f"rin: input file not found: {args.input}", file=sys.stderr)
        sys.exit(1)
    except Exception as exc:
        print(f"rin: error reading input – {exc}", file=sys.stderr)
        sys.exit(1)

    # ------------------------------------------------------------------
    # Load configuration -------------------------------------------------
    # ------------------------------------------------------------------
    try:
        if args.config:
            cfg = _load_config_from_toml(Path(args.config))
        else:
            cfg = RinConfig()  # type: ignore[call-arg]
    except Exception as exc:
        print(f"rin: failed to load config – {exc}", file=sys.stderr)
        sys.exit(1)

    # ------------------------------------------------------------------
    # Run normalisation --------------------------------------------------
    # ------------------------------------------------------------------
    try:
        cleaned_md, report = await normalize_markdown(raw_md, cfg)
    except Exception as exc:  # pragma: no cover – surface unexpected issues
        print(f"rin: processing error – {exc}", file=sys.stderr)
        sys.exit(1)

    # ------------------------------------------------------------------
    # Write outputs ------------------------------------------------------
    # ------------------------------------------------------------------
    try:
        if args.output:
            Path(args.output).write_text(cleaned_md, encoding="utf-8")
        else:
            print(cleaned_md, end="")
    except Exception as exc:
        print(f"rin: cannot write output – {exc}", file=sys.stderr)
        sys.exit(1)

    # ------------------------------------------------------------------
    # Optional JSON report ----------------------------------------------
    # ------------------------------------------------------------------
    if args.json:
        try:
            json_report: Dict[str, Any] = asdict(report)  # type: ignore[arg-type]
            print(json.dumps(json_report, indent=2), file=sys.stderr)
        except Exception as exc:
            print(f"rin: failed to serialise report – {exc}", file=sys.stderr)
            # Not fatal for exit code.


# ---------------------------------------------------------------------------
# Module entry-point
# ---------------------------------------------------------------------------

if __name__ == "__main__":  # pragma: no cover – manual invocation only
    asyncio.run(main())
