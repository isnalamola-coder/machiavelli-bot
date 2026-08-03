"""Pruebas del worker de turnos y de la respuesta pública de Discord."""

import unittest
from unittest.mock import AsyncMock, Mock, patch

from machiavelli.discord import (
    _execute_game_turn,
    _military_error_message,
    admin_group,
    run_game,
)
from machiavelli.engine.military import (
    CycleDiagnostic,
    DislodgementResolverRequired,
    InvalidMilitaryState,
    MilitaryResolutionError,
    UnresolvedMilitaryConflict,
)
from machiavelli.game import GameNotFoundException


class TestRunGameWorker(unittest.TestCase):
    """Verifica que carga, motor, informe y guardado comparten un único worker."""
    @patch("machiavelli.discord.GameEngine")
    @patch("machiavelli.discord.Game.load_game")
    @patch("machiavelli.discord.sqlite3.connect")
    def test_run_game_worker_owns_database_game_engine_report_and_save(
        self,
        mock_connect,
        mock_load_game,
        mock_engine_cls,
    ):
        connection = mock_connect.return_value
        connection.__enter__.return_value = connection
        game = Mock(name="game")
        game.turn_report.return_value = ["line one", "line two"]
        mock_load_game.return_value = game
        dislodgement_resolver = Mock(name="dislodgement_resolver")

        report = _execute_game_turn(
            "game.db",
            123,
            dislodgement_resolver=dislodgement_resolver,
        )

        self.assertEqual(report, ("line one", "line two"))
        mock_connect.assert_called_once_with("game.db")
        connection.__enter__.assert_called_once_with()
        connection.__exit__.assert_called_once()
        connection.close.assert_called_once_with()
        mock_load_game.assert_called_once_with(connection, channel_id=123)
        mock_engine_cls.assert_called_once_with(
            game,
            dislodgement_resolver=dislodgement_resolver,
        )
        mock_engine_cls.return_value.run.assert_called_once_with()
        game.turn_report.assert_called_once_with()
        game.save.assert_called_once_with(connection)

    @patch("machiavelli.discord.Game.load_game")
    @patch("machiavelli.discord.sqlite3.connect")
    def test_run_game_worker_closes_database_when_execution_fails(
        self,
        mock_connect,
        mock_load_game,
    ):
        connection = mock_connect.return_value
        connection.__enter__.return_value = connection
        failure = RuntimeError("load failed")
        mock_load_game.side_effect = failure

        with self.assertRaises(RuntimeError) as caught:
            _execute_game_turn("game.db", 123)

        self.assertIs(caught.exception, failure)
        connection.__enter__.assert_called_once_with()
        connection.__exit__.assert_called_once()
        connection.close.assert_called_once_with()


class TestRunGame(unittest.IsolatedAsyncioTestCase):
    """Comprueba la traducción de errores y la publicación del informe."""
    def setUp(self):
        """Crea una interacción asíncrona aislada para cada caso."""
        self.interaction = Mock(name="interaction")
        self.interaction.channel_id = 321
        self.interaction.response.defer = AsyncMock()
        self.interaction.delete_original_response = AsyncMock()
        self.interaction.edit_original_response = AsyncMock()
        self.interaction.followup.send = AsyncMock()

    async def test_run_game_success_runs_one_worker_and_publishes_public_report(self):
        with patch(
            "machiavelli.discord.asyncio.to_thread",
            new_callable=AsyncMock,
            return_value=("line one", "line two"),
        ) as mock_to_thread:
            await run_game.callback(self.interaction)

        self.interaction.response.defer.assert_awaited_once_with(ephemeral=True)
        mock_to_thread.assert_awaited_once_with(
            _execute_game_turn,
            admin_group.db_path,
            self.interaction.channel_id,
        )
        self.interaction.delete_original_response.assert_awaited_once_with()
        self.interaction.followup.send.assert_awaited_once_with(
            "line one\nline two",
            ephemeral=False,
        )
        self.interaction.edit_original_response.assert_not_awaited()

    async def test_run_game_not_found_edits_the_deferred_response(self):
        with patch(
            "machiavelli.discord.asyncio.to_thread",
            new_callable=AsyncMock,
            side_effect=GameNotFoundException,
        ):
            await run_game.callback(self.interaction)

        self.interaction.response.defer.assert_awaited_once_with(ephemeral=True)
        self.interaction.edit_original_response.assert_awaited_once()
        message = self.interaction.edit_original_response.await_args.kwargs["content"]
        self.assertIn("No hay ninguna partida activa", message)
        self.interaction.delete_original_response.assert_not_awaited()
        self.interaction.followup.send.assert_not_awaited()

    async def test_run_game_military_errors_are_logged_and_translated_safely(self):
        diagnostic = CycleDiagnostic(
            stage="all-support-cancellation-exhausted",
            first_seen_iteration=1,
            repeated_iteration=2,
            pending_conflicts=("secret-place",),
            state_signature=(("secret",),),
        )
        # Cada error conserva una acción distinta sin filtrar datos internos.
        cases = (
            (
                InvalidMilitaryState("duplicate at secret-place"),
                "ocupaciones incompatibles",
            ),
            (
                UnresolvedMilitaryConflict(diagnostic),
                "Revisa las órdenes",
            ),
            (
                DislodgementResolverRequired("missing resolver"),
                "gestión de retiradas",
            ),
            (
                MilitaryResolutionError("internal path discord.py:999"),
                "Reintenta el turno",
            ),
        )
        for error, guidance in cases:
            with self.subTest(error=type(error).__name__):
                self.setUp()
                with (
                    patch(
                        "machiavelli.discord.asyncio.to_thread",
                        new_callable=AsyncMock,
                        side_effect=error,
                    ),
                    patch("machiavelli.discord.logger.exception") as mock_log,
                ):
                    await run_game.callback(self.interaction)

                mock_log.assert_called_once()
                self.interaction.edit_original_response.assert_awaited_once()
                message = self.interaction.edit_original_response.await_args.kwargs[
                    "content"
                ]
                self.assertTrue(
                    message.startswith(
                        "No se pudo resolver la fase militar; "
                        "no se aplicó ningún cambio."
                    )
                )
                self.assertIn(guidance, message)
                for forbidden in (
                    type(error).__name__,
                    "CycleDiagnostic",
                    "secret-place",
                    "discord.py",
                    "999",
                    "Traceback",
                ):
                    self.assertNotIn(forbidden, message)
                self.interaction.delete_original_response.assert_not_awaited()
                self.interaction.followup.send.assert_not_awaited()

    def test_run_game_each_military_error_has_specific_guidance(self):
        diagnostic = CycleDiagnostic(
            stage="targeted-support-cancellation-exhausted",
            first_seen_iteration=0,
            repeated_iteration=1,
            pending_conflicts=("a",),
            state_signature=(),
        )
        messages = {
            _military_error_message(InvalidMilitaryState()): "invalid",
            _military_error_message(UnresolvedMilitaryConflict(diagnostic)): "cycle",
            _military_error_message(DislodgementResolverRequired()): "resolver",
            _military_error_message(MilitaryResolutionError()): "base",
        }

        self.assertEqual(len(messages), 4)


if __name__ == "__main__":
    unittest.main()
