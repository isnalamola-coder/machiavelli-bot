# machiavelli/events.py

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Self


class EventType(StrEnum):
    SEASON_START = "season_start"

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


@dataclass(frozen=True, slots=True)
class TurnEvent:
    type: EventType
    data: dict[str, Any]

    @classmethod
    def expense(
        cls,
        event_type: EventType,
        actor: str,
        expense_type: str,
        target: str,
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
