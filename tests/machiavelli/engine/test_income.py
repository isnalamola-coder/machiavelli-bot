# test/machiavelli/engine/test_income.py

import unittest
from unittest.mock import Mock, patch

from machiavelli.engine.income import IncomeManager
from machiavelli.events import EventType, TurnEvent
from tests.machiavelli.engine.helpers import create_mock_game, create_mock_player


class TestPlayerIncome(unittest.TestCase):
    def setUp(self):
        self.mock_game = create_mock_game()
        self.mock_player = create_mock_player("player_1")

        self.mock_scenario = Mock(
            variable_income_home_countries=["L", "N"],
            variable_income_provinces=["rome"],
        )
        self.mock_game.scenario = self.mock_scenario

        major_city = Mock(city="fortified", major_city=2)
        fortified_city = Mock(city="fortified", major_city=1)
        normal_city = Mock(city="city", major_city=1)
        only_province = Mock(city=None, major_city=None)
        self.mock_map = Mock(
            provinces={
                "venic": major_city,
                "rome": major_city,
                "flore": fortified_city,
                "piomb": normal_city,
                "sienn": only_province,
                "paler": only_province,
            }
        )
        self.mock_game.map = self.mock_map

        self.mock_rng = Mock()

    def test_player_income_provinces_and_seas(self):
        """Calcula los ingresos de provincias y mares."""
        # El jugador no controla ninguna ciudad, solo mares y provincias
        self.mock_player.ducats = 0

        self.mock_player.controlled_locations = ["sienn", "paler"]
        self.mock_player.armies = ["rome", "sienn"]
        self.mock_player.fleets = ["UA", "paler"]
        self.mock_player.home_countries = []

        manager = IncomeManager(self.mock_game)

        manager.player_income(self.mock_player)

        # Comprobamos que se ha llamado a add_event
        self.mock_game.add_event.assert_called_once()
        event = self.mock_game.add_event.call_args[0][0]
        self.assertIsInstance(event, TurnEvent)
        self.assertEqual(event.type, EventType.PLAYER_INCOME)
        self.assertEqual(event.data["player"], "player_1")
        self.assertEqual(event.data["fixed_income"], 4)
        self.assertEqual(set(event.data["locations"]), {"sienn", "paler", "rome", "UA"})
        self.assertEqual(self.mock_player.ducats, 4)

    def test_player_income_provinces_seas_and_cities(self):
        """Calcula los ingresos de provincias, mares y ciudades"""
        self.mock_player.ducats = 0

        self.mock_player.controlled_locations = ["sienn", "paler", "flore"]
        self.mock_player.armies = ["rome", "sienn"]
        self.mock_player.fleets = ["UA", "paler"]
        self.mock_player.garrisons = ["venic"]
        self.mock_player.home_countries = []

        manager = IncomeManager(self.mock_game)

        manager.player_income(self.mock_player)

        # Comprobamos que se ha llamado a add_event
        self.mock_game.add_event.assert_called_once()
        event = self.mock_game.add_event.call_args[0][0]
        self.assertIsInstance(event, TurnEvent)
        self.assertEqual(event.type, EventType.PLAYER_INCOME)
        self.assertEqual(event.data["player"], "player_1")
        self.assertEqual(event.data["fixed_income"], 5 + 3)
        self.assertEqual(
            set(event.data["locations"]),
            {"sienn", "paler", "rome", "flore", "UA"},
        )
        self.assertEqual(
            set(event.data["cities"]),
            {"venic", "flore"},
        )
        self.assertEqual(self.mock_player.ducats, 5 + 3)

    def test_player_income_famine(self):
        """Calcula los ingresos con hambre"""
        self.mock_player.ducats = 0

        self.mock_player.controlled_locations = ["sienn", "paler", "flore"]
        self.mock_player.armies = ["rome", "sienn"]
        self.mock_player.fleets = ["UA", "paler"]
        self.mock_player.garrisons = ["venic"]
        self.mock_player.home_countries = []

        # Los ingresos de las provincias con hambre no cuentan, pero sí las ciudades
        # si tienen guarnición
        self.mock_game.famine = ["rome", "venic", "flore"]

        manager = IncomeManager(self.mock_game)

        manager.player_income(self.mock_player)

        # Comprobamos que se ha llamado a add_event
        self.mock_game.add_event.assert_called_once()
        event = self.mock_game.add_event.call_args[0][0]
        self.assertIsInstance(event, TurnEvent)
        self.assertEqual(event.type, EventType.PLAYER_INCOME)
        self.assertEqual(event.data["player"], "player_1")
        self.assertEqual(event.data["fixed_income"], 3 + 2)
        self.assertEqual(
            set(event.data["locations"]),
            {"sienn", "paler", "UA"},
        )
        self.assertEqual(
            set(event.data["cities"]),
            {"venic"},
        )
        self.assertEqual(self.mock_player.ducats, 3 + 2)

    def test_player_income_famine_and_rebellion(self):
        """Calcula los ingresos con hambre y rebeliones"""
        self.mock_player.ducats = 0

        self.mock_player.controlled_locations = ["sienn", "paler", "flore"]
        self.mock_player.armies = ["rome", "sienn"]
        self.mock_player.fleets = ["UA", "paler"]
        self.mock_player.garrisons = ["venic"]
        self.mock_player.home_countries = []

        # Los ingresos de las provincias con hambre no cuentan, pero sí las ciudades
        # si tienen guarnición
        self.mock_game.famine = ["rome"]
        self.mock_player.rebelled_provinces = ["venic"]
        self.mock_player.rebelled_cities = ["flore"]

        manager = IncomeManager(self.mock_game)

        manager.player_income(self.mock_player)

        # Comprobamos que se ha llamado a add_event
        self.mock_game.add_event.assert_called_once()
        event = self.mock_game.add_event.call_args[0][0]
        self.assertIsInstance(event, TurnEvent)
        self.assertEqual(event.type, EventType.PLAYER_INCOME)
        self.assertEqual(event.data["player"], "player_1")
        self.assertEqual(event.data["fixed_income"], 3 + 2)
        self.assertEqual(
            set(event.data["locations"]),
            {"sienn", "paler", "UA"},
        )
        self.assertEqual(
            set(event.data["cities"]),
            {"venic"},
        )
        self.assertEqual(self.mock_player.ducats, 3 + 2)

    @patch("machiavelli.engine.income.GameTables")
    def test_player_income_famine_and_rebellion_variable(self, mock_tables):
        """Calcula los ingresos con hambre, rebelión, e ingresos variables."""
        # Ajusto la tirada de las tablas
        self.mock_rng.randint.side_effect = [0, 5]

        # Y los datos necesarios
        mock_tables.variable_income = {
            "N": [1, 2, 3, 4, 5, 6],
            "rome": [11, 12, 13, 14, 15, 16],
        }

        self.mock_player.ducats = 0

        self.mock_player.controlled_locations = ["sienn", "paler", "flore", "rome"]
        self.mock_player.armies = ["rome", "sienn"]
        self.mock_player.fleets = ["UA", "paler"]
        self.mock_player.garrisons = ["venic"]
        self.mock_player.home_countries = ["N"]

        # Los ingresos de las provincias con hambre no cuentan, pero sí las ciudades
        # si tienen guarnición
        self.mock_game.famine = ["rome"]
        self.mock_player.rebelled_provinces = ["venic"]
        self.mock_player.rebelled_cities = ["flore"]

        manager = IncomeManager(self.mock_game, self.mock_rng)

        manager.player_income(self.mock_player)

        # Comprobamos que se ha llamado a add_event
        self.mock_game.add_event.assert_called_once()
        event = self.mock_game.add_event.call_args[0][0]
        self.assertIsInstance(event, TurnEvent)
        self.assertEqual(event.type, EventType.PLAYER_INCOME)
        self.assertEqual(event.data["player"], "player_1")
        self.assertEqual(event.data["fixed_income"], 3 + 2)
        self.assertEqual(
            set(event.data["locations"]),
            {"sienn", "paler", "UA"},
        )
        self.assertEqual(
            set(event.data["cities"]),
            {"venic"},
        )
        self.assertEqual(event.data["home_countries"], ["N"])
        self.assertEqual(event.data["special_provinces"], ["rome"])
        self.assertEqual(event.data["variable_income"], 1 + 16)
        self.assertEqual(self.mock_player.ducats, 3 + 2 + 1 + 16)
