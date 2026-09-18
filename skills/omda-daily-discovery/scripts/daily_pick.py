#!/usr/bin/env python3
"""OMDA Skill Beta — Daily Discovery (Personal Markdown Mode).

One album per day, chosen deterministically from the OMDA Source Markdown
files the user selects via repeatable ``--source`` arguments.

Hard boundaries (ADR-0003, in particular section 10):

- This is the OMDA companion mode ("one album a day"), NOT the full 3x3
  engine. It never touches ``src/omda``, the SQLite official history, or any
  network API.
- Ratings, notes, profile free text and per-source *content* digests are
  display/audit only. The selection seed material uses ONLY the admissible
  selection-pool digest (normalized identity + resolved genre after
  eligibility and anti-repeat filtering), per constraint C1.
- Source frontmatter is a restricted OMDA flat format, NOT general YAML
  (constraint C2): nested values, sequences, tags, anchors, aliases,
  duplicate and unknown fields are rejected.
- There is no public date override; the clock is a test seam (ADR3-003 /
  AC-27).
- The atomic history replacement is the official commit point; daily output
  is rendered from committed history.

Exit codes: 0 ok (including same-day replay), 2 input/validation error,
3 history corruption, 4 collection exhausted.

Requires Python >= 3.9. Standard library only, zero network.
"""

import argparse
import datetime
import hashlib
import json
import os
import re
import sys
import tempfile
import unicodedata
from pathlib import Path

ALGORITHM_VERSION = 1
HISTORY_SCHEMA_VERSION = 2
SOURCE_FORMAT_VERSION = 1

EXIT_OK = 0
EXIT_INPUT_ERROR = 2
EXIT_HISTORY_CORRUPT = 3
EXIT_EXHAUSTED = 4

# Restricted flat frontmatter (C2): exactly these keys, scalar values only.
SOURCE_META_REQUIRED = ("source_id", "display_name", "curator", "provenance",
                        "sharing_note", "format_version")
SOURCE_META_OPTIONAL = ("rating_scale",)
SOURCE_META_ALLOWED = SOURCE_META_REQUIRED + SOURCE_META_OPTIONAL
SOURCE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
# YAML-feature markers that must never start a value (anchors, aliases,
# tags, flow collections, block scalars, directives, quotes).
_FORBIDDEN_VALUE_STARTS = ("&", "*", "!", "[", "]", "{", "}", "|", ">",
                           "%", "@", "`", '"', "'")
_FRONTMATTER_KEY_RE = re.compile(r"^([A-Za-z][A-Za-z0-9_-]*):[ ]?(.*)$")

# Header alias sets. A header cell matches a field when its NFC, lowercased,
# whitespace-stripped form equals one of the aliases.
_HEADER_ALIASES = {
    "artist": ("artist", "artist艺人", "艺人"),
    "album": ("album", "album专辑", "专辑"),
    "year": ("year", "year年份", "年份"),
    "genre": ("genre", "genre流派", "流派"),
    "rating": ("rating", "rating评分", "评分"),
    "note": ("note", "note备注", "备注"),
    "status": ("status", "status状态", "状态"),
}
_REQUIRED_SOURCE_HEADERS = ("artist", "album")
_REQUIRED_PROFILE_HEADERS = ("artist", "album", "status")

_STATUS_ALIASES = {
    "heard": ("heard", "heard已听", "已听"),
    "skip": ("skip", "skip跳过", "跳过"),
}

_GENRE_SPLIT_RE = re.compile(r"[、,，;；/]")
_UNCATEGORIZED = "uncategorized"

DOMAIN_SOURCE_CONTENT = b"omda-skill-source-content-v1"
DOMAIN_SELECTION_POOL = b"omda-skill-selection-pool-v1"
DOMAIN_SEED = b"omda-skill-seed-v1"
DOMAIN_UNIFORM = b"omda-skill-uniform-v1"

DISCLAIMER_ZH = ("本推荐来自 OMDA Skill Beta（个人 Markdown 模式）：一天一张、"
                 "来自你自己选择的来源清单。它不是 OMDA 完整的 3 Genre × 3 "
                 "Album 引擎，两者规则与历史互不通用。")
