# tests/machiavelli/game/test_game.py

import unittest

from machiavelli.events import EventType, TurnEvent
from machiavelli.game.game import Game
from tests.machiavelli.engine.helpers import (
    create_mock_game,
    create_mock_player,
)


class TestRetiredGameAlgorithms(unittest.TestCase):
    """Verify duplicated historical algorithms are absent from the aggregate."""

    def test_initial_setup_is_not_part_of_game_api(self):
        self.assertFalse(hasattr(Game, "initial_setup"))

    def test_spring_start_is_not_part_of_game_api(self):
        self.assertFalse(hasattr(Game, "spring_start"))


class TestAddEvent(unittest.TestCase):
    def test_preserves_exact_turn_event_object(self):
        game = Game("event identity")
        event = TurnEvent(EventType.START_GAME, {"scenario": "Rinascimento"})

        game.add_event(event)

        self.assertIs(game.turn_events[0], event)

    def test_preserves_insertion_order(self):
        game = Game("event order")
        first = TurnEvent(EventType.START_GAME, {"scenario": "Rinascimento"})
        second = TurnEvent(EventType.START_SEASON, {"year": 1454, "season": 1})

        game.add_event(first)
        game.add_event(second)

        self.assertEqual(game.turn_events, [first, second])
        self.assertIs(game.turn_events[0], first)
        self.assertIs(game.turn_events[1], second)

    def test_rejects_string_immediately_without_modifying_history(self):
        game = Game("event rejection")
        existing = TurnEvent(EventType.START_GAME, {"scenario": "Rinascimento"})
        game.add_event(existing)

        with self.assertRaises(TypeError):
            game.add_event("start_game|{}")  # type: ignore[arg-type]

        self.assertEqual(game.turn_events, [existing])
        self.assertIs(game.turn_events[0], existing)


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
