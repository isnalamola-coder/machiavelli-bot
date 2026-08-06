# tests/machiavelli/game/test_game.py

import unittest

from machiavelli.events import EventType, TurnEvent
from machiavelli.game.game import Game
from tests.machiavelli.engine.helpers import (
    create_mock_game,
    create_mock_player,
)


class TestRemovedLegacyAlgorithms(unittest.TestCase):
    """Fija la retirada de los algoritmos duplicados del agregado."""

    def test_initial_setup_does_not_exist(self):
        self.assertNotIn("initial_setup", Game.__dict__)

    def test_spring_start_does_not_exist(self):
        self.assertNotIn("spring_start", Game.__dict__)


class TestTurnEvents(unittest.TestCase):
    def test_add_event_keeps_object_identity_and_order(self):
        game = Game("typed-history")
        first = TurnEvent(EventType.START_GAME, {"scenario": "Be"})
        second = TurnEvent(EventType.START_SEASON, {"year": 1454, "season": 0})

        game.add_event(first)
        game.add_event(second)
        game.add_event(first)

        self.assertEqual(game.turn_events, [first, second, first])
        self.assertIs(game.turn_events[0], first)
        self.assertIs(game.turn_events[1], second)
        self.assertIs(game.turn_events[2], first)

    def test_add_event_rejects_strings(self):
        game = Game("typed-history")

        with self.assertRaisesRegex(TypeError, "TurnEvent"):
            game.add_event("start_game|{}")  # type: ignore[arg-type]

        self.assertEqual(game.turn_events, [])


class TestGetUnitOwner(unittest.TestCase):
    """Tests para el método get_unit_owner de Game."""

    def setUp(self):
        """Prepara la instancia de Game y los jugadores para las pruebas."""
        self.game = create_mock_game()
        # Enlazamos el método real de la clase Game a la instancia mockeada
        self.game.get_unit_owner = Game.get_unit_owner.__get__(self.game, Game)

        self.player1 = create_mock_player("P1")
        self.player2 = create_mock_player("P2")

        self.player1.armies = []
        self.player1.fleets = []
        self.player1.garrisons = []

        self.player2.armies = []
        self.player2.fleets = []
        self.player2.garrisons = []

        self.game.players = [self.player1, self.player2]
        self.game.independent_garrisons = []

    def test_get_unit_owner_player_army(self):
        """Devuelve el jugador correcto cuando se consulta un ejército existente."""
        self.player1.armies = ["tivol"]

        owner = self.game.get_unit_owner("A tivol")

        self.assertEqual(owner, self.player1)

    def test_get_unit_owner_player_fleet(self):
        """Devuelve el jugador correcto para una flota existente."""
        self.player1.fleets = ["prove S"]

        owner = self.game.get_unit_owner("F prove")

        self.assertEqual(owner, self.player1)

    def test_get_unit_owner_player_garrison(self):
        """Devuelve el jugador correcto para una guarnición."""
        self.player1.garrisons = ["rome"]

        owner = self.game.get_unit_owner("G rome")

        self.assertEqual(owner, self.player1)

    def test_get_unit_owner_multiple_players(self):
        """Verifica que asigna la unidad al jugador correcto cuando hay varios."""
        self.player1.armies = ["flore"]
        self.player2.armies = ["milan"]

        self.assertEqual(self.game.get_unit_owner("A flore"), self.player1)
        self.assertEqual(self.game.get_unit_owner("A milan"), self.player2)

    def test_get_unit_owner_independent_garrison(self):
        """Devuelve None si la guarnición existe pero es independiente."""
        self.game.independent_garrisons = ["pisa"]

        owner = self.game.get_unit_owner("G pisa")

        self.assertIsNone(owner)

    def test_get_unit_owner_unit_does_not_exist(self):
        """Lanza ValueError si la unidad no existe."""
        with self.assertRaises(ValueError):
            self.game.get_unit_owner("A prove")

    def test_get_unit_owner_invalid_format(self):
        """Lanza ValueError si el formato del identificador es incorrecto."""
        with self.assertRaises(ValueError):
            self.game.get_unit_owner("Aprove")
