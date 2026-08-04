"""Tests for the Discord adapter and its application-service boundary."""

from __future__ import annotations

import os
import subprocess
import sys
import unittest
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import AsyncMock, Mock, patch

from machiavelli import database
from machiavelli.discord import (
    _add_player_record,
    _chunk_lines,
    _create_game_record,
    _execute_game_turn,
    _get_player_commands,
    _get_status_report,
    _get_turn_report,
    _service_session,
    _set_scenario_record,
    _submit_command_record,
    _submit_expense_record,
    add_player,
    admin_group,
    cmd,
    expense,
    game_group,
    game_report,
    game_status,
    run_game,
)
from machiavelli.engine.exceptions import TooManyExpenses
from machiavelli.engine.military import (
    CycleDiagnostic,
    DislodgementResolverRequired,
    InvalidMilitaryState,
    MilitaryResolutionError,
    UnresolvedMilitaryConflict,
)
from machiavelli.game import (
    DuplicatePlayerException,
    GameNotFoundException,
    PlayerNotFoundException,
)


def make_interaction(*, channel_id: int = 321, discord_id: int = 654) -> Mock:
    """Build a network-free interaction mock with all response surfaces."""
    interaction = Mock(name="interaction")
    interaction.channel_id = channel_id
    interaction.user = Mock(id=discord_id)
    interaction.namespace = Mock(power=None)
    interaction.response.defer = AsyncMock()
    interaction.response.send_message = AsyncMock()
    interaction.delete_original_response = AsyncMock()
    interaction.edit_original_response = AsyncMock()
    interaction.followup.send = AsyncMock()
    return interaction


class TestServiceWorkers(unittest.TestCase):
    """Verify that synchronous workers own and close their service session."""

    @patch("machiavelli.discord.sqlite3.connect")
    def test_service_session_always_closes_connection(self, mock_connect: Mock) -> None:
        connection = mock_connect.return_value

        with _service_session("game.db") as service:
            self.assertIs(service.repo.conn, connection)

        mock_connect.assert_called_once_with("game.db")
        connection.close.assert_called_once_with()

    def test_run_game_worker_delegates_to_service(self) -> None:
        service = Mock(name="service")
        service.run_turn.return_value = ["line one", "line two"]
        resolver = Mock(name="resolver")

        @contextmanager
        def fake_session(db_path: str):
            self.assertEqual(db_path, "game.db")
            yield service

        with patch("machiavelli.discord._service_session", fake_session):
            report = _execute_game_turn(
                "game.db",
                123,
                dislodgement_resolver=resolver,
            )

        self.assertEqual(report, ("line one", "line two"))
        service.run_turn.assert_called_once_with(
            123,
            dislodgement_resolver=resolver,
        )

    def test_run_game_worker_propagates_atomic_failure(self) -> None:
        service = Mock(name="service")
        failure = InvalidMilitaryState("duplicate occupation")
        service.run_turn.side_effect = failure

        @contextmanager
        def fake_session(_db_path: str):
            yield service

        with (
            patch("machiavelli.discord._service_session", fake_session),
            self.assertRaises(InvalidMilitaryState) as caught,
        ):
            _execute_game_turn("game.db", 123)

        self.assertIs(caught.exception, failure)

    def test_workers_integrate_with_temporary_sqlite(self) -> None:
        with TemporaryDirectory() as directory:
            db_path = str(Path(directory) / "discord-phase8.db")
            database.upgrade(db_path)

            game_name, database_id = _create_game_record(db_path, "Adapter", 8080)
            scenario_game_name, scenario_name = _set_scenario_record(
                db_path,
                8080,
                "Be",
            )
            persisted_name, players = _add_player_record(
                db_path,
                8080,
                4242,
                "Florencia",
            )

            with _service_session(db_path) as service:
                game = service.get_game(8080)
                game.turn_number = 2
                game.players[0].armies = ["milan"]
                service.repo.save(game)

            report = _submit_command_record(
                db_path,
                8080,
                4242,
                "A milan",
                "H",
                None,
            )
            player_id, commands = _get_player_commands(db_path, 8080, 4242)
            status = _get_status_report(db_path, 8080)

            self.assertEqual(game_name, "Adapter")
            self.assertGreater(database_id, 0)
            self.assertEqual(scenario_game_name, "Adapter")
            self.assertIn("balance of power", scenario_name.casefold())
            self.assertEqual(persisted_name, "Adapter")
            self.assertEqual(players, [("Florencia", 4242)])
            self.assertTrue(report[0].startswith("Orden `"))
            self.assertEqual(player_id, "Florencia")
            self.assertEqual(len(commands), 1)
            self.assertIn("Mantener", commands[0])
            self.assertTrue(any("Adapter" in line for line in status))


