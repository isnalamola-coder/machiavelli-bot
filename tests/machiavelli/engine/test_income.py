"""Tests for the aggregate income_collected event."""

from unittest.mock import Mock, patch

from machiavelli.engine.income import IncomeManager
from machiavelli.events import EventType, TurnEvent
from tests.machiavelli.engine.helpers import create_mock_game, create_mock_player


def _income_game() -> tuple[Mock, Mock]:
    player = create_mock_player("P1")
    player.ducats = 0
    scenario = Mock(
        variable_income_home_countries=["N"],
        variable_income_provinces=["rome"],
    )
    game = create_mock_game(players=[player], scenario=scenario)
    game.map.provinces = {
        "venic": Mock(city="fortified", major_city=2),
        "rome": Mock(city="fortified", major_city=2),
        "flore": Mock(city="fortified", major_city=1),
        "piomb": Mock(city="city", major_city=1),
        "sienn": Mock(city=None, major_city=None),
        "paler": Mock(city=None, major_city=None),
    }
    return game, player


def test_income_event_contains_fixed_sources_and_total() -> None:
    game, player = _income_game()
    player.controlled_locations = ["sienn", "paler", "flore"]
    player.armies = ["rome", "sienn"]
    player.fleets = ["UA", "paler"]
    player.garrisons = ["venic"]

    IncomeManager(game)._collect_player_income(player)

    event = game.add_event.call_args.args[0]
    assert isinstance(event, TurnEvent)
    assert event.type is EventType.INCOME_COLLECTED
    assert event.data["player"] == "P1"
    assert event.data["provinces"] == ("UA", "flore", "paler", "rome", "sienn")
    assert event.data["province_income"] == 5
    assert event.data["cities"] == ("flore", "venic")
    assert event.data["city_income"] == 3
    assert event.data["variable_income"] == ()
    assert event.data["total_income"] == 8
    assert player.ducats == 8


def test_income_excludes_famine_and_rebellion_but_keeps_garrison_city() -> None:
    game, player = _income_game()
    player.controlled_locations = ["sienn", "paler", "flore"]
    player.armies = ["rome", "sienn"]
    player.fleets = ["UA", "paler"]
    player.garrisons = ["venic"]
    game.famine = ["rome"]
    player.rebelled_provinces = ["venic"]
    player.rebelled_cities = ["flore"]

    IncomeManager(game)._collect_player_income(player)

    event = game.add_event.call_args.args[0]
    assert event.data["provinces"] == ("UA", "paler", "sienn")
    assert event.data["province_income"] == 3
    assert event.data["cities"] == ("venic",)
    assert event.data["city_income"] == 2
    assert event.data["total_income"] == 5
    assert player.ducats == 5


@patch("machiavelli.engine.income.GameTables")
def test_income_records_each_variable_source_roll_and_amount(mock_tables: Mock) -> None:
    game, player = _income_game()
    player.controlled_locations = ["rome"]
    player.home_countries = ["N"]
    mock_tables.variable_income = {
        "N": [1, 2, 3, 4, 5, 6],
        "rome": [11, 12, 13, 14, 15, 16],
    }
    rng = Mock()
    rng.randint.side_effect = [1, 6]

    IncomeManager(game, rng)._collect_player_income(player)

    event = game.add_event.call_args.args[0]
    assert tuple(dict(item) for item in event.data["variable_income"]) == (
        {"source_type": "home_country", "source": "N", "roll": 1, "amount": 1},
        {"source_type": "province", "source": "rome", "roll": 6, "amount": 16},
    )
    assert event.data["province_income"] == 1
    assert event.data["city_income"] == 2
    assert event.data["total_income"] == 20
    assert player.ducats == 20


def test_fortress_counts_as_province_but_never_as_income_city() -> None:
    game, player = _income_game()
    game.map.provinces["keep"] = Mock(city="fortress", major_city=4)
    player.controlled_locations = ["keep"]
    player.garrisons = ["keep"]

    IncomeManager(game)._collect_player_income(player)

    event = game.add_event.call_args.args[0]
    assert event.data["provinces"] == ("keep",)
    assert event.data["province_income"] == 1
    assert event.data["cities"] == ()
    assert event.data["city_income"] == 0
    assert event.data["total_income"] == 1
    assert player.ducats == 1


def test_run_emits_one_income_event_per_player_in_order() -> None:
    first = create_mock_player("P1")
    second = create_mock_player("P2")
    first.ducats = 0
    second.ducats = 0
    game = create_mock_game(
        players=[first, second],
        scenario=Mock(variable_income_home_countries=[], variable_income_provinces=[]),
    )
    game.map.provinces = {}

    IncomeManager(game).run()

    events = [call.args[0] for call in game.add_event.call_args_list]
    assert [event.type for event in events] == [
        EventType.INCOME_COLLECTED,
        EventType.INCOME_COLLECTED,
    ]
    assert [event.data["player"] for event in events] == ["P1", "P2"]
