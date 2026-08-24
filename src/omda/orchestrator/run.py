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

# G4-004R: the REAL engine and the recovery helper share ONE decision path.
from omda.orchestrator.recovery import (
    COMMIT_HISTORY,
    COMPLETE_ALREADY,
    resolve_recovery_action,
)
from omda.output.markdown import (
    build_report_data,
    render_markdown,
    validate_markdown,
)
from omda.ports.album import AlbumSource
from omda.ports.critic import CriticRatingRow
from omda.ports.delivery import Delivery
from omda.ports.domain import (
    OP_CONFIRMED_FAILED,
    OP_RESOLVED_DELIVERED,
    OP_RESOLVED_NOT_DELIVERED,
    OP_SUCCEEDED,
    AlbumCandidate,
    AlbumIdentity,
    DeliveryOperation,
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
    InvalidInputError,
    InvariantFailureError,
    SourceUnavailableError,
    StateCommitFailureError,
    ValidationFailureError,
)
from omda.ports.genre import GenreSource
from omda.ports.history import HistoryPort
from omda.ports.llm import LLM
from omda.ports.source import (
    ValidatedSourceSet,
    assemble_validated_source_set,
)
from omda.seed import make_rng

MAX_PAYLOAD_LENGTH = 4000
MAX_RUN_ATTEMPTS = 2
# G4-008: bounded archival length for the LLM narrative in the GENERATED entry.
NARRATIVE_ARCHIVE_LENGTH = 1500

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
        source_registry: Any = None,
    ) -> None:
        self._config = config
        self._history = history
        self._genre_source = genre_source
        self._album_source = album_source
        self._llm = llm
        self._delivery = delivery
        # ADR-0002 §8-4: the reviewed source registry is the trust anchor. When
        # wired (the PRODUCTION path), every run assembles and validates a
        # ValidatedSourceSet AFTER fetch and BEFORE selection/delivery claim.
        self._source_registry = source_registry
        # ADR-0002 D8: v0.1 is a deterministic/no-LLM runtime — config only
        # permits llm.mode == "deterministic" (provider fails closed in config
        # validation); the engine therefore never calls an external LLM.
        self._llm_mode = config.llm.mode if config.llm is not None else "deterministic"
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

            # FETCH: candidates per genre. On the PRODUCTION path (a reviewed
            # source registry is wired) the trusted application boundary
            # assembles and validates a ValidatedSourceSet AFTER fetch and
            # BEFORE selection/delivery claim (ADR-0002 §8.4): every Genre
            # descriptor and Album batch must match the reviewed registry, and
            # the selected Genre IDs must belong to the digest-bound eligible
            # set. The FETCHED journal records the source evidence (§8.8) so
            # outbound facts and committed MBIDs trace to the same validated
            # source set.
            if self._source_registry is not None:
                genre_descriptors = (self._genre_source.descriptor(),)
                batches = tuple(self._album_source.source_batch(genre) for genre in chosen)
                try:
                    validated = assemble_validated_source_set(
                        self._source_registry,
                        genre_descriptors=genre_descriptors,
                        batches=batches,
                        selected_genre_ids=tuple(g.genre_id for g in chosen),
                        required_candidates_per_genre=self._config.albums_per_genre,
                    )
                except InvalidInputError as exc:
                    # G4-007B / ADR-0002 §8.4: sample/demo/missing/forged sources
                    # fail closed BEFORE selection, delivery claim or any
                    # history mutation — never substituted with unrelated data.
                    self._append(
                        run_id,
                        FAILED,
                        {
                            "reason": "validated source set rejected",
                            "message": str(exc),
                        },
                    )
                    return RunOutcome(run_id=run_id, state=FAILED)
                if validated.is_demo:
                    # ADR-0002 D6/§8-2: a demo Genre or demo Album batch can
                    # never reach external delivery — the production gate
                    # rejects it here (the illustrative rym-sample package is
                    # demo and must be refused on --deliver).
                    self._append(
                        run_id,
                        FAILED,
                        {
                            "reason": "demo source set rejected for external delivery",
                            "source_set_is_demo": True,
                        },
                    )
                    return RunOutcome(run_id=run_id, state=FAILED)
                self._append(run_id, FETCHED, _source_evidence(validated))
                candidates_by_genre = _candidates_from_validated(validated)
            else:
                # Fixture path (no registry): the provider-neutral envelope is
                # still used; selection data comes from the adapter as before.
                candidates_by_genre = {
                    genre.genre_id: self._album_source.candidates_for_genre(genre)
                    for genre in chosen
                }
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
            payload = self._generate(plan)  # appends GENERATED with the narrative
            self._validate_payload(payload, plan)
            self._append(run_id, VALIDATED)

            # DELIVER with stable idempotency key; persist receipt first.
            return self._deliver_and_commit(run_id, plan, payload)
        except (SourceUnavailableError, InsufficientCandidatesError, InvalidInputError) as exc:
            # InvalidInputError covers source-side rejection on the production
            # path (e.g. a Genre whose curated package has no batch) — it must
            # surface as an explicit FAILED run, never an unclassified crash,
            # and never a history mutation (G1-001).
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
        # ADR-0002 D8 / §8-10 / AC-8: v0.1 is a DETERMINISTIC (no-LLM) runtime.
        # No external LLM is ever called; the GENERATED journal records a TYPED
        # deterministic marker (never a fabricated narrative sentence), and the
        # delivered payload is the deterministic fact report (G4-005 mechanical
        # contract: no free-text slot, so an off-packet Album/Genre reference
        # can never be delivered). A future provider mode requires its own
        # implemented adapter, versioned config and Gate acceptance — it is not
        # part of v0.1.
        if self._llm_mode == "deterministic":
            self._append(
                plan.run_id,
                GENERATED,
                {"narrative_mode": "deterministic"},
            )
            return render_markdown(self._report_data(plan))
        # Unreachable in v0.1 (config fails closed on provider mode); retained
        # only as the documented future-provider seam.
        packet = FactPacket(run_id=plan.run_id, plan=plan)
        try:
            narrative = self._llm.generate_narrative(
                _packet_dict(packet),
                expected_genres=len(plan.genres),
                expected_albums=len(plan.albums),
            )
        except DomainError:
            raise
        except Exception as exc:  # provider-side generation failure
            raise GenerationFailureError(f"narrative generation failed: {exc}") from exc
        self._append(
            plan.run_id,
            GENERATED,
            {"narrative": (narrative or "")[:NARRATIVE_ARCHIVE_LENGTH]},
        )
        return render_markdown(self._report_data(plan))

    def _validate_payload(self, payload: str, plan: Plan) -> None:
        # G4-001: full structure/length/fact-reference validation of the
        # rendered report BEFORE any delivery (SPEC §8, T4.2). A payload that
        # fails this never reaches the Delivery Port.
        validate_markdown(payload, self._report_data(plan))

    def _report_data(self, plan: Plan):
        """Plain report facts from the selected plan (leaf data for Markdown)."""
        return build_report_data(
            run_id=plan.run_id,
            genres=[
                {"genre_id": g.genre_id, "name": g.name} for g in plan.genres
            ],
            albums=[
                {
                    "album_id": a.album_id,
                    "genre_id": a.genre_id,
                    "title": a.title,
                    "artist": a.artist,
                    "year": a.year,
                }
                for a in plan.albums
            ],
        )

    def _idempotency_key(self, run_id: str) -> str:
        return f"{run_id}:{self._config.delivery.channel}"

    def _receipt_matches(self, receipt: DeliveryReceipt, run_id: str, key: str) -> bool:
        """G2-009: a receipt only authorises official history for the current run
        when it is bound to the exact run id, idempotency key and configured
        channel. Success status is checked separately (G2-012)."""
        return (
            receipt.run_id == run_id
            and receipt.idempotency_key == key
            and receipt.channel == self._config.delivery.channel
        )

    def _deliver_and_commit(self, run_id: str, plan: Plan, payload: str) -> RunOutcome:
        key = self._idempotency_key(run_id)
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        # ADR-0001 v2: the atomic claim is persisted (with the DELIVERING
        # journal entry) BEFORE any network call. An existing operation row
        # blocks every other automatic caller (at-most-one outbound request).
        try:
            snapshot = self._history.begin_delivery_operation(
                run_id=run_id,
                idempotency_key=key,
                channel=self._config.delivery.channel,
                payload_digest=digest,
            )
        except (StateCommitFailureError, InvariantFailureError) as exc:
            self._append(
                run_id,
                RECOVERING,
                {"reason": "delivery claim failed", "message": str(exc)},
            )
            return RunOutcome(run_id=run_id, state=RECOVERING, plan=plan, payload=payload)
        if not snapshot.created:
            return self._existing_operation_outcome(
                run_id, plan, payload, snapshot.operation, digest
            )

        # Won the claim: perform the (single) external call.
        receipt = self._delivery.deliver(payload, key)
        # G2-012/ADR-0001: a receipt that does not bind to this run/key/channel
        # cannot confirm anything about the CURRENT operation — even an "ok"
        # status for another operation is malformed evidence. The external call
        # DID happen, so the attempt is recorded as AMBIGUOUS (never re-push,
        # never commit history), and only a bound receipt's status is trusted.
        bound = self._receipt_matches(receipt, run_id, key)
        outcome = receipt.status if bound else "ambiguous"
        if outcome not in ("ok", "failed", "ambiguous"):
            outcome = "ambiguous"  # unknown/pending/empty -> ambiguous (G2-012)
        try:
            self._history.finalize_delivery_attempt(
                operation_key=key,
                expected_version=snapshot.operation.version,
                outcome=outcome,
                evidence=receipt.target or "",
                attempted_at=receipt.delivered_at,
            )
        except (StateCommitFailureError, InvariantFailureError) as exc:
            # The external call MAY have happened and the evidence write failed
            # -> ambiguous; never an ordinary terminal failure (G2-012).
            self._append(
                run_id,
                RECOVERING,
                {"reason": "delivery finalize failed after external call", "message": str(exc)},
            )
            return RunOutcome(
                run_id=run_id, state=RECOVERING, plan=plan, payload=payload, receipt=receipt
            )
        if not bound:
            self._append(
                run_id,
                RECOVERING,
                {
                    "reason": "delivery receipt does not match run/key/channel",
                    "receipt_run_id": receipt.run_id,
                    "receipt_key": receipt.idempotency_key,
                    "receipt_channel": receipt.channel,
                    "receipt_status": receipt.status,
                },
            )
            return RunOutcome(
                run_id=run_id, state=RECOVERING, plan=plan, payload=payload, receipt=receipt
            )
        if receipt.status == "failed":
            # Correctly bound AND exactly "failed": a confirmed delivery failure
            # for the CURRENT operation is an ordinary terminal failure.
            self._append(
                run_id,
                FAILED,
                {
                    "reason": "delivery reported failure",
                    "receipt_status": receipt.status,
                },
            )
            return RunOutcome(run_id=run_id, state=FAILED, payload=payload)
        if receipt.status != "ok":
            # ambiguous (or any non-ok value): the adapter never confirmed
            # success or failure -> preserve the anomaly and enter RECOVERING.
            self._append(
                run_id,
                RECOVERING,
                {
                    "reason": "delivery receipt has unrecognized status",
                    "receipt_status": receipt.status,
                },
            )
            return RunOutcome(
                run_id=run_id, state=RECOVERING, plan=plan, payload=payload, receipt=receipt
            )
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

    def _existing_operation_outcome(
        self,
        run_id: str,
        plan: Plan,
        payload: str,
        operation: DeliveryOperation,
        digest: str,
    ) -> RunOutcome:
        """Handle a replay/concurrent call whose operation row already exists.

        Per ADR-0001 §5/§15-1 the transport is NEVER called again: the state
        table decides the outcome. A digest mismatch fails closed (no network).
        """
        if operation.payload_digest != digest:
            # §15-5: the same key cannot be replayed with different content.
            self._append(
                run_id,
                RECOVERING,
                {
                    "reason": "idempotency key replay with different payload digest",
                    "stored_digest": operation.payload_digest,
                },
            )
            return RunOutcome(run_id=run_id, state=RECOVERING, plan=plan, payload=payload)
        state = operation.state
        if state in (OP_SUCCEEDED, OP_RESOLVED_DELIVERED):
            # Delivered-but-not-committed (or human-confirmed delivered):
            # commit local history, NEVER re-push.
            try:
                self._commit_history(run_id, plan)
            except StateCommitFailureError:
                self._append(
                    run_id, RECOVERING, {"reason": "history commit failed after delivery"}
                )
                return RunOutcome(run_id=run_id, state=RECOVERING, plan=plan, payload=payload)
            self._append(run_id, COMPLETE)
            return RunOutcome(run_id=run_id, state=COMPLETE, plan=plan, payload=payload)
        if state in (OP_CONFIRMED_FAILED, OP_RESOLVED_NOT_DELIVERED):
            # Confirmed not delivered: terminal failure, no re-send, no history.
            self._append(
                run_id,
                FAILED,
                {"reason": "delivery confirmed not delivered", "operation_state": state},
            )
            return RunOutcome(run_id=run_id, state=FAILED, plan=plan, payload=payload)
        # IN_FLIGHT_OR_MAY_HAVE_SENT or AMBIGUOUS: never auto-resume (the claim
        # was committed before the call, so the call MAY have happened) -> the
        # conservative protocol requires human review (ADR-0001 §15-2).
        # Idempotent (G2-012): unchanged evidence never grows the journal.
        entries = self._journal(run_id)
        if entries and entries[-1].transition == RECOVERING:
            return RunOutcome(run_id=run_id, state=RECOVERING, plan=plan, payload=payload)
        self._append(
            run_id,
            RECOVERING,
            {
                "reason": "existing delivery operation is in-flight/ambiguous; human required",
                "operation_state": state,
            },
        )
        return RunOutcome(run_id=run_id, state=RECOVERING, plan=plan, payload=payload)

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
        # Rebuild the plan from durable journal evidence, then let the SINGLE
        # production recovery decision (resolve_recovery_action) decide the
        # action — the decision helper and the real engine can never diverge
        # (G4-004R). Only a delivered operation (SUCCEEDED or the human-confirmed
        # RESOLVED_DELIVERED) may commit history; nothing is ever re-pushed.
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
        decision = resolve_recovery_action(self._history, run_id, idempotency_key=key)
        if decision.action == COMMIT_HISTORY:
            try:
                self._commit_history(run_id, plan)
            except StateCommitFailureError:
                # Idempotent: unchanged failing evidence does not grow the journal.
                if entries[-1].transition == RECOVERING:
                    return RunOutcome(run_id=run_id, state=RECOVERING, plan=plan)
                self._append(run_id, RECOVERING, {"reason": "history commit still failing"})
                return RunOutcome(run_id=run_id, state=RECOVERING, plan=plan)
            self._append(run_id, COMPLETE)
            return RunOutcome(
                run_id=run_id,
                state=COMPLETE,
                plan=plan,
                receipt=decision.receipt,
            )
        if decision.action == COMPLETE_ALREADY:
            return RunOutcome(run_id=run_id, state=COMPLETE, plan=plan)
        # REQUIRE_HUMAN (missing/mismatched/in-flight/ambiguous evidence or a
        # confirmed-not-delivered operation): fail closed, never re-push, and
        # keep the journal bounded under retries (G2-012).
        if entries[-1].transition == RECOVERING:
            return RunOutcome(run_id=run_id, state=RECOVERING, plan=plan)
        self._append(run_id, RECOVERING, {"reason": decision.reason})
        return RunOutcome(run_id=run_id, state=RECOVERING, plan=plan)


