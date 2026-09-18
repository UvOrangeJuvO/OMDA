#!/usr/bin/env python3
"""G5 T5.3 — repository secret/security scan (SPEC §7-14, MP §7) — hardened.

Two independent layers:

1. TRACKED-PATH POLICY — forbidden artifact classes that must never be tracked
   even if empty: cookie jars, browser profiles, runtime databases, .env /
   credential files, private keys, netrc, password managers. A file matching
   the path denylist fails the scan WITHOUT reading its contents.

2. CONTENT POLICY — robust credential patterns scanned over TEXT files only.
   Binary files (detected via NUL bytes) are never text-decoded, so a binary
   store can never produce garbage matches; binary artifact classes are
   already caught by the path denylist.

Output is REDACTED: only the kind, path and line are printed — the matched
secret value is NEVER emitted (G5-004), so the scanner can run in CI/review
logs without copying credentials into the log.

Exit codes:
  0  no failing hits
  1  failing hits (or scan error)

Run from the repository root:
    python tools/release_audit/scan_secrets.py
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

# ---------------------------------------------------------------------------
# Layer 1: tracked-path denylist (forbidden artifact classes)
# ---------------------------------------------------------------------------

# (name, compiled pattern) matched against the POSIX-style relative path.
TRACKED_FORBIDDEN_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("dotenv", re.compile(r"(^|/)\.env(\.[A-Za-z0-9_]+)?$")),
    # G5-R1-001: cookie artifacts come in many shapes — `cookies.json`,
    # `cookies.txt`, bare browser `Cookies` (no extension), `cookie_store.txt`,
    # `cookiejar`, `cookie-jar.txt`. Any path whose basename is a cookie-store
    # name is refused, extension or not (conservative by design: a release gate
    # must never ship cookie material).
    ("cookie-jar", re.compile(
        r"(^|/)(cookie|cookies|cookiejar|cookie[-_]?store|cookie[-_]?jar)[^/]*$",
        re.IGNORECASE,
    )),
    ("browser-profile", re.compile(r"(^|/)browser-profile(/|$)", re.IGNORECASE)),
    ("runtime-db", re.compile(
        r"\.(sqlite|sqlite3|db|sqlite3-journal|db-wal|db-shm)$", re.IGNORECASE
    )),
    ("private-key", re.compile(r"\.(pem|key|p12|pfx|jks|keystore|asc)$", re.IGNORECASE)),
    ("ssh-key", re.compile(r"(^|/)(id_rsa|id_dsa|id_ecdsa|id_ed25519)(\.pub)?$")),
    ("netrc", re.compile(r"(^|/)\.netrc$")),
    ("credential-file", re.compile(
        r"(^|/)credentials?[^/]*\.(json|txt|ini|conf)$", re.IGNORECASE
    )),
    ("service-account", re.compile(
        r"(^|/)(service-account|service_account|client_secret|secret)"
        r"[^/]*\.json$",
        re.IGNORECASE,
    )),
]

# ---------------------------------------------------------------------------
# Layer 2: content credential patterns (TEXT files only)
# ---------------------------------------------------------------------------

TOKEN_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("pushplus-token", re.compile(r"(?i)pushplus[_ ]?token\s*=\s*[\"'][A-Za-z0-9_\-]{16,}[\"']")),
    ("generic-token-assign", re.compile(
        r"(?i)\b(token|secret|api[_-]?key|apikey|access[_-]?key)\s*[:=]\s*[\"'][A-Za-z0-9_\-\.]{16,}[\"']"
    )),
    ("private-key-block", re.compile(
        r"-----BEGIN (RSA |EC |OPENSSH |DSA |ENCRYPTED )?PRIVATE KEY-----"
    )),
    ("aws-access-key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("github-token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b")),
    ("bearer-token", re.compile(r"(?i)\bauthorization\s*[:=]\s*bearer\s+[A-Za-z0-9._~+/=-]{20,}")),
    ("basic-auth", re.compile(r"(?i)\bauthorization\s*[:=]\s*basic\s+[A-Za-z0-9+/]{20,}={0,2}")),
    ("slack-token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")),
    ("google-api-key", re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b")),
    ("stripe-key", re.compile(r"\b(?:sk|rk)_(?:live|test)_[0-9a-zA-Z]{20,}\b")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b")),
    ("cookie-content", re.compile(r"(?i)\bsession[_-]?id\s*[:=]\s*[\"'][A-Za-z0-9]{16,}[\"']")),
]

# INFORMATIONAL: placeholder contact markers referenced by the codebase's own
# rejection rules and tests — these are the strings that MUST be rejected at
# runtime, not shipped secrets; they are reported but never fail.
PLACEHOLDER_PATTERN = re.compile(r"@example\.(com|org|net)|\.invalid")

_BINARY_PROBE = b"\x00"


@dataclass(frozen=True)
class Hit:
    """One redacted scan hit — the secret value is NEVER stored."""

    kind: str  # "forbidden-path" | "token"
    path: Path
    detail: str
    line: int | None = None


def _is_binary(path: Path) -> bool:
    """Cheap binary probe: a NUL byte in the first 1024 bytes means the file is
    not text and must not be text-decoded."""
    try:
        with path.open("rb") as handle:
            return _BINARY_PROBE in handle.read(1024)
    except OSError:
        return True


def scan_paths(paths: list[Path]) -> tuple[list[Hit], list[tuple[Path, str]]]:
    """Scan explicit paths: path-denylist first, then text content patterns."""
    hits: list[Hit] = []
    placeholders: list[tuple[Path, str]] = []
    for path in paths:
        rel = path.as_posix()
        for name, pattern in TRACKED_FORBIDDEN_PATTERNS:
            if pattern.search(rel):
                hits.append(
                    Hit(kind="forbidden-path", path=path, detail=name)
                )
                # A forbidden artifact class fails on the path alone; its
                # content (possibly binary) is never decoded.
                break
        else:
            if path.is_file() and _is_binary(path):
                continue  # binary non-forbidden file: content scan skipped
            try:
                lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                continue
            for line_no, line in enumerate(lines, start=1):
                for name, pattern in TOKEN_PATTERNS:
                    if pattern.search(line):
                        hits.append(
                            Hit(kind="token", path=path, detail=name, line=line_no)
                        )
            if PLACEHOLDER_PATTERN.search("\n".join(lines)):
                placeholders.append((path, "placeholder-contact-reference"))
    return hits, placeholders


def tracked_files() -> list[Path]:
    """Every Git-TRACKED path (including force-added forbidden artifacts)."""
    out = subprocess.run(
        ["git", "ls-files", "-z"], capture_output=True, check=True, text=True
    )
    return [Path(p) for p in out.stdout.split("\0") if p]


def scan_tracked() -> tuple[list[Hit], list[tuple[Path, str]]]:
    return scan_paths(tracked_files())


def scan_tree(root: Path) -> tuple[list[Hit], list[tuple[Path, str]]]:
    """Scan EVERY file under ``root`` (tracked or not) — used by the synthetic
    positive/negative fixtures."""
    paths: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in (".git", "__pycache__")]
        paths.extend(Path(dirpath) / name for name in filenames)
    return scan_paths(paths)


def format_hits(hits: list[Hit]) -> str:
    """REDACTED report: kind + path + line only. The matched value is never
    printed, so a real secret can never be copied into a review/CI log."""
    lines: list[str] = []
    for hit in sorted(hits, key=lambda h: str(h.path)):
        where = f":{hit.line}" if hit.line is not None else ""
        lines.append(f"  FAIL[{hit.kind}-{hit.detail}]: {hit.path}{where}")
    return "\n".join(lines)


def main() -> int:
    hits, placeholders = scan_tracked()
    for path, name in placeholders:
        print(f"  info: {path}: [{name}] (rejection-rule reference, not a secret)")
    if hits:
        print(f"SECRET_SCAN: {len(hits)} FAILING hit(s):")
        print(format_hits(hits))
        return 1
    print(
        f"SECRET_SCAN: 0 secret hits "
        f"(informational placeholder references: {len(placeholders)})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
