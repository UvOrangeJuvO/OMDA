#!/usr/bin/env python3
"""One-time curation tool (G3-007-002): fetch verified MusicBrainz release-group
MBIDs for the curated-omda Album package.

This is DATA PREPARATION, not a runtime source: it is run manually by a human,
respects MusicBrainz's ~1 req/s pacing with a contactable User-Agent, and every
accepted match must be primary-type Album with a strong title/artist/year match.
The output is reviewed and committed into the curated package; no live source is
implemented (ADR-0002 §8.1: ODP-1 undecided).

Usage: python tools/curate_mbids.py  -> prints JSON {album_id: {...}}
"""

from __future__ import annotations

import json
import re
import sys
import time
import urllib.parse
import urllib.request

USER_AGENT = "OMDA-curation/0.1 (mailto:omda-curation@example.invalid)"
API = "https://musicbrainz.org/ws/2/release-group"
PACING = 1.1  # seconds between queries (>= 1 req/s guidance)

# (album_id, title, artist, year, genre_id)
ALBUMS = [
    ("curated-omda-ambient-0001", "Ambient 1: Music for Airports", "Brian Eno", 1978, "ambient"),
    ("curated-omda-ambient-0002", "Selected Ambient Works 85-92", "Aphex Twin", 1992, "ambient"),
    (
        "curated-omda-ambient-0003",
        "And Their Refinement of the Decline",
        "Stars of the Lid",
        2007,
        "ambient",
    ),
    ("curated-omda-ambient-0004", "The Pearl", "Harold Budd & Brian Eno", 1984, "ambient"),
    ("curated-omda-bebop-0001", "Brilliant Corners", "Thelonious Monk", 1957, "bebop"),
    ("curated-omda-bebop-0002", "Birth of the Cool", "Miles Davis", 1957, "bebop"),
    ("curated-omda-bebop-0003", "Charlie Parker with Strings", "Charlie Parker", 1950, "bebop"),
    ("curated-omda-bebop-0004", "The Amazing Bud Powell", "Bud Powell", 1951, "bebop"),
    ("curated-omda-krautrock-0001", "Autobahn", "Kraftwerk", 1974, "krautrock"),
    ("curated-omda-krautrock-0002", "Tago Mago", "Can", 1971, "krautrock"),
    ("curated-omda-krautrock-0003", "Neu!", "Neu!", 1972, "krautrock"),
    ("curated-omda-krautrock-0004", "Faust IV", "Faust", 1973, "krautrock"),
    ("curated-omda-tuareg-0001", "Aman Iman", "Tinariwen", 2007, "tuareg-music"),
    ("curated-omda-tuareg-0002", "Tassili", "Tinariwen", 2011, "tuareg-music"),
    ("curated-omda-tuareg-0003", "Ilana: The Creator", "Mdou Moctar", 2019, "tuareg-music"),
    ("curated-omda-tuareg-0004", "Chatma", "Tamikrest", 2013, "tuareg-music"),
    ("curated-omda-idm-0001", "Tri Repetae", "Autechre", 1995, "idm"),
    ("curated-omda-idm-0002", "Music Has the Right to Children", "Boards of Canada", 1998, "idm"),
    ("curated-omda-idm-0003", "Hard Normal Daddy", "Squarepusher", 1997, "idm"),
    ("curated-omda-idm-0004", "Los Angeles", "Flying Lotus", 2008, "idm"),
]


def _norm(value: str) -> str:
    """Light normalization for matching (not canonical identity)."""
    value = value.lower()
    value = re.sub(r"[^\w\s]", "", value)
    return re.sub(r"\s+", " ", value).strip()


def _fetch(title: str, artist: str) -> dict:
    query = urllib.parse.urlencode(
        {
            "query": f'release:"{title}" AND artist:"{artist}"',
            "fmt": "json",
            "limit": "5",
        }
    )
    url = f"{API}?{query}"
    last_error: Exception | None = None
    for attempt in range(4):  # transient 503/429/network retries with backoff
        try:
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            last_error = exc
            if exc.code not in (429, 503):
                raise
        except (urllib.error.URLError, TimeoutError) as exc:
            last_error = exc
        time.sleep(3 * (attempt + 1))  # bounded backoff before retry
    raise RuntimeError(f"musicbrainz query failed for {title!r}: {last_error}")


def _match(item: dict, title: str, artist: str, year: int) -> dict | None:
    if item.get("primary-type") != "Album":
        return None
    item_title = item.get("title", "")
    names = [c.get("name", "") for c in item.get("artist-credit", [])]
    item_artist = " ".join(names)
    if _norm(item_title) != _norm(title):
        return None
    if _norm(item_artist) != _norm(artist):
        return None
    first_date = item.get("first-release-date") or ""
    item_year = int(first_date[:4]) if first_date[:4].isdigit() else None
    if item_year is not None and item_year != year:
        return None
    score = item.get("score")
    if not isinstance(score, (int, float)) or score < 90:
        return None
    return {"mbid": item["id"], "score": score, "year": item_year}


def main() -> int:
    results: dict[str, dict] = {}
    for album_id, title, artist, year, genre in ALBUMS:
        data = _fetch(title, artist)
        items = data.get("release-groups", [])
        best = None
        for item in items:
            best = _match(item, title, artist, year)
            if best is not None:
                break
        results[album_id] = {
            "title": title,
            "artist": artist,
            "year": year,
            "genre_id": genre,
            "mbid": best["mbid"] if best else None,
            "match_score": best["score"] if best else None,
        }
        sys.stderr.write(f"{album_id}: {results[album_id]['mbid']}\n")
        time.sleep(PACING)
    print(json.dumps(results, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
