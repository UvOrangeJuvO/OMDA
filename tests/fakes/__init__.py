"""Shared fake/in-memory implementations of Port contracts (T1.4, used by G2).

These fakes are contract fixtures, not production code: they satisfy the Port
shapes so Orchestrator and contract tests run without live RYM/MusicBrainz/
LLM/PushPlus (SPEC §3.2: tests use fixtures/fakes for ordinary CI).

Semantics must match the SQLite adapter exactly — especially all-or-nothing
``commit_history`` (G1-001) and immutable delivery receipts (G1-002).
"""

from __future__ import annotations

from omda.ports.domain import (
    OP_AMBIGUOUS,
    OP_CONFIRMED_FAILED,
    OP_IN_FLIGHT_OR_MAY_HAVE_SENT,
    OP_RESOLVED_DELIVERED,
    OP_RESOLVED_NOT_DELIVERED,
    OP_SUCCEEDED,
    RESOLUTION_CONFIRMED_DELIVERED,
    RESOLUTION_CONFIRMED_NOT_DELIVERED,
    AlbumCandidate,
    AlbumIdentity,
    DeliveryAttempt,
    DeliveryOperation,
    DeliveryOperationSnapshot,
    DeliveryReceipt,
    GenrePickRecord,
    GenreRef,
    JournalEntry,
)
from omda.ports.errors import InvariantFailureError
from omda.ports.source import (
    BATCH_SCHEMA_VERSION,
    AlbumCandidateRecord,
    CandidateBatch,
    SourceDescriptor,
    digest_batch,
)


