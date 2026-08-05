"""Tests for per-order maintenance events and summaries."""

from unittest.mock import Mock

import pytest

from machiavelli.engine.maintenance import MaintenanceResolver
from machiavelli.events import EventType
from machiavelli.game.command import Command
from machiavelli.game.game import Game
from machiavelli.game.player import Player


def _game(*, ducats: int = 12) -> tuple[Game, Player]:
    scenario = Mock()
    scenario.province_home_country.return_value = "F"
    game_map = Mock()
    game_map.provinces = {
        "flore": Mock(city="fortified", is_venice=False, has_port=True),
        "pisa": Mock(city="city", is_venice=False, has_port=True),
        "sienn": Mock(city="city", is_venice=False, has_port=False),
    }
    game = Game("maintenance", scenario=scenario, map=game_map)
    player = Player(
        game,
        "P1",
        controlled_locations=["flore", "pisa", "sienn"],
        home_countries=["F"],
        ducats=ducats,
    )
    game.players = [player]
    return game, player


def _events(game: Game, event_type: EventType):
    return [event for event in game.turn_events if event.type is event_type]


_MAINTENANCE_RESULT_CASES = [
    (
        "disbanded",
        "D",
        "A flore",
        3,
        (["flore"], [], []),
        None,
        [],
        0,
        ([], [], []),
    ),
    (
        "unit_not_found",
        "D",
        "A flore",
        3,
        ([], [], []),
        None,
        [],
        0,
        ([], [], []),
    ),
    (
        "maintained",
        "M",
        "A flore",
        3,
        (["flore"], [], []),
        None,
        [],
        3,
        (["flore"], [], []),
    ),
    (
        "disbanded_no_funds",
        "M",
        "A flore",
        0,
        (["flore"], [], []),
        None,
        [],
        0,
        ([], [], []),
    ),
    (
        "recruited",
        "R",
        "A flore",
        3,
        ([], [], []),
        None,
        [],
        3,
        (["flore"], [], []),
    ),
    (
        "recruitment_no_funds",
        "R",
        "A flore",
        0,
        ([], [], []),
        None,
        [],
        0,
        ([], [], []),
    ),
    (
        "invalid_home_or_control",
        "R",
        "A pisa",
        3,
        ([], [], []),
        ["flore", "sienn"],
        [],
        0,
        ([], [], []),
    ),
    (
        "space_occupied",
        "R",
        "A flore",
        3,
        (["flore"], [], []),
        None,
        [],
        0,
        (["flore"], [], []),
    ),
    (
        "port_required",
        "R",
        "F sienn",
        3,
        ([], [], []),
        None,
        [],
        0,
        ([], [], []),
    ),
    (
        "rebelled_city",
        "R",
        "G flore",
        3,
        ([], [], []),
        None,
        ["flore"],
        0,
        ([], [], []),
    ),
    (
        "fortified_city_required",
        "R",
        "G pisa",
        3,
        ([], [], []),
        None,
        [],
        0,
        ([], [], []),
    ),
]


@pytest.mark.parametrize(
    (
        "result",
        "order",
        "actor",
        "available",
        "initial_units",
        "controlled_locations",
        "rebelled_cities",
        "expected_cost",
        "expected_units",
    ),
    _MAINTENANCE_RESULT_CASES,
    ids=[case[0] for case in _MAINTENANCE_RESULT_CASES],
)
def test_every_maintenance_result_emits_one_exact_attempt(
    result: str,
    order: str,
    actor: str,
    available: int,
    initial_units: tuple[list[str], list[str], list[str]],
    controlled_locations: list[str] | None,
    rebelled_cities: list[str],
    expected_cost: int,
    expected_units: tuple[list[str], list[str], list[str]],
) -> None:
    assert {case[0] for case in _MAINTENANCE_RESULT_CASES} == {
        "disbanded",
        "unit_not_found",
        "maintained",
        "disbanded_no_funds",
        "recruited",
        "recruitment_no_funds",
        "invalid_home_or_control",
        "space_occupied",
        "port_required",
        "rebelled_city",
        "fortified_city_required",
    }
    game, player = _game()
    player.armies = list(initial_units[0])
    player.fleets = list(initial_units[1])
    player.garrisons = list(initial_units[2])
    if controlled_locations is not None:
        player.controlled_locations = controlled_locations
    player.rebelled_cities = rebelled_cities
    command = Command(game, player, actor, order, None)
    resolver = MaintenanceResolver(game)

    if order == "D":
        charged = resolver._disband(player, command)
    elif order == "M":
        charged = resolver._maintain(player, command, available)
    else:
        charged = resolver._recruit(player, command, available)

    assert charged == expected_cost
    assert (player.armies, player.fleets, player.garrisons) == expected_units
    assert len(game.turn_events) == 1
    event = game.turn_events[0]
    assert event.type is EventType.MAINTENANCE_ORDER_RESOLVED
    assert event.data["result"] == result
    assert event.data["cost"] == expected_cost
    assert event.data["actor"] == actor
    assert event.data["order"] == order


