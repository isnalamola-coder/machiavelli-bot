# machiavelli/services/command_reporter.py

from __future__ import annotations

from typing import TYPE_CHECKING

from machiavelli.game.tables import GameTables

if TYPE_CHECKING:
    from machiavelli.game.command import Command
    from machiavelli.game.map import GameMap


class CommandReporter:
    """Responsable exclusivo de generar representaciones legibles de las órdenes."""

    @staticmethod
    def format_report(command: Command, game_map: GameMap, turn_number: int) -> str:
        """Genera una representación legible del comando.

        Args:
            command (Command): La orden a formatear.
            game_map (GameMap): Instancia del mapa de la partida para resolver nombres.
            turn_number (int): Turno para determinar si es mantenimiento o campaña.

        Returns:
            str: Descripción formateada de la orden separada por '|'.
        """
        locations = game_map.provinces | game_map.seas
        provinces = game_map.provinces

        try:
            report = []
            target_type = None

            # Parsear Actor
            actor_type, actor_id = command.actor.split()

            if actor_type in ("A", "F", "G"):
                actor_name = GameTables.actors.get(actor_type, actor_type)
                loc_name = (
                    locations[actor_id].name if actor_id in locations else actor_id
                )
                report.append(f"{actor_name} de {loc_name}")
            elif actor_type == "E":
                expense_info = GameTables.expenses.get(actor_id, {})
                report.append(expense_info.get("text", actor_id))
                target_type = expense_info.get("target_type")

            # Parsear Comando
            if actor_type in ("A", "F", "G"):
                is_spring_maintenance = turn_number % 4 == 1
                orders_table = (
                    GameTables.maintenance_orders
                    if is_spring_maintenance
                    else GameTables.military_orders
                )
                cmd_info = orders_table.get(command.command, {})
                report.append(cmd_info.get("text", command.command))
                target_type = cmd_info.get("target_type")

            # Parsear Target
            if target_type:
                CommandReporter._append_target_report(
                    report, command, target_type, locations, provinces
                )

            if actor_type == "E":
                report.append(f"{command.command} ducados")

            return "|".join(report)

        except (KeyError, ValueError, IndexError) as err:
            return f"Orden inválida ({err})"

    @staticmethod
    def _append_target_report(
        report: list[str],
        command: Command,
        target_type: str,
        locations: dict,
        provinces: dict,
    ) -> None:
        """Método auxiliar para formatear la sección del objetivo del comando."""
        if target_type == "army_ext":
            parts = command.target.split()
            actor_name = GameTables.actors.get(parts[0], parts[0])
            prov_name = provinces[parts[1]].name if parts[1] in provinces else parts[1]
            if len(parts) > 2:
                power_name = GameTables.powers.get(parts[2], parts[2])
                report.append(f"{actor_name} de {prov_name} ({power_name})")
            else:
                report.append(f"{actor_name} de {prov_name}")

        elif target_type == "location":
            report.append(
                locations[command.target].name
                if command.target in locations
                else command.target
            )

        elif target_type == "location_ext":
            parts = command.target.split()
            loc_name = locations[parts[0]].name if parts[0] in locations else parts[0]
            if len(parts) > 1:
                power_name = GameTables.powers.get(parts[1], parts[1])
                report.append(f"{loc_name} ({power_name})")
            else:
                report.append(loc_name)

        elif target_type == "province":
            report.append(
                provinces[command.target].name
                if command.target in provinces
                else command.target
            )

        elif target_type == "power":
            report.append(GameTables.powers.get(command.target, command.target))

        elif target_type == "unit":
            parts = command.target.split()
            actor_name = GameTables.actors.get(parts[0], parts[0])
            prov_name = provinces[parts[1]].name if parts[1] in provinces else parts[1]
            report.append(f"{actor_name} de {prov_name}")

        elif target_type == "unit_type":
            if command.target == "0":
                report.append("Desbandar")
            else:
                report.append(GameTables.actors.get(command.target, command.target))
