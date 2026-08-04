"""Pruebas de persistencia y reglas de Game relacionadas con la fase militar."""

import json
import sqlite3
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

import pytest

from machiavelli import database
from machiavelli.events import EventType, TurnEvent
from machiavelli.game.command import Command
from machiavelli.game.game import (
    DuplicatedGameException,
    Game,
    GameNotFoundException,
    Player,
)
from machiavelli.game.map import Map, Province


def test_player_constructor():
    """Test sobre el constructor de Player"""
    player_id = "username"
    discord_id = 10

    game = MagicMock(spec=Game)
    game.database_id = 111

    player = Player(game, player_id)

    assert player.game == game
    assert player.player_id == player_id
    assert player.discord_id is None

    player = Player(game, player_id, discord_id)

    assert player.game == game
    assert player.player_id == player_id
    assert player.discord_id == discord_id


def test_game_constructor():
    """Tests sobre el constructor de la clase"""
    name = "Test name"

    game = Game(name)

    assert game.name == name
    assert game.channel_id is None


def test_military_event_round_trip_preserves_six_lists(tmp_path):
    """Comprueba que el evento militar completo sobrevive al ciclo SQLite."""
    db_path = tmp_path / "game.db"
    database.upgrade(str(db_path))
    event = TurnEvent.military_resolution(
        [[["P1", "A", "rome"], "A", "pisa", False]],
        [["P1", "A", "rome"]],
        [],
        [],
        [["P1", "province", "rome", "subdued"]],
        [],
    )
    with sqlite3.connect(db_path) as conn:
        game = Game("Evento militar")
        game.add_event(event)
        game.save(conn)
        loaded = Game.load_game(conn, game_id=game.database_id)

    record = loaded.turn_events[-1]
    prefix, payload = record.split("|", 1)
    assert prefix == "military_resolution"
    assert json.loads(payload) == event.data


def test_military_event_is_canonical_compact_and_keeps_previous_records():
    """Verifica orden, formato compacto y compatibilidad con eventos previos."""
    event = TurnEvent.military_resolution(
        [
            [["V", "A", "zeta"], "A", "ñ", False],
            [["M", "F", "alfa"], "F", "beta", False],
        ],
        [["V", "A", "zeta"], ["M", "F", "alfa"]],
        [["V", "A", "zeta"]],
        [["M", "F", "alfa"]],
        [["V", "city", "ñ", "liberated"], ["M", "province", "alfa", "subdued"]],
        [
            [["V", "A", "zeta"], "ñ", "started"],
            [["M", "F", "alfa"], "beta", "lifted"],
        ],
    )
    assert event.data["outcomes"][0][0] == ["M", "F", "alfa"]
    assert event.data["cancelled_orders"] == [["M", "F", "alfa"], ["V", "A", "zeta"]]
    assert event.to_record() == (
        'military_resolution|{"broken_convoys":[["V","A","zeta"]],'
        '"cancelled_orders":[["M","F","alfa"],["V","A","zeta"]],'
        '"dislodgements":[["M","F","alfa"]],'
        '"outcomes":[[["M","F","alfa"],"F","beta",false],'
        '[["V","A","zeta"],"A","ñ",false]],'
        '"rebellions":[["M","province","alfa","subdued"],'
        '["V","city","ñ","liberated"]],'
        '"sieges":[[["M","F","alfa"],"beta","lifted"],'
        '[["V","A","zeta"],"ñ","started"]]}'
    )
    assert TurnEvent.expense(EventType.EXPENSE, "M", "A", "a", 1).to_record() == str(
        EventType.EXPENSE
    )


def test_military_event_rejects_non_primitive_or_malformed_lists():
    """Rechaza payloads que no respetan el contrato serializable."""
    malformed_lists = (
        ([[["P", "X", "a"], "A", "b", False]], [], [], [], [], []),
        ([[["P", "A", "a"], "X", "b", False]], [], [], [], [], []),
        ([[["P", "A", "a"], "A", None, False]], [], [], [], [], []),
        ([[["P", "A", "a"], "A", "b", True]], [], [], [], [], []),
        ([], [["P", "X", "a"]], [], [], [], []),
        ([], [], [["P", "A"]], [], [], []),
        ([], [], [], [["P", "A", "a", "extra"]], [], []),
        ([], [], [], [], [["P", "county", "a", "subdued"]], []),
        ([], [], [], [], [["P", "province", "a", "invalid"]], []),
        ([], [], [], [], [], [[["P", "X", "a"], "a", "started"]]),
        ([], [], [], [], [], [[["P", "A", "a"], "a", ["started"]]]),
    )
    for values in malformed_lists:
        with pytest.raises(ValueError):
            TurnEvent.military_resolution(*values)
    for index in range(6):
        values = [[] for _ in range(6)]
        values[index] = ()
        with pytest.raises(ValueError):
            TurnEvent.military_resolution(*values)


