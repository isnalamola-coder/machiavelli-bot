"""Discord-ready reporting for structured order-processing results."""

from __future__ import annotations

from machiavelli.engine.orders import OrderChangeKind, OrderProcessingResult
from machiavelli.game.map import Map

from .command_reporter import CommandReporter


class OrderReporter:
    """Render order-processing data without coupling the engine to Discord markup."""

    @staticmethod
    def generate(
        result: OrderProcessingResult,
        game_map: Map,
        turn_number: int,
    ) -> list[str]:
        """Return the historical order acknowledgement in stable order."""
        submitted = CommandReporter.format_report(
            result.submitted,
            game_map,
            turn_number,
        )
        report = [f"Orden `{submitted}` enviada."]

        for change in result.changes:
            previous = CommandReporter.format_report(
                change.previous,
                game_map,
                turn_number,
            )
            match change.kind:
                case OrderChangeKind.REPLACED:
                    report.append(f"Sustituye la orden anterior `{previous}`.")
                case OrderChangeKind.REMOVED:
                    report.append(f"Elimina el gasto anterior `{previous}`.")

        report.append("**Órdenes recibidas hasta ahora:**")
        report.extend(
            f"`{CommandReporter.format_report(command, game_map, turn_number)}`"
            for command in result.commands
        )
        return report
