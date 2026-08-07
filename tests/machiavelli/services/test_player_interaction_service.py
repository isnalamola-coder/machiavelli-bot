# tests/machiavelli/services/test_player_interaction_service.py

from unittest.mock import MagicMock

import pytest

from machiavelli.game.game import Game
from machiavelli.game.map import Map, Province
from machiavelli.game.player import Player
from machiavelli.game.scenario import HomeCountry, Rules, Scenario, VictoryConditions
from machiavelli.services.player_interaction_service import PlayerInteractionService


@pytest.fixture
def mock_game():
    game = MagicMock()
    game.turn_number = 1  # Por defecto turno de mantenimiento de primavera (1 % 4 == 1)
    game.famine = []
    game.independent_garrisons = []
    game.besieges = []
    game.players = []
    return game


@pytest.fixture
def mock_player(mock_game):
    player = MagicMock()
    player.game = mock_game
    player.armies = ["naple"]
    player.fleets = []
    player.garrisons = []
    player.ducats = 15
    player.home_countries = ["N"]
    player.controlled_locations = ["naple"]
    player.commands = []
    player.rebelled_provinces = []
    player.rebelled_cities = []
    player.power = "N"
    player.ass_counters = []
    return player


@pytest.fixture
def service(mock_player):
    return PlayerInteractionService(mock_player)


def test_cmd_available_actors_maintenance(service, mock_game):
    mock_game.turn_number = 1
    mock_province = MagicMock()
    mock_province.name = "Naples"
    mock_province.city = "city"
    mock_province.has_port = True

    mock_game.map.provinces = {"naple": mock_province}
    mock_game.map.seas = {}

    choices = service.cmd_available_actors()
    assert ("A naple", "Ejército en Naples") in choices


def test_cmd_available_actors_campaign(service, mock_game):
    mock_game.turn_number = 2  # Turno de campaña
    mock_province = MagicMock()
    mock_province.name = "Naples"
    mock_province.land_routes = []
    mock_province.sea_routes = []

    mock_game.map.provinces = {"naple": mock_province}
    mock_game.map.seas = {}

    choices = service.cmd_available_actors()
    assert ("A naple", "Ejército en Naples") in choices


def test_cmd_available_commands_maintenance(service, mock_game):
    mock_game.turn_number = 1
    service.player.armies = ["naple"]
    service.player.fleets = []
    service.player.garrisons = []

    with pytest.MonkeyPatch.context() as mp:
        from machiavelli.services import player_interaction_service

        mock_gt = MagicMock()
        mock_gt.maintenance_orders = {
            "M": {"text": "Mantener"},
            "D": {"text": "Desbandar"},
        }
        mp.setattr(player_interaction_service, "GameTables", mock_gt)

        choices = service.cmd_available_commands("A naple")
        assert ("M", "Mantener") in choices
        assert ("D", "Desbandar") in choices


def test_cmd_available_commands_campaign(service, mock_game):
    mock_game.turn_number = 2  # Turno de campaña
    mock_province = MagicMock()
    mock_province.name = "Naples"
    mock_province.has_port = False
    mock_game.map.provinces.get.return_value = mock_province

    with pytest.MonkeyPatch.context() as mp:
        from machiavelli.services import player_interaction_service

        mock_gt = MagicMock()
        mock_gt.military_orders = {
            "A": {"text": "Avanzar a Provincia o Mar"},
            "H": {"text": "Mantener"},
            "S": {"text": "Apoyar Provincia o Mar"},
            "C": {"text": "Convertir o desbandar"},
        }
        mp.setattr(player_interaction_service, "GameTables", mock_gt)

        choices = service.cmd_available_commands("A naple")
        commands = [c[0] for c in choices]
        assert "A" in commands
        assert "H" in commands
        assert "S" in commands
        assert "C" in commands


def test_exp_available_expenses(service, mock_game):
    service.player.ducats = 10

    with pytest.MonkeyPatch.context() as mp:
        from machiavelli.services import player_interaction_service

        mock_gt = MagicMock()
        mock_gt.expenses = {
            "A": {"cost": 5, "text": "Paliar hambruna"},
            "F": {"cost": 2, "text": "Contra-soborno"},
        }
        mp.setattr(player_interaction_service, "GameTables", mock_gt)

        mock_game.famine = ["naple"]
        mock_province = MagicMock()
        mock_province.land_routes = []
        mock_province.sea_routes = []
        mock_game.map.provinces = {"naple": mock_province}
        mock_game.map.seas = {}

        choices = service.exp_available_expenses()
        assert ("E A", "Paliar hambruna") in choices
        assert ("E F", "Contra-soborno") in choices


