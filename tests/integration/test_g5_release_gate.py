"""G5-R1-001 — the release secret gate must pass on the candidate itself.

The unit fixtures exercise the scanner's helper functions; this integration
assertion runs the REAL release gate over the exact Git-tracked tree. The full
suite therefore fails if the scanner ever matches its own repository text (the
self-match that made candidate `6a6d309` fail the gate) or if the documented
CLI stops exiting 0.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from tools.release_audit import scan_secrets

REPO = Path(__file__).resolve().parents[2]


def test_tracked_repository_secret_scan_is_clean(capsys) -> None:
    hits, placeholders = scan_secrets.scan_tracked()
    assert hits == [], (
        "the release gate must not match tracked repository text:\n"
        + scan_secrets.format_hits(hits)
    )
    code = scan_secrets.main()
    out = capsys.readouterr().out
    assert code == 0, out
    assert "SECRET_SCAN: 0 secret hits" in out
    assert "FAIL[" not in out
    # The reported informational count must match what was actually emitted.
    assert out.count("info:") == len(placeholders)


def test_secret_scan_cli_exits_zero_on_the_candidate() -> None:
    """The documented command must exit 0 on the tracked tree (G5-R1-001)."""
    proc = subprocess.run(
        [sys.executable, "tools/release_audit/scan_secrets.py"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "SECRET_SCAN: 0 secret hits" in proc.stdout
    # Redaction contract: no matched value is ever printed.
    assert "FAIL[" not in proc.stdout