class TestPlayerCommands(unittest.IsolatedAsyncioTestCase):
    """Exercise player registration and order submission without Discord network I/O."""

    async def test_add_player_uses_service_and_keeps_public_response(self) -> None:
        interaction = make_interaction()
        member = Mock(id=777, mention="<@777>")

        with patch(
            "machiavelli.discord.asyncio.to_thread",
            new_callable=AsyncMock,
            return_value=("Diplomacia", [("Florencia", 777)]),
        ) as mock_to_thread:
            await add_player.callback(interaction, member, "Florencia")

        interaction.response.defer.assert_awaited_once_with(ephemeral=False)
        mock_to_thread.assert_awaited_once_with(
            _add_player_record,
            admin_group.db_path,
            interaction.channel_id,
            member.id,
            "Florencia",
        )
        sent_message = interaction.followup.send.await_args.args[0]
        self.assertIn("Florencia", sent_message)
        self.assertIn("<@777>", sent_message)
        self.assertNotIn("ephemeral", interaction.followup.send.await_args.kwargs)

    async def test_add_player_reports_missing_game(self) -> None:
        interaction = make_interaction()
        member = Mock(id=777, mention="<@777>")

        with patch(
            "machiavelli.discord.asyncio.to_thread",
            new_callable=AsyncMock,
            side_effect=GameNotFoundException,
        ):
            await add_player.callback(interaction, member, "Florencia")

        message = interaction.followup.send.await_args.args[0]
        self.assertIn("No hay ninguna partida activa", message)

    async def test_add_player_reports_duplicate_without_leaking_details(self) -> None:
        interaction = make_interaction()
        member = Mock(id=777, mention="<@777>")

        with patch(
            "machiavelli.discord.asyncio.to_thread",
            new_callable=AsyncMock,
            side_effect=DuplicatePlayerException("internal duplicate row"),
        ):
            await add_player.callback(interaction, member, "Florencia")

        message = interaction.followup.send.await_args.args[0]
        self.assertIn("ya está inscrito", message)
        self.assertNotIn("internal duplicate row", message)

    async def test_submit_command_is_private_and_uses_service(self) -> None:
        interaction = make_interaction(discord_id=900)
        report = ("Orden enviada.", "**Órdenes recibidas hasta ahora:**")

        with patch(
            "machiavelli.discord.asyncio.to_thread",
            new_callable=AsyncMock,
            return_value=report,
        ) as mock_to_thread:
            await cmd.callback(interaction, "A milan", "H", None)

        interaction.response.defer.assert_awaited_once_with(ephemeral=True)
        mock_to_thread.assert_awaited_once_with(
            _submit_command_record,
            game_group.db_path,
            interaction.channel_id,
            interaction.user.id,
            "A milan",
            "H",
            None,
        )
        interaction.followup.send.assert_awaited_once_with(
            "\n".join(report),
            ephemeral=True,
        )

    async def test_submit_command_reports_unknown_player_privately(self) -> None:
        interaction = make_interaction()

        with patch(
            "machiavelli.discord.asyncio.to_thread",
            new_callable=AsyncMock,
            side_effect=PlayerNotFoundException,
        ):
            await cmd.callback(interaction, "A milan", "H", None)

        interaction.followup.send.assert_awaited_once_with(
            "**Error:** No se identificó al jugador.",
            ephemeral=True,
        )

    async def test_excessive_expense_is_private_and_not_reported_as_saved(self) -> None:
        interaction = make_interaction(discord_id=901)

        with patch(
            "machiavelli.discord.asyncio.to_thread",
            new_callable=AsyncMock,
            side_effect=TooManyExpenses,
        ) as mock_to_thread:
            await expense.callback(interaction, "E F", "milan", "3")

        interaction.response.defer.assert_awaited_once_with(ephemeral=True)
        mock_to_thread.assert_awaited_once_with(
            _submit_expense_record,
            game_group.db_path,
            interaction.channel_id,
            interaction.user.id,
            "E F",
            "milan",
            "3",
        )
        message = interaction.followup.send.await_args.args[0]
        self.assertIn("Superado el límite de gastos", message)
        self.assertIn("no se ha guardado", message)
        self.assertTrue(interaction.followup.send.await_args.kwargs["ephemeral"])


