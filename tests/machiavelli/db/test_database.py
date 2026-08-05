import sqlite3
from pathlib import Path
from typing import cast

import pytest

from machiavelli.db import database as database_module
from machiavelli.db.database import (
    _SCHEMA_VERSION,
    _UPGRADES,
    DatabaseManager,
    upgrade,
    upgrade_connection,
)


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
    # Crear manualmente una BBDD antigua completa (versión 1)
    conn = sqlite3.connect(db_path)
    conn.executescript(_UPGRADES[0])
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


def test_upgrade_connection_migrates_version_two(db_path: Path) -> None:
    """Una base en versión 2 recibe únicamente la tabla de comandos."""
    conn = sqlite3.connect(db_path)
    try:
        for script in _UPGRADES[:2]:
            conn.executescript(script)
        conn.execute("PRAGMA user_version = 2;")
        conn.commit()

        upgrade_connection(conn)

        assert conn.execute("PRAGMA user_version;").fetchone()[0] == _SCHEMA_VERSION
        assert conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='commands';"
        ).fetchone() == ("commands",)
    finally:
        conn.close()


def test_upgrade_connection_does_not_close_caller_connection(db_path: Path) -> None:
    """La función canónica no toma propiedad de la conexión recibida."""
    conn = sqlite3.connect(db_path)
    try:
        upgrade_connection(conn)
        assert conn.execute("SELECT 1;").fetchone() == (1,)
    finally:
        conn.close()


@pytest.mark.parametrize("source_version", [1, 2, 3])
def test_upgrade_preserves_domain_rows_and_restarts_events(
    db_path: Path, source_version: int
) -> None:
    """v4 conserva el agregado persistente y reinicia solo los eventos efímeros."""
    conn = sqlite3.connect(db_path)
    try:
        for script in _UPGRADES[:source_version]:
            conn.executescript(script)
        conn.execute(f"PRAGMA user_version = {source_version};")
        conn.execute(
            "INSERT INTO games "
            "(name, channel_id, scenario_id, turn_number, famine, "
            "independent_garrisons) VALUES (?, ?, ?, ?, ?, ?)",
            ("Histórica", 123, "Be", 7, '["milan"]', '["pisa"]'),
        )
        game_id = conn.execute(
            "SELECT id FROM games WHERE name = ?", ("Histórica",)
        ).fetchone()[0]
        conn.execute(
            "INSERT INTO players "
            "(game_id, player_id, discord_id, controlled_locations, armies, "
            "fleets, garrisons, ass_counters, ducats, rebelled_provinces, "
            "rebelled_cities, home_countries, power) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                game_id,
                "Florencia",
                456,
                '["florence"]',
                '["florence"]',
                "[]",
                "[]",
                "[]",
                12,
                "[]",
                "[]",
                '["Florencia"]',
                "Florencia",
            ),
        )
        conn.execute(
            "INSERT INTO game_events (game_id, message) VALUES (?, ?)",
            (game_id, "Evento histórico"),
        )
        if source_version == 3:
            conn.execute(
                "INSERT INTO commands "
                "(game_id, player_id, actor, command, target) "
                "VALUES (?, ?, ?, ?, ?)",
                (game_id, "Florencia", "A florence", "H", None),
            )
        conn.commit()

        upgrade_connection(conn)

        assert conn.execute("PRAGMA user_version;").fetchone()[0] == _SCHEMA_VERSION
        assert conn.execute(
            "SELECT name, channel_id, turn_number FROM games WHERE id = ?",
            (game_id,),
        ).fetchone() == ("Histórica", 123, 7)
        assert conn.execute(
            "SELECT player_id, discord_id, ducats FROM players WHERE game_id = ?",
            (game_id,),
        ).fetchone() == ("Florencia", 456, 12)
        assert [row[1] for row in conn.execute("PRAGMA table_info(game_events)")] == [
            "id",
            "game_id",
            "event_type",
            "data_json",
        ]
        assert conn.execute(
            "SELECT COUNT(*) FROM game_events WHERE game_id = ?", (game_id,)
        ).fetchone() == (0,)
        if source_version == 3:
            assert conn.execute(
                "SELECT actor, command, target FROM commands WHERE game_id = ?",
                (game_id,),
            ).fetchone() == ("A florence", "H", None)
    finally:
        conn.close()


def test_database_manager_and_upgrade_create_equivalent_schemas(
    tmp_path: Path,
) -> None:
    """Las dos entradas públicas producen el mismo esquema y versión."""
    upgrade_path = tmp_path / "upgrade.db"
    manager_path = tmp_path / "manager.db"

    upgrade(upgrade_path)
    DatabaseManager(manager_path).init_db()

    def schema_snapshot(path: Path) -> tuple[int, tuple[tuple[str, str | None], ...]]:
        conn = sqlite3.connect(path)
        try:
            version = conn.execute("PRAGMA user_version;").fetchone()[0]
            rows = conn.execute(
                "SELECT name, sql FROM sqlite_master "
                "WHERE type='table' AND name != 'sqlite_sequence' ORDER BY name;"
            ).fetchall()
            return version, tuple(rows)
        finally:
            conn.close()

    assert schema_snapshot(upgrade_path) == schema_snapshot(manager_path)


def test_database_manager_delegates_to_upgrade_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """DatabaseManager no mantiene un segundo bucle de migración."""

    class FakeConnection:
        def __init__(self) -> None:
            self.closed = False

        def close(self) -> None:
            self.closed = True

    connection = FakeConnection()
    manager = DatabaseManager("ignored.db")
    calls: list[FakeConnection] = []
    monkeypatch.setattr(manager, "get_connection", lambda: connection)
    monkeypatch.setattr(
        database_module,
        "upgrade_connection",
        lambda conn: calls.append(conn),
    )

    manager.init_db()

    assert calls == [connection]
    assert connection.closed


