"""Contract tests for deeply immutable structured turn events."""

import json
from collections.abc import Mapping
from dataclasses import FrozenInstanceError
from typing import get_args, get_origin

import pytest

from machiavelli.events import (
    EventType,
    InvalidTurnEventError,
    JSONValue,
    TurnEvent,
)

EXPECTED_EVENT_TYPES = {
    "start_game",
    "start_game_power_assigned",
    "start_season",
    "famine_spawn",
    "famine_relief",
    "famine_attrition",
    "famine_end",
    "plague_spawn",
    "plague_death",
    "rebellion_pacify",
    "rebellion_province",
    "rebellion_city",
    "expense",
    "expense_no_funds",
    "expense_syntax_error",
    "bribe_executed",
    "income_collected",
    "maintenance_order_resolved",
    "maintenance_summary",
    "get_control",
    "lose_control",
    "get_home_country",
    "lose_home_country",
    "player_eliminated",
    "player_won",
    "military_resolution",
}


def test_event_catalog_is_closed_and_exact() -> None:
    assert {event_type.value for event_type in EventType} == EXPECTED_EVENT_TYPES


def test_json_value_alias_uses_only_native_json_containers() -> None:
    container_origins = {
        get_origin(member)
        for member in get_args(JSONValue.__value__)
        if get_origin(member) is not None
    }
    assert container_origins == {list, dict}


def test_constructor_rejects_non_object_payload_directly() -> None:
    with pytest.raises(InvalidTurnEventError):
        TurnEvent(EventType.START_GAME, [])  # type: ignore[arg-type]


def test_fixture_contains_one_valid_payload_for_every_type(
    valid_event_payloads: Mapping[EventType, dict[str, JSONValue]],
) -> None:
    assert set(valid_event_payloads) == set(EventType)
    for event_type, payload in valid_event_payloads.items():
        event = TurnEvent(event_type, payload)
        assert event.type is event_type
        assert isinstance(event.data, Mapping)


@pytest.mark.parametrize("event_type", list(EventType))
def test_payload_keys_are_exact(
    event_type: EventType,
    valid_event_payloads: Mapping[EventType, dict[str, JSONValue]],
) -> None:
    payload = dict(valid_event_payloads[event_type])
    payload["unexpected"] = "value"
    with pytest.raises(InvalidTurnEventError):
        TurnEvent(event_type, payload)

    required_key = next(iter(valid_event_payloads[event_type]))
    missing = dict(valid_event_payloads[event_type])
    missing.pop(required_key)
    with pytest.raises(InvalidTurnEventError):
        TurnEvent(event_type, missing)


@pytest.mark.parametrize(
    ("event_type", "payload"),
    [
        (EventType.START_GAME, {"scenario": ""}),
        (
            EventType.START_GAME_POWER_ASSIGNED,
            {"player_id": "P1", "discord_id": True, "power_id": "F"},
        ),
        (EventType.START_SEASON, {"year": True, "season": 0}),
        (
            EventType.FAMINE_SPAWN,
            {"severity_roll": 0, "provinces": ["flore"]},
        ),
        (
            EventType.PLAGUE_SPAWN,
            {"severity_roll": 7, "provinces": ["rome"]},
        ),
        (
            EventType.REBELLION_PACIFY,
            {"player": "P1", "province": "flore", "kind": "district"},
        ),
        (
            EventType.EXPENSE,
            {"player": "P1", "expense": "A", "target": None, "amount": True},
        ),
        (
            EventType.MAINTENANCE_ORDER_RESOLVED,
            {
                "player": "P1",
                "actor": "A flore",
                "order": "X",
                "target": None,
                "result": "maintained",
                "cost": 3,
            },
        ),
        (
            EventType.MAINTENANCE_ORDER_RESOLVED,
            {
                "player": "P1",
                "actor": "A flore",
                "order": "M",
                "target": None,
                "result": "unknown",
                "cost": 3,
            },
        ),
        (EventType.GET_CONTROL, {"player": "P1", "provinces": []}),
    ],
)
def test_invalid_scalar_and_enum_values_are_rejected(
    event_type: EventType, payload: dict[str, JSONValue]
) -> None:
    with pytest.raises(InvalidTurnEventError):
        TurnEvent(event_type, payload)