def _rule_service(rules: Rules, *, turn_number: int = 2):
    game = Game(
        name="interaction-rules",
        turn_number=turn_number,
        scenario=Scenario(
            name="interaction-rules",
            year=1454,
            victory_conditions=VictoryConditions(cities=99, home_countries=99),
            rules=rules,
            home_countries={"M": HomeCountry(provinces=["keep"])},
        ),
        map=Map(
            provinces={
                "keep": Province("Keep", custom_id="keep", city="fortress"),
                "fort": Province("Fort", custom_id="fort", city="fortified"),
            },
            seas={},
        ),
    )
    player = Player(
        game=game,
        player_id="P1",
        power="M",
        ducats=20,
        controlled_locations=["keep"],
        home_countries=["M"],
        ass_counters=["V"],
    )
    opponent = Player(
        game=game,
        player_id="P2",
        power="V",
        home_countries=["V"],
    )
    game.players = [player, opponent]
    return PlayerInteractionService(player), game, player, opponent


@pytest.mark.parametrize(
    ("rules", "forbidden"),
    [
        (Rules(famine_active=False), "E A"),
        (Rules(assassinations_active=False), "E E"),
    ],
)
def test_disabled_rule_hides_its_expense(rules, forbidden, monkeypatch):
    service, game, _player, _opponent = _rule_service(rules)
    game.famine = ["fort"]
    monkeypatch.setattr(
        "machiavelli.services.player_interaction_service.GameTables.expenses",
        {
            "A": {"cost": 3, "text": "Hambre"},
            "E": {"cost": 3, "text": "Asesinato"},
            "F": {"cost": 3, "text": "Soborno"},
        },
    )

    codes = {code for code, _label in service.exp_available_expenses()}

    assert forbidden not in codes
    assert "E F" in codes
    assert service.exp_available_targets(forbidden) == []


@pytest.mark.parametrize("active", [False, True])
def test_fortress_actions_follow_the_scenario_rule(active):
    service, game, player, opponent = _rule_service(Rules(fortress_active=active))
    player.armies = ["keep"]
    game.independent_garrisons = ["keep"]
    opponent.rebelled_cities = ["keep"]

    commands = {code for code, _label in service.cmd_available_commands("A keep")}
    conversions = {
        code for code, _label in service.cmd_available_targets("A keep", "C")
    }

    assert ("B" in commands) is active
    assert ("C" in commands) is active
    assert ("G" in conversions) is active


def test_inactive_fortress_hides_stale_garrison_and_city_rebellion(monkeypatch):
    service, game, player, opponent = _rule_service(Rules(fortress_active=False))
    player.garrisons = ["keep"]
    opponent.rebelled_cities = ["keep"]
    monkeypatch.setattr(
        "machiavelli.services.player_interaction_service.GameTables.expenses",
        {"B": {"cost": 3, "text": "Pacificar"}},
    )

    actors = {code for code, _label in service.cmd_available_actors()}
    expenses = {code for code, _label in service.exp_available_expenses()}

    assert "G keep" not in actors
    assert "E B" not in expenses


def test_active_fortress_never_becomes_a_recruitment_option():
    service, game, player, _opponent = _rule_service(
        Rules(fortress_active=True),
        turn_number=1,
    )
    player.controlled_locations = ["keep"]

    assert all("keep" not in code for code, _label in service.cmd_available_actors())


def test_exp_available_amounts_fixed_cost(service):
    service.player.ducats = 20

    with pytest.MonkeyPatch.context() as mp:
        from machiavelli.services import player_interaction_service

        mock_gt = MagicMock()
        mock_gt.expenses = {"A": {"cost": 5, "text": "Paliar hambruna"}}
        mp.setattr(player_interaction_service, "GameTables", mock_gt)

        choices = service.exp_available_amounts("E A", "naple")
        assert ("0", "Cancelar gasto") in choices
        assert ("5", "5 ducados") in choices
