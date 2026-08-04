# tests/test_machiavelli/test_versions.py
import sqlite3
from unittest.mock import MagicMock, call, patch

import pytest

from machiavelli import database as public_database
from machiavelli.db import database as canonical_database

upgrade = public_database.upgrade


@patch("machiavelli.db.database.sqlite3")
@patch("machiavelli.db.database._SCHEMA_VERSION", 3)
@patch(
    "machiavelli.db.database._UPGRADES",
    ["SQL_STEP_1", "SQL_STEP_2", "SQL_STEP_3"],
)
def test_upgrade_database_from_scratch(mock_sqlite3):
    """Prueba que si la base de datos es nueva (v0), se ejecutan las migraciones."""
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_sqlite3.connect.return_value = mock_conn
    mock_conn.cursor.return_value = mock_cursor
    mock_cursor.fetchone.return_value = [0]

    upgrade("fake.db")

    mock_sqlite3.connect.assert_called_once_with("fake.db")
    assert mock_cursor.executescript.call_count == 3
    mock_cursor.executescript.assert_has_calls(
        [call("SQL_STEP_1"), call("SQL_STEP_2"), call("SQL_STEP_3")],
        any_order=False,
    )
    mock_cursor.execute.assert_has_calls(
        [
            call("PRAGMA user_version;"),
            call("PRAGMA user_version = 1;"),
            call("PRAGMA user_version = 2;"),
            call("PRAGMA user_version = 3;"),
        ],
        any_order=False,
    )
    mock_conn.commit.assert_called_once_with()
    mock_conn.close.assert_called_once_with()


@patch("machiavelli.db.database.sqlite3")
@patch("machiavelli.db.database._SCHEMA_VERSION", 3)
@patch(
    "machiavelli.db.database._UPGRADES",
    ["SQL_STEP_1", "SQL_STEP_2", "SQL_STEP_3"],
)
def test_upgrade_database_partial_migration(mock_sqlite3):
    """Prueba que si la DB ya estaba en v1, solo se aplican los pasos 2 y 3."""
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_sqlite3.connect.return_value = mock_conn
    mock_conn.cursor.return_value = mock_cursor
    mock_cursor.fetchone.return_value = [1]

    upgrade("fake.db")

    assert mock_cursor.executescript.call_count == 2
    mock_cursor.executescript.assert_has_calls(
        [call("SQL_STEP_2"), call("SQL_STEP_3")],
        any_order=False,
    )


@patch("machiavelli.db.database.sqlite3")
@patch("machiavelli.db.database._SCHEMA_VERSION", 3)
@patch(
    "machiavelli.db.database._UPGRADES",
    ["SQL_STEP_1", "SQL_STEP_2", "SQL_STEP_3"],
)
def test_upgrade_database_fails_at_second_step(mock_sqlite3):
    """Prueba que si el segundo script falla, se hace rollback y la DB queda en v1."""
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_sqlite3.connect.return_value = mock_conn
    mock_conn.cursor.return_value = mock_cursor
    mock_cursor.fetchone.return_value = [0]
    mock_cursor.executescript.side_effect = [
        None,
        sqlite3.OperationalError("Syntax error in Step 2"),
    ]

    with pytest.raises(sqlite3.OperationalError, match="Syntax error in Step 2"):
        upgrade("fake.db")

    assert mock_cursor.executescript.call_count == 2
    mock_cursor.executescript.assert_has_calls([call("SQL_STEP_1"), call("SQL_STEP_2")])
    mock_cursor.execute.assert_any_call("PRAGMA user_version = 1;")
    for args, _ in mock_cursor.execute.call_args_list:
        assert "user_version = 2" not in args[0]
        assert "user_version = 3" not in args[0]
    mock_conn.rollback.assert_called_once_with()
    mock_conn.commit.assert_not_called()
    mock_conn.close.assert_called_once_with()


def test_public_database_api_reexports_canonical_functions() -> None:
    assert public_database.upgrade is canonical_database.upgrade
    assert public_database.upgrade_connection is canonical_database.upgrade_connection
    assert public_database.DatabaseManager is canonical_database.DatabaseManager


def test_private_migration_tables_are_not_public() -> None:
    assert not hasattr(public_database, "_UPGRADES")
    assert not hasattr(public_database, "_SCHEMA_VERSION")
