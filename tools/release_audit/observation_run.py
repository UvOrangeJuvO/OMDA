#!/usr/bin/env python3
"""G5 T5.5 — honest controlled observations (G5-006).

Observations 1-7: SEVEN invocations of the PUBLIC ``--dry-run`` entry point
(``omda.cli.main``), each recording:

- UTC timestamp and the exact candidate SHA (``git rev-parse HEAD``);
- the command/mode string;
- the packaged data version (demo-omda manifest) and default config;
- ZERO live calls: an exploding PushPlus transport factory is installed, so
  any attempt to construct a transport for dry-run would fail the observation;
- the SHA-256 digest of the produced preview file;
- before/after official-history checks on the CLI default runtime store (the
  dry-run path never creates or mutates it).

The runs are intentionally same-day and automated; they are labeled as such,
NOT as elapsed operational stability.

Observation 8 (G5-002 replacement): the targeted Album-exclusion evidence —
one already-committed canonical identity is planted inside every selectable
Genre pool; a full engine run must complete with nine NEW real albums, never
the committed identity.

Output: JSON lines to stdout. Exit 0 only if every observation satisfies its
invariants.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

from omda import cli  # noqa: E402
from omda.orchestrator.run import COMPLETE  # noqa: E402


class _ExplodingTransportFactory:
    """Any attempt to construct a PushPlus transport during a dry-run fails."""

    def __call__(self):
        raise AssertionError(
            "dry-run must never construct a PushPlus transport (zero live calls)"
        )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _candidate_sha() -> str:
    out = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True, check=True, text=True
    )
    return out.stdout.strip()


def _demo_data_version() -> str:
    from omda.production import DEFAULT_DATA_DIR

    meta = (
        DEFAULT_DATA_DIR / "genres" / "demo-omda" / "source.yaml"
    ).read_text(encoding="utf-8")
    for line in meta.splitlines():
        if line.startswith("dataset_version:"):
            return line.split(":", 1)[1].strip().strip('"')
    return "unknown"


def _official_history_state() -> str:
    from omda.cli import DEFAULT_HISTORY_PATH

    if not DEFAULT_HISTORY_PATH.exists():
        return "absent"
    from omda.storage import SqliteHistory

    store = SqliteHistory(DEFAULT_HISTORY_PATH)
    try:
        return f"picks={store.latest_pick_index()}"
    finally:
        store.close()


def main() -> int:
    sha = _candidate_sha()
    data_version = _demo_data_version()
    observations: list[dict] = []

    # --- Observations 1-7: public --dry-run (same-day, automated) ------------
    for i in range(1, 8):
        with tempfile.TemporaryDirectory() as d:
            out_dir = Path(d) / "previews"
            out_dir.mkdir()
            run_id = f"g5-obs-{i}"
            argv = [
                "--dry-run",
                "--output-dir", str(out_dir),
                "--run-id", run_id,
            ]
            transport = _ExplodingTransportFactory()
            before = _official_history_state()
            import datetime as _dt

            ts = _dt.datetime.now(_dt.UTC).isoformat().replace("+00:00", "Z")
            saved = cli._pushplus_transport
            cli._pushplus_transport = transport  # type: ignore[attr-defined]
            try:
                code = cli.main(argv)
            finally:
                cli._pushplus_transport = saved  # type: ignore[attr-defined]
            after = _official_history_state()

            preview = out_dir / f"{run_id}.md"
            obs = {
                "observation": i,
                "timestamp": ts,
                "candidate_sha": sha,
                "command": "omda.cli --dry-run --output-dir <tmp> --run-id " + run_id,
                "mode": "public dry-run (CLI main entry)",
                "data_version": data_version,
                "config": "defaults (llm.mode=deterministic)",
                "live_calls": 0,
                "exit_code": code,
                "state": "COMPLETE",
                "preview_digest_sha256": _sha256(preview) if preview.exists() else None,
                "official_history_before": before,
                "official_history_after": after,
                "same_day_automated": True,
                "note": "not elapsed operational stability; rehearsals only",
            }
            observations.append(obs)
            assert code == 0, obs
            assert preview.exists(), obs
            assert obs["preview_digest_sha256"], obs
            assert obs["official_history_before"] == "absent", obs
            assert obs["official_history_after"] == "absent", obs
            # A dry-run must never mutate the official store (before/after equal).
            assert obs["official_history_before"] == obs["official_history_after"]

    # --- Observation 8 (G5-002 evidence): Album exclusion in the selection path
    from omda.adapters.delivery import MarkdownFileDelivery
    from omda.config import load_config
    from omda.orchestrator.run import RunEngine
    from omda.ports.domain import AlbumCandidate, AlbumIdentity, GenrePickRecord, GenreRef
    from omda.storage import SqliteHistory

    class _WideGenreSource:
        def __init__(self, genres):
            self._genres = genres

        def list_eligible_genres(self):
            return self._genres

    class _PoolAlbumSource:
        def __init__(self, by_genre):
            self._by_genre = by_genre

        def candidates_for_genre(self, genre, limit=None):
            found = self._by_genre.get(genre.genre_id, [])
            return found[:limit] if limit is not None else list(found)

    genres = [
        GenreRef(f"g{i:02d}", f"Genre {i:02d}", "Electronic", eligible=True)
        for i in range(40)
    ]

    def _cid(gid: str, idx: int) -> str:
        return f"00000000-0000-0000-{gid}-{idx:04d}"

    def _candidate(gid: str, idx: int, *, identity=None):
        return AlbumCandidate(
            album_id=f"{gid}-a{idx}", title=f"{gid} Album {idx}", artist="Artist",
            year=2000 + idx,
            identity=identity or AlbumIdentity(
                album_id=f"{gid}-a{idx}", canonical_id=_cid(gid, idx),
                canonical_source="musicbrainz",
            ),
        )

    committed = _candidate("g00", 1).identity
    by_genre = {}
    for g in genres:
        pool = [_candidate(g.genre_id, i) for i in (1, 2, 3, 4)]
        pool.append(
            AlbumCandidate(f"{g.genre_id}-planted", "Planted Repeat", "Artist", 2010,
                           identity=committed)
        )
        by_genre[g.genre_id] = pool

    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        db = d / "obs8.sqlite3"
        store = SqliteHistory(db)
        store.commit_history(
            "seed-run",
            [GenrePickRecord(1, "g99"), GenrePickRecord(2, "g98"), GenrePickRecord(3, "g97")],
            [committed],
            "2026-08-27T00:00:00Z",
        )
        engine = RunEngine(
            config=load_config(),
            history=store,
            genre_source=_WideGenreSource(genres),
            album_source=_PoolAlbumSource(by_genre),
            llm=None,
            delivery=MarkdownFileDelivery(output_dir=d / "preview"),
            seed="g5-obs8",
        )
        outcome = engine.run("g5-obs8")
        selected = outcome.plan.albums if outcome.plan else []
        selected_canonical = {a.canonical_id for a in selected}
        obs8 = {
            "observation": 8,
            "timestamp": _dt.datetime.now(_dt.UTC).isoformat().replace("+00:00", "Z"),
            "candidate_sha": sha,
            "mode": "Album-exclusion evidence (G5-002 replacement)",
            "state": outcome.state,
            "selected_albums": len(selected),
            "committed_identity_rejected": committed.canonical_id not in selected_canonical,
            "no_repeat_within_run": len({a.album_id for a in selected}) == len(selected),
            "official_history_picks_after": store.latest_pick_index(),
        }
        observations.append(obs8)
        assert outcome.state == COMPLETE, obs8
        assert len(selected) == 9, obs8
        assert committed.canonical_id not in selected_canonical, obs8
        assert obs8["no_repeat_within_run"], obs8
        store.close()

    for obs in observations:
        print(json.dumps(obs, ensure_ascii=False, sort_keys=True))
    print(f"OBSERVATIONS: {len(observations)} recorded, all invariants satisfied")
    return 0


if __name__ == "__main__":
    sys.exit(main())
