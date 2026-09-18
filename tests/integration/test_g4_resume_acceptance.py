"""ADR-0002 §5 acceptance (AC-1..AC-8, AC-9A) — G4 resume (G4-007B/002C/007C/
002D/002E, D8 deterministic runtime).

Every test uses the REAL curated packages + reviewed registry + fake network
boundaries — no live PushPlus/LLM/MusicBrainz. AC-9B stays conditional on the
undecided ODP-1 live-search path and is NOT implemented here (ADR-0002 §8-1).
"""

from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import replace
from pathlib import Path

import pytest
from tests.fakes import InMemoryHistory

from omda.adapters.curated import CuratedAlbumSource
from omda.adapters.datasets import GenreDatasetAdapter
from omda.adapters.delivery import AmbiguousFailure, ProviderSuccess
from omda.config import Config, LLMConfig, load_config
from omda.orchestrator.run import COMPLETE, FAILED
from omda.ports.domain import GenreRef
from omda.ports.errors import (
    DeliveryFailureError,
    InvariantFailureError,
    SourceUnavailableError,
)
from omda.ports.source import (
    BATCH_SCHEMA_VERSION,
    QUERY_POLICY_VERSION,
    CandidateBatch,
    GenreSourceDescriptor,
    digest_genre_ids,
)
from omda.production import (
    DEFAULT_DATA_DIR,
    build_curated_sources,
    build_production_engine,
)
from omda.sources.registry import RegistryEntry, SourceRegistry
from omda.storage import SqliteHistory

GENRES = DEFAULT_DATA_DIR / "genres" / "curated-omda"
ALBUMS = DEFAULT_DATA_DIR / "albums" / "curated-omda"
DEMO_GENRES = DEFAULT_DATA_DIR / "genres" / "demo-omda"
REGISTRY = DEFAULT_DATA_DIR / "sources" / "registry.jsonl"


def _registry() -> SourceRegistry:
    return SourceRegistry.load(REGISTRY)


def _pushplus_config(tmp_path: Path, token_env: str = "OMDA_PP_TOKEN") -> Path:
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps({"delivery": {"channel": "pushplus", "pushplus_token_env": token_env}}),
        encoding="utf-8",
    )
    return path


class _FakeTransport:
    def __init__(self, *script):
        self.script = list(script)
        self.calls = 0
        self.last_payload = None

    def post(self, url: str, payload: dict) -> ProviderSuccess:
        self.calls += 1
        self.last_payload = payload
        step = self.script[min(self.calls - 1, len(self.script) - 1)]
        if isinstance(step, Exception):
            raise step
        return step


# --- AC-1 (G4-007B positive): real curated 3x3 through the public entry -------


def test_ac1_public_cli_deliver_real_curated_3x3_traces_mbids(monkeypatch, tmp_path) -> None:
    # The PUBLIC --deliver route uses ONLY the reviewed non-demo curated source
    # set: the run completes with exactly one external call, the outbound
    # payload contains real curated facts (never sample markers), and official
    # history commits 9 production canonical MBIDs from the same source.
    import os

    from omda import cli

    os.environ["OMDA_PP_TOKEN"] = "ac1-token"
    try:
        fake = _FakeTransport(ProviderSuccess({"code": 200}))
        monkeypatch.setattr(cli, "_pushplus_transport", lambda: fake)
        db = tmp_path / "runtime-ac1.sqlite3"
        code = cli.main(
            [
                "--deliver",
                "--config",
                str(_pushplus_config(tmp_path)),
                "--run-id",
                "ac1",
                "--history",
                str(db),
            ]
        )
        assert code == 0  # COMPLETE
        assert fake.calls == 1
        # Outbound facts come from the curated package, never the sample source.
        assert fake.last_payload["content"].startswith("# 每日音乐发现")
        assert "Sample Artist" not in fake.last_payload["content"]
        # Official history: 9 committed identities, each a production MBID.
        store = SqliteHistory(db)
        try:
            ids = store.excluded_album_identities()
            assert len(ids) == 9
            for identity in ids:
                assert identity.canonical_id and len(identity.canonical_id) == 36
                assert identity.canonical_source == "musicbrainz"
        finally:
            store.close()
    finally:
        os.environ.pop("OMDA_PP_TOKEN", None)