def _packet_dict(packet: FactPacket) -> dict[str, Any]:
    return {
        "run_id": packet.run_id,
        "genres": [{"genre_id": g.genre_id, "name": g.name} for g in packet.plan.genres],
        "albums": [
            {"album_id": a.album_id, "title": a.title, "artist": a.artist, "year": a.year}
            for a in packet.plan.albums
        ],
    }


def _source_evidence(validated: ValidatedSourceSet) -> dict[str, Any]:
    """ADR-0002 §8.8: journal the validated Genre/Album source evidence.

    Records the source IDs, content/batch digests, schema/query-policy/package
    versions and demo flags of the validated source set, so outbound facts and
    committed MBIDs can be traced back to the SAME ValidatedSourceSet.
    """
    return {
        "source_evidence": {
            "genres": [
                {
                    "source_id": d.source_id,
                    "content_digest": d.content_digest,
                    "eligible_digest": d.eligible_digest,
                    "schema_version": d.schema_version,
                    "package_version": d.dataset_version,
                    "demo": d.demo,
                }
                for d in validated.genre_descriptors
            ],
            "albums": [
                {
                    "source_id": b.source.source_id,
                    "batch_digest": b.digest,
                    "genre_id": b.genre_id,
                    "schema_version": b.schema_version,
                    "query_policy_version": b.query_policy_version,
                    "package_version": b.source.dataset_version,
                    "demo": b.source.demo,
                }
                for b in validated.batches
            ],
            "selected_genre_ids": sorted(b.genre_id for b in validated.batches),
        }
    }


def _candidates_from_validated(
    validated: ValidatedSourceSet,
) -> dict[str, list[AlbumCandidate]]:
    """Derive the SELECT input strictly from the VALIDATED source set.

    The candidates come from the digest-bound batches that already passed
    registry + content validation (ADR-0002 §8.4), so selection can never
    consume unvalidated or substituted records on the production path.
    """
    by_genre: dict[str, list[AlbumCandidate]] = {}
    for batch in validated.batches:
        by_genre[batch.genre_id] = [
            AlbumCandidate(
                album_id=record.album_id,
                title=record.title,
                artist=record.artist,
                year=record.year,
                genres=(record.genre_id,),
                identity=_identity_for_record(record),
            )
            for record in batch.candidates
        ]
    return by_genre


def _identity_for_record(record) -> AlbumIdentity | None:
    """Canonical release-group identity from a validated batch record (G3-007-002).

    Mirrors ``CuratedAlbumSource`` identity semantics: a production record's
    verified MusicBrainz MBID becomes the permanent-exclusion identity.
    """
    if not record.mbid:
        return None
    return AlbumIdentity(
        album_id=record.album_id,
        canonical_id=record.mbid,
        canonical_source="musicbrainz",
        identity_confidence="exact",
    )


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
