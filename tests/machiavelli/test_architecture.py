import ast
from pathlib import Path

from machiavelli.engine import GameEngine as PublicGameEngine
from machiavelli.engine.core import GameEngine


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


def test_public_game_engine_is_canonical() -> None:
    assert PublicGameEngine is GameEngine


def test_shadowed_engine_module_does_not_exist() -> None:
    assert not Path("machiavelli/engine.py").exists()


def test_migration_tables_have_single_canonical_definitions() -> None:
    canonical_path = Path("machiavelli/db/database.py")
    assert _module_level_definitions("_UPGRADES") == [canonical_path]
    assert _module_level_definitions("_SCHEMA_VERSION") == [canonical_path]
