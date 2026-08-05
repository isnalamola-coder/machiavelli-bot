"""Integration tests for the phase-7 game application service."""

from __future__ import annotations

import inspect
import os
import sqlite3
from collections.abc import Mapping
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter
from unittest.mock import Mock, patch

import pytest

from machiavelli import database
from machiavelli.engine import GameEngine
from machiavelli.engine.military import DislodgementResolverRequired
from machiavelli.engine.setup import SetupManager
from machiavelli.events import EventType, InvalidTurnEventError, JSONValue, TurnEvent
from machiavelli.game import Command as PublicCommand
from machiavelli.game import DuplicatePlayerException, PlayerNotFoundException
from machiavelli.game import Game as PublicGame
from machiavelli.game import Player as PublicPlayer
from machiavelli.game.command import Command
from machiavelli.game.game import Game
from machiavelli.game.player import Player
from machiavelli.repositories.game_repository import GameRepository
from machiavelli.services import GameService, TurnReporter, game_service_session


def make_service(conn: sqlite3.Connection) -> GameService:
    database.upgrade_connection(conn)
    return GameService(GameRepository(conn))


def database_snapshot(
    conn: sqlite3.Connection,
) -> dict[str, tuple[tuple[object, ...], ...]]:
    """Return the complete persisted aggregate state in deterministic row order."""
    tables = ("games", "players", "commands", "game_events")
    return {
        table: tuple(
            tuple(row)
            for row in conn.execute(f"SELECT * FROM {table} ORDER BY rowid").fetchall()
        )
        for table in tables
    }


def make_turn_event_history(
    valid_event_payloads: Mapping[EventType, dict[str, JSONValue]],
) -> list[TurnEvent]:
    """Build a representative 100-event history from the complete public catalog."""
    samples = tuple(valid_event_payloads.items())
    return [TurnEvent(*samples[index % len(samples)]) for index in range(100)]


def run_turn_event_pipeline(
    service: GameService,
    game: Game,
    *,
    cycles: int = 10,
) -> tuple[Game, list[str]]:
    """Persist, reload, and render one representative history repeatedly."""
    report: list[str] = []
    for _cycle in range(cycles):
        service.repo.save(game)
        game = service.get_game(game.channel_id)
        report = TurnReporter.generate(game)
    return game, report


@pytest.mark.parametrize(
    "db_path",
    ["canonical.db", Path("canonical.db")],
    ids=["str", "path"],
)
@pytest.mark.parametrize("raise_inside", [False, True], ids=["success", "exception"])
def test_game_service_session_uses_canonical_manager_and_closes_once(
    db_path: str | Path,
    raise_inside: bool,
) -> None:
    connection = Mock(name="connection")
    manager = Mock(name="manager")
    manager.get_connection.return_value = connection
    repository = Mock(spec=GameRepository)
    service = Mock(spec=GameService)

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
        if raise_inside:
            with pytest.raises(RuntimeError, match="fallo del caso de uso"):
                with game_service_session(db_path) as yielded:
                    assert yielded is service
                    raise RuntimeError("fallo del caso de uso")
        else:
            with game_service_session(db_path) as yielded:
                assert yielded is service

    manager_class.assert_called_once_with(db_path)
    manager.get_connection.assert_called_once_with()
    repository_class.assert_called_once_with(connection)
    service_class.assert_called_once_with(repository)
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


def test_get_turn_report_uses_the_turn_reporter() -> None:
    repository = Mock(spec=GameRepository)
    game = Mock(spec=Game)
    repository.get_by_channel.return_value = game
    service = GameService(repository)

    with patch.object(
        TurnReporter,
        "generate",
        return_value=["línea uno", "línea dos"],
    ) as generate:
        report = service.get_turn_report(7100)

    assert report == ["línea uno", "línea dos"]
    repository.get_by_channel.assert_called_once_with(7100)
    generate.assert_called_once_with(game)
    repository.save.assert_not_called()


def test_public_turn_boundaries_do_not_accept_dislodgement_resolvers() -> None:
    assert list(inspect.signature(GameService.run_turn).parameters) == [
        "self",
        "channel_id",
    ]
    assert list(inspect.signature(GameEngine.__init__).parameters) == [
        "self",
        "game",
        "rng",
    ]


