"""Integration tests for the phase-7 game application service."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from inspect import signature
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

import pytest

from machiavelli import database
from machiavelli.engine import GameEngine
from machiavelli.engine.military import DislodgementResolverRequired
from machiavelli.events import InvalidTurnEventError
from machiavelli.game import Command as PublicCommand
from machiavelli.game import DuplicatePlayerException, PlayerNotFoundException
from machiavelli.game import Game as PublicGame
from machiavelli.game import Player as PublicPlayer
from machiavelli.game.command import Command
from machiavelli.game.game import Game
from machiavelli.game.player import Player
from machiavelli.repositories.game_repository import GameRepository
from machiavelli.services import GameService, game_service_session


def make_service(conn: sqlite3.Connection) -> GameService:
    database.upgrade_connection(conn)
    return GameService(GameRepository(conn))


def test_game_service_session_builds_once_and_closes_on_success() -> None:
    connection = Mock(name="connection")
    manager = Mock(name="manager")
    manager.get_connection.return_value = connection
    repository = Mock(name="repository")
    service = Mock(name="service")
    db_path = Path("game.db")

    with (
        patch(
            "machiavelli.services.game_service.DatabaseManager",
            return_value=manager,
        ) as manager_class,
        patch(
            "machiavelli.services.game_service.GameRepository",
            return_value=repository,
        ) as repository_class,
        patch(
            "machiavelli.services.game_service.GameService",
            return_value=service,
        ) as service_class,
    ):
        with game_service_session(db_path) as yielded:
            assert yielded is service

    manager_class.assert_called_once_with(db_path)
    manager.get_connection.assert_called_once_with()
    repository_class.assert_called_once_with(connection)
    service_class.assert_called_once_with(repository)
    connection.close.assert_called_once_with()


def test_game_service_session_closes_on_exception() -> None:
    connection = Mock(name="connection")
    manager = Mock(name="manager")
    manager.get_connection.return_value = connection
    failure = RuntimeError("boom")

    with (
        patch(
            "machiavelli.services.game_service.DatabaseManager",
            return_value=manager,
        ),
        pytest.raises(RuntimeError) as caught,
    ):
        with game_service_session("game.db"):
            raise failure

    assert caught.value is failure
    connection.close.assert_called_once_with()


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


def test_turn_boundaries_do_not_accept_a_dislodgement_resolver() -> None:
    assert "dislodgement_resolver" not in signature(GameService.run_turn).parameters
    assert "dislodgement_resolver" not in signature(GameEngine).parameters


def test_get_turn_report_uses_the_reporter_and_returns_its_lines() -> None:
    repository = Mock(name="repository")
    game = Mock(name="game")
    repository.get_by_channel.return_value = game
    service = GameService(repository)

    with patch(
        "machiavelli.services.game_service.TurnReporter.generate",
        return_value=["report one", "report two"],
    ) as generate:
        report = service.get_turn_report(7004)

    assert report == ["report one", "report two"]
    generate.assert_called_once_with(game)
    repository.save.assert_not_called()


def test_run_turn_uses_strict_load_engine_reporter_save_order() -> None:
    calls: list[str] = []
    repository = Mock(name="repository")
    game = Mock(name="game")
    repository.get_by_channel.side_effect = lambda _channel_id: (
        calls.append("load") or game
    )
    repository.save.side_effect = lambda _game: calls.append("save")
    service = GameService(repository)

    with (
        patch("machiavelli.services.game_service.GameEngine") as engine_class,
        patch("machiavelli.services.game_service.TurnReporter.generate") as generate,
    ):
        engine_class.return_value.run.side_effect = lambda: calls.append("engine")
        generate.side_effect = lambda _game: calls.append("reporter") or ["turn report"]
        report = service.run_turn(7005)

    assert report == ["turn report"]
    assert calls == ["load", "engine", "reporter", "save"]
    engine_class.assert_called_once_with(game)
    engine_class.return_value.run.assert_called_once_with()
    generate.assert_called_once_with(game)
    repository.save.assert_called_once_with(game)


@pytest.mark.parametrize(
    "failure",
    [
        RuntimeError("engine failed"),
        InvalidTurnEventError(row_id=4, event_type="broken"),
        DislodgementResolverRequired("retreat required"),
    ],
)
def test_run_turn_does_not_save_when_engine_fails(failure: Exception) -> None:
    repository = Mock(name="repository")
    repository.get_by_channel.return_value = Mock(name="game")
    service = GameService(repository)

    with (
        patch("machiavelli.services.game_service.GameEngine") as engine_class,
        pytest.raises(type(failure)) as caught,
    ):
        engine_class.return_value.run.side_effect = failure
        service.run_turn(7006)

    assert caught.value is failure
    repository.save.assert_not_called()


def test_run_turn_rolls_back_persistence_when_save_fails() -> None:
    with closing(sqlite3.connect(":memory:")) as conn:
        service = make_service(conn)
        service.create_game("Rollback", 7007, "Be")
        before = conn.execute(
            "SELECT name, channel_id, scenario_id, turn_number FROM games"
        ).fetchall()
        conn.execute(
            """
            CREATE TRIGGER fail_game_update
            BEFORE UPDATE ON games
            BEGIN
                SELECT RAISE(ABORT, 'forced save failure');
            END
            """
        )

        with (
            patch("machiavelli.services.game_service.GameEngine") as engine_class,
            patch(
                "machiavelli.services.game_service.TurnReporter.generate",
                return_value=["turn report"],
            ),
            pytest.raises(sqlite3.IntegrityError),
        ):
            engine_class.return_value.run.side_effect = lambda: setattr(
                engine_class.call_args.args[0],
                "turn_number",
                1,
            )
            service.run_turn(7007)

        after = conn.execute(
            "SELECT name, channel_id, scenario_id, turn_number FROM games"
        ).fetchall()
        assert after == before


def test_run_turn_does_not_save_when_reporting_fails() -> None:
    repository = Mock(name="repository")
    game = Mock(name="game")
    repository.get_by_channel.return_value = game
    service = GameService(repository)
    failure = InvalidTurnEventError(row_id=9, event_type="broken")

    with (
        patch("machiavelli.services.game_service.GameEngine"),
        patch(
            "machiavelli.services.game_service.TurnReporter.generate",
            side_effect=failure,
        ),
        pytest.raises(InvalidTurnEventError) as caught,
    ):
        service.run_turn(7006)

    assert caught.value is failure
    repository.save.assert_not_called()


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
