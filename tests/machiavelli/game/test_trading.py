"""Tests for the direct trading domain rules."""

from __future__ import annotations

import pytest

from machiavelli.game import TradeRuleException
from machiavelli.game.game import Game
from machiavelli.game.player import Player
from machiavelli.game.scenario import Scenario
from machiavelli.game.trading import (
    TradeResource,
    parse_trade_resource,
    player_has_trade_resource,
    transfer_trade_resource,
)


def make_scenario() -> Scenario:
    return Scenario.load_scenarios()["Be"]


def make_players() -> tuple[Player, Player]:
    game = Game("Trading")
    sender = Player(game, "sender", ducats=9, ass_counters=["V", "V"])
    receiver = Player(game, "receiver", ass_counters=["V"])
    return sender, receiver


@pytest.mark.parametrize(
    ("kind", "value", "message"),
    [
        (
            "ducats",
            True,
            "La cantidad de ducados debe ser un entero mayor que cero.",
        ),
        (
            "ducats",
            "9",
            "La cantidad de ducados debe ser un entero mayor que cero.",
        ),
        (
            "ducats",
            0,
            "La cantidad de ducados debe ser un entero mayor que cero.",
        ),
        (
            "ducats",
            -1,
            "La cantidad de ducados debe ser un entero mayor que cero.",
        ),
        (
            "assassin",
            1,
            "La facción objetivo de la ficha de asesinato no es válida en "
            "este escenario.",
        ),
        (
            "assassin",
            "",
            "La facción objetivo de la ficha de asesinato no es válida en "
            "este escenario.",
        ),
        (
            "unknown",
            1,
            "Tipo de recurso inválido. Usa 'ducats' o 'assassin'.",
        ),
    ],
)
def test_trade_resource_rejects_invalid_static_values(
    kind: str, value: int | str | bool, message: str
) -> None:
    with pytest.raises(TradeRuleException, match=f"^{message}$"):
        TradeResource(kind, value)  # type: ignore[arg-type]


@pytest.mark.parametrize("raw_value", ["0", "-1", "1.5", "", "not-a-number"])
def test_parse_trade_resource_rejects_invalid_ducats(raw_value: str) -> None:
    with pytest.raises(
        TradeRuleException,
        match="^La cantidad de ducados debe ser un entero mayor que cero\\.$",
    ):
        parse_trade_resource(make_scenario(), "ducats", raw_value)


def test_parse_trade_resource_accepts_canonical_resources() -> None:
    scenario = make_scenario()

    assert parse_trade_resource(scenario, "ducats", "9") == TradeResource("ducats", 9)
    assert parse_trade_resource(scenario, "assassin", "V") == TradeResource(
        "assassin", "V"
    )


def test_parse_trade_resource_rejects_invalid_assassin_inputs() -> None:
    scenario = make_scenario()

    with pytest.raises(
        TradeRuleException,
        match="^Tipo de recurso inválido\\. Usa 'ducats' o 'assassin'\\.$",
    ):
        parse_trade_resource(scenario, "Ducats", "9")

    scenario.rules.assassinations_active = False
    with pytest.raises(
        TradeRuleException,
        match="^Las fichas de asesinato no están disponibles en este escenario\\.$",
    ):
        parse_trade_resource(scenario, "assassin", "V")

    scenario.rules.assassinations_active = True
    with pytest.raises(
        TradeRuleException,
        match=(
            "^La facción objetivo de la ficha de asesinato no es válida en "
            "este escenario\\.$"
        ),
    ):
        parse_trade_resource(scenario, "assassin", "missing")


def test_transfer_moves_exactly_one_matching_assassin_counter() -> None:
    sender, receiver = make_players()
    resource = TradeResource("assassin", "V")

    assert player_has_trade_resource(sender, resource)
    transfer_trade_resource(sender, receiver, resource)

    assert sender.ass_counters == ["V"]
    assert receiver.ass_counters == ["V", "V"]


def test_transfer_moves_ducats_and_accepts_counter_targeted_at_receiver() -> None:
    sender, receiver = make_players()
    receiver.power = "V"

    transfer_trade_resource(sender, receiver, TradeResource("ducats", 9))
    assert sender.ducats == 0
    assert receiver.ducats == 9

    transfer_trade_resource(sender, receiver, TradeResource("assassin", "V"))
    assert sender.ass_counters == ["V"]
    assert receiver.ass_counters == ["V", "V"]


@pytest.mark.parametrize(
    ("resource", "message"),
    [
        (TradeResource("ducats", 10), "No tienes suficientes ducados."),
        (
            TradeResource("assassin", "M"),
            "No tienes una ficha de asesinato contra Milan.",
        ),
    ],
)
def test_transfer_rejects_insufficient_resources_without_mutation(
    resource: TradeResource, message: str
) -> None:
    sender, receiver = make_players()
    before = (
        sender.ducats,
        sender.ass_counters[:],
        receiver.ducats,
        receiver.ass_counters[:],
    )

    with pytest.raises(TradeRuleException, match=f"^{message}$"):
        transfer_trade_resource(sender, receiver, resource)

    assert (
        sender.ducats,
        sender.ass_counters,
        receiver.ducats,
        receiver.ass_counters,
    ) == before
