# test/machiavelli/engine/test_expenditure.py
import unittest
from unittest.mock import Mock

import pytest

from machiavelli.engine.expenditure import ExpenditureProcessor
from machiavelli.events import EventType, TurnEvent


@pytest.mark.parametrize(
    (
        "event_type",
        "command_value",
        "ducats",
        "target",
        "expected_amount",
        "expected_ducats",
        "command_retained",
    ),
    [
        (
            EventType.EXPENSE_SYNTAX_ERROR,
            "diez",
            50,
            None,
            "diez",
            50,
            False,
        ),
        (EventType.EXPENSE, "20", 50, "pisa", 20, 30, True),
        (EventType.EXPENSE_NO_FUNDS, "100", 50, None, 100, 50, False),
    ],
)
def test_expense_results_emit_exact_typed_payloads(
    event_type: EventType,
    command_value: str,
    ducats: int,
    target: str | None,
    expected_amount: int | str,
    expected_ducats: int,
    command_retained: bool,
) -> None:
    game = Mock()
    game.add_event = Mock()
    player = Mock(player_id="P1", ducats=ducats, commands=[])
    command = Mock(
        command=command_value,
        actor="E G",
        target=target,
    )
    command.is_valid_expense.return_value = True
    player.commands = [command]
    game.players = [player]

    ExpenditureProcessor(game).run()

    events = [call.args[0] for call in game.add_event.call_args_list]
    assert len(events) == 1
    assert all(isinstance(event, TurnEvent) for event in events)
    assert not any(isinstance(event, str) for event in events)
    event = events[0]
    assert event.type is event_type
    assert dict(event.data) == {
        "player": "P1",
        "expense": "G",
        "target": target,
        "amount": expected_amount,
    }
    assert player.ducats == expected_ducats
    assert player.commands == ([command] if command_retained else [])


class TestExpenditureProcessor(unittest.TestCase):
    """Tests unitarios para ExpenditureProcessor."""

    def setUp(self):
        self.mock_game = Mock()
        self.mock_game.add_event = Mock()
        self.processor = ExpenditureProcessor(self.mock_game)

        # Estado inicial del jugador de prueba
        self.player = Mock()
        self.player.player_id = "P1"
        self.player.ducats = 50
        self.player.commands = []
        self.mock_game.players = [self.player]

    def _make_cmd(self, is_expense: bool, command_val: str, actor="E G", target="pisa"):
        """Helper para construir mocks de Command con el formato esperado."""
        cmd = Mock()
        cmd.is_valid_expense.return_value = is_expense
        cmd.command = command_val
        cmd.actor = actor
        cmd.target = target
        return cmd

    def test_process_player_expenses_no_expense(self):
        """Las órdenes que no son de gasto se conservan silenciosamente."""
        cmd = self._make_cmd(is_expense=False, command_val="A flore")
        self.player.commands = [cmd]

        self.processor.run()

        self.assertEqual(self.player.commands, [cmd])
        self.assertEqual(self.player.ducats, 50)
        self.mock_game.add_event.assert_not_called()

    def test_process_player_expenses_no_numeric_amount(self):
        """Si el importe no es un entero, la descarta y emite EXPENSE_SYNTAX_ERROR."""
        cmd = self._make_cmd(is_expense=True, command_val="diez")
        self.player.commands = [cmd]

        self.processor.run()

        self.assertEqual(self.player.commands, [])
        self.assertEqual(self.player.ducats, 50)
        self.mock_game.add_event.assert_called_once()

        event = self.mock_game.add_event.call_args[0][0]
        self.assertEqual(event.type, EventType.EXPENSE_SYNTAX_ERROR)
        self.assertEqual(event.data["amount"], "diez")

    def test_process_player_expenses_zero_or_negative_amount(self):
        """Si el importe es <= 0, descarta las órdenes y emite EXPENSE_SYNTAX_ERROR."""
        cmd_zero = self._make_cmd(is_expense=True, command_val="0")
        cmd_neg = self._make_cmd(is_expense=True, command_val="-10")
        self.player.commands = [cmd_zero, cmd_neg]

        self.processor.run()

        self.assertEqual(self.player.commands, [])
        self.assertEqual(self.player.ducats, 50)
        self.assertEqual(self.mock_game.add_event.call_count, 2)

    def test_process_player_expenses(self):
        """Con saldo suficiente, descuenta ducados, la conserva y emite EXPENSE."""
        cmd = self._make_cmd(is_expense=True, command_val="20")
        self.player.commands = [cmd]

        self.processor.run()

        self.assertEqual(self.player.commands, [cmd])
        self.assertEqual(self.player.ducats, 30)
        self.mock_game.add_event.assert_called_once()

        event = self.mock_game.add_event.call_args[0][0]
        self.assertEqual(event.type, EventType.EXPENSE)
        self.assertEqual(event.data["amount"], 20)
        self.assertEqual(event.data["expense"], "G")

    def test_process_player_expenses_no_funds(self):
        """Sin saldo suficiente, la descarta, no descuenta y emite EXPENSE_NO_FUNDS."""
        cmd = self._make_cmd(is_expense=True, command_val="100")
        self.player.commands = [cmd]

        self.processor.run()

        self.assertEqual(self.player.commands, [])
        self.assertEqual(self.player.ducats, 50)
        self.mock_game.add_event.assert_called_once()

        event = self.mock_game.add_event.call_args[0][0]
        self.assertEqual(event.type, EventType.EXPENSE_NO_FUNDS)
        self.assertEqual(event.data["amount"], 100)

    def test_run_sequential(self):
        """Procesa órdenes en orden FIFO recalculando el saldo tras cada cobro."""
        cmd1 = self._make_cmd(is_expense=True, command_val="30")  # Pasa (50-30 = 20)
        cmd2 = self._make_cmd(is_expense=True, command_val="25")  # Falla (20 < 25)
        cmd3 = self._make_cmd(is_expense=True, command_val="15")  # Pasa (20-15 = 5)

        self.player.commands = [cmd1, cmd2, cmd3]

        self.processor.run()

        # Únicamente cmd1 y cmd3 quedan financiados y conservados en orden
        self.assertEqual(self.player.commands, [cmd1, cmd3])
        self.assertEqual(self.player.ducats, 5)
        self.assertEqual(self.mock_game.add_event.call_count, 3)

        # Verificar tipos de evento emitidos secuencialmente
        calls = self.mock_game.add_event.call_args_list
        self.assertEqual(calls[0][0][0].type, EventType.EXPENSE)
        self.assertEqual(calls[1][0][0].type, EventType.EXPENSE_NO_FUNDS)
        self.assertEqual(calls[2][0][0].type, EventType.EXPENSE)
