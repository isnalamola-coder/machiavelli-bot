"""Repository facade for persisted :class:`Game` aggregates."""

from __future__ import annotations

import sqlite3

from machiavelli.game.game import Game


class GameRepository:
    """Persist and load games while keeping transaction ownership explicit."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def save(self, game: Game) -> None:
        """Persist a complete game atomically unless a caller owns the transaction."""
        original_database_id = game.database_id
        try:
            if self.conn.in_transaction:
                game.save(self.conn)
                return
            with self.conn:
                game.save(self.conn)
        except Exception:
            game.database_id = original_database_id
            raise

    def get_by_id(self, game_id: int) -> Game:
        """Load a game by its SQLite identifier."""
        return Game.load_game(self.conn, game_id=game_id)

    def get_by_name(self, name: str) -> Game:
        """Load a game by its unique name."""
        return Game.load_game(self.conn, name=name)

    def get_by_channel(self, channel_id: int) -> Game:
        """Load a game by its Discord channel identifier."""
        return Game.load_game(self.conn, channel_id=channel_id)