class InMemoryHistory:
    """In-memory HistoryPort for tests: journal, picks, albums, receipts."""

    def __init__(self) -> None:
        self._journal: list[JournalEntry] = []
        self._next_journal_id = 1
        self._picks: list[GenrePickRecord] = []
        self._albums: dict[str, AlbumIdentity] = {}
        self._receipts: dict[str, DeliveryReceipt] = {}
        self._operations: dict[str, DeliveryOperation] = {}
        self._attempts: list[DeliveryAttempt] = []
        self._resolutions: list[dict] = []

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
        return max((p.pick_index for p in self._picks), default=0)

    def cooldown_pick_indices(self, genre_id: str) -> list[int]:
        return [p.pick_index for p in self._picks if p.genre_id == genre_id]

    def excluded_album_identities(self) -> frozenset[AlbumIdentity]:
        return frozenset(self._albums.values())

    def commit_history(
        self,
        run_id: str,
        genre_picks: list[GenrePickRecord],
        album_identities: list[AlbumIdentity],
        committed_at: str,
    ) -> None:
        # All-or-nothing (G1-001/G1-005): full pre-check against the incoming
        # batch AND the current state; only if every row is valid do we mutate.
        # Invariant conflicts raise the same domain exception as the SQLite
        # adapter (InvariantFailureError) — never a provider-specific type.
        seen_picks: set[int] = set()
        for pick in genre_picks:
            if pick.pick_index in seen_picks:
                raise InvariantFailureError(
                    f"duplicate pick_index {pick.pick_index} within commit batch"
                )
            seen_picks.add(pick.pick_index)
            if any(p.pick_index == pick.pick_index for p in self._picks):
                raise InvariantFailureError(
                    f"pick_index {pick.pick_index} already in official history"
                )
        seen_albums: set[str] = set()
        for identity in album_identities:
            if identity.album_id in seen_albums:
                raise InvariantFailureError(
                    f"duplicate album_id {identity.album_id!r} within commit batch"
                )
            seen_albums.add(identity.album_id)
            if identity.album_id in self._albums:
                raise InvariantFailureError(
                    f"album {identity.album_id!r} already in official history"
                )
        self._picks.extend(genre_picks)
        for identity in album_identities:
            self._albums[identity.album_id] = identity
        self.append_journal(
            run_id,
            "HISTORY_COMMITTED",
            committed_at,
            {"picks": len(genre_picks), "albums": len(album_identities)},
        )

    def save_delivery_receipt(self, receipt: DeliveryReceipt) -> DeliveryReceipt:
        existing = self._receipts.get(receipt.idempotency_key)
        if existing is None:
            self._receipts[receipt.idempotency_key] = receipt
            return receipt
        if existing == receipt:
            return existing  # exact replay: no-op
        raise InvariantFailureError(
            f"delivery receipt conflict for key {receipt.idempotency_key!r}; "
            "evidence is immutable (G1-002)"
        )

    def find_delivery_receipt(self, idempotency_key: str) -> DeliveryReceipt | None:
        return self._receipts.get(idempotency_key)

    # -- delivery operations (ADR-0001 v2; semantics mirror SqliteHistory) -----

    def begin_delivery_operation(
        self,
        *,
        run_id: str,
        idempotency_key: str,
        channel: str,
        payload_digest: str,
    ) -> DeliveryOperationSnapshot:
        existing = self._operations.get(idempotency_key)
        if existing is not None:
            return DeliveryOperationSnapshot(created=False, operation=existing)
        operation = DeliveryOperation(
            idempotency_key=idempotency_key,
            run_id=run_id,
            channel=channel,
            payload_digest=payload_digest,
            state=OP_IN_FLIGHT_OR_MAY_HAVE_SENT,
            version=1,
            created_at="2026-08-21T00:00:00Z",
        )
        self._operations[idempotency_key] = operation
        self.append_journal(
            run_id,
            "DELIVERING",
            operation.created_at,
            {"idempotency_key": idempotency_key, "payload_digest": payload_digest},
        )
        return DeliveryOperationSnapshot(created=True, operation=operation)

    def finalize_delivery_attempt(
        self,
        *,
        operation_key: str,
        expected_version: int,
        outcome: str,
        evidence: str,
        attempted_at: str,
    ) -> DeliveryOperation:
        op = self._operations.get(operation_key)
        if op is None:
            raise InvariantFailureError(f"no delivery operation for key {operation_key!r}")
        if op.version != expected_version:
            raise InvariantFailureError(
                f"delivery operation version mismatch for {operation_key!r}"
            )
        if operation_key in self._receipts:
            raise InvariantFailureError(
                f"delivery receipt already exists for key {operation_key!r}"
            )
        state = {
            "ok": OP_SUCCEEDED,
            "failed": OP_CONFIRMED_FAILED,
            "ambiguous": OP_AMBIGUOUS,
        }[outcome]
        seq = sum(1 for a in self._attempts if a.operation_key == operation_key) + 1
        self._attempts.append(
            DeliveryAttempt(
                attempt_id=f"{operation_key}#{seq}",
                operation_key=operation_key,
                outcome=outcome,
                evidence=evidence,
                attempted_at=attempted_at,
            )
        )
        self._receipts[operation_key] = DeliveryReceipt(
            run_id=op.run_id,
            idempotency_key=operation_key,
            delivered_at=attempted_at,
            channel=op.channel,
            status=outcome,
            target=evidence,
            attempt_id=f"{operation_key}#{seq}",
        )
        updated = DeliveryOperation(
            idempotency_key=op.idempotency_key,
            run_id=op.run_id,
            channel=op.channel,
            payload_digest=op.payload_digest,
            state=state,
            version=op.version + 1,
            created_at=op.created_at,
        )
        self._operations[operation_key] = updated
        return updated

    def record_delivery_resolution(
        self,
        *,
        operation_key: str,
        run_id: str,
        idempotency_key: str,
        attempt_id: str | None,
        outcome: str,
        actor: str,
        reason: str,
        decided_at: str,
    ) -> DeliveryOperation:
        op = self._operations.get(operation_key)
        if op is None:
            raise InvariantFailureError(f"no delivery operation for key {operation_key!r}")
        # G4-002B (§15-5): redundant fields must bind to the SAME operation.
        if op.run_id != run_id:
            raise InvariantFailureError(
                f"resolution run_id {run_id!r} does not match operation {operation_key!r}"
            )
        if idempotency_key != operation_key:
            raise InvariantFailureError(
                f"resolution idempotency_key {idempotency_key!r} does not match "
                f"operation_key {operation_key!r}"
            )
        if attempt_id is not None and not any(
            a.attempt_id == attempt_id and a.operation_key == operation_key
            for a in self._attempts
        ):
            raise InvariantFailureError(
                f"resolution attempt_id {attempt_id!r} does not belong to "
                f"operation {operation_key!r}"
            )
        self._resolutions.append(
            {
                "operation_key": operation_key,
                "run_id": run_id,
                "idempotency_key": idempotency_key,
                "attempt_id": attempt_id,
                "outcome": outcome,
                "actor": actor,
                "reason": reason,
                "decided_at": decided_at,
            }
        )
        new_state = {
            RESOLUTION_CONFIRMED_DELIVERED: OP_RESOLVED_DELIVERED,
            RESOLUTION_CONFIRMED_NOT_DELIVERED: OP_RESOLVED_NOT_DELIVERED,
        }.get(outcome)
        if new_state is None:  # STILL_UNKNOWN: record appended, state stays blocked
            return op
        if op.state not in (OP_IN_FLIGHT_OR_MAY_HAVE_SENT, OP_AMBIGUOUS):
            raise InvariantFailureError(
                f"resolution cannot advance operation {operation_key!r} "
                "from its current state (evidence immutable)"
            )
        updated = DeliveryOperation(
            idempotency_key=op.idempotency_key,
            run_id=op.run_id,
            channel=op.channel,
            payload_digest=op.payload_digest,
            state=new_state,
            version=op.version + 1,
            created_at=op.created_at,
        )
        self._operations[operation_key] = updated
        return updated

    def find_delivery_operation(self, idempotency_key: str) -> DeliveryOperation | None:
        return self._operations.get(idempotency_key)

    # -- test-only helpers (not part of HistoryPort) ---------------------------

    def record_pick_directly(self, pick_index: int, genre_id: str) -> None:
        """Seed a historical committed pick (test fixture convenience)."""
        self._picks.append(GenrePickRecord(pick_index, genre_id))


