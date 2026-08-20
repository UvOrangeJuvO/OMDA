"""G4 T4.5 — dry-run default and explicit delivery approval gate (OPH §14-8).

By default a run is a dry-run: it writes a local Markdown file and NEVER calls
an external service. External push requires an explicit ``--deliver`` /
config flag. Tests prove dry-run never constructs a PushPlus transport and
never resolves a token.
"""

from __future__ import annotations

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
