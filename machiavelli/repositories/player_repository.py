# machiavelli/repositories/player_repository.py

import json
import sqlite3
from typing import TYPE_CHECKING

from ..game.player import Player
from .command_repository import CommandRepository

if TYPE_CHECKING:
    from game import Game


class PlayerRepository:
    """Maneja la persistencia de los objetos Player en SQLite."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self.command_repo = CommandRepository(conn)

    def save(self, player: Player) -> None:
        """Guarda o actualiza al jugador y sus comandos en una transacción segura."""
        with self.conn:
            cursor = self.conn.cursor()
            cursor.execute(
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
                    player.game.database_id,
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

            # Persistir comandos asociados usando la misma transacción
            self.save_commands(player)

    def save_commands(self, player: Player) -> None:
        """Elimina comandos antiguos y guarda los nuevos."""
        cursor = self.conn.cursor()
        cursor.execute(
            "DELETE FROM commands WHERE game_id = ? AND player_id = ?",
            (player.game.database_id, player.player_id),
        )
        for command in player.commands:
            self.command_repo.save(command, player.game.database_id, player.player_id)

    def get_by_game(self, game: "Game") -> list[Player]:
        """Carga todos los jugadores pertenecientes a una partida."""
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT player_id, discord_id, controlled_locations, armies, fleets,
                garrisons, ass_counters, ducats, rebelled_provinces, rebelled_cities,
                home_countries, power
            FROM players WHERE game_id = ?
            """,
            (game.database_id,),
        )
        rows = cursor.fetchall()

        players = []
        for row in rows:
            player = Player(
                game=game,
                player_id=row[0],
                discord_id=row[1],
                controlled_locations=json.loads(row[2]) if row[2] else [],
                armies=json.loads(row[3]) if row[3] else [],
                fleets=json.loads(row[4]) if row[4] else [],
                garrisons=json.loads(row[5]) if row[5] else [],
                ass_counters=json.loads(row[6]) if row[6] else [],
                ducats=row[7],
                rebelled_provinces=json.loads(row[8]) if row[8] else [],
                rebelled_cities=json.loads(row[9]) if row[9] else [],
                home_countries=json.loads(row[10]) if row[10] else [],
                power=row[11],
            )
            # Cargar los comandos del jugador
            player.commands = self.command_repo.get_by_player(player)
            players.append(player)

        return players