def test_rebelled_city_recruitment_is_rejected_before_charging():
    """Impide reclutar en ciudad rebelada sin descontar el coste."""
    game_map = Map(
        provinces={
            "fort": Province("Fort", custom_id="fort", city="fortified", has_port=True)
        },
        seas={},
    )
    scenario = SimpleNamespace(
        year=1454,
        province_home_country=lambda _province: "M",
    )

    def build_game(rebelled_cities):
        """Crea el mismo mantenimiento con o sin rebelión urbana."""
        game = Game(
            "Mantenimiento",
            turn_number=1,
            scenario=scenario,
            map=game_map,
        )
        player = Player(
            game,
            "P1",
            controlled_locations=["fort"],
            ducats=3,
            rebelled_cities=list(rebelled_cities),
            home_countries=["M"],
            power="M",
        )
        player.commands = [Command(game, player, "G fort", "R", None)]
        game.players = [player]
        return game, player

    rebelled_game, rebelled_player = build_game(["fort"])
    rebelled_game.spring_maintenance()
    assert rebelled_player.garrisons == []
    assert rebelled_player.ducats == 3

    normal_game, normal_player = build_game([])
    normal_game.spring_maintenance()
    assert normal_player.garrisons == ["fort"]
    assert normal_player.ducats == 0


# Tests on database functions


def test_load_commands_orders_by_persisted_id():
    """Exige que las filas de orden se carguen por su identificador persistido."""
    mock_conn = MagicMock(spec=sqlite3.Connection)
    mock_cursor = MagicMock(spec=sqlite3.Cursor)
    mock_conn.cursor.return_value = mock_cursor
    mock_cursor.fetchall.return_value = []

    game = MagicMock(spec=Game)
    game.database_id = 42
    player = MagicMock(spec=Player)
    player.player_id = "P1"

    assert Command.load_commands(mock_conn, game, player) == []
    mock_cursor.execute.assert_called_once_with(
        "SELECT actor, command, target FROM commands "
        "WHERE game_id = ? AND player_id = ? ORDER BY commands.id ASC",
        (42, "P1"),
    )


def test_command_order_survives_repeated_loads_and_save_round_trip():
    """Conserva el orden relativo de un convoy tras cargas y guardados sucesivos."""

    def command_rows(game: Game) -> dict[str, tuple[tuple[str, str, str | None], ...]]:
        """Extrae las órdenes en la secuencia observada por cada jugador."""
        return {
            player.player_id: tuple(
                (command.actor, command.command, command.target)
                for command in player.commands
            )
            for player in game.players
        }

    expected = {
        "P1": (
            ("A rome", "A", "tyrrh"),
            ("A rome", "A", "westm"),
            ("A rome", "A", "pisa"),
        ),
        "P2": (
            ("A venic", "A", "ferrar"),
            ("A venic", "H", None),
        ),
    }

    assert database._SCHEMA_VERSION == 3
    assert len(database._UPGRADES) == 3

    with TemporaryDirectory() as directory:
        db_path = Path(directory) / "commands.db"
        database.upgrade(str(db_path))

        with closing(sqlite3.connect(db_path)) as conn:
            game = Game("Orden persistido")
            game.players = [Player(game, "P1"), Player(game, "P2")]
            game.save(conn)
            conn.executemany(
                "INSERT INTO commands "
                "(game_id, player_id, actor, command, target) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    (game.database_id, "P1", "A rome", "A", "tyrrh"),
                    (game.database_id, "P2", "A venic", "A", "ferrar"),
                    (game.database_id, "P1", "A rome", "A", "westm"),
                    (game.database_id, "P2", "A venic", "H", None),
                    (game.database_id, "P1", "A rome", "A", "pisa"),
                ),
            )
            conn.commit()

            first_load = Game.load_game(conn, game_id=game.database_id)
            second_load = Game.load_game(conn, game_id=game.database_id)
            assert command_rows(first_load) == expected
            assert command_rows(second_load) == expected

            first_load.save(conn)
            conn.commit()
            after_first_save = Game.load_game(conn, game_id=game.database_id)
            assert command_rows(after_first_save) == expected

            after_first_save.save(conn)
            conn.commit()
            after_second_save = Game.load_game(conn, game_id=game.database_id)
            assert command_rows(after_second_save) == expected
            assert conn.execute("PRAGMA user_version").fetchone() == (3,)


