# machiavelli/engine/orders.py

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from machiavelli.game.command import Command
    from machiavelli.game.player import Player

from machiavelli.engine.exceptions import (
    TooManyExpenses,
)
from machiavelli.game.map import MovementMode, Province
from machiavelli.game.player import TurnType

logger = logging.getLogger(__name__)


class OrderProcessor:
    """Gestiona la validación y registro de órdenes según el tipo de turno."""

    def __init__(self, game):
        self.game = game

    def process_command(
        self, player: Player, turn_type: TurnType, command: Command
    ) -> list[str]:
        report = [f"Orden `{command}` enviada."]

        if turn_type == TurnType.MAINTENANCE:
            report.extend(self._handle_maintenance_command(player, command))
        else:
            report.extend(self._handle_campaign_command(player, command))

        report.append("**Órdenes recibidas hasta ahora:**")
        for c in player.commands:
            report.append(f"`{c}`")

        return report

    def _handle_maintenance_command(self, player: Player, command: Command) -> None:
        """Valida y registra un comando de mantenimiento.

        Las órdenes imposibles o ilegales se registran también (por ejemplo, crear una
        guarnición allí dónde no haya ciudad fortificada, una flota en provincia de
        interior, etc). Se validan simplemente a nivel sintático.

        Lo que sí se hace es mantener una única orden por unidad, de forma que una
        segunda orden para una unidad sustituye la anterior, si la hubiera.

        Args:
            player (Player): Jugador que da las órdenes.
            command (Command): Orden a agregar.
        """
        current_cmd = [c for c in player.commands if c.actor == command.actor]

        if current_cmd:
            # La unidad ya tenía una orden, la sustituyo
            if len(current_cmd) > 1:
                # Si hay más de uno, lanzo un warning y borro los demás
                logger.warning(
                    "Múltiples comandos para el actor '%s'. "
                    "Eliminando los comandos sobrantes.",
                    command.actor,
                )
                for cmd in current_cmd[1:]:
                    player.commands.remove(cmd)

            current_cmd[0].command = command.command
            current_cmd[0].target = command.target

            actor_type, actor_id = command.actor.split()
            is_new_unit = (
                (actor_type == "A" and actor_id not in player.armies)
                or (actor_type == "F" and actor_id not in player.fleets)
                or (actor_type == "G" and actor_id not in player.garrisons)
            )

            # Si se trata de una nueva unidad y mando "D"esbandar, borro la orden
            if is_new_unit and command.command == "D":
                player.commands.remove(current_cmd[0])
        else:
            # Añade el nuevo comando
            player.add_command(command)

    def _handle_campaign_command(self, player: Player, command: Command) -> None:
        """Valida y registra un comando de campaña.

        Las órdenes imposibles o ilegales se registran también (por ejemplo, avanzar a
        una provincia no adyacente, o convertir una unidad en una provincia que no
        tenga ciudad fortificada, etc). Se validan simplemente a nivel sintáctico.

        Sin embargo sí se hace alguna comprobación:
        - Las órdenes de gasto (expense)"""
        actor_type, actor_id = command.actor.split()

        if actor_type == "E":
            expense = next(
                (
                    c
                    for c in player.commands
                    if c.actor == command.actor and c.target == command.target
                ),
                None,
            )
            if expense:
                if int(command.command) == 0:
                    player.remove_command(expense)
                else:
                    expense.command = command.command
            else:
                expense_count = sum(c.actor.startswith("E ") for c in player.commands)
                if expense_count >= 4:
                    raise TooManyExpenses(
                        message="Solo se permiten hasta cuatro gastos por campaña"
                    )
                player.add_command(command)
        else:
            cmds = [c for c in player.commands if c.actor == command.actor]
            if cmds:
                is_convoy = self._validate_convoy(player, command, actor_type, cmds)
                if is_convoy:
                    player.add_command(command)
                else:
                    for c in cmds:
                        player.remove_command(c)
                    player.add_command(command)
            else:
                player.add_command(command)

    def _validate_convoy(
        self, player: Player, command: Command, actor_type: str, cmds: list
    ) -> bool:
        """Extrae la lógica compleja de convoyes fuera del modelo de datos."""
        if actor_type != "A" or command.command != "A":
            return False

        locations = self.game.map.provinces | self.game.map.seas
        fleets = [f for p in self.game.players for f in p.fleets]
        convoy = [
            c.target
            for c in player.commands
            if c.actor == command.actor and c.command == "A"
        ]

        if len(convoy) == len(cmds):
            for c in convoy:
                if c not in fleets:
                    break
            else:
                last_place = convoy[-1]
                destination = locations.get(command.target)
                if (
                    last_place in fleets
                    and command.target
                    in self.game.map.adjacent_locations(last_place, MovementMode.BOTH)
                    and (command.target in fleets or isinstance(destination, Province))
                ):
                    return True
        return False
