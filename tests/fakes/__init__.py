"""Shared fake/in-memory implementations of Port contracts (T1.4, used by G2).

These fakes are contract fixtures, not production code: they satisfy the Port
shapes so Orchestrator and contract tests run without live RYM/MusicBrainz/
LLM/PushPlus (SPEC §3.2: tests use fixtures/fakes for ordinary CI).
"""

from __future__ import annotations

from omda.ports.domain import (
    AlbumCandidate,
    AlbumIdentity,
    DeliveryReceipt,
    GenreRef,
    JournalEntry,
)


class InMemoryHistory:
    """In-memory HistoryPort for tests: journal, picks, albums, receipts."""

    def __init__(self) -> None:
        self._journal: list[JournalEntry] = []
        self._next_journal_id = 1
        self._picks: list[tuple[int, str]] = []  # (pick_index, genre_id)
        self._albums: dict[str, AlbumIdentity] = {}
        self._receipts: dict[str, DeliveryReceipt] = {}

    def append_journal(
        self,
        run_id: str,
        transition: str,
        at: str,
        detail: dict | None = None,
    ) -> JournalEntry:
        entry = JournalEntry(
            journal_id=self._next_journal_id,
            run_id=run_id,
            transition=transition,
            at=at,
            detail=detail,
        )
        self._next_journal_id += 1
        self._journal.append(entry)
        return entry

    def journal_after(self, run_id: str, after_journal_id: int) -> list[JournalEntry]:
        return [
            e for e in self._journal if e.run_id == run_id and e.journal_id > after_journal_id
        ]

    def latest_pick_index(self) -> int:
        return max((idx for idx, _ in self._picks), default=0)

    def record_genre_pick(
        self, run_id: str, genre_id: str, pick_index: int, committed_at: str
    ) -> None:
        self._picks.append((pick_index, genre_id))

    def cooldown_pick_indices(self, genre_id: str) -> list[int]:
        return [idx for idx, gid in self._picks if gid == genre_id]

    def record_album(self, run_id: str, identity: AlbumIdentity, recommended_at: str) -> None:
        self._albums[identity.album_id] = identity

    def excluded_album_identities(self) -> set[AlbumIdentity]:
        return set(self._albums.values())

    def save_delivery_receipt(self, receipt: DeliveryReceipt) -> None:
        self._receipts[receipt.idempotency_key] = receipt

    def find_delivery_receipt(self, idempotency_key: str) -> DeliveryReceipt | None:
        return self._receipts.get(idempotency_key)


class FakeGenreSource:
    def __init__(self, genres: list[GenreRef] | None = None) -> None:
        self._genres = genres if genres is not None else []

    def list_eligible_genres(self) -> list[GenreRef]:
        return [g for g in self._genres if g.eligible]


class FakeAlbumSource:
    def __init__(self, by_genre: dict[str, list[AlbumCandidate]] | None = None) -> None:
        self._by_genre = by_genre or {}

    def candidates_for_genre(
        self, genre: GenreRef, limit: int | None = None
    ) -> list[AlbumCandidate]:
        found = self._by_genre.get(genre.genre_id, [])
        return found[:limit] if limit is not None else list(found)


class FakeCriticRatingSource:
    def __init__(self) -> None:
        self._rows: dict[str, list] = {}

    def add(self, album_id: str, row) -> None:
        self._rows.setdefault(album_id, []).append(row)

    def ratings_for(self, album: AlbumCandidate) -> list:
        return list(self._rows.get(album.album_id, []))


class FakeLLM:
    """Returns a fixed narrative; never alters selection."""

    def __init__(self, text: str = "Fake narrative.") -> None:
        self._text = text

    def generate_narrative(self, fact_packet: dict) -> str:
        return self._text


class FakeDelivery:
    """Records deliveries; same idempotency key never delivers twice."""

    def __init__(self) -> None:
        self.delivered: dict[str, str] = {}
        self._clock = iter(range(1, 10**6))

    def deliver(
        self,
        payload: str,
        idempotency_key: str,
        target: str | None = None,
    ) -> DeliveryReceipt:
        if idempotency_key in self.delivered:
            return DeliveryReceipt(
                run_id="",
                idempotency_key=idempotency_key,
                delivered_at="2026-08-19T00:00:00+00:00",
                channel="fake",
                status="ok",
                target=target,
            )
        self.delivered[idempotency_key] = payload
        return DeliveryReceipt(
            run_id="",
            idempotency_key=idempotency_key,
            delivered_at="2026-08-19T00:00:00+00:00",
            channel="fake",
            status="ok",
            target=target,
        )


__all__ = [
    "FakeAlbumSource",
    "FakeCriticRatingSource",
    "FakeDelivery",
    "FakeGenreSource",
    "FakeLLM",
    "InMemoryHistory",
]