DISCLAIMER_EN = ("This recommendation comes from OMDA Skill Beta (Personal "
                 "Markdown Mode): one album per day, from source lists you "
                 "selected. It is NOT the full OMDA 3 Genre × 3 Album engine; "
                 "the two share neither rules nor history.")

EXHAUSTED_ZH = ("清单已耗尽：所有条目都已听过、跳过或已被推荐过。"
                "请向你的来源清单添加新条目后明天再试。")
EXHAUSTED_EN = ("The collection is exhausted: every entry has been heard, "
                "skipped, or already recommended. Add new entries to your "
                "source lists and come back tomorrow.")

TEMPLATE_FILES = (
    "OMDA_SOURCE.template.zh-CN.md",
    "OMDA_SOURCE.template.en.md",
    "OMDA_PROFILE.template.zh-CN.md",
    "OMDA_PROFILE.template.en.md",
)


class OmdaError(Exception):
    """Domain error with a stable exit code."""

    def __init__(self, message, exit_code=EXIT_INPUT_ERROR):
        super().__init__(message)
        self.exit_code = exit_code


# ---------------------------------------------------------------------------
# Clock seam (test-only injection; there is no public date override)
# ---------------------------------------------------------------------------

def now_local():
    """Return the current local time as an aware datetime (test seam)."""
    return datetime.datetime.now().astimezone()


# ---------------------------------------------------------------------------
# Text normalization / identity
# ---------------------------------------------------------------------------

def normalize_text(value):
    """NFC -> lower -> collapse whitespace -> strip surrounding punctuation."""
    text = unicodedata.normalize("NFC", value).lower()
    text = " ".join(text.split())
    while text and unicodedata.category(text[0]).startswith("P"):
        text = text[1:]
    while text and unicodedata.category(text[-1]).startswith("P"):
        text = text[:-1]
    return text.strip()


def identity_key(artist, album):
    return normalize_text(artist) + "|" + normalize_text(album)


def _norm_header(cell):
    return unicodedata.normalize("NFC", cell).lower().replace(" ", "")


def _match_header(cell, field):
    return _norm_header(cell) in _HEADER_ALIASES[field]


def _header_matches(cells, required_fields):
    """True when every required field matches at least one header cell."""
    return all(any(_match_header(cell, field) for cell in cells)
               for field in required_fields)


def genre_group_key(raw_genre):
    text = unicodedata.normalize("NFC", raw_genre or "").strip()
    if not text:
        return _UNCATEGORIZED
    first = _GENRE_SPLIT_RE.split(text)[0].strip()
    return first or _UNCATEGORIZED


# ---------------------------------------------------------------------------
# Restricted flat frontmatter parsing (C2) — this is NOT general YAML
# ---------------------------------------------------------------------------

def parse_source_frontmatter(text, path_name):
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise OmdaError("%s: source frontmatter must start with '---' line"
                        % path_name)
    end = None
    for idx in range(1, len(lines)):
        if lines[idx].strip() == "---":
            end = idx
            break
    if end is None:
        raise OmdaError("%s: unterminated frontmatter (no closing '---')"
                        % path_name)
    meta = {}
    for lineno, line in zip(range(2, end + 1), lines[1:end]):
        if not line.strip():
            continue
        match = _FRONTMATTER_KEY_RE.match(line)
        if match is None:
            raise OmdaError(
                "%s: frontmatter line %d is not a flat 'key: value' pair "
                "(indentation, nested values, sequences, tags, anchors and "
                "aliases are rejected): %r" % (path_name, lineno, line))
        key, value = match.group(1), match.group(2).strip()
        if key not in SOURCE_META_ALLOWED:
            raise OmdaError("%s: unknown frontmatter field %r (line %d); "
                            "allowed fields: %s"
                            % (path_name, key, lineno,
                               ", ".join(SOURCE_META_ALLOWED)))
        if key in meta:
            raise OmdaError("%s: duplicate frontmatter field %r (line %d)"
                            % (path_name, key, lineno))
        if not value:
            raise OmdaError("%s: frontmatter field %r has an empty value "
                            "(line %d)" % (path_name, key, lineno))
        if value.startswith(_FORBIDDEN_VALUE_STARTS):
            raise OmdaError("%s: frontmatter value for %r (line %d) starts "
                            "with a reserved YAML-feature character; this "
                            "format accepts flat scalars only"
                            % (path_name, key, lineno))
        meta[key] = value
    missing = [key for key in SOURCE_META_REQUIRED if key not in meta]
    if missing:
        raise OmdaError("%s: missing required frontmatter fields: %s"
                        % (path_name, ", ".join(missing)))
    if meta["format_version"] != str(SOURCE_FORMAT_VERSION):
        raise OmdaError("%s: unsupported format_version %r (this build "
                        "supports %d)" % (path_name, meta["format_version"],
                                          SOURCE_FORMAT_VERSION))
    if not SOURCE_ID_RE.match(meta["source_id"]):
        raise OmdaError("%s: invalid source_id %r (must match "
                        "[a-z0-9][a-z0-9-]*)" % (path_name,
                                                 meta["source_id"]))
    return meta


