"""Pruebas de coordinación y barreras de error del motor de turnos."""

import unittest
from unittest.mock import Mock, call, patch

from machiavelli.engine.core import GameEngine
from machiavelli.engine.military import MilitaryResolutionError


class TestGameEngineRunStartup(unittest.TestCase):
    def setUp(self):
        self.mock_game = Mock()
        self.engine = GameEngine(game=self.mock_game)

    @patch("machiavelli.engine.core.SetupManager")
    @patch("machiavelli.engine.core.DisastersManager")
    @patch("machiavelli.engine.core.IncomeManager")
    def test_run_startup(
        self, mock_income_manager_cls, mock_disaster_manager_cls, mock_setup_manager_cls
    ):
        """Ejecuta correctamente el setup cuando estamos en el turno 0."""
        self.mock_game.turn_number = 0

        self.engine.run_startup()

        # Verifica que se instancia el SetupManager pasándole el game y el rng del motor
        mock_setup_manager_cls.assert_called_once_with(self.mock_game, self.engine.rng)

        # Instanciación correcta con game
        mock_disaster_manager_cls.assert_called_once_with(self.mock_game)
        mock_income_manager_cls.assert_called_once_with(self.mock_game)

        # Ejecución de los métodos correctos según core.py
        mock_disaster_manager_cls.return_value.spawn_famine.assert_called_once()
        mock_income_manager_cls.return_value.run.assert_called_once()

    @patch("machiavelli.engine.core.SetupManager")
    @patch("machiavelli.engine.core.DisastersManager")
    @patch("machiavelli.engine.core.IncomeManager")
    def test_run_startup_exception(
        self, mock_income_manager_cls, mock_disaster_manager_cls, mock_setup_manager_cls
    ):
        """Captura las excepciones y las reencadena como TurnExecutionFailed."""
        from machiavelli.engine.exceptions import (
            DuplicatePlayerError,
            TurnExecutionFailed,
        )

        self.mock_game.turn_number = 0

        # Simulamos que el SetupManager lanza un error de setup conocido
        error_raised = DuplicatePlayerError(player_id="p1", discord_id=None)
        mock_setup_manager_cls.return_value.run.side_effect = error_raised

        mock_disaster_manager_cls = mock_disaster_manager_cls.return_value
        mock_setup_manager_instance = mock_setup_manager_cls.return_value

        with self.assertRaises(TurnExecutionFailed) as ctx:
            self.engine.run_startup()

        # Comprobamos que el encadenamiento de excepciones (__cause__) se conserva
        self.assertIs(ctx.exception.__cause__, error_raised)

        # El manager de desastres posterior no debe haberse ejecutado
        mock_disaster_manager_cls.run.assert_not_called()

        # El setup manager SÍ fue llamado una vez antes de lanzar la excepción
        mock_setup_manager_instance.run.assert_called_once()


