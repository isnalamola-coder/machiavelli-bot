"""Application service for complete game use cases."""

from __future__ import annotations

from typing import Any

from machiavelli.engine import GameEngine
from machiavelli.game import (
    Command,
    Game,
    GameNotFoundException,
    Player,
    PlayerNotFoundException,
    TurnType,
)
from machiavelli.game.map import Map
from machiavelli.game.scenario import Scenario
from machiavelli.repositories.game_repository import GameRepository

type PlayerInfo = tuple[str, int | None]
type ActorOption = tuple[str, str]
type GameStatusDict = dict[str, Any]


class GameService:
    """Orchestrate game domain, engine, and repository operations."""

    def __init__(self, repository: GameRepository) -> None:
        self.repo = repository

    @staticmethod
    def _resolve_scenario(scenario_name: str) -> tuple[str, Scenario]:
        scenarios = Scenario.load_scenarios()
        if scenario_name in scenarios:
            return scenario_name, scenarios[scenario_name]

        matches = [
            (scenario_id, scenario)
            for scenario_id, scenario in scenarios.items()
            if scenario.name.casefold() == scenario_name.casefold()
        ]
        if len(matches) == 1:
            return matches[0]
        raise ValueError(f"Escenario desconocido: {scenario_name}")

    @staticmethod
    def _command_from_payload(
        game: Game,
        player: Player,
        payload: dict[str, Any],
    ) -> Command:
        actor = payload.get("actor")
        action = payload.get("command")
        target = payload.get("target")

        if not isinstance(actor, str) or not actor.strip():
            raise ValueError("La orden requiere un actor de texto no vacío")
        if not isinstance(action, str) or not action.strip():
            raise ValueError("La orden requiere un comando de texto no vacío")
        if target is not None and not isinstance(target, str):
            raise ValueError("El objetivo de la orden debe ser texto o None")

        return Command(
            game=game,
            player=player,
            actor=actor,
            command=action,
            target=target,
        )

    def create_game(self, name: str, channel_id: int, scenario_name: str) -> Game:
        """Create a fully initialized game aggregate and persist it."""
        scenario_id, scenario = self._resolve_scenario(scenario_name)
        game = Game(
            name=name,
            channel_id=channel_id,
            scenario_id=scenario_id,
            scenario=scenario,
            map=Map.load_map(exclude_ids=scenario.excluded_locations),
        )
        self.repo.save(game)
        return game

    def get_game(self, channel_id: int) -> Game:
        """Load a complete game aggregate by Discord channel."""
        return self.repo.get_by_channel(channel_id)

    def get_game_status(self, channel_id: int) -> GameStatusDict:
        """Return a structured summary using canonical game attributes."""
        game = self.get_game(channel_id)
        return {
            "id": game.database_id,
            "name": game.name,
            "turn": game.turn_number,
            "scenario": game.scenario.name if game.scenario else None,
            "scenario_id": game.scenario_id,
            "players_count": len(game.players),
            "players": [
                (player.player_id, player.discord_id) for player in game.players
            ],
        }

    def add_player(
        self,
        channel_id: int,
        discord_id: int,
        player_id: str,
    ) -> list[PlayerInfo]:
        """Register a player in the aggregate and persist the complete game."""
        game = self.get_game(channel_id)
        game.add_player(player_id=player_id, discord_id=discord_id)
        self.repo.save(game)
        return [(player.player_id, player.discord_id) for player in game.players]

    def remove_player(
        self,
        channel_id: int,
        discord_id: int,
    ) -> tuple[str, list[PlayerInfo]]:
        """Remove a player and synchronize persisted players and commands."""
        game = self.get_game(channel_id)
        removed_player = game.remove_player(discord_id=discord_id)
        self.repo.save(game)
        remaining = [
            (player.player_id, player.discord_id) for player in game.players
        ]
        return removed_player.player_id, remaining

    def run_turn(self, channel_id: int) -> list[str]:
        """Execute one turn, then persist the resulting aggregate atomically."""
        game = self.get_game(channel_id)
        GameEngine(game).run()
        report_lines = game.turn_report()
        self.repo.save(game)
        return report_lines

    def submit_command(
        self,
        channel_id: int,
        discord_id: int,
        command_payload: dict[str, Any],
        selected_power: str | None = None,
    ) -> list[str]:
        """Register or replace an order through the canonical order processor."""
        game = self.get_game(channel_id)
        player = self.resolve_player(game, discord_id, selected_power)
        command = self._command_from_payload(game, player, command_payload)
        turn_type = (
            TurnType.MAINTENANCE
            if game.turn_number % 4 == 1
            else TurnType.CAMPAIGN
        )
        report = player.cmd_add_command(turn_type, command)
        self.repo.save(game)
        return report

    def resolve_player(
        self,
        game: Game,
        discord_id: int,
        selected_power: str | None = None,
    ) -> Player:
        """Resolve a player by selected power/player ID or Discord account."""
        if selected_power:
            selected = selected_power.casefold()
            player = next(
                (
                    candidate
                    for candidate in game.players
                    if candidate.player_id.casefold() == selected
                    or (
                        candidate.power is not None
                        and candidate.power.casefold() == selected
                    )
                ),
                None,
            )
            if player is None:
                raise PlayerNotFoundException(
                    f"No existe la potencia o jugador '{selected_power}'."
                )
            return player

        player = next(
            (
                candidate
                for candidate in game.players
                if candidate.discord_id == discord_id
            ),
            None,
        )
        if player is None:
            raise PlayerNotFoundException(
                "Tu cuenta no está vinculada a ningún jugador en esta partida."
            )
        return player

    def get_available_actors(
        self,
        channel_id: int,
        discord_id: int,
        selected_power: str | None = None,
    ) -> list[ActorOption]:
        """Return actor choices without exposing lookup errors to autocomplete."""
        try:
            game = self.get_game(channel_id)
            player = self.resolve_player(game, discord_id, selected_power)
            return player.cmd_available_actors()
        except (GameNotFoundException, PlayerNotFoundException):
            return []
