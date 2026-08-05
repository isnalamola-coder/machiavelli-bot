"""Aggregate persistence tests for structured turn events."""

import sqlite3
from collections.abc import Mapping
from pathlib import Path

import pytest

from machiavelli import database
from machiavelli.events import (
    EventType,
    InvalidTurnEventError,
    JSONValue,
    TurnEvent,
)
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
    event = TurnEvent(EventType.START_GAME, {"scenario": "Rinascimento"})
    game = Game(
        name="Repositorio",
        channel_id=1234,
        famine=["rome"],
        independent_garrisons=["pisa"],
        besieges=["flore"],
        turn_events=[event],
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

    for loaded in (
        repo.get_by_id(game.database_id),
        repo.get_by_name("Repositorio"),
        repo.get_by_channel(1234),
    ):
        assert loaded.name == "Repositorio"
        assert loaded.famine == ["rome"]
        assert loaded.independent_garrisons == ["pisa"]
        assert loaded.besieges == ["flore"]
        assert loaded.turn_events == [event]
        assert loaded.players[0].commands[0].target is None


def test_all_event_types_and_repeats_survive_ten_replacing_save_load_cycles(
    connection: sqlite3.Connection,
    valid_event_payloads: Mapping[EventType, dict[str, JSONValue]],
) -> None:
    repo = GameRepository(connection)
    expected = [
        TurnEvent(event_type, payload)
        for event_type, payload in valid_event_payloads.items()
    ]
    repeated_start = expected[0]
    repeated_disaster = expected[5]
    expected.insert(3, repeated_start)
    expected.append(repeated_disaster)
    game = Game("Diez ciclos", turn_events=expected)
    previous_row_ids: set[int] = set()

    for _ in range(10):
        repo.save(game)
        rows = connection.execute(
            "SELECT id, event_type, data_json FROM game_events "
            "WHERE game_id = ? ORDER BY id",
            (game.database_id,),
        ).fetchall()
        current_row_ids = {row[0] for row in rows}
        assert len(rows) == len(expected)
        assert previous_row_ids.isdisjoint(current_row_ids)
        previous_row_ids = current_row_ids

        game = repo.get_by_id(game.database_id)
        assert game.turn_events == expected
        assert [event.type for event in game.turn_events] == [
            event.type for event in expected
        ]
        assert game.turn_events[0] == game.turn_events[3]
        assert game.turn_events[-1] == repeated_disaster

    assert [row[1] for row in rows] == [event.type.value for event in expected]
    assert [row[2] for row in rows] == [event.to_json() for event in expected]


@pytest.mark.parametrize(
    ("event_type", "data_json"),
    [
        ("unknown_type", "{}"),
        ("start_game", "not-json"),
        ("start_game", "[]"),
        ("start_game", "{}"),
    ],
    ids=["unknown-type", "malformed-json", "non-object-json", "invalid-payload"],
)
def test_sql_corruption_aborts_on_first_bad_row_with_diagnostic_context(
    connection: sqlite3.Connection,
    event_type: str,
    data_json: str,
) -> None:
    repo = GameRepository(connection)
    game = Game("Corrupta")
    repo.save(game)
    connection.execute(
        "INSERT INTO game_events (game_id, event_type, data_json) VALUES (?, ?, ?)",
        (game.database_id, "start_game", '{"scenario":"válido"}'),
    )
    first_corrupt = connection.execute(
        "INSERT INTO game_events (game_id, event_type, data_json) VALUES (?, ?, ?)",
        (game.database_id, event_type, data_json),
    )
    later_corrupt = connection.execute(
        "INSERT INTO game_events (game_id, event_type, data_json) VALUES (?, ?, ?)",
        (game.database_id, "start_season", "{}"),
    )
    connection.commit()

    with pytest.raises(InvalidTurnEventError) as error_info:
        repo.get_by_id(game.database_id)

    assert error_info.value.row_id == first_corrupt.lastrowid
    assert error_info.value.row_id != later_corrupt.lastrowid
    assert error_info.value.event_type == event_type
    assert error_info.value.__cause__ is not None
    assert f"fila {first_corrupt.lastrowid}" in str(error_info.value)
    assert repr(event_type) in str(error_info.value)
    assert data_json not in str(error_info.value)


def test_save_rejects_non_event_history_and_rolls_back_complete_aggregate(
    connection: sqlite3.Connection,
) -> None:
    repo = GameRepository(connection)
    game = Game(
        name="Evento inválido",
        channel_id=556,
        turn_events=[None],  # type: ignore[list-item]
    )
    player = Player(game, "P1")
    player.commands = [Command(game, player, "A rome", "H", None)]
    game.players = [player]

    with pytest.raises(TypeError, match="TurnEvent"):
        repo.save(game)

    assert game.database_id is None
    for table in ("games", "players", "commands", "game_events"):
        assert connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0


def _aggregate_snapshot(
    conn: sqlite3.Connection,
) -> dict[str, list[tuple[object, ...]]]:
    return {
        table: conn.execute(f"SELECT * FROM {table} ORDER BY rowid").fetchall()
        for table in ("games", "players", "commands", "game_events")
    }


def test_second_event_insert_failure_restores_previous_snapshot_on_new_connection(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "aggregate-rollback.sqlite3"
    connection = sqlite3.connect(database_path)
    connection.execute("PRAGMA foreign_keys = ON")
    database.upgrade_connection(connection)
    repo = GameRepository(connection)
    game = Game(
        "Rollback completo",
        channel_id=771,
        famine=["rome"],
        turn_events=[
            TurnEvent(EventType.START_GAME, {"scenario": "Rinascimento"}),
        ],
    )
    player = Player(
        game,
        "P1",
        discord_id=991,
        controlled_locations=["rome"],
        armies=["rome"],
        ducats=12,
        power="M",
    )
    player.commands = [Command(game, player, "A rome", "H", None)]
    game.players = [player]
    repo.save(game)
    previous_snapshot = _aggregate_snapshot(connection)

    game.name = "Rollback modificado"
    game.channel_id = 772
    game.famine = ["rome", "flore"]
    player.controlled_locations = ["flore"]
    player.armies = ["flore"]
    player.ducats = 99
    player.commands = [Command(game, player, "A flore", "D", None)]
    game.turn_events = [
        TurnEvent(EventType.START_GAME, {"scenario": "Modificado"}),
        TurnEvent(EventType.START_SEASON, {"year": 1455, "season": 2}),
    ]
    connection.execute(
        """
        CREATE TRIGGER fail_second_event
        BEFORE INSERT ON game_events
        WHEN NEW.event_type = 'start_season'
        BEGIN
            SELECT RAISE(ABORT, 'fallo inyectado');
        END
        """
    )
    connection.commit()

    with pytest.raises(sqlite3.IntegrityError, match="fallo inyectado"):
        repo.save(game)
    connection.close()

    fresh_connection = sqlite3.connect(database_path)
    try:
        fresh_connection.execute("PRAGMA foreign_keys = ON")
        assert _aggregate_snapshot(fresh_connection) == previous_snapshot
    finally:
        fresh_connection.close()
