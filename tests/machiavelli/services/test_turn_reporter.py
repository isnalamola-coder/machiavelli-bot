"""Tests for the complete, read-only turn-event reporter."""

from __future__ import annotations

import json
from collections.abc import Mapping
from unittest.mock import call, patch

import pytest

from machiavelli.events import EventType, JSONValue, TurnEvent
from machiavelli.game.game import Game
from machiavelli.game.map import Map
from machiavelli.game.scenario import Scenario
from machiavelli.services.game_status_reporter import GameStatusReporter
from machiavelli.services.turn_reporter import TurnReporter

EVENTS_HEADER = "## ⚠️ EVENTOS DEL TURNO"
SITUATION_HEADER = "## 🗺️ REPORTE DE SITUACIÓN"

EXPECTED_EVENT_LINES: dict[EventType, tuple[str, ...]] = {
    EventType.START_GAME: ("Comienza la partida con el escenario Rinascimento.",),
    EventType.START_GAME_POWER_ASSIGNED: ("jugador-ñ recibe la potencia France.",),
    EventType.START_SEASON: ("Comienza Verano de 1454.",),
    EventType.FAMINE_SPAWN: (
        "La hambruna aparece tras una tirada de 6: Florence y Pisa.",
    ),
    EventType.FAMINE_RELIEF: ("<@101> (Florence) reduce la hambruna en Florence.",),
    EventType.FAMINE_ATTRITION: (
        "La hambruna elimina unidades de una guarnición independiente: "
        "Guarnición en Pisa.",
    ),
    EventType.FAMINE_END: ("Finaliza la hambruna en Florence.",),
    EventType.PLAGUE_SPAWN: ("La peste aparece tras una tirada de 1: Rome.",),
    EventType.PLAGUE_DEATH: (
        "La peste elimina unidades de <@101> (Florence): Ejército en Rome.",
    ),
    EventType.REBELLION_PACIFY: (
        "<@101> (Florence) pacifica la rebelión urbana de Florence.",
    ),
    EventType.REBELLION_PROVINCE: (
        "Se inicia una rebelión provincial de <@101> (Florence) en Pisa.",
    ),
    EventType.REBELLION_CITY: (
        "Se inicia una rebelión urbana de <@101> (Florence) en Florence.",
    ),
    EventType.EXPENSE: (
        "<@101> (Florence) ejecuta el gasto Paliar hambruna por 3 ducados.",
    ),
    EventType.EXPENSE_NO_FUNDS: (
        "<@101> (Florence) no puede ejecutar por falta de fondos el gasto "
        "Pacificar rebelión sobre Pisa por mucho ducados.",
    ),
    EventType.EXPENSE_SYNTAX_ERROR: (
        "<@101> (Florence) presenta con sintaxis inválida el gasto Comenzar "
        "rebelión en provincia no natal por \\-1 ducados.",
    ),
    EventType.BRIBE_EXECUTED: (
        "<@101> (Florence) ejecuta el gasto Comprar ejército o flota sobre "
        "Ejército en Pisa por 18 ducados.",
    ),
    EventType.INCOME_COLLECTED: (
        "<@101> (Florence) recauda 11 ducados en total.",
        "Ingreso provincial (2): Florence y Pisa.",
        "Ingreso urbano (1): Florence.",
        "Ingreso variable de France: tirada 4, 5 ducados.",
        "Ingreso variable de Tunis: tirada 2, 3 ducados.",
    ),
    EventType.MAINTENANCE_ORDER_RESOLVED: (
        "Mantenimiento de <@101> (Florence): Ejército en Florence, orden "
        "Mantener; resultado mantenida; coste 3 ducados.",
    ),
    EventType.MAINTENANCE_SUMMARY: (
        "Resumen de mantenimiento de <@101> (Florence): 12 ducados iniciales, "
        "3 gastados y 9 restantes.",
    ),
    EventType.GET_CONTROL: ("<@101> (Florence) obtiene el control de Florence.",),
    EventType.LOSE_CONTROL: ("<@101> (Florence) pierde el control de Pisa.",),
    EventType.GET_HOME_COUNTRY: ("<@101> (Florence) obtiene el control de France.",),
    EventType.LOSE_HOME_COUNTRY: ("<@101> (Florence) pierde el control de Milan.",),
    EventType.PLAYER_ELIMINATED: ("<@101> (Florence) queda eliminado de la partida.",),
    EventType.PLAYER_WON: (
        "<@101> (Florence) gana la partida con 12 ciudades y 2 naciones controladas.",
    ),
    EventType.MILITARY_RESOLUTION: ("Sin cambios militares.",),
}


