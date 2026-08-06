"""Eventos de turno y serialización estable de la resolución militar."""

import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Self


class EventType(StrEnum):
    # Inicio de fases
    START_GAME = "start_game"
    START_SEASON = "start_season"

    # Inicio de partida
    START_GAME_POWER_ASSIGNED = "start_game_power_assigned"

    # Ingresos
    PLAYER_INCOME = "player_income"

    # Mantenimiento
    PLAYER_MAINTENANCE = "player_maintenance"

    # Desastres
    FAMINE_SPAWN = "famine_spawn"
    FAMINE_ATTRITION = "famine_attrition"
    FAMINE_END = "famine_end"
    PLAGUE_SPAWN = "plague_spawn"
    PLAGUE_DEATH = "plague_death"

    # Rebeliones
    REBELLION_PACIFY = "rebellion_pacify"
    REBELLION_PROVINCE = "rebellion_province"
    REBELLION_CITY = "rebellion_city"

    # Gastos (ExpenditureProcessor)
    EXPENSE = "expense"
    EXPENSE_NO_FUNDS = "expense_no_funds"
    EXPENSE_SYNTAX_ERROR = "expense_syntax_error"

    # Sobornos (BribeResolver)
    BRIBE_SET = "bribe_set"
    BRIBE_EXECUTED = "bribe_executed"

    # Control territorial y condición de victoria
    GET_CONTROL = "get_control"
    LOSE_CONTROL = "lose_control"
    GET_HOME_COUNTRY = "get_home_country"
    LOSE_HOME_COUNTRY = "lose_home_country"
    PLAYER_ELIMINATED = "player_eliminated"
    PLAYER_WON = "player_won"

    # Resolución militar
    MILITARY_RESOLUTION = "military_resolution"


@dataclass(frozen=True, slots=True)
class TurnEvent:
    """Evento de dominio preparado para su persistencia en el historial del turno."""

    type: EventType
    data: dict[str, Any]

    @classmethod
    def expense(
        cls,
        event_type: EventType,
        actor: str,
        expense_type: str,
        target: str | None,
        amount: int | str,
    ) -> Self:
        """Factory method para construir eventos de gasto."""
        return cls(
            type=event_type,
            data={
                "player": actor,
                "expense": expense_type,
                "target": target,
                "amount": int(amount) if str(amount).isdigit() else amount,
            },
        )

    @classmethod
    def military_resolution(
        cls,
        outcomes: list[list[object]],
        cancelled_orders: list[list[object]],
        broken_convoys: list[list[object]],
        dislodgements: list[list[object]],
        rebellions: list[list[object]],
        sieges: list[list[object]],
    ) -> Self:
        """Construye el único registro auditable de una campaña militar."""
        # Cada colección se valida y ordena antes de formar el registro auditable.
        data = {
            "outcomes": _canonicalize(outcomes, _outcome),
            "cancelled_orders": _canonicalize(cancelled_orders, _unit_key),
            "broken_convoys": _canonicalize(broken_convoys, _unit_key),
            "dislodgements": _canonicalize(dislodgements, _unit_key),
            "rebellions": _canonicalize(rebellions, _rebellion),
            "sieges": _canonicalize(sieges, _siege),
        }
        return cls(
            EventType.MILITARY_RESOLUTION,
            data,
        )

    def to_record(self) -> str:
        """Devuelve el formato persistido, preservando eventos anteriores."""
        # Los eventos históricos conservan exactamente su representación anterior.
        if self.type is not EventType.MILITARY_RESOLUTION:
            return str(self.type)
        payload = json.dumps(
            self.data,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return f"{self.type}|{payload}"


def _canonicalize(values: list[list[object]], validator: Any) -> list[list[object]]:
    """Valida una colección militar y devuelve su orden canónico."""
    if not isinstance(values, list):
        raise ValueError("Las listas del evento militar deben ser listas")
    canonical = [validator(value) for value in values]
    return sorted(canonical, key=_record_sort_key)


def _unit_key(value: object) -> list[object]:
    """Valida la identidad primitiva de una unidad militar."""
    if (
        not isinstance(value, list)
        or len(value) != 3
        or value[0] is not None
        and not isinstance(value[0], str)
        or not isinstance(value[1], str)
        or value[1] not in {"A", "F", "G"}
        or not isinstance(value[2], str)
        or not value[2]
    ):
        raise ValueError("Clave de unidad militar inválida")
    return value.copy()


def _outcome(value: object) -> list[object]:
    """Valida un resultado y la coherencia entre desalojo y destino."""
    if (
        not isinstance(value, list)
        or len(value) != 4
        or not isinstance(value[1], str)
        or value[1] not in {"A", "F", "G"}
        or value[2] is not None
        and not isinstance(value[2], str)
        or isinstance(value[2], str)
        and not value[2]
        or not isinstance(value[3], bool)
        or value[3]
        and value[2] is not None
        or not value[3]
        and not isinstance(value[2], str)
    ):
        raise ValueError("Resultado militar inválido")
    return [_unit_key(value[0]), value[1], value[2], value[3]]


def _rebellion(value: object) -> list[object]:
    """Valida una transición de rebelión serializable."""
    if (
        not isinstance(value, list)
        or len(value) != 4
        or value[0] is not None
        and not isinstance(value[0], str)
        or not isinstance(value[1], str)
        or value[1] not in {"province", "city"}
        or not isinstance(value[2], str)
        or not value[2]
        or not isinstance(value[3], str)
        or value[3] not in {"subdued", "liberated"}
    ):
        raise ValueError("Rebelión militar inválida")
    return value.copy()


def _siege(value: object) -> list[object]:
    """Valida una transición de asedio y su unidad responsable."""
    if (
        not isinstance(value, list)
        or len(value) != 3
        or not isinstance(value[1], str)
        or not value[1]
        or not isinstance(value[2], str)
        or value[2] not in {"started", "completed", "lifted"}
    ):
        raise ValueError("Asedio militar inválido")
    return [_unit_key(value[0]), value[1], value[2]]


def _record_sort_key(value: list[object]) -> str:
    """Genera una clave textual estable para ordenar registros heterogéneos."""
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
