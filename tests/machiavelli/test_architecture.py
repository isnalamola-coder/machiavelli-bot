from pathlib import Path

from machiavelli.engine import GameEngine as PublicGameEngine
from machiavelli.engine.core import GameEngine


def test_public_game_engine_is_canonical() -> None:
    assert PublicGameEngine is GameEngine


def test_shadowed_engine_module_does_not_exist() -> None:
    assert not Path("machiavelli/engine.py").exists()
