# machiavelli/engine/maintance.py

from ..events import EventType, TurnEvent
from ..game.command import Command
from ..game.game import Game
from ..game.player import Player


class MaintenanceResolver:
    """Responsable de gestionar la fase de mantenimiento."""

    def __init__(self, game: Game):
        self.game = game

    @staticmethod
    def _set_default_commands(player: Player) -> None:
        """Orde de mantener por defecto para las unidades existentes."""
        actors = {command.actor for command in player.commands}
        for unit_type, locations in (
            ("A", player.armies),
            ("F", player.fleets),
            ("G", player.garrisons),
        ):
            for location in locations:
                actor = f"{unit_type} {location}"
                if actor not in actors:
                    player.commands.append(
                        Command(player.game, player, actor, "M", target=None)
                    )

    def run(self):
        """Ejecuta la fase de mantenimiento."""
        turn_events = []

        for player in self.game.players:
            expenses = 0
            self._set_default_commands(player)

            disbanded_units = []
            maintained_units = []
            recruited_units = []
            failed_to_maintain = []
            failed_to_recruit = []

            # 1. Desmantelamientos (D)
            for command in [item for item in player.commands if item.command == "D"]:
                unit_type, unit_id = command.actor.split()
                units = {
                    "A": player.armies,
                    "F": player.fleets,
                    "G": player.garrisons,
                }[unit_type]
                if unit_id in units:
                    units.remove(unit_id)
                    disbanded_units.append(command.actor)

            # 2. Mantenimiento (M)
            for command in [item for item in player.commands if item.command == "M"]:
                unit_type, unit_id = command.actor.split()
                units = {
                    "A": player.armies,
                    "F": player.fleets,
                    "G": player.garrisons,
                }[unit_type]
                if unit_id not in units:
                    continue
                elif player.ducats - expenses >= 3:
                    maintained_units.append(command.actor)
                    expenses += 3
                else:
                    failed_to_maintain.append(command.actor)
                    units.remove(unit_id)

            # 3. Reclutamiento (R)
            home_countries_cities = [
                province
                for province in player.controlled_locations
                if self.game.scenario.province_home_country(province)
                in player.home_countries
                and self.game.map.provinces[province].city in ("city", "fortified")
            ]

            recruit_commands = [item for item in player.commands if item.command == "R"]
            for command in recruit_commands:
                if player.ducats - expenses < 3:
                    failed_to_recruit.append((command.actor, "no_enough_funds"))
                    continue

                unit_type, unit_id = command.actor.split()
                province = self.game.map.provinces[unit_id]

                if unit_type in ("A", "F"):
                    if unit_id not in home_countries_cities:
                        failed_to_recruit.append((command.actor, "invalid_province"))
                    elif unit_id in player.armies or unit_id in player.fleets:
                        failed_to_recruit.append((command.actor, "full_location"))
                    elif province.is_venice and unit_id in player.garrisons:
                        failed_to_recruit.append((command.actor, "full_venice"))
                    elif unit_type == "F" and not province.has_port:
                        failed_to_recruit.append((command.actor, "missing_port"))
                    else:
                        recruited_units.append(command.actor)
                        expenses += 3
                        if unit_type == "A":
                            player.armies.append(unit_id)
                        else:
                            player.fleets.append(unit_id)
                elif unit_type == "G":
                    if unit_id in player.rebelled_cities:
                        failed_to_recruit.append((command.actor, "rebelled_city"))
                    elif unit_id not in home_countries_cities:
                        failed_to_recruit.append((command.actor, "invalid_province"))
                    elif unit_id in player.garrisons:
                        failed_to_recruit.append((command.actor, "full_location"))
                    elif province.is_venice and (
                        unit_id in player.armies or unit_id in player.fleets
                    ):
                        failed_to_recruit.append((command.actor, "full_venice"))
                    elif province.city != "fortified":
                        failed_to_recruit.append((command.actor, "invalid_city"))
                    else:
                        recruited_units.append(command.actor)
                        expenses += 3
                        player.garrisons.append(unit_id)

            expected_expenses = (
                len(player.armies) + len(player.fleets) + len(player.garrisons)
            ) * 3
            if expenses != expected_expenses:
                raise AssertionError(
                    f"Gasto de mantenimiento inconsistente: {expenses} != "
                    f"{expected_expenses}"
                )

            self.game.add_event(
                TurnEvent(
                    type=EventType.PLAYER_MAINTENANCE,
                    data={
                        "player": player.player_id,
                        "disbanded": disbanded_units,
                        "maintained": maintained_units,
                        "recruited": recruited_units,
                        "failed_to_maintain": failed_to_maintain,
                        "failed_to_recruit": failed_to_recruit,
                        "expenses": expenses,
                    },
                )
            )
            turn_events.append(
                f"*Ducados iniciales*: {player.ducats}. "
                f"*Gastos:* {expenses}. "
                f"*Ducados restantes*: {player.ducats - expenses}. "
            )
            player.ducats -= expenses

        return turn_events
