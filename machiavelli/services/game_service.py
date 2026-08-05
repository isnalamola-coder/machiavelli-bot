"""Application service for complete game use cases."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from machiavelli.db.database import DatabaseManager
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

from .game_status_reporter import GameStatusReporter
from .order_reporter import OrderReporter
from .turn_reporter import TurnReporter

type PlayerInfo = tuple[str, int | None]
type ActorOption = tuple[str, str]
type GameStatusDict = dict[str, Any]


@contextmanager
def game_service_session(db_path: str | Path) -> Iterator[GameService]:
    """Yield one service backed by a canonical, always-closed SQLite session."""
    connection = DatabaseManager(db_path).get_connection()
    try:
        yield GameService(GameRepository(connection))
    finally:
        connection.close()


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

    def create_game(
        self,
        name: str,
        channel_id: int,
        scenario_name: str | None = None,
    ) -> Game:
        """Create and persist a game, optionally initializing its scenario."""
        if scenario_name is None:
            game = Game(name=name, channel_id=channel_id)
        else:
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
        remaining = [(player.player_id, player.discord_id) for player in game.players]
        return removed_player.player_id, remaining

    def set_scenario(self, channel_id: int, scenario_name: str) -> str:
        """Assign a known scenario and refresh the map before persisting."""
        scenario_id, scenario = self._resolve_scenario(scenario_name)
        game = self.get_game(channel_id)
        game.scenario_id = scenario_id
        game.scenario = scenario
        game.map = Map.load_map(exclude_ids=scenario.excluded_locations)
        self.repo.save(game)
        return scenario.name

    def update_deadlines(
        self,
        channel_id: int,
        *,
        weekly_deadline: str | None = None,
        next_deadline: str | None = None,
    ) -> str:
        """Persist already validated deadline values and return the game name."""
        game = self.get_game(channel_id)
        if weekly_deadline is not None:
            game.weekly_deadline = weekly_deadline
        if next_deadline is not None:
            game.next_deadline = next_deadline
        self.repo.save(game)
        return game.name

    def get_status_report(self, channel_id: int) -> list[str]:
        """Return the public game-status report without exposing persistence."""
        return GameStatusReporter.generate(self.get_game(channel_id))

    def get_turn_report(self, channel_id: int) -> list[str]:
        """Load and render the persisted structured turn history."""
        return TurnReporter.generate(self.get_game(channel_id))

    def get_player_commands(
        self,
        channel_id: int,
        discord_id: int,
    ) -> tuple[str, list[str]]:
        """Return a player's identifier and current commands as display strings."""
        game = self.get_game(channel_id)
        player = self.resolve_player(game, discord_id)
        return player.player_id, [str(command) for command in player.commands]

    def run_turn(self, channel_id: int) -> list[str]:
        """Execute one turn, then persist the resulting aggregate atomically."""
        game = self.get_game(channel_id)
        GameEngine(game).run()
        report_lines = TurnReporter.generate(game)
        self.repo.save(game)
        return report_lines

    def submit_command(
        self,
        channel_id: int,
        discord_id: int,
        command_payload: dict[str, Any],
        selected_power: str | None = None,
    ) -> list[str]:
        """Validate, register, and persist an order through canonical services."""
        game = self.get_game(channel_id)
        player = self.resolve_player(game, discord_id, selected_power)
        command = self._command_from_payload(game, player, command_payload)

        valid_actors = {code for code, _label in player.cmd_available_actors()}
        if command.actor not in valid_actors:
            raise ValueError(f"`{command.actor}` no es un actor válido.")

        valid_commands = {
            code for code, _label in player.cmd_available_commands(command.actor)
        }
        if command.command not in valid_commands:
            raise ValueError(f"`{command.command}` no es una orden válida.")

        valid_targets = [
            code
            for code, _label in player.cmd_available_targets(
                command.actor,
                command.command,
            )
        ]
        if (
            valid_targets
            and valid_targets[0] != ""
            and command.target not in valid_targets
        ):
            raise ValueError(f"`{command.target}` no es un objetivo válido.")

        turn_type = (
            TurnType.MAINTENANCE if game.turn_number % 4 == 1 else TurnType.CAMPAIGN
        )
        result = player.cmd_add_command(turn_type, command)
        report = OrderReporter.generate(result, game.require_map(), game.turn_number)
        self.repo.save(game)
        return report

    def submit_expense(
        self,
        channel_id: int,
        discord_id: int,
        *,
        expense: str,
        target: str,
        amount: str,
        selected_power: str | None = None,
    ) -> list[str]:
        """Validate, register, and persist one campaign expense."""
        game = self.get_game(channel_id)
        player = self.resolve_player(game, discord_id, selected_power)

        valid_expenses = {code for code, _label in player.exp_available_expenses()}
        if expense not in valid_expenses:
            raise ValueError(f"`{expense}` no es un gasto válido.")

        valid_targets = {code for code, _label in player.exp_available_targets(expense)}
        if target not in valid_targets:
            raise ValueError(f"`{target}` no es un objetivo válido.")

        valid_amounts = {
            code for code, _label in player.exp_available_amounts(expense, target)
        }
        if amount not in valid_amounts:
            raise ValueError(f"`{amount}` no es una cantidad válida.")

        command = Command(
            game=game,
            player=player,
            actor=expense,
            command=amount,
            target=target,
        )
        result = player.cmd_add_command(TurnType.CAMPAIGN, command)
        report = OrderReporter.generate(result, game.require_map(), game.turn_number)
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

    def get_available_commands(
        self,
        channel_id: int,
        discord_id: int,
        actor: str,
        selected_power: str | None = None,
    ) -> list[ActorOption]:
        """Return command choices for one actor, or no choices on lookup failure."""
        try:
            game = self.get_game(channel_id)
            player = self.resolve_player(game, discord_id, selected_power)
            return player.cmd_available_commands(actor)
        except (GameNotFoundException, PlayerNotFoundException):
            return []

    def get_available_targets(
        self,
        channel_id: int,
        discord_id: int,
        actor: str,
        command: str,
        selected_power: str | None = None,
    ) -> list[ActorOption]:
        """Return target choices for one order, or no choices on lookup failure."""
        try:
            game = self.get_game(channel_id)
            player = self.resolve_player(game, discord_id, selected_power)
            return player.cmd_available_targets(actor, command)
        except (GameNotFoundException, PlayerNotFoundException):
            return []

    def get_available_expenses(
        self,
        channel_id: int,
        discord_id: int,
        selected_power: str | None = None,
    ) -> list[ActorOption]:
        """Return expense choices, or no choices on lookup failure."""
        try:
            game = self.get_game(channel_id)
            player = self.resolve_player(game, discord_id, selected_power)
            return player.exp_available_expenses()
        except (GameNotFoundException, PlayerNotFoundException):
            return []

    def get_expense_targets(
        self,
        channel_id: int,
        discord_id: int,
        expense: str,
        selected_power: str | None = None,
    ) -> list[ActorOption]:
        """Return target choices for one expense, or no choices on lookup failure."""
        try:
            game = self.get_game(channel_id)
            player = self.resolve_player(game, discord_id, selected_power)
            return player.exp_available_targets(expense)
        except (GameNotFoundException, PlayerNotFoundException):
            return []

    def get_expense_amounts(
        self,
        channel_id: int,
        discord_id: int,
        expense: str,
        target: str,
        selected_power: str | None = None,
    ) -> list[ActorOption]:
        """Return amount choices for one expense, or no choices on lookup failure."""
        try:
            game = self.get_game(channel_id)
            player = self.resolve_player(game, discord_id, selected_power)
            return player.exp_available_amounts(expense, target)
        except (GameNotFoundException, PlayerNotFoundException):
            return []

    def get_active_powers(self, channel_id: int) -> list[str]:
        """Return assigned power identifiers in authoritative player order."""
        return [
            player.power
            for player in self.get_game(channel_id).players
            if player.power is not None
        ]
