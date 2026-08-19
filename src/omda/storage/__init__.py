"""Runtime storage: SQLite adapter for history/journal/cache (never community source of truth)."""

from omda.storage.sqlite_history import SqliteHistory

__all__ = ["SqliteHistory"]