def test_ac1_outbound_facts_and_committed_mbids_belong_to_validated_batch(
    tmp_path, monkeypatch
) -> None:
    # AC-1 / ADR2-006: every outbound Album fact and the committed identity are
    # bound to the SAME digest-bound CandidateBatch of the validated source set;
    # the FETCHED journal records the source evidence (ADR-0002 §8.8).
    import os

    os.environ["OMDA_PP_TOKEN"] = "ac1b-token"
    try:
        genre_source, album_source, registry = build_curated_sources()
        config = load_config(_pushplus_config(tmp_path))
        db = tmp_path / "runtime-ac1b.sqlite3"
        history = SqliteHistory(db)
        try:
            transport = _FakeTransport(ProviderSuccess({"code": 200}))
            engine = build_production_engine(
                config=config,
                history=history,
                genre_source=genre_source,
                album_source=album_source,
                transport=transport,
                source_registry=registry,
                token_env="OMDA_PP_TOKEN",
                seed="ac1b",
            )
            outcome = engine.run("ac1b")
            assert outcome.state == COMPLETE
            plan = outcome.plan
            assert plan is not None and len(plan.albums) == 9
            # Trace: each selected album's facts + canonical MBID come from the
            # curated batch for its Genre (the same batch that passed assembly).
            for album in plan.albums:
                batch = album_source.source_batch(
                    GenreRef(album.genre_id, album.genre_id, "", eligible=True)
                )
                record = next(
                    r for r in batch.candidates if r.album_id == album.album_id
                )
                assert record.title == album.title
                assert record.artist == album.artist
                assert record.year == album.year
                assert record.mbid == album.canonical_id
                assert album.canonical_source == "musicbrainz"
            # §8-8: the FETCHED journal carries the validated source evidence.
            fetched = next(
                e
                for e in history.journal_after("ac1b", 0)
                if e.transition == "FETCHED"
            )
            evidence = fetched.detail["source_evidence"]
            assert len(evidence["albums"]) == 3  # the three selected genres
            for album_ev in evidence["albums"]:
                assert album_ev["batch_digest"] and len(album_ev["batch_digest"]) == 64
                assert album_ev["schema_version"] == BATCH_SCHEMA_VERSION
                assert album_ev["query_policy_version"] == QUERY_POLICY_VERSION
                assert album_ev["demo"] is False
            assert evidence["genres"] and all(
                g["content_digest"] and g["eligible_digest"] and g["demo"] is False
                for g in evidence["genres"]
            )
        finally:
            history.close()
    finally:
        os.environ.pop("OMDA_PP_TOKEN", None)


# --- AC-2 (G4-007B negative): sample/demo/missing/forged fail closed ----------


def test_ac2_unregistered_demo_genre_rejected_for_external_delivery(
    tmp_path, monkeypatch
) -> None:
    # The illustrative demo-omda Genre package is demo AND not registered:
    # assembly fails closed before selection — zero external calls, zero
    # official-history mutation.
    import os

    from omda.ports.domain import AlbumCandidate

    os.environ["OMDA_PP_TOKEN"] = "ac2-token"

    class AnyAlbumSource:
        # Whatever batch shape the album source returns, the assembly boundary
        # must reject the UNREGISTERED demo Genre package BEFORE any batch can
        # matter — the Genre descriptor fails registry verification first.
        def source_batch(self, genre) -> CandidateBatch:
            return CuratedAlbumSource(ALBUMS).source_batch(
                GenreRef("ambient", "Ambient", "Electronic", eligible=True)
            )

        def candidates_for_genre(self, genre, limit=None) -> list[AlbumCandidate]:
            return []

    try:
        transport = _FakeTransport(ProviderSuccess({"code": 200}))
        engine = build_production_engine(
            config=load_config(_pushplus_config(tmp_path)),
            history=InMemoryHistory(),
            genre_source=GenreDatasetAdapter(DEMO_GENRES),
            album_source=AnyAlbumSource(),
            transport=transport,
            source_registry=_registry(),
            token_env="OMDA_PP_TOKEN",
            seed="ac2",
        )
        outcome = engine.run("ac2-demo")
        assert outcome.state == FAILED
        assert transport.calls == 0
    finally:
        os.environ.pop("OMDA_PP_TOKEN", None)


