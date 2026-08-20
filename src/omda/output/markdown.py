"""Markdown report generation and validation (G4 T4.2).

Renders a deterministic, structured Markdown report from the already-selected
plan facts (the LLM narrative is embedded as an untrusted explanatory section)
and validates structure, length and FACT REFERENCES before anything is
delivered (SPEC §3.5, §8; MP §3.6: "LLM 输出必须经过结构、长度和引用事实
验证"). A payload that fails validation MUST NOT be delivered.

The module depends only on plain report data (run id, genres, albums), not on
the Orchestrator's Plan type, so it stays a leaf dependency.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from omda.ports.errors import ValidationFailureError

MAX_MARKDOWN_LENGTH = 4000
MAX_NARRATIVE_LENGTH = 1500

# Required structural markers of a rendered report.
_TITLE_PREFIX = "# 每日音乐发现"
_GENRE_HEADING_PREFIX = "## "
_ALBUM_BULLET_PREFIX = "- "


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


def render_markdown(data: ReportData, narrative: str) -> str:
    """Render a deterministic structured Markdown report.

    The narrative is embedded as untrusted explanatory text; all Genre and
    Album facts come from ``data`` (the deterministic selection), so the LLM
    cannot alter the recommendation through its text.
    """
    if not isinstance(narrative, str) or len(narrative) > MAX_NARRATIVE_LENGTH:
        raise ValidationFailureError(
            f"narrative must be a string of at most {MAX_NARRATIVE_LENGTH} characters"
        )
    lines: list[str] = [_TITLE_PREFIX, "", f"Run: {data.run_id}", ""]
    lines.append("## 说明")
    lines.append("")
    lines.append(narrative.strip() or "（本次推荐说明待补充）")
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
            title = album.get("title", "?")
            artist = album.get("artist", "?")
            year = album.get("year")
            year_part = f" ({year})" if year else ""
            lines.append(f"{_ALBUM_BULLET_PREFIX}{title} — {artist}{year_part}")
        lines.append("")
    body = "\n".join(lines).rstrip() + "\n"
    if len(body) > MAX_MARKDOWN_LENGTH:
        raise ValidationFailureError(
            f"rendered report exceeds {MAX_MARKDOWN_LENGTH} characters"
        )
    return body


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

    # 1) STRUCTURE: every selected Genre heading and every selected Album
    #    bullet must be present (the LLM cannot silently drop a fact).
    text = payload
    for genre in data.genres:
        name = genre.get("name", genre.get("genre_id", "?"))
        if f"{_GENRE_HEADING_PREFIX}{name}" not in text:
            raise ValidationFailureError(f"missing genre section: {name!r}")
    for album in data.albums:
        title = album.get("title", "?")
        if f"{_ALBUM_BULLET_PREFIX}{title}" not in text:
            raise ValidationFailureError(f"missing album bullet: {title!r}")

    # 2) FACT REFERENCES: a Genre heading / Album bullet that is NOT part of
    #    the selected plan is a fabrication and fails closed.
    known_genres = {g.get("name", g.get("genre_id", "?")) for g in data.genres}
    for line in lines:
        if line.startswith(_GENRE_HEADING_PREFIX):
            heading = line[len(_GENRE_HEADING_PREFIX):].strip()
            if heading not in known_genres and heading != "说明":
                raise ValidationFailureError(f"unknown genre heading in payload: {heading!r}")
    known_albums = {a.get("title", "?") for a in data.albums}
    for line in lines:
        if line.startswith(_ALBUM_BULLET_PREFIX):
            bullet = line[len(_ALBUM_BULLET_PREFIX):]
            title = re.split(r" — ", bullet, maxsplit=1)[0].strip()
            if title not in known_albums:
                raise ValidationFailureError(f"unknown album bullet in payload: {title!r}")


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
    "MAX_NARRATIVE_LENGTH",
    "ReportData",
    "build_report_data",
    "render_markdown",
    "validate_markdown",
]
