"""Read-only presentation of validated turn events for Discord."""

from __future__ import annotations

from collections.abc import Mapping
from typing import cast

from discord.utils import escape_markdown, escape_mentions

from machiavelli.events import (
    EventType,
    FrozenJSONValue,
    InvalidTurnEventError,
    TurnEvent,
)
from machiavelli.game.game import Game
from machiavelli.game.tables import GameTables

from .game_status_reporter import GameStatusReporter

type UnitKeyValue = tuple[str | None, str, str]
type OutcomeValue = tuple[UnitKeyValue, str, str | None, bool]
type RebellionTransitionValue = tuple[str | None, str, str, str]
type SiegeTransitionValue = tuple[UnitKeyValue, str, str]


class TurnReporter:
    """Transform structured turn facts into complete Spanish report lines."""

    EVENTS_HEADER = "## ⚠️ EVENTOS DEL TURNO"
    SITUATION_HEADER = "## 🗺️ REPORTE DE SITUACIÓN"

    @staticmethod
    def generate(game: Game) -> list[str]:
        """Render one game without mutating its state or its immutable events."""
        scenario = game.require_scenario()
        game.require_map()

        turn_index = max(game.turn_number, 1) - 1
        year = scenario.year + turn_index // len(GameTables.seasons)
        season = GameTables.seasons[turn_index % len(GameTables.seasons)]
        report = [
            f"## 📜 {TurnReporter._safe_code(game.name)}, turno {game.turn_number}",
            f"### 🗓️ {season} de {year}",
            TurnReporter.EVENTS_HEADER,
        ]

        for event in game.turn_events:
            if not isinstance(event, TurnEvent):
                raise InvalidTurnEventError(
                    "El historial contiene un valor que no es TurnEvent"
                )
            event_lines = TurnReporter._render_event(game, event)
            if not event_lines or any(not line.strip() for line in event_lines):
                raise InvalidTurnEventError(
                    f"El evento {event.type.value} no produjo una descripción válida",
                    event_type=event.type.value,
                )
            report.extend(event_lines)

        report.append(TurnReporter.SITUATION_HEADER)
        report.extend(GameStatusReporter.generate(game))
        return report

    @staticmethod
    def _render_event(game: Game, event: TurnEvent) -> list[str]:
        data = event.data

        match event.type:
            case EventType.START_GAME:
                scenario = TurnReporter._scenario(
                    game,
                    TurnReporter._text(data, "scenario"),
                )
                return [f"Comienza la partida con el escenario {scenario}."]

            case EventType.START_GAME_POWER_ASSIGNED:
                player_id = TurnReporter._text(data, "player_id")
                discord_id = TurnReporter._optional_integer(data, "discord_id")
                subject = TurnReporter._player(game, player_id)
                discord_user = TurnReporter._discord_user(game, discord_id)
                if discord_user is not None and discord_user not in subject:
                    subject = f"{subject} ({discord_user})"
                power = TurnReporter._power(
                    game,
                    TurnReporter._text(data, "power_id"),
                )
                return [f"{subject} recibe la potencia {power}."]

            case EventType.START_SEASON:
                year = TurnReporter._integer(data, "year")
                season_index = TurnReporter._integer(data, "season")
                season = GameTables.seasons[season_index]
                return [f"Comienza {season} de {year}."]

            case EventType.FAMINE_SPAWN:
                roll = TurnReporter._integer(data, "severity_roll")
                provinces = TurnReporter._locations(
                    game,
                    TurnReporter._string_sequence(data, "provinces"),
                )
                return [
                    f"La hambruna aparece tras una tirada de {roll}: "
                    f"{TurnReporter._join(provinces)}."
                ]

            case EventType.FAMINE_RELIEF:
                player = TurnReporter._player(
                    game,
                    TurnReporter._text(data, "player"),
                )
                province = TurnReporter._location(
                    game,
                    TurnReporter._text(data, "province"),
                )
                return [f"{player} reduce la hambruna en {province}."]

            case EventType.FAMINE_ATTRITION:
                affected_player_id = TurnReporter._optional_text(data, "player")
                owner = TurnReporter._owner(game, affected_player_id)
                units = TurnReporter._unit_strings(
                    game,
                    TurnReporter._string_sequence(data, "units"),
                )
                return [
                    f"La hambruna elimina unidades de {owner}: "
                    f"{TurnReporter._join(units)}."
                ]

            case EventType.FAMINE_END:
                provinces = TurnReporter._locations(
                    game,
                    TurnReporter._string_sequence(data, "provinces"),
                )
                return [f"Finaliza la hambruna en {TurnReporter._join(provinces)}."]

            case EventType.PLAGUE_SPAWN:
                roll = TurnReporter._integer(data, "severity_roll")
                provinces = TurnReporter._locations(
                    game,
                    TurnReporter._string_sequence(data, "provinces"),
                )
                return [
                    f"La peste aparece tras una tirada de {roll}: "
                    f"{TurnReporter._join(provinces)}."
                ]

            case EventType.PLAGUE_DEATH:
                affected_player_id = TurnReporter._optional_text(data, "player")
                owner = TurnReporter._owner(game, affected_player_id)
                units = TurnReporter._unit_strings(
                    game,
                    TurnReporter._string_sequence(data, "units"),
                )
                return [
                    f"La peste elimina unidades de {owner}: "
                    f"{TurnReporter._join(units)}."
                ]

            case EventType.REBELLION_PACIFY:
                player = TurnReporter._player(
                    game,
                    TurnReporter._text(data, "player"),
                )
                province = TurnReporter._location(
                    game,
                    TurnReporter._text(data, "province"),
                )
                kind = TurnReporter._rebellion_kind(TurnReporter._text(data, "kind"))
                return [f"{player} pacifica la rebelión {kind} de {province}."]

            case EventType.REBELLION_PROVINCE:
                player = TurnReporter._player(
                    game,
                    TurnReporter._text(data, "player"),
                )
                province = TurnReporter._location(
                    game,
                    TurnReporter._text(data, "province"),
                )
                return [f"Se inicia una rebelión provincial de {player} en {province}."]

            case EventType.REBELLION_CITY:
                player = TurnReporter._player(
                    game,
                    TurnReporter._text(data, "player"),
                )
                province = TurnReporter._location(
                    game,
                    TurnReporter._text(data, "province"),
                )
                return [f"Se inicia una rebelión urbana de {player} en {province}."]

            case EventType.EXPENSE:
                return [TurnReporter._expense_line(game, data, status="ejecuta")]

            case EventType.EXPENSE_NO_FUNDS:
                return [
                    TurnReporter._expense_line(
                        game,
                        data,
                        status="no puede ejecutar por falta de fondos",
                    )
                ]

            case EventType.EXPENSE_SYNTAX_ERROR:
                return [
                    TurnReporter._expense_line(
                        game,
                        data,
                        status="presenta con sintaxis inválida",
                    )
                ]

            case EventType.BRIBE_EXECUTED:
                return [TurnReporter._expense_line(game, data, status="ejecuta")]

            case EventType.INCOME_COLLECTED:
                return TurnReporter._income_lines(game, data)

            case EventType.MAINTENANCE_ORDER_RESOLVED:
                return [TurnReporter._maintenance_order_line(game, data)]

            case EventType.MAINTENANCE_SUMMARY:
                player = TurnReporter._player(
                    game,
                    TurnReporter._text(data, "player"),
                )
                initial = TurnReporter._integer(data, "initial_ducats")
                expenses = TurnReporter._integer(data, "expenses")
                remaining = TurnReporter._integer(data, "remaining_ducats")
                return [
                    f"Resumen de mantenimiento de {player}: {initial} ducados "
                    f"iniciales, {expenses} gastados y {remaining} restantes."
                ]

            case EventType.GET_CONTROL:
                player = TurnReporter._player(
                    game,
                    TurnReporter._text(data, "player"),
                )
                provinces = TurnReporter._locations(
                    game,
                    TurnReporter._string_sequence(data, "provinces"),
                )
                return [
                    f"{player} obtiene el control de {TurnReporter._join(provinces)}."
                ]

            case EventType.LOSE_CONTROL:
                player = TurnReporter._player(
                    game,
                    TurnReporter._text(data, "player"),
                )
                provinces = TurnReporter._locations(
                    game,
                    TurnReporter._string_sequence(data, "provinces"),
                )
                return [
                    f"{player} pierde el control de {TurnReporter._join(provinces)}."
                ]

            case EventType.GET_HOME_COUNTRY:
                player = TurnReporter._player(
                    game,
                    TurnReporter._text(data, "player"),
                )
                power = TurnReporter._power(
                    game,
                    TurnReporter._text(data, "home_country"),
                )
                return [f"{player} obtiene el control de {power}."]

            case EventType.LOSE_HOME_COUNTRY:
                player = TurnReporter._player(
                    game,
                    TurnReporter._text(data, "player"),
                )
                power = TurnReporter._power(
                    game,
                    TurnReporter._text(data, "home_country"),
                )
                return [f"{player} pierde el control de {power}."]

            case EventType.PLAYER_ELIMINATED:
                player = TurnReporter._player(
                    game,
                    TurnReporter._text(data, "player"),
                )
                return [f"{player} queda eliminado de la partida."]

            case EventType.PLAYER_WON:
                player = TurnReporter._player(
                    game,
                    TurnReporter._text(data, "player"),
                )
                cities = TurnReporter._integer(data, "cities")
                home_countries = TurnReporter._integer(data, "home_countries")
                return [
                    f"{player} gana la partida con {cities} ciudades y "
                    f"{home_countries} naciones controladas."
                ]

            case EventType.MILITARY_RESOLUTION:
                return TurnReporter._military_lines(game, data)

        raise InvalidTurnEventError(
            "Tipo de evento sin representación",
            event_type=event.type.value,
        )

    @staticmethod
    def _expense_line(
        game: Game,
        data: Mapping[str, FrozenJSONValue],
        *,
        status: str,
    ) -> str:
        player = TurnReporter._player(game, TurnReporter._text(data, "player"))
        expense_code = TurnReporter._text(data, "expense")
        expense = GameTables.expenses.get(expense_code)
        expense_name = (
            expense["text"]
            if expense is not None
            else TurnReporter._safe_code(expense_code)
        )
        target_code = TurnReporter._optional_text(data, "target")
        target = TurnReporter._expense_target(game, expense_code, target_code)
        amount_value = data["amount"]
        amount = (
            str(amount_value)
            if isinstance(amount_value, int) and not isinstance(amount_value, bool)
            else TurnReporter._safe_code(cast(str, amount_value))
        )
        target_fragment = f" sobre {target}" if target is not None else ""
        return (
            f"{player} {status} el gasto {expense_name}{target_fragment} "
            f"por {amount} ducados."
        )

    @staticmethod
    def _expense_target(
        game: Game,
        expense_code: str,
        target: str | None,
    ) -> str | None:
        if target is None:
            return None
        expense = GameTables.expenses.get(expense_code)
        if expense is None:
            return TurnReporter._safe_code(target)
        match expense["target_type"]:
            case "province":
                return TurnReporter._location(game, target)
            case "power":
                return TurnReporter._power(game, target)
            case "unit":
                return TurnReporter._unit_string(game, target)

    @staticmethod
    def _income_lines(
        game: Game,
        data: Mapping[str, FrozenJSONValue],
    ) -> list[str]:
        player = TurnReporter._player(game, TurnReporter._text(data, "player"))
        province_income = TurnReporter._integer(data, "province_income")
        city_income = TurnReporter._integer(data, "city_income")
        total_income = TurnReporter._integer(data, "total_income")
        provinces = TurnReporter._locations(
            game,
            TurnReporter._string_sequence(data, "provinces"),
        )
        cities = TurnReporter._locations(
            game,
            TurnReporter._string_sequence(data, "cities"),
        )
        lines = [
            f"{player} recauda {total_income} ducados en total.",
            f"Ingreso provincial ({province_income}): "
            f"{TurnReporter._join(provinces, empty='ninguna provincia')}.",
            f"Ingreso urbano ({city_income}): "
            f"{TurnReporter._join(cities, empty='ninguna ciudad')}.",
        ]

        variable_income = cast(
            tuple[Mapping[str, FrozenJSONValue], ...],
            data["variable_income"],
        )
        for source in variable_income:
            source_type = TurnReporter._text(source, "source_type")
            source_code = TurnReporter._text(source, "source")
            source_name = (
                TurnReporter._power(game, source_code)
                if source_type == "home_country"
                else TurnReporter._location(game, source_code)
            )
            roll = TurnReporter._integer(source, "roll")
            amount = TurnReporter._integer(source, "amount")
            lines.append(
                f"Ingreso variable de {source_name}: tirada {roll}, {amount} ducados."
            )
        return lines

    @staticmethod
    def _maintenance_order_line(
        game: Game,
        data: Mapping[str, FrozenJSONValue],
    ) -> str:
        player = TurnReporter._player(game, TurnReporter._text(data, "player"))
        actor = TurnReporter._unit_string(game, TurnReporter._text(data, "actor"))
        order_code = TurnReporter._text(data, "order")
        order = GameTables.maintenance_orders[order_code]["text"]
        target_code = TurnReporter._optional_text(data, "target")
        target = (
            f" con objetivo {TurnReporter._safe_code(target_code)}"
            if target_code is not None
            else ""
        )
        result = TurnReporter._maintenance_result(TurnReporter._text(data, "result"))
        cost = TurnReporter._integer(data, "cost")
        return (
            f"Mantenimiento de {player}: {actor}, orden {order}{target}; "
            f"resultado {result}; coste {cost} ducados."
        )

    @staticmethod
    def _military_lines(
        game: Game,
        data: Mapping[str, FrozenJSONValue],
    ) -> list[str]:
        outcomes = cast(tuple[OutcomeValue, ...], data["outcomes"])
        cancelled_orders = cast(
            tuple[UnitKeyValue, ...],
            data["cancelled_orders"],
        )
        broken_convoys = cast(
            tuple[UnitKeyValue, ...],
            data["broken_convoys"],
        )
        dislodgements = cast(
            tuple[UnitKeyValue, ...],
            data["dislodgements"],
        )
        rebellions = cast(
            tuple[RebellionTransitionValue, ...],
            data["rebellions"],
        )
        sieges = cast(tuple[SiegeTransitionValue, ...], data["sieges"])

        if not any(
            (
                outcomes,
                cancelled_orders,
                broken_convoys,
                dislodgements,
                rebellions,
                sieges,
            )
        ):
            return ["Sin cambios militares."]

        lines: list[str] = []
        for unit, final_unit_type, final_location, dislodged in outcomes:
            original = TurnReporter._unit_key(game, unit)
            final_type = TurnReporter._unit_type(final_unit_type)
            if dislodged:
                final = f"{final_type}, desalojada"
            else:
                assert final_location is not None
                final = (
                    f"{final_type} en {TurnReporter._location(game, final_location)}"
                )
            lines.append(f"Resultado: {original} → {final}.")

        lines.extend(
            f"Orden cancelada: {TurnReporter._unit_key(game, unit)}."
            for unit in cancelled_orders
        )
        lines.extend(
            f"Convoy roto: {TurnReporter._unit_key(game, unit)}."
            for unit in broken_convoys
        )
        lines.extend(
            f"Desalojo: {TurnReporter._unit_key(game, unit)}." for unit in dislodgements
        )

        for player_id, kind_code, province_code, transition_code in rebellions:
            owner = TurnReporter._owner(game, player_id)
            kind = TurnReporter._rebellion_kind(kind_code)
            province = TurnReporter._location(game, province_code)
            transition = {
                "subdued": "sofocada",
                "liberated": "liberada",
            }[transition_code]
            lines.append(f"Rebelión: {kind} de {owner} en {province}, {transition}.")

        for unit, province_code, transition_code in sieges:
            rendered_unit = TurnReporter._unit_key(game, unit)
            province = TurnReporter._location(game, province_code)
            transition = {
                "started": "iniciado",
                "completed": "completado",
                "lifted": "levantado",
            }[transition_code]
            lines.append(f"Asedio: {rendered_unit} sobre {province}, {transition}.")
        return lines

    @staticmethod
    def _scenario(game: Game, scenario_code: str) -> str:
        scenario = game.require_scenario()
        if scenario_code in {game.scenario_id, scenario.name}:
            return scenario.name
        return TurnReporter._safe_code(scenario_code)

    @staticmethod
    def _player(game: Game, player_id: str) -> str:
        player = next(
            (
                candidate
                for candidate in game.players
                if candidate.player_id == player_id
            ),
            None,
        )
        if player is None:
            return TurnReporter._safe_code(player_id)

        power = TurnReporter._power(game, player.power) if player.power else None
        if player.discord_id is not None:
            mention = f"<@{player.discord_id}>"
            return f"{mention} ({power})" if power is not None else mention
        if power is not None:
            return power
        return TurnReporter._safe_code(player.player_id)

    @staticmethod
    def _discord_user(game: Game, discord_id: int | None) -> str | None:
        if discord_id is None:
            return None
        if any(player.discord_id == discord_id for player in game.players):
            return f"<@{discord_id}>"
        return TurnReporter._safe_code(f"@{discord_id}")

    @staticmethod
    def _owner(game: Game, player_id: str | None) -> str:
        return (
            "una guarnición independiente"
            if player_id is None
            else TurnReporter._player(game, player_id)
        )

    @staticmethod
    def _power(game: Game, power_code: str) -> str:
        scenario = game.scenario
        if scenario is not None:
            power = scenario.powers.get(power_code)
            if power is not None and power.name:
                return power.name
        public_name = GameTables.powers.get(power_code)
        return public_name or TurnReporter._safe_code(power_code)

    @staticmethod
    def _location(game: Game, location_code: str) -> str:
        game_map = game.require_map()
        locations = game_map.provinces | game_map.seas
        base, separator, coast = location_code.partition(" ")
        location = locations.get(location_code)
        if location is not None:
            if separator and coast:
                return f"{location.name} ({TurnReporter._safe_code(coast)})"
            return location.name

        base_location = locations.get(base)
        if base_location is not None and separator and coast:
            return f"{base_location.name} ({TurnReporter._safe_code(coast)})"
        return TurnReporter._safe_code(location_code)

    @staticmethod
    def _locations(game: Game, location_codes: tuple[str, ...]) -> list[str]:
        return [TurnReporter._location(game, code) for code in location_codes]

    @staticmethod
    def _unit_type(unit_type: str) -> str:
        return GameTables.actors.get(unit_type, TurnReporter._safe_code(unit_type))

    @staticmethod
    def _unit_string(game: Game, unit_code: str) -> str:
        unit_type, separator, location = unit_code.partition(" ")
        if not separator or not location:
            return TurnReporter._safe_code(unit_code)
        return (
            f"{TurnReporter._unit_type(unit_type)} en "
            f"{TurnReporter._location(game, location)}"
        )

    @staticmethod
    def _unit_strings(game: Game, unit_codes: tuple[str, ...]) -> list[str]:
        return [TurnReporter._unit_string(game, code) for code in unit_codes]

    @staticmethod
    def _unit_key(game: Game, unit: UnitKeyValue) -> str:
        player_id, unit_type, origin = unit
        owner = TurnReporter._owner(game, player_id)
        return (
            f"{TurnReporter._unit_type(unit_type)} de {owner} en "
            f"{TurnReporter._location(game, origin)}"
        )

    @staticmethod
    def _rebellion_kind(kind: str) -> str:
        return {"province": "provincial", "city": "urbana"}[kind]

    @staticmethod
    def _maintenance_result(result: str) -> str:
        return {
            "disbanded": "desbandada",
            "unit_not_found": "unidad no encontrada",
            "maintained": "mantenida",
            "disbanded_no_funds": "desbandada por falta de fondos",
            "recruited": "reclutada",
            "recruitment_no_funds": "reclutamiento rechazado por falta de fondos",
            "invalid_home_or_control": "ubicación natal o control inválidos",
            "space_occupied": "espacio ocupado",
            "port_required": "puerto requerido",
            "rebelled_city": "ciudad en rebelión",
            "fortified_city_required": "ciudad fortificada requerida",
        }[result]

    @staticmethod
    def _join(values: list[str], *, empty: str = "ninguno") -> str:
        if not values:
            return empty
        if len(values) == 1:
            return values[0]
        return f"{', '.join(values[:-1])} y {values[-1]}"

    @staticmethod
    def _safe_code(value: str) -> str:
        escaped_markdown = escape_markdown(value, as_needed=False)
        return escape_mentions(escaped_markdown)

    @staticmethod
    def _text(data: Mapping[str, FrozenJSONValue], key: str) -> str:
        return cast(str, data[key])

    @staticmethod
    def _optional_text(
        data: Mapping[str, FrozenJSONValue],
        key: str,
    ) -> str | None:
        return cast(str | None, data[key])

    @staticmethod
    def _integer(data: Mapping[str, FrozenJSONValue], key: str) -> int:
        return cast(int, data[key])

    @staticmethod
    def _optional_integer(
        data: Mapping[str, FrozenJSONValue],
        key: str,
    ) -> int | None:
        return cast(int | None, data[key])

    @staticmethod
    def _string_sequence(
        data: Mapping[str, FrozenJSONValue],
        key: str,
    ) -> tuple[str, ...]:
        return cast(tuple[str, ...], data[key])


__all__ = ["TurnReporter"]
