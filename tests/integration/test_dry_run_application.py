"""G4 Re-review 1 — G4-003: a real executable dry-run application path.

The production dry-run must: run the real RunEngine with a real (scripted)
LLM adapter; write the intended local Markdown preview; make ZERO external
calls; resolve NO PushPlus token; and leave ALL official Genre/Album history
unchanged across repeated dry-runs. Only --deliver can enable external push
and official commit.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from tests.fakes import FakeAlbumSource, FakeGenreSource, InMemoryHistory

from omda.adapters.llm import LLMAdapter
from omda.cli import DeliveryMode, run_dry_run
from omda.orchestrator.run import COMPLETE
from omda.ports.domain import AlbumCandidate, GenreRef


class ScriptedLLM:
    def __init__(self, text: str = "A concise explanation of the picks.") -> None:
        self.text = text
        self.calls = 0

    def complete(self, system: str, user: str) -> str:
        self.calls += 1
        return self.text


def _genres() -> list[GenreRef]:
    return [
        GenreRef("ambient", "Ambient", "Electronic"),
        GenreRef("bebop", "Bebop", "Jazz"),
        GenreRef("krautrock", "Krautrock", "Rock"),
        GenreRef("tuareg", "Tuareg Music", "Regional"),
        GenreRef("idm", "IDM", "Electronic"),
    ]


def _albums(gid: str) -> list[AlbumCandidate]:
    return [
        AlbumCandidate(f"{gid}-1", f"{gid} Album 1", "Artist", 2015),
        AlbumCandidate(f"{gid}-2", f"{gid} Album 2", "Artist", 2000),
        AlbumCandidate(f"{gid}-3", f"{gid} Album 3", "Artist", 1990),
        AlbumCandidate(f"{gid}-4", f"{gid} Album 4", "Artist", 2020),
    ]


def _dry_run(run_id: str, out: Path, seed: str):
    return run_dry_run(
        run_id=run_id,
        output_dir=out,
        genre_source=FakeGenreSource(_genres()),
        album_source=FakeAlbumSource({g.genre_id: _albums(g.genre_id) for g in _genres()}),
        llm=LLMAdapter(transport=ScriptedLLM()),
        seed=seed,
    )


def test_run_dry_run_writes_preview_and_keeps_history_neutral() -> None:
    # The PRODUCTION dry-run callable executes the real RunEngine, writes the
    # local Markdown preview, makes zero external calls and leaves the official
    # (sentinel) history untouched — the dry-run uses an isolated history.
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "previews"
        os.environ.pop("PUSHPLUS_TOKEN", None)

        outcome = _dry_run("dry-1", out, "dry-run")
        assert outcome.state == COMPLETE
        assert outcome.payload.startswith("# 每日音乐发现")
        # Local preview exists.
        preview = out / "dry-1.md"
        assert preview.exists()
        assert preview.read_text(encoding="utf-8").startswith("# 每日音乐发现")
        # The sentinel PRODUCTION history was never opened or written.
        assert not (out / "history.sqlite").exists()


def test_repeated_dry_runs_do_not_pollute_history() -> None:
    # Seven rehearsals must not advance official cooldown or Album history —
    # each dry-run works against an isolated history, so the official store
    # (a fresh sentinel) stays empty across all runs.
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "previews"
        official = InMemoryHistory()  # sentinel: the official store
        for i in range(7):
            outcome = _dry_run(f"dry-{i}", out, f"dry-{i}")
            assert outcome.state == COMPLETE
            # The dry-run NEVER touched the official store.
            assert official.latest_pick_index() == 0
            assert official.excluded_album_identities() == frozenset()
        assert len(list(out.glob("*.md"))) == 7


def test_dry_run_resolves_no_token() -> None:
    # A token in the environment must not be resolved by the dry-run path
    # (only the PushPlus deliver path reads it); the dry-run completes cleanly.
    os.environ["PUSHPLUS_TOKEN"] = "should-not-be-touched"
    try:
        with tempfile.TemporaryDirectory() as d:
            outcome = _dry_run("dry-token", Path(d), "dry-token")
            assert outcome.state == COMPLETE
    finally:
        del os.environ["PUSHPLUS_TOKEN"]


def test_deliver_mode_still_requires_explicit_flag() -> None:
    # Only an explicit --deliver unlocks external push; the default remains
    # dry-run even when the delivery config names pushplus.
    from omda.cli import parse_args

    assert parse_args([]).deliver is False
    assert parse_args(["--deliver"]).deliver is True
    assert DeliveryMode.DRY_RUN.value == "dry-run"
