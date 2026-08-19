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
import random
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from omda.config import Config, config_to_dict
from omda.core.album import dedupe_candidates, filter_candidates
from omda.core.genre import select_daily_genres
from omda.core.rating import rank_candidates
from omda.core.year import AlbumSelectionResult, select_albums_for_genre
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
    InvariantFailureError,
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

    ``selection_results`` exposes the observable year-constraint outcome per
    Genre (G2-004), persisted in the journal digest.
    """

    run_id: str
    genres: tuple[GenreRef, ...]
    albums: tuple[SelectedAlbum, ...]
    pick_records: tuple[GenrePickRecord, ...] = ()
    selection_results: tuple[AlbumSelectionResult, ...] = ()

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
            "album_selection": [
                {
                    "genre_id": g.genre_id,
                    "status": r.status,
                    "reason": r.reason,
                    "modern_count": r.modern_count,
                    "older_count": r.older_count,
                    "unknown_year_count": r.unknown_year_count,
                    "candidates_considered": r.candidates_considered,
                }
                for g, r in zip(self.genres, self.selection_results, strict=True)
            ]
            if self.selection_results
            else [],
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
        selection_results = tuple(
            AlbumSelectionResult(
                albums=(),
                status=entry.get("status", "normal"),
                reason=entry.get("reason", ""),
                modern_count=entry.get("modern_count", 0),
                older_count=entry.get("older_count", 0),
                unknown_year_count=entry.get("unknown_year_count", 0),
                candidates_considered=entry.get("candidates_considered", 0),
            )
            for entry in digest.get("album_selection", [])
        )
        return cls(
            run_id=run_id,
            genres=genres,
            albums=albums,
            pick_records=pick_records,
            selection_results=selection_results,
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
        seed: str | None = None,
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
        # G2-006/G2-008: the engine never holds a mutable long-lived RNG. The base
        # seed is explicit (caller argument takes precedence over Config.seed);
        # every run derives its own generator from durable provenance, so later
        # runs are reproducible across a process restart.
        self._seed = seed if seed is not None else (config.seed or "default")
        self._input_version = input_version
        self._config_version = _config_fingerprint(config)
        self._critic_rows = critic_rows or {}
        self._rating_weights = rating_weights or {}
        self._missing_policy = missing_policy

    def _run_rng(self, run_id: str) -> random.Random:
        # G2-008: per-run RNG derived only from durable provenance (base seed +
        # run id); no process-lifetime state is involved.
        return make_rng(f"{self._seed}:{run_id}")

    # -- public API ------------------------------------------------------------

    def run(self, run_id: str) -> RunOutcome:
        # G2-005: inspect durable state first — an existing run is only returned
        # in its terminal state or recovered; never a fresh plan under the same
        # idempotency key.
        entries = self._journal(run_id)
        if entries:
            last = entries[-1].transition
            if last in _TERMINAL_FAILED:
                return RunOutcome(run_id=run_id, state=last)
            if last in (HISTORY_COMMITTED, COMPLETE):
                return self._complete_durably(run_id, last)
            return self.recover(run_id)
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
            return self._complete_durably(run_id, last)
        if last in _AFTER_DELIVER:
            return self._finish_after_delivery(run_id, entries)
        # Mid-flight failure before delivery: safe to fail (history untouched).
        self._append(run_id, FAILED, {"reason": "recover from incomplete pre-delivery state"})
        return RunOutcome(run_id=run_id, state=FAILED)

    def _complete_durably(self, run_id: str, last: str) -> RunOutcome:
        """A HISTORY_COMMITTED tail gets a durable COMPLETE appended exactly once
        (G2-005); a COMPLETE tail is returned unchanged."""
        if last == HISTORY_COMMITTED:
            self._append(run_id, COMPLETE)
        return RunOutcome(run_id=run_id, state=COMPLETE)

    # -- internals --------------------------------------------------------------

    def _journal(self, run_id: str) -> list[JournalEntry]:
        return self._history.journal_after(run_id, 0)

    def _append(self, run_id: str, transition: str, detail: dict[str, Any] | None = None) -> None:
        self._history.append_journal(run_id, transition, utc_now(), detail)

    def _run_once(self, run_id: str) -> RunOutcome:
        # G2-006/G2-008: provenance records the exact per-run derivation inputs
        # (base seed + run id + input/config versions) WITHOUT consuming a draw;
        # the run generator is derived from exactly these values.
        run_rng = self._run_rng(run_id)
        self._append(
            run_id,
            PLANNED,
            {
                "seed": self._seed,
                "run_id": run_id,
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
            # G2-010: carry the source taxonomy's parent memberships and the
            # configured parent limits into the Core as set constraints.
            parents_by_genre = {g.genre_id: g.parents for g in genres}
            chosen = select_daily_genres(
                genres,
                self._config.daily_genre_count,
                run_rng,
                pick_history=pick_history,
                global_start_index=global_start,
                cooldown_picks=self._config.genre_cooldown_picks,
                parent_limits=self._config.genre_parent_limits,
                parents_by_genre=parents_by_genre,
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
        selection_results: list[AlbumSelectionResult] = []
        already_selected: list[AlbumCandidate] = []
        for genre in chosen:
            pool = filter_candidates(candidates_by_genre.get(genre.genre_id, []), exclusions)
            pool = dedupe_candidates(pool, already_selected)
            ranked = rank_candidates(
                pool, self._critic_rows, self._rating_weights, self._missing_policy
            )
            result = select_albums_for_genre(
                ranked,
                count=self._config.albums_per_genre,
                modern_year=self._config.modern_album_year,
            )
            selection_results.append(result)
            already_selected.extend(result.albums)
            for album in result.albums:
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
            selection_results=tuple(selection_results),
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

    def _receipt_matches(self, receipt: DeliveryReceipt, run_id: str, key: str) -> bool:
        """G2-009: a receipt only authorises official history for the current run
        when it is bound to the exact run id, idempotency key, configured channel
        and a successful status."""
        return (
            receipt.run_id == run_id
            and receipt.idempotency_key == key
            and receipt.channel == self._config.delivery.channel
            and receipt.status == "ok"
        )

    def _deliver_and_commit(self, run_id: str, plan: Plan, payload: str) -> RunOutcome:
        key = self._idempotency_key(run_id)
        self._append(run_id, DELIVERING, {"idempotency_key": key})
        receipt = self._delivery.deliver(payload, key)
        if not self._receipt_matches(receipt, run_id, key):
            # G2-009: an unbound receipt (wrong run/key/channel or non-ok status)
            # must fail closed WITHOUT committing official history; no receipt is
            # stored under a key it does not own.
            self._append(
                run_id,
                FAILED,
                {
                    "reason": "delivery receipt does not match run/key/channel/status",
                    "receipt_run_id": receipt.run_id,
                    "receipt_key": receipt.idempotency_key,
                    "receipt_channel": receipt.channel,
                    "receipt_status": receipt.status,
                },
            )
            return RunOutcome(run_id=run_id, state=FAILED, payload=payload)
        try:
            self._history.save_delivery_receipt(receipt)  # durable evidence first
        except InvariantFailureError as exc:
            # G2-005: a conflicting receipt must fail closed — original evidence
            # stays intact, never overwritten, and no history is written.
            self._append(
                run_id,
                FAILED,
                {"reason": "delivery receipt conflict", "message": str(exc)},
            )
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
        key = self._idempotency_key(run_id)
        receipt = self._history.find_delivery_receipt(key)
        if receipt is None or not self._receipt_matches(receipt, run_id, key):
            # G2-009: missing OR unbound evidence -> do NOT re-push; fail closed
            # for human review; no official history mutation.
            self._append(run_id, RECOVERING, {"reason": "delivery evidence missing or mismatched"})
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