def test_run_turn_renders_before_saving_and_returns_reporter_lines() -> None:
    repository = Mock(spec=GameRepository)
    game = Mock(spec=Game)
    service = GameService(repository)
    engine = Mock(name="engine")
    call_order: list[str] = []

    repository.get_by_channel.side_effect = lambda channel: (
        call_order.append("load") or game
    )
    engine.run.side_effect = lambda: call_order.append("run")
    repository.save.side_effect = lambda saved: call_order.append("save")

    with (
        patch(
            "machiavelli.services.game_service.GameEngine",
            return_value=engine,
        ) as engine_class,
        patch.object(
            TurnReporter,
            "generate",
            side_effect=lambda rendered: call_order.append("report") or ["informe"],
        ) as generate,
    ):
        report = service.run_turn(7101)

    assert report == ["informe"]
    assert call_order == ["load", "run", "report", "save"]
    engine_class.assert_called_once_with(game)
    generate.assert_called_once_with(game)
    repository.save.assert_called_once_with(game)


def test_run_turn_does_not_save_when_the_reporter_fails() -> None:
    repository = Mock(spec=GameRepository)
    game = Mock(spec=Game)
    repository.get_by_channel.return_value = game
    service = GameService(repository)
    engine = Mock(name="engine")
    failure = RuntimeError("fallo de presentación interno")

    with (
        patch(
            "machiavelli.services.game_service.GameEngine",
            return_value=engine,
        ),
        patch.object(TurnReporter, "generate", side_effect=failure),
        pytest.raises(RuntimeError, match="fallo de presentación interno"),
    ):
        service.run_turn(7102)

    engine.run.assert_called_once_with()
    repository.save.assert_not_called()


def test_dislodgement_failure_propagates_before_repository_commit() -> None:
    repository = Mock(spec=GameRepository)
    game = Mock(spec=Game)
    repository.get_by_channel.return_value = game
    service = GameService(repository)
    failure = DislodgementResolverRequired("Se requiere gestor de desalojos")

    with (
        patch("machiavelli.services.game_service.GameEngine") as engine_class,
        pytest.raises(DislodgementResolverRequired) as caught,
    ):
        engine_class.return_value.run.side_effect = failure
        service.run_turn(7103)

    assert caught.value is failure
    engine_class.assert_called_once_with(game)
    repository.save.assert_not_called()


