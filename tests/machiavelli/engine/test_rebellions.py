"""Tests for structured rebellion events and expense routing."""

from unittest.mock import Mock, patch

import pytest

from machiavelli.engine.rebellions import RebellionManager
from machiavelli.events import EventType, TurnEvent


def _game() -> Mock:
    game = Mock()
    game.add_event = Mock()
    game.scenario.rules.fortress_active = True
    game.scenario.province_home_country.return_value = "M"
    game.map.provinces = {"pisa": Mock(city="fortified")}
    return game


@pytest.mark.parametrize(
    ("target", "kind"),
    [("pisa", "province"), ("flore", "city")],
)
def test_pacify_emits_affected_player_and_kind(target: str, kind: str) -> None:
    game = _game()
    owner = Mock(
        player_id="FLORENCE",
        rebelled_provinces=["pisa"],
        rebelled_cities=["flore"],
    )
    game.players = [owner]
    manager = RebellionManager(game)
    command = Mock(target=target)

    manager.expense_rebellion_pacify(command)

    collection_name = {
        "province": "rebelled_provinces",
        "city": "rebelled_cities",
    }[kind]
    assert target not in getattr(owner, collection_name)
    event = game.add_event.call_args.args[0]
    assert isinstance(event, TurnEvent)
    assert event.type is EventType.REBELLION_PACIFY
    assert dict(event.data) == {
        "player": "FLORENCE",
        "province": target,
        "kind": kind,
    }


def test_pacify_non_rebelled_target_emits_nothing() -> None:
    game = _game()
    game.players = [
        Mock(
            player_id="FLORENCE",
            rebelled_provinces=["pisa"],
            rebelled_cities=["flore"],
        )
    ]

    RebellionManager(game).expense_rebellion_pacify(Mock(target="rome"))

    game.add_event.assert_not_called()


@pytest.mark.parametrize(
    ("city", "fortress_active", "garrisons", "event_type", "kind_attr"),
    [
        ("fortified", True, [], EventType.REBELLION_CITY, "rebelled_cities"),
        (
            "fortified",
            True,
            ["pisa"],
            EventType.REBELLION_PROVINCE,
            "rebelled_provinces",
        ),
        ("fortress", True, [], EventType.REBELLION_CITY, "rebelled_cities"),
        ("fortress", False, [], EventType.REBELLION_PROVINCE, "rebelled_provinces"),
        (None, True, [], EventType.REBELLION_PROVINCE, "rebelled_provinces"),
    ],
)
def test_rebellion_kind_follows_city_and_garrison_rules(
    city: str | None,
    fortress_active: bool,
    garrisons: list[str],
    event_type: EventType,
    kind_attr: str,
) -> None:
    game = _game()
    game.scenario.rules.fortress_active = fortress_active
    game.map.provinces["pisa"].city = city
    owner = Mock(
        player_id="FLORENCE",
        rebelled_provinces=[],
        rebelled_cities=[],
        garrisons=garrisons,
    )

    RebellionManager(game)._do_rebellion(owner, "pisa")

    assert getattr(owner, kind_attr) == ["pisa"]
    event = game.add_event.call_args.args[0]
    assert event.type is event_type
    assert dict(event.data) == {"player": "FLORENCE", "province": "pisa"}


def test_existing_rebellion_is_not_duplicated() -> None:
    game = _game()
    owner = Mock(
        player_id="FLORENCE",
        rebelled_provinces=["pisa"],
        rebelled_cities=[],
        garrisons=[],
    )

    RebellionManager(game)._do_rebellion(owner, "pisa")

    assert owner.rebelled_provinces == ["pisa"]
    game.add_event.assert_not_called()


def test_non_home_country_expense_targets_current_controller() -> None:
    game = _game()
    owner = Mock(
        player_id="FLORENCE",
        controlled_locations=["pisa"],
        home_countries=["F"],
    )
    game.players = [owner]
    manager = RebellionManager(game)

    with patch.object(manager, "_do_rebellion") as do_rebellion:
        manager.expense_rebellion_non_home_country(Mock(target="pisa"))

    do_rebellion.assert_called_once_with(owner=owner, target="pisa")


def test_home_country_expense_requires_owner_home_country() -> None:
    game = _game()
    owner = Mock(
        player_id="MILAN",
        controlled_locations=["pisa"],
        home_countries=["M"],
    )
    game.players = [owner]
    manager = RebellionManager(game)

    with patch.object(manager, "_do_rebellion") as do_rebellion:
        manager.expense_rebellion_home_country(Mock(target="pisa"))

    do_rebellion.assert_called_once_with(owner=owner, target="pisa")


def test_rebellion_expenses_dispatches_supported_commands() -> None:
    game = _game()
    player = Mock()
    pacify = Mock(target="pisa")
    pacify.is_valid_expense.side_effect = lambda kinds: kinds == {"B"}
    non_home = Mock(target="pisa")
    non_home.is_valid_expense.side_effect = lambda kinds: kinds == {"D"}
    player.commands = [pacify, non_home]
    game.players = [player]
    manager = RebellionManager(game)

    with (
        patch.object(manager, "expense_rebellion_pacify") as pacify_call,
        patch.object(manager, "expense_rebellion_non_home_country") as non_home_call,
    ):
        manager.rebellion_expenses()

    pacify_call.assert_called_once_with(pacify)
    non_home_call.assert_called_once_with(non_home)
