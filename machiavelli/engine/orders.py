"""Order submission and replacement rules."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Self

from machiavelli.engine.exceptions import TooManyExpenses
from machiavelli.game.map import MovementMode, Province
from machiavelli.game.player import TurnType

if TYPE_CHECKING:
    from machiavelli.game.command import Command
    from machiavelli.game.game import Game
    from machiavelli.game.player import Player


@dataclass(frozen=True, slots=True)
class CommandSnapshot:
    """Immutable command data captured before or after an order mutation."""

    actor: str
    command: str
    target: str | None

    @classmethod
    def from_command(cls, command: Command) -> Self:
        """Capture the primitive fields required by service-layer reporting."""
        return cls(
            actor=command.actor,
            command=command.command,
            target=command.target,
        )


class OrderChangeKind(Enum):
    """Describe how an existing registered order changed."""

    REPLACED = "replaced"
    REMOVED = "removed"


@dataclass(frozen=True, slots=True)
class OrderChange:
    """One structured change to an order that existed before submission."""

    kind: OrderChangeKind
    previous: CommandSnapshot


@dataclass(frozen=True, slots=True)
class OrderProcessingResult:
    """Structured result of registering one command."""

    submitted: CommandSnapshot
    changes: tuple[OrderChange, ...]
    commands: tuple[CommandSnapshot, ...]


class OrderProcessor:
    """Validate and register orders according to the active turn type."""

    def __init__(self, game: Game) -> None:
        self.game = game

    def process_command(
        self,
        player: Player,
        turn_type: TurnType,
        command: Command,
    ) -> OrderProcessingResult:
        """Register one order and return only structured domain data."""
        submitted = CommandSnapshot.from_command(command)

        if turn_type == TurnType.MAINTENANCE:
            changes = self._handle_maintenance_command(player, command)
        else:
            changes = self._handle_campaign_command(player, command)

        return OrderProcessingResult(
            submitted=submitted,
            changes=changes,
            commands=tuple(
                CommandSnapshot.from_command(registered)
                for registered in player.commands
            ),
        )

    def _handle_maintenance_command(
        self,
        player: Player,
        command: Command,
    ) -> tuple[OrderChange, ...]:
        """Register a maintenance order, keeping at most one row per actor."""
        current_commands = [
            current for current in player.commands if current.actor == command.actor
        ]
        if len(current_commands) > 1:
            raise ValueError(
                f"Se encontraron múltiples comandos para el actor '{command.actor}'"
            )

        if not current_commands:
            if command.command != "D":
                player.add_command(command)
            return ()

        current = current_commands[0]
        previous = CommandSnapshot.from_command(current)
        current.command = command.command
        current.target = command.target

        actor_type, actor_id = command.actor.split()
        is_new_unit = (
            (actor_type == "A" and actor_id not in player.armies)
            or (actor_type == "F" and actor_id not in player.fleets)
            or (actor_type == "G" and actor_id not in player.garrisons)
        )
        if is_new_unit and command.command == "D":
            player.remove_command(current)

        return (OrderChange(OrderChangeKind.REPLACED, previous),)

    def _handle_campaign_command(
        self,
        player: Player,
        command: Command,
    ) -> tuple[OrderChange, ...]:
        """Register a campaign order, expense update, or convoy segment."""
        actor_type, _actor_id = command.actor.split()
        if actor_type == "E":
            return self._handle_expense_command(player, command)

        current_commands = [
            current for current in player.commands if current.actor == command.actor
        ]
        if not current_commands:
            player.add_command(command)
            return ()

        if self._validate_convoy(player, command, actor_type, current_commands):
            player.add_command(command)
            return ()

        changes = tuple(
            OrderChange(
                kind=OrderChangeKind.REPLACED,
                previous=CommandSnapshot.from_command(current),
            )
            for current in current_commands
        )
        for current in current_commands:
            player.remove_command(current)
        player.add_command(command)
        return changes

    def _handle_expense_command(
        self,
        player: Player,
        command: Command,
    ) -> tuple[OrderChange, ...]:
        """Create, update, or remove one campaign expense."""
        expense = next(
            (
                current
                for current in player.commands
                if current.actor == command.actor and current.target == command.target
            ),
            None,
        )
        if expense is not None:
            previous = CommandSnapshot.from_command(expense)
            if int(command.command) == 0:
                player.remove_command(expense)
                return (OrderChange(OrderChangeKind.REMOVED, previous),)

            expense.command = command.command
            return (OrderChange(OrderChangeKind.REPLACED, previous),)

        expense_count = sum(
            current.actor.startswith("E ") for current in player.commands
        )
        if expense_count >= 4:
            raise TooManyExpenses()

        player.add_command(command)
        return ()

    def _validate_convoy(
        self,
        player: Player,
        command: Command,
        actor_type: str,
        current_commands: list[Command],
    ) -> bool:
        """Return whether ``command`` extends a syntactically valid convoy route."""
        if actor_type != "A" or command.command != "A" or command.target is None:
            return False

        game_map = self.game.require_map()
        locations = game_map.provinces | game_map.seas
        fleets = [fleet for owner in self.game.players for fleet in owner.fleets]
        convoy = [
            current.target
            for current in player.commands
            if current.actor == command.actor and current.command == "A"
        ]

        if len(convoy) != len(current_commands):
            return False
        if not all(location in fleets for location in convoy):
            return False

        last_place = convoy[-1]
        if last_place is None:
            return False

        destination = locations.get(command.target)
        return (
            last_place in fleets
            and command.target
            in game_map.adjacent_locations(last_place, MovementMode.BOTH)
            and (command.target in fleets or isinstance(destination, Province))
        )
