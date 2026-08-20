"""Browser Companion page-state classification contract (G3 T3.4).

Classifies a fetched RYM page into: ``ok`` (extractable), or a human-action
state (login required / CAPTCHA challenge / rate limited / session invalid /
unknown page). Any non-``ok`` state is a typed ``SourceUnavailableError`` with
``detail.kind == "human-action-required"`` so operators pause and intervene —
the companion NEVER auto-bypasses.
"""

from __future__ import annotations

import re

from omda.ports.errors import SourceUnavailableError

OK_STATUS = "ok"
LOGIN_REQUIRED = "login_required"
CAPTCHA_CHALLENGE = "captcha_challenge"
RATE_LIMITED = "rate_limited"
SESSION_INVALID = "session_invalid"
UNKNOWN_PAGE = "unknown_page"

HUMAN_ACTION_STATUSES = frozenset(
    {LOGIN_REQUIRED, CAPTCHA_CHALLENGE, RATE_LIMITED, SESSION_INVALID, UNKNOWN_PAGE}
)

_LOGIN_MARKERS = (
    r"\b(log\s?in|sign\s?in)\b",
    r"\b(please log in)\b",
)
_CAPTCHA_MARKERS = (
    r"\b(are you human|captcha|challenge)\b",
    r"\b(verify you are human)\b",
)
_RATE_MARKERS = (
    r"\b(rate\s?limit|too many requests|429)\b",
    r"\b(slow down)\b",
)
_SESSION_MARKERS = (
    r"\b(session\s?expired|invalid session)\b",
    r"\b(please sign in again)\b",
)

_genre_title_re = re.compile(r"^(.+?)\s+Music\s+genre\s*$", re.IGNORECASE)


def classify_page(title: str, body_sample: str) -> str:
    """Classify a page from its title and a bounded sample of the body."""
    text = f"{title} {body_sample}".lower()
    for pattern in _CAPTCHA_MARKERS:
        if re.search(pattern, text):
            return CAPTCHA_CHALLENGE
    for pattern in _RATE_MARKERS:
        if re.search(pattern, text):
            return RATE_LIMITED
    for pattern in _SESSION_MARKERS:
        if re.search(pattern, text):
            return SESSION_INVALID
    for pattern in _LOGIN_MARKERS:
        if re.search(pattern, text):
            return LOGIN_REQUIRED
    if _genre_title_re.match(title.strip()):
        return OK_STATUS
    return UNKNOWN_PAGE


def extract_genre_metadata(title: str) -> dict:
    """Best-effort genre name from an RYM genre page title.

    ``{"genre_name": str, "genre_id": str}`` or empty when not recognisable.
    """
    match = _genre_title_re.match(title.strip())
    if not match:
        return {}
    name = match.group(1).strip()
    genre_id = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return {"genre_name": name, "genre_id": genre_id or None}


def human_action_error(
    page_url: str, status: str, detail_extra: dict | None = None
) -> SourceUnavailableError:
    """Build the typed error for any non-ok page state (manual review)."""
    detail = {
        "kind": "human-action-required",
        "page_status": status,
        "page_url": page_url,
    }
    if detail_extra:
        detail.update(detail_extra)
    return SourceUnavailableError(f"rym: {status} — human action required", detail=detail)


__all__ = [
    "CAPTCHA_CHALLENGE",
    "HUMAN_ACTION_STATUSES",
    "LOGIN_REQUIRED",
    "OK_STATUS",
    "RATE_LIMITED",
    "SESSION_INVALID",
    "UNKNOWN_PAGE",
    "classify_page",
    "extract_genre_metadata",
    "human_action_error",
]
