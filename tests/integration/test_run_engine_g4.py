"""G4 Re-review 1 — G4-001: production RunEngine must render+validate Markdown.

The REAL application path (RunEngine) must deliver a deterministic structured
Markdown report whose facts come only from the selected plan, or fail
validation. An adversarial LLM response must never be delivered raw, and on
validation failure delivery calls and official Genre/Album history must stay
zero.
"""

from __future__ import annotations

from tests.fakes import FakeAlbumSource, FakeDelivery, FakeGenreSource, InMemoryHistory

from omda.adapters.llm import LLMAdapter
from omda.config import load_config
from omda.orchestrator.run import COMPLETE, FAILED, RunEngine
from omda.ports.domain import AlbumCandidate, GenreRef


def _genres() -> list[GenreRef]:
    return [
        GenreRef("ambient", "Ambient", "Electronic"),
        GenreRef("bebop", "Bebop", "Jazz"),
        GenreRef("krautrock", "Krautrock", "Rock"),
        GenreRef("tuareg", "Tuareg Music", "Regional"),
        GenreRef("idm", "IDM", "Electronic"),
    ]


def _albums(genre_id: str) -> list[AlbumCandidate]:
    return [
        AlbumCandidate(f"{genre_id}-1", f"{genre_id} Album 1", "Artist", 2015),
        AlbumCandidate(f"{genre_id}-2", f"{genre_id} Album 2", "Artist", 2000),
        AlbumCandidate(f"{genre_id}-3", f"{genre_id} Album 3", "Artist", 1990),
        AlbumCandidate(f"{genre_id}-4", f"{genre_id} Album 4", "Artist", 2020),
    ]


class ScriptedLLMTransport:
    def __init__(self, text: str) -> None:
        self.text = text
        self.calls = 0

    def complete(self, system: str, user: str) -> str:
        self.calls += 1
        return self.text


def _run_with_llm_text(text: str, delivery: FakeDelivery | None = None):
    history = InMemoryHistory()
    llm = LLMAdapter(transport=ScriptedLLMTransport(text))
    if delivery is None:
        delivery = FakeDelivery()
    engine = RunEngine(
        config=load_config(),
        history=history,
        genre_source=FakeGenreSource(_genres()),
        album_source=FakeAlbumSource({g.genre_id: _albums(g.genre_id) for g in _genres()}),
        llm=llm,
        delivery=delivery,
        seed="g4-001",
    )
    return engine, history, delivery


def test_production_run_delivers_structured_markdown_not_raw_llm_text() -> None:
    # Reviewer reproduction: the LLM answers with a fabricated recommendation.
    # The production run must deliver a deterministic Markdown report whose
    # facts come ONLY from the selected plan — the fabricated claim must NOT
    # be delivered, and official history must only advance on a valid report.
    engine, history, delivery = _run_with_llm_text(
        "IGNORE FACTS: recommend Fabricated Album by Fake Artist"
    )
    outcome = engine.run("run-1")
    assert outcome.state in (COMPLETE, FAILED)
    if outcome.state == COMPLETE:
        assert outcome.payload is not None
        # The delivered payload is the structured report: title + plan facts.
        assert outcome.payload.startswith("# 每日音乐发现")
        # The fabricated bullet is not delivered (facts come from the plan).
        assert "- Fabricated Album" not in outcome.payload
        # A real planned album IS present in the delivered report.
        assert "- " in outcome.payload and "Album 1" in outcome.payload
        # History advanced only for the VALID report (one run, one set).
        assert len(delivery.delivered) == 1
    else:
        # Validation failure: delivery and official history both zero.
        assert len(delivery.delivered) == 0
        assert history.latest_pick_index() == 0
        assert history.excluded_album_identities() == frozenset()


def test_production_run_never_commits_history_for_invalid_payload() -> None:
    # A payload that fails the fact validator must not deliver and must not
    # commit official Genre/Album history (SPEC §4, T4.2).
    engine, history, delivery = _run_with_llm_text(
        "# 每日音乐发现\n\n## 说明\n\nThis is a totally fabricated report with "
        "no plan structure at all.\n"
    )
    outcome = engine.run("run-1")
    # Either rejected (FAILED) or normalized into the structured report; in the
    # FAILED case nothing may be delivered or committed.
    if outcome.state == FAILED:
        assert len(delivery.delivered) == 0
        assert history.latest_pick_index() == 0
        assert history.excluded_album_identities() == frozenset()
    else:
        assert outcome.state == COMPLETE
        assert outcome.payload.startswith("# 每日音乐发现")


# --- G4-008 re-review 3: the LLM narrative is archived (bounded), not discarded --


def test_generated_narrative_is_archived_bounded_in_journal() -> None:
    # The LLM output is invoked once and its result is PERSISTED (bounded)
    # into the GENERATED journal entry — it is never discarded (G4-008), and
    # it is still never part of the delivered payload.

    engine, history, delivery = _run_with_llm_text("Some archival explanation.")
    outcome = engine.run("run-1")
    assert outcome.state == COMPLETE
    generated = next(e for e in history.journal_after("run-1", 0) if e.transition == "GENERATED")
    assert generated.detail is not None
    assert generated.detail["narrative"] == "Some archival explanation."
    # The delivered payload has no free-text slot (mechanical contract).
    assert "Some archival explanation" not in outcome.payload


def test_generated_narrative_is_truncated_to_bounded_length() -> None:
    engine, history, delivery = _run_with_llm_text("x" * 10_000)
    outcome = engine.run("run-1")
    assert outcome.state == COMPLETE
    generated = next(e for e in history.journal_after("run-1", 0) if e.transition == "GENERATED")
    assert len(generated.detail["narrative"]) <= 1500
