# machiavelli/game.py
from __future__ import annotations

import json
import random
import sqlite3
from dataclasses import dataclass, field, fields
from datetime import datetime, timedelta
from typing import Self

from machiavelli.events import TurnEvent

from .command import Command
from .exceptions import (
    DuplicatedGameException,
    FailedToStartError,
    GameNotFoundException,
)
from .map import Map, MovementMode, Sea
from .player import Player
from .scenario import Power, Scenario
from .tables import GameTables


@dataclass
class _HistoricalCommand:
    """Representa un comando en la partida.

    En esta clase guardaremos los comandos de los jugadores. Además guardamos
    datos sobre el jugador y la partida necesarios para interactuar con la base
    de datos.

    El formato de los comandos va a ser el siguiente:

    - actor:
        A <provincia>: el ejército que esté situado en esa provincia.
        F <provincia>: la flota situada en sa provincia.
        G <provincia>: la guarnición que esté situada en esa provincia.
        E <gasto>    : un gasto/soborno/etc.
    - command:
        + En la fase de mantenimiento:
            actor es una unidad
            * M: mantener
            * D: desbandar
            * C: crear
        + En las campañas:
            actor es una unidad
            * las de GameTables.military_orders
            actor es un gasto
            * el número de ducados a gastar

    Attributes:
        game(Game)    : Referencia al Game a que pertenece este comando.
        player(Player): Referencia al Player al que pertenece este comando.
        actor (str)   : Unidad, provincia o facción que está actuando.
        command (str) : Comando que se está ejecutando.
        target (str)  : Objetivo del comando.
    """

    game: Game
    player: Player
    actor: str
    command: str
    target: str

    def save(self, conn: sqlite3.Connection):
        """Guarda los datos del comando"""
        cursor = conn.cursor()

        cursor.execute(
            "INSERT INTO commands "
            "(game_id, player_id, actor, command, target) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                self.game.database_id,
                self.player.player_id,
                self.actor,
                self.command,
                self.target,
            ),
        )

    def is_valid_expense(
        self, allowed_types: set[str] | list[str] | None = None
    ) -> bool:
        """Comprueba si el comando es un gasto válido y bien formado."""
        actor = self.actor.split()
        if len(actor) != 2 or actor[0] != "E":
            return False
        if allowed_types is None:
            return actor[1] in GameTables.expenses
        else:
            return actor[1] in allowed_types

    @classmethod
    def load_commands(
        cls, conn: sqlite3.Connection, game: Game, player: Player
    ) -> list[Self]:
        """Busca y devuelve todos los comandos de un jugador.

        Args:
            conn (sqlite3.Connection): Conexión activa a la BBDD.
            game (Game)              : Referencia a la partida actual.
            player (Player)          : Referencia al jugador actual.

        Returns:
            list[Command]: Lista de objetos Command instanciados.
        """
        cursor = conn.cursor()
        cursor.execute(
            "SELECT actor, command, target FROM commands "
            "WHERE game_id = ? AND player_id = ? ORDER BY commands.id ASC",
            (game.database_id, player.player_id),
        )
        rows = cursor.fetchall()

        commands = []
        for row in rows:
            commands.append(
                cls(game, player, actor=row[0], command=row[1], target=row[2])
            )

        return commands

    def __str__(self) -> str:
        """Devuelve una representación legible del comando"""

        provinces = self.game.map.provinces
        seas = self.game.map.seas

        locations = provinces | seas

        try:
            report = []

            # target_type will be set from action
            target_type = None

            # Actor
            # A/F/G/E (Army/Fleet/Garrison/Expense)
            actor_type, actor_id = self.actor.split()

            if actor_type in ("A", "F", "G"):
                # Army/Fleet/Garrison
                report.append(
                    f"{GameTables.actors[actor_type]} de {locations[actor_id].name}"
                )
            elif actor_type == "E":
                # Expense
                report.append(f"{GameTables.expenses[actor_id]['text']}")
                target_type = GameTables.expenses[actor_id]["target_type"]

            # Command
            # For A/F/G it is maintenance_orders (spring maintenance turn)
            # or military_orders (campaigns).
            # For E it is the ammount of money to spend
            if actor_type in ("A", "F", "G"):
                # Army/Fleet/Garrison
                if self.game.turn_number % 4 == 1:
                    # Spring maintenance turn
                    report.append(GameTables.maintenance_orders[self.command]["text"])
                    target_type = GameTables.maintenance_orders[self.command][
                        "target_type"
                    ]
                else:
                    # Campaign
                    report.append(GameTables.military_orders[self.command]["text"])
                    target_type = GameTables.military_orders[self.command][
                        "target_type"
                    ]

            # Target. Target types are
            # None
            # army_ext    : an army from another faction (transport orders)
            # location    : a location (province/sea)
            # location_ext: a location (province/sea), optionally with a
            #               faction descriptor for support orders
            # province    : a province
            # power       : una potencia (para su uso para los asesinatos)
            # unit        : una unidad cualquiera (ejército/flota/guarnición)
            if target_type:
                if target_type == "army_ext":
                    army_ext = self.target.split()
                    if len(army_ext) > 2:
                        report.append(
                            f"{GameTables.actors[army_ext[0]]} "
                            f"de {provinces[army_ext[1]].name} "
                            f"({GameTables.powers[army_ext[2]]})"
                        )
                    else:
                        report.append(
                            f"{GameTables.actors[army_ext[0]]} "
                            f"de {provinces[army_ext[1]].name}"
                        )
                elif target_type == "location":
                    report.append(locations[self.target].name)
                elif target_type == "location_ext":
                    location_ext = self.target.split()
                    if len(location_ext) > 1:
                        report.append(
                            f"{locations[location_ext[0]].name} "
                            f"({GameTables.powers[location_ext[1]]})"
                        )
                    else:
                        report.append(f"{locations[location_ext[0]].name}")
                elif target_type == "province":
                    report.append(provinces[self.target].name)
                elif target_type == "power":
                    report.append(GameTables.powers[self.target])
                elif target_type == "unit":
                    unit_ext = self.target.split()
                    report.append(
                        f"{GameTables.actors[unit_ext[0]]} "
                        f"de {provinces[unit_ext[1]].name}"
                    )
                elif target_type == "unit_type":
                    if self.target == "0":
                        report.append("Desbandar")
                    else:
                        report.append(f"{GameTables.actors[self.target]}")

            if actor_type == "E":
                report.append(f"{self.command} ducados")

            return "|".join(report)
        except Exception:
            # Alguna orden mal formada
            return "Orden inválida"


