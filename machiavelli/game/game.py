"""Canonical game aggregate and persistence compatibility facade."""

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
    DuplicatePlayerException,
    FailedToStartError,
    GameNotFoundException,
    PlayerNotFoundException,
)
from .map import Map
from .player import Player
from .scenario import Scenario
from .tables import GameTables


@dataclass
class Game:
    """Represent a complete Machiavelli game aggregate."""

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

    def require_map(self) -> Map:
        """Return the loaded map or fail fast for an invalid game state."""
        game_map = self.map
        if game_map is None:
            raise RuntimeError("La partida requiere un mapa cargado")
        return game_map

    def require_scenario(self) -> Scenario:
        """Return the loaded scenario or fail fast for an invalid game state."""
        scenario = self.scenario
        if scenario is None:
            raise RuntimeError("La partida requiere un escenario cargado")
        return scenario

    def add_player(self, player_id: str, discord_id: int | None = None) -> Player:
        """Create and register one canonical player in this game aggregate."""
        if any(player.player_id == player_id for player in self.players):
            raise DuplicatePlayerException(
                f"El jugador '{player_id}' ya está inscrito en la partida."
            )
        if discord_id is not None and any(
            player.discord_id == discord_id for player in self.players
        ):
            raise DuplicatePlayerException(
                f"La cuenta de Discord '{discord_id}' ya está inscrita en la partida."
            )

        player = Player(game=self, player_id=player_id, discord_id=discord_id)
        self.players.append(player)
        return player

    def remove_player(self, discord_id: int) -> Player:
        """Remove and return the player linked to a Discord account."""
        player = next(
            (
                candidate
                for candidate in self.players
                if candidate.discord_id == discord_id
            ),
            None,
        )
        if player is None:
            raise PlayerNotFoundException(
                f"La cuenta de Discord '{discord_id}' no pertenece a la partida."
            )
        self.players.remove(player)
        return player

    def advance_turn(self) -> None:
        """Advance lifecycle metadata after a successfully completed engine run."""
        self.turn_number += 1
        if self.next_deadline:
            deadline = datetime.fromisoformat(self.next_deadline)
            self.next_deadline = (deadline + timedelta(weeks=1)).strftime(
                "%Y-%m-%d %H:%M"
            )
        for player in self.players:
            player.commands.clear()

    def save(self, conn: sqlite3.Connection) -> None:
        """Persist the complete aggregate using the caller's transaction."""
        cursor = conn.cursor()
        columns = [
            item.name
            for item in fields(self)
            if item.name
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
        values = [getattr(self, column) for column in columns]

        for column, value in (
            ("famine", self.famine),
            ("independent_garrisons", self.independent_garrisons),
            ("besieges", self.besieges),
        ):
            columns.append(column)
            values.append(json.dumps(value))

        if self.database_id is None:
            try:
                placeholders = ", ".join(["?"] * len(columns))
                query = (
                    f"INSERT INTO games ({', '.join(columns)}) VALUES ({placeholders})"
                )
                cursor.execute(query, tuple(values))
                self.database_id = cursor.lastrowid
            except sqlite3.IntegrityError as error:
                raise DuplicatedGameException(
                    "No se pudo crear la partida. "
                    f"El nombre '{self.name}' o el canal "
                    f"'{self.channel_id}' ya están en uso."
                ) from error
        else:
            set_clause = ", ".join([f"{column} = ?" for column in columns])
            query = f"UPDATE games SET {set_clause} WHERE id = ?"
            cursor.execute(query, tuple(values) + (self.database_id,))

        from machiavelli.repositories.player_repository import PlayerRepository

        PlayerRepository(conn).replace_for_game(self)

        cursor.execute("DELETE FROM game_events WHERE game_id = ?", (self.database_id,))
        if self.turn_events:
            cursor.executemany(
                """
                INSERT INTO game_events (game_id, message)
                VALUES (?, ?)
                """,
                [(self.database_id, message) for message in self.turn_events],
            )

    def report_status(self) -> list[str]:
        """Return the current public game status as report lines."""
        report = [f"## __**Partida**: {self.name}__"]
        report.append(
            f"**Escenario:** {self.scenario.name if self.scenario else 'Por definir'}."
        )
        report.append(
            f"**Horario de los turnos:** {self.weekly_deadline or 'Por definir'}."
        )

        if self.turn_number == 0:
            report.append("### __**Estado:** Por comenzar.__")
            if self.players:
                players = ", ".join(
                    f"<@{player.discord_id}> ({player.player_id})"
                    for player in self.players
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
            if self.scenario is None:
                raise ValueError("Una partida iniciada debe tener escenario")
            year = (self.turn_number - 1) // 4 + self.scenario.year
            season = (
                "Primavera (mantenimiento)",
                "Primavera (campaña)",
                "Verano",
                "Otoño",
            )[(self.turn_number - 1) % 4]
            report.append(f"### __**Estado:** {season} de {year}__")
            report.append("**Han enviado sus órdenes:**")
            ordered_players = [player for player in self.players if player.commands]
            if ordered_players:
                report.extend(
                    f"- <@{player.discord_id}> ({player.player_id})"
                    for player in ordered_players
                )
            else:
                report.append("- Nadie :wink:.")

        report.append(f"**Próximo turno:** {self.next_deadline or 'Por definir'}.")
        return report

    def start_game(self) -> list[str]:
        """Start the game through the historical domain compatibility path."""
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

        report.extend(self.initial_setup())
        report.extend(self.spring_start())
        return self.turn_events

    def run_game(self) -> list[str]:
        """Execute one turn through the historical compatibility path."""
        self.turn_events = [f"### __**{self.name}, turno {self.turn_number}**__"]
        if self.next_deadline is None:
            raise ValueError("La partida no tiene próximo plazo configurado")

        now = datetime.now().strftime("%d-%m-%Y %H:%M")
        last_date = datetime.fromisoformat(self.next_deadline)
        next_date = last_date + timedelta(weeks=1)
        next_deadline = next_date.strftime("%d-%m-%Y %H:%M")
        self.turn_events.append(f"**Fecha:** {now}. **Próximo turno:** {next_deadline}")

        if self.turn_number == 0:
            self.start_game()
        elif self.turn_number % 4 == 1:
            self.spring_maintenance()
        else:
            self.run_campaign()

        self.turn_number += 1
        self.next_deadline = next_date.strftime("%Y-%m-%d %H:%M")
        for player in self.players:
            player.commands = []
        return self.turn_report()

    def run_campaign(self) -> None:
        """Execute the canonical campaign engine for compatibility callers."""
        from machiavelli.engine.core import GameEngine

        GameEngine(self).run_campaign()

    @classmethod
    def create_game(cls, name: str, channel_id: int, conn: sqlite3.Connection) -> Self:
        """Create and insert a game through the historical persistence facade."""
        cursor = conn.cursor()
        try:
            cursor.execute(
                "INSERT INTO games (name, channel_id) VALUES (?, ?)",
                (name, channel_id),
            )
        except sqlite3.IntegrityError as error:
            raise DuplicatedGameException(
                f"No se pudo crear la partida. El nombre '{name}' o el canal "
                f"'{channel_id}' ya están en uso."
            ) from error
        return cls(name=name, channel_id=channel_id, database_id=cursor.lastrowid)

    @classmethod
    def load_game(
        cls,
        conn: sqlite3.Connection,
        *,
        game_id: int | None = None,
        name: str | None = None,
        channel_id: int | None = None,
    ) -> Self:
        """Load a complete and internally consistent aggregate from SQLite."""
        cursor = conn.cursor()
        columns = [
            item.name
            for item in fields(cls)
            if item.name
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

        init_kwargs = {
            columns[index]: game_row[index + 1] for index in range(len(columns))
        }
        for column in ("famine", "independent_garrisons", "besieges"):
            init_kwargs[column] = (
                json.loads(init_kwargs[column]) if init_kwargs[column] else []
            )

        game = cls(**init_kwargs)
        game.database_id = game_row[0]

        from machiavelli.repositories.player_repository import PlayerRepository

        game.players = PlayerRepository(conn).get_by_game(game)
        cursor.execute(
            "SELECT message FROM game_events WHERE game_id = ? ORDER BY id ASC",
            (game.database_id,),
        )
        game.turn_events = [row[0] for row in cursor.fetchall()]

        if game.scenario_id:
            scenarios = Scenario.load_scenarios()
            try:
                game.scenario = scenarios[game.scenario_id]
            except KeyError as error:
                raise ValueError(
                    f"Escenario persistido desconocido: {game.scenario_id}"
                ) from error
            excluded_locations = game.scenario.excluded_locations
        else:
            game.scenario = None
            excluded_locations = None
        game.map = Map.load_map(exclude_ids=excluded_locations)
        return game

    def initial_setup(self) -> list[str]:
        """Perform the historical setup operations used by compatibility callers."""
        if self.scenario is None or self.map is None:
            raise ValueError("La partida requiere escenario y mapa para inicializarse")

        report = ["### __Setup inicial__"]
        self.turn_events.append("**Setup inicial**")
        power_ids = list(self.scenario.powers)
        random.shuffle(power_ids)
        garrisons = [
            key
            for key, province in self.map.provinces.items()
            if province.city == "fortified"
        ]

        for player, power_id in zip(self.players, power_ids, strict=False):
            power = self.scenario.powers[power_id]
            report.append(
                f"<@{player.discord_id}> ({player.player_id}) dirigirá a {power.name}"
            )
            self.turn_events.append(
                f"- <@{player.discord_id}> ({player.player_id}) dirigirá a {power.name}"
            )
            player.assign_power_from_scenario(power_id, power, power_ids)
            garrisons = [
                province
                for province in garrisons
                if province not in power.controlled_provinces
            ]

        self.independent_garrisons = garrisons
        return report

    def spring_start(self) -> list[str]:
        """Resolve famine and income at the beginning of spring."""
        if self.scenario is None or self.map is None:
            raise ValueError("La partida requiere escenario y mapa")

        report: list[str] = []
        year = self.scenario.year + self.turn_number // 4
        self.turn_events.append(f"\n__Primavera de {year}__")
        self.famine = []

        if self.scenario.rules.famine_active and self.turn_number > 0:
            self.turn_events.append("**Fase de Hambre**")
            report.append(f"### __Primavera de {year}: Hambre__")
            dice = random.randint(1, 6)
            famine = GameTables.disasters[dice - 1]
            report.append(f"- **Fase de hambre**: 1d6 => {dice}. {famine[1]}")
            self.turn_events.append(f"- **Hambre (=>{dice}):** {famine[1]}")

            if famine[0] in ["both", "row"]:
                dice = random.randint(1, 6) + random.randint(1, 6)
                row = GameTables.famine[dice - 2]
                famine_provinces = {
                    key: province
                    for key, province in self.map.provinces.items()
                    if key in row
                }
                self.famine.extend(famine_provinces)
                names = [province.name for province in famine_provinces.values()]
                report.append(
                    f"  * **Fila**: 2d6 => {dice}, **Hambre** en {', '.join(names)}"
                )
                joined_names = " y ".join([", ".join(names[:-1]), names[-1]])
                self.turn_events.append(f"* **Fila (=>{dice}):** {joined_names}")

            if famine[0] in ["both", "column"]:
                dice = random.randint(1, 6) + random.randint(1, 6)
                column = [row[dice - 2] for row in GameTables.famine]
                famine_provinces = {
                    key: province
                    for key, province in self.map.provinces.items()
                    if key in column
                }
                self.famine.extend(famine_provinces)
                names = [province.name for province in famine_provinces.values()]
                report.append(
                    f"  * **Columna**: 2d6 => {dice}, **Hambre** en {', '.join(names)}"
                )
                joined_names = " y ".join([", ".join(names[:-1]), names[-1]])
                self.turn_events.append(f"* **Fila (=>{dice}):** {joined_names}")

        report.append(f"### __Primavera de {year}: Ingresos__")
        self.turn_events.append("**Fase de Ingresos**")

        for player in self.players:
            if player.power is None:
                raise ValueError("Todos los jugadores deben tener potencia asignada")
            report.append(
                f"- {GameTables.powers[player.power]} (<@{player.discord_id}>)"
            )
            self.turn_events.append(
                f"- __{GameTables.powers[player.power]}__ (<@{player.discord_id}>)"
            )

            maybe_provinces = (
                set(player.controlled_locations)
                | set(player.armies)
                | {fleet.split()[0] for fleet in player.fleets}
            )
            provinces = [
                province
                for province in maybe_provinces
                if province not in self.famine
                and province not in player.rebelled_provinces
                and province not in player.rebelled_cities
            ]
            province_income = len(provinces)

            maybe_cities = {
                province
                for province in player.controlled_locations
                if province not in self.famine
                and province not in player.rebelled_cities
                and province not in player.rebelled_provinces
            } | set(player.garrisons)
            cities = [
                city
                for city in maybe_cities
                if self.map.provinces[city].city in ("city", "fortified")
            ]
            city_income = sum(
                self.map.provinces[city].major_city or 0 for city in cities
            )
            fixed_income = (
                "  * **Ingresos fijos.** Por Provincias y Mares, "
                f"{province_income} ducados. Por Ciudades, {city_income} ducados"
            )
            report.append(fixed_income)
            self.turn_events.append(fixed_income)

            variable_income = 0
            for home_country in self.scenario.variable_income_home_countries:
                if home_country in player.home_countries:
                    dice = random.randint(1, 6)
                    amount = GameTables.variable_income[home_country][dice - 1]
                    report.append(
                        "  * **Ingresos variables.** "
                        f"{GameTables.powers[home_country]} (1d6 => {dice}), "
                        f"{amount} ducados"
                    )
                    self.turn_events.append(
                        "  * **Ingresos variables.** Por nación "
                        f"{GameTables.powers[home_country]} (=>{dice}), "
                        f"{amount} ducados"
                    )
                    variable_income += amount

            for province in self.scenario.variable_income_provinces:
                if province in player.controlled_locations:
                    dice = random.randint(1, 6)
                    amount = GameTables.variable_income[province][dice - 1]
                    report.append(
                        "  * **Ingresos variables.** "
                        f"{self.map.provinces[province].name} (1d6 => {dice}), "
                        f"{amount} ducados"
                    )
                    self.turn_events.append(
                        "  * **Ingresos variables.** Por provincia "
                        f"{self.map.provinces[province].name} (=>{dice}), "
                        f"{amount} ducados"
                    )
                    variable_income += amount

            total_income = province_income + city_income + variable_income
            player.ducats += total_income
            report.append(
                f"  * **Total ingresos.** {province_income} + {city_income} + "
                f"{variable_income} = {total_income} ducados"
            )
            self.turn_events.append(f"  * **Ingresos totales.** {total_income} ducados")

        return report

    def spring_maintenance(self) -> list[str]:
        """Resolve historical spring maintenance without changing its rule order."""
        if self.scenario is None or self.map is None:
            raise ValueError("La partida requiere escenario y mapa")

        year = self.scenario.year + (self.turn_number - 1) // 4
        self.turn_events.append(f"\n__Primavera de {year}__")
        self.turn_events.append("**Fase de Mantenimiento**")

        for player in self.players:
            if player.power is None:
                raise ValueError("Todos los jugadores deben tener potencia asignada")
            self.turn_events.append(
                f"\n__{GameTables.powers[player.power]} "
                f"(<@{player.discord_id}>). Órdenes:__"
            )
            expenses = 0
            player.set_default_commands()

            for command in [item for item in player.commands if item.command == "D"]:
                unit_type, unit_id = command.actor.split()
                units = {
                    "A": player.armies,
                    "F": player.fleets,
                    "G": player.garrisons,
                }[unit_type]
                unit_name = {"A": "ejército", "F": "flota", "G": "guarnición"}[
                    unit_type
                ]
                if unit_id in units:
                    units.remove(unit_id)
                    self.turn_events.append(
                        f"- `{command}:` {unit_name.capitalize()} disuelta."
                        if unit_type != "A"
                        else f"- `{command}:` Ejército disuelto."
                    )
                else:
                    article = "el" if unit_type == "A" else "la"
                    self.turn_events.append(
                        f"- `{command}:` No existe {article} {unit_name}."
                    )

            for command in [item for item in player.commands if item.command == "M"]:
                unit_type, unit_id = command.actor.split()
                units = {
                    "A": player.armies,
                    "F": player.fleets,
                    "G": player.garrisons,
                }[unit_type]
                labels = {
                    "A": ("Ejército", "mantenido", "disuelto", "el ejército"),
                    "F": ("Flota", "mantenida", "disuelta", "la flota"),
                    "G": (
                        "Guarnición",
                        "mantenida",
                        "disuelta",
                        "la guarnición",
                    ),
                }
                label, maintained, disbanded, missing_label = labels[unit_type]
                if unit_id not in units:
                    self.turn_events.append(
                        f"- `{command}:` No existe {missing_label}."
                    )
                elif player.ducats - expenses >= 3:
                    self.turn_events.append(f"- `{command}:` {label} {maintained}.")
                    expenses += 3
                else:
                    self.turn_events.append(
                        f"- `{command}:` Sin fondos. {label} {disbanded}."
                    )
                    units.remove(unit_id)

            recruit_commands = [item for item in player.commands if item.command == "R"]
            home_countries_cities = [
                province
                for province in player.controlled_locations
                if self.scenario.province_home_country(province)
                in player.home_countries
                and self.map.provinces[province].city in ("city", "fortified")
            ]
            for command in recruit_commands:
                if player.ducats - expenses < 3:
                    self.turn_events.append(
                        f"- `{command}:` Sin fondos. Reclutamiento no realizado."
                    )
                    continue

                unit_type, unit_id = command.actor.split()
                province = self.map.provinces[unit_id]
                if unit_type in ("A", "F"):
                    if unit_id not in home_countries_cities:
                        self.turn_events.append(
                            f"- `{command}:` La provincia no es de un país natal "
                            "o no se controla. No se pudo reclutar"
                        )
                    elif unit_id in player.armies or unit_id in player.fleets:
                        self.turn_events.append(
                            f"- `{command}:` Provincia ocupada. No se pudo reclutar."
                        )
                    elif province.is_venice and unit_id in player.garrisons:
                        occupied = "Ciudad" if unit_type == "F" else "Provincia"
                        self.turn_events.append(
                            f"- `{command}:` {occupied} ocupada. No se pudo reclutar."
                        )
                    elif unit_type == "F" and not province.has_port:
                        self.turn_events.append(
                            f"- `{command}:` Las flotas solo se pueden reclutar "
                            "en puertos. No se pudo reclutar."
                        )
                    else:
                        label = "Ejército" if unit_type == "A" else "Flota"
                        self.turn_events.append(
                            f"- `{command}:` {label} reclutada en {province.name}."
                        )
                        (player.armies if unit_type == "A" else player.fleets).append(
                            unit_id
                        )
                        expenses += 3
                elif unit_type == "G":
                    if unit_id in player.rebelled_cities:
                        self.turn_events.append(
                            f"- `{command}:` Ciudad rebelada. No se pudo reclutar."
                        )
                    elif unit_id not in home_countries_cities:
                        self.turn_events.append(
                            f"- `{command}:` La provincia no es de un país natal "
                            "o no se controla. No se pudo reclutar"
                        )
                    elif unit_id in player.garrisons:
                        self.turn_events.append(
                            f"- `{command}:` Ciudad ocupada. No se pudo reclutar."
                        )
                    elif province.is_venice and (
                        unit_id in player.armies or unit_id in player.fleets
                    ):
                        self.turn_events.append(
                            f"- `{command}:` Provincia ocupada. No se pudo reclutar."
                        )
                    elif province.city != "fortified":
                        self.turn_events.append(
                            f"- `{command}:` Las guarniciones solo se pueden "
                            "reclutar en ciudades fortificadas. No se pudo reclutar."
                        )
                    else:
                        self.turn_events.append(
                            f"- `{command}:` Guarnición reclutada en {province.name}."
                        )
                        player.garrisons.append(unit_id)
                        expenses += 3

            expected_expenses = (
                len(player.armies) + len(player.fleets) + len(player.garrisons)
            ) * 3
            if expenses != expected_expenses:
                raise AssertionError(
                    f"Gasto de mantenimiento inconsistente: {expenses} != "
                    f"{expected_expenses}"
                )
            self.turn_events.append(
                f"*Ducados iniciales*: {player.ducats}. "
                f"*Gastos:* {expenses}. "
                f"*Ducados restantes*: {player.ducats - expenses}. "
            )
            player.ducats -= expenses

        return self.turn_events

    def turn_report(self) -> list[str]:
        """Return the public report for the current turn."""
        if self.scenario is None or self.map is None:
            raise ValueError("La partida requiere escenario y mapa para informar")

        year = self.scenario.year + (self.turn_number - 1) // 4
        season = (
            "Primavera (mantenimiento)",
            "Primavera (campaña)",
            "Verano",
            "Otoño",
        )[(self.turn_number - 1) % 4]
        report = [
            f"## 📜 {self.name}, turno {self.turn_number}",
            f"### 🗓️ {season} de {year}",
            "> ⚠️ **EVENTOS DEL TURNO ANTERIOR**",
        ]
        report.extend(f"> {event}" for event in self.turn_events)
        report.append("## 🗺️ REPORTE DE SITUACIÓN")

        if self.famine:
            names = [
                province.name
                for key, province in self.map.provinces.items()
                if key in self.famine
            ]
            famine = " y ".join([", ".join(names[:-1]), names[-1]])
            report.append(f"🌾 **Hambre:** {famine}")

        if self.independent_garrisons:
            names = [
                province.name
                for key, province in self.map.provinces.items()
                if key in self.independent_garrisons
            ]
            garrisons = (
                " y ".join([", ".join(names[:-1]), names[-1]])
                if len(names) > 1
                else names[0]
            )
            report.append(f"🛡️ **Guarniciones independientes:** {garrisons}")

        for player in self.players:
            report.extend(player.player_report())
        return report

    def add_event(self, turn_event: TurnEvent) -> None:
        """Append the persistable representation of a turn event."""
        self.turn_events.append(turn_event.to_record())

    def get_unit_owner(self, unit_id: str) -> Player | None:
        """Return the owner of a unit, or None for an independent garrison."""
        parts = unit_id.split(" ", 1)
        if len(parts) != 2:
            raise ValueError(
                f"Formato de identificador de unidad inválido: '{unit_id}'"
            )
        unit_type, base_location = parts
        if unit_type not in ("A", "F", "G"):
            raise ValueError(f"Tipo de unidad desconocido: '{unit_type}'")

        for player in self.players:
            units = {
                "A": player.armies,
                "F": player.fleets,
                "G": player.garrisons,
            }[unit_type]
            if any(unit.split()[0] == base_location for unit in units):
                return player

        if unit_type == "G" and base_location in self.independent_garrisons:
            return None
        raise ValueError(f"No existe ninguna unidad '{unit_id}' en el juego.")


def __getattr__(name: str) -> object:
    """Resolve temporary compatibility exports without creating import cycles."""
    if name == "TooManyExpenses":
        from machiavelli.engine.exceptions import TooManyExpenses

        return TooManyExpenses
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "Command",
    "DuplicatePlayerException",
    "DuplicatedGameException",
    "FailedToStartError",
    "Game",
    "GameNotFoundException",
    "Player",
    "PlayerNotFoundException",
]
