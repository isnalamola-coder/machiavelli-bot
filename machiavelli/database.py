# machiavelli/database.py
import logging
import sqlite3

_SCHEMA_VERSION = 3

_UPGRADES = (
    # SCHEMA 1
    """\
    CREATE TABLE IF NOT EXISTS games (
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

    CREATE TABLE IF NOT EXISTS players (
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
        PRIMARY KEY (game_id, player_id),
        FOREIGN KEY (game_id) REFERENCES games (id) ON DELETE CASCADE,
        UNIQUE(game_id, discord_id)
    );

    CREATE TABLE IF NOT EXISTS game_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        game_id INTEGER NOT NULL,
        message TEXT NOT NULL,
        FOREIGN KEY (game_id) REFERENCES games(id) ON DELETE CASCADE
    );
    """,
    # SCHEMA 2
    """\
    ALTER TABLE games ADD COLUMN besieges TEXT;
    """,
    # SCHEMA 3
    """\
    CREATE TABLE IF NOT EXISTS commands (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        game_id INTEGER NOT NULL,
        player_id TEXT NOT NULL,
        actor TEXT NOT NULL,
        command TEXT NOT NULL,
        target TEXT,
        FOREIGN KEY (game_id) REFERENCES games(id) ON DELETE CASCADE,
        FOREIGN KEY (game_id, player_id)
            REFERENCES players(game_id, player_id) ON DELETE CASCADE
    );
    """,
)

# Importamos el logger
logger = logging.getLogger(__name__)


def upgrade_connection(conn: sqlite3.Connection) -> None:
    """Upgrade an existing connection without taking ownership of its lifetime."""
    cursor = conn.cursor()
    cursor.execute("PRAGMA user_version;")
    current = cursor.fetchone()[0]

    if current >= _SCHEMA_VERSION:
        logger.info("No existen actualizaciones de base de datos")
        return

    logger.warning(
        "Actualiza el schema de la BBDD de %s a %s",
        current,
        _SCHEMA_VERSION,
    )
    try:
        for version in range(current, _SCHEMA_VERSION):
            target_version = version + 1
            logger.info("Actualizando a la versión %s", target_version)
            cursor.executescript(_UPGRADES[version])
            cursor.execute(f"PRAGMA user_version = {target_version};")
        conn.commit()
        logger.info("Esquema de la BBDD actualizado con éxito")
    except Exception:
        conn.rollback()
        logger.exception("Falló la actualización al schema %s", target_version)
        raise


def upgrade(db_path: str) -> None:
    """Open a SQLite database, apply all pending migrations, and close it."""
    conn = sqlite3.connect(db_path)
    try:
        upgrade_connection(conn)
    finally:
        conn.close()
