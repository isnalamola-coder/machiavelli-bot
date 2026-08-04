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
    def test_run_startup(self, mock_setup_manager_cls):
        """Ejecuta correctamente el setup cuando estamos en el turno 0."""
        self.mock_game.turn_number = 0
        mock_setup_manager_instance = mock_setup_manager_cls.return_value

        self.engine.run_startup()

        # Verifica que se instancia el SetupManager pasándole el game y el rng del motor
        mock_setup_manager_cls.assert_called_once_with(self.mock_game, self.engine.rng)
        # Verifica que se llama al método run() del manager
        mock_setup_manager_instance.run.assert_called_once()

    @patch("machiavelli.engine.core.SetupManager")
    def test_run_startup_exception(self, mock_setup_manager_cls):
        """Captura las excepciones y las reencadena como TurnExecutionFailed."""
        from machiavelli.engine.exceptions import (
            DuplicatePlayerError,
            TurnExecutionFailed,
        )

        self.mock_game.turn_number = 0

        # Simulamos que el SetupManager lanza un error de setup conocido
        error_raised = DuplicatePlayerError(player_id="p1", discord_id=None)
        mock_setup_manager_cls.return_value.run.side_effect = error_raised

        with self.assertRaises(TurnExecutionFailed) as ctx:
            self.engine.run_startup()

        # Comprobamos que el encadenamiento de excepciones (__cause__) se conserva
        self.assertIs(ctx.exception.__cause__, error_raised)


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
    def test_run_campaign_season_2_execution_order(
        self,
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
            call.military_run(dislodgement_resolver=None),
            call.attrition(),
            call.control_run(),
            call.clear_famine(),
            call.spawn_plague(),
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

    def test_run_maintenance_uses_the_game_domain_rules(self):
        """La integración no duplica todavía el algoritmo de mantenimiento."""
        self.engine.run_maintenance()
        self.mock_game.spring_maintenance.assert_called_once_with()


class TestGameEngineDislodgementBarrier(unittest.TestCase):
    """Verifica la inyección de retiradas y la parada tras un fallo militar."""
    @patch("machiavelli.engine.core.ControlManager")
    @patch("machiavelli.engine.core.MilitaryResolver")
    @patch("machiavelli.engine.core.AssassinationResolver")
    @patch("machiavelli.engine.core.BribeResolver")
    @patch("machiavelli.engine.core.RebellionManager")
    @patch("machiavelli.engine.core.DisastersManager")
    @patch("machiavelli.engine.core.ExpenditureProcessor")
    def test_manager_is_forwarded_and_control_observes_consolidated_state(
        self,
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
        dislodgement_resolver = Mock(name="dislodgement_resolver")
        observed_by_control = []

        def finish_military(*, dislodgement_resolver):
            """Simula el commit militar antes de que se ejecute control."""
            self.assertIs(dislodgement_resolver, dislodgement_resolver_mock)
            player.armies = ["resolved"]

        def capture_control():
            """Captura el estado que recibe la fase posterior al resolver militar."""
            observed_by_control.append(tuple(player.armies))

        dislodgement_resolver_mock = dislodgement_resolver
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

        engine = GameEngine(
            game,
            dislodgement_resolver=dislodgement_resolver,
        )
        self.assertIs(engine.dislodgement_resolver, dislodgement_resolver)
        engine.run_campaign()

        mock_military_cls.return_value.run.assert_called_once_with(
            dislodgement_resolver=dislodgement_resolver
        )
        self.assertEqual(observed_by_control, [("resolved",)])
        self.assertEqual(
            order.mock_calls,
            [
                call.military(dislodgement_resolver=dislodgement_resolver),
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
    def test_military_error_stops_all_later_campaign_phases(
        self,
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
        dislodgement_resolver = Mock(name="dislodgement_resolver")
        error = MilitaryResolutionError("stop")
        mock_military_cls.return_value.run.side_effect = error
        engine = GameEngine(
            game,
            dislodgement_resolver=dislodgement_resolver,
        )

        with self.assertRaises(MilitaryResolutionError) as caught:
            engine.run_campaign()

        self.assertIs(caught.exception, error)
        mock_military_cls.return_value.run.assert_called_once_with(
            dislodgement_resolver=dislodgement_resolver
        )
        mock_disasters_cls.return_value.resolve_famine_attrition.assert_not_called()
        mock_control_cls.return_value.run.assert_not_called()
        mock_disasters_cls.return_value.clear_famine.assert_not_called()
        mock_disasters_cls.return_value.spawn_plague.assert_not_called()
