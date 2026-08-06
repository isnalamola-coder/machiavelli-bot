import ast
from pathlib import Path

from machiavelli import database as public_database
from machiavelli.db import database as canonical_database
from machiavelli.engine import GameEngine as PublicGameEngine
from machiavelli.engine.core import GameEngine
from machiavelli.game import Command as PublicCommand
from machiavelli.game import Player as PublicPlayer
from machiavelli.game.command import Command
from machiavelli.game.player import Player


def _module_level_definitions(name: str) -> list[Path]:
    definitions: list[Path] = []
    for path in Path("machiavelli").rglob("*.py"):
        module = ast.parse(path.read_text(encoding="utf-8"))
        for node in module.body:
            if isinstance(node, ast.Assign) and any(
                isinstance(target, ast.Name) and target.id == name
                for target in node.targets
            ):
                definitions.append(path)
            elif (
                isinstance(node, ast.AnnAssign)
                and isinstance(node.target, ast.Name)
                and node.target.id == name
            ):
                definitions.append(path)
    return definitions


def test_public_domain_entities_are_canonical() -> None:
    assert PublicCommand is Command
    assert PublicPlayer is Player


def test_public_game_engine_is_canonical() -> None:
    assert PublicGameEngine is GameEngine


def test_public_database_api_is_canonical() -> None:
    assert public_database.upgrade is canonical_database.upgrade
    assert public_database.upgrade_connection is canonical_database.upgrade_connection
    assert public_database.DatabaseManager is canonical_database.DatabaseManager


def test_private_migration_tables_are_not_public() -> None:
    assert not hasattr(public_database, "_UPGRADES")
    assert not hasattr(public_database, "_SCHEMA_VERSION")


def test_migration_tables_have_single_canonical_definitions() -> None:
    canonical_path = Path("machiavelli/db/database.py")
    assert _module_level_definitions("_UPGRADES") == [canonical_path]
    assert _module_level_definitions("_SCHEMA_VERSION") == [canonical_path]


def test_forbidden_legacy_files_do_not_exist() -> None:
    forbidden_paths = (
        Path("machiavelli/engine.py"),
        Path("database.py"),
        Path("cli.log"),
    )
    assert not [path for path in forbidden_paths if path.exists()]
