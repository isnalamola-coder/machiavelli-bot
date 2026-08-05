# tests/machiavelli/engine/test_setup.py
from random import Random
from unittest.mock import Mock

import pytest

from machiavelli.engine.exceptions import (
    DuplicatePlayerError,
    GameAlreadyStartedError,
    InvalidPlayerCountError,
    ScenarioNotSelectedError,
)
from machiavelli.engine.setup import SetupManager
from machiavelli.events import EventType, TurnEvent

from .helpers import create_mock_game, create_mock_player


def test_setup_raises_scenario_not_selected():
    game = create_mock_game(turn_number=0, scenario_id=None, scenario=None)
    manager = SetupManager(game)

    with pytest.raises(ScenarioNotSelectedError):
        manager.run()


def test_setup_raises_duplicate_player_id():
    p1 = create_mock_player("p1", discord_id=100)
    p2 = create_mock_player("p1", discord_id=200)
    game = create_mock_game(turn_number=0, players=[p1, p2])

    manager = SetupManager(game)

    with pytest.raises(DuplicatePlayerError) as exc_info:
        manager.run()

    assert exc_info.value.player_id == "p1"


def test_setup_raises_duplicate_discord_id():
    p1 = create_mock_player("p1", discord_id=100)
    p2 = create_mock_player("p2", discord_id=100)
    game = create_mock_game(turn_number=0, players=[p1, p2])

    manager = SetupManager(game)

    with pytest.raises(DuplicatePlayerError) as exc_info:
        manager.run()

    assert exc_info.value.discord_id == 100


def test_setup_raises_invalid_player_count():
    p1 = create_mock_player("p1", discord_id=100)
    p2 = create_mock_player("p2", discord_id=200)
    power = Mock()
    scenario = Mock(powers={"M": power, "V": power, "L": power})
    game = create_mock_game(turn_number=0, players=[p1, p2], scenario=scenario)

    manager = SetupManager(game)

    with pytest.raises(InvalidPlayerCountError) as exc_info:
        manager.run()

    assert exc_info.value.current == 2
    assert exc_info.value.scenario_players == 3


def test_setup_raises_already_started():
    game = create_mock_game(turn_number=1)

    manager = SetupManager(game)

    with pytest.raises(GameAlreadyStartedError):
        manager.run()


def _run_reproducible_setup() -> tuple[list[TurnEvent], list[Mock]]:
    players = [
        create_mock_player("p1", discord_id=100),
        create_mock_player("p2", discord_id=200),
    ]
    powers = {
        "V": Mock(controlled_provinces=["venic"]),
        "M": Mock(controlled_provinces=["milan"]),
    }
    game = create_mock_game(
        turn_number=0,
        players=players,
        scenario=Mock(powers=powers),
        scenario_id="scenario_1",
    )
    game.map = Mock(
        provinces={
            "venic": Mock(city="fortified"),
            "milan": Mock(city="fortified"),
            "flore": Mock(city="fortified"),
        }
    )

    SetupManager(game, rng=Random(42)).run()
    return [item.args[0] for item in game.add_event.call_args_list], players


def test_setup_emits_exact_reproducible_structured_history():
    first_events, first_players = _run_reproducible_setup()
    second_events, _ = _run_reproducible_setup()

    assert first_events == second_events
    assert first_events[0] == TurnEvent(
        EventType.START_GAME, {"scenario": "scenario_1"}
    )
    assert [event.type for event in first_events] == [
        EventType.START_GAME,
        EventType.START_GAME_POWER_ASSIGNED,
        EventType.START_GAME_POWER_ASSIGNED,
    ]
    assert all(isinstance(event, TurnEvent) for event in first_events)

    for player, event in zip(first_players, first_events[1:], strict=True):
        assigned_power = player.assign_power_from_scenario.call_args.args[0]
        assert event.data == {
            "player_id": player.player_id,
            "discord_id": player.discord_id,
            "power_id": assigned_power,
        }


def test_setup_successful_run():
    p1 = create_mock_player("p1", discord_id=100)
    p2 = create_mock_player("p2", discord_id=200)

    power_venice = Mock(controlled_provinces=["venic"])
    power_milan = Mock(controlled_provinces=["milan"])

    scenario = Mock(powers={"V": power_venice, "M": power_milan})

    prov_venice = Mock(city="fortified")
    prov_milan = Mock(city="fortified")
    prov_florence = Mock(city="fortified")

    map_obj = Mock(
        provinces={
            "venic": prov_venice,
            "milan": prov_milan,
            "flore": prov_florence,
        }
    )

    game = create_mock_game(
        turn_number=0,
        players=[p1, p2],
        scenario=scenario,
        scenario_id="scenario_1",
    )
    game.map = map_obj

    manager = SetupManager(game, rng=Random(42))
    manager.run()

    assert game.add_event.call_count == 3
    assert game.independent_garrisons == ["flore"]
    p1.assign_power_from_scenario.assert_called_once()
    p2.assign_power_from_scenario.assert_called_once()
