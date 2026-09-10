from __future__ import annotations

import sqlite3
from pathlib import Path


class LobbiesDB:
    """Persists the voice-chat-role triplet for each dynamic lobby."""

    def __init__(self, db_path: Path):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._con = sqlite3.connect(db_path)
        self._con.execute(
            """CREATE TABLE IF NOT EXISTS lobbies (
                lobby BIGINT PRIMARY KEY,
                chat BIGINT,
                role BIGINT
            )"""
        )
        self._con.commit()

    def add(self, lobby_id: int, chat_id: int, role_id: int) -> None:
        self._con.execute(
            "INSERT OR IGNORE INTO lobbies VALUES (?,?,?)", [lobby_id, chat_id, role_id]
        )
        self._con.commit()

    def get(self, lobby_id: int) -> tuple[int, int, int] | None:
        row = self._con.execute(
            "SELECT * FROM lobbies WHERE lobby = ?", [lobby_id]
        ).fetchone()
        return row if row else None

    def remove(self, lobby_id: int) -> None:
        self._con.execute("DELETE FROM lobbies WHERE lobby = ?", [lobby_id])
        self._con.commit()

    def close(self) -> None:
        self._con.close()