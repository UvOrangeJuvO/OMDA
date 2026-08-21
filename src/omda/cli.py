"""G4 T4.5 — default dry-run and explicit delivery approval gate (OPH §14-8).

The CLI defaults to a DRY-RUN: the run writes a local Markdown file and never
calls an external service (no token resolution, no HTTP transport is even
constructed). External push (PushPlus) is allowed only with an explicit
``--deliver`` flag (or an explicit configuration flag in programmatic use).
Explicit ``--dry-run`` always wins over ``--deliver``: it is a safety gate.
"""

from __future__ import annotations

import argparse
import enum
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from omda.orchestrator.run import RunOutcome

DEFAULT_OUTPUT_DIR = Path("var/output")
DEFAULT_TOKEN_ENV = "PUSHPLUS_TOKEN"
# Package-root anchored default runtime store (independent of the caller's CWD).
DEFAULT_HISTORY_PATH = Path(
    __import__("omda.production", fromlist=["DEFAULT_DATA_DIR"]).DEFAULT_DATA_DIR
).parent / "var" / "omda.sqlite3"


class DeliveryMode(enum.Enum):
    """The effective external-delivery decision of a run."""

    DRY_RUN = "dry-run"
    DELIVER = "deliver"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments; external push is OFF unless ``--deliver``."""
    parser = argparse.ArgumentParser(prog="omda", description="OMDA daily music discovery")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="write a local Markdown report without any external push (default safety gate)",
    )
    parser.add_argument(
        "--deliver",
        action="store_true",
        default=False,
        help="allow an external PushPlus push for this run (explicit approval required)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="directory for the dry-run Markdown report",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="JSON config file (see data/schemas/config.schema.json); defaults apply if absent",
    )
    parser.add_argument(
        "--history",
        type=Path,
        default=DEFAULT_HISTORY_PATH,
        help="SQLite runtime-store path used by the --deliver path",
    )
    parser.add_argument(
        "--source-path",
        type=Path,
        default=None,
        help="explicit genre dataset directory (default: packaged sample data)",
    )
    parser.add_argument(
        "--token-env",
        default=DEFAULT_TOKEN_ENV,
        help="environment variable that holds the PushPlus token (never logged)",
    )
    parser.add_argument("--run-id", default=None, help="optional run id (default: generated)")
    return parser.parse_args(argv)


def select_delivery(args: argparse.Namespace) -> DeliveryMode:
    """Decide the delivery mode: explicit ``--dry-run`` wins; else only an
    explicit ``--deliver`` unlocks external push."""
    if args.dry_run:
        return DeliveryMode.DRY_RUN
    if args.deliver:
        return DeliveryMode.DELIVER
    return DeliveryMode.DRY_RUN  # default: dry-run, no external side effects


def run_dry_run(
    *,
    run_id: str,
    output_dir: Path | str,
    genre_source,
    album_source,
    llm,
    seed: str | None = None,
) -> RunOutcome:
    """Execute a REAL production dry-run against an ISOLATED history.

    G4-003: the dry-run wires the actual ``RunEngine`` with the local Markdown
    file delivery channel and a fresh in-memory history. It therefore:

    - writes the intended local Markdown preview (``<output_dir>/<run_id>.md``);
    - makes ZERO external calls (no PushPlus transport is constructed, no token
      is resolved);
    - NEVER touches the official Genre/Album history store — each dry-run works
      against its own isolated history, so repeated rehearsals (e.g. seven) are
      history-neutral (IMPLEMENTATION_PLAN T4.5, OPH §14-8).

    Only the explicit ``--deliver`` application path may construct a PushPlus
    delivery and write official history.
    """
    from omda.adapters.delivery import MarkdownFileDelivery
    from omda.config import load_config
    from omda.orchestrator.run import RunEngine
    from omda.storage import SqliteHistory

    engine = RunEngine(
        config=load_config(),
        history=SqliteHistory(":memory:"),  # isolated: official history never touched
        genre_source=genre_source,
        album_source=album_source,
        llm=llm,
        delivery=MarkdownFileDelivery(output_dir=output_dir),
        seed=seed,
    )
    return engine.run(run_id)


__all__ = [
    "DEFAULT_OUTPUT_DIR",
    "DEFAULT_TOKEN_ENV",
    "DeliveryMode",
    "parse_args",
    "run_dry_run",
    "select_delivery",
]


def main(argv: list[str] | None = None) -> int:
    """Application entry point (``python -m omda.cli``).

    Defaults to a DRY-RUN: executes the real production dry-run pipeline
    against isolated history and writes a local Markdown preview, making zero
    external calls. An explicit ``--deliver`` runs the REAL production
    Agent/PushPlus composition (G4-007): a PushPlus HTTP transport, the
    packaged data sources and the official SQLite runtime store; the push only
    happens for that explicitly approved run.
    """
    args = parse_args(argv)
    mode = select_delivery(args)
    try:
        return _main(mode, args)
    except SystemExit:
        raise
    except Exception as exc:  # any unexpected failure -> non-zero exit code
        print(f"omda: run failed: {exc}")
        return 1


def _main(mode: DeliveryMode, args: argparse.Namespace) -> int:
    if mode is DeliveryMode.DELIVER:
        from omda.config import load_config
        from omda.orchestrator.run import COMPLETE
        from omda.production import build_production_engine
        from omda.storage import SqliteHistory

        config = load_config(args.config)
        if config.delivery is None or config.delivery.channel != "pushplus":
            raise SystemExit(
                "--deliver requires delivery.channel == 'pushplus' in config "
                "(pass --config with a pushplus channel; see data/schemas/config.schema.json)"
            )
        genre_source = _sample_genre_source(args)
        genres = genre_source.list_eligible_genres()
        album_source = _sample_album_source(genres)
        run_id = args.run_id or _new_run_id("run")
        history = SqliteHistory(args.history)
        try:
            engine = build_production_engine(
                config=config,
                history=history,
                genre_source=genre_source,
                album_source=album_source,
                llm_transport=_LocalEchoTransport(),
                transport=_pushplus_transport(),
                token_env=args.token_env or config.delivery.pushplus_token_env,
                seed=run_id,
            )
            outcome = engine.run(run_id)
        finally:
            history.close()
        print(f"deliver {run_id}: {outcome.state}")
        return 0 if outcome.state == COMPLETE else 1

    # DRY-RUN (default safety gate): local preview, zero external calls.
    from omda.adapters.llm import LLMAdapter

    genre_source = _sample_genre_source(args)
    genres = genre_source.list_eligible_genres()
    album_source = _sample_album_source(genres)
    run_id = args.run_id or _new_run_id("dry")
    llm = LLMAdapter(transport=_LocalEchoTransport())
    outcome = run_dry_run(
        run_id=run_id,
        output_dir=args.output_dir,
        genre_source=genre_source,
        album_source=album_source,
        llm=llm,
        seed=run_id,
    )
    target = outcome.receipt.target if outcome.receipt is not None else str(
        Path(args.output_dir) / f"{run_id}.md"
    )
    print(f"dry-run {run_id}: {outcome.state}")
    print(f"preview: {target}")
    from omda.orchestrator.run import COMPLETE

    return 0 if outcome.state == COMPLETE else 1


def _pushplus_transport() -> object:
    """Return the concrete PushPlus HTTP transport for the --deliver route.

    Injectable for tests (fake network boundary) via monkeypatching; the
    production default is the standard-library PushPlusHttpTransport.
    """
    from omda.production import PushPlusHttpTransport

    return PushPlusHttpTransport()


def _new_run_id(prefix: str) -> str:
    from omda.orchestrator.run import utc_now

    # No dots: the run id is the file-name input for Markdown delivery, so the
    # printed preview path must match the actual file exactly (G4-003 P2).
    return f"{prefix}-{utc_now().replace(':', '').replace('.', '').replace('Z', '')}"


def _sample_genre_source(args) -> object:
    from omda.adapters.datasets import GenreDatasetAdapter

    if args.source_path is not None:
        return GenreDatasetAdapter(str(args.source_path))
    # Packaged data resolved independently of the caller's working directory.
    from omda.production import DEFAULT_DATA_DIR

    return GenreDatasetAdapter(str(DEFAULT_DATA_DIR / "genres" / "rym-sample"))


class _LocalEchoTransport:
    """Local echo transport for the sample dry-run (no network, no SDK)."""

    def complete(self, system: str, user: str) -> str:
        return "A concise local explanation of the selected picks."


def _sample_album_source(genres):
    from omda.ports.domain import AlbumCandidate

    class SampleAlbums:
        def candidates_for_genre(self, genre) -> list[AlbumCandidate]:
            gid = genre.genre_id
            return [
                AlbumCandidate(f"{gid}-1", f"{gid} Sample 1", "Sample Artist", 2015),
                AlbumCandidate(f"{gid}-2", f"{gid} Sample 2", "Sample Artist", 2000),
                AlbumCandidate(f"{gid}-3", f"{gid} Sample 3", "Sample Artist", 1990),
            ]

    return SampleAlbums()


if __name__ == "__main__":  # pragma: no cover - entry point
    raise SystemExit(main())
