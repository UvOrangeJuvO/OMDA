"""G5-004 — secret scanner positive/negative fixtures and redaction contract.

The scanner is the T5.3 release gate. These tests prove, with synthetic
fixtures, that forbidden artifact classes are caught by PATH POLICY even when
empty/binary, that representative synthetic tokens are caught by CONTENT
POLICY over text files, that binary files are never text-decoded, and that the
reported output NEVER contains the matched secret value.
"""

from __future__ import annotations

from pathlib import Path

from tools.release_audit.scan_secrets import (
    format_hits,
    scan_paths,
    scan_tree,
)

SYNTHETIC_TOKEN = "sk_live_" + "a" * 28  # Stripe-shaped synthetic token
SYNTHETIC_PUSHPUSH = "PUSHPLUS_TOKEN = '<SYNTHETIC_TEST_VALUE>'"
SYNTHETIC_PRIVATE_KEY = "-----BEGIN SYNTHETIC TEST KEY-----"

# A fake secret that must NEVER appear in scanner output.
UNSHIPPED_SECRET = "SYNTHETIC-VALUE-NEVER-PRINT"


def _make_tree(root: Path, forbidden: bool) -> Path:
    """Build a synthetic tree with (or without) forbidden artifacts."""
    root.mkdir(parents=True, exist_ok=True)
    (root / "README.md").write_text(
        "OMDA release fixture. Contact: admin@example.com (placeholder).",
        encoding="utf-8",
    )
    (root / "src").mkdir()
    (root / "src" / "app.py").write_text(
        "# real code\nAPI_URL = 'https://example.com'\ncfg = dict(channel='markdown')\n",
        encoding="utf-8",
    )
    if forbidden:
        (root / "cookies-live.json").write_text("{}", encoding="utf-8")
        (root / "leaked-state.sqlite3").write_bytes(b"\x00\x01\x02SQLite format 3\x00")
        (root / ".env").write_text("OMDA_PP_TOKEN=should-never-ship\n", encoding="utf-8")
        (root / "browser-profile" / "Default" / "cookies").mkdir(parents=True)
        (root / "browser-profile" / "Default" / "cookies" / "data").write_bytes(b"\x00\x01")
        (root / "id_rsa").write_text(SYNTHETIC_PRIVATE_KEY + "\n", encoding="utf-8")
        (root / "src" / "secrets.py").write_text(
            f"token = '{UNSHIPPED_SECRET}'\n{SYNTHETIC_PUSHPUSH}\n",
            encoding="utf-8",
        )
        (root / "src" / "pay.py").write_text(
            f"sk = '{SYNTHETIC_TOKEN}'\n", encoding="utf-8"
        )
    return root


def test_forbidden_path_policy_catches_artifact_classes(tmp_path: Path) -> None:
    root = _make_tree(tmp_path / "leak", forbidden=True)
    hits, _ = scan_tree(root)
    kinds = {(h.kind, h.detail) for h in hits}
    # Every forbidden artifact class is caught by PATH POLICY — even the empty
    # cookie jar and the binary sqlite file that carry no text token.
    assert ("forbidden-path", "cookie-jar") in kinds
    assert ("forbidden-path", "runtime-db") in kinds
    assert ("forbidden-path", "dotenv") in kinds
    assert ("forbidden-path", "browser-profile") in kinds
    assert ("forbidden-path", "ssh-key") in kinds  # id_rsa
    # Content policy also fires on the text token assignments.
    assert ("token", "pushplus-token") in kinds
    assert ("token", "stripe-key") in kinds


def test_clean_tree_has_no_failing_hits(tmp_path: Path) -> None:
    root = _make_tree(tmp_path / "clean", forbidden=False)
    hits, placeholders = scan_tree(root)
    assert hits == []
    # The @example.com placeholder reference is informational only (the
    # codebase's own rejection-rule marker), never a failing hit.
    assert placeholders, "placeholder reference should be reported as info"


def test_binary_files_are_never_text_decoded(tmp_path: Path) -> None:
    # A binary blob that CONTAINS token-shaped bytes must not be decoded: it
    # cannot be a real credential, and garbage matches must not fire.
    blob = b"token = '" + b"x" * 40 + b"'"
    p = tmp_path / "blob.bin"
    p.write_bytes(b"\x00\x01\x02" + blob + b"\x00")
    hits, _ = scan_paths([p])
    assert hits == []


def test_report_never_prints_the_matched_secret(tmp_path: Path) -> None:
    root = _make_tree(tmp_path / "redact", forbidden=True)
    hits, _ = scan_tree(root)
    assert hits, "fixture must produce hits"
    report = format_hits(hits)
    # The redacted report contains kind/path/line but never the secret values.
    assert UNSHIPPED_SECRET not in report
    assert SYNTHETIC_TOKEN not in report
    assert SYNTHETIC_PUSHPUSH not in report
    assert SYNTHETIC_PRIVATE_KEY not in report
    assert "FAIL[forbidden-path-" in report or "FAIL[token-" in report
    # Line numbers are present for content hits.
    assert any("secrets.py:2" in line or "pay.py:1" in line for line in report.splitlines())


def test_tracked_force_added_forbidden_artifact_is_detected(tmp_path: Path) -> None:
    """Reviewer reproduction: force-added cookies-live.json / leaked-state.sqlite3
    are TRACKED, so `scan_tracked` must flag them even though .gitignore normally
    excludes them. The test cleans up its own git-index mutation."""
    import subprocess

    from tools.release_audit.scan_secrets import scan_tracked

    repo = Path.cwd()
    synthetic = repo / "var" / "g5-secret-fixture"
    synthetic.mkdir(parents=True, exist_ok=True)
    cookie = synthetic / "cookies-live.json"
    state = synthetic / "leaked-state.sqlite3"
    cookie.write_text("{}", encoding="utf-8")
    state.write_bytes(b"\x00SQLite format 3\x00")
    try:
        subprocess.run(
            ["git", "add", "-f", str(cookie), str(state)],
            check=True, capture_output=True,
        )
        try:
            hits, _ = scan_tracked()
        finally:
            subprocess.run(["git", "reset", "-q", "--", str(cookie), str(state)], check=True)
        kinds = {(h.kind, h.detail, h.path.name) for h in hits}
        assert ("forbidden-path", "cookie-jar", "cookies-live.json") in kinds
        assert ("forbidden-path", "runtime-db", "leaked-state.sqlite3") in kinds
    finally:
        cookie.unlink(missing_ok=True)
        state.unlink(missing_ok=True)
        synthetic.rmdir()
