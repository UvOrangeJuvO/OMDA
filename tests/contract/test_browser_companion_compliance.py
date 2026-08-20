"""G3 T3.4 — Browser Companion compliance contract tests.

Prove (by source inspection and repository state, not chat claims):
1. live RYM is never required by ordinary tests;
2. no cookie / browser profile / personal data is tracked in Git;
3. no mass-crawl, stealth, CAPTCHA solver or Album Detail fan-out path exists;
4. disabling the Browser Companion leaves Core/G2 fully functional (fakes);
5. Core stays free of any browser_companion import.
"""

from __future__ import annotations

import ast
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
COMPANION_DIR = REPO / "browser_companion"
CORE_DIR = REPO / "src" / "omda" / "core"

FORBIDDEN_IMPORTS = {
    "socket",
    "urllib",
    "requests",
    "httpx",
    "selenium",
    "playwright",
    "bs4",
}
FORBIDDEN_TERMS = (
    "captcha_solver",
    "solve_captcha",
    "stealth",
    "cloudflare_bypass",
    "bypass_cloudflare",
    "album_detail",
    "fan_out",
    "fanout",
    "mass_crawl",
    "pre_crawl",
)


def _python_files(directory: Path) -> list[Path]:
    return sorted(directory.rglob("*.py"))


def _read_tree(path: Path) -> ast.AST:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _imported_names(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module.split(".")[0])
    return names


def test_companion_has_no_network_or_browser_sdk_imports() -> None:
    # The companion extracts from HTML strings only; no live RYM is reachable
    # from ordinary code, hence not required by ordinary tests.
    for path in _python_files(COMPANION_DIR):
        imported = _imported_names(_read_tree(path))
        assert not (imported & FORBIDDEN_IMPORTS), f"{path}: imports {imported & FORBIDDEN_IMPORTS}"


def test_no_anti_detection_or_album_detail_fanout_terms() -> None:
    # No stealth / CAPTCHA solving / Cloudflare bypass / mass-crawl / Album
    # Detail fan-out anywhere in the companion source.
    for path in _python_files(COMPANION_DIR):
        text = path.read_text(encoding="utf-8").lower()
        for term in FORBIDDEN_TERMS:
            assert term not in text, f"{path}: forbidden term {term!r}"


def test_no_cookie_or_profile_files_are_tracked() -> None:
    tracked = subprocess.run(
        ["git", "ls-files"], cwd=REPO, capture_output=True, text=True, check=True
    ).stdout.splitlines()
    offenders = [
        p
        for p in tracked
        if "cookie" in p.lower()
        or "browser-profile" in p.lower()
        or p.endswith((".sqlite3", ".db"))
    ]
    assert offenders == [], f"tracked files must not include cookies/profiles/db: {offenders}"


def test_no_cookie_or_profile_usage_in_companion_code() -> None:
    # Comments/docstrings may mention cookies (describing that they are never
    # touched); CODE must never reference cookie/profile identifiers.
    for path in _python_files(COMPANION_DIR):
        tree = _read_tree(path)
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and (
                "cookie" in node.id.lower() or "profile" in node.id.lower()
            ):
                raise AssertionError(f"{path}: code references {node.id!r}")
            if isinstance(node, ast.Attribute) and (
                "cookie" in node.attr.lower() or "profile" in node.attr.lower()
            ):
                raise AssertionError(f"{path}: code references {node.attr!r}")


def test_core_never_imports_browser_companion() -> None:
    for path in _python_files(CORE_DIR):
        imported = _imported_names(_read_tree(path))
        assert "browser_companion" not in imported, f"{path}: Core imports browser_companion"


def test_disabling_companion_leaves_core_fully_functional() -> None:
    # With no Browser Companion involved, the accepted G2 engine still produces
    # a complete plan using fakes (SPEC §3.4: companion is optional).
    from tests.fakes import FakeAlbumSource, FakeDelivery, FakeGenreSource, FakeLLM, InMemoryHistory

    from omda.config import load_config
    from omda.orchestrator.run import RunEngine

    genres = [__import__("omda.ports.domain", fromlist=["GenreRef"]).GenreRef(
        f"g{i}", f"G{i}", f"F{i % 3}"
    ) for i in range(9)]
    albums = {
        g.genre_id: [
            __import__("omda.ports.domain", fromlist=["AlbumCandidate"]).AlbumCandidate(
                f"{g.genre_id}-a", f"{g.genre_id} Album", "Artist", 2015
            ),
            __import__("omda.ports.domain", fromlist=["AlbumCandidate"]).AlbumCandidate(
                f"{g.genre_id}-b", f"{g.genre_id} B", "Artist", 2000
            ),
            __import__("omda.ports.domain", fromlist=["AlbumCandidate"]).AlbumCandidate(
                f"{g.genre_id}-c", f"{g.genre_id} C", "Artist", 1990
            ),
        ]
        for g in genres
    }
    engine = RunEngine(
        config=load_config(),
        history=InMemoryHistory(),
        genre_source=FakeGenreSource(genres),
        album_source=FakeAlbumSource(albums),
        llm=FakeLLM("Explanatory text."),
        delivery=FakeDelivery(),
        seed="no-companion",
    )
    outcome = engine.run("run-1")
    assert outcome.state == "COMPLETE"
    assert outcome.plan is not None and len(outcome.plan.genres) == 3
