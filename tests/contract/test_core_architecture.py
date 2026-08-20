"""Cross-Gate architecture test (G2 #1): the Recommendation Core stays pure.

Core modules must not import storage, sqlite3, network, browser or vendor SDKs,
and must not import external Ports (GenreSource/HistoryPort/LLM/Delivery) — the
Orchestrator reads immutable history snapshots and passes them in as arguments.
"""

from __future__ import annotations

import ast
from pathlib import Path

CORE_DIR = Path(__file__).resolve().parents[2] / "src" / "omda" / "core"

FORBIDDEN_TOP_LEVEL = {
    "sqlite3",
    "requests",
    "urllib",
    "http",
    "httpx",
    "socket",
    "playwright",
    "selenium",
    "bs4",
    "browser",
}
FORBIDDEN_PORT_MODULES = {
    # Port PROTOCOL modules and storage/orchestration: Core may only use domain
    # values (omda.ports.domain, omda.ports.critic value types) as arguments.
    "omda.ports.history",
    "omda.ports.llm",
    "omda.ports.delivery",
    "omda.storage",
    "omda.adapters",
    "omda.orchestrator",
}


def _imported_names(tree: ast.AST) -> list[str]:
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module)
    return names


def test_core_has_no_forbidden_imports() -> None:
    core_files = sorted(CORE_DIR.glob("*.py"))
    assert core_files, "core package has no modules"
    for path in core_files:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for name in _imported_names(tree):
            assert name.split(".")[0] not in FORBIDDEN_TOP_LEVEL, (
                f"{path.name} imports forbidden top-level module {name!r}"
            )
            for forbidden in FORBIDDEN_PORT_MODULES:
                assert not name.startswith(forbidden), (
                    f"{path.name} imports external Port/storage module {name!r}"
                )


def test_core_package_imports_without_side_effects() -> None:
    # Importing the whole core package must not pull in storage or orchestrator.
    import sys

    before = {m for m in sys.modules if m.startswith("omda.")}
    import omda.core  # noqa: F401
    import omda.core.album  # noqa: F401
    import omda.core.cooldown  # noqa: F401
    import omda.core.diversity  # noqa: F401
    import omda.core.genre  # noqa: F401
    import omda.core.rating  # noqa: F401
    import omda.core.year  # noqa: F401

    newly_loaded = {m for m in sys.modules if m.startswith("omda.")} - before
    forbidden_prefixes = ("omda.storage", "omda.orchestrator", "omda.adapters")
    assert not any(m.startswith(forbidden_prefixes) for m in newly_loaded)
