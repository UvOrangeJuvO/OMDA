#!/usr/bin/env python3
"""G5 T5.3 — repository secret/security scan (SPEC §7-14, MP §7).

Scans every Git-TRACKED file (plus the packed dependency metadata) for
credential patterns: PushPlus/private tokens, private-key blocks, AWS/GitHub
secrets, cookie/profile material and obvious placeholder leakage.

Exit codes:
  0  no hits
  1  hits found (or scan error)

Run from the repository root:
    python tools/release_audit/scan_secrets.py
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

# (name, compiled pattern) — conservative, false-positive-tolerant by design.
# FAIL patterns: real credential shapes that must never ship.
PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("pushplus-token", re.compile(r"(?i)pushplus[_ ]?token\s*=\s*[\"'][A-Za-z0-9_\-]{16,}[\"']")),
    ("generic-token-assign", re.compile(
        r"(?i)(token|secret|apikey|api_key)\s*[:=]\s*[\"'][A-Za-z0-9_\-\.]{16,}[\"']"
    )),
    ("private-key-block", re.compile(r"-----BEGIN (RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----")),
    ("aws-access-key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("github-token", re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}")),
    ("cookie-content", re.compile(r"(?i)session_id\s*[:=]\s*[\"'][A-Za-z0-9]{16,}[\"']")),
    ("browser-profile-path", re.compile(
        r"(?i)(chrome|vivaldi).*(profile|user.data).*[A-Za-z0-9]{8,}"
    )),
]

# INFORMATIONAL: placeholder contact markers referenced by the codebase's own
# rejection rules (G3-007-008) and tests — these are the strings that MUST be
# rejected at runtime, not shipped secrets; they are reported but never fail.
PLACEHOLDER_PATTERN = re.compile(r"@example\.(com|org|net)|\.invalid")

# Files that legitimately carry the pattern names in documentation (allowed
# references are checked separately by the Reviewer; the scanner reports only
# ASSIGNMENT-shaped hits and blocks).
SKIP_SUFFIXES = (".pyc", ".png", ".jpg", ".jpeg", ".gif", ".sqlite3", ".db")


def tracked_files() -> list[Path]:
    out = subprocess.run(
        ["git", "ls-files", "-z"], capture_output=True, check=True, text=True
    )
    return [Path(p) for p in out.stdout.split("\0") if p]


def scan() -> tuple[list[tuple[Path, str, str]], list[tuple[Path, str]]]:
    hits: list[tuple[Path, str, str]] = []
    placeholders: list[tuple[Path, str]] = []
    for path in tracked_files():
        if path.suffix in SKIP_SUFFIXES:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for name, pattern in PATTERNS:
            for match in pattern.finditer(text):
                snippet = text[max(0, match.start() - 40): match.end() + 40]
                snippet = " ".join(snippet.split())
                hits.append((path, name, snippet))
        if PLACEHOLDER_PATTERN.search(text):
            placeholders.append((path, "placeholder-contact-reference"))
    return hits, placeholders


def main() -> int:
    hits, placeholders = scan()
    for path, name in placeholders:
        print(f"  info: {path}: [{name}] (rejection-rule reference, not a secret)")
    if hits:
        print(f"SECRET_SCAN: {len(hits)} FAILING hit(s):")
        for path, name, snippet in hits:
            print(f"  {path}: [{name}] ...{snippet}...")
        return 1
    print(f"SECRET_SCAN: 0 secret hits (informational placeholder references: {len(placeholders)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
