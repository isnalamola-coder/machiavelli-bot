"""Domain model for player commands."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import TYPE_CHECKING, Self

from .tables import GameTables

if TYPE_CHECKING:
    from .game import Game
    from .player import Player


@dataclass(slots=True)
class Command:
    """Represent an order issued by a player in a game."""

    game: Game
    player: Player
    actor: str
    command: str
    target: str | None = None

    @property
    def game_id(self) -> int | None:
        """Return the persisted game identifier derived from the domain object."""
        return self.game.database_id

    @property
    def player_id(self) -> str:
        """Return the player identifier derived from the domain object."""
        return self.player.player_id

    def save(self, conn: sqlite3.Connection) -> None:
        """Persist this command using the historical compatibility facade."""
        conn.execute(
            "INSERT INTO commands "
            "(game_id, player_id, actor, command, target) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                self.game_id,
                self.player_id,
                self.actor,
                self.command,
                self.target,
            ),
        )

    @classmethod
    def load_commands(
        cls,
        conn: sqlite3.Connection,
        game: Game,
        player: Player,
    ) -> list[Self]:
        """Load a player's commands in their persisted relative order."""
        cursor = conn.cursor()
        cursor.execute(
            "SELECT actor, command, target FROM commands "
            "WHERE game_id = ? AND player_id = ? ORDER BY commands.id ASC",
            (game.database_id, player.player_id),
        )
        return [
            cls(
                game=game,
                player=player,
                actor=row[0],
                command=row[1],
                target=row[2],
            )
            for row in cursor.fetchall()
        ]

    def is_valid_expense(
        self,
        allowed_types: set[str] | list[str] | None = None,
    ) -> bool:
        """Return whether the command is a well-formed supported expense."""
        actor = self.actor.split()
        if len(actor) != 2 or actor[0] != "E":
            return False
        if allowed_types is None:
            return actor[1] in GameTables.expenses
        return actor[1] in allowed_types

    def __repr__(self) -> str:
        return (
            f"Command(actor={self.actor!r}, command={self.command!r}, "
            f"target={self.target!r})"
        )

    def __str__(self) -> str:
        """Return the historical human-readable representation of the command."""
        provinces = self.game.map.provinces
        seas = self.game.map.seas
        locations = provinces | seas

        try:
            report: list[str] = []
            target_type = None
            actor_type, actor_id = self.actor.split()

            if actor_type in ("A", "F", "G"):
                report.append(
                    f"{GameTables.actors[actor_type]} de {locations[actor_id].name}"
                )
            elif actor_type == "E":
                report.append(GameTables.expenses[actor_id]["text"])
                target_type = GameTables.expenses[actor_id]["target_type"]

            if actor_type in ("A", "F", "G"):
                if self.game.turn_number % 4 == 1:
                    order = GameTables.maintenance_orders[self.command]
                else:
                    order = GameTables.military_orders[self.command]
                report.append(order["text"])
                target_type = order["target_type"]

            if target_type:
                assert self.target is not None
                if target_type == "army_ext":
                    army_ext = self.target.split()
                    if len(army_ext) > 2:
                        report.append(
                            f"{GameTables.actors[army_ext[0]]} "
                            f"de {provinces[army_ext[1]].name} "
                            f"({GameTables.powers[army_ext[2]]})"
                        )
                    else:
                        report.append(
                            f"{GameTables.actors[army_ext[0]]} "
                            f"de {provinces[army_ext[1]].name}"
                        )
                elif target_type == "location":
                    report.append(locations[self.target].name)
                elif target_type == "location_ext":
                    location_ext = self.target.split()
                    if len(location_ext) > 1:
                        report.append(
                            f"{locations[location_ext[0]].name} "
                            f"({GameTables.powers[location_ext[1]]})"
                        )
                    else:
                        report.append(locations[location_ext[0]].name)
                elif target_type == "province":
                    report.append(provinces[self.target].name)
                elif target_type == "power":
                    report.append(GameTables.powers[self.target])
                elif target_type == "unit":
                    unit_ext = self.target.split()
                    report.append(
                        f"{GameTables.actors[unit_ext[0]]} "
                        f"de {provinces[unit_ext[1]].name}"
                    )
                elif target_type == "unit_type":
                    if self.target == "0":
                        report.append("Desbandar")
                    else:
                        report.append(GameTables.actors[self.target])

            if actor_type == "E":
                report.append(f"{self.command} ducados")

            return "|".join(report)
        except Exception:
            return "Orden inválida"