def test_ac2_demo_registered_source_set_rejected_by_demo_gate(
    tmp_path, monkeypatch
) -> None:
    # A REGISTERED demo Genre (registry entry with demo=true) passes assembly
    # but MUST be rejected by the production demo gate (ADR-0002 D6/§8-2):
    # external delivery refuses any demo source set.
    import os

    os.environ["OMDA_PP_TOKEN"] = "ac2-token"
    try:
        real_genre = GenreDatasetAdapter(GENRES).descriptor()
        demo_genre = replace(
            real_genre,
            demo=True,
            eligible_genre_ids=("ambient", "bebop", "krautrock"),
            eligible_digest=digest_genre_ids(("ambient", "bebop", "krautrock")),
        )
        album_entry = _registry().get("curated-omda", "album")
        registry = SourceRegistry(
            {
                "curated-omda:genre": RegistryEntry(
                    source_id="curated-omda",
                    kind="genre",
                    display_name=demo_genre.display_name,
                    origin_url=demo_genre.origin_url,
                    license=demo_genre.license,
                    retrieved_at=demo_genre.retrieved_at,
                    dataset_version=demo_genre.dataset_version,
                    schema_version=demo_genre.schema_version,
                    data_scope=demo_genre.data_scope,
                    records_file=demo_genre.records_file,
                    demo=True,
                    data_derivation=demo_genre.data_derivation,
                    upstream_license=demo_genre.upstream_license,
                    license_core_facts=demo_genre.license_core_facts,
                    license_supplementary_used=demo_genre.license_supplementary_used,
                    license_service_terms=demo_genre.license_service_terms,
                    license_derived_package=demo_genre.license_derived_package,
                    content_digest=demo_genre.content_digest,
                    eligible_digest=demo_genre.eligible_digest,
                ),
                "curated-omda:album": album_entry,
            }
        )

        class DemoGenreSource:
            def list_eligible_genres(self):
                return [
                    GenreRef("ambient", "Ambient", "Electronic"),
                    GenreRef("bebop", "Bebop", "Jazz"),
                    GenreRef("krautrock", "Krautrock", "Rock"),
                ]

            def descriptor(self) -> GenreSourceDescriptor:
                return demo_genre

        transport = _FakeTransport(ProviderSuccess({"code": 200}))
        engine = build_production_engine(
            config=load_config(_pushplus_config(tmp_path)),
            history=InMemoryHistory(),
            genre_source=DemoGenreSource(),
            album_source=CuratedAlbumSource(ALBUMS),
            transport=transport,
            source_registry=registry,
            token_env="OMDA_PP_TOKEN",
            seed="ac2-demo2",
        )
        outcome = engine.run("ac2-demo2")
        assert outcome.state == FAILED  # demo gate: external delivery rejected
        assert transport.calls == 0
        assert engine._history.latest_pick_index() == 0
    finally:
        os.environ.pop("OMDA_PP_TOKEN", None)


def test_ac2_forged_album_batch_rejected_before_delivery(tmp_path, monkeypatch) -> None:
    # A batch that self-labels the reviewed source_id but has a forged digest
    # (content not bound) fails assembly — never delivered, never committed.
    import os

    os.environ["OMDA_PP_TOKEN"] = "ac2-token"
    try:
        real = CuratedAlbumSource(ALBUMS).source_batch(
            GenreRef("ambient", "Ambient", "Electronic", eligible=True)
        )
        forged = replace(real, digest="0" * 64)

        class ForgedSource:
            def source_batch(self, genre) -> CandidateBatch:
                return forged

            def candidates_for_genre(self, genre, limit=None):
                return []

        transport = _FakeTransport(ProviderSuccess({"code": 200}))
        engine = build_production_engine(
            config=load_config(_pushplus_config(tmp_path)),
            history=InMemoryHistory(),
            genre_source=GenreDatasetAdapter(GENRES),
            album_source=ForgedSource(),
            transport=transport,
            source_registry=_registry(),
            token_env="OMDA_PP_TOKEN",
            seed="ac2-forged",
        )
        outcome = engine.run("ac2-forged")
        assert outcome.state == FAILED
        assert transport.calls == 0
    finally:
        os.environ.pop("OMDA_PP_TOKEN", None)


def test_ac2_missing_package_fails_closed() -> None:
    with pytest.raises(DeliveryFailureError):
        build_curated_sources(
            genres_dir=DEFAULT_DATA_DIR / "genres" / "does-not-exist",
        )


# --- AC-3 (G4-002C): begin binding fails closed, SQLite + InMemory parity -----