# database on Player
def test_load_players_success():
    """Comprueba la consulta y las instancias devueltas por load_players."""
    mock_conn = MagicMock(spec=sqlite3.Connection)
    mock_cursor = MagicMock(spec=sqlite3.Cursor)
    mock_conn.cursor.return_value = mock_cursor

    mock_game = MagicMock(spec=Game)
    mock_game.database_id = 42

    mock_cursor.fetchall.return_value = [
        (
            "carlos_id",
            1111,
            '["rome", "bari"]',
            '["veron", "messi"]',
            '["berga", "bolog"]',
            '["venic", "bosni"]',
            '["V", "L"]',
            8,
            '["flore"]',
            '["pisa"]',
            '["M"]',
            "M",
        ),
        ("sofia_id", None, None, None, None, None, None, 0, None, None, None, None),
    ]

    players = Player.load_players(mock_conn, mock_game)

    mock_cursor.execute.assert_has_calls(
        [
            call(
                """
            SELECT player_id, discord_id, controlled_locations, armies, fleets,
                garrisons, ass_counters, ducats, rebelled_provinces,
                rebelled_cities, home_countries, power
            FROM players WHERE game_id = ?
            """,
                (42,),
            ),
            call(
                "SELECT actor, command, target FROM commands "
                "WHERE game_id = ? AND player_id = ? ORDER BY commands.id ASC",
                (42, "carlos_id"),
            ),
            call(
                "SELECT actor, command, target FROM commands "
                "WHERE game_id = ? AND player_id = ? ORDER BY commands.id ASC",
                (42, "sofia_id"),
            ),
        ]
    )

    assert len(players) == 2
    assert isinstance(players[0], Player)
    assert players[0].player_id == "carlos_id"
    assert players[0].discord_id == 1111
    assert len(players[0].controlled_locations) == 2
    assert len(players[0].armies) == 2
    assert len(players[0].fleets) == 2
    assert len(players[0].garrisons) == 2
    assert len(players[0].ass_counters) == 2
    assert len(players[0].rebelled_provinces) == 1
    assert len(players[0].rebelled_cities) == 1
    assert len(players[0].home_countries) == 1
    assert "rome" in players[0].controlled_locations
    assert "messi" in players[0].armies
    assert "berga" in players[0].fleets
    assert "bosni" in players[0].garrisons
    assert "V" in players[0].ass_counters
    assert players[0].ducats == 8
    assert "flore" in players[0].rebelled_provinces
    assert "pisa" in players[0].rebelled_cities
    assert "M" in players[0].home_countries
    assert players[0].power == "M"

    assert isinstance(players[1], Player)
    assert players[1].player_id == "sofia_id"
    assert players[1].discord_id is None
    assert len(players[1].controlled_locations) == 0
    assert len(players[1].armies) == 0
    assert len(players[1].fleets) == 0
    assert len(players[1].garrisons) == 0
    assert len(players[1].ass_counters) == 0
    assert len(players[1].rebelled_provinces) == 0
    assert len(players[1].rebelled_cities) == 0
    assert len(players[1].home_countries) == 0
    assert players[1].ducats == 0
    assert players[1].power is None


# database on Game
def test_create_game_success():
    """Comprueba que create_game inserta la partida correctamente en la BBDD
    y devuelve la instancia de Game con su id de base de datos asignado.
    """
    mock_conn = MagicMock(spec=sqlite3.Connection)
    mock_cursor = MagicMock(spec=sqlite3.Cursor)

    mock_conn.cursor.return_value = mock_cursor
    mock_cursor.lastrowid = 42

    name = "Guerra de Familias"
    channel_id = 123456789

    game = Game.create_game(name=name, channel_id=channel_id, conn=mock_conn)

    mock_conn.cursor.assert_called_once()
    mock_cursor.execute.assert_called_once_with(
        "INSERT INTO games (name, channel_id) VALUES (?, ?)", (name, channel_id)
    )

    assert isinstance(game, Game)
    assert game.name == name
    assert game.channel_id == channel_id
    assert game.database_id == 42


def test_create_game_raises_duplicated_exception():
    """Comprueba que si la base de datos lanza un IntegrityError (por nombre
    o canal duplicado), el método lo captura y lanza DuplicatedGameException.
    """
    mock_conn = MagicMock(spec=sqlite3.Connection)
    mock_cursor = MagicMock(spec=sqlite3.Cursor)
    mock_conn.cursor.return_value = mock_cursor

    mock_cursor.execute.side_effect = sqlite3.IntegrityError("UNIQUE constraint failed")

    name = "Partida Repetida"
    channel_id = 999999

    with pytest.raises(DuplicatedGameException) as exc_info:
        Game.create_game(name=name, channel_id=channel_id, conn=mock_conn)

    assert name in str(exc_info.value)
    assert str(channel_id) in str(exc_info.value)

    mock_cursor.execute.assert_called_once_with(
        "INSERT INTO games (name, channel_id) VALUES (?, ?)", (name, channel_id)
    )


