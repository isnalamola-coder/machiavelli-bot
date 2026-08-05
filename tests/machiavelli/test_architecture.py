import ast
import unicodedata
from pathlib import Path

from machiavelli import database as public_database
from machiavelli.db import database as canonical_database
from machiavelli.engine import GameEngine as PublicGameEngine
from machiavelli.engine.core import GameEngine
from machiavelli.game import Command as PublicCommand
from machiavelli.game import Player as PublicPlayer
from machiavelli.game.command import Command
from machiavelli.game.game import Game
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


def test_discord_imports_only_the_public_service_boundary() -> None:
    module = ast.parse(Path("machiavelli/discord.py").read_text(encoding="utf-8"))
    forbidden_imports: list[str] = []

    for node in ast.walk(module):
        if isinstance(node, ast.Import):
            forbidden_imports.extend(
                alias.name
                for alias in node.names
                if alias.name == "sqlite3"
                or alias.name.startswith("machiavelli.db")
                or alias.name.startswith("machiavelli.repositories")
            )
        elif isinstance(node, ast.ImportFrom):
            imported_module = node.module or ""
            if imported_module == "sqlite3" or imported_module.startswith(
                ("machiavelli.db", "machiavelli.repositories")
            ):
                forbidden_imports.append(imported_module)

    assert forbidden_imports == []


def test_discord_does_not_accept_a_dislodgement_resolver() -> None:
    module = ast.parse(Path("machiavelli/discord.py").read_text(encoding="utf-8"))
    offenders: list[str] = []

    for node in ast.walk(module):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        parameters = (
            [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]
            + ([node.args.vararg] if node.args.vararg is not None else [])
            + ([node.args.kwarg] if node.args.kwarg is not None else [])
        )
        if any(parameter.arg == "dislodgement_resolver" for parameter in parameters):
            offenders.append(node.name)

    assert offenders == []


def _docstring_nodes(module: ast.Module) -> set[int]:
    docstrings: set[int] = set()
    for owner in ast.walk(module):
        if not isinstance(
            owner,
            (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef),
        ):
            continue
        if not owner.body:
            continue
        first = owner.body[0]
        if (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
        ):
            docstrings.add(id(first.value))
    return docstrings


def _contains_channel_presentation(value: str) -> bool:
    stripped = value.lstrip()
    return (
        any(marker in value for marker in ("**", "__", "`", "<@"))
        or stripped.startswith(("# ", "## ", "### ", "> ", "- "))
        or any(unicodedata.category(character) == "So" for character in value)
    )


def test_game_and_engine_do_not_construct_channel_presentation() -> None:
    paths = [Path("machiavelli/game/game.py"), *Path("machiavelli/engine").glob("*.py")]
    offenders: list[str] = []

    for path in paths:
        module = ast.parse(path.read_text(encoding="utf-8"))
        docstrings = _docstring_nodes(module)
        for node in ast.walk(module):
            if (
                isinstance(node, ast.Constant)
                and id(node) not in docstrings
                and isinstance(node.value, str)
                and _contains_channel_presentation(node.value)
            ):
                offenders.append(f"{path}:{node.lineno}:{node.value!r}")

    assert offenders == []


def _is_text_expression(node: ast.AST) -> bool:
    if isinstance(node, ast.Constant):
        return isinstance(node.value, str)
    if isinstance(node, ast.JoinedStr):
        return True
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return _is_text_expression(node.left) or _is_text_expression(node.right)
    return False


def test_turn_event_layers_accept_only_structured_event_values() -> None:
    paths = [Path("machiavelli/game/game.py"), *Path("machiavelli/engine").glob("*.py")]
    offenders: list[str] = []

    for path in paths:
        module = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(module):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if node.func.attr == "add_event" and node.args:
                    if _is_text_expression(node.args[0]):
                        offenders.append(f"{path}:add_event-text")
                if (
                    node.func.attr == "append"
                    and isinstance(node.func.value, ast.Attribute)
                    and node.func.value.attr == "turn_events"
                    and node.args
                    and _is_text_expression(node.args[0])
                ):
                    offenders.append(f"{path}:turn_events-append-text")
            if isinstance(node, (ast.Assign, ast.AnnAssign)):
                targets = (
                    node.targets if isinstance(node, ast.Assign) else [node.target]
                )
                value = node.value
                if value is None:
                    continue
                if any(
                    isinstance(target, ast.Attribute) and target.attr == "turn_events"
                    for target in targets
                ) and _is_text_expression(value):
                    offenders.append(f"{path}:turn_events-text")

    assert offenders == []


def test_turn_event_layers_do_not_construct_legacy_type_json_records() -> None:
    paths = [Path("machiavelli/game/game.py"), *Path("machiavelli/engine").glob("*.py")]
    offenders: list[str] = []

    for path in paths:
        module = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(module):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if node.func.attr == "to_record":
                    offenders.append(f"{path}:to_record")
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and "|{" in node.value
            ):
                offenders.append(f"{path}:type-json-record")

    assert offenders == []


def test_removed_game_presentation_and_setup_methods_stay_absent() -> None:
    for method_name in (
        "initial_setup",
        "spring_start",
        "turn_report",
        "report_status",
    ):
        assert not hasattr(Game, method_name)
