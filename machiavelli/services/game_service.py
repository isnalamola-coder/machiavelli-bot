# machiavelli/services/game_service.py

from typing import Any

from machiavelli.engine import GameEngine
from machiavelli.game import (
    Command,
    Game,
    GameNotFoundException,
    GameRuleException,
    Player,
)
from machiavelli.repositories.game_repository import GameRepository

# Definición de alias de tipos
type PlayerInfo = tuple[str, int]
type ActorOption = tuple[str, str]
type GameStatusDict = dict[str, Any]


class GameService:
    """
    Capa de Aplicación (Servicio).
    Orquesta los casos de uso coordinando el Dominio (Game, Engine)
    y la Infraestructura (GameRepository).
    """

    def __init__(self, repository: GameRepository) -> None:
        """Crea el GameService"""
        self.repo = repository

    def create_game(self, name: str, channel_id: int, scenario_name: str) -> Game:
        """Crea una nueva partida en el canal especificado y la persiste."""
        game = Game.create(
            name=name,
            channel_id=channel_id,
            scenario_name=scenario_name,
        )
        self.repo.save(game)
        return game

    def get_game_status(self, channel_id: int) -> GameStatusDict:
        """Obtiene un resumen estructurado del estado actual de la partida."""
        game = self.repo.get_by_channel(channel_id)
        return {
            "id": game.database_id,
            "name": game.name,
            "turn": game.turn,
            "scenario": getattr(game, "scenario_name", "Standard"),
            "players_count": len(game.players),
            "players": [(p.player_id, p.discord_id) for p in game.players],
        }

    def add_player(
        self, channel_id: int, discord_id: int, player_id: str
    ) -> list[PlayerInfo]:
        """Inscribe a un jugador delegando las validaciones al dominio."""
        game = self.repo.get_by_channel(channel_id)

        # Delegamos la adición y sus validaciones al método del agregado Game
        game.add_player(player_id=player_id, discord_id=discord_id)

        self.repo.save(game)
        return [(p.player_id, p.discord_id) for p in game.players]

    def remove_player(
        self, channel_id: int, discord_id: int
    ) -> tuple[str, list[PlayerInfo]]:
        """Elimina a un jugador de la partida activa a través de la entidad Game."""
        game = self.repo.get_by_channel(channel_id)

        # El dominio se encarga de buscar y remover la entidad Player
        removed_player = game.remove_player(discord_id=discord_id)

        self.repo.save(game)

        remaining = [(p.player_id, p.discord_id) for p in game.players]
        return removed_player.player_id, remaining

    def run_turn(self, channel_id: int) -> list[str]:
        """Ejecuta la resolución del turno mediante GameEngine y persiste el estado."""
        game = self.repo.get_by_channel(channel_id)

        engine = GameEngine(game)
        engine.run()

        report_lines = game.turn_report()
        self.repo.save(game)

        return report_lines

    def submit_command(
        self,
        channel_id: int,
        discord_id: int,
        command_payload: dict[str, Any],
        selected_power: str | None = None,
    ) -> str:
        """Registra o actualiza una orden enviada por un jugador."""
        game = self.repo.get_by_channel(channel_id)
        player = self.resolve_player(game, discord_id, selected_power)

        command = Command.from_dict(player=player, data=command_payload)
        game.add_command(command)

        self.repo.save(game)
        return f"Orden guardada exitosamente para **{player.player_id}**."

    def resolve_player(
        self,
        game: Game,
        discord_id: int,
        selected_power: str | None = None,
    ) -> Player:
        """Resuelve la entidad Player asociada a la petición dentro de la partida."""
        if selected_power:
            player = next(
                (
                    p
                    for p in game.players
                    if p.player_id.lower() == selected_power.lower()
                ),
                None,
            )
            if not player:
                raise GameRuleException(
                    f"No existe la potencia o jugador '{selected_power}'."
                )
            return player

        player = next((p for p in game.players if p.discord_id == discord_id), None)
        if not player:
            raise GameRuleException(
                "Tu cuenta no está vinculada a ningún jugador en esta partida."
            )

        return player

    def get_available_actors(
        self,
        channel_id: int,
        discord_id: int,
        selected_power: str | None = None,
    ) -> list[ActorOption]:
        """Suministra opciones para autocompletado de actores/unidades."""
        try:
            game = self.repo.get_by_channel(channel_id)
            player = self.resolve_player(game, discord_id, selected_power)

            if hasattr(player, "cmd_available_actors"):
                return player.cmd_available_actors()
            return []
        except (GameNotFoundException, GameRuleException):
            return []
