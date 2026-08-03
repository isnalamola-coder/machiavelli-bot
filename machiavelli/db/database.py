# machiavelli/db/database.py

import logging
import sqlite3
from pathlib import Path

logger = logging.getLogger(__name__)

_SCHEMA_VERSION = 3

_UPGRADES: tuple[str, ...] = (
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


class DatabaseManager:
    """Capa de Persistencia (Infraestructura).

    Gestiona la base de datos SQLite, migraciones de esquema y operaciones CRUD.
    """

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)

    def get_connection(self) -> sqlite3.Connection:
        """Abre una conexión a SQLite y aplica las configuraciones por sesión."""
        if not self.db_path.parent.exists():
            self.db_path.parent.mkdir(parents=True, exist_ok=True)

        conn = sqlite3.connect(self.db_path)

        # Mapeo de columnas por nombre
        conn.row_factory = sqlite3.Row

        # Pragmas obligatorios por sesión
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA journal_mode = WAL;")

        return conn

    def init_db(self) -> None:
        """Comprueba el 'user_version' y lo actualiza si es necesario."""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("PRAGMA user_version;")
            row = cursor.fetchone()
            current_version = row[0] if row else 0

            if current_version >= _SCHEMA_VERSION:
                logger.info(
                    "Esquema de BBDD actualizado (versión %d).", current_version
                )
                return

            logger.warning(
                "Actualizando esquema de BBDD de versión %d a %d.",
                current_version,
                _SCHEMA_VERSION,
            )

            for version in range(current_version, _SCHEMA_VERSION):
                target_version = version + 1
                logger.info("Aplicando migración a versión %d...", target_version)

                try:
                    # executescript gestiona sus propias transacciones DDL
                    cursor.executescript(_UPGRADES[version])
                    cursor.execute(f"PRAGMA user_version = {target_version};")
                    conn.commit()
                except Exception:
                    conn.rollback()
                    logger.exception(
                        "Falló la actualización al esquema %d.", target_version
                    )
                    raise

            logger.info(
                "Esquema de BBDD actualizado con éxito a la versión %d.",
                _SCHEMA_VERSION,
            )

        finally:
            conn.close()