class FakeGenreSource:
    def __init__(self, genres: list[GenreRef] | None = None) -> None:
        self._genres = genres if genres is not None else []

    def list_eligible_genres(self) -> list[GenreRef]:
        return [g for g in self._genres if g.eligible]


class FakeAlbumSource:
    """Contract-parity fake: candidates_for_genre + provider-neutral source_batch.

    ``source_batch`` returns a digest-bound CandidateBatch for the requested
    Genre (G3-007-004), so the trusted boundary can assemble a
    ValidatedSourceSet without importing a concrete adapter.
    """

    def __init__(self, by_genre: dict[str, list[AlbumCandidate]] | None = None) -> None:
        self._by_genre = by_genre or {}

    def candidates_for_genre(
        self, genre: GenreRef, limit: int | None = None
    ) -> list[AlbumCandidate]:
        found = self._by_genre.get(genre.genre_id, [])
        return found[:limit] if limit is not None else list(found)

    def source_batch(self, genre: GenreRef) -> CandidateBatch:
        found = self._by_genre.get(genre.genre_id, [])
        records = tuple(
            AlbumCandidateRecord(
                album_id=c.album_id,
                genre_id=genre.genre_id,
                title=c.title,
                artist=c.artist,
                year=c.year,
                mbid=c.identity.canonical_id if c.identity else None,
            )
            for c in found
        )
        source = SourceDescriptor(
            source_id="fake",
            kind="album",
            display_name="Fake Albums",
            license="CC0-1.0 (fake)",
            origin_url="https://fake.example/albums",
            retrieved_at="2026-08-22T00:00:00+00:00",
            dataset_version="1",
            schema_version="1",
            data_scope="fake",
            records_file="albums.jsonl",
            demo=False,
            data_derivation="independently_curated",
            upstream_license="none",
            license_core_facts="CC0-1.0",
            license_supplementary_used="none",
            license_service_terms="n/a",
            license_derived_package="CC0-1.0",
        )
        batch = CandidateBatch(
            schema_version=BATCH_SCHEMA_VERSION,
            query_policy_version="1",
            genre_id=genre.genre_id,
            source=source,
            digest="",
            candidates=records,
        )
        from dataclasses import replace

        return replace(batch, digest=digest_batch(batch))


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

    def generate_narrative(
        self,
        fact_packet: dict,
        *,
        expected_genres: int | None = None,
        expected_albums: int | None = None,
    ) -> str:
        return self._text


class FakeDelivery:
    """Records deliveries; same idempotency key never delivers twice.

    ``calls`` counts deliver() invocations; ``delivered`` maps only the keys that
    produced a real external side effect — recovery must never increment
    ``delivered`` for an already-delivered run (G2-005).
    """

    def __init__(self) -> None:
        self.delivered: dict[str, str] = {}
        self.calls = 0

    def deliver(
        self,
        payload: str,
        idempotency_key: str,
        target: str | None = None,
    ) -> DeliveryReceipt:
        self.calls += 1
        # The idempotency key is "{run_id}:{channel}"; the receipt must bind to
        # the same run and channel (G2-009) so the Orchestrator can trust it.
        run_id, _, channel = idempotency_key.partition(":")
        if idempotency_key in self.delivered:
            # Replay of the same key: no second external delivery (SPEC §4).
            return DeliveryReceipt(
                run_id=run_id,
                idempotency_key=idempotency_key,
                delivered_at="2026-08-19T00:00:00+00:00",
                channel=channel or "markdown",
                status="ok",
                target=target,
            )
        self.delivered[idempotency_key] = payload
        return DeliveryReceipt(
            run_id=run_id,
            idempotency_key=idempotency_key,
            delivered_at="2026-08-19T00:00:00+00:00",
            channel=channel or "markdown",
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
