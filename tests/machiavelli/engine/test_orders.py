# tests/machiavelli/engine/test_orders.py

from __future__ import annotations

import pytest

from machiavelli.engine.exceptions import TooManyExpenses
from machiavelli.engine.orders import OrderProcessor
from machiavelli.game.command import Command
from machiavelli.game.player import TurnType
from tests.machiavelli.engine.helpers import create_mock_game, create_mock_player


@pytest.fixture
def pyt_game():
    return create_mock_game()


@pytest.fixture
def pyt_player():
    player = create_mock_player(
        player_id="player_1",
        armies=["paler"],
        fleets=["messi"],
        garrisons=["naple"],
    )
    # Inicializamos las colecciones y métodos que espera OrderProcessor
    player.commands = []
    player.remove_command = lambda cmd: (
        player.commands.remove(cmd) if cmd in player.commands else None
    )
    player.add_command = lambda cmd: player.commands.append(cmd)
    return player


@pytest.fixture
def pyt_processor(pyt_game):
    return OrderProcessor(pyt_game)


class TestMaintenanceTurn:
    def test_add_new_command(self, pyt_processor, pyt_player):
        cmd = Command(actor="A A1", command="M", target="Madrid")
        report = pyt_processor.process_command(pyt_player, TurnType.MAINTENANCE, cmd)

        assert len(pyt_player.commands) == 1
        assert pyt_player.commands[0] == cmd
        assert any("Orden" in line for line in report)

    def test_replace_existing_command(self, pyt_processor, pyt_player):
        cmd1 = Command(actor="A A1", command="M", target="Madrid")
        pyt_player.commands.append(cmd1)

        cmd2 = Command(actor="A A1", command="S", target="Toledo")
        pyt_processor.process_command(pyt_player, TurnType.MAINTENANCE, cmd2)

        assert len(pyt_player.commands) == 1
        assert pyt_player.commands[0].command == "S"
        assert pyt_player.commands[0].target == "Toledo"

    def test_delete_new_unit_command_with_d(self, pyt_processor, pyt_player):
        cmd_initial = Command(actor="A A2", command="C", target="Sevilla")
        pyt_player.commands.append(cmd_initial)

        cmd_delete = Command(actor="A A2", command="D", target="Sevilla")
        pyt_processor.process_command(pyt_player, TurnType.MAINTENANCE, cmd_delete)

        assert len(pyt_player.commands) == 0

    def test_multiple_commands_raises_value_error(self, pyt_processor, pyt_player):
        pyt_player.commands.append(Command(actor="A A1", command="M", target="Madrid"))
        pyt_player.commands.append(Command(actor="A A1", command="S", target="Toledo"))

        cmd = Command(actor="A A1", command="H", target="")
        with pytest.raises(ValueError, match="Se encontraron múltiples comandos"):
            pyt_processor.process_command(pyt_player, TurnType.MAINTENANCE, cmd)


class TestCampaignTurn:
    def test_add_expense(self, pyt_processor, pyt_player):
        cmd = Command(actor="E 1", command="5", target="Gold")
        pyt_processor.process_command(pyt_player, TurnType.CAMPAIGN, cmd)

        assert len(pyt_player.commands) == 1
        assert pyt_player.commands[0] == cmd

    def test_update_or_remove_expense(self, pyt_processor, pyt_player):
        expense = Command(actor="E 1", command="5", target="Gold")
        pyt_player.commands.append(expense)

        update_cmd = Command(actor="E 1", command="3", target="Gold")
        pyt_processor.process_command(pyt_player, TurnType.CAMPAIGN, update_cmd)
        assert pyt_player.commands[0].command == "3"

        remove_cmd = Command(actor="E 1", command="0", target="Gold")
        pyt_processor.process_command(pyt_player, TurnType.CAMPAIGN, remove_cmd)
        assert len(pyt_player.commands) == 0

    def test_too_many_expenses_raises_exception(self, pyt_processor, pyt_player):
        for i in range(4):
            pyt_player.commands.append(
                Command(actor=f"E {i}", command="2", target="Gold")
            )

        new_expense = Command(actor="E 5", command="1", target="Gold")
        with pytest.raises(
            TooManyExpenses, match="Solo se permiten hasta cuatro gastos"
        ):
            pyt_processor.process_command(pyt_player, TurnType.CAMPAIGN, new_expense)

    def test_campaign_standard_command_replacement(self, pyt_processor, pyt_player):
        cmd1 = Command(actor="A A1", command="M", target="Madrid")
        pyt_player.commands.append(cmd1)

        cmd2 = Command(actor="A A1", command="H", target="")
        pyt_processor.process_command(pyt_player, TurnType.CAMPAIGN, cmd2)

        assert len(pyt_player.commands) == 1
        assert pyt_player.commands[0].command == "H"
