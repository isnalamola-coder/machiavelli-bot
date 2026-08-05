"""Pruebas de coordinación y barreras de error del motor de turnos."""

import inspect
import unittest
from collections.abc import Callable, Mapping
from random import Random
from unittest.mock import Mock, call, patch

import pytest

from machiavelli.engine.core import GameEngine
from machiavelli.engine.disasters import DisastersManager as RealDisastersManager
from machiavelli.engine.income import IncomeManager as RealIncomeManager
from machiavelli.engine.military import MilitaryResolutionError
from machiavelli.events import EventType, TurnEvent
from machiavelli.game.command import Command
from machiavelli.game.game import Game
from machiavelli.game.map import Map, Province
from machiavelli.game.player import Player
from machiavelli.game.scenario import (
    HomeCountry,
    Power,
    Rules,
    Scenario,
    VictoryConditions,
)


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
    def test_run_campaign_season_2_runs_disaster_steps(
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
            call.military_run(),
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
    @patch("machiavelli.engine.core.IncomeManager")
    def test_run_campaign_season_0_execution_order(
        self,
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
            call.military_run(),
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


class _TurnEventTrackingGame(Game):
    """Track replacements of the ephemeral event-list object."""

    def __init__(self, turn_number: int) -> None:
        super().__init__(
            name="tracking",
            turn_number=turn_number,
            turn_events=[TurnEvent(EventType.START_GAME, {"scenario": "before"})],
        )
        self.turn_event_replacements = 0
        self.advance_calls = 0

    def __setattr__(self, name: str, value: object) -> None:
        if name == "turn_events" and hasattr(self, "turn_event_replacements"):
            object.__setattr__(
                self,
                "turn_event_replacements",
                self.turn_event_replacements + 1,
            )
        super().__setattr__(name, value)

    def advance_turn(self) -> None:
        self.advance_calls += 1


@pytest.mark.parametrize(
    ("turn_number", "phase_method"),
    [(0, "run_startup"), (1, "run_maintenance"), (2, "run_campaign")],
    ids=("startup", "maintenance", "campaign"),
)
def test_run_replaces_event_history_exactly_once(
    turn_number: int, phase_method: str
) -> None:
    game = _TurnEventTrackingGame(turn_number)
    previous_history = game.turn_events
    engine = GameEngine(game)
    produced = TurnEvent(EventType.START_SEASON, {"year": 1500, "season": 0})

    with patch.object(
        engine,
        phase_method,
        side_effect=lambda: game.turn_events.append(produced),
    ):
        engine.run()

    assert game.turn_event_replacements == 1
    assert game.turn_events is not previous_history
    assert game.turn_events == [produced]
    assert previous_history == [TurnEvent(EventType.START_GAME, {"scenario": "before"})]
    assert game.advance_calls == 1


_CHARACTERIZATION_PHASES = ("startup", "maintenance", "campaign")
_ACTIVE_RULE_VALUES = {
    "fortress_active": True,
    "assassinations_active": True,
    "famine_active": True,
    "first_turn_famine": True,
    "plague_active": True,
}


def _characterization_game(
    rule_overrides: Mapping[str, bool] | None = None,
) -> Game:
    rule_values = dict(_ACTIVE_RULE_VALUES)
    if rule_overrides is not None:
        rule_values.update(rule_overrides)
    scenario = Scenario(
        name="Rule characterization",
        year=1454,
        victory_conditions=VictoryConditions(cities=99, home_countries=2),
        rules=Rules(**rule_values),
        home_countries={
            "H": HomeCountry(["fort", "keep", "rural"]),
            "J": HomeCountry(["port", "plain"]),
        },
        powers={
            "H": Power(
                home_countries=["H"],
                armies=["keep", "rural"],
                garrisons=["fort"],
            ),
            "J": Power(
                home_countries=["J"],
                armies=["plain"],
                fleets=["port"],
            ),
        },
    )
    game = Game(
        "rule-characterization",
        scenario_id="rules",
        scenario=scenario,
        map=Map(
            provinces={
                "fort": Province(
                    "Fortified City",
                    custom_id="fort",
                    city="fortified",
                    major_city=7,
                ),
                "keep": Province(
                    "Fortress",
                    custom_id="keep",
                    city="fortress",
                ),
                "rural": Province("Rural", custom_id="rural"),
                "port": Province(
                    "Port",
                    custom_id="port",
                    city="city",
                    has_port=True,
                    major_city=4,
                ),
                "plain": Province("Plain", custom_id="plain"),
                "citad": Province(
                    "Independent Citadel",
                    custom_id="citad",
                    city="fortified",
                ),
            },
            seas={},
        ),
    )
    game.players = [
        Player(game, "P1", discord_id=101),
        Player(game, "P2", discord_id=202),
    ]
    return game


def _set_characterization_campaign_commands(game: Game) -> None:
    for player in game.players:
        if player.power == "H":
            player.commands = [
                Command(game, player, "A keep", "C", "G"),
                Command(game, player, "A rural", "H", None),
                Command(game, player, "G fort", "H", None),
            ]
        else:
            player.commands = [
                Command(game, player, "A plain", "H", None),
                Command(game, player, "F port", "H", None),
            ]


def _commands_snapshot(
    game: Game,
) -> tuple[tuple[str, tuple[tuple[str, str, str | None], ...]], ...]:
    return tuple(
        (
            player.player_id,
            tuple(
                (command.actor, command.command, command.target)
                for command in player.commands
            ),
        )
        for player in sorted(game.players, key=lambda item: item.player_id)
    )


def _characterization_snapshot(
    game: Game,
    orders_before_clear: tuple[
        tuple[str, tuple[tuple[str, str, str | None], ...]], ...
    ],
) -> dict[str, object]:
    return {
        "turn_number": game.turn_number,
        "rules": tuple(
            (rule_name, getattr(game.require_scenario().rules, rule_name))
            for rule_name in _ACTIVE_RULE_VALUES
        ),
        "famine": tuple(game.famine),
        "independent_garrisons": tuple(game.independent_garrisons),
        "besieges": tuple(game.besieges),
        "orders_before_clear": orders_before_clear,
        "players": tuple(
            {
                "player_id": player.player_id,
                "discord_id": player.discord_id,
                "power": player.power,
                "controlled_locations": tuple(player.controlled_locations),
                "home_countries": tuple(player.home_countries),
                "armies": tuple(player.armies),
                "fleets": tuple(player.fleets),
                "garrisons": tuple(player.garrisons),
                "ass_counters": tuple(player.ass_counters),
                "ducats": player.ducats,
                "rebelled_provinces": tuple(player.rebelled_provinces),
                "rebelled_cities": tuple(player.rebelled_cities),
                "commands": tuple(
                    (command.actor, command.command, command.target)
                    for command in player.commands
                ),
            }
            for player in sorted(game.players, key=lambda item: item.player_id)
        ),
        "events": tuple(
            (event.type.value, event.to_json()) for event in game.turn_events
        ),
    }


def _run_characterization_game_until(
    game: Game,
    phase: str,
) -> dict[str, object]:
    with (
        patch(
            "machiavelli.engine.core.DisastersManager",
            side_effect=lambda active_game: RealDisastersManager(
                active_game,
                Random(200),
            ),
        ),
        patch("machiavelli.engine.disasters.GameTables") as disaster_tables,
    ):
        disaster_tables.expenses = {"A": {"cost": 3}}
        disaster_tables.disasters = [("row",)] * 6
        disaster_tables.famine = [["rural"] for _ in range(11)]
        disaster_tables.plague = [["plain"] for _ in range(11)]
        for index, current_phase in enumerate(_CHARACTERIZATION_PHASES):
            if current_phase == "campaign":
                _set_characterization_campaign_commands(game)
            orders_before_clear = ()
            original_advance_turn = game.advance_turn

            def capture_orders_then_advance(
                advance_turn: Callable[[], None] = original_advance_turn,
            ) -> None:
                nonlocal orders_before_clear
                orders_before_clear = _commands_snapshot(game)
                advance_turn()

            with patch.object(
                game,
                "advance_turn",
                side_effect=capture_orders_then_advance,
            ):
                GameEngine(game, rng=Random(100 + index)).run()
            if current_phase == phase:
                return _characterization_snapshot(game, orders_before_clear)
    raise ValueError(f"Fase de caracterización desconocida: {phase}")


def _run_characterization_until(
    phase: str,
    rule_overrides: Mapping[str, bool] | None = None,
) -> dict[str, object]:
    return _run_characterization_game_until(
        _characterization_game(rule_overrides),
        phase,
    )


def _expected_characterization_player(
    player_id: str,
    discord_id: int,
    power: str | None,
    controlled_locations: tuple[str, ...],
    home_countries: tuple[str, ...],
    *,
    armies: tuple[str, ...] = (),
    fleets: tuple[str, ...] = (),
    garrisons: tuple[str, ...] = (),
    ass_counters: tuple[str, ...] = (),
    ducats: int = 0,
) -> dict[str, object]:
    return {
        "player_id": player_id,
        "discord_id": discord_id,
        "power": power,
        "controlled_locations": controlled_locations,
        "home_countries": home_countries,
        "armies": armies,
        "fleets": fleets,
        "garrisons": garrisons,
        "ass_counters": ass_counters,
        "ducats": ducats,
        "rebelled_provinces": (),
        "rebelled_cities": (),
        "commands": (),
    }


def _expected_characterization_snapshot(
    turn_number: int,
    famine: tuple[str, ...],
    players: tuple[dict[str, object], ...],
    events: tuple[tuple[str, str], ...],
    orders_before_clear: tuple[
        tuple[str, tuple[tuple[str, str, str | None], ...]], ...
    ],
    *,
    rules: tuple[tuple[str, bool], ...],
    independent_garrisons: tuple[str, ...] = ("citad",),
) -> dict[str, object]:
    return {
        "turn_number": turn_number,
        "rules": rules,
        "famine": famine,
        "independent_garrisons": independent_garrisons,
        "besieges": (),
        "orders_before_clear": orders_before_clear,
        "players": players,
        "events": events,
    }


_ACTIVE_RULES_SNAPSHOT = (
    ("fortress_active", True),
    ("assassinations_active", True),
    ("famine_active", True),
    ("first_turn_famine", True),
    ("plague_active", True),
)
_INACTIVE_RULES_SNAPSHOTS = {
    "fortress_active": (
        ("fortress_active", False),
        ("assassinations_active", True),
        ("famine_active", True),
        ("first_turn_famine", True),
        ("plague_active", True),
    ),
    "assassinations_active": (
        ("fortress_active", True),
        ("assassinations_active", False),
        ("famine_active", True),
        ("first_turn_famine", True),
        ("plague_active", True),
    ),
    "famine_active": (
        ("fortress_active", True),
        ("assassinations_active", True),
        ("famine_active", False),
        ("first_turn_famine", True),
        ("plague_active", True),
    ),
    "first_turn_famine": (
        ("fortress_active", True),
        ("assassinations_active", True),
        ("famine_active", True),
        ("first_turn_famine", False),
        ("plague_active", True),
    ),
    "plague_active": (
        ("fortress_active", True),
        ("assassinations_active", True),
        ("famine_active", True),
        ("first_turn_famine", True),
        ("plague_active", False),
    ),
}

_ACTIVE_MILITARY_JSON = (
    '{"broken_convoys":[],"cancelled_orders":[],"dislodgements":[],'
    '"outcomes":[[["P1","A","plain"],"A","plain",false],'
    '[["P1","F","port"],"F","port",false],'
    '[["P2","A","keep"],"G","keep",false],'
    '[["P2","A","rural"],"A","rural",false],'
    '[["P2","G","fort"],"G","fort",false],'
    '[[null,"G","citad"],"G","citad",false]],'
    '"rebellions":[],"sieges":[]}'
)
_INACTIVE_FORTRESS_MILITARY_JSON = (
    '{"broken_convoys":[],"cancelled_orders":[],"dislodgements":[],'
    '"outcomes":[[["P1","A","plain"],"A","plain",false],'
    '[["P1","F","port"],"F","port",false],'
    '[["P2","A","keep"],"A","keep",false],'
    '[["P2","A","rural"],"A","rural",false],'
    '[["P2","G","fort"],"G","fort",false],'
    '[[null,"G","citad"],"G","citad",false]],'
    '"rebellions":[],"sieges":[]}'
)
_ACTIVE_CAMPAIGN_EVENTS = (
    ("military_resolution", _ACTIVE_MILITARY_JSON),
    ("famine_attrition", '{"player":"P2","units":["A rural"]}'),
    ("start_season", '{"season":2,"year":1454}'),
    ("famine_end", '{"provinces":["rural"]}'),
    ("plague_spawn", '{"provinces":["plain"],"severity_roll":1}'),
    ("plague_death", '{"player":"P1","units":["A plain"]}'),
)
_STARTUP_ORDERS = (("P1", ()), ("P2", ()))
_MAINTENANCE_ORDERS = (
    ("P1", (("A plain", "M", None), ("F port", "M", None))),
    (
        "P2",
        (
            ("A keep", "M", None),
            ("A rural", "M", None),
            ("G fort", "M", None),
        ),
    ),
)
_CAMPAIGN_ORDERS = (
    ("P1", (("A plain", "H", None), ("F port", "H", None))),
    (
        "P2",
        (
            ("A keep", "C", "G"),
            ("A rural", "H", None),
            ("G fort", "H", None),
        ),
    ),
)

_EXPECTED_ACTIVE_RULE_SNAPSHOTS = {
    "startup": _expected_characterization_snapshot(
        1,
        ("rural",),
        (
            _expected_characterization_player(
                "P1",
                101,
                "J",
                ("port", "plain"),
                ("J",),
                armies=("plain",),
                fleets=("port",),
                ass_counters=("H",),
                ducats=6,
            ),
            _expected_characterization_player(
                "P2",
                202,
                "H",
                ("fort", "keep", "rural"),
                ("H",),
                armies=("keep", "rural"),
                garrisons=("fort",),
                ass_counters=("J",),
                ducats=9,
            ),
        ),
        (
            ("start_game", '{"scenario":"rules"}'),
            (
                "start_game_power_assigned",
                '{"discord_id":101,"player_id":"P1","power_id":"J"}',
            ),
            (
                "start_game_power_assigned",
                '{"discord_id":202,"player_id":"P2","power_id":"H"}',
            ),
            (
                "famine_spawn",
                '{"provinces":["rural"],"severity_roll":1}',
            ),
            (
                "income_collected",
                '{"cities":["port"],"city_income":4,"player":"P1",'
                '"province_income":2,"provinces":["plain","port"],'
                '"total_income":6,"variable_income":[]}',
            ),
            (
                "income_collected",
                '{"cities":["fort"],"city_income":7,"player":"P2",'
                '"province_income":2,"provinces":["fort","keep"],'
                '"total_income":9,"variable_income":[]}',
            ),
        ),
        _STARTUP_ORDERS,
        rules=_ACTIVE_RULES_SNAPSHOT,
    ),
    "maintenance": _expected_characterization_snapshot(
        2,
        ("rural",),
        (
            _expected_characterization_player(
                "P1",
                101,
                "J",
                ("port", "plain"),
                ("J",),
                armies=("plain",),
                fleets=("port",),
                ass_counters=("H",),
            ),
            _expected_characterization_player(
                "P2",
                202,
                "H",
                ("fort", "keep", "rural"),
                ("H",),
                armies=("keep", "rural"),
                garrisons=("fort",),
                ass_counters=("J",),
            ),
        ),
        (
            (
                "maintenance_order_resolved",
                '{"actor":"A plain","cost":3,"order":"M","player":"P1",'
                '"result":"maintained","target":null}',
            ),
            (
                "maintenance_order_resolved",
                '{"actor":"F port","cost":3,"order":"M","player":"P1",'
                '"result":"maintained","target":null}',
            ),
            (
                "maintenance_summary",
                '{"expenses":6,"initial_ducats":6,"player":"P1","remaining_ducats":0}',
            ),
            (
                "maintenance_order_resolved",
                '{"actor":"A keep","cost":3,"order":"M","player":"P2",'
                '"result":"maintained","target":null}',
            ),
            (
                "maintenance_order_resolved",
                '{"actor":"A rural","cost":3,"order":"M","player":"P2",'
                '"result":"maintained","target":null}',
            ),
            (
                "maintenance_order_resolved",
                '{"actor":"G fort","cost":3,"order":"M","player":"P2",'
                '"result":"maintained","target":null}',
            ),
            (
                "maintenance_summary",
                '{"expenses":9,"initial_ducats":9,"player":"P2","remaining_ducats":0}',
            ),
        ),
        _MAINTENANCE_ORDERS,
        rules=_ACTIVE_RULES_SNAPSHOT,
    ),
    "campaign": _expected_characterization_snapshot(
        3,
        (),
        (
            _expected_characterization_player(
                "P1",
                101,
                "J",
                ("port", "plain"),
                ("J",),
                fleets=("port",),
                ass_counters=("H",),
            ),
            _expected_characterization_player(
                "P2",
                202,
                "H",
                ("fort", "keep", "rural"),
                ("H",),
                garrisons=("fort", "keep"),
                ass_counters=("J",),
            ),
        ),
        _ACTIVE_CAMPAIGN_EVENTS,
        _CAMPAIGN_ORDERS,
        rules=_ACTIVE_RULES_SNAPSHOT,
    ),
}

_EXPECTED_INACTIVE_RULE_SNAPSHOTS = {
    "fortress_active": _expected_characterization_snapshot(
        3,
        (),
        (
            _expected_characterization_player(
                "P1",
                101,
                "J",
                ("port", "plain"),
                ("J",),
                fleets=("port",),
                ass_counters=("H",),
            ),
            _expected_characterization_player(
                "P2",
                202,
                "H",
                ("fort", "keep", "rural"),
                ("H",),
                armies=("keep",),
                garrisons=("fort",),
                ass_counters=("J",),
            ),
        ),
        (
            ("military_resolution", _INACTIVE_FORTRESS_MILITARY_JSON),
            ("famine_attrition", '{"player":"P2","units":["A rural"]}'),
            ("start_season", '{"season":2,"year":1454}'),
            ("famine_end", '{"provinces":["rural"]}'),
            ("plague_spawn", '{"provinces":["plain"],"severity_roll":1}'),
            ("plague_death", '{"player":"P1","units":["A plain"]}'),
        ),
        _CAMPAIGN_ORDERS,
        rules=_INACTIVE_RULES_SNAPSHOTS["fortress_active"],
    ),
    "assassinations_active": _expected_characterization_snapshot(
        3,
        (),
        (
            _expected_characterization_player(
                "P1",
                101,
                "J",
                ("port", "plain"),
                ("J",),
                fleets=("port",),
            ),
            _expected_characterization_player(
                "P2",
                202,
                "H",
                ("fort", "keep", "rural"),
                ("H",),
                garrisons=("fort", "keep"),
            ),
        ),
        _ACTIVE_CAMPAIGN_EVENTS,
        _CAMPAIGN_ORDERS,
        rules=_INACTIVE_RULES_SNAPSHOTS["assassinations_active"],
    ),
    "famine_active": _expected_characterization_snapshot(
        3,
        (),
        (
            _expected_characterization_player(
                "P1",
                101,
                "J",
                ("port", "plain"),
                ("J",),
                fleets=("port",),
                ass_counters=("H",),
            ),
            _expected_characterization_player(
                "P2",
                202,
                "H",
                ("fort", "keep", "rural"),
                ("H",),
                armies=("rural",),
                garrisons=("fort", "keep"),
                ass_counters=("J",),
                ducats=1,
            ),
        ),
        (
            ("military_resolution", _ACTIVE_MILITARY_JSON),
            ("start_season", '{"season":2,"year":1454}'),
            ("plague_spawn", '{"provinces":["plain"],"severity_roll":1}'),
            ("plague_death", '{"player":"P1","units":["A plain"]}'),
        ),
        _CAMPAIGN_ORDERS,
        rules=_INACTIVE_RULES_SNAPSHOTS["famine_active"],
    ),
    "first_turn_famine": _expected_characterization_snapshot(
        3,
        (),
        (
            _expected_characterization_player(
                "P1",
                101,
                "J",
                ("port", "plain"),
                ("J",),
                fleets=("port",),
                ass_counters=("H",),
            ),
            _expected_characterization_player(
                "P2",
                202,
                "H",
                ("fort", "keep", "rural"),
                ("H",),
                armies=("rural",),
                garrisons=("fort", "keep"),
                ass_counters=("J",),
                ducats=1,
            ),
        ),
        (
            ("military_resolution", _ACTIVE_MILITARY_JSON),
            ("start_season", '{"season":2,"year":1454}'),
            ("plague_spawn", '{"provinces":["plain"],"severity_roll":1}'),
            ("plague_death", '{"player":"P1","units":["A plain"]}'),
        ),
        _CAMPAIGN_ORDERS,
        rules=_INACTIVE_RULES_SNAPSHOTS["first_turn_famine"],
    ),
    "plague_active": _expected_characterization_snapshot(
        3,
        (),
        (
            _expected_characterization_player(
                "P1",
                101,
                "J",
                ("port", "plain"),
                ("J",),
                armies=("plain",),
                fleets=("port",),
                ass_counters=("H",),
            ),
            _expected_characterization_player(
                "P2",
                202,
                "H",
                ("fort", "keep", "rural"),
                ("H",),
                garrisons=("fort", "keep"),
                ass_counters=("J",),
            ),
        ),
        (
            ("military_resolution", _ACTIVE_MILITARY_JSON),
            ("famine_attrition", '{"player":"P2","units":["A rural"]}'),
            ("start_season", '{"season":2,"year":1454}'),
            ("famine_end", '{"provinces":["rural"]}'),
        ),
        _CAMPAIGN_ORDERS,
        rules=_INACTIVE_RULES_SNAPSHOTS["plague_active"],
    ),
}

_INITIAL_CHARACTERIZATION_PLAYERS = (
    _expected_characterization_player("P1", 101, None, (), ()),
    _expected_characterization_player("P2", 202, None, (), ()),
)
_EXPECTED_INITIAL_RULE_SNAPSHOTS = {
    "fortress_active": _expected_characterization_snapshot(
        0,
        (),
        _INITIAL_CHARACTERIZATION_PLAYERS,
        (),
        _STARTUP_ORDERS,
        rules=_INACTIVE_RULES_SNAPSHOTS["fortress_active"],
        independent_garrisons=(),
    ),
    "assassinations_active": _expected_characterization_snapshot(
        0,
        (),
        _INITIAL_CHARACTERIZATION_PLAYERS,
        (),
        _STARTUP_ORDERS,
        rules=_INACTIVE_RULES_SNAPSHOTS["assassinations_active"],
        independent_garrisons=(),
    ),
    "famine_active": _expected_characterization_snapshot(
        0,
        (),
        _INITIAL_CHARACTERIZATION_PLAYERS,
        (),
        _STARTUP_ORDERS,
        rules=_INACTIVE_RULES_SNAPSHOTS["famine_active"],
        independent_garrisons=(),
    ),
    "first_turn_famine": _expected_characterization_snapshot(
        0,
        (),
        _INITIAL_CHARACTERIZATION_PLAYERS,
        (),
        _STARTUP_ORDERS,
        rules=_INACTIVE_RULES_SNAPSHOTS["first_turn_famine"],
        independent_garrisons=(),
    ),
    "plague_active": _expected_characterization_snapshot(
        0,
        (),
        _INITIAL_CHARACTERIZATION_PLAYERS,
        (),
        _STARTUP_ORDERS,
        rules=_INACTIVE_RULES_SNAPSHOTS["plague_active"],
        independent_garrisons=(),
    ),
}

_FORBIDDEN_EVENT_TYPES_BY_RULE = {
    "fortress_active": frozenset({"rebellion_city"}),
    "assassinations_active": frozenset(),
    "famine_active": frozenset(
        {"famine_spawn", "famine_relief", "famine_attrition", "famine_end"}
    ),
    "first_turn_famine": frozenset({"famine_spawn", "famine_attrition", "famine_end"}),
    "plague_active": frozenset({"plague_spawn", "plague_death"}),
}


@pytest.mark.parametrize("phase", _CHARACTERIZATION_PHASES)
def test_active_rule_characterizations_match_exact_versioned_snapshots(
    phase: str,
) -> None:
    assert _run_characterization_until(phase) == _EXPECTED_ACTIVE_RULE_SNAPSHOTS[phase]


@pytest.mark.parametrize("phase", _CHARACTERIZATION_PHASES)
def test_rule_matrix_reuses_unchanged_active_characterizations(phase: str) -> None:
    assert _run_characterization_until(phase) == _EXPECTED_ACTIVE_RULE_SNAPSHOTS[phase]


@pytest.mark.parametrize("rule_name", tuple(_ACTIVE_RULE_VALUES))
def test_each_inactive_rule_has_exact_integrated_state_and_event_order(
    rule_name: str,
) -> None:
    game = _characterization_game({rule_name: False})
    before = _characterization_snapshot(game, _commands_snapshot(game))
    actual = _run_characterization_game_until(game, "campaign")
    expected = _EXPECTED_INACTIVE_RULE_SNAPSHOTS[rule_name]

    assert before == _EXPECTED_INITIAL_RULE_SNAPSHOTS[rule_name]
    assert actual == expected

    actual_event_types = tuple(event_type for event_type, _ in actual["events"])
    expected_event_types = tuple(event_type for event_type, _ in expected["events"])
    forbidden = _FORBIDDEN_EVENT_TYPES_BY_RULE[rule_name]
    active_event_types = tuple(
        event_type
        for event_type, _ in _EXPECTED_ACTIVE_RULE_SNAPSHOTS["campaign"]["events"]
    )

    assert actual_event_types == expected_event_types
    assert forbidden.isdisjoint(actual_event_types)
    assert (
        tuple(
            event_type
            for event_type in active_event_types
            if event_type not in forbidden
        )
        == actual_event_types
    )


def _real_engine_game() -> Game:
    scenario = Scenario.load_scenarios()["Be"]
    game = Game(
        name="integrated-turn-events",
        scenario_id="Be",
        scenario=scenario,
        map=Map.load_map(exclude_ids=scenario.excluded_locations),
    )
    game.players = [
        Player(game, f"P{index + 1}", discord_id=10_000 + index)
        for index in range(len(scenario.powers))
    ]
    return game


def _payload_strings(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, Mapping):
        return [item for nested in value.values() for item in _payload_strings(nested)]
    if isinstance(value, tuple):
        return [item for nested in value for item in _payload_strings(nested)]
    return []


@pytest.mark.parametrize(
    ("turn_index", "phase"),
    [(0, "startup"), (1, "maintenance"), (2, "campaign")],
)
def test_real_managers_produce_only_reconstructable_domain_events(
    turn_index: int, phase: str
) -> None:
    game = _real_engine_game()

    with (
        patch(
            "machiavelli.engine.core.DisastersManager",
            side_effect=lambda active_game: RealDisastersManager(
                active_game, Random(200)
            ),
        ),
        patch(
            "machiavelli.engine.core.IncomeManager",
            side_effect=lambda active_game: RealIncomeManager(active_game, Random(300)),
        ),
    ):
        for index in range(turn_index + 1):
            GameEngine(game, rng=Random(100 + index)).run()

    events = game.turn_events
    rebuilt = [TurnEvent(type=event.type, data=event.data) for event in events]
    types = [event.type for event in events]

    assert events
    assert rebuilt == events
    assert all(isinstance(event, TurnEvent) for event in events)
    assert all(event.type in EventType for event in events)
    assert not any(
        marker in value
        for event in events
        for value in _payload_strings(event.data)
        for marker in ("**", "__", "`", "<@", "@everyone", "@here", "\n")
    )

    if phase == "startup":
        assert types[0] is EventType.START_GAME
        assert types[1:7] == [EventType.START_GAME_POWER_ASSIGNED] * 6
        assert types[-6:] == [EventType.INCOME_COLLECTED] * 6
    elif phase == "maintenance":
        assert types.count(EventType.MAINTENANCE_SUMMARY) == 6
        assert types.count(EventType.MAINTENANCE_ORDER_RESOLVED) >= 6
        assert len(types) > len(set(types))
    else:
        assert types[0] is EventType.MILITARY_RESOLUTION
        assert EventType.START_SEASON in types


class TestGameEngineDislodgementBarrier(unittest.TestCase):
    """Verifica que la política de retiradas no escape del resolvedor militar."""

    def test_constructor_exposes_only_game_and_rng(self) -> None:
        self.assertEqual(
            list(inspect.signature(GameEngine.__init__).parameters),
            ["self", "game", "rng"],
        )

    @patch("machiavelli.engine.core.ControlManager")
    @patch("machiavelli.engine.core.MilitaryResolver")
    @patch("machiavelli.engine.core.AssassinationResolver")
    @patch("machiavelli.engine.core.BribeResolver")
    @patch("machiavelli.engine.core.RebellionManager")
    @patch("machiavelli.engine.core.DisastersManager")
    @patch("machiavelli.engine.core.ExpenditureProcessor")
    def test_military_runs_without_external_policy_and_control_observes_commit(
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
        observed_by_control = []

        def finish_military() -> None:
            """Simula el commit militar antes de que se ejecute control."""
            player.armies = ["resolved"]

        def capture_control() -> None:
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

        mock_military_cls.return_value.run.assert_called_once_with()
        self.assertEqual(observed_by_control, [("resolved",)])
        self.assertEqual(
            order.mock_calls,
            [
                call.military(),
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
        error = MilitaryResolutionError("stop")
        mock_military_cls.return_value.run.side_effect = error
        engine = GameEngine(game)

        with self.assertRaises(MilitaryResolutionError) as caught:
            engine.run_campaign()

        self.assertIs(caught.exception, error)
        mock_military_cls.return_value.run.assert_called_once_with()
        mock_disasters_cls.return_value.resolve_famine_attrition.assert_not_called()
        mock_control_cls.return_value.run.assert_not_called()
        mock_disasters_cls.return_value.clear_famine.assert_not_called()
        mock_disasters_cls.return_value.spawn_plague.assert_not_called()


def _rules_game(
    turn_number: int,
    *,
    assassinations_active: bool = True,
    famine_active: bool = True,
    first_turn_famine: bool = True,
    plague_active: bool = True,
) -> Mock:
    game = Mock()
    game.turn_number = turn_number
    game.scenario.rules.assassinations_active = assassinations_active
    game.scenario.rules.famine_active = famine_active
    game.scenario.rules.first_turn_famine = first_turn_famine
    game.scenario.rules.plague_active = plague_active
    game.require_scenario.return_value = game.scenario
    return game


@pytest.mark.parametrize(
    ("famine_active", "first_turn_famine", "spawned"),
    [
        (False, False, False),
        (False, True, False),
        (True, False, False),
        (True, True, True),
    ],
)
def test_startup_famine_requires_both_rules(
    famine_active: bool, first_turn_famine: bool, spawned: bool
) -> None:
    game = _rules_game(
        0,
        famine_active=famine_active,
        first_turn_famine=first_turn_famine,
    )
    with (
        patch("machiavelli.engine.core.SetupManager") as setup,
        patch("machiavelli.engine.core.DisastersManager") as disasters,
        patch("machiavelli.engine.core.IncomeManager") as income,
    ):
        GameEngine(game).run_startup()

    setup.return_value.run.assert_called_once()
    income.return_value.run.assert_called_once()
    if spawned:
        disasters.return_value.spawn_famine.assert_called_once()
    else:
        disasters.assert_not_called()


def test_campaign_omits_disabled_assassinations_and_all_disasters() -> None:
    game = _rules_game(
        4,
        assassinations_active=False,
        famine_active=False,
        plague_active=False,
    )
    with (
        patch("machiavelli.engine.core.ExpenditureProcessor"),
        patch("machiavelli.engine.core.DisastersManager") as disasters,
        patch("machiavelli.engine.core.RebellionManager"),
        patch("machiavelli.engine.core.BribeResolver"),
        patch("machiavelli.engine.core.AssassinationResolver") as assassinations,
        patch("machiavelli.engine.core.MilitaryResolver"),
        patch("machiavelli.engine.core.ControlManager"),
        patch("machiavelli.engine.core.IncomeManager") as income,
    ):
        GameEngine(game).run_campaign()

    assassinations.assert_not_called()
    disasters.assert_not_called()
    income.return_value.run.assert_called_once()


@pytest.mark.parametrize(
    ("famine_active", "plague_active"),
    [(False, True), (True, False)],
)
def test_summer_calls_only_enabled_disaster_branches(
    famine_active: bool, plague_active: bool
) -> None:
    game = _rules_game(
        2,
        famine_active=famine_active,
        plague_active=plague_active,
    )
    with (
        patch("machiavelli.engine.core.ExpenditureProcessor"),
        patch("machiavelli.engine.core.DisastersManager") as disasters,
        patch("machiavelli.engine.core.RebellionManager"),
        patch("machiavelli.engine.core.BribeResolver"),
        patch("machiavelli.engine.core.AssassinationResolver"),
        patch("machiavelli.engine.core.MilitaryResolver"),
        patch("machiavelli.engine.core.ControlManager"),
    ):
        GameEngine(game).run_campaign()

    manager = disasters.return_value
    if famine_active:
        manager.process_famine_relief_expenses.assert_called_once()
        manager.resolve_famine_attrition.assert_called_once()
        manager.clear_famine.assert_called_once()
    else:
        manager.process_famine_relief_expenses.assert_not_called()
        manager.resolve_famine_attrition.assert_not_called()
        manager.clear_famine.assert_not_called()
    if plague_active:
        manager.spawn_plague.assert_called_once()
    else:
        manager.spawn_plague.assert_not_called()