@pytest.mark.parametrize(
    "factory",
    [
        pytest.param(lambda p: SqliteHistory(p), id="sqlite"),
        pytest.param(lambda p: InMemoryHistory(), id="in-memory"),
    ],
)
def test_ac3_begin_rejects_mismatched_binding(factory, tmp_path) -> None:
    store = factory(tmp_path / "ac3.db")
    try:
        store.begin_delivery_operation(
            run_id="run-a", idempotency_key="shared:pushplus",
            channel="pushplus", payload_digest="digest-a",
        )
        # wrong run id
        with pytest.raises(InvariantFailureError):
            store.begin_delivery_operation(
                run_id="run-b", idempotency_key="shared:pushplus",
                channel="pushplus", payload_digest="digest-a",
            )
        # wrong channel
        with pytest.raises(InvariantFailureError):
            store.begin_delivery_operation(
                run_id="run-a", idempotency_key="shared:pushplus",
                channel="markdown", payload_digest="digest-a",
            )
        # wrong payload digest
        with pytest.raises(InvariantFailureError):
            store.begin_delivery_operation(
                run_id="run-a", idempotency_key="shared:pushplus",
                channel="pushplus", payload_digest="digest-b",
            )
        # identical binding is still a no-op snapshot
        snap = store.begin_delivery_operation(
            run_id="run-a", idempotency_key="shared:pushplus",
            channel="pushplus", payload_digest="digest-a",
        )
        assert snap.created is False
    finally:
        getattr(store, "close", lambda: None)()


# --- AC-4 (G4-002C): receipt attempt binding + v1 null-attempt compatibility ---


@pytest.mark.parametrize(
    "factory",
    [
        pytest.param(lambda p: SqliteHistory(p), id="sqlite"),
        pytest.param(lambda p: InMemoryHistory(), id="in-memory"),
    ],
)
def test_ac4_save_receipt_rejects_unbound_attempt(factory, tmp_path) -> None:
    from omda.ports.domain import DeliveryReceipt

    store = factory(tmp_path / "ac4.db")
    try:
        snap_a = store.begin_delivery_operation(
            run_id="run-a", idempotency_key="a:pushplus",
            channel="pushplus", payload_digest="digest-a",
        )
        store.finalize_delivery_attempt(
            operation_key="a:pushplus",
            expected_version=snap_a.operation.version,
            outcome="ok", evidence="ok", attempted_at="2026-08-22T00:00:01Z",
        )
        store.begin_delivery_operation(
            run_id="run-b", idempotency_key="b:pushplus",
            channel="pushplus", payload_digest="digest-b",
        )
        # attempt from a DIFFERENT operation -> fail closed (§15-5).
        with pytest.raises(InvariantFailureError):
            store.save_delivery_receipt(
                DeliveryReceipt(
                    run_id="run-a", idempotency_key="a:pushplus",
                    delivered_at="2026-08-22T00:00:01Z", channel="pushplus",
                    status="ok", attempt_id="b:pushplus#1",
                )
            )
        # attempt that does not exist -> fail closed.
        with pytest.raises(InvariantFailureError):
            store.save_delivery_receipt(
                DeliveryReceipt(
                    run_id="run-a", idempotency_key="a:pushplus",
                    delivered_at="2026-08-22T00:00:01Z", channel="pushplus",
                    status="ok", attempt_id="a:pushplus#99",
                )
            )
        # G4-002F: a FRESH key with attempt_id=None can no longer be inserted —
        # only genuine pre-v3 migrated rows may keep a NULL attempt binding.
        with pytest.raises(InvariantFailureError):
            store.save_delivery_receipt(
                DeliveryReceipt(
                    run_id="run-c", idempotency_key="c:markdown",
                    delivered_at="2026-01-01T00:00:00Z", channel="markdown",
                    status="ok", target="c.md", attempt_id=None,
                )
            )
        assert store.find_delivery_receipt("c:markdown") is None
    finally:
        getattr(store, "close", lambda: None)()


@pytest.mark.parametrize(
    "factory",
    [
        pytest.param(lambda p: SqliteHistory(p), id="sqlite"),
        pytest.param(lambda p: InMemoryHistory(), id="in-memory"),
    ],
)
def test_ac4_bound_receipt_binding_is_validated(factory, tmp_path) -> None:
    # AC-4 (G4-002F positive): a correctly bound receipt (operation + attempt)
    # is accepted; its run/channel/attempt must all match the operation.

    store = factory(tmp_path / "ac4b.db")
    try:
        snap = store.begin_delivery_operation(
            run_id="run-a", idempotency_key="a:pushplus",
            channel="pushplus", payload_digest="digest-a",
        )
        store.finalize_delivery_attempt(
            operation_key="a:pushplus",
            expected_version=snap.operation.version,
            outcome="ok", evidence="ok", attempted_at="2026-08-22T00:00:01Z",
        )
        bound = store.find_delivery_receipt("a:pushplus")
        assert bound is not None and bound.attempt_id == "a:pushplus#1"
        # Exact replay of the bound receipt is a no-op (immutable).
        assert store.save_delivery_receipt(bound) == bound
    finally:
        getattr(store, "close", lambda: None)()