class TestReports(unittest.IsolatedAsyncioTestCase):
    """Verify public/private response semantics and safe message partitioning."""

    async def test_game_status_is_public(self) -> None:
        interaction = make_interaction()

        with patch(
            "machiavelli.discord.asyncio.to_thread",
            new_callable=AsyncMock,
            return_value=("status one", "status two"),
        ) as mock_to_thread:
            await game_status.callback(interaction)

        interaction.response.defer.assert_awaited_once_with(ephemeral=False)
        mock_to_thread.assert_awaited_once_with(
            _get_status_report,
            game_group.db_path,
            interaction.channel_id,
        )
        interaction.followup.send.assert_awaited_once_with(
            "status one\nstatus two",
            ephemeral=False,
        )

    async def test_game_report_is_private(self) -> None:
        interaction = make_interaction()

        with patch(
            "machiavelli.discord.asyncio.to_thread",
            new_callable=AsyncMock,
            return_value=("report one", "report two"),
        ) as mock_to_thread:
            await game_report.callback(interaction)

        interaction.response.defer.assert_awaited_once_with(ephemeral=True)
        mock_to_thread.assert_awaited_once_with(
            _get_turn_report,
            game_group.db_path,
            interaction.channel_id,
        )
        interaction.followup.send.assert_awaited_once_with(
            "report one\nreport two",
            ephemeral=True,
        )

    def test_chunk_lines_preserves_order_and_never_exceeds_limit(self) -> None:
        lines = ("a" * 1200, "b" * 1200, "c" * 2100)

        chunks = _chunk_lines(lines, limit=1950)

        self.assertGreaterEqual(len(chunks), 3)
        self.assertTrue(all(0 < len(chunk) <= 1950 for chunk in chunks))
        self.assertEqual("".join(chunks).replace("\n", ""), "".join(lines))


class TestRunGame(unittest.IsolatedAsyncioTestCase):
    """Verify successful publication and safe atomic military failures."""

    async def test_run_game_success_publishes_public_report(self) -> None:
        interaction = make_interaction()

        with patch(
            "machiavelli.discord.asyncio.to_thread",
            new_callable=AsyncMock,
            return_value=("line one", "line two"),
        ) as mock_to_thread:
            await run_game.callback(interaction)

        interaction.response.defer.assert_awaited_once_with(ephemeral=True)
        mock_to_thread.assert_awaited_once_with(
            _execute_game_turn,
            admin_group.db_path,
            interaction.channel_id,
        )
        interaction.delete_original_response.assert_awaited_once_with()
        interaction.followup.send.assert_awaited_once_with(
            "line one\nline two",
            ephemeral=False,
        )
        interaction.edit_original_response.assert_not_awaited()

    async def test_run_game_not_found_edits_deferred_response(self) -> None:
        interaction = make_interaction()

        with patch(
            "machiavelli.discord.asyncio.to_thread",
            new_callable=AsyncMock,
            side_effect=GameNotFoundException,
        ):
            await run_game.callback(interaction)

        message = interaction.edit_original_response.await_args.kwargs["content"]
        self.assertIn("No hay ninguna partida activa", message)
        interaction.delete_original_response.assert_not_awaited()
        interaction.followup.send.assert_not_awaited()

    async def test_military_errors_are_logged_and_translated_atomically(self) -> None:
        diagnostic = CycleDiagnostic(
            stage="all-support-cancellation-exhausted",
            first_seen_iteration=1,
            repeated_iteration=2,
            pending_conflicts=("secret-place",),
            state_signature=(("secret",),),
        )
        cases = (
            (InvalidMilitaryState("duplicate at secret-place"), "ocupaciones"),
            (UnresolvedMilitaryConflict(diagnostic), "Revisa las órdenes"),
            (DislodgementResolverRequired("missing resolver"), "retiradas"),
            (MilitaryResolutionError("discord.py:999"), "Reintenta"),
        )

        for error, guidance in cases:
            with self.subTest(error=type(error).__name__):
                interaction = make_interaction()
                with (
                    patch(
                        "machiavelli.discord.asyncio.to_thread",
                        new_callable=AsyncMock,
                        side_effect=error,
                    ),
                    patch("machiavelli.discord.logger.exception") as mock_log,
                ):
                    await run_game.callback(interaction)

                mock_log.assert_called_once()
                message = interaction.edit_original_response.await_args.kwargs[
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
                    "secret-place",
                    "discord.py",
                    "999",
                    "Traceback",
                ):
                    self.assertNotIn(forbidden, message)
                interaction.delete_original_response.assert_not_awaited()
                interaction.followup.send.assert_not_awaited()


class TestImportSafety(unittest.TestCase):
    """Ensure importing adapters does not require a token or create a database."""

    def test_imports_have_no_database_or_network_side_effects(self) -> None:
        project_root = Path(__file__).resolve().parents[2]
        with TemporaryDirectory() as directory:
            database_path = Path(directory) / "must-not-exist.db"
            env = os.environ.copy()
            env.pop("DISCORD_TOKEN", None)
            env["DATABASE_PATH"] = str(database_path)
            env["PYTHONPATH"] = os.pathsep.join(
                filter(
                    None,
                    (str(project_root), env.get("PYTHONPATH", "")),
                )
            )

            result = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    "import bot; import machiavelli.discord; print('ok')",
                ],
                cwd=directory,
                env=env,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), "ok")
            self.assertFalse(database_path.exists())

    def test_public_command_groups_keep_their_names(self) -> None:
        self.assertEqual(game_group.name, "mach")
        self.assertEqual(admin_group.name, "shar")
        self.assertIn("cmd", {command.name for command in game_group.commands})
        self.assertIn("run_game", {command.name for command in admin_group.commands})


if __name__ == "__main__":
    unittest.main()
