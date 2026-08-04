# tests/machiavelli/game/test_game.py

import unittest

from machiavelli.game.game import Game
from tests.machiavelli.engine.helpers import (
    create_mock_game,
    create_mock_player,
)


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