def test_ac4_migrated_legacy_row_stays_null_readable_and_immutable(tmp_path) -> None:
    # G4-002F: a GENUINE pre-v3 row migrated to v3 keeps NULL attempt_id, stays
    # readable and can be exactly replayed — but a fresh null write is rejected
    # (covered above) and the migrated row can never be modified.
    import sqlite3

    path = tmp_path / "legacy-ac4.db"
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE run_journal (journal_id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "run_id TEXT NOT NULL, transition TEXT NOT NULL, at TEXT NOT NULL, detail TEXT)"
    )
    conn.execute(
        "CREATE TABLE genre_pick_history (pick_index INTEGER PRIMARY KEY, "
        "run_id TEXT NOT NULL, genre_id TEXT NOT NULL, committed_at TEXT NOT NULL)"
    )
    conn.execute(
        "CREATE TABLE album_history (album_id TEXT PRIMARY KEY, canonical_id TEXT, "
        "canonical_source TEXT, identity_confidence TEXT NOT NULL, run_id TEXT NOT NULL, "
        "recommended_at TEXT NOT NULL)"
    )
    conn.execute(
        "CREATE TABLE delivery_receipt (idempotency_key TEXT PRIMARY KEY, "
        "run_id TEXT NOT NULL, delivered_at TEXT NOT NULL, channel TEXT NOT NULL, "
        "status TEXT NOT NULL, target TEXT)"
    )
    conn.execute(
        "INSERT INTO delivery_receipt VALUES "
        "('old:markdown', 'old', '2026-01-01T00:00:00Z', 'markdown', 'ok', 'old.md')"
    )
    conn.execute("PRAGMA user_version = 1")
    conn.commit()
    conn.close()
    store = SqliteHistory(path)
    try:
        assert store.schema_version() == 3
        legacy = store.find_delivery_receipt("old:markdown")
        assert legacy is not None and legacy.attempt_id is None
        # Exact replay of the migrated legacy row is a no-op.
        assert store.save_delivery_receipt(legacy) == legacy
        # A conflicting write to the legacy row fails closed (immutable).
        from omda.ports.domain import DeliveryReceipt

        with pytest.raises(InvariantFailureError):
            store.save_delivery_receipt(
                DeliveryReceipt(
                    run_id="new", idempotency_key="old:markdown",
                    delivered_at="2026-02-01T00:00:00Z", channel="markdown",
                    status="ok", attempt_id=None,
                )
            )
    finally:
        store.close()


# --- AC-5 (G4-007C): config-only / CLI-override / missing-token -------------


def test_ac5_token_config_only(monkeypatch, tmp_path) -> None:
    from omda import cli

    os.environ["OMDA_PP_TOKEN"] = "config-token"
    try:
        fake = _FakeTransport(ProviderSuccess({"code": 200}))
        monkeypatch.setattr(cli, "_pushplus_transport", lambda: fake)
        code = cli.main(
            [
                "--deliver",
                "--config",
                str(_pushplus_config(tmp_path)),
                "--run-id",
                "ac5-cfg",
                "--history",
                str(tmp_path / "ac5-cfg.sqlite3"),
            ]
        )
        assert code == 0
        assert fake.last_payload["token"] == "config-token"
    finally:
        os.environ.pop("OMDA_PP_TOKEN", None)


def test_ac5_token_cli_override(monkeypatch, tmp_path) -> None:
    from omda import cli

    os.environ["OMDA_OVERRIDE"] = "cli-token"
    try:
        fake = _FakeTransport(ProviderSuccess({"code": 200}))
        monkeypatch.setattr(cli, "_pushplus_transport", lambda: fake)
        code = cli.main(
            [
                "--deliver",
                "--config",
                str(_pushplus_config(tmp_path, "OMDA_PP_TOKEN")),
                "--token-env",
                "OMDA_OVERRIDE",
                "--run-id",
                "ac5-cli",
                "--history",
                str(tmp_path / "ac5-cli.sqlite3"),
            ]
        )
        assert code == 0
        assert fake.last_payload["token"] == "cli-token"
    finally:
        os.environ.pop("OMDA_OVERRIDE", None)