def test_constructor_defensively_copies_and_deeply_freezes_payload() -> None:
    payload: dict[str, JSONValue] = {
        "player": "P1",
        "provinces": ["flore"],
        "province_income": 1,
        "cities": ["flore"],
        "city_income": 1,
        "variable_income": [
            {
                "source_type": "province",
                "source": "tunis",
                "roll": 6,
                "amount": 4,
            }
        ],
        "total_income": 6,
    }
    event = TurnEvent(EventType.INCOME_COLLECTED, payload)

    payload["player"] = "changed"
    provinces = payload["provinces"]
    assert isinstance(provinces, list)
    provinces.append("pisa")
    variable_income = payload["variable_income"]
    assert isinstance(variable_income, list)
    nested = variable_income[0]
    assert isinstance(nested, dict)
    nested["amount"] = 99

    assert event.data["player"] == "P1"
    assert event.data["provinces"] == ("flore",)
    frozen_variable = event.data["variable_income"]
    assert isinstance(frozen_variable, tuple)
    assert frozen_variable[0]["amount"] == 4

    with pytest.raises(TypeError):
        event.data["player"] = "changed"  # type: ignore[index]
    with pytest.raises(TypeError):
        frozen_variable[0]["amount"] = 99  # type: ignore[index]


def test_frozen_dataclass_rejects_field_reassignment() -> None:
    event = TurnEvent(EventType.START_GAME, {"scenario": "Rinascimento"})
    with pytest.raises(FrozenInstanceError):
        event.type = EventType.START_SEASON  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        event.data = {}  # type: ignore[misc]


def test_military_payload_accepts_lists_and_tuples_and_empty_collections() -> None:
    empty = TurnEvent.military_resolution([], [], [], [], [], [])
    assert all(value == () for value in empty.data.values())

    event = TurnEvent.military_resolution(
        ((("P1", "A", "flore"), "A", "pisa", False),),
        (("P1", "A", "flore"),),
        (),
        (),
        (("P1", "province", "flore", "subdued"),),
        ((("P1", "A", "flore"), "pisa", "started"),),
    )
    assert event.data["outcomes"][0][0] == ("P1", "A", "flore")


def test_json_is_compact_deterministic_and_uses_native_values() -> None:
    event = TurnEvent.military_resolution(
        [[["Pñ", "A", "flore"], "A", None, True]],
        [],
        [],
        [["Pñ", "A", "flore"]],
        [],
        [],
    )
    expected = (
        '{"broken_convoys":[],"cancelled_orders":[],"dislodgements":'
        '[["Pñ","A","flore"]],"outcomes":[[["Pñ","A","flore"],'
        '"A",null,true]],"rebellions":[],"sieges":[]}'
    )
    assert event.to_json() == expected
    assert json.loads(event.to_json()) == {
        "broken_convoys": [],
        "cancelled_orders": [],
        "dislodgements": [["Pñ", "A", "flore"]],
        "outcomes": [[["Pñ", "A", "flore"], "A", None, True]],
        "rebellions": [],
        "sieges": [],
    }


def test_from_persisted_reuses_validation_and_exposes_row_context() -> None:
    event = TurnEvent.from_persisted(
        row_id=7,
        event_type="start_game",
        data_json='{"scenario":"Rinascimento"}',
    )
    assert event == TurnEvent(EventType.START_GAME, {"scenario": "Rinascimento"})

    invalid_rows = [
        ("unknown", "{}"),
        ("start_game", "not-json"),
        ("start_game", "[]"),
        ("start_game", "{}"),
    ]
    for event_type, data_json in invalid_rows:
        with pytest.raises(InvalidTurnEventError) as error_info:
            TurnEvent.from_persisted(
                row_id=42,
                event_type=event_type,
                data_json=data_json,
            )
        assert error_info.value.row_id == 42
        assert error_info.value.event_type == event_type
        assert error_info.value.__cause__ is not None
        assert "fila 42" in str(error_info.value)
        assert repr(event_type) in str(error_info.value)
        assert data_json not in str(error_info.value)
