"""Markdown report generation and validation (G4 T4.2, G4-005).

Renders a deterministic, structured Markdown report from the already-selected
plan facts and validates structure, length and FACT REFERENCES before anything
is delivered (SPEC §3.5, §8; MP §3.6). A payload that fails validation MUST
NOT be delivered.

G4-005 (mechanical output contract): the deliverable contains NO unconstrained
LLM prose. Every Genre heading and every complete Album bullet is generated
from the deterministic fact packet, so an off-packet Album/Genre reference can
never appear in the delivered report — there is no free-text slot to smuggle
one through. The LLM narrative (if any) is produced by the Orchestrator for
archival purposes only and is NOT part of the delivered payload.

Validation is machine-verifiable against the fact packet:

- the title and run id must match exactly;
- every selected Genre heading and EVERY complete Album bullet
  (``title — artist (year)``) must be present under its own Genre section;
- a Genre heading / Album bullet not in the plan is a fabrication and fails
  closed.

The module depends only on plain report data (run id, genres, albums), not on
the Orchestrator's Plan type, so it stays a leaf dependency.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from omda.ports.errors import ValidationFailureError

MAX_MARKDOWN_LENGTH = 4000

# Required structural markers of a rendered report.
_TITLE_PREFIX = "# 每日音乐发现"
_RUN_PREFIX = "Run: "
_GENRE_HEADING_PREFIX = "## "
_ALBUM_BULLET_PREFIX = "- "
_NOTE_HEADING = "## 说明"


class ReportData:
    """Plain validated report facts used for rendering and validation."""

    def __init__(
        self,
        *,
        run_id: str,
        genres: Sequence[Mapping[str, Any]],
        albums: Sequence[Mapping[str, Any]],
    ) -> None:
        self.run_id = run_id
        self.genres = list(genres)
        self.albums = list(albums)


def render_markdown(data: ReportData) -> str:
    """Render a deterministic structured Markdown report.

    All Genre and Album facts come from ``data`` (the deterministic selection);
    no LLM text is embedded, so nothing outside the plan can be delivered.
    """
    lines: list[str] = [_TITLE_PREFIX, "", f"{_RUN_PREFIX}{data.run_id}", ""]
    lines.append(_NOTE_HEADING)
    lines.append("")
    lines.append("（本次推荐由已确定的选择计划生成：以下流派与专辑为每日发现结果。）")
    lines.append("")
    for genre in data.genres:
        name = genre.get("name", genre.get("genre_id", "?"))
        lines.append(f"{_GENRE_HEADING_PREFIX}{name}")
        lines.append("")
        for album in data.albums:
            if album.get("genre_id") != genre.get(
                "genre_id"
            ) and album.get("genre") != genre.get("genre_id"):
                continue
            lines.append(f"{_ALBUM_BULLET_PREFIX}{_bullet_text(album)}")
        lines.append("")
    body = "\n".join(lines).rstrip() + "\n"
    if len(body) > MAX_MARKDOWN_LENGTH:
        raise ValidationFailureError(
            f"rendered report exceeds {MAX_MARKDOWN_LENGTH} characters"
        )
    return body


def _bullet_text(album: Mapping[str, Any]) -> str:
    title = album.get("title", "?")
    artist = album.get("artist", "?")
    year = album.get("year")
    year_part = f" ({year})" if year else ""
    return f"{title} — {artist}{year_part}"


def validate_markdown(payload: str, data: ReportData) -> None:
    """Validate structure, length and fact references of a rendered report.

    Raises ``ValidationFailureError`` (never returns a failing payload) so the
    delivery boundary refuses anything malformed, oversized or fabricated.
    """
    if not isinstance(payload, str) or not payload.strip():
        raise ValidationFailureError("markdown payload is empty")
    if len(payload) > MAX_MARKDOWN_LENGTH:
        raise ValidationFailureError(
            f"markdown payload exceeds {MAX_MARKDOWN_LENGTH} characters"
        )
    lines = payload.splitlines()
    if not lines or not lines[0].startswith(_TITLE_PREFIX):
        raise ValidationFailureError("markdown payload missing the report title")

    # 0) RUN ID: the report must carry exactly the plan's run id.
    run_line = next((ln for ln in lines if ln.startswith(_RUN_PREFIX)), None)
    if run_line != f"{_RUN_PREFIX}{data.run_id}":
        raise ValidationFailureError(
            f"markdown payload run id mismatch: expected {data.run_id!r}"
        )

    # 1) STRUCTURE + FACT REFERENCES: every selected Genre section and every
    #    COMPLETE Album bullet must appear under its own Genre section.
    known_genres = {g.get("name", g.get("genre_id", "?")) for g in data.genres}
    albums_by_genre: dict[str, set[str]] = {}
    for album in data.albums:
        genre_key = album.get("genre_id") or album.get("genre")
        genre_name = next(
            (
                g.get("name", g.get("genre_id", "?"))
                for g in data.genres
                if g.get("genre_id") == genre_key or g.get("name") == genre_key
            ),
            genre_key,
        )
        albums_by_genre.setdefault(genre_name, set()).add(_bullet_text(album))

    seen_bullets: set[str] = set()
    current_genre: str | None = None
    for line in lines:
        if line.startswith(_GENRE_HEADING_PREFIX):
            heading = line[len(_GENRE_HEADING_PREFIX):].strip()
            if heading == "说明":
                current_genre = None
                continue
            if heading not in known_genres:
                raise ValidationFailureError(f"unknown genre heading in payload: {heading!r}")
            current_genre = heading
            continue
        if line.startswith(_ALBUM_BULLET_PREFIX):
            bullet = line[len(_ALBUM_BULLET_PREFIX):].strip()
            if current_genre is None or current_genre not in albums_by_genre:
                raise ValidationFailureError(
                    f"album bullet outside any selected genre section: {bullet!r}"
                )
            if bullet not in albums_by_genre[current_genre]:
                raise ValidationFailureError(
                    f"album bullet does not match the selected fact packet: {bullet!r}"
                )
            seen_bullets.add(bullet)

    # Every selected Album must actually appear in the payload.
    expected_bullets = {b for bs in albums_by_genre.values() for b in bs}
    missing = expected_bullets - seen_bullets
    if missing:
        raise ValidationFailureError(f"missing album bullet: {sorted(missing)[0]!r}")
    # Every selected Genre section must actually appear.
    missing_genres = known_genres - {
        ln[len(_GENRE_HEADING_PREFIX):].strip()
        for ln in lines
        if ln.startswith(_GENRE_HEADING_PREFIX)
        and ln[len(_GENRE_HEADING_PREFIX):].strip() != "说明"
    }
    if missing_genres:
        raise ValidationFailureError(f"missing genre section: {sorted(missing_genres)[0]!r}")


def build_report_data(
    *,
    run_id: str,
    genres: Sequence[Mapping[str, Any]],
    albums: Sequence[Mapping[str, Any]],
) -> ReportData:
    """Build report facts; each album must carry the genre_id it belongs to."""
    return ReportData(run_id=run_id, genres=genres, albums=albums)


__all__ = [
    "MAX_MARKDOWN_LENGTH",
    "ReportData",
    "build_report_data",
    "render_markdown",
    "validate_markdown",
]
