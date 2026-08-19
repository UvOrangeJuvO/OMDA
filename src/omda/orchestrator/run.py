"""Application Orchestrator: run state machine and recovery (G2 T2.6).

Implements the SPEC §4 state machine against the G1 Port contracts and fakes
only — no live RYM/MusicBrainz/LLM/PushPlus. The deterministic Recommendation
Core performs every selection; the Orchestrator sequences side effects and
enforces history-write ordering (official history ONLY after validated
delivery).

State machine: PLAN -> FETCH -> SELECT -> GENERATE -> VALIDATE -> DELIVER
-> COMMIT HISTORY -> COMPLETE, plus FAILED / ABANDONED / RECOVERING.

Recovery semantics: every durable transition is journaled; delivery success is
backed by an immutable receipt keyed by a stable idempotency key; a
delivered-but-not-committed window is resolved from durable evidence, never by
blind re-delivery. All retry paths are bounded.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from omda.config import Config, config_to_dict
from omda.core.album import dedupe_candidates, filter_candidates
from omda.core.genre import select_daily_genres
from omda.core.rating import rank_candidates
from omda.core.year import select_albums_for_genre
from omda.ports.album import AlbumSource
from omda.ports.critic import CriticRatingRow
from omda.ports.delivery import Delivery
from omda.ports.domain import (
    AlbumCandidate,
    AlbumIdentity,
    DeliveryReceipt,
    GenrePickRecord,
    GenreRef,
    JournalEntry,
)
from omda.ports.errors import (
    DeliveryFailureError,
    DomainError,
    GenerationFailureError,
    InsufficientCandidatesError,
    SourceUnavailableError,
    StateCommitFailureError,
    ValidationFailureError,
)
from omda.ports.genre import GenreSource
from omda.ports.history import HistoryPort
from omda.ports.llm import LLM
from omda.seed import make_rng

MAX_PAYLOAD_LENGTH = 4000
MAX_RUN_ATTEMPTS = 2

# Run transitions (SPEC §4).
PLANNED = "PLANNED"
FETCHED = "FETCHED"
SELECTED = "SELECTED"
GENERATED = "GENERATED"
VALIDATED = "VALIDATED"
DELIVERING = "DELIVERING"
DELIVERED = "DELIVERED"
HISTORY_COMMITTED = "HISTORY_COMMITTED"
COMPLETE = "COMPLETE"
FAILED = "FAILED"
ABANDONED = "ABANDONED"
RECOVERING = "RECOVERING"

_TERMINAL_FAILED = frozenset({FAILED, ABANDONED})
_AFTER_DELIVER = frozenset({DELIVERING, DELIVERED, RECOVERING})


def utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _config_fingerprint(config: Config) -> str:
    """Deterministic fingerprint of the effective configuration (G2-006)."""
    raw = json.dumps(config_to_dict(config), sort_keys=True, default=str)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


@dataclass(frozen=True)
class SelectedAlbum:
    album_id: str
    genre_id: str
    title: str
    artist: str
    year: int | None
    canonical_id: str | None = None
    canonical_source: str | None = None
    identity_confidence: str = "exact"


@dataclass(frozen=True)
class Plan:
    """The selected 3x3 recommendation plan (deterministic Core output).

    ``pick_records`` carries the EXACT ordered official GenrePickRecord values
    (global indices starting at ``latest_pick_index + 1``); recovery never
    regenerates local 1..N indices (G2-001).
    """

    run_id: str
    genres: tuple[GenreRef, ...]
    albums: tuple[SelectedAlbum, ...]
    pick_records: tuple[GenrePickRecord, ...] = ()

    def genre_picks(self) -> list[GenrePickRecord]:
        if self.pick_records:
            return list(self.pick_records)
        # Fallback for plans constructed without explicit records (never used by
        # the Orchestrator): preserve deterministic 1..N order only as a last resort.
        return [GenrePickRecord(i + 1, g.genre_id) for i, g in enumerate(self.genres)]

    def album_identities(self) -> list[AlbumIdentity]:
        return [
            AlbumIdentity(
                album_id=a.album_id,
                canonical_id=a.canonical_id,
                canonical_source=a.canonical_source,
                identity_confidence=a.identity_confidence,
            )
            for a in self.albums
        ]

    def digest(self) -> dict[str, Any]:
        return {
            "genres": [
                {
                    "genre_id": g.genre_id,
                    "pick_index": pick.pick_index,
                    "family": g.family,
                }
                for g, pick in zip(self.genres, self.genre_picks(), strict=True)
            ],
            "albums": [
                {
                    "album_id": a.album_id,
                    "genre_id": a.genre_id,
                    "title": a.title,
                    "artist": a.artist,
                    "year": a.year,
                    "canonical_id": a.canonical_id,
                    "canonical_source": a.canonical_source,
                    "identity_confidence": a.identity_confidence,
                }
                for a in self.albums
            ],
        }

    @classmethod
    def from_digest(cls, run_id: str, digest: dict[str, Any]) -> Plan:
        genres = tuple(
            GenreRef(g["genre_id"], g["genre_id"], g.get("family", ""))
            for g in digest["genres"]
        )
        pick_records = tuple(
            GenrePickRecord(g["pick_index"], g["genre_id"]) for g in digest["genres"]
        )
        albums = tuple(
            SelectedAlbum(
                album_id=a["album_id"],
                genre_id=a["genre_id"],
                title=a["title"],
                artist=a["artist"],
                year=a.get("year"),
                canonical_id=a.get("canonical_id"),
                canonical_source=a.get("canonical_source"),
                identity_confidence=a.get("identity_confidence", "exact"),
            )
            for a in digest["albums"]
        )
        return cls(
            run_id=run_id,
            genres=genres,
            albums=albums,
            pick_records=pick_records,
        )


@dataclass(frozen=True)
class FactPacket:
    run_id: str
    plan: Plan


@dataclass(frozen=True)
class RunOutcome:
    run_id: str
    state: str
    plan: Plan | None = None
    payload: str | None = None
    receipt: DeliveryReceipt | None = None


class RunEngine:
    """Sequences one recommendation run over the Port contracts.

    All state transitions are journaled; official history is written only via
    ``HistoryPort.commit_history`` after validated delivery (SPEC §4).
    """

    def __init__(
        self,
        *,
        config: Config,
        history: HistoryPort,
        genre_source: GenreSource,
        album_source: AlbumSource,
        llm: LLM,
        delivery: Delivery,
        seed: str = "default",
        input_version: str = "unknown",
        critic_rows: dict[str, list[CriticRatingRow]] | None = None,
        rating_weights: dict[str, float] | None = None,
        missing_policy: str = "skip",
    ) -> None:
        self._config = config
        self._history = history
        self._genre_source = genre_source
        self._album_source = album_source
        self._llm = llm
        self._delivery = delivery
        # G2-006: the RNG is bound to the recorded seed; journaling the seed must
        # not consume a draw, so the generator starts from the same provenance.
        self._seed = seed
        self._input_version = input_version
        self._config_version = _config_fingerprint(config)
        self._rng = make_rng(seed)
        self._critic_rows = critic_rows or {}
        self._rating_weights = rating_weights or {}
        self._missing_policy = missing_policy

    # -- public API ------------------------------------------------------------

    def run(self, run_id: str) -> RunOutcome:
        # Single bounded pass: a failed run is FAILED with history untouched.
        # (Replanning is intentionally not layered here — G2 keeps retry paths
        # explicit and bounded at the Orchestrator level.)
        return self._run_once(run_id)

    def recover(self, run_id: str) -> RunOutcome:
        """Resume from durable journal/receipt evidence (no process memory)."""
        entries = self._journal(run_id)
        if not entries:
            return RunOutcome(run_id=run_id, state=FAILED)
        last = entries[-1].transition
        if last in _TERMINAL_FAILED:
            return RunOutcome(run_id=run_id, state=last)
        if last in (HISTORY_COMMITTED, COMPLETE):
            return RunOutcome(run_id=run_id, state=COMPLETE)
        if last in _AFTER_DELIVER:
            return self._finish_after_delivery(run_id, entries)
        # Mid-flight failure before delivery: safe to fail (history untouched).
        self._append(run_id, FAILED, {"reason": "recover from incomplete pre-delivery state"})
        return RunOutcome(run_id=run_id, state=FAILED)

    # -- internals --------------------------------------------------------------

    def _journal(self, run_id: str) -> list[JournalEntry]:
        return self._history.journal_after(run_id, 0)

    def _append(self, run_id: str, transition: str, detail: dict[str, Any] | None = None) -> None:
        self._history.append_journal(run_id, transition, utc_now(), detail)

    def _run_once(self, run_id: str) -> RunOutcome:
        # G2-006: record provenance (seed/input/config versions) WITHOUT consuming
        # the RNG — the recorded seed is the one the generator was built from.
        self._append(
            run_id,
            PLANNED,
            {
                "seed": self._seed,
                "input_version": self._input_version,
                "config_version": self._config_version,
            },
        )
        try:
            # PLAN: authoritative global next index comes from committed history
            # (G2-001), never inferred from the currently visible Genre source.
            genres = self._genre_source.list_eligible_genres()
            pick_history = {
                g.genre_id: self._history.cooldown_pick_indices(g.genre_id) for g in genres
            }
            global_start = self._history.latest_pick_index() + 1
            chosen = select_daily_genres(
                genres,
                self._config.daily_genre_count,
                self._rng,
                pick_history=pick_history,
                global_start_index=global_start,
                cooldown_picks=self._config.genre_cooldown_picks,
            )

            # FETCH: candidates per genre.
            candidates_by_genre: dict[str, list[AlbumCandidate]] = {}
            for genre in chosen:
                candidates_by_genre[genre.genre_id] = self._album_source.candidates_for_genre(
                    genre
                )
            self._append(run_id, FETCHED)

            # SELECT: deterministic Core selection (3x3), permanent exclusion +
            # within-run dedup + rating + year constraints.
            exclusions = self._history.excluded_album_identities()
            plan = self._select(run_id, chosen, global_start, candidates_by_genre, exclusions)
            # Validate the planned sequence BEFORE delivery: an index conflict
            # must never first appear after external delivery (G2-001).
            for pick in plan.genre_picks():
                if pick.pick_index in pick_history.get(pick.genre_id, ()):
                    self._append(run_id, FAILED, {"reason": "planned pick collides with history"})
                    return RunOutcome(run_id=run_id, state=FAILED)
            self._append(run_id, SELECTED, plan.digest())

            # GENERATE + VALIDATE.
            payload = self._generate(plan)
            self._append(run_id, GENERATED)
            self._validate_payload(payload)
            self._append(run_id, VALIDATED)

            # DELIVER with stable idempotency key; persist receipt first.
            return self._deliver_and_commit(run_id, plan, payload)
        except (SourceUnavailableError, InsufficientCandidatesError) as exc:
            self._append(run_id, FAILED, {"reason": type(exc).__name__, "message": str(exc)})
            return RunOutcome(run_id=run_id, state=FAILED)
        except (GenerationFailureError, ValidationFailureError, DeliveryFailureError) as exc:
            self._append(run_id, FAILED, {"reason": type(exc).__name__, "message": str(exc)})
            return RunOutcome(run_id=run_id, state=FAILED)

    def _replan_worthwhile(self, run_id: str) -> bool:
        # Kept for bounded-replan intent; always False at this layer (no silent
        # retries; candidate shortage surfaces as FAILED for the caller).
        return False

    def _select(
        self,
        run_id: str,
        chosen: list[GenreRef],
        global_start_index: int,
        candidates_by_genre: dict[str, list[AlbumCandidate]],
        exclusions: frozenset[AlbumIdentity],
    ) -> Plan:
        # Exact ordered official pick records (G2-001): position i receives global
        # index global_start_index + i; never regenerated locally afterwards.
        pick_records = tuple(
            GenrePickRecord(global_start_index + i, genre.genre_id)
            for i, genre in enumerate(chosen)
        )
        selected_albums: list[SelectedAlbum] = []
        already_selected: list[AlbumCandidate] = []
        for genre in chosen:
            pool = filter_candidates(candidates_by_genre.get(genre.genre_id, []), exclusions)
            pool = dedupe_candidates(pool, already_selected)
            ranked = rank_candidates(
                pool, self._critic_rows, self._rating_weights, self._missing_policy
            )
            picked = select_albums_for_genre(
                ranked,
                count=self._config.albums_per_genre,
                modern_year=self._config.modern_album_year,
            )
            already_selected.extend(picked)
            for album in picked:
                identity = album.identity
                selected_albums.append(
                    SelectedAlbum(
                        album_id=album.album_id,
                        genre_id=genre.genre_id,
                        title=album.title,
                        artist=album.artist,
                        year=album.year,
                        canonical_id=identity.canonical_id if identity else None,
                        canonical_source=identity.canonical_source if identity else None,
                        identity_confidence=identity.identity_confidence if identity else "exact",
                    )
                )
        return Plan(
            run_id=run_id,
            genres=tuple(chosen),
            albums=tuple(selected_albums),
            pick_records=pick_records,
        )

    def _generate(self, plan: Plan) -> str:
        packet = FactPacket(run_id=plan.run_id, plan=plan)
        try:
            return self._llm.generate_narrative(_packet_dict(packet))
        except DomainError:
            raise
        except Exception as exc:  # provider-side generation failure
            raise GenerationFailureError(f"narrative generation failed: {exc}") from exc

    def _validate_payload(self, payload: str) -> None:
        if not payload or not payload.strip():
            raise ValidationFailureError("generated payload is empty")
        if len(payload) > MAX_PAYLOAD_LENGTH:
            raise ValidationFailureError(
                f"generated payload exceeds {MAX_PAYLOAD_LENGTH} characters"
            )

    def _idempotency_key(self, run_id: str) -> str:
        return f"{run_id}:{self._config.delivery.channel}"

    def _deliver_and_commit(self, run_id: str, plan: Plan, payload: str) -> RunOutcome:
        key = self._idempotency_key(run_id)
        self._append(run_id, DELIVERING, {"idempotency_key": key})
        receipt = self._delivery.deliver(payload, key)
        self._history.save_delivery_receipt(receipt)  # durable evidence first
        if receipt.status != "ok":
            self._append(run_id, FAILED, {"reason": "delivery reported failure"})
            return RunOutcome(run_id=run_id, state=FAILED, payload=payload)
        self._append(run_id, DELIVERED, plan.digest())
        try:
            self._commit_history(run_id, plan)
        except StateCommitFailureError:
            self._append(run_id, RECOVERING, {"reason": "history commit failed after delivery"})
            return RunOutcome(
                run_id=run_id, state=RECOVERING, plan=plan, payload=payload, receipt=receipt
            )
        self._append(run_id, COMPLETE)
        return RunOutcome(
            run_id=run_id, state=COMPLETE, plan=plan, payload=payload, receipt=receipt
        )

    def _commit_history(self, run_id: str, plan: Plan) -> None:
        self._history.commit_history(
            run_id,
            plan.genre_picks(),
            plan.album_identities(),
            utc_now(),
        )

    def _finish_after_delivery(
        self, run_id: str, entries: list[JournalEntry]
    ) -> RunOutcome:
        # Rebuild the plan from durable journal evidence; confirm delivery via the
        # immutable receipt before committing history (never blind re-delivery).
        digest: dict[str, Any] | None = None
        for entry in reversed(entries):
            if entry.detail and "albums" in entry.detail:
                digest = dict(entry.detail)
                break
        if digest is None:
            self._append(run_id, FAILED, {"reason": "no selectable plan in journal"})
            return RunOutcome(run_id=run_id, state=FAILED)

        plan = Plan.from_digest(run_id, digest)
        receipt = self._history.find_delivery_receipt(self._idempotency_key(run_id))
        if receipt is None or receipt.status != "ok":
            # Ambiguous delivery: do NOT re-push; fail closed for human review.
            self._append(run_id, RECOVERING, {"reason": "delivery evidence missing or failed"})
            return RunOutcome(run_id=run_id, state=RECOVERING, plan=plan)
        try:
            self._commit_history(run_id, plan)
        except StateCommitFailureError:
            self._append(run_id, RECOVERING, {"reason": "history commit still failing"})
            return RunOutcome(run_id=run_id, state=RECOVERING, plan=plan)
        self._append(run_id, COMPLETE)
        return RunOutcome(run_id=run_id, state=COMPLETE, plan=plan, receipt=receipt)


def _packet_dict(packet: FactPacket) -> dict[str, Any]:
    return {
        "run_id": packet.run_id,
        "genres": [{"genre_id": g.genre_id, "name": g.name} for g in packet.plan.genres],
        "albums": [
            {"album_id": a.album_id, "title": a.title, "artist": a.artist, "year": a.year}
            for a in packet.plan.albums
        ],
    }


__all__ = [
    "ABANDONED",
    "COMPLETE",
    "DELIVERED",
    "DELIVERING",
    "FAILED",
    "FETCHED",
    "GENERATED",
    "HISTORY_COMMITTED",
    "MAX_PAYLOAD_LENGTH",
    "MAX_RUN_ATTEMPTS",
    "PLANNED",
    "RECOVERING",
    "RunEngine",
    "RunOutcome",
    "SELECTED",
    "VALIDATED",
]
