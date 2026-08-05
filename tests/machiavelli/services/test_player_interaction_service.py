# tests/machiavelli/services/test_player_interaction_service.py

from unittest.mock import MagicMock

import pytest

from machiavelli.services.player_interaction_service import PlayerInteractionService


@pytest.fixture
def mock_game():
    game = MagicMock()
    game.turn_number = 1  # Por defecto turno de mantenimiento de primavera (1 % 4 == 1)
    game.famine = []
    game.independent_garrisons = []
    game.besieges = []
    game.players = []
    game.scenario.rules.fortress_active = True
    game.scenario.rules.assassinations_active = True
    game.scenario.rules.famine_active = True
    game.scenario.is_defensible_city.side_effect = lambda city: (
        city == "fortified"
        or (city == "fortress" and game.scenario.rules.fortress_active)
    )
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


@pytest.mark.parametrize(
    ("rule_name", "hidden_expense"),
    [("famine_active", "E A"), ("assassinations_active", "E E")],
)
def test_expenses_hide_disabled_optional_mechanics(
    service, mock_game, rule_name, hidden_expense
):
    service.player.ducats = 20
    service.player.ass_counters = ["M"]
    target = MagicMock(power="M", home_countries=["M"])
    mock_game.players = [service.player, target]
    mock_game.famine = ["naple"]
    province = MagicMock(land_routes=[], sea_routes=[])
    mock_game.map.provinces = {"naple": province}
    mock_game.map.seas = {}
    setattr(mock_game.scenario.rules, rule_name, False)

    with pytest.MonkeyPatch.context() as mp:
        from machiavelli.services import player_interaction_service

        mock_gt = MagicMock()
        mock_gt.expenses = {
            "A": {"cost": 5, "text": "Paliar hambruna"},
            "E": {"cost": 5, "text": "Asesinar"},
            "F": {"cost": 2, "text": "Contra-soborno"},
        }
        mp.setattr(player_interaction_service, "GameTables", mock_gt)

        choices = service.exp_available_expenses()

    assert hidden_expense not in {value for value, _ in choices}
    assert "E F" in {value for value, _ in choices}


def test_inactive_fortress_hides_garrison_actor_and_siege_command(service, mock_game):
    mock_game.turn_number = 2
    mock_game.scenario.rules.fortress_active = False
    keep = MagicMock(
        name="Keep",
        city="fortress",
        has_port=True,
        land_routes=[],
        sea_routes=[],
    )
    mock_game.map.provinces = {"keep": keep}
    mock_game.map.seas = {}
    service.player.armies = ["keep"]
    service.player.garrisons = ["keep"]
    mock_game.independent_garrisons = ["keep"]

    actors = service.cmd_available_actors()

    with pytest.MonkeyPatch.context() as mp:
        from machiavelli.services import player_interaction_service

        mock_gt = MagicMock()
        mock_gt.military_orders = {
            code: {"text": code} for code in ("A", "B", "H", "S", "C")
        }
        mp.setattr(player_interaction_service, "GameTables", mock_gt)
        commands = service.cmd_available_commands("A keep")

    assert "G keep" not in {value for value, _ in actors}
    assert "B" not in {value for value, _ in commands}


def test_active_fortress_offers_garrison_actor_and_siege_command(service, mock_game):
    mock_game.turn_number = 2
    mock_game.scenario.rules.fortress_active = True
    keep = MagicMock(
        name="Keep",
        city="fortress",
        has_port=True,
        land_routes=[],
        sea_routes=[],
    )
    mock_game.map.provinces = {"keep": keep}
    mock_game.map.seas = {}
    service.player.armies = ["keep"]
    service.player.garrisons = ["keep"]
    mock_game.players = [service.player]

    actors = service.cmd_available_actors()

    with pytest.MonkeyPatch.context() as mp:
        from machiavelli.services import player_interaction_service

        mock_gt = MagicMock()
        mock_gt.military_orders = {
            code: {"text": code} for code in ("A", "B", "H", "S", "C")
        }
        mp.setattr(player_interaction_service, "GameTables", mock_gt)
        commands = service.cmd_available_commands("A keep")

    assert "G keep" in {value for value, _ in actors}
    assert "B" in {value for value, _ in commands}


def test_active_fortress_never_offers_recruitment(service, mock_game):
    mock_game.turn_number = 1
    mock_game.scenario.rules.fortress_active = True
    mock_game.scenario.home_countries = {
        "N": MagicMock(provinces=["keep"]),
    }
    service.player.home_countries = ["N"]
    service.player.controlled_locations = ["keep"]
    service.player.armies = []
    keep = MagicMock(
        name="Keep",
        city="fortress",
        has_port=True,
        land_routes=[],
        sea_routes=[],
    )
    mock_game.map.provinces = {"keep": keep}
    mock_game.map.seas = {}

    choices = service.cmd_available_actors()

    assert choices == []


def test_active_fortress_allows_conversion_to_garrison(service, mock_game):
    mock_game.turn_number = 2
    keep = MagicMock(name="Keep", city="fortress", has_port=True)
    mock_game.map.provinces = {"keep": keep}
    mock_game.map.seas = {}

    mock_game.scenario.rules.fortress_active = True
    active = service.cmd_available_targets("A keep", "C")
    mock_game.scenario.rules.fortress_active = False
    inactive = service.cmd_available_targets("A keep", "C")

    assert ("G", "Guarnición") in active
    assert ("G", "Guarnición") not in inactive


def test_active_fortress_offers_city_rebellion_target(service, mock_game):
    mock_game.scenario.rules.fortress_active = True
    keep = MagicMock(id="keep", city="fortress")
    keep.name = "Keep"
    mock_game.map.provinces = {"keep": keep, "naple": MagicMock()}
    mock_game.map.seas = {}
    owner = MagicMock(rebelled_provinces=[], rebelled_cities=["keep"])
    mock_game.players = [service.player, owner]

    choices = service.exp_available_targets("E B")

    assert choices == [("keep", "Keep")]


def test_inactive_fortress_hides_residual_city_rebellion_target(service, mock_game):
    mock_game.scenario.rules.fortress_active = False
    keep = MagicMock(id="keep", name="Keep", city="fortress")
    mock_game.map.provinces = {"keep": keep, "naple": MagicMock()}
    mock_game.map.seas = {}
    owner = MagicMock(rebelled_provinces=[], rebelled_cities=["keep"])
    mock_game.players = [service.player, owner]

    choices = service.exp_available_targets("E B")

    assert choices == []