@dataclass
class _HistoricalPlayer:
    """Representa a un jugador de la partida.

    En esta clase guardaremos todo lo necesario para identificar al jugador y
    contactarle si fuera necesario, así como el estado de sus ejércitos,
    provincias y recursos.

    Attributes:
        game (Game)                     : Partida a la que pertenece el jugador.
        player_id (str)                 : Identificador único del jugador.
        discord_id (int)                : Identificador de usuario de Discord.
        controlled_locations (list[str]): Localizaciones controladas.
        armies (list[str])              : Localizaciones de los ejércitos.
        fleets (list[str])              : Localizaciones de las flotas.
        garrisons (list[str])           : Localizaciones de las guarniciones.
        ass_counters (list[str])        : Lista de fichas de asesinatos.
        ducats (int)                    : Ducados del jugador.
        rebelled_provinces (list[str])  : Provincias rebeladas.
        rebelled_cities (list[str])     : Ciudades rebeladas.
        home_countries (list[str])      : Naciones natales controladas.
        power (str)                     : Potencia que maneja el jugador
        commands (list[Command])        : Lista de comandos del jugador
    """

    game: Game
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
    power: str | None = None
    commands: list[Command] = field(default_factory=list)

    def assign_power(self, power: Power):
        """Asigna una potencia al jugador e inicializa sus valores"""
        self.power = power.id
        self.home_countries = power.home_countries
        self.controlled_locations = power.controlled_provinces.copy()
        self.armies = power.armies.copy()
        self.fleets = power.fleets.copy()
        self.garrisons = power.garrisons.copy()

    def save(self, conn: sqlite3.Connection) -> None:
        """Guarda o actualiza al jugador en la base de datos vinculándolo a una partida.

        Al usar ON CONFLICT, si el par (game_id, player_id) ya existe,
        actualizará el discord_id con el valor actual en memoria.

        Args:
            conn (sqlite3.Connection): La conexión a la base de datos.
        """
        cursor = conn.cursor()

        # Convertimos la lista de controlled_locations a un string JSON
        locations_json = json.dumps(self.controlled_locations)
        armies_json = json.dumps(self.armies)
        fleets_json = json.dumps(self.fleets)
        garrisons_json = json.dumps(self.garrisons)
        ass_counters_json = json.dumps(self.ass_counters)
        rebelled_provinces_json = json.dumps(self.rebelled_provinces)
        rebelled_cities_json = json.dumps(self.rebelled_cities)
        home_countries_json = json.dumps(self.home_countries)

        cursor.execute(
            """
            INSERT INTO players (
                game_id, player_id, discord_id, controlled_locations,
                armies, fleets, garrisons, ass_counters, ducats,
                rebelled_provinces, rebelled_cities, home_countries, power
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(game_id, player_id) DO UPDATE SET
                discord_id = excluded.discord_id,
                controlled_locations = excluded.controlled_locations,
                armies = excluded.armies,
                fleets = excluded.fleets,
                garrisons = excluded.garrisons,
                ass_counters = excluded.ass_counters,
                ducats = excluded.ducats,
                rebelled_provinces = excluded.rebelled_provinces,
                rebelled_cities = excluded.rebelled_cities,
                home_countries = excluded.home_countries,
                power = excluded.power
            """,
            (
                self.game.database_id,
                self.player_id,
                self.discord_id,
                locations_json,
                armies_json,
                fleets_json,
                garrisons_json,
                ass_counters_json,
                self.ducats,
                rebelled_provinces_json,
                rebelled_cities_json,
                home_countries_json,
                self.power,
            ),
        )

        # Guarda los comandos del jugador
        self.save_commands(conn)

    def hc_provinces(self):
        """Devuelve los códigos de las provincias natales del jugador"""
        # Provincias de los home countries del jugador
        provinces = [
            p
            for hc in self.home_countries
            for p in self.game.scenario.home_countries[hc].provinces
        ]

        return [p for p in self.controlled_locations if p in provinces]

    def nonhc_provinces(self):
        """Devuelve los códigos de las provincias no natales del jugador"""
        # Provincias de los home countries del jugador
        provinces = [
            p
            for hc in self.home_countries
            for p in self.game.scenario.home_countries[hc].provinces
        ]

        return [p for p in self.controlled_locations if p not in provinces]

    def set_default_commands(self):
        """Asigna órdenes por defecto a todas las unidades que no tengan"""
        actors = [c.actor for c in self.commands]

        for u in self.armies:
            if f"A {u}" not in actors:
                self.commands.append(Command(self.game, self, f"A {u}", "M", None))

        for u in self.fleets:
            if f"F {u}" not in actors:
                self.commands.append(Command(self.game, self, f"F {u}", "M", None))

        for u in self.garrisons:
            if f"G {u}" not in actors:
                self.commands.append(Command(self.game, self, f"G {u}", "M", None))

    def save_commands(self, conn: sqlite3.Connection) -> None:
        """Guarda o actualiza las órdenes del jugador

        Args:
            conn (sqlite3.Connection): La conexión a la base de datos.
        """
        cursor = conn.cursor()

        # Guarda los comandos del jugador. Primero limpia los datos anteriores
        cursor.execute(
            "DELETE FROM commands WHERE game_id = ? AND player_id = ?",
            (self.game.database_id, self.player_id),
        )

        for command in self.commands:
            command.save(conn)

    def player_report(self) -> list[str]:
        """Genera las líneas del informe de situación para el jugador."""
        map = self.game.map
        besieges = self.game.besieges

        report = []
        report.append(
            f"### 🏰 __**{GameTables.powers[self.power]} (<@{self.discord_id}>)**__"
        )

        if self.home_countries:
            # Países natales
            hc_names = [GameTables.powers[p] for p in self.home_countries]
            if len(self.home_countries) > 1:
                hc = " y ".join([", ".join(hc_names[0:-1]), hc_names[-1]])
            else:
                hc = hc_names[0]
            report.append(f"> 👑 **Naciones controladas:** {hc}")

            # Recursos
            ass_names = [GameTables.powers[p] for p in self.ass_counters]
            if len(self.ass_counters) == 0:
                assassination = "Ninguna"
            elif len(self.ass_counters) > 1:
                assassination = " y ".join([", ".join(ass_names[0:-1]), ass_names[-1]])
            else:
                assassination = ass_names[0]
            report.append(f"> 💰 **Recursos:** {self.ducats} ducados.")
            report.append(
                f"> 🗡️ **Fichas de asesinato ({len(ass_names)}):** {assassination}"
            )

            # Provincias controladas
            province_names = [
                p.name
                for k, p in map.provinces.items()
                if k in self.controlled_locations
            ]
            if len(self.controlled_locations) == 0:
                provinces = "Ninguna"
            elif len(self.controlled_locations) > 1:
                provinces = " y ".join(
                    [", ".join(province_names[0:-1]), province_names[-1]]
                )
            else:
                provinces = province_names[0]
            report.append(f"> 🗺️ **Provincias controladas:** {provinces}")

            # Rebeliones
            if self.rebelled_provinces or self.rebelled_cities:
                province_names = [
                    p.name
                    for k, p in map.provinces.items()
                    if k in self.rebelled_provinces
                ]
                city_names = [
                    f"{p.name} (ciudad)"
                    for k, p in map.provinces.items()
                    if k in self.rebelled_cities
                ]
                names = province_names + city_names

                if len(names) > 1:
                    provinces = " y ".join([", ".join(names[0:-1]), names[-1]])
                else:
                    provinces = names[0]

                report.append(f"> 🔥 **Rebeliones:** {provinces}")

            # Ejércitos
            province_names = [
                " ".join([p.name, "(asediando)"]) if k in besieges else p.name
                for k, p in map.provinces.items()
                if k in self.armies
            ]
            if len(province_names) == 0:
                provinces = "Ninguno"
            elif len(province_names) > 1:
                provinces = " y ".join(
                    [", ".join(province_names[0:-1]), province_names[-1]]
                )
            else:
                provinces = province_names[0]
            report.append(f"> ⚔️ **Ejércitos:** {provinces}")

            # Flotas
            locations = map.provinces | map.seas
            province_names = [
                " ".join([p.name, "(asediando)"]) if k in besieges else p.name
                for k, p in locations.items()
                if k in self.fleets
            ]
            if len(province_names) == 0:
                provinces = "Ninguna"
            elif len(province_names) > 1:
                provinces = " y ".join(
                    [", ".join(province_names[0:-1]), province_names[-1]]
                )
            else:
                provinces = province_names[0]
            report.append(f"> ⚓ **Flotas:** {provinces}")

            # Guarniciones
            province_names = [
                p.name for k, p in map.provinces.items() if k in self.garrisons
            ]
            if len(province_names) == 0:
                provinces = "Ninguna"
            elif len(province_names) > 1:
                provinces = " y ".join(
                    [", ".join(province_names[0:-1]), province_names[-1]]
                )
            else:
                provinces = province_names[0]
            report.append(f"> 🛡️ **Guarniciones:** {provinces}")
        else:
            report.append("> ❌ **Eliminado**")

        return report

    # Funciones para la precarga de órdenes disponibles
    def cmd_available_actors(self) -> list[tuple[str, str]]:
        """Devuelve la lista de actores disponibles para una orden.

        Los actores se devuelven como pares de código y texto visible. Ejemplo:
        ("A veron", "Ejército de Verona")
        """
        # Primero, tenemos que saber si estamos en una campaña o en el mantenimiento
        choices = []

        map = self.game.map
        provinces = self.game.map.provinces
        locations = self.game.map.provinces | self.game.map.seas

        if self.game.turn_number % 4 == 1:
            # Primer turno de la primavera, mantenimiento

            # Los actores son todos las unidades del jugador
            for a in self.armies:
                choices.append((f"A {a}", f"Ejército en {provinces[a].name}"))
            for a in self.fleets:
                choices.append((f"F {a}", f"Flota en {locations[a].name}"))
            for a in self.garrisons:
                choices.append((f"G {a}", f"Guarnición en {provinces[a].name}"))

            # También cualquier provincia natal con ciudad bajo su control.
            home_countries_cities = [
                p
                for hc_id in self.home_countries
                if hc_id in self.game.scenario.home_countries
                for p in self.game.scenario.home_countries[hc_id].provinces
                if p in self.controlled_locations
                and map.provinces[p].city in ("city", "fortified")
            ]

            for p in home_countries_cities:
                if (
                    p not in self.armies
                    and p not in self.fleets
                    and (p not in self.garrisons)
                ):
                    choices.append(
                        (f"A {p}", f"Ejército en {provinces[p].name} (reclutar)")
                    )
                    if map.provinces[p].has_port:
                        choices.append(
                            (f"F {p}", f"Flota en {provinces[p].name} (reclutar)")
                        )
                if p not in self.garrisons and map.provinces[p].city == "fortified":
                    choices.append(
                        (f"G {p}", f"Guarnición en {provinces[p].name} (reclutar)")
                    )
        else:
            # Resto de turnos, campaña

            # Los actores son todas las unidades del jugador
            for a in self.armies:
                choices.append((f"A {a}", f"Ejército en {provinces[a].name}"))
            for a in self.fleets:
                choices.append((f"F {a}", f"Flota en {locations[a].name}"))
            for a in self.garrisons:
                choices.append((f"G {a}", f"Guarnición en {provinces[a].name}"))

            # Provincias adyacentes a unidades del jugador.
            # Para sobornos, cualquier tipo de unidad se considera adyacente.
            # independientemente del tipo de movimiento
            # Hay que tener en cuenta las provincias que tienen dos costas
            locations = self.game.map.provinces | self.game.map.seas
            unit_provinces = {p for p in self.armies}
            unit_provinces |= {p.split()[0] for p in self.fleets}
            unit_provinces |= {p for p in self.garrisons}
            unit_provinces |= {
                p for p in locations.keys() if p.split()[0] in unit_provinces
            }

            adjacent = {
                r.destination for a in unit_provinces for r in locations[a].land_routes
            }
            adjacent |= {
                r.destination.split()[0]
                for a in unit_provinces
                for r in locations[a].sea_routes
            }

            bribe_armies = [
                a
                for p in self.game.players
                for a in p.armies
                if p != self and a in adjacent
            ]
            bribe_fleets = [
                f
                for p in self.game.players
                for f in p.fleets
                if p != self and f.split()[0] in adjacent
            ]
            bribe_garrisons = [
                g
                for p in self.game.players
                for g in p.garrisons
                if p != self and g in adjacent
            ]
            bribe_independent = [
                g for g in self.game.independent_garrisons if g in adjacent
            ]

            # Y ahora añado las unidades susceptibles de ser sobornadas
            for a in bribe_armies:
                choices.append((f"A {a}", f"Ejército en {provinces[a].name}"))
            for a in bribe_fleets:
                choices.append((f"F {a}", f"Flota en {locations[a].name}"))
            for a in bribe_garrisons:
                choices.append((f"G {a}", f"Guarnición en {provinces[a].name}"))
            for a in bribe_independent:
                choices.append((f"G {a}", f"Guarnición en {provinces[a].name}"))

        return choices

    def cmd_available_commands(self, actor: str) -> list[tuple[str, str]]:
        """Devuelve los comandos disponibles para un actor.

        El actor se entrega como una cadena con su tipo e identificación.

        Los comandos se devuelven como pares de código y texto visible. Ejemplo:
        ("M", "Mantener").
        """
        # Primero, tenemos que saber si estamos en una campaña o en el mantenimiento
        choices = []

        if self.game.turn_number % 4 == 1:
            # Primer turno de la primavera, mantenimiento

            # Los actores son todos las unidades del jugador
            actor_type, actor_id = actor.split()

            # ¿Es nuevo?
            if (
                (actor_type == "A" and actor_id in self.armies)
                or (actor_type == "F" and actor_id in self.fleets)
                or (actor_type == "G" and actor_id in self.garrisons)
            ):
                # Es una unidad existente
                for c in ("M", "D"):
                    choices.append((c, GameTables.maintenance_orders[c]["text"]))
            else:
                # Es una unidad nueva. Permito "D"isolver para cancelar órdenes previas
                for c in ("R", "D"):
                    choices.append((c, GameTables.maintenance_orders[c]["text"]))
        else:
            # Campaña
            actor_type, actor_location = actor.split(maxsplit=1)
            actor_id = actor_location.split()[0]

            is_besieging = actor_id in self.game.besieges
            garrisons = [
                g for p in self.game.players for g in p.garrisons
            ] + self.game.independent_garrisons
            has_garrison = actor_id in garrisons
            province = self.game.map.provinces.get(actor_location)
            has_port = province.has_port if province else False

            if actor_type in ("A", "F") and not is_besieging:
                choices.append(("A", f"{GameTables.military_orders['A']['text']}"))
            if actor_type == "A" and has_garrison:
                choices.append(("B", f"{GameTables.military_orders['B']['text']}"))
            if actor_type == "F" and has_garrison and has_port:
                choices.append(("B", f"{GameTables.military_orders['B']['text']}"))
            choices.append(("H", f"{GameTables.military_orders['H']['text']}"))
            if actor_type in ("A", "F") and is_besieging:
                choices.append(("L", f"{GameTables.military_orders['L']['text']}"))
            choices.append(("S", f"{GameTables.military_orders['S']['text']}"))
            if actor_type == "F":
                choices.append(("T", f"{GameTables.military_orders['T']['text']}"))
            choices.append(("C", f"{GameTables.military_orders['C']['text']}"))

        return choices

    def cmd_available_targets(self, actor: str, command: str) -> list[tuple[str, str]]:
        """Devuelve los objetivos disponibles para un actor y comando.

        El actor contiene su tipo e identificación. El comando es su código.

        Los objetivos se devuelven como pares de código y texto visible. Ejemplo:
        ("M", "Mantener").
        """
        # Primero, tenemos que saber si estamos en una campaña o en el mantenimiento
        choices = []

        if self.game.turn_number % 4 == 1:
            # Primer turno de la primavera, mantenimiento
            choices.append(("", "Ninguno"))
        else:
            # Campaña
            map = self.game.map
            locations = map.provinces | map.seas

            actor_type, actor_location = actor.split(maxsplit=1)
            actor_id = actor_location.split()[0]

            if command in ("B", "H", "L"):
                # Sin objetivo (Asediar/Mantener/Levantar asedio)
                choices.append(("", "Ninguno"))
            elif command == "A":
                assert actor_type in ("A", "F")
                if actor_type == "A":
                    # Es un ejército, usar land_routes
                    for r in locations[actor_location].land_routes:
                        choices.append(
                            (r.destination, f"{locations[r.destination].name}")
                        )

                    # Además, tengo que considerar convoys (ie, ejércitos transportados)
                    fleets = [f for p in self.game.players for f in p.fleets]

                    convoy = [
                        c.target
                        for c in self.commands
                        if c.actor == actor and c.command == "A"
                    ]

                    # Un convoy exige flotas en todos los pasos intermedios.
                    # Las previas ya se comprobaron; queda validar la última.
                    if convoy:
                        # Comprobamos que hay flota en cada punto del convoy.
                        for s in convoy:
                            if s not in fleets:
                                break
                        else:
                            # Convoy completo: continuamos desde su último punto.
                            convoy_end = convoy[-1]
                            for r in map.adjacent_locations(
                                convoy_end, mode=MovementMode.BOTH
                            ):
                                if isinstance(locations[r], Sea):
                                    if r in fleets:
                                        # Un mar exige una flota presente.
                                        choices.append((r, f"{locations[r].name}"))
                                else:
                                    choices.append((r, f"{locations[r].name}"))
                        # Eliminamos duplicados
                        choices = list(dict.fromkeys(choices))
                    else:
                        # Un convoy nuevo exige flota en el primer destino.
                        for r in map.adjacent_locations(
                            actor_location, mode=MovementMode.BOTH
                        ):
                            if r in fleets:
                                choices.append((r, f"{locations[r].name}"))

                elif actor_type == "F":
                    # Es una flota, usar sea_routes
                    for r in locations[actor_location].sea_routes:
                        choices.append(
                            (r.destination, f"{locations[r.destination].name}")
                        )
            elif command == "S":
                # Apoyar lugares alcanzables y las facciones disponibles.
                if actor_type == "A":
                    for r in locations[actor_location].land_routes:
                        choices.append(
                            (r.destination, f"{locations[r.destination].name}")
                        )
                    # Y ahora, apoyando al resto de facciones
                    for r in locations[actor_location].land_routes:
                        for p in self.game.players:
                            if p != self:
                                choices.append(
                                    (
                                        f"{r.destination} ({p.power})",
                                        f"{locations[r.destination].name} "
                                        f"({GameTables.powers[p.power]})",
                                    )
                                )
                elif actor_type == "F":
                    for r in locations[actor_location].sea_routes:
                        choices.append(
                            (r.destination, f"{locations[r.destination].name}")
                        )
                    # Y ahora, apoyando al resto de facciones
                    for r in locations[actor_location].sea_routes:
                        for p in self.game.players:
                            if p != self:
                                choices.append(
                                    (
                                        f"{r.destination} ({p.power})",
                                        f"{locations[r.destination].name} "
                                        f"({GameTables.powers[p.power]})",
                                    )
                                )
                elif actor_type == "G":
                    # Las guarniciones solo pueden apoyar en su provincia
                    choices.append(
                        (actor_location, f"{locations[actor_location].name}")
                    )
                    for p in self.game.players:
                        if p != self:
                            choices.append(
                                (
                                    f"{actor_location} ({p.power})",
                                    f"{locations[actor_location].name} "
                                    f"({GameTables.powers[p.power]})",
                                )
                            )
            elif command == "T":
                assert actor_type in ("F")
                # Añadimos los ejércitos situados en provincias costeras.
                armies = [
                    a
                    for p in self.game.players
                    for a in p.armies
                    if locations[a].sea_routes
                ]
                for a in armies:
                    choices.append((f"A {a}", f"Ejército en {locations[a].name}"))
            elif command == "C":
                choices.append(("0", "Desbandar"))
                if locations[actor_id].city == "fortified":
                    # Las conversiones, en ciudades fortificadas
                    if actor_type == "G":
                        choices.append(("A", f"{GameTables.actors['A']}"))
                        if locations[actor_id].has_port:
                            choices.append(("F", f"{GameTables.actors['F']}"))
                    elif actor_type == "A" or locations[actor_id].has_port:
                        choices.append(("G", f"{GameTables.actors['G']}"))

        return choices

    # Funciones para la precarga de gastos disponibles
    def exp_available_expenses(self) -> list[tuple[str, str]]:
        """Devuelve la lista de gastos disponibles para un jugador.

        Los gastos se devuelven como pares de código y texto visible. Ejemplo:
        ("E B", "Pacificar rebelión")
        """
        choices = []

        # Solo los gastos que el jugador se puede permitir
        expenses = {
            k: e for k, e in GameTables.expenses.items() if e["cost"] <= self.ducats
        }

        # Provincias adyacentes a unidades del jugador.
        # Para sobornos, cualquier tipo de unidad se considera adyacente,
        # independientemente del tipo de movimiento.
        # Hay que tener en cuenta las provincias que tienen dos costas.
        locations = self.game.map.provinces | self.game.map.seas
        unit_provinces = {p for p in self.armies}
        unit_provinces |= {p.split()[0] for p in self.fleets}
        unit_provinces |= {p for p in self.garrisons}
        unit_provinces |= {
            p for p in locations.keys() if p.split()[0] in unit_provinces
        }

        adjacent = {
            r.destination for a in unit_provinces for r in locations[a].land_routes
        }
        adjacent |= {
            r.destination.split()[0]
            for a in unit_provinces
            for r in locations[a].sea_routes
        }

        bribe_armies = [
            a
            for p in self.game.players
            for a in p.armies
            if p != self and a in adjacent
        ]
        bribe_fleets = [
            f
            for p in self.game.players
            for f in p.fleets
            if p != self and f.split()[0] in adjacent
        ]
        bribe_garrisons = [
            g
            for p in self.game.players
            for g in p.garrisons
            if p != self and g in adjacent
        ]

        for key, expense in expenses.items():
            # Trataremos cada caso individualmente
            if key == "A" and self.game.famine:
                # Paliar hambruna
                choices.append((f"E {key}", f"{expense['text']}"))
            elif key == "B":
                # Pacificar rebelión
                rebellions = [
                    r
                    for p in self.game.players
                    for r in (p.rebelled_provinces + p.rebelled_cities)
                ]
                if rebellions:
                    choices.append((f"E {key}", f"{expense['text']}"))
            elif key == "C":
                # Comenzar rebelión en provincia no natal
                no_hc = [
                    pr
                    for p in self.game.players
                    for pr in p.nonhc_provinces()
                    if p != self
                    if pr not in p.rebelled_provinces
                    if pr not in p.rebelled_cities
                ]
                if no_hc:
                    choices.append((f"E {key}", f"{expense['text']}"))
            elif key == "D":
                # Comenzar rebelión en provincia natal
                hc = [
                    pr
                    for p in self.game.players
                    for pr in p.hc_provinces()
                    if p != self
                    if pr not in p.rebelled_provinces
                    if pr not in p.rebelled_cities
                ]
                if hc:
                    choices.append((f"E {key}", f"{expense['text']}"))
            elif key == "E":
                # Ordenar asesinato
                ass = [
                    p.power
                    for p in self.game.players
                    if p.home_countries
                    if p.power in self.ass_counters
                ]
                if ass:
                    choices.append((f"E {key}", f"{expense['text']}"))
            elif key == "F":
                # Contra-soborno
                choices.append((f"E {key}", f"{expense['text']}"))
            elif key in ("G", "H"):
                # Desbandar/Comprar guarnición autónoma
                garrisons = [
                    g for g in self.game.independent_garrisons if g in adjacent
                ]
                if garrisons:
                    choices.append((f"E {key}", f"{expense['text']}"))
            elif key == "I":
                # Convertir guarnición en autónoma
                if bribe_garrisons:
                    choices.append((f"E {key}", f"{expense['text']}"))
            elif key == "J":
                # Desbandar unidad
                if bribe_armies or bribe_fleets or bribe_garrisons:
                    choices.append((f"E {key}", f"{expense['text']}"))
            elif key == "K":
                # Comprar ejército o flota
                if bribe_armies or bribe_fleets:
                    choices.append((f"E {key}", f"{expense['text']}"))

        return choices

    def exp_available_targets(self, expense: str) -> list[tuple[str, str]]:
        """Devuelve los objetivos disponibles para un gasto.

        Los objetivos se devuelven como pares de código y texto. Ejemplo:
        ("E B", "Pacificar rebelión")
        """
        choices = []

        # Recuperamos los datos del gasto
        _, key = expense.split()
        map = self.game.map

        # Provincias adyacentes a unidades del jugador.
        # Para sobornos, cualquier tipo de unidad se considera adyacente,
        # independientemente del tipo de movimiento.
        # Hay que tener en cuenta las provincias que tienen dos costas
        locations = self.game.map.provinces | self.game.map.seas
        unit_provinces = {p for p in self.armies}
        unit_provinces |= {p.split()[0] for p in self.fleets}
        unit_provinces |= {p for p in self.garrisons}
        unit_provinces |= {
            p for p in locations.keys() if p.split()[0] in unit_provinces
        }

        adjacent = {
            r.destination for a in unit_provinces for r in locations[a].land_routes
        }
        adjacent |= {
            r.destination.split()[0]
            for a in unit_provinces
            for r in locations[a].sea_routes
        }

        bribe_armies = [
            a
            for p in self.game.players
            for a in p.armies
            if p != self and a in adjacent
        ]
        bribe_fleets = [
            f
            for p in self.game.players
            for f in p.fleets
            if p != self and f.split()[0] in adjacent
        ]
        bribe_garrisons = [
            g
            for p in self.game.players
            for g in p.garrisons
            if p != self and g in adjacent
        ]

        if key == "A":
            # Paliar hambruna
            for f in self.game.famine:
                choices.append((f"{map.provinces[f].id}", f"{map.provinces[f].name}"))
        elif key == "B":
            # Pacificar rebelión
            rebellions = [
                r
                for p in self.game.players
                for r in (p.rebelled_provinces + p.rebelled_cities)
            ]
            for r in rebellions:
                choices.append((f"{map.provinces[r].id}", f"{map.provinces[r].name}"))
        elif key == "C":
            # Comenzar rebelión en provincia no natal
            no_hc = [
                pr
                for p in self.game.players
                for pr in p.nonhc_provinces()
                if p != self
                if pr not in p.rebelled_provinces
                if pr not in p.rebelled_cities
            ]
            for r in no_hc:
                choices.append((f"{map.provinces[r].id}", f"{map.provinces[r].name}"))
        elif key == "D":
            # Comenzar rebelión en provincia natal
            hc = [
                pr
                for p in self.game.players
                for pr in p.hc_provinces()
                if p != self
                if pr not in p.rebelled_provinces
                if pr not in p.rebelled_cities
            ]
            for r in hc:
                choices.append((f"{map.provinces[r].id}", f"{map.provinces[r].name}"))
        elif key == "E":
            # Ordenar asesinato
            ass = [
                p.power
                for p in self.game.players
                if p.home_countries
                if p.power in self.ass_counters
            ]
            for a in ass:
                choices.append((f"{a}", f"{GameTables.powers[a]}"))
        elif key == "F":
            # Contra-soborno
            # Son todas las unidades del juego
            armies = [u for p in self.game.players for u in p.armies]
            for a in armies:
                choices.append((f"A {a}", f"Ejército en {locations[a].name}"))
            fleets = [u for p in self.game.players for u in p.fleets]
            for f in fleets:
                choices.append((f"F {f}", f"Flota en {locations[f].name}"))
            garrisons = [
                u for p in self.game.players for u in p.garrisons
            ] + self.game.independent_garrisons
            for g in garrisons:
                choices.append((f"G {g}", f"Guarnición en {locations[g].name}"))
        elif key in ("G", "H"):
            # Desbandar/Comprar guarnición autónoma
            garrisons = [g for g in self.game.independent_garrisons if g in adjacent]
            for g in garrisons:
                choices.append((f"G {g}", f"Guarnición en {locations[g].name}"))
        elif key == "I":
            # Convertir guarnición en autónoma
            for g in bribe_garrisons:
                choices.append((f"G {g}", f"Guarnición en {locations[g].name}"))
        elif key == "J":
            # Desbandar unidad
            for a in bribe_armies:
                choices.append((f"A {a}", f"Ejército en {locations[a].name}"))
            for f in bribe_fleets:
                choices.append((f"F {f}", f"Flota en {locations[f].name}"))
            for g in bribe_garrisons:
                choices.append((f"F {g}", f"Guarnición en {locations[g].name}"))
        elif key == "K":
            # Comprar ejército o flota
            for a in bribe_armies:
                choices.append((f"A {a}", f"Ejército en {locations[a].name}"))
            for f in bribe_fleets:
                choices.append((f"F {f}", f"Flota en {locations[f].name}"))

        return choices

    def exp_available_amounts(self, expense: str, target: str) -> list[tuple[str, str]]:
        """Devuelve la lista de cantidades disponibles para un gasto

        Incluye siempre el 0 para cancelar una orden previa y después las
        cantidades desde el mínimo hasta los ducados disponibles.
        """
        choices = [("0", "Cancelar gasto")]

        # Recuperamos los datos del gasto
        _, key = expense.split()
        exp = GameTables.expenses[key]
        cost = exp["cost"]
        map = self.game.map

        if key in ("A", "B", "C", "D"):
            # Gastos fijos: paliar hambruna, pacificar rebelión, comenzar rebelión
            choices.append((str(cost), f"{cost} ducados"))
        elif key == "E":
            # Ordenar asesinato
            for c in range(cost, cost * 3 + 1, cost):
                choices.append((str(c), f"{c} ducados"))
        elif key == "F":
            # Contra-soborno
            for c in range(cost, self.ducats + 1, 3):
                choices.append((str(c), f"{c} ducados"))
        elif key in ("G", "H", "I", "J", "K"):
            # Sobornos
            # Dobla el coste para guarniciones en ciudades mayores
            target_type, target_id = target.split()
            if target_type == "G" and map.provinces[target_id].major_city > 1:
                cost *= 2
            for c in range(cost, self.ducats + 1, 3):
                choices.append((str(c), f"{c} ducados"))

        return choices

    @classmethod
    def load_players(cls, conn: sqlite3.Connection, game: Game) -> list[Self]:
        """Busca y devuelve todos los jugadores asociados a un id de partida.

        Args:
            conn (sqlite3.Connection): Conexión activa a la BBDD.
            game (Game)              : Partida actual.

        Returns:
            list[Player]: Lista de objetos Player instanciados.
        """
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT player_id, discord_id, controlled_locations, armies, fleets,
                garrisons, ass_counters, ducats, rebelled_provinces,
                rebelled_cities, home_countries, power
            FROM players WHERE game_id = ?
            """,
            (game.database_id,),
        )
        rows = cursor.fetchall()

        players = []
        for row in rows:
            locations = json.loads(row[2]) if row[2] else []
            armies = json.loads(row[3]) if row[3] else []
            fleets = json.loads(row[4]) if row[4] else []
            garrisons = json.loads(row[5]) if row[5] else []
            ass_counters = json.loads(row[6]) if row[6] else []
            rebelled_provinces = json.loads(row[8]) if row[8] else []
            rebelled_cities = json.loads(row[9]) if row[9] else []
            home_countries = json.loads(row[10]) if row[10] else []
            player = cls(
                game=game,
                player_id=row[0],
                discord_id=row[1],
                controlled_locations=locations,
                armies=armies,
                fleets=fleets,
                garrisons=garrisons,
                ass_counters=ass_counters,
                ducats=row[7],
                rebelled_provinces=rebelled_provinces,
                rebelled_cities=rebelled_cities,
                home_countries=home_countries,
                power=row[11],
            )
            player.commands = Command.load_commands(conn, game, player)
            players.append(player)

        return players


@dataclass
class Game:
    """Representa una partida de Machiavelli.

    Attributes:
        name (str): Nombre descriptivo de la partida.
        channel_id (int): Identificador del canal de Discord.
        database_id (int | None): ID de base de datos, o None si es nueva.
        scenario_id (str | None): Identificador del escenario.
        turn_number (int): Turno actual; una partida nueva comienza en 0.
        weekly_deadline (str | None): Calendario semanal de turnos.
        next_deadline (str | None): Fecha del siguiente turno.
        players (list[Player]): Jugadores apuntados.
        scenario (Scenario | None): Escenario completo asociado.
        map (Map | None): Mapa de la partida.
        famine (list[str]): Provincias con hambre.
        independent_garrisons (list[str]): Guarniciones independientes.
        besieges (list[str]): Provincias con asedios en marcha.
        turn_events (list[str]): Eventos que se publicarán en el reporte.
    """

    name: str
    channel_id: int | None = None
    database_id: int | None = None
    scenario_id: str | None = None
    turn_number: int = 0
    weekly_deadline: str | None = None
    next_deadline: str | None = None
    players: list[Player] = field(default_factory=list)
    scenario: Scenario | None = None
    map: Map | None = None
    famine: list[str] = field(default_factory=list)
    independent_garrisons: list[str] = field(default_factory=list)
    besieges: list[str] = field(default_factory=list)
    turn_events: list[str] = field(default_factory=list)

    def save(self, conn: sqlite3.Connection) -> None:
        """Guarda el estado actual de la partida en la base de datos.

        Si no tiene database_id, la inserta como nueva. En caso contrario,
        actualiza sus datos.

        Raises:
            DuplicatedGameException: Si el nombre o canal ya existen.
        """
        cursor = conn.cursor()

        # Calcula los campos que vamos a guardar en la base de datos
        columns = [
            f.name
            for f in fields(self)
            if f.name
            not in (
                "database_id",
                "players",
                "scenario",
                "map",
                "famine",
                "independent_garrisons",
                "besieges",
                "turn_events",
            )
        ]
        values = [getattr(self, col) for col in columns]

        famine_json = json.dumps(self.famine)
        columns.append("famine")
        values.append(famine_json)

        garrisons_json = json.dumps(self.independent_garrisons)
        columns.append("independent_garrisons")
        values.append(garrisons_json)

        besieges_json = json.dumps(self.besieges)
        columns.append("besieges")
        values.append(besieges_json)

        # Partida nueva
        if self.database_id is None:
            try:
                placeholders = ", ".join(["?"] * len(columns))
                query = (
                    f"INSERT INTO games ({', '.join(columns)}) VALUES ({placeholders})"
                )
                cursor.execute(query, tuple(values))
                self.database_id = cursor.lastrowid
            except sqlite3.IntegrityError as e:
                raise DuplicatedGameException(
                    "No se pudo crear la partida. "
                    f"El nombre '{self.name}' o el canal "
                    f"'{self.channel_id}' ya están en uso."
                ) from e
        # Actualizar
        else:
            set_clause = ", ".join([f"{col} = ?" for col in columns])
            query = f"UPDATE games SET {set_clause} WHERE id = ?"
            cursor.execute(query, tuple(values) + (self.database_id,))

        # Guardamos todos los elementos
        for player in self.players:
            player.save(conn)

        # Para los eventos refrescamos completamente la tabla
        cursor.execute("DELETE FROM game_events WHERE game_id = ?", (self.database_id,))
        if self.turn_events:
            payload = [(self.database_id, msg) for msg in self.turn_events]
            cursor.executemany(
                """
                INSERT INTO game_events (game_id, message)
                VALUES (?, ?)
            """,
                payload,
            )

    def report_status(self) -> list[str]:
        """Devuelve el estado actual de la partida.

        Devuelve una lista de cadenas, cada una con una línea del estado.

        Returns:
            list(str): Estado actual de la partida.
        """
        report = [f"## __**Partida**: {self.name}__"]

        report.append(
            f"**Escenario:** {self.scenario.name if self.scenario else 'Por definir'}."
        )

        weekly_deadline = self.weekly_deadline or "Por definir"
        report.append(f"**Horario de los turnos:** {weekly_deadline}.")

        if self.turn_number == 0:
            report.append("### __**Estado:** Por comenzar.__")
            if self.players:
                players = ", ".join(
                    [f"<@{p.discord_id}> ({p.player_id})" for p in self.players]
                )
                if self.scenario:
                    report.append(
                        f"**Jugadores {len(self.players)}/"
                        f"{len(self.scenario.powers)}:** {players}"
                    )
                else:
                    report.append(f"**Jugadores {len(self.players)}:** {players}")
            else:
                report.append("**Jugadores:** Ninguno")
        else:
            year = (self.turn_number - 1) // 4 + self.scenario.year
            season_number = (self.turn_number - 1) % 4
            season = (
                "Primavera (mantenimiento)",
                "Primavera (campaña)",
                "Verano",
                "Otoño",
            )[season_number]

            report.append(f"### __**Estado:** {season} de {year}__")
            report.append("**Han enviado sus órdenes:**")
            players = [p for p in self.players if p.commands]
            if players:
                for p in players:
                    report.append(f"- <@{p.discord_id}> ({p.player_id})")
            else:
                report.append("- Nadie :wink:.")

        next_deadline = self.next_deadline or "Por definir"
        report.append(f"**Próximo turno:** {next_deadline}.")

        return report

    def start_game(self) -> list[str]:
        """Comienza la partida.

        Requiere escenario, jugadores suficientes y fechas de turno fijadas.

        Returns:
            list(str): Reporte de la ejecución.
        """
        # Comprobamos primero que se cumplan las condiciones
        message = None
        report = ["__Iniciando partida__"]
        self.turn_events.append("\n__Iniciando partida__")

        if not self.scenario:
            message = "No se seleccionó escenario"
        elif not self.weekly_deadline or not self.next_deadline:
            message = "No se fijó la fecha de los turnos"
        elif len(self.players) != len(self.scenario.powers):
            message = "El número de jugadores no coincide con el escenario"
        elif self.turn_number > 0:
            message = "La partida ya está en curso"

        if message:
            report.append(f"No se pudo iniciar la partida: {message}")
            raise FailedToStartError(message=message)

        # Ahora la podemos comenzar
        report.extend(self.initial_setup())
        report.extend(self.spring_start())

        return self.turn_events
        # return report

    def run_game(self) -> list[str]:
        """Ejecuta un turno y genera el reporte.

        Requiere escenario, jugadores suficientes y fechas de turno fijadas.

        Returns:
            list(str): Reporte de la ejecución.
        """
        # Clean up events
        self.turn_events = []

        self.turn_events.append(f"### __**{self.name}, turno {self.turn_number}**__")

        now = datetime.now().strftime("%d-%m-%Y %H:%M")
        last_date = datetime.fromisoformat(self.next_deadline)
        next_date = last_date + timedelta(weeks=1)
        next_deadline = next_date.strftime("%d-%m-%Y %H:%M")
        self.turn_events.append(f"**Fecha:** {now}. **Próximo turno:** {next_deadline}")

        if self.turn_number == 0:
            self.start_game()
        else:
            # Ya tenemos la partida en marcha
            if self.turn_number % 4 == 1:
                self.spring_maintenance()
            else:
                # Campaña
                self.run_campaign()

        self.turn_number += 1
        last_date = datetime.fromisoformat(self.next_deadline)
        self.next_deadline = next_date.strftime("%Y-%m-%d %H:%M")
        for p in self.players:
            p.commands = []

        return self.turn_report()

    @classmethod
    def create_game(cls, name: str, channel_id: int, conn: sqlite3.Connection) -> Self:
        """Crea una nueva partida y la guarda en la base de datos.

        Args:
            name (str): Nombre de la partida.
            channel_id (int): El ID del canal de Discord de esta partida.
            conn (ssqlite3.Connectionql): Conexión activa a la base de datos.

        Returns:
            Self: La instancia de Game recién creada con su 'database_id ya asignado.

        Raises:
            DuplicatedGameException: Si el nombre o canal ya existen.
        """
        cursor = conn.cursor()

        try:
            cursor.execute(
                "INSERT INTO games (name, channel_id) VALUES (?, ?)",
                (name, channel_id),
            )
        except sqlite3.IntegrityError as e:
            raise DuplicatedGameException(
                f"No se pudo crear la partida. El nombre '{name}' o el canal "
                f"'{channel_id}' ya están en uso."
            ) from e

        db_id = cursor.lastrowid

        return cls(name=name, channel_id=channel_id, database_id=db_id)

    @classmethod
    def load_game(
        cls,
        conn: sqlite3.Connection,
        *,
        game_id: int | None = None,
        name: str | None = None,
        channel_id: int | None = None,
    ) -> Self:
        """Busca y carga una partida completa de la BBDD.

        El uso de '*' obliga a pasar los criterios de búsqueda como argumentos
        con nombre, por ejemplo Game.load_game(conn, channel_id=12345).

        Raises:
            ValueError: Si no se proporciona ningún criterio de búsqueda.
            GameNotFoundException: Si la partida no existe en la base de datos.
        """
        cursor = conn.cursor()

        # Eliminamos las columnas quen no están en la base de datos
        columns = [
            f.name
            for f in fields(cls)
            if f.name
            not in ("database_id", "players", "scenario", "map", "turn_events")
        ]
        select_clause = ", ".join(["id"] + columns)

        if game_id is not None:
            cursor.execute(
                f"SELECT {select_clause} FROM games WHERE id = ?", (game_id,)
            )
        elif name is not None:
            cursor.execute(f"SELECT {select_clause} FROM games WHERE name = ?", (name,))
        elif channel_id is not None:
            cursor.execute(
                f"SELECT {select_clause} FROM games WHERE channel_id = ?", (channel_id,)
            )
        else:
            raise ValueError("Debes proporcionar al menos un criterio de búsqueda.")

        game_row = cursor.fetchone()
        if not game_row:
            raise GameNotFoundException("No se encontró ninguna partida.")

        # Mapeo dinámico de los datos primitivos
        init_kwargs = {columns[i]: game_row[i + 1] for i in range(len(columns))}

        # Parsea famine y garrisons (de JSON a list)
        famine = json.loads(init_kwargs["famine"]) if init_kwargs["famine"] else []
        garrisons = (
            json.loads(init_kwargs["independent_garrisons"])
            if init_kwargs["independent_garrisons"]
            else []
        )
        besieges = (
            json.loads(init_kwargs["besieges"]) if init_kwargs["besieges"] else []
        )

        init_kwargs["famine"] = famine
        init_kwargs["independent_garrisons"] = garrisons
        init_kwargs["besieges"] = besieges

        game = cls(**init_kwargs)

        # Cargamos los jugadores
        game.database_id = game_row[0]
        game.players = Player.load_players(conn, game)

        # Cargamos los eventos
        cursor.execute(
            "SELECT message FROM game_events WHERE game_id = ? ORDER BY id ASC",
            (game.database_id,),
        )

        game.turn_events = [row[0] for row in cursor.fetchall()]

        # Cargamos el escenario
        if game.scenario_id:
            game.scenario = Scenario.load_scenarios().get(game.scenario_id)
            excluded_locations = game.scenario.excluded_locations
        else:
            game.scenario = None
            excluded_locations = None

        # Cargamos el mapa
        game.map = Map.load_map(exclude_ids=excluded_locations)

        # Resultado
        return game

    # Game phases
    def initial_setup(self) -> list[str]:
        """Realiza el setup inicial de la partida según el escenario.

        Estas acciones son:
        - Reparte las facciones al azar entre los jugadores
        - Asigna a cada jugador las provincias controladas y las unidades
        - Reparte recursos a cada jugador (fichas de asesinato principalmente)
        - Coloca guarniciones independientes en ciudades sin propietario

        Returns:
            list(str): Una lista con los mensajes generados en la operación.
        """
        report = []

        report.append("### __Setup inicial__")
        self.turn_events.append("**Setup inicial**")

        powers = self.scenario.powers.copy()
        random.shuffle(powers)

        garrisons = [k for k, p in self.map.provinces.items() if p.city == "fortified"]

        for player, power in zip(self.players, powers, strict=False):
            report.append(
                f"<@{player.discord_id}> ({player.player_id}) dirigirá a {power.name}"
            )
            self.turn_events.append(
                f"- <@{player.discord_id}> ({player.player_id}) dirigirá a {power.name}"
            )
            # Asigna la potencia al jugador, junto con sus provincias y unidades.
            player.assign_power(power)
            # Asigna las fichas de asesinato
            player.ass_counters = [p.id for p in powers if p.id != power.id]
            # Elimina las guarniciones independientes de sus provincias
            garrisons = [p for p in garrisons if p not in power.controlled_provinces]

        self.independent_garrisons = garrisons

        return report

    def spring_start(self) -> list[str]:
        """Realiza las operaciones del inicio de la primavera.

        Estas acciones son:
        - Coloca marcadores de hambre
        - Calcula los ingresos

        Returns:
            list(str): Una lista con los mensajes generados en la operación.
        """
        report = []

        # Inicio de año
        year = self.scenario.year + self.turn_number // 4

        self.turn_events.append(f"\n__Primavera de {year}__")

        # El primer año no haremos tirada de hambre
        self.famine = []
        if self.scenario.rules.famine_active and self.turn_number > 0:
            self.turn_events.append("**Fase de Hambre**")

            report.append(f"### __Primavera de {year}: Hambre__")
            dice = random.randint(1, 6)
            famine = GameTables.disasters[dice - 1]
            report.append(f"- **Fase de hambre**: 1d6 => {dice}. {famine[1]}")

            self.turn_events.append(f"- **Hambre (=>{dice}):** {famine[1]}")
            famine_names = []

            # Fila
            if famine[0] in ["both", "row"]:
                dice = random.randint(1, 6) + random.randint(1, 6)
                row = GameTables.famine[dice - 2]
                provinces = {i: p for i, p in self.map.provinces.items() if i in row}
                self.famine.extend(provinces.keys())
                names = [v.name for v in provinces.values()]
                report.append(
                    f"  * **Fila**: 2d6 => {dice}, **Hambre** en {', '.join(names)}"
                )
                famine_names.extend(names)
                joined_names = " y ".join([", ".join(names[:-1]), names[-1]])
                self.turn_events.append(f"* **Fila (=>{dice}):** {joined_names}")

            # Columna
            if famine[0] in ["both", "column"]:
                dice = random.randint(1, 6) + random.randint(1, 6)
                column = [r[dice - 2] for r in GameTables.famine]
                provinces = {i: p for i, p in self.map.provinces.items() if i in column}
                self.famine.extend(provinces.keys())
                names = [v.name for v in provinces.values()]
                report.append(
                    f"  * **Columna**: 2d6 => {dice}, **Hambre** en {', '.join(names)}"
                )
                famine_names.extend(names)
                joined_names = " y ".join([", ".join(names[:-1]), names[-1]])
                self.turn_events.append(f"* **Fila (=>{dice}):** {joined_names}")

        # Ingresos
        report.append(f"### __Primavera de {year}: Ingresos__")

        self.turn_events.append("**Fase de Ingresos**")

        for player in self.players:
            report.append(
                f"- {GameTables.powers[player.power]} (<@{player.discord_id}>)"
            )
            self.turn_events.append(
                f"- __{GameTables.powers[player.power]}__ (<@{player.discord_id}>)"
            )

            # Ingresos fijos (provincias y mares)
            # Provincias controladas y ocupadas
            maybe_provinces = (
                {p for p in player.controlled_locations}
                | {p for p in player.armies}
                | {p.split()[0] for p in player.fleets}
            )
            # Elimina las que tengan hambre o rebeliones
            provinces = [
                p
                for p in maybe_provinces
                if p not in self.famine
                if p not in player.rebelled_provinces
                if p not in player.rebelled_cities
            ]
            province_income = len(provinces)

            # Las ciudades con hambre o rebelión generan ingresos con guarnición.
            maybe_cities = {
                p
                for p in player.controlled_locations
                if p not in self.famine
                if p not in player.rebelled_cities
                if p not in player.rebelled_provinces
            } | {p for p in player.garrisons}
            cities = [
                c
                for c in maybe_cities
                if self.map.provinces[c].city in ("city", "fortified")
            ]
            city_income = sum(self.map.provinces[c].major_city for c in cities)

            fixed_income = (
                "  * **Ingresos fijos.** Por Provincias y Mares, "
                f"{province_income} ducados. Por Ciudades, {city_income} ducados"
            )
            report.append(fixed_income)
            self.turn_events.append(fixed_income)

            # Ingresos variables (home countries)
            hc_income = 0
            for hc in self.scenario.variable_income_home_countries:
                if hc in player.home_countries:
                    dice = random.randint(1, 6)
                    this_hc_income = GameTables.variable_income[hc][dice - 1]
                    report.append(
                        "  * **Ingresos variables.** "
                        f"{GameTables.powers[hc]} (1d6 => {dice}), "
                        f"{this_hc_income} ducados"
                    )
                    self.turn_events.append(
                        "  * **Ingresos variables.** Por nación "
                        f"{GameTables.powers[hc]} (=>{dice}), "
                        f"{this_hc_income} ducados"
                    )
                    hc_income += this_hc_income

            for p in self.scenario.variable_income_provinces:
                if p in player.controlled_locations:
                    dice = random.randint(1, 6)
                    this_hc_income = GameTables.variable_income[p][dice - 1]
                    report.append(
                        "  * **Ingresos variables.** "
                        f"{self.map.provinces[p].name} (1d6 => {dice}), "
                        f"{this_hc_income} ducados"
                    )
                    self.turn_events.append(
                        "  * **Ingresos variables.** Por provincia "
                        f"{self.map.provinces[p].name} (=>{dice}), "
                        f"{this_hc_income} ducados"
                    )
                    hc_income += this_hc_income

            # Total ingresos
            total_income = province_income + city_income + hc_income
            player.ducats += total_income
            report.append(
                f"  * **Total ingresos.** {province_income} + {city_income} + "
                f"{hc_income} = {total_income} ducados"
            )

            self.turn_events.append(f"  * **Ingresos totales.** {total_income} ducados")

        return report

    def spring_maintenance(self) -> list[str]:
        """Realiza las operaciones de mantenimiento de primavera.

        Estas acciones son:
        - Desbanda, mantiene y recluta unidades
        - Comprueba que ninguna unidad se recluta dónde haya una desbandada
        - Calcula el coste, y descuenta los ducados
        - Las órdenes que no tengan suficiente dinero para ejecutarse, no se ejecutan

        Returns:
            list(str): Una lista con los mensajes generados en la operación.
        """
        # Inicio de año
        year = self.scenario.year + (self.turn_number - 1) // 4

        self.turn_events.append(f"\n__Primavera de {year}__")
        self.turn_events.append("**Fase de Mantenimiento**")

        # Recorremos todos los jugadores y ejecutamos sus órdenes
        for player in self.players:
            self.turn_events.append(
                f"\n__{GameTables.powers[player.power]} "
                f"(<@{player.discord_id}>). Órdenes:__"
            )
            disbanded = []
            expenses = 0

            # Damos órdenes por defecto a todas las unidades
            player.set_default_commands()

            # Primero las órdenes de disband
            disband_commands = [cmd for cmd in player.commands if cmd.command == "D"]
            for cmd in disband_commands:
                unit_type, unit_id = cmd.actor.split()
                if unit_type == "A":
                    if unit_id in player.armies:
                        player.armies.remove(unit_id)
                        self.turn_events.append(f"- `{cmd}:` Ejército disuelto.")
                        disbanded.append(unit_id)
                    else:
                        self.turn_events.append(f"- `{cmd}:` No existe el ejército.")
                elif unit_type == "F":
                    if unit_id in player.fleets:
                        player.fleets.remove(unit_id)
                        self.turn_events.append(f"- `{cmd}:` Flota disuelta.")
                        disbanded.append(unit_id)
                    else:
                        self.turn_events.append(f"- `{cmd}:` No existe la flota.")
                elif unit_type == "G":
                    if unit_id in player.garrisons:
                        player.garrisons.remove(unit_id)
                        self.turn_events.append(f"- `{cmd}:` Guarnición disuelta.")
                        disbanded.append(unit_id)
                    else:
                        self.turn_events.append(f"- `{cmd}:` No existe la guarnición.")

            # A continuación las de mantenimiento
            maintain_commands = [cmd for cmd in player.commands if cmd.command == "M"]
            for cmd in maintain_commands:
                unit_type, unit_id = cmd.actor.split()
                if unit_type == "A":
                    if unit_id in player.armies:
                        if (player.ducats - expenses) >= 3:
                            self.turn_events.append(f"- `{cmd}:` Ejército mantenido.")
                            expenses += 3
                        else:
                            self.turn_events.append(
                                f"- `{cmd}:` Sin fondos. Ejército disuelto."
                            )
                            player.armies.remove(unit_id)
                            disbanded.append(unit_id)
                    else:
                        self.turn_events.append(f"- `{cmd}:` No existe el ejército.")
                elif unit_type == "F":
                    if unit_id in player.fleets:
                        if (player.ducats - expenses) >= 3:
                            self.turn_events.append(f"- `{cmd}:` Flota mantenida.")
                            expenses += 3
                        else:
                            self.turn_events.append(
                                f"- `{cmd}:` Sin fondos. Flota disuelta."
                            )
                            player.fleets.remove(unit_id)
                            disbanded.append(unit_id)
                    else:
                        self.turn_events.append(f"- `{cmd}:` No existe la flota.")
                elif unit_type == "G":
                    if unit_id in player.garrisons:
                        if (player.ducats - expenses) >= 3:
                            self.turn_events.append(f"- `{cmd}:` Guarnición mantenida.")
                            expenses += 3
                        else:
                            self.turn_events.append(
                                f"- `{cmd}:` Sin fondos. Guarnición disuelta."
                            )
                            player.garrisons.remove(unit_id)
                            disbanded.append(unit_id)
                    else:
                        self.turn_events.append(f"- `{cmd}:` No existe la guarnición.")

            # Por último, los nuevos reclutamientos
            recruit_commands = [cmd for cmd in player.commands if cmd.command == "R"]
            home_countries_cities = [
                p
                for p in player.controlled_locations
                if self.scenario.province_home_country(p) in player.home_countries
                and self.map.provinces[p].city in ("city", "fortified")
            ]
            for cmd in recruit_commands:
                if (player.ducats - expenses) >= 3:
                    unit_type, unit_id = cmd.actor.split()
                    if unit_type == "A":
                        if unit_id not in home_countries_cities:
                            self.turn_events.append(
                                f"- `{cmd}:` La provincia no es de un país natal "
                                "o no se controla. No se pudo reclutar"
                            )
                        elif unit_id in player.armies or unit_id in player.fleets:
                            self.turn_events.append(
                                f"- `{cmd}:` Provincia ocupada. No se pudo reclutar."
                            )
                        elif (
                            self.map.provinces[unit_id].is_venice
                            and unit_id in player.garrisons
                        ):
                            self.turn_events.append(
                                f"- `{cmd}:` Provincia ocupada. No se pudo reclutar."
                            )
                        else:
                            self.turn_events.append(
                                f"- `{cmd}:` Ejército reclutado en "
                                f"{self.map.provinces[unit_id].name}."
                            )
                            player.armies.append(unit_id)
                            expenses += 3
                    elif unit_type == "F":
                        if unit_id not in home_countries_cities:
                            self.turn_events.append(
                                f"- `{cmd}:` La provincia no es de un país natal "
                                "o no se controla. No se pudo reclutar"
                            )
                        elif unit_id in player.armies or unit_id in player.fleets:
                            self.turn_events.append(
                                f"- `{cmd}:` Provincia ocupada. No se pudo reclutar."
                            )
                        elif (
                            self.map.provinces[unit_id].is_venice
                            and unit_id in player.garrisons
                        ):
                            self.turn_events.append(
                                f"- `{cmd}:` Ciudad ocupada. No se pudo reclutar."
                            )
                        elif not self.map.provinces[unit_id].has_port:
                            self.turn_events.append(
                                f"- `{cmd}:` Las flotas solo se pueden reclutar "
                                "en puertos. No se pudo reclutar."
                            )
                        else:
                            self.turn_events.append(
                                f"- `{cmd}:` Flota reclutada en "
                                f"{self.map.provinces[unit_id].name}."
                            )
                            player.fleets.append(unit_id)
                            expenses += 3
                    elif unit_type == "G":
                        # Una ciudad rebelada no puede reclutar ni consumir ducados.
                        if unit_id in player.rebelled_cities:
                            self.turn_events.append(
                                f"- `{cmd}:` Ciudad rebelada. No se pudo reclutar."
                            )
                        elif unit_id not in home_countries_cities:
                            self.turn_events.append(
                                f"- `{cmd}:` La provincia no es de un país natal "
                                "o no se controla. No se pudo reclutar"
                            )
                        elif unit_id in player.garrisons:
                            self.turn_events.append(
                                f"- `{cmd}:` Ciudad ocupada. No se pudo reclutar."
                            )
                        elif self.map.provinces[unit_id].is_venice and (
                            unit_id in player.armies or unit_id in player.fleets
                        ):
                            self.turn_events.append(
                                f"- `{cmd}:` Provincia ocupada. No se pudo reclutar."
                            )
                        elif self.map.provinces[unit_id].city != "fortified":
                            self.turn_events.append(
                                f"- `{cmd}:` Las guarniciones solo se pueden "
                                "reclutar en ciudades fortificadas. "
                                "No se pudo reclutar."
                            )
                        else:
                            self.turn_events.append(
                                f"- `{cmd}:` Guarnición reclutada en "
                                f"{self.map.provinces[unit_id].name}."
                            )
                            player.garrisons.append(unit_id)
                            expenses += 3
                else:
                    self.turn_events.append(
                        f"- `{cmd}:` Sin fondos. Reclutamiento no realizado."
                    )

            assert (
                expenses
                == (len(player.armies) + len(player.fleets) + len(player.garrisons)) * 3
            )
            self.turn_events.append(
                f"*Ducados iniciales*: {player.ducats}. "
                f"*Gastos:* {expenses}. "
                f"*Ducados restantes*: {player.ducats - expenses}. "
            )
            player.ducats -= expenses

        return self.turn_events

    def turn_report(self) -> list[str]:
        """Devuelve el informe del turno actual"""
        report = []

        year = self.scenario.year + (self.turn_number - 1) // 4
        season_number = (self.turn_number - 1) % 4
        season = (
            "Primavera (mantenimiento)",
            "Primavera (campaña)",
            "Verano",
            "Otoño",
        )[season_number]

        report.append(f"## 📜 {self.name}, turno {self.turn_number}")
        report.append(f"### 🗓️ {season} de {year}")

        # Reporta los eventos del turno anterior
        report.append("> ⚠️ **EVENTOS DEL TURNO ANTERIOR**")
        for event in self.turn_events:
            report.append(f"> {event}")

        # Y ahora el estado actual del tablero
        report.append("## 🗺️ REPORTE DE SITUACIÓN")

        if self.famine:
            names = [p.name for k, p in self.map.provinces.items() if k in self.famine]
            famine = " y ".join([", ".join(names[:-1]), names[-1]])
            report.append(f"🌾 **Hambre:** {famine}")

        if self.independent_garrisons:
            names = [
                p.name
                for k, p in self.map.provinces.items()
                if k in self.independent_garrisons
            ]
            if len(names) > 1:
                garrisons = " y ".join([", ".join(names[0:-1]), names[-1]])
            else:
                garrisons = names[0]
            report.append(f"🛡️ **Guarniciones independientes:** {garrisons}")

        for p in self.players:
            report.extend(p.player_report())

        return report

    def add_event(self, turn_event: TurnEvent):
        """Añade la representación persistible del evento al historial del turno."""
        self.turn_events.append(turn_event.to_record())

    def get_unit_owner(self, unit_id: str) -> Player | None:
        """Devuelve el jugador propietario de una unidad.

        Args:
            unit_id (str): Identificador de la unidad con formato '<tipo> <provincia>'
                        (por ejemplo: 'A prove', 'F prove', 'G rome').

        Returns:
            Player | None: El jugador propietario, o None si la unidad es independiente.

        Raises:
            ValueError: Si el formato es inválido o la unidad no existe.
        """
        parts = unit_id.split(" ", 1)
        if len(parts) != 2:
            raise ValueError(
                f"Formato de identificador de unidad inválido: '{unit_id}'"
            )

        unit_type, base_location = parts
        if unit_type not in ("A", "F", "G"):
            raise ValueError(f"Tipo de unidad desconocido: '{unit_type}'")

        # Buscar en las unidades de los jugadores
        for player in self.players:
            units = {
                "A": player.armies,
                "F": player.fleets,
                "G": player.garrisons,
            }[unit_type]

            if any(u.split()[0] == base_location for u in units):
                return player

        #  Verificar si es una guarnición independiente existente
        if unit_type == "G" and any(
            g == base_location for g in self.independent_garrisons
        ):
            return None

        # Si no pertenece a un jugador ni es independiente, la unidad no existe
        raise ValueError(f"No existe ninguna unidad '{unit_id}' en el juego.")


def __getattr__(name: str) -> object:
    """Resolve temporary compatibility exports without creating import cycles."""
    if name == "TooManyExpenses":
        from machiavelli.engine.exceptions import TooManyExpenses

        return TooManyExpenses
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "Command",
    "DuplicatedGameException",
    "FailedToStartError",
    "Game",
    "GameNotFoundException",
    "Player",
]

# The historical in-file implementations are deliberately removed from the
# runtime namespace after the canonical classes have been imported above.
del _HistoricalCommand, _HistoricalPlayer
