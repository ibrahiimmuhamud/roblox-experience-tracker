"""SQLite persistence for experience snapshots."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from roblox_api import ExperienceSnapshot

SCHEMA = """
CREATE TABLE IF NOT EXISTS snapshots (
    universe_id INTEGER NOT NULL,
    name        TEXT    NOT NULL,
    playing     INTEGER NOT NULL,
    visits      INTEGER NOT NULL,
    favorites   INTEGER NOT NULL,
    captured_at TEXT    NOT NULL,
    PRIMARY KEY (universe_id, captured_at)
);
CREATE INDEX IF NOT EXISTS idx_snapshots_universe ON snapshots (universe_id, captured_at);
"""


class SnapshotStore:
    """Stores snapshots, ignoring duplicate (universe_id, captured_at) pairs.

    The composite primary key makes re-running the collector for the same
    timestamp idempotent, so a retried workflow cannot double-count a reading.
    """

    def __init__(self, db_path: str | Path = "data/snapshots.db") -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(self.db_path)
        self._connection.row_factory = sqlite3.Row
        self._connection.executescript(SCHEMA)
        self._connection.commit()

    def save_all(self, snapshots: list[ExperienceSnapshot]) -> int:
        """Insert snapshots and return how many rows were newly written."""
        rows = [
            (s.universe_id, s.name, s.playing, s.visits, s.favorites, s.captured_at)
            for s in snapshots
        ]
        cursor = self._connection.executemany(
            "INSERT OR IGNORE INTO snapshots "
            "(universe_id, name, playing, visits, favorites, captured_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            rows,
        )
        self._connection.commit()
        return cursor.rowcount

    def history(self, universe_id: int, limit: int = 50) -> list[sqlite3.Row]:
        """Return the most recent readings for one experience, oldest first."""
        cursor = self._connection.execute(
            "SELECT * FROM snapshots WHERE universe_id = ? "
            "ORDER BY captured_at DESC LIMIT ?",
            (universe_id, limit),
        )
        return list(reversed(cursor.fetchall()))

    def latest_per_experience(self) -> list[sqlite3.Row]:
        """Return the newest reading for every tracked experience."""
        cursor = self._connection.execute(
            "SELECT s.* FROM snapshots s "
            "JOIN (SELECT universe_id, MAX(captured_at) AS newest "
            "      FROM snapshots GROUP BY universe_id) latest "
            "  ON s.universe_id = latest.universe_id "
            " AND s.captured_at = latest.newest "
            "ORDER BY s.playing DESC"
        )
        return cursor.fetchall()

    def total_snapshots(self) -> int:
        return self._connection.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0]

    def close(self) -> None:
        self._connection.close()
