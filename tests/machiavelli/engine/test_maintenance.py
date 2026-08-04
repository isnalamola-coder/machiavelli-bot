# tests/machiavelli/engine/test_maintenance.py

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from machiavelli.engine.maintenance import MaintenanceResolver
from machiavelli.events import EventType
from machiavelli.game.command import Command


class DummyProvince:
    def __init__(self, city="city", is_venice=False, has_port=True):
        self.city = city
        self.is_venice = is_venice
        self.has_port = has_port


class TestMaintenanceResolver(unittest.TestCase):
    def setUp(self):
        self.mock_game = MagicMock()
        self.mock_player = MagicMock()
        self.mock_player.player_id = "player_1"
        self.mock_player.ducats = 20
        self.mock_player.home_countries = ["Italy"]
        self.mock_player.controlled_locations = ["rome", "flore"]
        self.mock_player.armies = []
        self.mock_player.fleets = []
        self.mock_player.garrisons = []
        self.mock_player.commands = []
        self.mock_player.rebelled_cities = set()

        self.mock_game.players = [self.mock_player]
        self.mock_game.scenario.province_home_country.side_effect = lambda p: (
            "Italy" if p in ["rome", "flore"] else "Other"
        )
        self.mock_game.map.provinces = {
            "rome": DummyProvince(city="city"),
            "flore": DummyProvince(city="fortified"),
            "venic": DummyProvince(city="city", has_port=True, is_venice=True),
        }

    def test_set_default_commands(self):
        """Verifica que se asignan órdenes 'M' por defecto."""
        self.mock_player.armies = ["rome"]
        self.mock_player.fleets = ["venic"]
        self.mock_player.commands = []

        MaintenanceResolver._set_default_commands(self.mock_player)

        commands_actors = {c.actor for c in self.mock_player.commands}
        self.assertIn("A rome", commands_actors)
        self.assertIn("F venic", commands_actors)

    def test_run_successful_maintenance(self):
        """Ejecuta correctamente el mantenimiento pagando las unidades existentes."""
        self.mock_player.armies = ["rome"]
        self.mock_player.ducats = 10
        self.mock_player.commands = [
            Command(self.mock_game, self.mock_player, "A rome", "M")
        ]

        resolver = MaintenanceResolver(self.mock_game)
        resolver.run()

        self.assertEqual(self.mock_player.ducats, 7)  # 10 - 3
        self.mock_game.add_event.assert_called_once()

        event_arg = self.mock_game.add_event.call_args[0][0]
        self.assertEqual(event_arg.type, EventType.PLAYER_MAINTENANCE)
        self.assertEqual(event_arg.data["expenses"], 3)
        self.assertIn("A rome", event_arg.data["maintained"])

    def test_run_failed_maintenance_due_to_funds(self):
        """Desbanca unidades si no hay suficientes ducados para mantenerlas."""
        self.mock_player.armies = ["rome", "flore"]  # Coste total: 6
        self.mock_player.ducats = 3  # Solo para una
        self.mock_player.commands = [
            Command(self.mock_game, self.mock_player, "A rome", "M"),
            Command(self.mock_game, self.mock_player, "A flore", "M"),
        ]

        resolver = MaintenanceResolver(self.mock_game)
        resolver.run()

        self.assertEqual(self.mock_player.ducats, 0)
        self.assertIn("rome", self.mock_player.armies)
        self.assertNotIn("flore", self.mock_player.armies)

        event_arg = self.mock_game.add_event.call_args[0][0]
        self.assertIn("A flore", event_arg.data["failed_to_maintain"])

    def test_run_successful_recruitment(self):
        """Recluta con éxito una unidad si cumple condiciones y hay fondos."""
        self.mock_player.armies = []
        self.mock_player.ducats = 5
        self.mock_player.commands = [
            Command(self.mock_game, self.mock_player, "A rome", "R")
        ]

        resolver = MaintenanceResolver(self.mock_game)
        resolver.run()

        self.assertEqual(self.mock_player.ducats, 2)
        self.assertIn("rome", self.mock_player.armies)

        event_arg = self.mock_game.add_event.call_args[0][0]
        self.assertIn("A rome", event_arg.data["recruited"])

    def test_run_recruitment_failures(self):
        """Valida que falle el reclutamiento por fondos insuficientes."""
        self.mock_player.ducats = 2  # Menos de 3
        self.mock_player.commands = [
            Command(self.mock_game, self.mock_player, "A rome", "R")
        ]

        resolver = MaintenanceResolver(self.mock_game)
        resolver.run()

        event_arg = self.mock_game.add_event.call_args[0][0]
        failed_reasons = dict(event_arg.data["failed_to_recruit"])
        self.assertEqual(failed_reasons["A rome"], "no_enough_funds")