# ---------------------------------------------------------------------------
# Markdown table parsing (fenced blocks are skipped; blank rows ignored)
# ---------------------------------------------------------------------------

def _split_row(line):
    cells = line.strip().split("|")
    if cells and cells[0] == "":
        cells = cells[1:]
    if cells and cells[-1] == "":
        cells = cells[:-1]
    return [cell.strip() for cell in cells]


def _is_separator_row(cells):
    return any(cells) and all(re.fullmatch(r":?-{3,}:?", cell)
                              for cell in cells)


def parse_album_table(text, path_name, required_fields, kind):
    """Parse the FIRST matching Markdown table into a list of dict rows.

    Rules:
    - Lines inside fenced code blocks (``` ... ```) are skipped, so example
      blocks can never become candidates (AC-29).
    - Fully blank rows are ignored; a partially filled row missing a required
      field fails closed with its line number.
    - Only the first matching header's table is parsed (documented).
    """
    lines = text.splitlines()
    header = None
    header_fields = None
    rows = []
    in_fence = False
    for lineno, line in enumerate(lines, start=1):
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if "|" not in line:
            if header is not None and line.strip():
                break  # non-blank non-table line ends the table
            continue
        cells = _split_row(line)
        if header is None:
            if not any(cells):
                continue
            if _header_matches(cells, required_fields):
                header = cells
                header_fields = []
                for cell in header:
                    matched = None
                    for field in _HEADER_ALIASES:
                        if _match_header(cell, field):
                            matched = field
                            break
                    header_fields.append(matched)
            continue
        if _is_separator_row(cells):
            continue
        if not any(cells):
            continue  # fully blank rows are ignored
        if cells == header:
            break  # a repeated header row starts a different table
        if len(cells) != len(header):
            raise OmdaError(
                "%s: table row at line %d has %d cells but the header has %d"
                % (path_name, lineno, len(cells), len(header)))
        row = {}
        for field, cell in zip(header_fields, cells):
            if field is not None:
                row[field] = cell
        missing = [field for field in required_fields if not row.get(field)]
        if missing:
            raise OmdaError(
                "%s: table row at line %d is missing required field(s): %s "
                "(fail-closed; fill the values or delete the row)"
                % (path_name, lineno, ", ".join(missing)))
        rows.append(row)
    if header is None:
        raise OmdaError("%s: no %s table with header column(s) %s found"
                        % (path_name, kind, "/".join(required_fields)))
    return rows


# ---------------------------------------------------------------------------
# Source / profile loading
# ---------------------------------------------------------------------------

class SourceData(object):
    def __init__(self, meta, records, content_digest, path):
        self.meta = meta
        self.records = records  # list of dict, file order
        self.content_digest = content_digest  # audit only (C1)
        self.path = path

    @property
    def source_id(self):
        return self.meta["source_id"]

    @property
    def display_name(self):
        return self.meta["display_name"]


