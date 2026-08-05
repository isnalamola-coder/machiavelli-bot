"""Shared fixtures for the structured turn-event contract."""

from collections.abc import Mapping

import pytest

from machiavelli.events import EventType, JSONValue


@pytest.fixture
def valid_event_payloads() -> Mapping[EventType, dict[str, JSONValue]]:
    """Return exactly one valid payload for every public turn-event type."""
    return {
        EventType.START_GAME: {"scenario": "Rinascimento"},
        EventType.START_GAME_POWER_ASSIGNED: {
            "player_id": "jugador-ñ",
            "discord_id": None,
            "power_id": "F",
        },
        EventType.START_SEASON: {"year": 1454, "season": 2},
        EventType.FAMINE_SPAWN: {
            "severity_roll": 6,
            "provinces": ["flore", "pisa"],
        },
        EventType.FAMINE_RELIEF: {"player": "P1", "province": "flore"},
        EventType.FAMINE_ATTRITION: {
            "player": None,
            "units": ["G pisa"],
        },
        EventType.FAMINE_END: {"provinces": ["flore"]},
        EventType.PLAGUE_SPAWN: {
            "severity_roll": 1,
            "provinces": ["rome"],
        },
        EventType.PLAGUE_DEATH: {
            "player": "P1",
            "units": ["A rome"],
        },
        EventType.REBELLION_PACIFY: {
            "player": "P1",
            "province": "flore",
            "kind": "city",
        },
        EventType.REBELLION_PROVINCE: {
            "player": "P1",
            "province": "pisa",
        },
        EventType.REBELLION_CITY: {
            "player": "P1",
            "province": "flore",
        },
        EventType.EXPENSE: {
            "player": "P1",
            "expense": "A",
            "target": None,
            "amount": 3,
        },
        EventType.EXPENSE_NO_FUNDS: {
            "player": "P1",
            "expense": "B",
            "target": "pisa",
            "amount": "mucho",
        },
        EventType.EXPENSE_SYNTAX_ERROR: {
            "player": "P1",
            "expense": "C",
            "target": None,
            "amount": "-1",
        },
        EventType.BRIBE_EXECUTED: {
            "player": "P1",
            "expense": "K",
            "target": "A pisa",
            "amount": 18,
        },
        EventType.INCOME_COLLECTED: {
            "player": "P1",
            "provinces": ["flore", "pisa"],
            "province_income": 2,
            "cities": ["flore"],
            "city_income": 1,
            "variable_income": [
                {
                    "source_type": "home_country",
                    "source": "F",
                    "roll": 4,
                    "amount": 5,
                },
                {
                    "source_type": "province",
                    "source": "tunis",
                    "roll": 2,
                    "amount": 3,
                },
            ],
            "total_income": 11,
        },
        EventType.MAINTENANCE_ORDER_RESOLVED: {
            "player": "P1",
            "actor": "A flore",
            "order": "M",
            "target": None,
            "result": "maintained",
            "cost": 3,
        },
        EventType.MAINTENANCE_SUMMARY: {
            "player": "P1",
            "initial_ducats": 12,
            "expenses": 3,
            "remaining_ducats": 9,
        },
        EventType.GET_CONTROL: {
            "player": "P1",
            "provinces": ["flore"],
        },
        EventType.LOSE_CONTROL: {
            "player": "P1",
            "provinces": ["pisa"],
        },
        EventType.GET_HOME_COUNTRY: {
            "player": "P1",
            "home_country": "F",
        },
        EventType.LOSE_HOME_COUNTRY: {
            "player": "P1",
            "home_country": "M",
        },
        EventType.PLAYER_ELIMINATED: {"player": "P1"},
        EventType.PLAYER_WON: {
            "player": "P1",
            "cities": 12,
            "home_countries": 2,
        },
        EventType.MILITARY_RESOLUTION: {
            "outcomes": [],
            "cancelled_orders": [],
            "broken_convoys": [],
            "dislodgements": [],
            "rebellions": [],
            "sieges": [],
        },
    }
