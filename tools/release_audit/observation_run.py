#!/usr/bin/env python3
"""G5 T5.5 — controlled observations (OPH §14-9 / IMPLEMENTATION_PLAN T5.5).

Runs the REAL production composition (reviewed curated sources + registry)
against a FAKE PushPlus transport — zero live calls — and records a structured
observation per run: run_id, state, picks, album count, within-run repeats and
official-history pick index.

Observations 1-7: each run uses an ISOLATED history (dry-run semantics) to
demonstrate that repeated daily-style runs are history-neutral and always
produce a valid 3x3 with no repeats.
Observation 8: the SAME durable history is reused so permanent exclusion can be
observed — a second run never repeats a committed identity and either completes
with fresh identities or fails explicitly on exhaustion.

Output: JSON lines to stdout (and written to reviews/stage-05/OBSERVATION_LOG.md
by the Executor). Exit 0 only if every observation satisfies its invariants.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from omda.adapters.delivery import ProviderSuccess
from omda.config import DeliveryConfig, load_config
from omda.orchestrator.run import COMPLETE, FAILED
from omda.production import build_curated_sources, build_production_engine
from omda.storage import SqliteHistory


class _FakeTransport:
    def __init__(self) -> None:
        self.calls = 0
        self.last_payload = None

    def post(self, url: str, payload: dict) -> ProviderSuccess:
        self.calls += 1
        self.last_payload = payload
        return ProviderSuccess({"code": 200})


def _config() -> object:
    from dataclasses import replace

    return replace(
        load_config(),
        delivery=DeliveryConfig(channel="pushplus", pushplus_token_env="OMDA_PP_TOKEN"),
    )


def _engine(history, transport):
    genre_source, album_source, registry = build_curated_sources()
    return build_production_engine(
        config=_config(),
        history=history,
        genre_source=genre_source,
        album_source=album_source,
        transport=transport,
        token_env="OMDA_PP_TOKEN",
        source_registry=registry,
        seed="g5-observation",
    )


def main() -> int:
    os.environ["OMDA_PP_TOKEN"] = "observation-token"
    observations: list[dict] = []
    try:
        # Observations 1-7: isolated history each (history-neutral daily rehearsal).
        for i in range(1, 8):
            history = SqliteHistory(":memory:")
            transport = _FakeTransport()
            engine = _engine(history, transport)
            outcome = engine.run(f"g5-obs-{i}")
            ids = [a.album_id for a in (outcome.plan.albums if outcome.plan else [])]
            obs = {
                "observation": i,
                "run_id": f"g5-obs-{i}",
                "state": outcome.state,
                "transport_calls": transport.calls,
                "committed_picks_in_isolated_history": history.latest_pick_index(),
                "albums": len(ids),
                "within_run_repeats": len(ids) - len(set(ids)),
                "mode": "isolated-history dry rehearsal",
            }
            observations.append(obs)
            assert outcome.state == COMPLETE, obs
            assert len(ids) == 9 and len(set(ids)) == 9, obs
            assert transport.calls == 1, obs
            assert history.latest_pick_index() == 3, obs
            history.close()

        # Observation 8: shared durable history — permanent exclusion behavior.
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            db = Path(d) / "obs.sqlite3"
            transport = _FakeTransport()
            engine = _engine(SqliteHistory(db), transport)
            first = engine.run("g5-obs-shared-1")
            first_ids = {a.album_id for a in (first.plan.albums if first.plan else [])}
            second = engine.run("g5-obs-shared-2")
            second_ids = {a.album_id for a in (second.plan.albums if second.plan else [])}
            obs = {
                "observation": 8,
                "run_id": "g5-obs-shared-1/2",
                "state": f"{first.state} -> {second.state}",
                "transport_calls": transport.calls,
                "picks": engine._history.latest_pick_index(),
                "shared_history_no_repeat": bool(second_ids.isdisjoint(first_ids)),
                "mode": "shared durable history (permanent exclusion)",
            }
            observations.append(obs)
            if second.state == COMPLETE:
                assert len(second_ids) == 9 and second_ids.isdisjoint(first_ids), obs
            else:
                assert second.state == FAILED, obs  # explicit exhaustion, no repeat
            engine._history.close()
    finally:
        os.environ.pop("OMDA_PP_TOKEN", None)

    for obs in observations:
        print(json.dumps(obs, ensure_ascii=False, sort_keys=True))
    print(f"OBSERVATIONS: {len(observations)} recorded, all invariants satisfied")
    return 0


if __name__ == "__main__":
    sys.exit(main())
