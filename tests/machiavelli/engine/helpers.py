# tests/machiavelli/test_helpers.py

from random import Random
from unittest.mock import Mock

from machiavelli.engine import GameEngine
from machiavelli.game import Game, Player


def create_mock_player(
    player_id: str,
    armies: list[str] | None = None,
    fleets: list[str] | None = None,
    garrisons: list[str] | None = None,
    controlled_locations: list[str] | None = None,
    home_countries: list[str] | None = None,
    rebelled_provinces: list[str] | None = None,
    rebelled_cities: list[str] | None = None,
) -> Mock:
    """Crea un Mock con la especificación de Player."""
    player = Mock(spec=Player)
    player.player_id = player_id
    player.armies = armies if armies is not None else []
    player.fleets = fleets if fleets is not None else []
    player.garrisons = garrisons if garrisons is not None else []
    player.controlled_locations = (
        controlled_locations if controlled_locations is not None else []
    )
    player.home_countries = home_countries if home_countries is not None else []
    player.rebelled_provinces = (
        rebelled_provinces if rebelled_provinces is not None else []
    )
    player.rebelled_cities = rebelled_cities if rebelled_cities is not None else []
    return player


def create_mock_game(
    players: list[Mock] | None = None,
    independent_garrisons: list[str] | None = None,
    famine: list[str] | None = None,
    provinces: set[str] | None = None,
) -> Mock:
    """Crea un Mock con la especificación de Game y atributos por defecto."""
    game = Mock(spec=Game)
    game.players = players if players is not None else []
    game.independent_garrisons = (
        independent_garrisons if independent_garrisons is not None else []
    )
    game.famine = famine if famine is not None else []

    if provinces is not None:
        game.map.provinces = provinces

    return game


def create_test_engine(game: Mock | None = None, seed: int = 42) -> GameEngine:
    """Instancia un GameEngine con una semilla fija o un Game personalizado."""
    if game is None:
        game = create_mock_game()
    return GameEngine(game=game, rng=Random(seed))
