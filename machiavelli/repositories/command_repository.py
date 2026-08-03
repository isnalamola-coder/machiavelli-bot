# machiavelli/repositories/command_repository.py

import sqlite3

from machiavelli.game.command import Command


class CommandRepository:
    """Maneja la persistencia de objetos Command en la base de datos SQLite."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def save(self, command: Command) -> None:
        """Guarda un único comando en la base de datos."""
        query = """
            INSERT INTO commands (game_id, player_id, actor, command, target)
            VALUES (?, ?, ?, ?, ?)
        """
        cursor = self.conn.cursor()
        cursor.execute(
            query,
            (
                command.game_id,
                command.player_id,
                command.actor,
                command.command,
                command.target,
            ),
        )
        self.conn.commit()

    def save_many(self, commands: list[Command]) -> None:
        """Guarda una lista de comandos en una sola transacción eficiente."""
        query = """
            INSERT INTO commands (game_id, player_id, actor, command, target)
            VALUES (?, ?, ?, ?, ?)
        """
        data = [
            (c.game_id, c.player_id, c.actor, c.command, c.target) for c in commands
        ]
        cursor = self.conn.cursor()
        cursor.executemany(query, data)
        self.conn.commit()

    def get_by_player(self, game_id: int, player_id: int) -> list[Command]:
        """Recupera todas las órdenes registradas para un jugador en una partida."""
        query = """
            SELECT actor, command, target 
            FROM commands 
            WHERE game_id = ? AND player_id = ?
        """
        cursor = self.conn.cursor()
        cursor.execute(query, (game_id, player_id))
        rows = cursor.fetchall()

        return [
            Command(
                game_id=game_id,
                player_id=player_id,
                actor=row[0],
                command=row[1],
                target=row[2],
            )
            for row in rows
        ]

    def delete_by_player(self, game_id: int, player_id: int) -> None:
        """Limpia las órdenes previas de un jugador (útil al reescribir órdenes de un turno)."""
        query = "DELETE FROM commands WHERE game_id = ? AND player_id = ?"
        cursor = self.conn.cursor()
        cursor.execute(query, (game_id, player_id))
        self.conn.commit()
