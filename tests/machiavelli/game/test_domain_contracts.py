from __future__ import annotations

import importlib

from machiavelli.game.command import Command
from machiavelli.game.game import Game
from machiavelli.game.player import Player


def test_player_keeps_its_game_reference() -> None:
    game = Game(name="contract")

    player = Player(game=game, player_id="P1")

    assert player.game is game
    assert player.player_id == "P1"


def test_player_derived_identifiers_and_power_alias_are_consistent() -> None:
    game = Game(name="contract", database_id=42)
    player = Player(game=game, player_id="P1", power="M")

    assert player.game_id == 42
    assert player.power == "M"
    assert player.power_id == "M"

    player.power = "V"
    assert player.power_id == "V"


def test_player_mutable_defaults_are_not_shared() -> None:
    game = Game(name="contract")
    first = Player(game=game, player_id="P1")
    second = Player(game=game, player_id="P2")

    first.armies.append("milan")
    first.commands.append(
        Command(game=game, player=first, actor="A milan", command="H")
    )

    assert second.armies == []
    assert second.commands == []


def test_player_adds_and_removes_the_exact_command_object() -> None:
    game = Game(name="contract")
    player = Player(game=game, player_id="P1")
    command = Command(game=game, player=player, actor="A milan", command="H")

    player.add_command(command)
    assert player.commands == [command]
    assert player.commands[0] is command

    player.remove_command(command)
    assert player.commands == []


def test_command_keeps_domain_references_and_derives_identifiers() -> None:
    game = Game(name="contract", database_id=42)
    player = Player(game=game, player_id="P1")

    command = Command(
        game=game,
        player=player,
        actor="A milan",
        command="H",
        target=None,
    )

    assert command.game is game
    assert command.player is player
    assert command.game_id == 42
    assert command.player_id == "P1"
    assert command.target is None


def test_public_game_api_exports_the_canonical_class_objects() -> None:
    public_api = importlib.import_module("machiavelli.game")

    assert public_api.Command is Command
    assert public_api.Player is Player
    assert public_api.Game is Game