def compute_source_content_digest(meta, records):
    """Per-source *content* digest — audit only, never enters the seed (C1)."""
    digest = hashlib.sha256()
    digest.update(DOMAIN_SOURCE_CONTENT + b"\n")
    for key in SOURCE_META_ALLOWED:
        raw = unicodedata.normalize("NFC",
                                    meta.get(key, "")).encode("utf-8")
        digest.update(len(raw).to_bytes(8, "big"))
        digest.update(raw)
    for record in records:
        for field in ("artist", "album", "year", "genre", "rating", "note"):
            raw = unicodedata.normalize("NFC",
                                        record.get(field, "")).encode("utf-8")
            digest.update(len(raw).to_bytes(8, "big"))
            digest.update(raw)
    return digest.hexdigest()


def load_source(path):
    path = Path(path)
    if not path.is_file():
        raise OmdaError("source file not found: %s" % path)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise OmdaError("cannot read source file %s: %s" % (path, exc))
    meta = parse_source_frontmatter(text, str(path))
    rows = parse_album_table(text, str(path), _REQUIRED_SOURCE_HEADERS,
                             "source album")
    records = []
    for row in rows:
        records.append({
            "artist": row["artist"],
            "album": row["album"],
            "year": row.get("year", ""),
            "genre": row.get("genre", ""),
            "rating": row.get("rating", ""),
            "note": row.get("note", ""),
        })
    return SourceData(meta, records,
                      compute_source_content_digest(meta, records), path)


def _has_status_table(text):
    in_fence = False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence or "|" not in line:
            continue
        cells = _split_row(line)
        if any(cells) and _header_matches(cells,
                                          _REQUIRED_PROFILE_HEADERS):
            return True
    return False


def load_profile_status(path):
    """Read ONLY the structured heard/skip table from the profile.

    Free-text profile sections are never read here (ADR3-001): they exist
    for the Agent's explanation only.
    """
    path = Path(path)
    if not path.is_file():
        raise OmdaError("profile file not found: %s" % path)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise OmdaError("cannot read profile file %s: %s" % (path, exc))
    if not _has_status_table(text):
        return {}  # a profile without a status table excludes nothing
    rows = parse_album_table(text, str(path), _REQUIRED_PROFILE_HEADERS,
                             "profile status")
    status = {}
    for row in rows:
        raw_status = _norm_header(row["status"])
        mapped = None
        for canonical, aliases in _STATUS_ALIASES.items():
            if raw_status in aliases:
                mapped = canonical
                break
        if mapped is None:
            raise OmdaError("%s: unknown status %r for %s (allowed: heard, "
                            "skip)" % (path, row["status"], row["artist"]))
        status[identity_key(row["artist"], row["album"])] = mapped
    return status


# ---------------------------------------------------------------------------
# In-memory merge (sources stay read-only; nothing is written back)
# ---------------------------------------------------------------------------

def merge_sources(sources):
    """Merge sources into a deduplicated candidate pool.

    - Same identity key across any number of occurrences -> ONE candidate;
      occurrence count never increases selection probability (AC-20).
    - Per-source rating/note/attribution are kept separately (AC-21).
    - A conflict on the selection-relevant Genre fails closed and reports
      every involved source's value (AC-22).
    """
    occurrences = {}
    for source in sorted(sources, key=lambda item: item.source_id):
        for order, record in enumerate(source.records):
            key = identity_key(record["artist"], record["album"])
            group = genre_group_key(record["genre"])
            occurrences.setdefault(key, []).append({
                "identity_key": key,
                "artist": record["artist"],
                "album": record["album"],
                "genre_group": group,
                "annotation": {
                    "source_id": source.source_id,
                    "source_display_name": source.display_name,
                    "rating": record["rating"],
                    "note": record["note"],
                    "year": record["year"],
                    "order": order,
                },
            })
    candidates = {}
    conflicts = {}
    for key, occs in occurrences.items():
        groups = sorted({occ["genre_group"] for occ in occs})
        if len(groups) > 1:
            conflicts[key] = occs
            continue
        annotations = [occ["annotation"] for occ in occs]
        candidates[key] = {
            "identity_key": key,
            "artist": occs[0]["artist"],
            "album": occs[0]["album"],
            "genre_group": groups[0],
            "annotations": annotations,
        }
    if conflicts:
        details = []
        for key in sorted(conflicts):
            per_source = ", ".join(
                "%s=%s" % (occ["annotation"]["source_id"],
                           occ["genre_group"])
                for occ in sorted(conflicts[key],
                                  key=lambda occ:
                                  occ["annotation"]["source_id"]))
            details.append("%s (%s)" % (key, per_source))
        raise OmdaError(
            "selection-relevant Genre conflict for duplicate album identity; "
            "resolve the sources before running (fail-closed, nothing was "
            "selected or committed): %s" % "; ".join(details))
    return candidates