class TestGameEngineRunCampaign(unittest.TestCase):
    def setUp(self):
        self.mock_game = Mock()
        self.engine = GameEngine(game=self.mock_game)

    @patch("machiavelli.engine.core.ControlManager")
    @patch("machiavelli.engine.core.MilitaryResolver")
    @patch("machiavelli.engine.core.AssassinationResolver")
    @patch("machiavelli.engine.core.BribeResolver")
    @patch("machiavelli.engine.core.RebellionManager")
    @patch("machiavelli.engine.core.DisastersManager")
    @patch("machiavelli.engine.core.ExpenditureProcessor")
    def test_run_campaign_standard_season(
        self,
        mock_expenditure_cls,
        mock_disasters_cls,
        mock_rebellion_cls,
        mock_bribe_cls,
        mock_assassination_cls,
        mock_military_cls,
        mock_control_cls,
    ):
        """Para season != 2 (ej. season 1), omite los eventos de verano."""
        self.mock_game.turn_number = 1  # 1 % 4 = 1 (season 1)

        mock_disasters_inst = mock_disasters_cls.return_value

        self.engine.run_campaign()

        # Instanciación correcta con game
        mock_expenditure_cls.assert_called_once_with(self.mock_game)
        mock_disasters_cls.assert_called_once_with(self.mock_game)
        mock_rebellion_cls.assert_called_once_with(self.mock_game)
        mock_bribe_cls.assert_called_once_with(self.mock_game)
        mock_assassination_cls.assert_called_once_with(self.mock_game)
        mock_military_cls.assert_called_once_with(self.mock_game)
        mock_control_cls.assert_called_once_with(self.mock_game)

        # Ejecución de procesadores principales
        mock_expenditure_cls.return_value.run.assert_called_once()
        mock_disasters_inst.process_famine_relief_expenses.assert_called_once()
        mock_rebellion_cls.return_value.rebellion_expenses.assert_called_once()
        mock_bribe_cls.return_value.run.assert_called_once()
        mock_assassination_cls.return_value.run.assert_called_once()
        mock_military_cls.return_value.run.assert_called_once()
        mock_control_cls.return_value.run.assert_called_once()

        # Métodos exclusivos de season == 2 NO deben llamarse
        mock_disasters_inst.resolve_famine_attrition.assert_not_called()
        mock_disasters_inst.clear_famine.assert_not_called()
        mock_disasters_inst.spawn_plague.assert_not_called()

    @patch("machiavelli.engine.core.ControlManager")
    @patch("machiavelli.engine.core.MilitaryResolver")
    @patch("machiavelli.engine.core.AssassinationResolver")
    @patch("machiavelli.engine.core.BribeResolver")
    @patch("machiavelli.engine.core.RebellionManager")
    @patch("machiavelli.engine.core.DisastersManager")
    @patch("machiavelli.engine.core.ExpenditureProcessor")
    def test_run_campaign_season_2(
        self,
        mock_expenditure_cls,
        mock_disasters_cls,
        mock_rebellion_cls,
        mock_bribe_cls,
        mock_assassination_cls,
        mock_military_cls,
        mock_control_cls,
    ):
        """Para season == 2 ejecuta attrition, limpia hambre y genera de plaga."""
        self.mock_game.turn_number = 2  # 2 % 4 = 2 (season 2)

        mock_disasters_inst = mock_disasters_cls.return_value

        self.engine.run_campaign()

        # Métodos de season == 2 SÍ deben ejecutarse
        mock_disasters_inst.resolve_famine_attrition.assert_called_once()
        mock_disasters_inst.clear_famine.assert_called_once()
        mock_disasters_inst.spawn_plague.assert_called_once()

    @patch("machiavelli.engine.core.ControlManager")
    @patch("machiavelli.engine.core.MilitaryResolver")
    @patch("machiavelli.engine.core.AssassinationResolver")
    @patch("machiavelli.engine.core.BribeResolver")
    @patch("machiavelli.engine.core.RebellionManager")
    @patch("machiavelli.engine.core.DisastersManager")
    @patch("machiavelli.engine.core.ExpenditureProcessor")
    @patch("machiavelli.engine.core.RetreatHandler")
    def test_run_campaign_season_2_execution_order(
        self,
        mock_retreat_handler_cls,
        mock_expenditure_cls,
        mock_disasters_cls,
        mock_rebellion_cls,
        mock_bribe_cls,
        mock_assassination_cls,
        mock_military_cls,
        mock_control_cls,
    ):
        """Verifica el orden secuencial exacto de ejecución durante en season == 2."""
        self.mock_game.turn_number = 2
        mock_retreat_instance = mock_retreat_handler_cls.return_value

        # Rastreador centralizado de orden de llamadas
        manager = Mock()
        manager.attach_mock(mock_expenditure_cls.return_value.run, "expenditure_run")
        manager.attach_mock(
            mock_disasters_cls.return_value.process_famine_relief_expenses,
            "famine_relief",
        )
        manager.attach_mock(
            mock_rebellion_cls.return_value.rebellion_expenses, "rebellion_expenses"
        )
        manager.attach_mock(mock_bribe_cls.return_value.run, "bribe_run")
        manager.attach_mock(
            mock_assassination_cls.return_value.run, "assassination_run"
        )
        manager.attach_mock(mock_military_cls.return_value.run, "military_run")
        manager.attach_mock(
            mock_disasters_cls.return_value.resolve_famine_attrition, "attrition"
        )
        manager.attach_mock(mock_control_cls.return_value.run, "control_run")
        manager.attach_mock(
            mock_disasters_cls.return_value.clear_famine, "clear_famine"
        )
        manager.attach_mock(
            mock_disasters_cls.return_value.spawn_plague, "spawn_plague"
        )

        self.engine.run_campaign()

        expected_calls = [
            call.expenditure_run(),
            call.famine_relief(),
            call.rebellion_expenses(),
            call.bribe_run(),
            call.assassination_run(),
            call.military_run(dislodgement_resolver=mock_retreat_instance),
            call.attrition(),
            call.control_run(),
            call.clear_famine(),
            call.spawn_plague(),
        ]

        self.assertEqual(manager.mock_calls, expected_calls)

    @patch("machiavelli.engine.core.ControlManager")
    @patch("machiavelli.engine.core.MilitaryResolver")
    @patch("machiavelli.engine.core.AssassinationResolver")
    @patch("machiavelli.engine.core.BribeResolver")
    @patch("machiavelli.engine.core.RebellionManager")
    @patch("machiavelli.engine.core.DisastersManager")
    @patch("machiavelli.engine.core.ExpenditureProcessor")
    @patch("machiavelli.engine.core.IncomeManager")
    @patch("machiavelli.engine.core.RetreatHandler")
    def test_run_campaign_season_0_execution_order(
        self,
        mock_retreat_handler_cls,
        mock_income_cls,
        mock_expenditure_cls,
        mock_disasters_cls,
        mock_rebellion_cls,
        mock_bribe_cls,
        mock_assassination_cls,
        mock_military_cls,
        mock_control_cls,
    ):
        """Verifica el orden secuencial exacto de ejecución durante en season == 0."""
        self.mock_game.turn_number = 4
        mock_retreat_instance = mock_retreat_handler_cls.return_value

        # Rastreador centralizado de orden de llamadas
        manager = Mock()
        manager.attach_mock(mock_expenditure_cls.return_value.run, "expenditure_run")
        manager.attach_mock(
            mock_disasters_cls.return_value.process_famine_relief_expenses,
            "famine_relief",
        )
        manager.attach_mock(
            mock_rebellion_cls.return_value.rebellion_expenses, "rebellion_expenses"
        )
        manager.attach_mock(mock_bribe_cls.return_value.run, "bribe_run")
        manager.attach_mock(
            mock_assassination_cls.return_value.run, "assassination_run"
        )
        manager.attach_mock(mock_military_cls.return_value.run, "military_run")
        manager.attach_mock(mock_control_cls.return_value.run, "control_run")
        manager.attach_mock(
            mock_disasters_cls.return_value.spawn_famine, "spawn_famine"
        )
        manager.attach_mock(mock_income_cls.return_value.run, "income_run")

        self.engine.run_campaign()

        expected_calls = [
            call.expenditure_run(),
            call.famine_relief(),
            call.rebellion_expenses(),
            call.bribe_run(),
            call.assassination_run(),
            call.military_run(dislodgement_resolver=mock_retreat_instance),
            call.control_run(),
            call.spawn_famine(),
            call.income_run(),
        ]

        self.assertEqual(manager.mock_calls, expected_calls)


