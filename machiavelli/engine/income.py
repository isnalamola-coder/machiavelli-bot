# machiavelli/engine/incomes.py

from random import Random

from ..events import EventType, TurnEvent
from ..game.game import Game
from ..game.player import Player
from ..game.tables import GameTables


class IncomeManager:
    """Responsable del cálculo de ingresos del inicio de primavera."""

    def __init__(self, game: Game, rng: Random | None = None):
        """Constructor del manager."""
        self.game = game
        self.rng = rng if rng is not None else Random()

    def player_income(self, player: Player):
        """Calcula los ingresos de un jugador."""

        # Provincias controladas u ocupadas por ejércitos y flotas
        # Los mares no pueden ser controlados, pero sí ocupados
        maybe_provinces = (
            set(player.controlled_locations)
            | set(player.armies)
            | {fleet.split()[0] for fleet in player.fleets}
        )

        # Las provincias con hambre o con rebelión no proporcionan ingresos
        provinces = [
            province
            for province in maybe_provinces
            if province not in self.game.famine
            and province not in player.rebelled_provinces
            and province not in player.rebelled_cities
        ]
        province_income = len(provinces)

        # Las ciudades en provincias con hambre o rebelión tampoco,
        # excepto si tienen guarnición
        maybe_cities = {
            province
            for province in player.controlled_locations
            if province not in self.game.famine
            and province not in player.rebelled_cities
            and province not in player.rebelled_provinces
        } | set(player.garrisons)
        cities = [
            city
            for city in maybe_cities
            if self.game.map.provinces[city].city in ("city", "fortified")
        ]
        # major_city es el ingreso por ciudad. Si no es mayor, vale 1
        city_income = sum(
            self.game.map.provinces[city].major_city or 0 for city in cities
        )

        fixed_income = province_income + city_income

        variable_income = 0
        for home_country in self.game.scenario.variable_income_home_countries:
            if home_country in player.home_countries:
                dice = self.rng.randint(0, 5)
                amount = GameTables.variable_income[home_country][dice]
                variable_income += amount

        special_provinces = []
        for province in self.game.scenario.variable_income_provinces:
            if province in player.controlled_locations:
                special_provinces.append(province)
                dice = self.rng.randint(0, 5)
                amount = GameTables.variable_income[province][dice]
                variable_income += amount

        total_income = fixed_income + variable_income
        player.ducats += total_income

        self.game.add_event(
            TurnEvent(
                type=EventType.PLAYER_INCOME,
                data={
                    "player": player.player_id,
                    "locations": provinces,
                    "cities": cities,
                    "home_countries": player.home_countries,
                    "special_provinces": special_provinces,
                    "fixed_income": fixed_income,
                    "variable_income": variable_income,
                },
            )
        )

    def run(self):
        """Ejecuta la fase de ingresos y actualiza los recursos de los jugadores."""
        for player in self.game.players:
            self.player_income(player)