def make_game() -> Game:
    """Build a representative game with resolvable public identifiers."""
    scenario = Scenario.load_scenarios()["Be"]
    game = Game(
        name="Partida de prueba",
        channel_id=9001,
        scenario_id="Be",
        scenario=scenario,
        map=Map.load_map(exclude_ids=scenario.excluded_locations),
        turn_number=2,
        next_deadline="2026-08-11 21:00",
    )
    first = game.add_player("P1", 101)
    first.power = "L"
    first.home_countries = ["L"]
    second = game.add_player("P2", 202)
    second.power = "M"
    second.home_countries = ["M"]
    return game


def extract_event_lines(report: list[str]) -> list[str]:
    """Return only rendered event lines from a complete report."""
    start = report.index(EVENTS_HEADER) + 1
    end = report.index(SITUATION_HEADER)
    return report[start:end]


def test_every_event_type_has_a_non_empty_spanish_representation(
    valid_event_payloads: Mapping[EventType, dict[str, JSONValue]],
) -> None:
    game = make_game()

    assert set(EXPECTED_EVENT_LINES) == set(EventType)
    assert set(valid_event_payloads) == set(EXPECTED_EVENT_LINES)
    for event_type, payload in valid_event_payloads.items():
        event = TurnEvent(event_type, payload)
        game.turn_events = [event]

        report = TurnReporter.generate(game)
        event_lines = extract_event_lines(report)

        assert event_lines == list(EXPECTED_EVENT_LINES[event_type])
        assert all(line.strip() for line in event_lines)
        rendered = "\n".join(event_lines)
        native_payload = json.loads(event.to_json())
        raw_payload_representations = {
            event.to_json(),
            json.dumps(native_payload, ensure_ascii=False),
            repr(event.data),
            repr(dict(event.data)),
            repr(native_payload),
        }
        assert event_type.value not in rendered
        assert "mappingproxy" not in rendered
        assert "TurnEvent" not in rendered
        assert "EventType" not in rendered
        assert all(
            raw_payload not in rendered for raw_payload in raw_payload_representations
        )


def test_report_preserves_general_order_repetitions_and_game_state() -> None:
    game = make_game()
    repeated = TurnEvent(
        EventType.GET_CONTROL,
        {"player": "P1", "provinces": ["flore"]},
    )
    final = TurnEvent(
        EventType.LOSE_CONTROL,
        {"player": "P2", "provinces": ["milan"]},
    )
    game.turn_events = [repeated, repeated, final]
    original_events = list(game.turn_events)
    original_json = [event.to_json() for event in game.turn_events]
    original_players = [
        (player.player_id, player.discord_id, player.power, list(player.home_countries))
        for player in game.players
    ]

    report = TurnReporter.generate(game)
    event_lines = extract_event_lines(report)

    assert report[0] == "## 📜 Partida de prueba, turno 2"
    assert report[1].startswith("### 🗓️ ")
    assert report.index(EVENTS_HEADER) < report.index(SITUATION_HEADER)
    assert report[report.index(SITUATION_HEADER) + 1 :] == GameStatusReporter.generate(
        game
    )
    assert len(event_lines) == 3
    assert event_lines[0] == event_lines[1]
    assert "Florence" in event_lines[0]
    assert "Milan" in event_lines[2]
    assert game.turn_events == original_events
    assert all(
        actual is expected
        for actual, expected in zip(
            game.turn_events,
            original_events,
            strict=True,
        )
    )
    assert [event.to_json() for event in game.turn_events] == original_json
    assert [
        (player.player_id, player.discord_id, player.power, list(player.home_countries))
        for player in game.players
    ] == original_players


def test_known_identifiers_resolve_to_mentions_names_locations_and_units() -> None:
    game = make_game()
    game.turn_events = [
        TurnEvent(
            EventType.START_GAME_POWER_ASSIGNED,
            {"player_id": "P1", "discord_id": 101, "power_id": "L"},
        ),
        TurnEvent(
            EventType.BRIBE_EXECUTED,
            {"player": "P1", "expense": "K", "target": "A milan", "amount": 18},
        ),
    ]

    event_lines = extract_event_lines(TurnReporter.generate(game))

    assert event_lines == [
        "<@101> (Florence) recibe la potencia Florence.",
        "<@101> (Florence) ejecuta el gasto Comprar ejército o flota sobre "
        "Ejército en Milan por 18 ducados.",
    ]