def test_default_maintenance_emits_one_attempt_per_unit_and_summary() -> None:
    game, player = _game(ducats=9)
    player.armies = ["flore"]
    player.fleets = ["pisa"]
    player.garrisons = ["flore"]

    MaintenanceResolver(game).run()

    attempts = _events(game, EventType.MAINTENANCE_ORDER_RESOLVED)
    assert [event.data["actor"] for event in attempts] == (
        ["A flore", "F pisa", "G flore"]
    )
    assert [event.data["result"] for event in attempts] == [
        "maintained",
        "maintained",
        "maintained",
    ]
    assert [event.data["cost"] for event in attempts] == [3, 3, 3]
    summary = _events(game, EventType.MAINTENANCE_SUMMARY)[0]
    assert dict(summary.data) == {
        "player": "P1",
        "initial_ducats": 9,
        "expenses": 9,
        "remaining_ducats": 0,
    }
    assert player.ducats == 0


def test_maintenance_without_funds_disbands_unit_and_records_zero_cost() -> None:
    game, player = _game(ducats=0)
    player.armies = ["flore"]

    MaintenanceResolver(game).run()

    attempt = _events(game, EventType.MAINTENANCE_ORDER_RESOLVED)[0]
    assert attempt.data["result"] == "disbanded_no_funds"
    assert attempt.data["cost"] == 0
    assert player.armies == []


def test_explicit_disband_and_missing_unit_each_emit_an_attempt() -> None:
    game, player = _game()
    player.armies = ["flore"]
    player.commands = [
        Command(game, player, "A flore", "D", None),
        Command(game, player, "F pisa", "D", None),
    ]

    MaintenanceResolver(game).run()

    attempts = _events(game, EventType.MAINTENANCE_ORDER_RESOLVED)
    assert [event.data["result"] for event in attempts] == [
        "disbanded",
        "unit_not_found",
    ]
    assert player.armies == []


def test_successful_recruitment_emits_cost_and_updates_units() -> None:
    game, player = _game(ducats=6)
    player.commands = [
        Command(game, player, "A flore", "R", None),
        Command(game, player, "F pisa", "R", None),
    ]

    MaintenanceResolver(game).run()

    attempts = _events(game, EventType.MAINTENANCE_ORDER_RESOLVED)
    assert [event.data["result"] for event in attempts] == ["recruited", "recruited"]
    assert player.armies == ["flore"]
    assert player.fleets == ["pisa"]
    assert player.ducats == 0


def test_recruitment_failures_use_closed_results_without_charging() -> None:
    game, player = _game(ducats=3)
    player.rebelled_cities = ["flore"]
    player.commands = [
        Command(game, player, "G flore", "R", None),
        Command(game, player, "F sienn", "R", None),
        Command(game, player, "G pisa", "R", None),
    ]

    MaintenanceResolver(game).run()

    attempts = _events(game, EventType.MAINTENANCE_ORDER_RESOLVED)
    assert [event.data["result"] for event in attempts] == [
        "rebelled_city",
        "port_required",
        "fortified_city_required",
    ]
    assert [event.data["cost"] for event in attempts] == [0, 0, 0]
    assert player.ducats == 3


def test_recruitment_after_spending_all_funds_reports_no_funds() -> None:
    game, player = _game(ducats=3)
    player.armies = ["flore"]
    player.commands = [
        Command(game, player, "A flore", "M", None),
        Command(game, player, "F pisa", "R", None),
    ]

    MaintenanceResolver(game).run()

    attempts = _events(game, EventType.MAINTENANCE_ORDER_RESOLVED)
    assert [event.data["result"] for event in attempts] == [
        "maintained",
        "recruitment_no_funds",
    ]
    assert player.ducats == 0
