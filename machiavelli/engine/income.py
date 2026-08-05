"""Income calculation and structured audit events."""

from random import Random

from ..events import EventType, TurnEvent
from ..game.game import Game
from ..game.player import Player
from ..game.tables import GameTables


class IncomeManager:
    """Calculate spring income for every player."""

    def __init__(self, game: Game, rng: Random | None = None) -> None:
        self.game = game
        self.rng = rng if rng is not None else Random()

    def _collect_player_income(self, player: Player) -> None:
        """Apply one player's fixed and variable income and emit one event."""
        game_map = self.game.require_map()
        scenario = self.game.require_scenario()

        occupied_or_controlled = (
            set(player.controlled_locations)
            | set(player.armies)
            | {fleet.split()[0] for fleet in player.fleets}
        )
        provinces = sorted(
            province
            for province in occupied_or_controlled
            if province not in self.game.famine
            and province not in player.rebelled_provinces
            and province not in player.rebelled_cities
        )
        province_income = len(provinces)

        possible_cities = {
            province
            for province in player.controlled_locations
            if province not in self.game.famine
            and province not in player.rebelled_cities
            and province not in player.rebelled_provinces
        } | set(player.garrisons)
        cities = sorted(
            city
            for city in possible_cities
            if game_map.provinces[city].city in ("city", "fortified")
        )
        city_income = sum(game_map.provinces[city].major_city or 0 for city in cities)

        variable_items: list[dict[str, object]] = []
        variable_income = 0
        for home_country in scenario.variable_income_home_countries:
            if home_country not in player.home_countries:
                continue
            roll = self.rng.randint(1, 6)
            amount = GameTables.variable_income[home_country][roll - 1]
            variable_items.append(
                {
                    "source_type": "home_country",
                    "source": home_country,
                    "roll": roll,
                    "amount": amount,
                }
            )
            variable_income += amount

        for province in scenario.variable_income_provinces:
            if province not in player.controlled_locations:
                continue
            roll = self.rng.randint(1, 6)
            amount = GameTables.variable_income[province][roll - 1]
            variable_items.append(
                {
                    "source_type": "province",
                    "source": province,
                    "roll": roll,
                    "amount": amount,
                }
            )
            variable_income += amount

        total_income = province_income + city_income + variable_income
        player.ducats += total_income

        self.game.add_event(
            TurnEvent(
                type=EventType.INCOME_COLLECTED,
                data={
                    "player": player.player_id,
                    "provinces": provinces,
                    "province_income": province_income,
                    "cities": cities,
                    "city_income": city_income,
                    "variable_income": variable_items,
                    "total_income": total_income,
                },
            )
        )

    def run(self) -> None:
        """Calculate and apply income for all players in stable player order."""
        for player in self.game.players:
            self._collect_player_income(player)