def _create_v3_database(path: Path) -> tuple[int, tuple[object, ...]]:
    """Create a representative v3 database and return its stable row snapshot."""
    conn = sqlite3.connect(path)
    try:
        for script in _UPGRADES[:3]:
            conn.executescript(script)
        conn.execute("PRAGMA user_version = 3;")
        conn.execute(
            "INSERT INTO games (name, channel_id, famine, independent_garrisons, "
            "besieges) VALUES (?, ?, ?, ?, ?)",
            ("v3", 777, "[]", "[]", "[]"),
        )
        game_id = conn.execute(
            "SELECT id FROM games WHERE name = ?", ("v3",)
        ).fetchone()[0]
        conn.execute(
            "INSERT INTO players (game_id, player_id, controlled_locations, armies, "
            "fleets, garrisons, ass_counters, ducats, rebelled_provinces, "
            "rebelled_cities, home_countries) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (game_id, "P1", "[]", "[]", "[]", "[]", "[]", 5, "[]", "[]", "[]"),
        )
        conn.execute(
            "INSERT INTO commands (game_id, player_id, actor, command, target) "
            "VALUES (?, ?, ?, ?, ?)",
            (game_id, "P1", "A flore", "H", None),
        )
        conn.execute(
            "INSERT INTO game_events (game_id, message) VALUES (?, ?)",
            (game_id, "histórico"),
        )
        conn.commit()
        snapshot = (
            conn.execute("SELECT name, channel_id FROM games").fetchone(),
            conn.execute("SELECT player_id, ducats FROM players").fetchone(),
            conn.execute("SELECT actor, command, target FROM commands").fetchone(),
            conn.execute("SELECT message FROM game_events").fetchone(),
        )
        return game_id, snapshot
    finally:
        conn.close()


def test_schema_v4_creates_structured_event_columns(repo: DatabaseManager) -> None:
    repo.init_db()
    conn = repo.get_connection()
    try:
        columns = [
            row["name"] for row in conn.execute("PRAGMA table_info(game_events)")
        ]
        assert _SCHEMA_VERSION == 4
        assert columns == ["id", "game_id", "event_type", "data_json"]
    finally:
        conn.close()


def test_upgrade_v3_to_v4_restarts_only_event_history(db_path: Path) -> None:
    game_id, snapshot = _create_v3_database(db_path)

    conn = sqlite3.connect(db_path)
    try:
        upgrade_connection(conn)
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 4
        assert [row[1] for row in conn.execute("PRAGMA table_info(game_events)")] == [
            "id",
            "game_id",
            "event_type",
            "data_json",
        ]
        assert conn.execute("SELECT COUNT(*) FROM game_events").fetchone()[0] == 0
        assert (
            conn.execute(
                "SELECT name, channel_id FROM games WHERE id = ?", (game_id,)
            ).fetchone()
            == snapshot[0]
        )
        assert (
            conn.execute(
                "SELECT player_id, ducats FROM players WHERE game_id = ?", (game_id,)
            ).fetchone()
            == snapshot[1]
        )
        assert (
            conn.execute(
                "SELECT actor, command, target FROM commands WHERE game_id = ?",
                (game_id,),
            ).fetchone()
            == snapshot[2]
        )
    finally:
        conn.close()


class _FailingV4Cursor(sqlite3.Cursor):
    """Raise after a selected v4 statement has executed."""

    def execute(self, sql: str, parameters=()):  # type: ignore[no-untyped-def]
        result = super().execute(sql, parameters)
        marker = cast("_FailingV4Connection", self.connection).failure_marker
        normalized = " ".join(sql.upper().split())
        if marker in normalized:
            raise sqlite3.OperationalError(f"fallo inyectado tras {marker}")
        return result


class _FailingV4Connection(sqlite3.Connection):
    failure_marker: str

    def cursor(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        kwargs["factory"] = _FailingV4Cursor
        return super().cursor(*args, **kwargs)


@pytest.mark.parametrize(
    "failure_marker",
    [
        "DROP TABLE GAME_EVENTS",
        "CREATE TABLE GAME_EVENTS",
        "PRAGMA USER_VERSION = 4",
    ],
)
def test_v4_migration_rolls_back_schema_rows_and_version(
    db_path: Path, failure_marker: str
) -> None:
    _, snapshot = _create_v3_database(db_path)
    conn = sqlite3.connect(db_path, factory=_FailingV4Connection)
    conn.failure_marker = failure_marker
    try:
        with pytest.raises(sqlite3.OperationalError, match="fallo inyectado"):
            upgrade_connection(conn)
    finally:
        conn.close()

    verification = sqlite3.connect(db_path)
    try:
        assert verification.execute("PRAGMA user_version").fetchone()[0] == 3
        assert [
            row[1] for row in verification.execute("PRAGMA table_info(game_events)")
        ] == ["id", "game_id", "message"]
        assert (
            verification.execute("SELECT message FROM game_events").fetchone()
            == snapshot[3]
        )
        assert (
            verification.execute("SELECT name, channel_id FROM games").fetchone()
            == snapshot[0]
        )
        assert (
            verification.execute("SELECT player_id, ducats FROM players").fetchone()
            == snapshot[1]
        )
        assert (
            verification.execute(
                "SELECT actor, command, target FROM commands"
            ).fetchone()
            == snapshot[2]
        )
    finally:
        verification.close()
