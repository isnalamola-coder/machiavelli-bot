"""Closed, validated, and deeply immutable turn-event contract."""

from __future__ import annotations

import json
import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import cast

type JSONScalar = None | bool | int | float | str
type JSONValue = JSONScalar | list[JSONValue] | dict[str, JSONValue]
type FrozenJSONValue = (
    JSONScalar | tuple[FrozenJSONValue, ...] | Mapping[str, FrozenJSONValue]
)


class EventType(StrEnum):
    """Complete public catalog of facts produced by one game turn."""

    START_GAME = "start_game"
    START_GAME_POWER_ASSIGNED = "start_game_power_assigned"
    START_SEASON = "start_season"
    FAMINE_SPAWN = "famine_spawn"
    FAMINE_RELIEF = "famine_relief"
    FAMINE_ATTRITION = "famine_attrition"
    FAMINE_END = "famine_end"
    PLAGUE_SPAWN = "plague_spawn"
    PLAGUE_DEATH = "plague_death"
    REBELLION_PACIFY = "rebellion_pacify"
    REBELLION_PROVINCE = "rebellion_province"
    REBELLION_CITY = "rebellion_city"
    EXPENSE = "expense"
    EXPENSE_NO_FUNDS = "expense_no_funds"
    EXPENSE_SYNTAX_ERROR = "expense_syntax_error"
    BRIBE_EXECUTED = "bribe_executed"
    INCOME_COLLECTED = "income_collected"
    MAINTENANCE_ORDER_RESOLVED = "maintenance_order_resolved"
    MAINTENANCE_SUMMARY = "maintenance_summary"
    GET_CONTROL = "get_control"
    LOSE_CONTROL = "lose_control"
    GET_HOME_COUNTRY = "get_home_country"
    LOSE_HOME_COUNTRY = "lose_home_country"
    PLAYER_ELIMINATED = "player_eliminated"
    PLAYER_WON = "player_won"
    MILITARY_RESOLUTION = "military_resolution"


class InvalidTurnEventError(ValueError):
    """Raised when a turn event does not satisfy its closed payload contract."""

    def __init__(
        self,
        message: str,
        *,
        row_id: int | None = None,
        event_type: str | None = None,
    ) -> None:
        super().__init__(message)
        self.row_id = row_id
        self.event_type = event_type


type Validator[T] = Callable[[object], T]


def _exact_object(
    value: object, fields: Mapping[str, Validator[object]]
) -> dict[str, object]:
    if not isinstance(value, Mapping):
        raise TypeError("El payload del evento debe ser un objeto JSON")
    actual_keys = set(value)
    expected_keys = set(fields)
    if actual_keys != expected_keys:
        missing = sorted(expected_keys - actual_keys)
        extra = sorted(actual_keys - expected_keys, key=str)
        raise ValueError(
            f"Claves de payload inválidas; faltan={missing}, sobran={extra}"
        )
    return {name: validator(value[name]) for name, validator in fields.items()}


