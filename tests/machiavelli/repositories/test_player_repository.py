# tests/machiavelli/repositories/test_player_repository.py

import sqlite3
from unittest.mock import MagicMock

import pytest

from machiavelli.game.player import Player
from machiavelli.repositories.player_repository import PlayerRepository


@pytest.fixture
def db_connection():
    """Crea una base de datos SQLite en memoria con el esquema básico de tablas."""
    conn = sqlite3.connect(":memory:")
    cursor = conn.cursor()

    # Esquema mínimo para probar Player y Commands
    cursor.execute("""
        CREATE TABLE players (
            game_id INTEGER,
            player_id TEXT,
            discord_id INTEGER,
            controlled_locations TEXT,
            armies TEXT,
            fleets TEXT,
            garrisons TEXT,
            ass_counters TEXT,
            ducats INTEGER,
            rebelled_provinces TEXT,
            rebelled_cities TEXT,
            home_countries TEXT,
            power TEXT,
            PRIMARY KEY (game_id, player_id)
        )
    """)
    cursor.execute("""
        CREATE TABLE commands (
            game_id INTEGER,
            player_id TEXT,
            command_data TEXT
        )
    """)
    conn.commit()
    yield conn
    conn.close()


@pytest.fixture
def mock_game():
    game = MagicMock()
    game.database_id = 100
    return game


@pytest.fixture
def mock_command_repo():
    """Mock de CommandRepository para aislar los tests del repositorio de jugadores."""
    mock_repo = MagicMock()
    mock_repo.get_by_player.return_value = []
    return mock_repo


def test_save_and_get_player(db_connection, mock_game, mock_command_repo):
    """Prueba que un jugador se guarda en BBDD y se recupera con los mismos datos."""
    repo = PlayerRepository(db_connection)
    repo.command_repo = mock_command_repo

    player_original = Player(
        game=mock_game,
        player_id="p1",
        discord_id=987654321,
        controlled_locations=["paler", "messi"],
        armies=["messi"],
        ducats=15,
        power="N",
    )

    # Guardar
    repo.save(player_original)

    # Recuperar
    loaded_players = repo.get_by_game(mock_game)

    assert len(loaded_players) == 1
    p_loaded = loaded_players[0]

    assert p_loaded.player_id == "p1"
    assert p_loaded.discord_id == 987654321
    assert p_loaded.controlled_locations == ["paler", "messi"]
    assert p_loaded.armies == ["messi"]
    assert p_loaded.ducats == 15
    assert p_loaded.power == "N"


def test_update_existing_player_upsert(db_connection, mock_game, mock_command_repo):
    """Verifica que ON CONFLICT actualice el registro existente sin duplicarlo."""
    repo = PlayerRepository(db_connection)
    repo.command_repo = mock_command_repo

    player = Player(game=mock_game, player_id="p1", ducats=10)
    repo.save(player)

    # Modificar estado en memoria
    player.ducats = 25
    player.armies.append("naple")
    repo.save(player)

    loaded_players = repo.get_by_game(mock_game)
    assert len(loaded_players) == 1
    assert loaded_players[0].ducats == 25
    assert loaded_players[0].armies == ["naple"]


def test_save_commands_transaction_cleanup(db_connection, mock_game, mock_command_repo):
    """Verifica que al guardar comandos se limpian primero las órdenes anteriores."""
    repo = PlayerRepository(db_connection)
    repo.command_repo = mock_command_repo

    cursor = db_connection.cursor()
    # Insertar un comando basura previo
    cursor.execute(
        "INSERT INTO commands (game_id, player_id, command_data) VALUES (?, ?, ?)",
        (100, "p1", "OLD_COMMAND"),
    )
    db_connection.commit()

    player = Player(game=mock_game, player_id="p1")
    repo.save_commands(player)

    # Debe haber borrado la orden anterior
    cursor.execute("SELECT * FROM commands WHERE game_id = 100 AND player_id = 'p1'")
    assert len(cursor.fetchall()) == 0
