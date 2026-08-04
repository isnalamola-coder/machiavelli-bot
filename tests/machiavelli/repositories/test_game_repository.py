"""Tests for aggregate persistence through GameRepository."""

import sqlite3

import pytest

from machiavelli import database
from machiavelli.game.command import Command
from machiavelli.game.game import Game
from machiavelli.game.player import Player
from machiavelli.repositories.game_repository import GameRepository


@pytest.fixture
def connection():
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")
    database.upgrade_connection(conn)
    yield conn
    conn.close()


def test_save_and_load_complete_game(connection: sqlite3.Connection) -> None:
    repo = GameRepository(connection)
    game = Game(
        name="Repositorio",
        channel_id=1234,
        famine=["rome"],
        independent_garrisons=["pisa"],
        besieges=["flore"],
        turn_events=["evento anterior"],
    )
    player = Player(
        game,
        "P1",
        discord_id=9876,
        controlled_locations=["rome"],
        armies=["rome"],
        ducats=12,
        power="M",
    )
    player.commands = [Command(game, player, "A rome", "H", None)]
    game.players = [player]

    repo.save(game)

    by_id = repo.get_by_id(game.database_id)
    by_name = repo.get_by_name("Repositorio")
    by_channel = repo.get_by_channel(1234)

    for loaded in (by_id, by_name, by_channel):
        assert loaded.name == "Repositorio"
        assert loaded.famine == ["rome"]
        assert loaded.independent_garrisons == ["pisa"]
        assert loaded.besieges == ["flore"]
        assert loaded.turn_events == ["evento anterior"]
        assert len(loaded.players) == 1
        assert loaded.players[0].player_id == "P1"
        assert loaded.players[0].controlled_locations == ["rome"]
        assert loaded.players[0].commands[0].target is None


def test_save_rolls_back_complete_new_game_on_player_command_error(
    connection: sqlite3.Connection,
) -> None:
    repo = GameRepository(connection)
    game = Game(name="Debe revertirse", channel_id=555)
    first = Player(game, "P1", ducats=10)
    first.commands = [Command(game, first, "A rome", "H", None)]
    second = Player(game, "P2", ducats=20)
    second.commands = [
        Command(game, second, None, "H", None)  # type: ignore[arg-type]
    ]
    game.players = [first, second]

    with pytest.raises(sqlite3.IntegrityError):
        repo.save(game)

    assert game.database_id is None
    assert connection.execute("SELECT COUNT(*) FROM games").fetchone()[0] == 0
    assert connection.execute("SELECT COUNT(*) FROM players").fetchone()[0] == 0
    assert connection.execute("SELECT COUNT(*) FROM commands").fetchone()[0] == 0