def _string(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TypeError("Se esperaba un string no vacío")
    return value


def _nullable_string(value: object) -> str | None:
    return None if value is None else _string(value)


def _integer(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError("Se esperaba un entero JSON")
    return value


def _nonnegative_integer(value: object) -> int:
    result = _integer(value)
    if result < 0:
        raise ValueError("El entero no puede ser negativo")
    return result


def _nullable_integer(value: object) -> int | None:
    return None if value is None else _integer(value)


def _boolean(value: object) -> bool:
    if not isinstance(value, bool):
        raise TypeError("Se esperaba un booleano JSON")
    return value


def _choice(*values: str) -> Validator[str]:
    allowed = frozenset(values)

    def validate(value: object) -> str:
        result = _string(value)
        if result not in allowed:
            raise ValueError(f"Valor fuera del catálogo cerrado: {result}")
        return result

    return validate


def _roll(value: object) -> int:
    result = _integer(value)
    if not 1 <= result <= 6:
        raise ValueError("La tirada debe estar entre 1 y 6")
    return result


def _season(value: object) -> int:
    result = _integer(value)
    if not 0 <= result <= 3:
        raise ValueError("La estación debe estar entre 0 y 3")
    return result


def _amount(value: object) -> int | str:
    if isinstance(value, bool):
        raise TypeError("Un booleano no es un importe")
    if isinstance(value, int):
        return value
    return _string(value)


def _sequence[T](
    value: object,
    item_validator: Validator[T],
    *,
    allow_empty: bool = True,
) -> list[T]:
    if not isinstance(value, (list, tuple)):
        raise TypeError("Se esperaba una lista o tupla")
    result = [item_validator(item) for item in value]
    if not allow_empty and not result:
        raise ValueError("La colección no puede estar vacía")
    return result


def _strings(value: object, *, allow_empty: bool = True) -> list[str]:
    return _sequence(value, _string, allow_empty=allow_empty)


def _variable_income(value: object) -> dict[str, object]:
    return _exact_object(
        value,
        {
            "source_type": _choice("home_country", "province"),
            "source": _string,
            "roll": _roll,
            "amount": _nonnegative_integer,
        },
    )


def _unit_key(value: object) -> list[object]:
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise TypeError("Clave de unidad militar inválida")
    return [
        _nullable_string(value[0]),
        _choice("A", "F", "G")(value[1]),
        _string(value[2]),
    ]


def _outcome(value: object) -> list[object]:
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        raise TypeError("Resultado militar inválido")
    unit = _unit_key(value[0])
    final_unit_type = _choice("A", "F", "G")(value[1])
    final_location = _nullable_string(value[2])
    dislodged = _boolean(value[3])
    if dislodged and final_location is not None:
        raise ValueError("Una unidad desalojada no conserva localización final")
    if not dislodged and final_location is None:
        raise ValueError("Una unidad no desalojada requiere localización final")
    return [unit, final_unit_type, final_location, dislodged]


def _rebellion_transition(value: object) -> list[object]:
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        raise TypeError("Transición de rebelión inválida")
    return [
        _nullable_string(value[0]),
        _choice("province", "city")(value[1]),
        _string(value[2]),
        _choice("subdued", "liberated")(value[3]),
    ]


def _siege_transition(value: object) -> list[object]:
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise TypeError("Transición de asedio inválida")
    return [
        _unit_key(value[0]),
        _string(value[1]),
        _choice("started", "completed", "lifted")(value[2]),
    ]


def _record_sort_key(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _canonical_sequence[T](value: object, validator: Validator[T]) -> list[T]:
    return sorted(_sequence(value, validator), key=_record_sort_key)


def _validate_start_game(data: object) -> dict[str, object]:
    return _exact_object(data, {"scenario": _string})


def _validate_power_assigned(data: object) -> dict[str, object]:
    return _exact_object(
        data,
        {
            "player_id": _string,
            "discord_id": _nullable_integer,
            "power_id": _string,
        },
    )


def _validate_start_season(data: object) -> dict[str, object]:
    return _exact_object(data, {"year": _integer, "season": _season})


def _validate_spawn(data: object) -> dict[str, object]:
    return _exact_object(
        data,
        {
            "severity_roll": _roll,
            "provinces": lambda value: _strings(value, allow_empty=False),
        },
    )


def _validate_famine_relief(data: object) -> dict[str, object]:
    return _exact_object(data, {"player": _string, "province": _string})


def _validate_disaster_death(data: object) -> dict[str, object]:
    return _exact_object(
        data,
        {
            "player": _nullable_string,
            "units": lambda value: _strings(value, allow_empty=False),
        },
    )


def _validate_provinces_only(data: object) -> dict[str, object]:
    return _exact_object(
        data, {"provinces": lambda value: _strings(value, allow_empty=False)}
    )


def _validate_rebellion_pacify(data: object) -> dict[str, object]:
    return _exact_object(
        data,
        {
            "player": _string,
            "province": _string,
            "kind": _choice("province", "city"),
        },
    )


def _validate_player_province(data: object) -> dict[str, object]:
    return _exact_object(data, {"player": _string, "province": _string})


def _validate_expense(data: object) -> dict[str, object]:
    return _exact_object(
        data,
        {
            "player": _string,
            "expense": _string,
            "target": _nullable_string,
            "amount": _amount,
        },
    )


def _validate_bribe(data: object) -> dict[str, object]:
    return _exact_object(
        data,
        {
            "player": _string,
            "expense": _string,
            "target": _string,
            "amount": _nonnegative_integer,
        },
    )


def _validate_income(data: object) -> dict[str, object]:
    result = _exact_object(
        data,
        {
            "player": _string,
            "provinces": _strings,
            "province_income": _nonnegative_integer,
            "cities": _strings,
            "city_income": _nonnegative_integer,
            "variable_income": lambda value: _sequence(value, _variable_income),
            "total_income": _nonnegative_integer,
        },
    )
    variable_items = cast(list[dict[str, object]], result["variable_income"])
    expected_total = (
        cast(int, result["province_income"])
        + cast(int, result["city_income"])
        + sum(cast(int, item["amount"]) for item in variable_items)
    )
    if result["total_income"] != expected_total:
        raise ValueError("El total de ingresos no coincide con sus subtotales")
    return result


_MAINTENANCE_RESULTS = (
    "disbanded",
    "unit_not_found",
    "maintained",
    "disbanded_no_funds",
    "recruited",
    "recruitment_no_funds",
    "invalid_home_or_control",
    "space_occupied",
    "port_required",
    "rebelled_city",
    "fortified_city_required",
)


def _validate_maintenance_order(data: object) -> dict[str, object]:
    return _exact_object(
        data,
        {
            "player": _string,
            "actor": _string,
            "order": _choice("D", "M", "R"),
            "target": _nullable_string,
            "result": _choice(*_MAINTENANCE_RESULTS),
            "cost": _nonnegative_integer,
        },
    )


def _validate_maintenance_summary(data: object) -> dict[str, object]:
    result = _exact_object(
        data,
        {
            "player": _string,
            "initial_ducats": _nonnegative_integer,
            "expenses": _nonnegative_integer,
            "remaining_ducats": _nonnegative_integer,
        },
    )
    if cast(int, result["initial_ducats"]) - cast(int, result["expenses"]) != cast(
        int, result["remaining_ducats"]
    ):
        raise ValueError("El resumen de mantenimiento no cuadra")
    return result


def _validate_control(data: object) -> dict[str, object]:
    return _exact_object(
        data,
        {
            "player": _string,
            "provinces": lambda value: _strings(value, allow_empty=False),
        },
    )


def _validate_home_country(data: object) -> dict[str, object]:
    return _exact_object(data, {"player": _string, "home_country": _string})


def _validate_player(data: object) -> dict[str, object]:
    return _exact_object(data, {"player": _string})


def _validate_player_won(data: object) -> dict[str, object]:
    return _exact_object(
        data,
        {
            "player": _string,
            "cities": _nonnegative_integer,
            "home_countries": _nonnegative_integer,
        },
    )


def _validate_military(data: object) -> dict[str, object]:
    return _exact_object(
        data,
        {
            "outcomes": lambda value: _canonical_sequence(value, _outcome),
            "cancelled_orders": lambda value: _canonical_sequence(value, _unit_key),
            "broken_convoys": lambda value: _canonical_sequence(value, _unit_key),
            "dislodgements": lambda value: _canonical_sequence(value, _unit_key),
            "rebellions": lambda value: _canonical_sequence(
                value, _rebellion_transition
            ),
            "sieges": lambda value: _canonical_sequence(value, _siege_transition),
        },
    )


_VALIDATORS: Mapping[EventType, Callable[[object], dict[str, object]]] = {
    EventType.START_GAME: _validate_start_game,
    EventType.START_GAME_POWER_ASSIGNED: _validate_power_assigned,
    EventType.START_SEASON: _validate_start_season,
    EventType.FAMINE_SPAWN: _validate_spawn,
    EventType.FAMINE_RELIEF: _validate_famine_relief,
    EventType.FAMINE_ATTRITION: _validate_disaster_death,
    EventType.FAMINE_END: _validate_provinces_only,
    EventType.PLAGUE_SPAWN: _validate_spawn,
    EventType.PLAGUE_DEATH: _validate_disaster_death,
    EventType.REBELLION_PACIFY: _validate_rebellion_pacify,
    EventType.REBELLION_PROVINCE: _validate_player_province,
    EventType.REBELLION_CITY: _validate_player_province,
    EventType.EXPENSE: _validate_expense,
    EventType.EXPENSE_NO_FUNDS: _validate_expense,
    EventType.EXPENSE_SYNTAX_ERROR: _validate_expense,
    EventType.BRIBE_EXECUTED: _validate_bribe,
    EventType.INCOME_COLLECTED: _validate_income,
    EventType.MAINTENANCE_ORDER_RESOLVED: _validate_maintenance_order,
    EventType.MAINTENANCE_SUMMARY: _validate_maintenance_summary,
    EventType.GET_CONTROL: _validate_control,
    EventType.LOSE_CONTROL: _validate_control,
    EventType.GET_HOME_COUNTRY: _validate_home_country,
    EventType.LOSE_HOME_COUNTRY: _validate_home_country,
    EventType.PLAYER_ELIMINATED: _validate_player,
    EventType.PLAYER_WON: _validate_player_won,
    EventType.MILITARY_RESOLUTION: _validate_military,
}


def _freeze(value: object) -> FrozenJSONValue:
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("Los floats JSON deben ser finitos")
        return value
    if isinstance(value, Mapping):
        return MappingProxyType(
            {str(key): _freeze(item) for key, item in value.items()}
        )
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    raise TypeError(f"Valor no serializable como JSON: {type(value).__name__}")


def _thaw(value: FrozenJSONValue) -> JSONValue:
    if isinstance(value, Mapping):
        return {key: _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    return value


@dataclass(frozen=True, slots=True, init=False)
class TurnEvent:
    """One validated domain fact with a deeply immutable JSON payload."""

    type: EventType
    data: Mapping[str, FrozenJSONValue]

    def __init__(self, type: EventType | str, data: Mapping[str, object]) -> None:
        raw_type = type
        try:
            event_type = (
                raw_type if isinstance(raw_type, EventType) else EventType(raw_type)
            )
            normalized = _VALIDATORS[event_type](data)
            frozen = _freeze(normalized)
            if not isinstance(frozen, Mapping):
                raise TypeError("El payload congelado debe seguir siendo un objeto")
        except (TypeError, ValueError, KeyError) as error:
            raw_value = (
                raw_type.value if isinstance(raw_type, EventType) else str(raw_type)
            )
            raise InvalidTurnEventError(
                f"Payload inválido para el evento {raw_value}",
                event_type=raw_value,
            ) from error
        object.__setattr__(self, "type", event_type)
        object.__setattr__(self, "data", frozen)

    @classmethod
    def expense(
        cls,
        event_type: EventType,
        actor: str,
        expense_type: str,
        target: str | None,
        amount: int | str,
    ) -> TurnEvent:
        """Construct one of the supported expense or executed-bribe events."""
        allowed = {
            EventType.EXPENSE,
            EventType.EXPENSE_NO_FUNDS,
            EventType.EXPENSE_SYNTAX_ERROR,
            EventType.BRIBE_EXECUTED,
        }
        if event_type not in allowed:
            raise InvalidTurnEventError(
                f"El tipo {event_type} no es un evento de gasto",
                event_type=str(event_type),
            )
        normalized_amount: int | str = (
            int(amount) if isinstance(amount, str) and amount.isdigit() else amount
        )
        return cls(
            type=event_type,
            data={
                "player": actor,
                "expense": expense_type,
                "target": target,
                "amount": normalized_amount,
            },
        )

    @classmethod
    def military_resolution(
        cls,
        outcomes: Sequence[object],
        cancelled_orders: Sequence[object],
        broken_convoys: Sequence[object],
        dislodgements: Sequence[object],
        rebellions: Sequence[object],
        sieges: Sequence[object],
    ) -> TurnEvent:
        """Build the canonical military event from primitive collections."""
        return cls(
            type=EventType.MILITARY_RESOLUTION,
            data={
                "outcomes": outcomes,
                "cancelled_orders": cancelled_orders,
                "broken_convoys": broken_convoys,
                "dislodgements": dislodgements,
                "rebellions": rebellions,
                "sieges": sieges,
            },
        )

    def to_json(self) -> str:
        """Serialize a fresh native JSON tree compactly and deterministically."""
        return json.dumps(
            _thaw(cast(FrozenJSONValue, self.data)),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )

    @classmethod
    def from_persisted(
        cls,
        *,
        row_id: int,
        event_type: str,
        data_json: str,
    ) -> TurnEvent:
        """Reconstruct and validate one persisted row with diagnostic context."""
        try:
            parsed = json.loads(data_json)
            if not isinstance(parsed, dict):
                raise TypeError("El JSON persistido debe ser un objeto")
            return cls(type=EventType(event_type), data=parsed)
        except (TypeError, ValueError, InvalidTurnEventError) as error:
            raise InvalidTurnEventError(
                f"Evento de turno persistido inválido en fila {row_id} "
                f"para tipo {event_type!r}",
                row_id=row_id,
                event_type=event_type,
            ) from error


__all__ = [
    "EventType",
    "FrozenJSONValue",
    "InvalidTurnEventError",
    "JSONValue",
    "TurnEvent",
]