def test_load_game_success():
    """Comprueba que load_game recupera los datos de la partida de la BBDD"""

    mock_conn = MagicMock(spec=sqlite3.Connection)
    mock_cursor = MagicMock(spec=sqlite3.Cursor)
    mock_conn.cursor.return_value = mock_cursor

    mock_cursor.fetchone.return_value = (
        7,
        "Campaña de Milán",
        987654,
        None,
        0,
        None,
        None,
        '["venic", "bari"]',
        '["rome", "parma"]',
        '["turin"]',
    )

    with patch.object(Player, "load_players") as mock_load_players:
        mock_load_players.side_effect = lambda conn, game: [
            Player(game, player_id="fake_carlos", discord_id=111),
            Player(game, player_id="fake_sofia", discord_id=222),
        ]

        game = Game.load_game(mock_conn, game_id=7)

        assert isinstance(game, Game)
        assert game.database_id == 7
        assert game.name == "Campaña de Milán"
        assert game.channel_id == 987654
        assert len(game.players) == 2
        assert game.players[0].player_id == "fake_carlos"
        assert game.players[1].discord_id == 222
        assert "venic" in game.famine
        assert "parma" in game.independent_garrisons
        assert "turin" in game.besieges

        mock_cursor.execute.assert_has_calls(
            [
                call(
                    "SELECT id, name, channel_id, scenario_id, turn_number, "
                    "weekly_deadline, next_deadline, famine, independent_garrisons, "
                    "besieges FROM games WHERE id = ?",
                    (7,),
                ),
                call(
                    "SELECT message FROM game_events WHERE game_id = ? ORDER BY id ASC",
                    (7,),
                ),
            ]
        )

        mock_load_players.assert_called_once_with(mock_conn, game)


def test_load_game_raises_not_found_and_never_loads_players():
    """No carga jugadores cuando la partida solicitada no existe."""
    mock_conn = MagicMock(spec=sqlite3.Connection)
    mock_cursor = MagicMock(spec=sqlite3.Cursor)
    mock_conn.cursor.return_value = mock_cursor
    mock_cursor.fetchone.return_value = None

    with patch.object(Player, "load_players") as mock_load_players:
        with pytest.raises(GameNotFoundException):
            Game.load_game(mock_conn, name="Inexistente")

        mock_load_players.assert_not_called()


def test_game_save_inserts_new_game():
    """Comprueba que si database_id es None, save() hace un INSERT."""
    mock_conn = MagicMock(spec=sqlite3.Connection)
    mock_cursor = MagicMock(spec=sqlite3.Cursor)
    mock_conn.cursor.return_value = mock_cursor
    mock_cursor.lastrowid = 99

    # Partida sin ID (Nueva)
    game = Game(name="Nueva Partida", channel_id=111)

    game.save(mock_conn)

    # Verificamos que llamó al INSERT
    mock_cursor.execute.assert_any_call(
        "INSERT INTO games "
        "(name, channel_id, scenario_id, turn_number, weekly_deadline, "
        "next_deadline, famine, independent_garrisons, besieges) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("Nueva Partida", 111, None, 0, None, None, "[]", "[]", "[]"),
    )
    # Verificamos que el objeto actualizó su ID en memoria
    assert game.database_id == 99


def test_game_save_updates_existing_game():
    """Comprueba que si database_id ya existe, save() hace un UPDATE."""
    mock_conn = MagicMock(spec=sqlite3.Connection)
    mock_cursor = MagicMock(spec=sqlite3.Cursor)
    mock_conn.cursor.return_value = mock_cursor

    # Partida que YA existe en la BBDD (tiene ID 42)
    game = Game(name="Partida Vieja", channel_id=222, database_id=42)

    # Modificamos un dato en memoria (ej. el nombre)
    game.name = "Partida Renombrada"

    game.save(mock_conn)

    # Verificamos que ejecutó el UPDATE usando el ID como filtro
    mock_cursor.execute.assert_any_call(
        "UPDATE games SET name = ?, channel_id = ?, scenario_id = ?, "
        "turn_number = ?, weekly_deadline = ?, next_deadline = ?, famine = ?, "
        "independent_garrisons = ?, besieges = ? WHERE id = ?",
        ("Partida Renombrada", 222, None, 0, None, None, "[]", "[]", "[]", 42),
    )
    # El ID no debe haber cambiado
    assert game.database_id == 42
