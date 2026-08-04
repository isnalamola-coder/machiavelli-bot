"""Backward-compatible public SQLite API."""

from machiavelli.db.database import (
    DatabaseManager,
    upgrade,
    upgrade_connection,
)

__all__ = [
    "DatabaseManager",
    "upgrade",
    "upgrade_connection",
]