class TestGameEngineRun(unittest.TestCase):
    def setUp(self):
        self.mock_game = Mock()
        self.engine = GameEngine(game=self.mock_game)

    def test_run_do_startup(self):
        """Llama exclusivamente a run_startup() cuando turn_number es 0."""
        self.mock_game.turn_number = 0

        with (
            patch.object(self.engine, "run_startup") as mock_startup,
            patch.object(self.engine, "run_maintenance") as mock_maintenance,
            patch.object(self.engine, "run_campaign") as mock_campaign,
        ):
            self.engine.run()

            mock_startup.assert_called_once()
            mock_maintenance.assert_not_called()
            mock_campaign.assert_not_called()

    def test_run_do_maintenance(self):
        """Llama exclusivamente a run_maintenance() en el primer turno de primavera."""
        spring_turns = [1, 5, 9, 13]

        for turn in spring_turns:
            with self.subTest(turn_number=turn):
                self.mock_game.turn_number = turn

                with (
                    patch.object(self.engine, "run_startup") as mock_startup,
                    patch.object(self.engine, "run_maintenance") as mock_maintenance,
                    patch.object(self.engine, "run_campaign") as mock_campaign,
                ):
                    self.engine.run()

                    mock_maintenance.assert_called_once()
                    mock_startup.assert_not_called()
                    mock_campaign.assert_not_called()

    def test_run_do_campaign(self):
        """Llama exclusivamente a run_campaign() en el resto de estaciones."""
        campaign_turns = [2, 3, 4, 6, 7, 8, 10, 11, 12]

        for turn in campaign_turns:
            with self.subTest(turn_number=turn):
                self.mock_game.turn_number = turn

                with (
                    patch.object(self.engine, "run_startup") as mock_startup,
                    patch.object(self.engine, "run_maintenance") as mock_maintenance,
                    patch.object(self.engine, "run_campaign") as mock_campaign,
                ):
                    self.engine.run()

                    mock_campaign.assert_called_once()
                    mock_startup.assert_not_called()
                    mock_maintenance.assert_not_called()

    def test_run_advances_lifecycle_only_after_success(self):
        """No avanza ni limpia órdenes cuando la fase activa falla."""
        self.mock_game.turn_number = 2

        with patch.object(self.engine, "run_campaign"):
            self.engine.run()
        self.mock_game.advance_turn.assert_called_once_with()

        self.mock_game.advance_turn.reset_mock()
        with (
            patch.object(
                self.engine,
                "run_campaign",
                side_effect=RuntimeError("phase failed"),
            ),
            self.assertRaises(RuntimeError),
        ):
            self.engine.run()
        self.mock_game.advance_turn.assert_not_called()

    # def test_run_maintenance_uses_the_game_domain_rules(self):
    #     """La integración no duplica todavía el algoritmo de mantenimiento."""
    #     self.engine.run_maintenance()
    #     self.mock_game.spring_maintenance.assert_called_once_with()


