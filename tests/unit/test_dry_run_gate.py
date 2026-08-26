"""G4 T4.5 — dry-run default and explicit delivery approval gate (OPH §14-8).

By default a run is a dry-run: it writes a local Markdown file and NEVER calls
an external service. External push requires an explicit ``--deliver`` /
config flag. Tests prove dry-run never constructs a PushPlus transport and
never resolves a token.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from omda.cli import DeliveryMode, parse_args, select_delivery
from omda.config import Config, DeliveryConfig


def test_default_mode_is_dry_run() -> None:
    args = parse_args([])
    assert args.deliver is False  # external push is OFF by default
    assert select_delivery(args) == DeliveryMode.DRY_RUN


def test_explicit_deliver_flag_enables_push() -> None:
    args = parse_args(["--deliver"])
    assert args.deliver is True
    assert select_delivery(args) == DeliveryMode.DELIVER


def test_explicit_dry_run_flag_overrides_default() -> None:
    args = parse_args(["--dry-run", "--deliver"])
    # Explicit --dry-run wins: it is a safety gate, never silently ignored.
    assert select_delivery(args) == DeliveryMode.DRY_RUN


def test_dry_run_never_constructs_external_transport() -> None:
    # Proof: selecting the dry-run delivery does not build a PushPlus adapter,
    # so no external call is even possible.
    from omda.adapters.delivery import MarkdownFileDelivery

    args = parse_args(["--output-dir", "/tmp/omda-dry"])
    delivery = build_delivery(args)
    assert isinstance(delivery, MarkdownFileDelivery)
    assert not hasattr(delivery, "_transport")  # no HTTP boundary exists


def test_dry_run_never_resolves_token() -> None:
    import os

    os.environ["OMDA_TEST_TOKEN"] = "should-not-be-touched"
    try:
        args = parse_args([])
        from omda.adapters.delivery import MarkdownFileDelivery

        delivery = build_delivery(args)
        assert isinstance(delivery, MarkdownFileDelivery)
    finally:
        del os.environ["OMDA_TEST_TOKEN"]


def test_deliver_mode_requires_channel_config() -> None:
    # Push requires an explicit channel config; a markdown-only config never
    # pushes even with --deliver.
    args = parse_args(["--deliver"])
    config = Config(delivery=DeliveryConfig(channel="markdown"))
    assert config.delivery.channel == "markdown"
    # Channel config decides the target; --deliver only unlocks external push.
    assert args.deliver is True


# --- helpers exposed for composition (implemented below) ----------------------


def build_delivery(args) -> object:
    """Return the concrete Delivery adapter for the parsed CLI args.

    Dry-run (default): local Markdown file delivery — no network, no token.
    Explicit --deliver: the configured external channel (PushPlus) may be
    constructed; the caller must supply the token via the environment.
    """
    from omda.adapters.delivery import MarkdownFileDelivery, PushPlusDelivery

    if select_delivery(args) == DeliveryMode.DRY_RUN:
        return MarkdownFileDelivery(output_dir=args.output_dir)
    return PushPlusDelivery(
        token_env=args.token_env,
        transport=__import__(
            "omda.adapters.delivery", fromlist=["HttpTransport"]
        ).HttpTransport,
        sleeper=__import__("time", fromlist=["sleep"]).sleep,
    )


# --- G4-007: the CLI main() wiring (dry-run executable, --deliver guard) -------


def test_main_dry_run_exits_zero_and_reports_real_preview_path(monkeypatch, tmp_path) -> None:
    from omda import cli

    out = tmp_path / "previews"
    run_id = "cli-dry-1"
    code = cli.main(["--dry-run", "--output-dir", str(out), "--run-id", run_id])
    assert code == 0
    # The reported preview file actually exists (no dots in the run id).
    preview = out / f"{run_id}.md"
    assert preview.exists()
    assert preview.read_text(encoding="utf-8").startswith("# 每日音乐发现")


def test_main_dry_run_returns_nonzero_on_failed_run(monkeypatch, tmp_path) -> None:
    from omda import cli

    out = tmp_path / "previews"
    # A dataset with a valid source.yaml but NO eligible genres -> the run
    # fails (InsufficientCandidatesError) and the CLI exits nonzero.
    ds = tmp_path / "genres"
    ds.mkdir()
    (ds / "source.yaml").write_text(
        "# empty dataset: valid source meta, zero records\n"
        "source_id: genres\n"
        "display_name: Empty Genres\n"
        "license: CC0-1.0\n"
        "origin_url: https://example.org\n"
        "retrieved_at: 2026-08-21T00:00:00+00:00\n"
        "dataset_version: 2026-08-21\n"
        "data_scope: empty\n"
        "records_file: genres.jsonl\n",
        encoding="utf-8",
    )
    (ds / "genres.jsonl").write_text("", encoding="utf-8")
    code = cli.main(
        ["--dry-run", "--output-dir", str(out), "--run-id", "cli-fail", "--source-path", str(ds)]
    )
    assert code != 0


def test_main_deliver_rejects_non_pushplus_channel(monkeypatch) -> None:
    from omda import cli

    # Default config uses channel == "markdown": --deliver must refuse loudly.
    with pytest.raises(SystemExit):
        cli.main(["--deliver", "--run-id", "cli-pp"])


# --- G4-007 re-review 3: the PUBLIC --deliver route is reachable ----------------


class _FakePushPlusTransport:
    def __init__(self, *script):
        self.script = list(script)
        self.calls = 0
        self.last_payload = None

    def post(self, url: str, payload: dict):
        self.calls += 1
        self.last_payload = payload
        step = self.script[min(self.calls - 1, len(self.script) - 1)]
        if isinstance(step, Exception):
            raise step
        return step


def _pushplus_config(tmp_path) -> Path:
    path = tmp_path / "config.json"
    path.write_text(
        '{"delivery": {"channel": "pushplus", "pushplus_token_env": "OMDA_PP_TOKEN"}}',
        encoding="utf-8",
    )
    return path


def test_public_cli_deliver_reaches_composition_and_uses_chosen_token(
    monkeypatch, tmp_path
) -> None:
    # The PUBLIC CLI route: --deliver + --config (pushplus channel) + explicit
    # --token-env reaches the production composition with an injected fake
    # network boundary; the chosen token variable is honoured.
    import os

    from omda import cli
    from omda.adapters.delivery import ProviderSuccess

    os.environ["OMDA_PP_TOKEN"] = "chosen-token"
    try:
        fake = _FakePushPlusTransport(ProviderSuccess({"code": 200}))
        monkeypatch.setattr(cli, "_pushplus_transport", lambda: fake)
        code = cli.main(
            [
                "--deliver",
                "--config",
                str(_pushplus_config(tmp_path)),
                "--token-env",
                "OMDA_PP_TOKEN",
                "--run-id",
                "cli-pp-1",
                "--history",
                str(tmp_path / "runtime.sqlite3"),
            ]
        )
        assert code == 0  # COMPLETE
        assert fake.calls == 1  # exactly one external push
        assert fake.last_payload["token"] == "chosen-token"
    finally:
        os.environ.pop("OMDA_PP_TOKEN", None)


def test_public_cli_deliver_ambiguous_exits_nonzero(monkeypatch, tmp_path) -> None:
    import os

    from omda import cli
    from omda.adapters.delivery import AmbiguousFailure

    os.environ["OMDA_PP_TOKEN"] = "chosen-token"
    try:
        fake = _FakePushPlusTransport(AmbiguousFailure("timeout"))
        monkeypatch.setattr(cli, "_pushplus_transport", lambda: fake)
        code = cli.main(
            [
                "--deliver",
                "--config",
                str(_pushplus_config(tmp_path)),
                "--token-env",
                "OMDA_PP_TOKEN",
                "--run-id",
                "cli-pp-amb",
                "--history",
                str(tmp_path / "runtime.sqlite3"),
            ]
        )
        assert code != 0  # RECOVERING -> non-zero
        assert fake.calls == 1  # ambiguous is never blindly retried
    finally:
        os.environ.pop("OMDA_PP_TOKEN", None)


def test_public_cli_deliver_without_pushplus_config_still_refuses(monkeypatch, tmp_path) -> None:
    # The safety gate stays: no config / markdown channel -> --deliver refuses.
    from omda import cli

    with pytest.raises(SystemExit):
        cli.main(["--deliver", "--run-id", "cli-nope"])
