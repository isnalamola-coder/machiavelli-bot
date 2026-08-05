"""Unit maintenance and recruitment with one event per attempted order."""

from ..events import EventType, TurnEvent
from ..game.command import Command
from ..game.game import Game
from ..game.player import Player

_MAINTENANCE_COST = 3


class MaintenanceResolver:
    """Resolve disband, maintenance, and recruitment orders."""

    def __init__(self, game: Game) -> None:
        self.game = game

    @staticmethod
    def _set_default_commands(player: Player) -> None:
        """Add an effective maintain order for each unit without an explicit order."""
        explicit_actors = {command.actor for command in player.commands}
        for unit_type, locations in (
            ("A", player.armies),
            ("F", player.fleets),
            ("G", player.garrisons),
        ):
            for location in locations:
                actor = f"{unit_type} {location}"
                if actor not in explicit_actors:
                    player.commands.append(
                        Command(player.game, player, actor, "M", target=None)
                    )

    @staticmethod
    def _units(player: Player, unit_type: str) -> list[str]:
        try:
            return {
                "A": player.armies,
                "F": player.fleets,
                "G": player.garrisons,
            }[unit_type]
        except KeyError as error:
            raise ValueError(
                f"Tipo de unidad de mantenimiento inválido: {unit_type}"
            ) from error

    def _emit(
        self,
        player: Player,
        command: Command,
        result: str,
        cost: int,
    ) -> None:
        self.game.add_event(
            TurnEvent(
                EventType.MAINTENANCE_ORDER_RESOLVED,
                {
                    "player": player.player_id,
                    "actor": command.actor,
                    "order": command.command,
                    "target": command.target,
                    "result": result,
                    "cost": cost,
                },
            )
        )

    def _disband(self, player: Player, command: Command) -> int:
        unit_type, unit_id = command.actor.split(maxsplit=1)
        units = self._units(player, unit_type)
        if unit_id not in units:
            self._emit(player, command, "unit_not_found", 0)
            return 0
        units.remove(unit_id)
        self._emit(player, command, "disbanded", 0)
        return 0

    def _maintain(self, player: Player, command: Command, available: int) -> int:
        unit_type, unit_id = command.actor.split(maxsplit=1)
        units = self._units(player, unit_type)
        if unit_id not in units:
            self._emit(player, command, "unit_not_found", 0)
            return 0
        if available >= _MAINTENANCE_COST:
            self._emit(player, command, "maintained", _MAINTENANCE_COST)
            return _MAINTENANCE_COST
        units.remove(unit_id)
        self._emit(player, command, "disbanded_no_funds", 0)
        return 0

    def _recruit(self, player: Player, command: Command, available: int) -> int:
        game_map = self.game.require_map()
        scenario = self.game.require_scenario()
        unit_type, unit_id = command.actor.split(maxsplit=1)

        if available < _MAINTENANCE_COST:
            self._emit(player, command, "recruitment_no_funds", 0)
            return 0

        home_country_cities = {
            province
            for province in player.controlled_locations
            if scenario.province_home_country(province) in player.home_countries
            and game_map.provinces[province].city in ("city", "fortified")
        }
        province = game_map.provinces[unit_id]

        if unit_id not in home_country_cities:
            self._emit(player, command, "invalid_home_or_control", 0)
            return 0

        if unit_type in ("A", "F"):
            occupied = unit_id in player.armies or any(
                fleet.split()[0] == unit_id for fleet in player.fleets
            )
            if occupied or province.is_venice and unit_id in player.garrisons:
                self._emit(player, command, "space_occupied", 0)
                return 0
            if unit_type == "F" and not province.has_port:
                self._emit(player, command, "port_required", 0)
                return 0
            target = player.armies if unit_type == "A" else player.fleets
            target.append(unit_id)
        elif unit_type == "G":
            if unit_id in player.rebelled_cities:
                self._emit(player, command, "rebelled_city", 0)
                return 0
            if (
                unit_id in player.garrisons
                or province.is_venice
                and (
                    unit_id in player.armies
                    or any(fleet.split()[0] == unit_id for fleet in player.fleets)
                )
            ):
                self._emit(player, command, "space_occupied", 0)
                return 0
            if province.city != "fortified":
                self._emit(player, command, "fortified_city_required", 0)
                return 0
            player.garrisons.append(unit_id)
        else:
            raise ValueError(f"Tipo de reclutamiento inválido: {unit_type}")

        self._emit(player, command, "recruited", _MAINTENANCE_COST)
        return _MAINTENANCE_COST

    def run(self) -> None:
        """Resolve all players and emit ordered attempt and summary events."""
        for player in self.game.players:
            initial_ducats = player.ducats
            expenses = 0
            self._set_default_commands(player)

            for order in ("D", "M", "R"):
                for command in [
                    item for item in player.commands if item.command == order
                ]:
                    if order == "D":
                        expenses += self._disband(player, command)
                    elif order == "M":
                        expenses += self._maintain(
                            player, command, initial_ducats - expenses
                        )
                    else:
                        expenses += self._recruit(
                            player, command, initial_ducats - expenses
                        )

            player.ducats = initial_ducats - expenses
            self.game.add_event(
                TurnEvent(
                    EventType.MAINTENANCE_SUMMARY,
                    {
                        "player": player.player_id,
                        "initial_ducats": initial_ducats,
                        "expenses": expenses,
                        "remaining_ducats": player.ducats,
                    },
                )
            )
