# tests/machiavelli/engine/test_setup.py
from random import Random
from unittest.mock import Mock

import pytest
from helpers import create_mock_game, create_mock_player

from machiavelli.engine.exceptions import (
    DuplicatePlayerError,
    GameAlreadyStartedError,
    InvalidPlayerCountError,
    ScenarioNotSelectedError,
)
from machiavelli.engine.setup import SetupManager


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
    p1.assign_power.assert_called_once()
    p2.assign_power.assert_called_once()
