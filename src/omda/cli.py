"""G4 T4.5 — default dry-run and explicit delivery approval gate (OPH §14-8).

The CLI defaults to a DRY-RUN: the run writes a local Markdown file and never
calls an external service (no token resolution, no HTTP transport is even
constructed). External push (PushPlus) is allowed only with an explicit
``--deliver`` flag (or an explicit configuration flag in programmatic use).
Explicit ``--dry-run`` always wins over ``--deliver``: it is a safety gate.
"""

from __future__ import annotations

import argparse
import enum
from pathlib import Path

DEFAULT_OUTPUT_DIR = Path("var/output")
DEFAULT_TOKEN_ENV = "PUSHPLUS_TOKEN"


class DeliveryMode(enum.Enum):
    """The effective external-delivery decision of a run."""

    DRY_RUN = "dry-run"
    DELIVER = "deliver"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments; external push is OFF unless ``--deliver``."""
    parser = argparse.ArgumentParser(prog="omda", description="OMDA daily music discovery")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="write a local Markdown report without any external push (default safety gate)",
    )
    parser.add_argument(
        "--deliver",
        action="store_true",
        default=False,
        help="allow an external PushPlus push for this run (explicit approval required)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="directory for the dry-run Markdown report",
    )
    parser.add_argument(
        "--token-env",
        default=DEFAULT_TOKEN_ENV,
        help="environment variable that holds the PushPlus token (never logged)",
    )
    parser.add_argument("--run-id", default=None, help="optional run id (default: generated)")
    return parser.parse_args(argv)


def select_delivery(args: argparse.Namespace) -> DeliveryMode:
    """Decide the delivery mode: explicit ``--dry-run`` wins; else only an
    explicit ``--deliver`` unlocks external push."""
    if args.dry_run:
        return DeliveryMode.DRY_RUN
    if args.deliver:
        return DeliveryMode.DELIVER
    return DeliveryMode.DRY_RUN  # default: dry-run, no external side effects


__all__ = [
    "DEFAULT_OUTPUT_DIR",
    "DEFAULT_TOKEN_ENV",
    "DeliveryMode",
    "parse_args",
    "select_delivery",
]