def test_ac5_missing_token_fails_without_external_call(monkeypatch, tmp_path) -> None:
    from omda import cli

    cfg = tmp_path / "config.json"
    cfg.write_text('{"delivery": {"channel": "pushplus"}}', encoding="utf-8")
    fake = _FakeTransport(ProviderSuccess({"code": 200}))
    monkeypatch.setattr(cli, "_pushplus_transport", lambda: fake)
    code = cli.main(
        [
            "--deliver",
            "--config",
            str(cfg),
            "--run-id",
            "ac5-missing",
            "--history",
            str(tmp_path / "ac5-missing.sqlite3"),
        ]
    )
    assert code != 0  # token missing -> run fails
    assert fake.calls == 0  # never reached the network
    # The secret is never logged: stdout contains no token value (it was absent).


@pytest.mark.parametrize("bad_override", ["", "invalid-name", "lower_case", "HAS SPACE"])
def test_ac5_invalid_explicit_token_override_is_rejected_not_discarded(
    bad_override, monkeypatch, tmp_path, capsys
) -> None:
    # G4-007E: an EXPLICIT empty/invalid --token-env must be rejected — it must
    # never silently fall back to the configured secret. Zero network calls,
    # non-zero exit, and neither the configured nor the (absent) override token
    # ever appears in output.
    from omda import cli

    os.environ["OMDA_PP_TOKEN"] = "configured-secret"
    try:
        fake = _FakeTransport(ProviderSuccess({"code": 200}))
        monkeypatch.setattr(cli, "_pushplus_transport", lambda: fake)
        code = cli.main(
            [
                "--deliver",
                "--config",
                str(_pushplus_config(tmp_path, "OMDA_PP_TOKEN")),
                "--token-env",
                bad_override,
                "--run-id",
                "ac5-bad",
                "--history",
                str(tmp_path / f"ac5-bad-{len(bad_override)}.sqlite3"),
            ]
        )
        assert code != 0  # rejected, never silently accepted
        assert fake.calls == 0  # zero transport calls
        captured = capsys.readouterr()
        assert "configured-secret" not in (captured.out + captured.err)
    finally:
        os.environ.pop("OMDA_PP_TOKEN", None)


# --- AC-6 (G4-002E): production docstring matches the enforced classification -


def test_ac6_production_docstring_classification_is_exact() -> None:
    import inspect

    from omda import production

    doc = inspect.getdoc(production) or ""
    assert "NO HTTP 4xx class is treated as a definitive rejection" in doc
    assert "ambiguous, NO retry" in doc
    assert "NoBytesSentError" in doc and "the ONLY retryable class" in doc
    assert "ProviderRejection (terminal)" not in doc
    # Code + doc agree: every non-200 status raises AmbiguousFailure.
    transport = production.PushPlusHttpTransport(
        urlopen=_urlopen_returning(400, b"bad request")
    )
    with pytest.raises(AmbiguousFailure):
        transport.post("https://x/send", {"a": 1})


def _urlopen_returning(status: int, body: bytes):
    import io
    import urllib.error

    def urlopen(request, timeout):
        if status >= 400:
            raise urllib.error.HTTPError(
                request.full_url, status, "err", {}, io.BytesIO(body)
            )
        raise AssertionError("expected an HTTP error for status >= 400")

    return urlopen


# --- AC-7 (G4-002D / ADR-0002 D7): v3 four-layout migration + fail-closed -----


