"""SQLite persistence for canonical :class:`Player` domain objects."""

from __future__ import annotations

import json
import sqlite3
from typing import TYPE_CHECKING, Any

from machiavelli.game.player import Player

from .command_repository import CommandRepository

if TYPE_CHECKING:
    from machiavelli.game.game import Game


class PlayerRepository:
    """Translate between canonical players and SQLite rows."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        self.command_repo = CommandRepository(conn)

    @staticmethod
    def _game_id(player: Player) -> int:
        game_id = player.game.database_id
        if game_id is None:
            raise ValueError("No se puede persistir un jugador de una partida sin ID")
        return game_id

    @staticmethod
    def _decode_list(value: Any) -> list[str]:
        if value is None or value == "":
            return []
        decoded = json.loads(value)
        if not isinstance(decoded, list) or not all(
            isinstance(item, str) for item in decoded
        ):
            raise ValueError(
                "El estado JSON del jugador no contiene una lista de texto"
            )
        return decoded

    def _upsert(self, player: Player) -> None:
        game_id = self._game_id(player)
        self.conn.execute(
            """
            INSERT INTO players (
                game_id, player_id, discord_id, controlled_locations,
                armies, fleets, garrisons, ass_counters, ducats,
                rebelled_provinces, rebelled_cities, home_countries, power
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(game_id, player_id) DO UPDATE SET
                discord_id = excluded.discord_id,
                controlled_locations = excluded.controlled_locations,
                armies = excluded.armies,
                fleets = excluded.fleets,
                garrisons = excluded.garrisons,
                ass_counters = excluded.ass_counters,
                ducats = excluded.ducats,
                rebelled_provinces = excluded.rebelled_provinces,
                rebelled_cities = excluded.rebelled_cities,
                home_countries = excluded.home_countries,
                power = excluded.power
            """,
            (
                game_id,
                player.player_id,
                player.discord_id,
                json.dumps(player.controlled_locations),
                json.dumps(player.armies),
                json.dumps(player.fleets),
                json.dumps(player.garrisons),
                json.dumps(player.ass_counters),
                player.ducats,
                json.dumps(player.rebelled_provinces),
                json.dumps(player.rebelled_cities),
                json.dumps(player.home_countries),
                player.power,
            ),
        )

    def _replace_commands(self, player: Player) -> None:
        self.command_repo._delete_by_player(player)
        self.command_repo._save_many(player.commands)

    def save(self, player: Player) -> None:
        """Upsert a player and commands without committing an outer transaction."""
        if self.conn.in_transaction:
            self._upsert(player)
            self._replace_commands(player)
            return
        with self.conn:
            self._upsert(player)
            self._replace_commands(player)

    def save_commands(self, player: Player) -> None:
        """Replace commands without committing an outer transaction."""
        if self.conn.in_transaction:
            self._replace_commands(player)
            return
        with self.conn:
            self._replace_commands(player)

    def get_by_game(self, game: Game) -> list[Player]:
        """Load all players and their commands for a persisted game."""
        if game.database_id is None:
            raise ValueError("No se pueden cargar jugadores de una partida sin ID")

        rows = self.conn.execute(
            """
            SELECT player_id, discord_id, controlled_locations, armies, fleets,
                garrisons, ass_counters, ducats, rebelled_provinces,
                rebelled_cities, home_countries, power
            FROM players
            WHERE game_id = ?
            ORDER BY rowid ASC
            """,
            (game.database_id,),
        ).fetchall()

        players: list[Player] = []
        for row in rows:
            player = Player(
                game=game,
                player_id=row[0],
                discord_id=row[1],
                controlled_locations=self._decode_list(row[2]),
                armies=self._decode_list(row[3]),
                fleets=self._decode_list(row[4]),
                garrisons=self._decode_list(row[5]),
                ass_counters=self._decode_list(row[6]),
                ducats=row[7],
                rebelled_provinces=self._decode_list(row[8]),
                rebelled_cities=self._decode_list(row[9]),
                home_countries=self._decode_list(row[10]),
                power=row[11],
            )
            player.commands = self.command_repo.get_by_player(player)
            players.append(player)

        return players
