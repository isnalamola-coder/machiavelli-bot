# tests/machiavelli/game/test_command.py

from machiavelli.game.command import Command
from machiavelli.game.tables import GameTables


def test_command_repr():
    cmd = Command(
        game_id=1,
        player_id=10,
        actor="A milan",
        command="M",
        target="venic",
    )
    assert repr(cmd) == "Command(actor='A milan', command='M', target='venic')"


class TestIsValidExpense:
    def test_valid_expense_default_tables(self, monkeypatch):
        monkeypatch.setattr(
            GameTables, "expenses", {"B": {"text": "Pacificar rebelión"}}
        )

        cmd = Command(game_id=1, player_id=1, actor="E B", command="12")
        assert cmd.is_valid_expense() is True

    def test_valid_expense_with_allowed_types(self):
        cmd = Command(game_id=1, player_id=1, actor="E B", command="12")
        assert cmd.is_valid_expense(allowed_types={"B", "S"}) is True
        assert cmd.is_valid_expense(allowed_types={"S"}) is False

    def test_invalid_actor_format(self):
        invalid_actors = ["A milan", "E", "E B 12", "E_B"]
        for actor in invalid_actors:
            cmd = Command(game_id=1, player_id=1, actor=actor, command="12")
            assert cmd.is_valid_expense() is False
