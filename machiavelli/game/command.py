# machiavelli/game/command.py

from __future__ import annotations

from dataclasses import dataclass

from machiavelli.game.tables import GameTables


@dataclass(slots=True)
class Command:
    """Representa una orden dictada por un jugador en la partida.

    Attributes:
        game_id (int): Identificador de la partida en la base de datos.
        player_id (int): Identificador del jugador que emite la orden.
        actor (str): Unidad o gasto que ejecuta la orden (ej: 'A milan', 'E B').
        command (str): Tipo de comando u orden militar/mantenimiento.
        target (str): Objetivo sobre el que recae el comando.
    """

    game_id: int
    player_id: int
    actor: str
    command: str
    target: str = ""

    def is_valid_expense(
        self, allowed_types: set[str] | list[str] | None = None
    ) -> bool:
        """Comprueba si el comando representa un gasto válido y bien formado."""
        parts = self.actor.split()
        if len(parts) != 2 or parts[0] != "E":
            return False

        expense_type = parts[1]
        if allowed_types is None:
            return expense_type in GameTables.expenses
        return expense_type in allowed_types

    def __repr__(self) -> str:
        return (
            f"Command(actor={self.actor!r}, command={self.command!r}, "
            f"target={self.target!r})"
        )