def test_event_construction_failure_skips_reporter_and_save_and_keeps_persistence(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "atomic-event-construction.sqlite3"
    database.upgrade(db_path)

    with closing(sqlite3.connect(db_path)) as conn:
        service = GameService(GameRepository(conn))
        service.create_game("Evento inválido", 7199, "Be")
        before = database_snapshot(conn)

        def fail_during_event_construction(manager: SetupManager) -> None:
            game = manager.game
            game.turn_number = 99
            game.famine.append("milan")
            TurnEvent(type=EventType.START_GAME, data={"scenario": ""})

        with (
            patch(
                "machiavelli.engine.core.SetupManager.run",
                autospec=True,
                side_effect=fail_during_event_construction,
            ) as setup_run,
            patch.object(TurnReporter, "generate") as generate,
            patch.object(service.repo, "save", wraps=service.repo.save) as save,
            pytest.raises(InvalidTurnEventError),
        ):
            service.run_turn(7199)

        setup_run.assert_called_once()
        generate.assert_not_called()
        save.assert_not_called()

    with closing(sqlite3.connect(db_path)) as verification:
        assert database_snapshot(verification) == before


@pytest.mark.parametrize(
    "failure_stage",
    ["engine", "corrupt_history", "reporter", "save"],
)
def test_run_turn_failure_keeps_previous_persistence_intact(
    tmp_path: Path,
    failure_stage: str,
) -> None:
    db_path = tmp_path / f"atomic-{failure_stage}.sqlite3"
    database.upgrade(db_path)

    with closing(sqlite3.connect(db_path)) as conn:
        service = GameService(GameRepository(conn))
        game = service.create_game("Atomicidad", 7200, "Be")
        if failure_stage == "corrupt_history":
            conn.execute(
                """
                INSERT INTO game_events (game_id, event_type, data_json)
                VALUES (?, ?, ?)
                """,
                (game.database_id, "unknown_event", "{}"),
            )
            conn.commit()
        before = database_snapshot(conn)

        if failure_stage == "corrupt_history":
            with pytest.raises(InvalidTurnEventError):
                service.run_turn(7200)
        elif failure_stage == "engine":
            with (
                patch("machiavelli.services.game_service.GameEngine") as engine_class,
                pytest.raises(RuntimeError, match="fallo del motor"),
            ):
                engine_class.return_value.run.side_effect = RuntimeError(
                    "fallo del motor"
                )
                service.run_turn(7200)
        elif failure_stage == "reporter":
            with (
                patch("machiavelli.services.game_service.GameEngine") as engine_class,
                patch.object(
                    TurnReporter,
                    "generate",
                    side_effect=RuntimeError("fallo del reporter"),
                ),
                pytest.raises(RuntimeError, match="fallo del reporter"),
            ):
                engine_class.return_value.run.side_effect = lambda: setattr(
                    engine_class.call_args.args[0],
                    "turn_number",
                    99,
                )
                service.run_turn(7200)
        else:

            def fail_after_partial_write(
                aggregate: Game,
                connection: sqlite3.Connection,
            ) -> None:
                connection.execute(
                    "UPDATE games SET turn_number = 99 WHERE id = ?",
                    (aggregate.database_id,),
                )
                raise sqlite3.OperationalError("fallo del guardado")

            with (
                patch("machiavelli.services.game_service.GameEngine") as engine_class,
                patch.object(TurnReporter, "generate", return_value=["informe"]),
                patch.object(
                    Game,
                    "save",
                    autospec=True,
                    side_effect=fail_after_partial_write,
                ),
                pytest.raises(sqlite3.OperationalError, match="fallo del guardado"),
            ):
                engine_class.return_value.run.side_effect = lambda: setattr(
                    engine_class.call_args.args[0],
                    "turn_number",
                    99,
                )
                service.run_turn(7200)

    with closing(sqlite3.connect(db_path)) as verification:
        assert database_snapshot(verification) == before


def test_turn_event_pipeline_survives_ten_save_load_render_cycles(
    valid_event_payloads: Mapping[EventType, dict[str, JSONValue]],
) -> None:
    with closing(sqlite3.connect(":memory:")) as conn:
        service = make_service(conn)
        game = service.create_game("Pipeline de eventos", 7300, "Be")
        game.turn_number = 1
        game.turn_events = make_turn_event_history(valid_event_payloads)
        expected_events = tuple(game.turn_events)

        loaded, report = run_turn_event_pipeline(service, game)

        assert len(loaded.turn_events) == 100
        assert tuple(loaded.turn_events) == expected_events
        assert report[0] == "## 📜 Pipeline de eventos, turno 1"
        assert TurnReporter.EVENTS_HEADER in report
        assert TurnReporter.SITUATION_HEADER in report
        assert all(line.strip() for line in report)


@pytest.mark.skipif(
    os.getenv("MACHIAVELLI_REFERENCE_PERF") != "1",
    reason="Solo se ejecuta en el job de rendimiento de referencia",
)
def test_turn_event_pipeline_budget(
    valid_event_payloads: Mapping[EventType, dict[str, JSONValue]],
) -> None:
    with closing(sqlite3.connect(":memory:")) as conn:
        service = make_service(conn)
        game = service.create_game("Presupuesto de eventos", 7301, "Be")
        game.turn_number = 1
        game.turn_events = make_turn_event_history(valid_event_payloads)

        started = perf_counter()
        loaded, report = run_turn_event_pipeline(service, game)
        duration = perf_counter() - started

    assert len(loaded.turn_events) == 100
    assert report
    assert duration < 1.0, (
        f"duration={duration:.6f}s; cycles=10; events={len(loaded.turn_events)}"
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
