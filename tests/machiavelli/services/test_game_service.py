"""Integration tests for the phase-7 game application service."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from machiavelli import database
from machiavelli.game import Command as PublicCommand
from machiavelli.game import DuplicatePlayerException, PlayerNotFoundException
from machiavelli.game import Game as PublicGame
from machiavelli.game import Player as PublicPlayer
from machiavelli.game.command import Command
from machiavelli.game.game import Game
from machiavelli.game.player import Player
from machiavelli.repositories.game_repository import GameRepository
from machiavelli.services import GameService


def make_service(conn: sqlite3.Connection) -> GameService:
    database.upgrade_connection(conn)
    return GameService(GameRepository(conn))


def test_create_load_and_status_use_the_canonical_domain() -> None:
    with closing(sqlite3.connect(":memory:")) as conn:
        service = make_service(conn)

        created = service.create_game("Integración", 7001, "Be")
        loaded = service.get_game(7001)
        status = service.get_game_status(7001)

        assert PublicGame is Game
        assert PublicPlayer is Player
        assert PublicCommand is Command
        assert isinstance(created, Game)
        assert isinstance(loaded, Game)
        assert created.database_id == loaded.database_id
        assert loaded.scenario_id == "Be"
        assert loaded.scenario is not None
        assert loaded.map is not None
        assert status == {
            "id": created.database_id,
            "name": "Integración",
            "turn": 0,
            "scenario": "The balance of power (six players)",
            "scenario_id": "Be",
            "players_count": 0,
            "players": [],
        }


def test_add_remove_and_resolve_player_persist_the_authoritative_collection() -> None:
    with closing(sqlite3.connect(":memory:")) as conn:
        service = make_service(conn)
        service.create_game("Jugadores", 7002, "Be")

        assert service.add_player(7002, 101, "P1") == [("P1", 101)]
        assert service.add_player(7002, 202, "P2") == [("P1", 101), ("P2", 202)]

        game = service.get_game(7002)
        game.players[0].power = "M"
        game.players[0].commands = [
            Command(game, game.players[0], "A milan", "H", None)
        ]
        service.repo.save(game)

        assert service.resolve_player(game, 101).player_id == "P1"
        assert service.resolve_player(game, 0, "M").player_id == "P1"
        assert service.resolve_player(game, 0, "p2").discord_id == 202

        removed, remaining = service.remove_player(7002, 101)
        assert removed == "P1"
        assert remaining == [("P2", 202)]
        assert [player.player_id for player in service.get_game(7002).players] == ["P2"]
        assert conn.execute(
            "SELECT COUNT(*) FROM players WHERE player_id = 'P1'"
        ).fetchone() == (0,)
        assert conn.execute(
            "SELECT COUNT(*) FROM commands WHERE player_id = 'P1'"
        ).fetchone() == (0,)

        with pytest.raises(DuplicatePlayerException):
            service.add_player(7002, 202, "P3")
        with pytest.raises(PlayerNotFoundException):
            service.remove_player(7002, 999)


def test_submit_and_replace_command_survive_reload() -> None:
    with closing(sqlite3.connect(":memory:")) as conn:
        service = make_service(conn)
        service.create_game("Órdenes", 7003, "Be")
        service.add_player(7003, 303, "P1")

        game = service.get_game(7003)
        game.turn_number = 2
        game.players[0].armies = ["milan"]
        service.repo.save(game)

        first_report = service.submit_command(
            7003,
            303,
            {"actor": "A milan", "command": "H", "target": None},
        )
        replacement_report = service.submit_command(
            7003,
            303,
            {"actor": "A milan", "command": "A", "target": "pavia"},
        )

        loaded = service.get_game(7003)
        commands = loaded.players[0].commands
        assert first_report[0].startswith("Orden `")
        assert any("Sustituye la orden anterior" in line for line in replacement_report)
        assert len(commands) == 1
        assert commands[0].game is loaded
        assert commands[0].player is loaded.players[0]
        assert (commands[0].actor, commands[0].command, commands[0].target) == (
            "A milan",
            "A",
            "pavia",
        )


def test_run_turn_persists_and_can_continue_after_reopening_connection() -> None:
    with TemporaryDirectory() as directory:
        db_path = Path(directory) / "phase7.db"
        database.upgrade(str(db_path))

        with closing(sqlite3.connect(db_path)) as conn:
            service = GameService(GameRepository(conn))
            service.create_game("Reinicio", 7004, "Be")
            for index in range(6):
                service.add_player(7004, 400 + index, f"P{index + 1}")

            report = service.run_turn(7004)
            persisted = service.get_game(7004)

            assert report
            assert persisted.turn_number == 1
            assert all(player.power is not None for player in persisted.players)
            assert all(player.commands == [] for player in persisted.players)
            assert persisted.turn_events

        with closing(sqlite3.connect(db_path)) as reopened:
            continued_service = GameService(GameRepository(reopened))
            restored = continued_service.get_game(7004)

            assert restored.turn_number == 1
            assert len(restored.players) == 6
            assert all(player.game is restored for player in restored.players)
            assert all(
                command.game is restored and command.player is player
                for player in restored.players
                for command in player.commands
            )
            assert restored.scenario is not None
            assert restored.map is not None
