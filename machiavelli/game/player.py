from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from .command import Command
from .map import MovementMode, Province
from .scenario import Power, Scenario


class TurnType(Enum):
    """Representa el tipo de fase o turno actual en la partida."""

    MAINTENANCE = "maintenance"
    CAMPAIGN = "campaign"


@dataclass
class Player:
    """Representa a un jugador de la partida.

    En esta clase guardaremos lo necesario para identificar al jugador y contactarle si
    fuera necesario, así como el estado de sus ejércitos, provincias y recursos.

    Attributes:
        game_id (str): Identificador de la partida a la que pertenece el jugador.
        player_id (str): Identificador único del jugador.
        discord_id (int): Identificador de usuario de Discord.
        controlled_locations (list[str]): Lista de id de localizaciones controladas.
        armies (list[str]): Lista de id de localizaciones en que están los Ejércitos.
        fleets (list[str]): Lista de id de localizaciones en que se sitúan las Flotas.
        garrisons (list[str]): Lista de id de localizaciones con Guarniciones.
        ass_counters (list[str]): Lista de fichas de asesinatos.
        ducats (int): Ducados del jugador.
        rebelled_provinces (list[str]): Lista de id de provincias con rebelión.
        rebelled_cities (list[str]): Lista de id ciudades con rebelión.
        home_countries (list[str]): Lista de naciones natales que controla el jugador.
        power_id (str): Id de la potencia que maneja el jugador.
        commands (list[Command]): Lista de comandos del jugador.
    """

    game_id: str
    player_id: str
    discord_id: int | None = None
    controlled_locations: list[str] = field(default_factory=list)
    armies: list[str] = field(default_factory=list)
    fleets: list[str] = field(default_factory=list)
    garrisons: list[str] = field(default_factory=list)
    ass_counters: list[str] = field(default_factory=list)
    ducats: int = 0
    rebelled_provinces: list[str] = field(default_factory=list)
    rebelled_cities: list[str] = field(default_factory=list)
    home_countries: list[str] = field(default_factory=list)
    power_id: str | None = None
    commands: list[Command] = field(default_factory=list)

    def assign_power(self, power_id: str, power: Power, power_ids: list[str]):
        """Asigna una potencia al jugador e inicializa sus valores.

        Args:
            power_id (str): identificador de la potencia.
            power (Power): datos de la potencia.
            power_ids (str): listado de ids de potencias del escenario.
        """
        self.power_id = power_id
        self.home_countries = power.home_countries
        self.controlled_locations = power.controlled_provinces.copy()
        self.armies = power.armies.copy()
        self.fleets = power.fleets.copy()
        self.garrisons = power.garrisons.copy()

        # Asigna las fichas de asesionato
        self.ass_counters = [pid for pid in power_ids if pid != power_id]

    def hc_provinces(self, scenario: Scenario):
        """Devuelve los códigos de las provincias natales del jugador"""
        # Provincias de los home countries del jugador
        provinces = scenario.home_countries_provinces(self.home_countries)

        return [p for p in self.controlled_locations if p in provinces]

    def nonhc_provinces(self, scenario: Scenario):
        """Devuelve los códigos de las provincias no natales del jugador"""
        # Provincias de los home countries del jugador
        provinces = scenario.home_countries_provinces(self.home_countries)

        return [p for p in self.controlled_locations if p not in provinces]

    def cmd_add_command(self, turn_type: TurnType, command: Command) -> list[str]:
        """Añade o modifica una orden del jugador"""
        report = []

        # Reportamos la orden recibida
        report.append(f"Orden `{command}` enviada.")

        if turn_type == TurnType.MAINTENANCE:
            # Primer turno de la primavera, mantenimiento
            # Busco si ya existe un comando para el mismo actor
            current_cmd = [c for c in self.commands if c.actor == command.actor]
            if current_cmd:
                ### Si lo hay, sustituyo el comando
                assert len(current_cmd) == 1
                report.append(f"Sustituye la orden anterior `{current_cmd[0]}`.")
                current_cmd[0].command = command.command
                current_cmd[0].target = command.target

                # Si es una unidad recién creada y elijo "D" como orden, borra la orden
                actor_type, actor_id = command.actor.split()

                if (
                    (actor_type == "A" and actor_id not in self.armies)
                    or (actor_type == "F" and actor_id not in self.fleets)
                    or (actor_type == "G" and actor_id not in self.garrisons)
                ) and (command.command == "D"):
                    self.commands.remove(current_cmd[0])
            else:
                if command.command != "D":
                    ### Nuevo actor, añado el comando
                    self.commands.append(command)
        else:
            # Campaña
            actor_type, actor_id = command.actor.split()

            if actor_type == "E":
                # Buscamos si el gasto ya estaba registrado
                expense = next(
                    (
                        c
                        for c in self.commands
                        if c.actor == command.actor and c.target == command.target
                    ),
                    None,
                )

                if expense:
                    if int(command.command) == 0:
                        self.commands.remove(expense)
                    else:
                        expense.command = command.command
                else:
                    expense_count = sum(
                        command.actor.startswith("E ") for command in self.commands
                    )
                    if expense_count >= 4:
                        raise TooManyExpenses(
                            message="Solo se permiten hasta cuatro gastos por campaña"
                        )
                    else:
                        self.commands.append(command)
            else:
                # Buscamos si el actor ya estaba registrado
                cmds = [c for c in self.commands if c.actor == command.actor]

                if cmds:
                    # Y ahora comprobamos si hay convoy
                    is_convoy = False
                    locations = self.game.map.provinces | self.game.map.seas

                    if actor_type == "A" and command.command == "A":
                        fleets = [f for p in self.game.players for f in p.fleets]
                        convoy = [
                            c.target
                            for c in self.commands
                            if c.actor == command.actor and c.command == "A"
                        ]
                        if len(convoy) == len(cmds):
                            for c in convoy:
                                if c not in fleets:
                                    break
                            else:
                                # Tenemos un convoy, vamos a ver si el último destino es válido
                                last_place = convoy[-1]
                                destination = locations[command.target]
                                if (
                                    last_place in fleets
                                    and command.target
                                    in self.game.map.adjacent_locations(
                                        last_place, MovementMode.BOTH
                                    )
                                    and (
                                        command.target in fleets
                                        or isinstance(destination, Province)
                                    )
                                ):
                                    is_convoy = True
                    # Ya lo tenemos. Ahora, si es convoy añadimos el comando, sino sustituimos lo anterior
                    if is_convoy:
                        self.commands.append(command)
                    else:
                        # Borramos los anteriores
                        self.commands = [c for c in self.commands if c not in cmds]
                        self.commands.append(command)
                else:
                    # Nueva orden, solo la registramos
                    self.commands.append(command)

        # Reportamos las órdenes hasta ahora
        report.append("**Órdenes recibidas hasta ahora:**")
        for c in self.commands:
            report.append(f"`{c}`")

        return report
