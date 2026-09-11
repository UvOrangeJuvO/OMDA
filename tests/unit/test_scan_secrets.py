"""G5-004 / G5-R1-001 — secret scanner fixtures and redaction contract.

The scanner is the T5.3 release gate. These tests prove, with synthetic
fixtures, that forbidden artifact classes are caught by PATH POLICY even when
empty/binary, that representative synthetic credentials are caught by CONTENT
POLICY over text files, that binary files are never text-decoded, and that the
reported output NEVER contains the matched secret value.

G5-R1-001: every synthetic credential VALUE is assembled at RUNTIME from
fragments. The tracked source of this file therefore contains no complete
credential shape, so the release gate can never match its own fixture — the
exact self-match that made the previous candidate fail. Test files are NOT
exempted from scanning.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from tools.release_audit.scan_secrets import (
    format_hits,
    scan_paths,
    scan_tree,
)

# --- runtime-assembled synthetic credentials (never contiguous in source) -----

_FRAG_PP_KEY = "PUSHPLUS" + "_" + "TOKEN"
_FRAG_PP_VALUE = "abcd1234" + "efgh5678" + "ijkl9012" + "mnop3456"
_FRAG_PEM_HEAD = "-----BEGIN RSA " + "PRIVATE" + " KEY-----"
_FRAG_STRIPE = "sk" + "_" + "live" + "_" + "a" * 28
_FRAG_SESSION = "sess" + "0123456789abcdef" + "fedcba98"
# A fake value that must NEVER appear in scanner output.
_FRAG_UNSHIPPED = "S3CR3T" + "-VALUE-NEVER-PRINT-" + "7f8a9b0c"


def _pushplus_assignment() -> str:
    return f"{_FRAG_PP_KEY} = '{_FRAG_PP_VALUE}'"


def _stripe_assignment() -> str:
    return f"key = '{_FRAG_STRIPE}'"


def _session_assignment() -> str:
    return f"session_id = '{_FRAG_SESSION}'"


# --- fixtures -----------------------------------------------------------------

COOKIE_SHAPES = [
    "cookies.json",
    "cookies.txt",
    "Cookies",  # bare browser cookie file, no extension
    "cookie_store.txt",
    "cookiejar.txt",
    "cookie-jar.json",
]


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
        # Cookie artifacts in several common shapes.
        (root / "cookies-live.json").write_text("{}", encoding="utf-8")
        (root / "cookies.txt").write_text("# Netscape HTTP Cookie File\n", encoding="utf-8")
        (root / "Cookies").write_text("", encoding="utf-8")
        (root / "cookie_store.txt").write_text("", encoding="utf-8")
        # Runtime database + browser profile directory.
        (root / "leaked-state.sqlite3").write_bytes(b"\x00\x01\x02SQLite format 3\x00")
        (root / ".env").write_text("OMDA_PP_TOKEN=should-never-ship\n", encoding="utf-8")
        (root / "browser-profile" / "Default" / "cookies").mkdir(parents=True)
        (root / "browser-profile" / "Default" / "cookies" / "data").write_bytes(b"\x00\x01")
        # Key material + content-policy hits (values assembled at runtime).
        (root / "id_rsa").write_text(_FRAG_PEM_HEAD + "\n", encoding="utf-8")
        (root / "src" / "secrets.py").write_text(
            "\n".join(
                [
                    f"value = '{_FRAG_UNSHIPPED}'",
                    _pushplus_assignment(),
                    _session_assignment(),
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        (root / "src" / "pay.py").write_text(_stripe_assignment() + "\n", encoding="utf-8")
    return root


def test_forbidden_path_policy_catches_artifact_classes(tmp_path: Path) -> None:
    root = _make_tree(tmp_path / "leak", forbidden=True)
    hits, _ = scan_tree(root)
    kinds = {(h.kind, h.detail) for h in hits}
    # Every forbidden artifact class is caught by PATH POLICY — even the empty
    # cookie jars and the binary sqlite file that carry no text token.
    assert ("forbidden-path", "cookie-jar") in kinds
    assert ("forbidden-path", "runtime-db") in kinds
    assert ("forbidden-path", "dotenv") in kinds
    assert ("forbidden-path", "browser-profile") in kinds
    assert ("forbidden-path", "ssh-key") in kinds  # id_rsa
    # Content policy also fires on the text credential assignments.
    assert ("token", "pushplus-token") in kinds
    assert ("token", "stripe-key") in kinds
    assert ("token", "cookie-content") in kinds


@pytest.mark.parametrize("name", COOKIE_SHAPES)
def test_cookie_artifact_shapes_are_caught(tmp_path: Path, name: str) -> None:
    """G5-R1-001: cookies.json/.txt, bare `Cookies`, cookie_store.txt,
    cookiejar.txt and cookie-jar.json are all refused by the path policy."""
    path = tmp_path / name
    path.write_text("", encoding="utf-8")
    hits, _ = scan_paths([path])
    assert any(
        h.kind == "forbidden-path" and h.detail == "cookie-jar" for h in hits
    ), f"{name} was not flagged as a cookie artifact"


def test_nested_cookie_artifact_is_caught(tmp_path: Path) -> None:
    nested = tmp_path / "profile" / "Default"
    nested.mkdir(parents=True)
    path = nested / "cookie_store.txt"
    path.write_text("", encoding="utf-8")
    hits, _ = scan_paths([path])
    assert any(h.detail == "cookie-jar" for h in hits if h.kind == "forbidden-path")


def test_ordinary_source_files_are_not_flagged(tmp_path: Path) -> None:
    paths = []
    for name in ("notes.md", "app.py", "settings.json", "records.jsonl"):
        p = tmp_path / name
        p.write_text("plain content\n", encoding="utf-8")
        paths.append(p)
    hits, _ = scan_paths(paths)
    assert hits == []


def test_clean_tree_has_no_failing_hits(tmp_path: Path) -> None:
    root = _make_tree(tmp_path / "clean", forbidden=False)
    hits, placeholders = scan_tree(root)
    assert hits == []
    # The @example.com placeholder reference is informational only (the
    # codebase's own rejection-rule marker), never a failing hit.
    assert placeholders, "placeholder reference should be reported as info"


def test_binary_files_are_never_text_decoded(tmp_path: Path) -> None:
    # A binary blob that CONTAINS credential-shaped bytes must not be decoded:
    # it cannot be a real credential, and garbage matches must not fire.
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
    assert _FRAG_UNSHIPPED not in report
    assert _FRAG_STRIPE not in report
    assert _FRAG_PP_VALUE not in report
    assert _FRAG_PEM_HEAD not in report
    assert _FRAG_SESSION not in report
    assert "FAIL[forbidden-path-" in report or "FAIL[token-" in report
    # Line numbers are present for content hits.
    assert any(
        "secrets.py:2" in line or "pay.py:1" in line for line in report.splitlines()
    )


def test_tracked_force_added_forbidden_artifact_is_detected() -> None:
    """Reviewer reproduction: force-added cookie/database artifacts are TRACKED,
    so `scan_tracked` must flag them even though .gitignore normally excludes
    them. The test cleans up its own git-index mutation."""
    import subprocess

    from tools.release_audit.scan_secrets import scan_tracked

    repo = Path.cwd()
    synthetic = repo / "var" / "g5-secret-fixture"
    synthetic.mkdir(parents=True, exist_ok=True)
    artifacts = {
        "cookies-live.json": b"{}",
        "cookies.txt": b"# Netscape HTTP Cookie File\n",
        "Cookies": b"",
        "cookie_store.txt": b"",
        "leaked-state.sqlite3": b"\x00SQLite format 3\x00",
    }
    created = []
    for name, data in artifacts.items():
        p = synthetic / name
        p.write_bytes(data)
        created.append(p)
    try:
        subprocess.run(
            ["git", "add", "-f", *[str(p) for p in created]],
            check=True, capture_output=True,
        )
        try:
            hits, _ = scan_tracked()
        finally:
            subprocess.run(
                ["git", "reset", "-q", "--", *[str(p) for p in created]], check=True
            )
        flagged = {(h.detail, h.path.name) for h in hits if h.kind == "forbidden-path"}
        for name in ("cookies-live.json", "cookies.txt", "Cookies", "cookie_store.txt"):
            assert ("cookie-jar", name) in flagged, f"{name} not flagged"
        assert ("runtime-db", "leaked-state.sqlite3") in flagged
    finally:
        for p in created:
            p.unlink(missing_ok=True)
        synthetic.rmdir()
