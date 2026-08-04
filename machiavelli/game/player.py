"""Domain model for Machiavelli players."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Self

from .command import Command
from .scenario import Power, Scenario

if TYPE_CHECKING:
    from .game import Game


class TurnType(Enum):
    """Represent the kind of phase in which an order is submitted."""

    MAINTENANCE = "maintenance"
    CAMPAIGN = "campaign"


@dataclass
class Player:
    """Represent a player and their complete in-game state."""

    game: Game
    player_id: str
    discord_id: int | None = None
    controlled_locations: list[str] = field(default_factory=list)
    armies: list[str] = field(default_factory=list)
    fleets: list[str] = field(default_factory=list)
    garrisons: list[str] = field(default_factory=list)
    ass_counters: list[str] = field(default_factory=list)
    ducats: int = 0
    rebelled_provinces: list[str] = field(default_factory=list)
    rebelled_cities: list[str] = field(default_factory=list)
    home_countries: list[str] = field(default_factory=list)
    power: str | None = None
    commands: list[Command] = field(default_factory=list)

    @property
    def game_id(self) -> int | None:
        """Return the persisted game identifier derived from ``game``."""
        return self.game.database_id

    @property
    def power_id(self) -> str | None:
        """Compatibility alias for the canonical ``power`` state."""
        return self.power

    def add_command(self, command: Command) -> None:
        """Append exactly the command object received."""
        self.commands.append(command)

    def remove_command(self, command: Command) -> None:
        """Remove exactly the command object received."""
        self.commands.remove(command)

    def assign_power(self, power: Power) -> None:
        """Assign a domain power and initialize the player's starting state."""
        power_id = getattr(power, "id", None)
        if not power_id and self.game.scenario is not None:
            power_id = next(
                (
                    candidate_id
                    for candidate_id, candidate in self.game.scenario.powers.items()
                    if candidate is power
                ),
                None,
            )

        self.power = power_id
        self.home_countries = list(power.home_countries)
        self.controlled_locations = list(power.controlled_provinces)
        self.armies = list(power.armies)
        self.fleets = list(power.fleets)
        self.garrisons = list(power.garrisons)

    def assign_power_from_scenario(
        self,
        power_id: str,
        power: Power,
        available_power_ids: Iterable[str],
    ) -> None:
        """Assign a power when its scenario identifier is already known."""
        self.assign_power(power)
        self.power = power_id
        self.ass_counters = [
            candidate for candidate in available_power_ids if candidate != power_id
        ]

    def hc_provinces(self, scenario: Scenario | None = None) -> list[str]:
        """Return controlled provinces belonging to the player's home countries."""
        active_scenario = scenario or self.game.scenario
        if active_scenario is None:
            raise ValueError("El jugador no tiene un escenario activo")
        provinces = active_scenario.home_countries_provinces(self.home_countries) or []
        return [
            province
            for province in self.controlled_locations
            if province in provinces
        ]

    def nonhc_provinces(self, scenario: Scenario | None = None) -> list[str]:
        """Return controlled provinces outside the player's home countries."""
        active_scenario = scenario or self.game.scenario
        if active_scenario is None:
            raise ValueError("El jugador no tiene un escenario activo")
        provinces = active_scenario.home_countries_provinces(self.home_countries) or []
        return [
            province
            for province in self.controlled_locations
            if province not in provinces
        ]

    def set_default_commands(self) -> None:
        """Add maintenance orders for units that do not have one yet."""
        actors = {command.actor for command in self.commands}
        for unit_type, locations in (
            ("A", self.armies),
            ("F", self.fleets),
            ("G", self.garrisons),
        ):
            for location in locations:
                actor = f"{unit_type} {location}"
                if actor not in actors:
                    self.commands.append(
                        Command(self.game, self, actor, "M", target=None)
                    )

    def save(self, conn: sqlite3.Connection) -> None:
        """Persist the player through the historical compatibility facade."""
        cursor = conn.cursor()
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
                self.game_id,
                self.player_id,
                self.discord_id,
                json.dumps(self.controlled_locations),
                json.dumps(self.armies),
                json.dumps(self.fleets),
                json.dumps(self.garrisons),
                json.dumps(self.ass_counters),
                self.ducats,
                json.dumps(self.rebelled_provinces),
                json.dumps(self.rebelled_cities),
                json.dumps(self.home_countries),
                self.power,
            ),
        )
        self.save_commands(conn)

    def save_commands(self, conn: sqlite3.Connection) -> None:
        """Replace the persisted commands while preserving their list order."""
        conn.execute(
            "DELETE FROM commands WHERE game_id = ? AND player_id = ?",
            (self.game_id, self.player_id),
        )
        for command in self.commands:
            command.save(conn)

    @classmethod
    def load_players(cls, conn: sqlite3.Connection, game: Game) -> list[Self]:
        """Load all players associated with a game."""
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT player_id, discord_id, controlled_locations, armies, fleets,
                garrisons, ass_counters, ducats, rebelled_provinces,
                rebelled_cities, home_countries, power
            FROM players WHERE game_id = ?
            """,
            (game.database_id,),
        )

        players: list[Self] = []
        for row in cursor.fetchall():
            player = cls(
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
            player.commands = Command.load_commands(conn, game, player)
            players.append(player)
        return players

    def player_report(self) -> list[str]:
        """Generate the player's current public report."""
        from machiavelli.services.player_reporter import PlayerReporter

        return PlayerReporter.generate_report(self)

    def cmd_available_actors(self) -> list[tuple[str, str]]:
        from machiavelli.services.player_interaction_service import (
            PlayerInteractionService,
        )

        return PlayerInteractionService(self).cmd_available_actors()

    def cmd_available_commands(self, actor: str) -> list[tuple[str, str]]:
        from machiavelli.services.player_interaction_service import (
            PlayerInteractionService,
        )

        return PlayerInteractionService(self).cmd_available_commands(actor)

    def cmd_available_targets(
        self,
        actor: str,
        command: str,
    ) -> list[tuple[str, str]]:
        from machiavelli.services.player_interaction_service import (
            PlayerInteractionService,
        )

        return PlayerInteractionService(self).cmd_available_targets(actor, command)

    def exp_available_expenses(self) -> list[tuple[str, str]]:
        from machiavelli.services.player_interaction_service import (
            PlayerInteractionService,
        )

        return PlayerInteractionService(self).exp_available_expenses()

    def exp_available_targets(self, expense: str) -> list[tuple[str, str]]:
        from machiavelli.services.player_interaction_service import (
            PlayerInteractionService,
        )

        return PlayerInteractionService(self).exp_available_targets(expense)

    def exp_available_amounts(
        self,
        expense: str,
        target: str,
    ) -> list[tuple[str, str]]:
        from machiavelli.services.player_interaction_service import (
            PlayerInteractionService,
        )

        return PlayerInteractionService(self).exp_available_amounts(expense, target)

    def cmd_add_command(
        self,
        turn_type: TurnType,
        command: Command,
    ) -> list[str]:
        """Compatibility facade over the central order processor."""
        from machiavelli.engine.orders import OrderProcessor

        return OrderProcessor(self.game).process_command(self, turn_type, command)
