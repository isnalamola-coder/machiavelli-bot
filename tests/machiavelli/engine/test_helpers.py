"""Pruebas de las factorías y snapshots militares compartidos."""

import unittest

from machiavelli.game import Command, Game, Player
from machiavelli.map import Map
from tests.machiavelli.engine.helpers import (
    create_military_game,
    iter_military_orderings,
    military_snapshot,
)


class TestMilitaryHelpers(unittest.TestCase):
    """Comprueba aislamiento, ordenaciones incidentales y enlaces de órdenes."""
    def test_factory_snapshot_and_orderings(self):
        def factory() -> Game:
            """Crea una partida fresca para cada variante de ordenación."""
            return create_military_game(
                Map(),
                players=[
                    {
                        "player_id": "P1",
                        "armies": ["rome", "flore"],
                        "fleets": ["prove S"],
                        "garrisons": ["pisa"],
                        "rebelled_provinces": ["rome"],
                        "rebelled_cities": ["pisa"],
                        "orders": [
                            ("A rome", "A", "flore"),
                            ("A rome", "A", "pisa"),
                        ],
                    },
                    {
                        "player_id": "P2",
                        "armies": ["sienn"],
                        "fleets": ["venic N"],
                        "garrisons": ["lucca"],
                        "orders": [("A sienn", "A", "rome")],
                    },
                ],
                independent_garrisons=["lucca"],
                besieges=["pisa"],
                turn_events=["evento"],
            )

        game = factory()
        self.assertIsInstance(game, Game)
        self.assertIsInstance(game.players[0], Player)
        self.assertEqual(
            military_snapshot(game),
            (
                (("P1", "flore"), ("P1", "rome"), ("P2", "sienn")),
                (("P1", "prove S"), ("P2", "venic N")),
                (("P1", "pisa"), ("P2", "lucca")),
                ("lucca",),
                ("pisa",),
                (("P1", "city", "pisa"), ("P1", "province", "rome")),
                ("evento",),
            ),
        )

        games = list(iter_military_orderings(factory))
        self.assertEqual(len(games), 4)
        self.assertEqual(
            [player.player_id for player in games[0].players], ["P1", "P2"]
        )
        self.assertEqual(
            [player.player_id for player in games[1].players], ["P2", "P1"]
        )
        self.assertEqual(games[0].players[0].armies, ["rome", "flore"])
        self.assertEqual(games[2].players[0].armies, ["flore", "rome"])

        snapshots = [military_snapshot(variant) for variant in games]
        self.assertTrue(all(snapshot == snapshots[0] for snapshot in snapshots))

        for variant in games:
            player = next(p for p in variant.players if p.player_id == "P1")
            targets = [
                command.target
                for command in player.commands
                if command.actor == "A rome"
            ]
            self.assertEqual(targets, ["flore", "pisa"])
            self.assertTrue(
                all(isinstance(command, Command) for command in player.commands)
            )
            self.assertTrue(
                all(command.player is player for command in player.commands)
            )
            self.assertTrue(all(command.game is variant for command in player.commands))

        players = [player for variant in games for player in variant.players]
        commands = [command for player in players for command in player.commands]
        self.assertEqual(len({id(player) for player in players}), len(players))
        self.assertEqual(len({id(command) for command in commands}), len(commands))


if __name__ == "__main__":
    unittest.main()