def test_unknown_identifiers_escape_markdown_then_mentions() -> None:
    game = make_game()
    hostile_player = "@everyone_<@123>_*`|\\"
    hostile_province = "@here_<@456>_**"
    game.turn_events = [
        TurnEvent(
            EventType.REBELLION_PROVINCE,
            {"player": hostile_player, "province": hostile_province},
        )
    ]

    with (
        patch(
            "machiavelli.services.turn_reporter.escape_markdown",
            side_effect=lambda value, *, as_needed: f"markdown({value})",
        ) as markdown,
        patch(
            "machiavelli.services.turn_reporter.escape_mentions",
            side_effect=lambda value: f"mentions({value})",
        ) as mentions,
    ):
        rendered = "\n".join(extract_event_lines(TurnReporter.generate(game)))

    assert f"mentions(markdown({hostile_player}))" in rendered
    assert f"mentions(markdown({hostile_province}))" in rendered
    assert call(hostile_player, as_needed=False) in markdown.call_args_list
    assert call(hostile_province, as_needed=False) in markdown.call_args_list
    assert call(f"markdown({hostile_player})") in mentions.call_args_list
    assert call(f"markdown({hostile_province})") in mentions.call_args_list


def test_unknown_discord_identifier_never_becomes_a_real_mention() -> None:
    game = make_game()
    game.turn_events = [
        TurnEvent(
            EventType.START_GAME_POWER_ASSIGNED,
            {"player_id": "intruso", "discord_id": 123, "power_id": "X_*"},
        )
    ]

    rendered = "\n".join(extract_event_lines(TurnReporter.generate(game)))

    assert "<@123>" not in rendered
    assert "@123" in rendered


def test_military_resolution_renders_every_item_in_canonical_group_order() -> None:
    game = make_game()
    game.turn_events = [
        TurnEvent(
            EventType.MILITARY_RESOLUTION,
            {
                "outcomes": [
                    [["P1", "F", "croat N"], "F", "WGOL", False],
                    [[None, "G", "pisa"], "G", None, True],
                ],
                "cancelled_orders": [["P1", "A", "flore"]],
                "broken_convoys": [["P2", "F", "WGOL"]],
                "dislodgements": [[None, "G", "pisa"]],
                "rebellions": [["P1", "city", "flore", "subdued"]],
                "sieges": [[["P2", "A", "milan"], "pisa", "started"]],
            },
        )
    ]

    event_lines = extract_event_lines(TurnReporter.generate(game))

    assert event_lines == [
        "Resultado: Flota de <@101> (Florence) en Croatia (N) → "
        "Flota en Western Gulf of Lyons.",
        "Resultado: Guarnición de una guarnición independiente en Pisa → "
        "Guarnición, desalojada.",
        "Orden cancelada: Ejército de <@101> (Florence) en Florence.",
        "Convoy roto: Flota de <@202> (Milan) en Western Gulf of Lyons.",
        "Desalojo: Guarnición de una guarnición independiente en Pisa.",
        "Rebelión: urbana de <@101> (Florence) en Florence, sofocada.",
        "Asedio: Ejército de <@202> (Milan) en Milan sobre Pisa, iniciado.",
    ]


@pytest.mark.parametrize("turn_number", [1, 2, 3, 4, 5])
def test_report_date_uses_canonical_turn_season(turn_number: int) -> None:
    game = make_game()
    game.turn_number = turn_number
    game.turn_events = []

    report = TurnReporter.generate(game)

    assert report[1].startswith("### 🗓️ ")
    assert str(game.scenario.year + (turn_number - 1) // 4) in report[1]


def test_empty_military_resolution_produces_exactly_one_event_line() -> None:
    game = make_game()
    game.turn_events = [
        TurnEvent(
            EventType.MILITARY_RESOLUTION,
            {
                "outcomes": [],
                "cancelled_orders": [],
                "broken_convoys": [],
                "dislodgements": [],
                "rebellions": [],
                "sieges": [],
            },
        )
    ]

    assert extract_event_lines(TurnReporter.generate(game)) == [
        "Sin cambios militares."
    ]