# ---------------------------------------------------------------------------
# History (versioned JSON; atomic replacement = official commit point)
# ---------------------------------------------------------------------------

_HISTORY_RECORD_TYPES = {
    "day_key": str,
    "timezone_evidence": dict,
    "selected": dict,
    "source_ids": list,
    "source_display_names": dict,
    "per_source_content_digests": dict,
    "selection_pool_digest": str,
    "seed_material_digest": str,
    "algorithm_version": int,
    "schema_version": int,
    "selected_at": str,
}


def _validate_history(data):
    if not isinstance(data, dict):
        raise ValueError("history root is not an object")
    if data.get("schema_version") != HISTORY_SCHEMA_VERSION:
        raise ValueError("unsupported history schema_version %r"
                         % data.get("schema_version"))
    if data.get("algorithm_version") != ALGORITHM_VERSION:
        raise ValueError("unsupported algorithm_version %r"
                         % data.get("algorithm_version"))
    days = data.get("days")
    if not isinstance(days, dict):
        raise ValueError("history 'days' is not an object")
    day_key_re = re.compile(r"^\d{4}-\d{2}-\d{2}$")
    for day_key, record in days.items():
        if not day_key_re.match(day_key):
            raise ValueError("invalid day key %r" % day_key)
        if not isinstance(record, dict):
            raise ValueError("day %s record is not an object" % day_key)
        for name, expected in _HISTORY_RECORD_TYPES.items():
            if name not in record or not isinstance(record[name], expected):
                raise ValueError("day %s field %r missing or wrong type"
                                 % (day_key, name))


def load_history(path):
    path = Path(path)
    if not path.exists():
        return {"schema_version": HISTORY_SCHEMA_VERSION,
                "algorithm_version": ALGORITHM_VERSION, "days": {}}
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise OmdaError("cannot read history file %s: %s" % (path, exc),
                        EXIT_HISTORY_CORRUPT)
    try:
        data = json.loads(raw.decode("utf-8"))
        _validate_history(data)
    except (ValueError, UnicodeDecodeError) as exc:
        stamp = now_local().strftime("%Y%m%dT%H%M%S%z")
        corrupt = path.parent / ("history.corrupt-%s.json" % stamp)
        kept = ""
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            corrupt.write_bytes(raw)
            kept = " (corrupt copy kept at %s)" % corrupt
        except OSError:
            pass
        raise OmdaError(
            "history file %s is corrupt or unsupported (%s); refusing to run "
            "(fail-closed, nothing was overwritten)%s. Restore from backup or "
            "repair it manually; do NOT delete it."
            % (path, exc, kept), EXIT_HISTORY_CORRUPT)
    return data


def _atomic_write(path, data_bytes):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=".omda-",
                                    suffix=".tmp")
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data_bytes)
        os.replace(str(tmp_path), str(path))
    except BaseException:
        try:
            tmp_path.unlink()
        except OSError:
            pass
        raise


def atomic_write_history(path, data):
    """Atomically replace the history file. This IS the commit point."""
    payload = (json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True)
               + "\n").encode("utf-8")
    _atomic_write(path, payload)


def atomic_write_text(path, text):
    _atomic_write(path, text.encode("utf-8"))


# ---------------------------------------------------------------------------
# Deterministic selection protocol (versioned; C1 digest separation)
# ---------------------------------------------------------------------------

