"""Browser Companion package (G3 T3.4).

A deliberately thin, disable-able boundary between a legitimate user browser
session and OMDA. It extracts only the minimum page data an active run needs,
classifies human-intervention states (login / CAPTCHA challenge / rate limit /
session invalid / unknown page), NEVER bypasses Cloudflare or solves CAPTCHAs,
never mass-crawls and never fans out to Album Detail pages by default.
Cookie/profile/session material stays local and is never touched here.

The package is optional: when disabled, the Recommendation Core and Orchestrator
keep working with other data sources/fakes (contract tests enforce this).
"""

from __future__ import annotations

from .contract import (
    HUMAN_ACTION_STATUSES,
    OK_STATUS,
    classify_page,
    extract_genre_metadata,
)
from .parser import parse_page
from .source import RymGenrePageSource

__all__ = [
    "HUMAN_ACTION_STATUSES",
    "OK_STATUS",
    "RymGenrePageSource",
    "classify_page",
    "extract_genre_metadata",
    "parse_page",
]