def _base_tables(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE TABLE run_journal (journal_id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "run_id TEXT NOT NULL, transition TEXT NOT NULL, at TEXT NOT NULL, detail TEXT)"
    )
    conn.execute(
        "CREATE TABLE genre_pick_history (pick_index INTEGER PRIMARY KEY, "
        "run_id TEXT NOT NULL, genre_id TEXT NOT NULL, committed_at TEXT NOT NULL)"
    )
    conn.execute(
        "CREATE TABLE album_history (album_id TEXT PRIMARY KEY, canonical_id TEXT, "
        "canonical_source TEXT, identity_confidence TEXT NOT NULL, run_id TEXT NOT NULL, "
        "recommended_at TEXT NOT NULL)"
    )
    conn.execute(
        "CREATE TABLE delivery_receipt (idempotency_key TEXT PRIMARY KEY, "
        "run_id TEXT NOT NULL, delivered_at TEXT NOT NULL, channel TEXT NOT NULL, "
        "status TEXT NOT NULL, target TEXT)"
    )


def _operation_tables(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE TABLE delivery_operation (operation_key TEXT PRIMARY KEY, "
        "run_id TEXT NOT NULL, channel TEXT NOT NULL, payload_digest TEXT NOT NULL, "
        "state TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL)"
    )
    conn.execute(
        "CREATE TABLE delivery_attempt (attempt_id TEXT PRIMARY KEY, "
        "operation_key TEXT NOT NULL, outcome TEXT NOT NULL, evidence TEXT NOT NULL, "
        "attempted_at TEXT NOT NULL)"
    )
    conn.execute(
        "CREATE TABLE delivery_resolution (id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "operation_key TEXT NOT NULL, run_id TEXT NOT NULL, idempotency_key TEXT NOT NULL, "
        "attempt_id TEXT, outcome TEXT NOT NULL, actor TEXT NOT NULL, reason TEXT NOT NULL, "
        "decided_at TEXT NOT NULL)"
    )


def _make_db(path: Path, layout: str) -> None:
    conn = sqlite3.connect(path)
    _base_tables(conn)
    if layout in ("v2-with-column", "v2-without-column", "v3"):
        _operation_tables(conn)
    if layout in ("v2-with-column", "v3"):
        conn.execute("ALTER TABLE delivery_receipt ADD COLUMN attempt_id TEXT")
    version = {"v1": 1, "v2-with-column": 2, "v2-without-column": 2, "v3": 3}[layout]
    conn.execute(f"PRAGMA user_version = {version}")
    conn.commit()
    conn.close()


@pytest.mark.parametrize("layout", ["v1", "v2-with-column", "v2-without-column", "v3"])
def test_ac7_all_four_layouts_converge_to_v3(tmp_path, layout) -> None:
    path = tmp_path / f"{layout}.db"
    _make_db(path, layout)
    store = SqliteHistory(path)
    try:
        assert store.schema_version() == 3
        cols = [r[1] for r in store._conn.execute("PRAGMA table_info(delivery_receipt)")]
        assert "attempt_id" in cols
    finally:
        store.close()


def test_ac7_future_version_fails_closed(tmp_path) -> None:
    path = tmp_path / "future.db"
    conn = sqlite3.connect(path)
    _base_tables(conn)
    _operation_tables(conn)
    conn.execute("ALTER TABLE delivery_receipt ADD COLUMN attempt_id TEXT")
    conn.execute("PRAGMA user_version = 4")  # unknown FUTURE version
    conn.commit()
    conn.close()
    with pytest.raises(SourceUnavailableError) as excinfo:
        SqliteHistory(path)
    assert "newer than supported" in str(excinfo.value)


def test_ac7_unknown_fingerprint_fails_closed(tmp_path) -> None:
    # user_version=2 but the v2 operation tables are missing: the version
    # number alone must NOT be a sufficient migration precondition (ADR2-007).
    path = tmp_path / "fingerprint.db"
    conn = sqlite3.connect(path)
    _base_tables(conn)
    conn.execute("PRAGMA user_version = 2")
    conn.commit()
    conn.close()
    with pytest.raises(SourceUnavailableError) as excinfo:
        SqliteHistory(path)
    assert "fingerprint" in str(excinfo.value).lower() or "missing" in str(
        excinfo.value
    ).lower()


def test_ac7_migration_preserves_legacy_rows_and_never_synthesizes(tmp_path) -> None:
    path = tmp_path / "legacy.db"
    conn = sqlite3.connect(path)
    _base_tables(conn)
    conn.execute(
        "INSERT INTO delivery_receipt VALUES "
        "('v1:markdown', 'v1', '2026-01-01T00:00:00Z', 'markdown', 'ok', 'v1.md')"
    )
    conn.execute("PRAGMA user_version = 1")
    conn.commit()
    conn.close()
    store = SqliteHistory(path)
    try:
        assert store.schema_version() == 3
        receipt = store.find_delivery_receipt("v1:markdown")
        assert receipt is not None and receipt.status == "ok"
        assert receipt.attempt_id is None  # legacy rows stay null, never guessed
    finally:
        store.close()


# --- AC-8 (G4-009 / ADR-0002 D8): deterministic runtime, provider fail-closed -


def test_ac8_config_rejects_provider_mode(tmp_path) -> None:
    # Direct construction fails closed (no run/journal/network side effect).
    with pytest.raises(ValueError) as excinfo:
        Config(llm=LLMConfig(mode="provider"))
    assert "not supported in v0.1" in str(excinfo.value)
    # A config file with llm.mode=provider is rejected by the schema.
    cfg = tmp_path / "provider.json"
    cfg.write_text('{"llm": {"mode": "provider"}}', encoding="utf-8")
    with pytest.raises(ValueError):
        load_config(cfg)


def test_ac8_deterministic_full_pipeline_no_llm_and_marker(tmp_path, monkeypatch) -> None:
    # AC-8: llm.mode=deterministic — the full engine run performs NO external
    # LLM call, the deliverable is the deterministic fact report, and the
    # GENERATED journal stores a typed deterministic marker (never a
    # fabricated narrative).
    import os

    os.environ["OMDA_PP_TOKEN"] = "ac8-token"

    class ExplodingLLM:
        def generate_narrative(self, fact_packet, **kwargs):
            raise AssertionError("v0.1 deterministic runtime must never call an LLM")

    try:
        genre_source, album_source, registry = build_curated_sources()
        config = load_config(_pushplus_config(tmp_path))
        assert config.llm.mode == "deterministic"
        db = tmp_path / "runtime-ac8.sqlite3"
        history = SqliteHistory(db)
        try:
            transport = _FakeTransport(ProviderSuccess({"code": 200}))
            engine = build_production_engine(
                config=config,
                history=history,
                genre_source=genre_source,
                album_source=album_source,
                transport=transport,
                source_registry=registry,
                token_env="OMDA_PP_TOKEN",
                seed="ac8",
            )
            engine._llm = ExplodingLLM()  # would fail if the engine ever called it
            outcome = engine.run("ac8")
            assert outcome.state == COMPLETE
            generated = next(
                e
                for e in history.journal_after("ac8", 0)
                if e.transition == "GENERATED"
            )
            assert generated.detail == {"narrative_mode": "deterministic"}
            assert "narrative" not in generated.detail
        finally:
            history.close()
    finally:
        os.environ.pop("OMDA_PP_TOKEN", None)


# --- AC-9A (public entry, curated 3x3): exhaustion behavior after history -----


def test_ac9a_second_run_never_repeats_and_fails_closed_on_exhaustion(tmp_path) -> None:
    # AC-9A: after the first run commits 9 Albums, a second deterministic run
    # against the same store permanently excludes those identities. The curated
    # package holds only 4 records per Genre, so a re-selected Genre is
    # exhausted: the run must FAIL CLOSED (explicit exhaustion, never a repeat
    # and never a sample substitution), leaving the 9 committed identities
    # unchanged.
    import os

    from omda import cli

    os.environ["OMDA_PP_TOKEN"] = "ac9a-token"
    try:
        import omda.cli as cli_module

        monkeypatch = pytest.MonkeyPatch()
        fake = _FakeTransport(ProviderSuccess({"code": 200}))
        monkeypatch.setattr(cli_module, "_pushplus_transport", lambda: fake)
        db = tmp_path / "runtime-ac9a.sqlite3"
        cfg = _pushplus_config(tmp_path)
        assert (
            cli.main(
                ["--deliver", "--config", str(cfg), "--run-id", "ac9a-1",
                 "--history", str(db)]
            )
            == 0
        )
        store = SqliteHistory(db)
        try:
            first_ids = {i.album_id for i in store.excluded_album_identities()}
            assert len(first_ids) == 9
        finally:
            store.close()
        # Second run: with a limited 4-per-Genre curated package, a re-selected
        # Genre cannot supply 3 fresh records -> explicit failure is the CORRECT
        # AC-9A outcome ("insufficient candidates -> explicit failure, no
        # sample substitution, no history pollution").
        code2 = cli.main(
            ["--deliver", "--config", str(cfg), "--run-id", "ac9a-2", "--history", str(db)]
        )
        store = SqliteHistory(db)
        try:
            all_ids = {i.album_id for i in store.excluded_album_identities()}
            assert all_ids == first_ids  # nothing new was committed
            assert len(all_ids) == 9
        finally:
            store.close()
        if code2 == 0:
            # A lucky second run picked only fresh Genres -> it must still have
            # committed 9 NEW identities, never a repeat.
            store = SqliteHistory(db)
            try:
                second_ids = {i.album_id for i in store.excluded_album_identities()}
            finally:
                store.close()
            assert len(second_ids) == 18
            assert not second_ids.intersection(first_ids)
    finally:
        os.environ.pop("OMDA_PP_TOKEN", None)
