"""Tests for famine and plague structured events."""

from unittest.mock import Mock, patch

import pytest

from machiavelli.engine.disasters import DisastersManager
from machiavelli.events import EventType
from machiavelli.game.command import Command
from machiavelli.game.game import Game
from machiavelli.game.player import Player
from machiavelli.game.scenario import Rules, Scenario, VictoryConditions


def _game() -> tuple[Game, Player]:
    game_map = Mock()
    game_map.provinces = {key: Mock() for key in ("flore", "pisa", "rome")}
    game = Game(
        "disasters",
        map=game_map,
        scenario=Scenario(
            name="rules",
            year=1454,
            victory_conditions=VictoryConditions(cities=1, home_countries=1),
            rules=Rules(),
        ),
    )
    player = Player(game, "P1", ducats=20)
    game.players = [player]
    return game, player


def test_famine_relief_emits_only_when_famine_is_removed() -> None:
    game, player = _game()
    game.famine = ["flore"]
    player.commands = [
        Command(game, player, "E A", "3", "flore"),
        Command(game, player, "E A", "3", "pisa"),
    ]

    with patch("machiavelli.engine.disasters.GameTables") as tables:
        tables.expenses = {"A": {"cost": 3}}
        DisastersManager(game).process_famine_relief_expenses()

    assert game.famine == []
    assert len(game.turn_events) == 1
    event = game.turn_events[0]
    assert event.type is EventType.FAMINE_RELIEF
    assert dict(event.data) == {"player": "P1", "province": "flore"}


@pytest.mark.parametrize(
    "event_type",
    [EventType.FAMINE_ATTRITION, EventType.PLAGUE_DEATH],
)
def test_disaster_deaths_emit_player_and_independent_events(
    event_type: EventType,
) -> None:
    game, player = _game()
    player.armies = ["flore"]
    player.fleets = ["pisa coast"]
    player.garrisons = ["rome"]
    game.independent_garrisons = ["pisa"]

    DisastersManager(game)._apply_disaster_deaths(event_type, ["flore", "pisa"])

    assert player.armies == []
    assert player.fleets == []
    assert player.garrisons == ["rome"]
    assert game.independent_garrisons == []
    assert [event.type for event in game.turn_events] == [event_type, event_type]
    assert dict(game.turn_events[0].data) == {
        "player": "P1",
        "units": ("A flore", "F pisa coast"),
    }
    assert dict(game.turn_events[1].data) == {
        "player": None,
        "units": ("G pisa",),
    }


def test_disaster_deaths_omit_empty_events_and_reject_unrelated_type() -> None:
    game, _ = _game()
    manager = DisastersManager(game)

    manager._apply_disaster_deaths(EventType.FAMINE_ATTRITION, [])
    manager._apply_disaster_deaths(EventType.EXPENSE, ["flore"])

    assert game.turn_events == []


def test_clear_famine_emits_final_provinces_then_clears_state() -> None:
    game, _ = _game()
    game.famine = ["flore", "pisa"]

    DisastersManager(game).clear_famine()

    assert game.famine == []
    event = game.turn_events[0]
    assert event.type is EventType.FAMINE_END
    assert event.data["provinces"] == ("flore", "pisa")


@pytest.mark.parametrize(
    ("event_type", "severity_roll", "province"),
    [
        (EventType.FAMINE_SPAWN, 1, "flore"),
        (EventType.FAMINE_SPAWN, 6, "pisa"),
        (EventType.PLAGUE_SPAWN, 1, "rome"),
        (EventType.PLAGUE_SPAWN, 6, "flore"),
    ],
)
def test_spawn_records_boundary_severity_and_exact_payload(
    event_type: EventType,
    severity_roll: int,
    province: str,
) -> None:
    game, _ = _game()
    rng = Mock()
    rng.randint.side_effect = [severity_roll, 0, 0]

    with patch("machiavelli.engine.disasters.GameTables") as tables:
        tables.disasters = [("row",)] * 6
        tables.famine = [[province] for _ in range(11)]
        tables.plague = [[province] for _ in range(11)]
        result = DisastersManager(game, rng)._spawn_disaster(event_type)

    assert result == [province]
    assert len(game.turn_events) == 1
    event = game.turn_events[0]
    assert event.type is event_type
    assert dict(event.data) == {
        "severity_roll": severity_roll,
        "provinces": (province,),
    }


@patch("machiavelli.engine.disasters.GameTables")
def test_spawn_filters_unknown_and_duplicate_provinces(tables: Mock) -> None:
    game, _ = _game()
    tables.disasters = [("both",)] * 6
    tables.famine = [["flore", "unknown"] + ["flore"] * 9 for _ in range(11)]
    tables.plague = tables.famine
    rng = Mock()
    rng.randint.side_effect = [1, 0, 0, 0, 0]

    result = DisastersManager(game, rng)._spawn_disaster(EventType.FAMINE_SPAWN)

    assert result == ["flore"]
    assert game.turn_events[0].data["provinces"] == ("flore",)


@patch("machiavelli.engine.disasters.GameTables")
def test_empty_spawn_emits_no_event(tables: Mock) -> None:
    game, _ = _game()
    tables.disasters = [("row",)] * 6
    tables.famine = [[None] for _ in range(11)]
    tables.plague = tables.famine
    rng = Mock()
    rng.randint.side_effect = [1, 0, 0]

    result = DisastersManager(game, rng)._spawn_disaster(EventType.PLAGUE_SPAWN)

    assert result == []
    assert game.turn_events == []


def test_spawn_plague_applies_deaths_after_spawn() -> None:
    game, _ = _game()
    manager = DisastersManager(game)
    manager._spawn_disaster = Mock(return_value=["rome"])  # type: ignore[method-assign]
    manager._apply_disaster_deaths = Mock()  # type: ignore[method-assign]

    manager.spawn_plague()

    manager._spawn_disaster.assert_called_once_with(event_type=EventType.PLAGUE_SPAWN)
    manager._apply_disaster_deaths.assert_called_once_with(
        event_type=EventType.PLAGUE_DEATH, provinces=["rome"]
    )


def test_inactive_famine_makes_every_public_famine_operation_a_noop() -> None:
    game, player = _game()
    game.scenario.rules.famine_active = False
    game.scenario.rules.first_turn_famine = True
    game.famine = ["flore"]
    player.armies = ["flore"]
    player.commands = [Command(game, player, "E A", "3", "flore")]
    manager = DisastersManager(game)
    manager._spawn_disaster = Mock(return_value=["pisa"])  # type: ignore[method-assign]
    manager._apply_disaster_deaths = Mock()  # type: ignore[method-assign]

    manager.process_famine_relief_expenses()
    manager.resolve_famine_attrition()
    manager.clear_famine()
    manager.spawn_famine()

    assert game.famine == ["flore"]
    assert player.armies == ["flore"]
    assert game.turn_events == []
    manager._spawn_disaster.assert_not_called()
    manager._apply_disaster_deaths.assert_not_called()


def test_inactive_plague_skips_spawn_deaths_and_events() -> None:
    game, player = _game()
    game.scenario.rules.plague_active = False
    player.armies = ["rome"]
    manager = DisastersManager(game)
    manager._spawn_disaster = Mock(return_value=["rome"])  # type: ignore[method-assign]
    manager._apply_disaster_deaths = Mock()  # type: ignore[method-assign]

    manager.spawn_plague()

    assert player.armies == ["rome"]
    assert game.turn_events == []
    manager._spawn_disaster.assert_not_called()
    manager._apply_disaster_deaths.assert_not_called()
