import sqlite3
from pathlib import Path

import pytest

from machiavelli.db.database import _SCHEMA_VERSION, DatabaseManager


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    """Proporciona una ruta válida para una BBDD temporal."""
    return tmp_path / "test_machiavelli.db"


@pytest.fixture
def repo(db_path: Path) -> DatabaseManager:
    """Instancia de GameRepository lista para usar."""
    return DatabaseManager(db_path)


def test_init(tmp_path: Path) -> None:
    """Verifica que el constructor acepte tanto cadenas como objetos Path."""
    str_path = str(tmp_path / "str_db.db")
    path_obj = tmp_path / "path_db.db"

    repo_str = DatabaseManager(str_path)
    repo_path = DatabaseManager(path_obj)

    assert repo_str.db_path == Path(str_path)
    assert repo_path.db_path == path_obj


def test_get_connection_creates_parent_directories(tmp_path: Path) -> None:
    """Debe crear los directorios padres si no existen al intentar conectar."""
    deep_path = tmp_path / "nested" / "subfolder" / "game.db"
    repo = DatabaseManager(deep_path)

    assert not deep_path.parent.exists()

    conn = repo.get_connection()
    conn.close()

    assert deep_path.parent.exists()


def test_get_connection_configures_pragmas_and_row_factory(
    repo: DatabaseManager,
) -> None:
    """Verifica que la conexión configure el row_factory y los PRAGMAs requeridos."""
    conn = repo.get_connection()

    # 1. Row factory
    assert conn.row_factory == sqlite3.Row

    # 2. Foreign keys activadas
    cursor = conn.cursor()
    fk_status = cursor.execute("PRAGMA foreign_keys;").fetchone()[0]
    assert fk_status == 1

    # 3. Journal mode en WAL
    journal_mode = cursor.execute("PRAGMA journal_mode;").fetchone()[0]
    assert journal_mode.lower() == "wal"

    conn.close()


def test_get_connection_foreign_keys_are_enforced(repo: DatabaseManager) -> None:
    """Garantiza que la BBDD realmente rechace violaciones de clave foránea."""
    repo.init_db()

    conn = repo.get_connection()
    cursor = conn.cursor()

    # Intentar insertar un jugador asignado a un game_id inexistente (999)
    with pytest.raises(sqlite3.IntegrityError):
        cursor.execute(
            "INSERT INTO players (game_id, player_id, discord_id) VALUES (?, ?, ?)",
            (999, "FRANCE", 123456789),
        )
    conn.close()


def test_init_db_creates_schema_from_scratch(repo: DatabaseManager) -> None:
    """Crea la base de datos desde cero hasta la última versión del esquema."""
    repo.init_db()

    conn = repo.get_connection()
    cursor = conn.cursor()

    # 1. Comprobar que el PRAGMA user_version es el objetivo
    version = cursor.execute("PRAGMA user_version;").fetchone()[0]
    assert version == _SCHEMA_VERSION

    # 2. Comprobar existencia de tablas principales
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = {row["name"] for row in cursor.fetchall()}

    expected_tables = {"games", "players", "game_events", "commands"}
    assert expected_tables.issubset(tables)

    # 3. Comprobar que la columna agregada en la migración 2 (besieges) existe
    cursor.execute("PRAGMA table_info(games);")
    columns = {row["name"] for row in cursor.fetchall()}
    assert "besieges" in columns

    conn.close()


def test_init_db_is_idempotent(repo: DatabaseManager) -> None:
    """Ejecutar init_db múltiples veces en una BBDD no falla ni altera la versión."""
    repo.init_db()
    repo.init_db()  # Segunda llamada debe ser un no-op

    conn = repo.get_connection()
    version = conn.execute("PRAGMA user_version;").fetchone()[0]
    conn.close()

    assert version == _SCHEMA_VERSION


def test_init_db_incremental_migration(db_path: Path) -> None:
    """Prueba que una BBDD en versión 1 se actualice correctamente."""
    # Crear manualmente una BBDD antigua (versión 1)
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE games (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            channel_id INTEGER UNIQUE,
            scenario_id TEXT,
            turn_number INTEGER DEFAULT 0,
            weekly_deadline TEXT,
            next_deadline TEXT,
            famine TEXT,
            independent_garrisons TEXT
        );
        """
    )
    conn.execute("PRAGMA user_version = 1;")
    conn.commit()
    conn.close()

    # Ejecutar init_db a través del repositorio
    repo = DatabaseManager(db_path)
    repo.init_db()

    # Verificar que saltó de v1 a v3
    conn = repo.get_connection()
    version = conn.execute("PRAGMA user_version;").fetchone()[0]

    # Comprobar que la tabla `commands` (añadida en v3) existe ahora
    cursor = conn.cursor()
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='commands';"
    )
    command_table = cursor.fetchone()

    conn.close()

    assert version == _SCHEMA_VERSION
    assert command_table is not None


def test_init_db_rolls_back_on_migration_failure(
    repo: DatabaseManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Si script de migración falla, debe hacer rollback y no avanzar user_version."""
    import machiavelli.db.database as repo_module

    # Inyectar una migración corrupta en la versión 1
    bad_upgrades = ("CREATE TABLE games (id INTEGER);", "SINTAXIS_SQL_INVALIDA;")
    monkeypatch.setattr(repo_module, "_UPGRADES", bad_upgrades)
    monkeypatch.setattr(repo_module, "_SCHEMA_VERSION", 2)

    with pytest.raises(sqlite3.OperationalError):
        repo.init_db()

    # La primera migración debió aplicarse (v1), pero la v2 debió fallar y mantener v1
    conn = repo.get_connection()
    version = conn.execute("PRAGMA user_version;").fetchone()[0]
    conn.close()

    assert version == 1