class TestGameEngineDislodgementBarrier(unittest.TestCase):
    """Verifica la inyección de retiradas y la parada tras un fallo militar."""

    @patch("machiavelli.engine.core.ControlManager")
    @patch("machiavelli.engine.core.MilitaryResolver")
    @patch("machiavelli.engine.core.AssassinationResolver")
    @patch("machiavelli.engine.core.BribeResolver")
    @patch("machiavelli.engine.core.RebellionManager")
    @patch("machiavelli.engine.core.DisastersManager")
    @patch("machiavelli.engine.core.ExpenditureProcessor")
    @patch("machiavelli.engine.core.RetreatHandler")
    def test_manager_is_forwarded_and_control_observes_consolidated_state(
        self,
        mock_retreat_handler_cls,
        mock_expenditure_cls,
        mock_disasters_cls,
        mock_rebellion_cls,
        mock_bribe_cls,
        mock_assassination_cls,
        mock_military_cls,
        mock_control_cls,
    ):
        game = Mock()
        game.turn_number = 2
        player = Mock()
        player.armies = ["before"]
        game.players = [player]
        mock_retreat_instance = mock_retreat_handler_cls.return_value
        observed_by_control = []

        def finish_military(*, dislodgement_resolver):
            """Simula el commit militar antes de que se ejecute control."""
            self.assertIs(dislodgement_resolver, mock_retreat_instance)
            player.armies = ["resolved"]

        def capture_control():
            """Captura el estado que recibe la fase posterior al resolver militar."""
            observed_by_control.append(tuple(player.armies))

        mock_military_cls.return_value.run.side_effect = finish_military
        mock_control_cls.return_value.run.side_effect = capture_control
        order = Mock()
        order.attach_mock(mock_military_cls.return_value.run, "military")
        order.attach_mock(
            mock_disasters_cls.return_value.resolve_famine_attrition,
            "attrition",
        )
        order.attach_mock(mock_control_cls.return_value.run, "control")
        order.attach_mock(mock_disasters_cls.return_value.clear_famine, "clear")
        order.attach_mock(mock_disasters_cls.return_value.spawn_plague, "plague")

        engine = GameEngine(game)
        engine.run_campaign()

        mock_military_cls.return_value.run.assert_called_once_with(
            dislodgement_resolver=mock_retreat_instance
        )
        self.assertEqual(observed_by_control, [("resolved",)])
        self.assertEqual(
            order.mock_calls,
            [
                call.military(dislodgement_resolver=mock_retreat_instance),
                call.attrition(),
                call.control(),
                call.clear(),
                call.plague(),
            ],
        )

    @patch("machiavelli.engine.core.ControlManager")
    @patch("machiavelli.engine.core.MilitaryResolver")
    @patch("machiavelli.engine.core.AssassinationResolver")
    @patch("machiavelli.engine.core.BribeResolver")
    @patch("machiavelli.engine.core.RebellionManager")
    @patch("machiavelli.engine.core.DisastersManager")
    @patch("machiavelli.engine.core.ExpenditureProcessor")
    @patch("machiavelli.engine.core.RetreatHandler")
    def test_military_error_stops_all_later_campaign_phases(
        self,
        mock_retreat_handler_cls,
        mock_expenditure_cls,
        mock_disasters_cls,
        mock_rebellion_cls,
        mock_bribe_cls,
        mock_assassination_cls,
        mock_military_cls,
        mock_control_cls,
    ):
        game = Mock()
        game.turn_number = 2
        mock_retreat_instance = mock_retreat_handler_cls.return_value
        error = MilitaryResolutionError("stop")
        mock_military_cls.return_value.run.side_effect = error
        engine = GameEngine(game)

        with self.assertRaises(MilitaryResolutionError) as caught:
            engine.run_campaign()

        self.assertIs(caught.exception, error)
        mock_military_cls.return_value.run.assert_called_once_with(
            dislodgement_resolver=mock_retreat_instance
        )
        mock_disasters_cls.return_value.resolve_famine_attrition.assert_not_called()
        mock_control_cls.return_value.run.assert_not_called()
        mock_disasters_cls.return_value.clear_famine.assert_not_called()
        mock_disasters_cls.return_value.spawn_plague.assert_not_called()
