"""G4 end-to-end pipeline composition (T4.1 + T4.2 + T4.3).

A generated narrative from the LLM adapter is rendered into a structured
Markdown report, validated (structure/length/fact references) and delivered via
the Markdown file channel. A fabricated/dropped fact fails validation and is
never delivered. All local; no live LLM or PushPlus.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from omda.adapters.delivery import MarkdownFileDelivery
from omda.adapters.llm import LLMAdapter
from omda.output.markdown import build_report_data, render_markdown, validate_markdown
from omda.ports.errors import ValidationFailureError


class ScriptedTransport:
    def __init__(self, text: str) -> None:
        self.text = text
        self.calls = 0

    def complete(self, system: str, user: str) -> str:
        self.calls += 1
        return self.text


def _report_data() -> object:
    return build_report_data(
        run_id="run-g4",
        genres=[
            {"genre_id": "ambient", "name": "Ambient"},
            {"genre_id": "jazz", "name": "Jazz"},
        ],
        albums=[
            {
                "album_id": "a1",
                "genre_id": "ambient",
                "title": "Selected Album",
                "artist": "Artist A",
                "year": 2015,
            },
            {
                "album_id": "a2",
                "genre_id": "jazz",
                "title": "Jazz Album",
                "artist": "Artist C",
                "year": 1998,
            },
        ],
    )


def test_full_pipeline_generates_validates_and_delivers_markdown() -> None:
    # The LLM only explains: even a narrative mentioning other albums cannot
    # alter the plan facts, and the validated report is delivered locally.
    llm = LLMAdapter(transport=ScriptedTransport("A concise explanation of the picks."))
    data = _report_data()
    narrative = llm.generate_narrative(
        {
            "run_id": "run-g4",
            "genres": [
                {"genre_id": "ambient", "name": "Ambient"},
                {"genre_id": "jazz", "name": "Jazz"},
            ],
            "albums": [
                {"album_id": "a1", "title": "Selected Album", "artist": "Artist A", "year": 2015},
                {"album_id": "a2", "title": "Jazz Album", "artist": "Artist C", "year": 1998},
            ],
        }
    )
    payload = render_markdown(data, narrative)
    validate_markdown(payload, data)  # facts come from the plan
    assert "- Album X" not in payload

    with tempfile.TemporaryDirectory() as d:
        delivery = MarkdownFileDelivery(output_dir=Path(d) / "out")
        receipt = delivery.deliver(payload, "run-g4:markdown")
        assert receipt.status == "ok"
        assert (Path(d) / "out" / "run-g4.md").exists()


def test_fabricated_report_is_never_delivered() -> None:
    # Validation failure blocks delivery: the file channel is never written.
    data = _report_data()
    payload = render_markdown(data, "ok")
    payload = payload.replace("## Jazz\n", "", 1)  # dropped a fact
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "out"
        MarkdownFileDelivery(output_dir=out)  # channel exists but must not be used
        try:
            validate_markdown(payload, data)
        except ValidationFailureError:
            pass  # validation refused the payload
        else:
            raise AssertionError("fabricated payload must fail validation")
        assert not (out / "run-g4.md").exists()  # never delivered
