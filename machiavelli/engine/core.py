# machiavelli/engine/core.py


from random import Random

from ..game.game import Game
from .assassination import AssassinationResolver
from .bribes import BribeResolver
from .control import ControlManager
from .disasters import DisastersManager
from .exceptions import (
    DuplicatePlayerError,
    GameAlreadyStartedError,
    InvalidPlayerCountError,
    ScenarioNotSelectedError,
    TurnExecutionFailed,
)
from .expenditure import ExpenditureProcessor
from .military import DislodgementResolver, MilitaryResolver
from .rebellions import RebellionManager
from .setup import SetupManager


class GameEngine:
    """Coordina las fases del turno y respeta sus barreras de error."""

    def __init__(
        self,
        game: Game,
        rng: Random | None = None,
        dislodgement_resolver: DislodgementResolver | None = None,
    ):
        """Configura el motor y el gestor opcional de retiradas militares."""
        self.game = game
        self.rng = rng if rng is not None else Random()
        self.dislodgement_resolver = dislodgement_resolver

    def run_startup(self) -> None:
        """Ejecutamos el flujo completo del inicio de la partida."""
        try:
            SetupManager(self.game, self.rng).run()
        except (
            DuplicatePlayerError,
            InvalidPlayerCountError,
            ScenarioNotSelectedError,
            GameAlreadyStartedError,
        ) as e:
            raise TurnExecutionFailed(
                f"Fallo en la inicialización de la partida: {e}"
            ) from e

    def run_maintenance(self) -> None:
        pass

    def run_campaign(self) -> None:
        """Ejecutamos el flujo completo de turno de campaña."""
        # Los turnos de campaña empiezan en season-1 y terminan en season, teniendo en
        # cuenta que:
        # - season 0: es la fase de mantenimiento de primavera
        # - season 1: es la campaña de primavera
        # - season 2: es la campaña de verano
        # - season 3: es la campaña de otoño
        #
        # Así, el turno 1 season es 1 (turn_number % 4), y comienza en mantenimiento de
        # primavera (season 0) y termina en la campaña de primavera (season 1)
        season = self.game.turn_number % 4

        # Las fases de una campaña son las siguientes:
        # 1. Expenditure: se comprueban los gastos de cada jugador, se mantienen los que
        #   puede pagar, se descartan los que no y se deduce el importe de su tesorería
        # 2. Se ejecutan todos los gastos excepto los asesinatos:
        #   2.1 Paliar hambruna
        #   2.2 Crear y pacificar rebeliones
        #   2.3 Sobornos y contrasobornos
        # 3. Se ejecutan los asesinatos
        # 4. Se ejecutan las órdenes militares y se resuelven los conflictos
        # 5. Se eliminan las unidades en provincias con hambre (final campaña de
        #   primavera, season==2)
        # 6. Se recalcula el control de provincias y países natales, y se comprueban
        #   las condiciones de victoria.
        # 7. Cambio de estación (solo evento)
        # 8. Se elimina el hambre (solo inicio de verano, season==2)
        # 9. Se resuelve la plaga (solo inicio de verano, season==2)
        disaster_manager = DisastersManager(self.game)  # Lo usaremos varias veces
        self.game.turn_events = []  # Vaciamos los eventos al comenzar

        ExpenditureProcessor(self.game).run()
        disaster_manager.process_famine_relief_expenses()
        RebellionManager(self.game).rebellion_expenses()
        BribeResolver(self.game).run()
        AssassinationResolver(self.game).run()
        # Un fallo militar interrumpe la campaña antes de hambre, control y plaga.
        MilitaryResolver(self.game).run(
            dislodgement_resolver=self.dislodgement_resolver
        )
        if season == 2:
            disaster_manager.resolve_famine_attrition()
        ControlManager(self.game).run()
        if season == 2:
            disaster_manager.clear_famine()
            disaster_manager.spawn_plague()

    def run(self) -> None:
        """Ejecuta el flujo completo del turno actual.

        Existen tres tipos de turno, cada uno con una secuencia distinta.
        1. El de start up, que solo se ejecuta en el turn_number == 0, que sortea
            facciones entre los jugadores y crea los datos del juego.
        2. Los turnos de mantenimiento, que se ejecutan en el primer turno de primavera
            (turn_number % 4 == 1)
        3. Los turnos de campaña, que se ejecutan en primavera/verano/otoño
        """
        if self.game.turn_number == 0:
            self.run_startup()
        elif (self.game.turn_number % 4) == 1:
            self.run_maintenance()
        else:
            self.run_campaign()
