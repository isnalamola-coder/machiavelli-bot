# tests/machiavelli/repositories/test_command_repository.py
import sqlite3

import pytest

from machiavelli.db.database import _UPGRADES, DatabaseManager
from machiavelli.game.command import Command
from machiavelli.repositories.command_repository import CommandRepository

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db_conn():
    """Crea una base de datos SQLite en memoria con las migraciones aplicadas

    sobre la misma conexión activa.
    """
    db_manager = DatabaseManager(":memory:")
    conn = db_manager.get_connection()

    # Aplicamos todas las migraciones en la conexión activa
    cursor = conn.cursor()
    for version, script in enumerate(_UPGRADES, start=1):
        cursor.executescript(script)
        cursor.execute(f"PRAGMA user_version = {version};")
    conn.commit()

    yield conn
    conn.close()


@pytest.fixture
def repo(db_conn: sqlite3.Connection):
    """Instancia del repositorio para cada test."""
    return CommandRepository(db_conn)


@pytest.fixture
def setup_game_and_players(db_conn: sqlite3.Connection):
    """Inserta registros ficticios en 'games' y 'players' para respetar Foreign Keys."""
    cursor = db_conn.cursor()

    # Insertar partida de prueba (id = 1)
    cursor.execute(
        "INSERT INTO games (id, name, channel_id) VALUES (?, ?, ?)",
        (1, "Partida Test", 1001),
    )

    # Insertar jugadores de prueba
    cursor.execute(
        "INSERT INTO players (game_id, player_id, discord_id) VALUES (?, ?, ?)",
        (1, "p1", 2001),
    )
    cursor.execute(
        "INSERT INTO players (game_id, player_id, discord_id) VALUES (?, ?, ?)",
        (1, "p2", 2002),
    )

    db_conn.commit()


# ---------------------------------------------------------------------------
# Tests: Operaciones CRUD
# ---------------------------------------------------------------------------


def test_save_and_get_by_player(repo: CommandRepository, setup_game_and_players):
    """Verifica que un comando guardado individualmente se recupera correctamente."""
    cmd = Command(
        game_id=1,
        player_id="p1",
        actor="A milan",
        command="A",
        target="venic",
    )

    repo.save(cmd)
    retrieved = repo.get_by_player(game_id=1, player_id="p1")

    assert len(retrieved) == 1
    assert retrieved[0].game_id == 1
    assert retrieved[0].player_id == "p1"
    assert retrieved[0].actor == "A milan"
    assert retrieved[0].command == "A"
    assert retrieved[0].target == "venic"


def test_save_many(repo: CommandRepository, setup_game_and_players):
    """Verifica que se pueden guardar múltiples órdenes en lote."""
    commands = [
        Command(
            game_id=1, player_id="p1", actor="A milan", command="A", target="venic"
        ),
        Command(game_id=1, player_id="p1", actor="F UA", command="H", target=""),
        Command(game_id=1, player_id="p1", actor="E B", command="12", target="flore"),
    ]

    repo.save_many(commands)
    retrieved = repo.get_by_player(game_id=1, player_id="p1")

    assert len(retrieved) == 3
    assert [c.actor for c in retrieved] == ["A milan", "F UA", "E B"]


def test_get_by_player_isolation(repo: CommandRepository, setup_game_and_players):
    """Verifica que recuperar comandos de un jugador no devuelve los de otros."""
    cmd_p1 = Command(
        game_id=1, player_id="p1", actor="A milan", command="A", target="venic"
    )
    cmd_p2 = Command(game_id=1, player_id="p2", actor="F UA", command="H", target="")

    repo.save_many([cmd_p1, cmd_p2])

    p1_orders = repo.get_by_player(game_id=1, player_id="p1")
    p2_orders = repo.get_by_player(game_id=1, player_id="p2")

    assert len(p1_orders) == 1
    assert p1_orders[0].actor == "A milan"

    assert len(p2_orders) == 1
    assert p2_orders[0].actor == "F UA"


def test_delete_by_player(repo: CommandRepository, setup_game_and_players):
    """Verifica que borra las órdenes de un jugador sin borrar las de otros."""
    cmd_p1 = Command(
        game_id=1, player_id="p1", actor="A milan", command="A", target="venic"
    )
    cmd_p2 = Command(game_id=1, player_id="p2", actor="F UA", command="H", target="")

    repo.save_many([cmd_p1, cmd_p2])

    # Borramos únicamente las órdenes de p1
    repo.delete_by_player(game_id=1, player_id="p1")

    assert len(repo.get_by_player(game_id=1, player_id="p1")) == 0
    assert len(repo.get_by_player(game_id=1, player_id="p2")) == 1


def test_foreign_key_constraint(repo: CommandRepository):
    """Sin ejecutar setup_game_and_players, guardar un comando falla por la FK."""
    cmd = Command(
        game_id=999,  # No existe en 'games'
        player_id="non_existent",  # No existe en 'players'
        actor="A milan",
        command="A",
        target="venic",
    )

    with pytest.raises(sqlite3.IntegrityError):
        repo.save(cmd)