def _length_prefix(value):
    raw = unicodedata.normalize("NFC", value).encode("utf-8")
    return len(raw).to_bytes(8, "big") + raw


def selection_pool_digest(admissible):
    """Digest of the *selection canonical projection*: normalized identity
    plus resolved genre of every admissible candidate, sorted. Nothing else
    (no ratings, notes, years, display names, paths, CLI order) enters here
    (C1)."""
    digest = hashlib.sha256()
    digest.update(DOMAIN_SELECTION_POOL + b"\n")
    for key, group in sorted(admissible):
        digest.update(_length_prefix(key))
        digest.update(_length_prefix(group))
    return digest.hexdigest()


def seed_material_digest(day_key, pool_digest, consumed_picks):
    digest = hashlib.sha256()
    digest.update(DOMAIN_SEED + b"\n")
    digest.update(_length_prefix(str(ALGORITHM_VERSION)))
    digest.update(_length_prefix(day_key))
    digest.update(_length_prefix(pool_digest))
    digest.update(_length_prefix(str(consumed_picks)))
    return digest.hexdigest()


def uniform_index(seed_hex, stage, count):
    """Versioned unbiased uniform index in [0, count): domain-separated
    SHA-256 bytes with rejection sampling. Independent of random.Random call
    sequences, hash ordering, or Python version."""
    if count <= 0:
        raise OmdaError("internal invariant failure: empty selection range")
    limit = (2 ** 64 // count) * count
    material = seed_hex.encode("ascii")
    counter = 0
    while True:
        digest = hashlib.sha256()
        digest.update(DOMAIN_UNIFORM + b"\n")
        digest.update(stage + b"\n")
        digest.update(material)
        digest.update(("\n%d\n" % counter).encode("ascii"))
        value = int.from_bytes(digest.digest()[:8], "big")
        if value < limit:
            return value % count
        counter += 1
        if counter > 100000:
            raise OmdaError("internal invariant failure: rejection sampling "
                            "did not terminate")


def select(admissible_keys_by_group, last_group, day_key, consumed_picks):
    """Two-stage equal-opportunity selection over the admissible pool.

    Returns (chosen_group, chosen_key, pool_digest, seed_hex, forced_note).
    Anti-repeat rule: the immediately preceding successful pick's genre group
    is removed when more than one admissible group exists; if only one
    admissible group remains, it is used with an explicit forced note.
    """
    groups = sorted(admissible_keys_by_group)
    if not groups:
        raise OmdaError("internal invariant failure: no admissible groups")
    pool = []
    for group in groups:
        for key in sorted(admissible_keys_by_group[group]):
            pool.append((key, group))
    pool_digest = selection_pool_digest(pool)
    seed_hex = seed_material_digest(day_key, pool_digest, consumed_picks)
    usable = list(groups)
    forced_note = None
    if len(usable) > 1 and last_group is not None and last_group in usable:
        usable = [group for group in usable if group != last_group]
        if len(usable) == 1:
            forced_note = ("only one admissible genre group remains "
                           "(anti-repeat rule waived)")
    group_index = uniform_index(seed_hex, b"genre", len(usable))
    chosen_group = usable[group_index]
    keys = sorted(admissible_keys_by_group[chosen_group])
    album_index = uniform_index(seed_hex, b"album", len(keys))
    return chosen_group, keys[album_index], pool_digest, seed_hex, forced_note


# ---------------------------------------------------------------------------
# Rendering (deterministic; no volatile timestamps in the payload)
# ---------------------------------------------------------------------------

def render_day(record, lang):
    """Deterministically render the committed day record. The rendered bytes
    are identical for the original write and any same-day re-render; no
    volatile data (including replay notes) enters the payload."""
    selected = record["selected"]
    zh = (lang != "en")
    lines = ["> " + DISCLAIMER_ZH, ">", "> " + DISCLAIMER_EN, ""]
    lines.append("## 今天的推荐" if zh else "## Today's pick")
    lines.append("")
    year = selected.get("year") or ("（留空）" if zh else "(blank)")
    if zh:
        lines.append("- 艺人 Artist：%s" % selected["artist"])
        lines.append("- 专辑 Album：%s" % selected["album"])
        lines.append("- 年份 Year：%s" % year)
        lines.append("- 流派分组 Genre group：%s" % selected["genre_group"])
        lines.append("- 来源 Source：%s — %s"
                     % (selected["source_id"],
                        selected["source_display_name"]))
    else:
        lines.append("- Artist: %s" % selected["artist"])
        lines.append("- Album: %s" % selected["album"])
        lines.append("- Year: %s" % year)
        lines.append("- Genre group: %s" % selected["genre_group"])
        lines.append("- Source: %s — %s"
                     % (selected["source_id"],
                        selected["source_display_name"]))
    if selected.get("annotations"):
        lines.append("")
        lines.append("来源注记（仅展示）：" if zh
                     else "Source notes (display only):")
        for ann in selected["annotations"]:
            rating = ann["rating"] or ("—" if zh else "-")
            note = ann["note"] or ("—" if zh else "-")
            lines.append("- %s — %s：Rating %s / Note %s"
                         % (ann["source_id"], ann["source_display_name"],
                            rating, note))
    if selected.get("forced_note"):
        lines.append("")
        lines.append("Note: %s" % selected["forced_note"])
    lines.append("")
    lines.append("Day key: %s (%s)"
                 % (record["day_key"],
                    record["timezone_evidence"].get("utc_offset", "")))
    lines.append("Algorithm version: %s" % record["algorithm_version"])
    lines.append("Selection pool digest: %s" % record["selection_pool_digest"])
    lines.append("Per-source content digests (audit only):")
    for sid in record["source_ids"]:
        lines.append("  - %s: %s"
                     % (sid, record["per_source_content_digests"].get(sid, "")))
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_arg_parser():
    parser = argparse.ArgumentParser(
        prog="daily_pick.py",
        description="OMDA Skill Beta daily deterministic pick (one album per "
                    "day from user-selected OMDA Source Markdown files).")
    parser.add_argument("--profile", required=True,
                        help="path to profile/MY_PROFILE.md")
    parser.add_argument("--source", action="append", required=True,
                        metavar="SOURCE_MD",
                        help="OMDA Source Markdown file; repeatable")
    parser.add_argument("--history", required=True,
                        help="path to the private history JSON")
    parser.add_argument("--output-dir", required=True,
                        help="directory for the daily output Markdown")
    parser.add_argument("--template-dir", default=None,
                        help="optional path to the bundled templates; when "
                             "given it is validated so an Agent can copy a "
                             "new source template for the user")
    parser.add_argument("--lang", choices=("zh", "en"), default="zh",
                        help="output language")
    return parser


def _validate_template_dir(template_dir):
    base = Path(template_dir)
    if not base.is_dir():
        raise OmdaError("template dir not found: %s" % base)
    for name in TEMPLATE_FILES:
        if not (base / name).is_file():
            raise OmdaError("template dir %s is missing %s" % (base, name))


def _check_unique_source_paths(paths):
    seen = set()
    for path in paths:
        resolved = str(Path(path))
        if resolved in seen:
            raise OmdaError("source file passed twice: %s" % path)
        seen.add(resolved)


def _utc_offset_string(now):
    raw = now.strftime("%z")
    if not raw:
        return "+00:00"
    return raw[0] + raw[1:3] + ":" + raw[3:5]


def run(args):
    now = now_local()
    day_key = now.date().isoformat()

    history = load_history(args.history)
    days = history["days"]

    if day_key in days:
        # Same-day replay: return the committed result. The source set and
        # the result are locked for today; provided --source arguments are
        # intentionally NOT read (they may even point to files that no
        # longer exist — that must not matter).
        record = days[day_key]
        text = render_day(record, args.lang)
        out_path = Path(args.output_dir) / ("%s.md" % day_key)
        atomic_write_text(out_path, text)
        names = ", ".join(
            "%s — %s" % (sid, record["source_display_names"].get(sid, sid))
            for sid in record["source_ids"])
        print("already committed today: %s (source set locked: %s)"
              % (day_key, names))
        print("The --source arguments of this run were ignored; "
              "nothing was re-drawn." if args.lang == "en" else
              "本次运行提供的 --source 参数被忽略，没有重新抽取。")
        print("output: %s" % out_path)
        return EXIT_OK

    if args.template_dir:
        _validate_template_dir(args.template_dir)

    _check_unique_source_paths(args.source)
    sources = [load_source(path) for path in args.source]
    source_ids = [source.source_id for source in sources]
    if len(set(source_ids)) != len(source_ids):
        raise OmdaError("duplicate source_id across selected sources: %s"
                        % ", ".join(sorted(source_ids)))

    status = load_profile_status(args.profile)
    pool = merge_sources(sources)

    # Eligibility: personal status table + permanent recommendation history.
    permanent = set()
    for record in days.values():
        permanent.add(record["selected"]["identity_key"])
    admissible = [cand for key, cand in sorted(pool.items())
                  if status.get(key) not in ("heard", "skip")
                  and key not in permanent]
    if not admissible:
        print(EXHAUSTED_EN if args.lang == "en" else EXHAUSTED_ZH)
        print("Day key: %s" % day_key)
        return EXIT_EXHAUSTED

    by_group = {}
    for cand in admissible:
        by_group.setdefault(cand["genre_group"], []).append(cand["identity_key"])

    last_group = None
    if days:
        latest_day = max(days)
        last_group = days[latest_day]["selected"]["genre_group"]
    groups_before = sorted(by_group)
    chosen_group, chosen_key, pool_digest, seed_hex, forced_note = \
        select(by_group, last_group, day_key, len(days))
    if len(groups_before) > 1 and last_group is not None \
            and last_group in groups_before and chosen_group == last_group:
        raise OmdaError("internal invariant failure: anti-repeat rule "
                        "violated")

    candidate = pool[chosen_key]
    annotations = sorted(candidate["annotations"],
                         key=lambda ann: (ann["source_id"], ann["order"]))
    first = annotations[0]
    selected = {
        "identity_key": chosen_key,
        "artist": candidate["artist"],
        "album": candidate["album"],
        "year": first["year"],
        "genre_group": chosen_group,
        "source_id": first["source_id"],
        "source_display_name": first["source_display_name"],
        "annotations": annotations,
        "forced_note": forced_note,
    }
    record = {
        "day_key": day_key,
        "timezone_evidence": {
            "utc_offset": _utc_offset_string(now),
            "local_iso": now.isoformat(timespec="seconds"),
            "utc_iso": now.astimezone(datetime.timezone.utc).isoformat(
                timespec="seconds"),
        },
        "selected": selected,
        "source_ids": source_ids,
        "source_display_names": {source.source_id: source.display_name
                                 for source in sources},
        "per_source_content_digests": {source.source_id:
                                       source.content_digest
                                       for source in sources},
        "selection_pool_digest": pool_digest,
        "seed_material_digest": seed_hex,
        "algorithm_version": ALGORITHM_VERSION,
        "schema_version": HISTORY_SCHEMA_VERSION,
        "selected_at": now.isoformat(timespec="seconds"),
    }

    # Official commit point: atomic history replacement. If this fails,
    # nothing is reported as a successful recommendation.
    days[day_key] = record
    atomic_write_history(Path(args.history), history)

    # Output is rendered from committed history; if this write fails, the
    # next run re-renders the same bytes without a new selection.
    text = render_day(record, args.lang)
    out_path = Path(args.output_dir) / ("%s.md" % day_key)
    atomic_write_text(out_path, text)
    print("committed %s: %s — %s (%s)"
          % (day_key, selected["artist"], selected["album"], chosen_group))
    print("output: %s" % out_path)
    return EXIT_OK


def main(argv=None):
    args = build_arg_parser().parse_args(argv)
    try:
        return run(args)
    except OmdaError as exc:
        print("omda-skill: %s" % exc, file=sys.stderr)
        return exc.exit_code


if __name__ == "__main__":
    sys.exit(main())
