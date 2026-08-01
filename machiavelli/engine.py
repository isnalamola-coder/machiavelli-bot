# machiavelli/engine.py
from collections import defaultdict
from random import Random

from .events import EventType, TurnEvent
from .game import Command, Game, Player
from .tables import GameTables


class GameEngine:
    """Administra toda la lógica del juego"""

    # Handlers de las funciones de gastor
    EXPENSE_HANDLERS = {
        "A": "expense_famine_relief",
        "B": "expense_pacify_rebellion",
        "C": "expense_rebellion_non_home_country",
        "D": "expense_rebellion_home_country",
        "E": "expense_assassination",
        "F": "expense_counterbribe",
        "G": "expense_bribe",
        "H": "expense_bribe",
        "I": "expense_bribe",
        "J": "expense_bribe",
        "K": "expense_bribe",
    }

    def __init__(self, game: Game, rng: Random | None = None):
        self.game = game
        self.rng = rng if rng is not None else Random()
        self.bribes = defaultdict(list)
        self.counterbribes: dict[str, int] = {}

    def phase_campaign(self) -> None:
        """Ejecuta las acciones de una campaña"""
        self.subphase_expenses()
        self.subphase_assassination()
        self.subphase_military_orders()
        self.subphase_control_adjustment()
        self.subphase_plague()

    def expense_famine_relief(self, player: Player, command: Command) -> None:
        """Paliar hambruna."""
        if command.target in self.game.famine:
            self.game.famine.remove(command.target)

    def expense_pacify_rebellion(self, player: Player, command: Command) -> None:
        """Pacificar rebelión."""
        # La rebelión puede estar en la ciudad o la provincia
        for p in self.game.players:
            if command.target in p.rebelled_provinces:
                p.rebelled_provinces.remove(command.target)
            if command.target in p.rebelled_cities:
                p.rebelled_cities.remove(command.target)

    def _do_rebellion(self, owner: Player, target: str) -> None:
        """Realiza una rebelión."""

        # Comprobamos que no haya rebeliones ya, pues no puede haber más de una
        if target in owner.rebelled_provinces or target in owner.rebelled_cities:
            return

        # Determinamos los tipos de ciudad válidos según la regla fortress_active
        valid_cities = (
            ("fortified", "fortress")
            if self.game.scenario.rules.fortress_active
            else ("fortified",)
        )

        if (
            self.game.map.provinces[target].city in valid_cities
            and target not in owner.garrisons
        ):
            # Si hay ciudad fortificada (o fuerte) sin guarnición, rebelión en la ciudad
            owner.rebelled_cities.append(target)
        else:
            # Si no, la rebelión se sitúa en la provincia
            owner.rebelled_provinces.append(target)

    def expense_rebellion_non_home_country(
        self, player: Player, command: Command
    ) -> None:
        """Comenzar rebelión en una provincia no natal."""
        # Primer comprobamos si la provincia la controla alguien
        # (si no hay control, no hay rebeliones)
        target = command.target

        player_owner = next(
            (p for p in self.game.players if target in p.controlled_locations),
            None,
        )

        if not player_owner:
            return

        # Comprobamos que no sea una provincia natal del jugador. Si es natal de otro
        # jugador no importa
        hc = self.game.scenario.province_home_country(target)
        if hc in player_owner.home_countries:
            return

        # Realizamos la rebelión
        self._do_rebellion(owner=player_owner, target=target)

    def expense_rebellion_home_country(self, player: Player, command: Command) -> None:
        """Comenzar una rebelión en una provincia no natal."""
        # Primer comprobamos si la provincia la controla alguien
        # (si no hay control, no hay rebeliones)
        target = command.target

        player_owner = next(
            (p for p in self.game.players if target in p.controlled_locations),
            None,
        )

        if not player_owner:
            return

        # Comprobamos que sea una provincia natal del jugador
        hc = self.game.scenario.province_home_country(target)
        if hc not in player_owner.home_countries:
            return

        # Realizamos la rebelión
        self._do_rebellion(owner=player_owner, target=target)

    def expense_assassination(self, player: Player, command: Command) -> None:
        """Ordenar asesinato."""
        pass

    def subphase_expenses(self) -> None:
        """Ejecuta la subfase de gastos (sobornos, contrasobornos, paliar hambruna).

        El gasto de ordenar asesinatos se ejecuta en una subfase aparte, posterior a
        ésta.
        """

        for player in self.game.players:
            expenses = [
                c
                for c in player.commands
                if c.actor[:2] == "E "
                if c.actor.split()[1] != "E"  # Asesinato va en una fase posterior
            ]
            for e in expenses:
                _, exp_type = e.actor.split()

                if player.ducats >= int(e.command):
                    self.game.add_event(
                        TurnEvent(
                            type=EventType.EXPENSE,
                            data={
                                "player": player.player_id,
                                "expense": exp_type,
                                "target": e.target,
                                "amount": e.command,
                            },
                        )
                    )

                    # El dinero se gasta independientemente de que la acción tenga éxito
                    player.ducats -= int(e.command)

                    # Si el dinero gastado no llega al necesario para la acción,
                    # no se realiza (aunque se haya gastado)

                    # En el caso de los sobornos (exp_type G-K), el coste se dobla para
                    # las guarniciones en ciudades mayores
                    cost = GameTables.expenses[exp_type]["cost"]
                    if exp_type >= "G":
                        target_type, target_code = e.target.split(maxsplit=1)
                        # ¿Guarnición en ciudad mayor?
                        if (
                            target_type == "G"
                            and self.game.map.provinces[target_code].major_city > 1
                        ):
                            cost *= 2

                    if int(e.command) < cost:
                        continue

                    # Recupero handler del gasto realizado
                    handler_name = self.EXPENSE_HANDLERS.get(exp_type)

                    if handler_name:
                        # Llamo al handler con el comando
                        handler = getattr(self, handler_name)
                        handler(player, e)

                else:
                    self.game.add_event(
                        TurnEvent(
                            type=EventType.EXPENSE_NO_FUNDS,
                            data={
                                "player": player.player_id,
                                "expense": exp_type,
                                "target": e.target,
                                "amount": e.command,
                                "ducats": player.ducats,
                            },
                        )
                    )
                    player.ducats = 0

        # Ya hemos procesado todos los gastos (salvo asesinato), ejecutamos los sobornos
        self.resolve_bribes()

    def subphase_assassination(self) -> None:
        """Ejecuta la subfase de asesinato."""
        pass

    def subphase_military_orders(self) -> None:
        """Ejecuta la subfase de órdenes militares"""
        pass

    def control_changes(self, player: Player) -> None:
        """Actualiza los cambios de control de las provincias de un jugador."""

        own_provinces, others_provinces = set(), set()
        own_provinces.update(p for p in player.armies)
        own_provinces.update(
            p.split()[0] for p in player.fleets if p in self.game.map.provinces
        )
        own_provinces.update(p for p in player.garrisons)

        others_provinces.update(
            p for other in self.game.players for p in other.armies if other != player
        )
        others_provinces.update(
            p.split()[0]
            for other in self.game.players
            for p in other.fleets
            if other != player
            if p in self.game.map.provinces
        )
        others_provinces.update(
            p for other in self.game.players for p in other.garrisons if other != player
        )
        others_provinces.update(p for p in self.game.independent_garrisons)

        new_controlled_provinces = [
            p
            for p in own_provinces
            if p not in others_provinces
            if p not in player.controlled_locations
        ]
        lost_controlled_provinces = [
            p for p in player.controlled_locations if p in others_provinces
        ]

        if new_controlled_provinces:
            self.game.add_event(
                TurnEvent(
                    type=EventType.GET_CONTROL,
                    data={
                        "player": player.player_id,
                        "provinces": new_controlled_provinces,
                    },
                )
            )
            player.controlled_locations.extend(new_controlled_provinces)

        if lost_controlled_provinces:
            self.game.add_event(
                TurnEvent(
                    type=EventType.LOSE_CONTROL,
                    data={
                        "player": player.player_id,
                        "provinces": lost_controlled_provinces,
                    },
                )
            )
            player.controlled_locations = [
                p
                for p in player.controlled_locations
                if p not in lost_controlled_provinces
            ]

    def hc_control_changes(self, player: Player) -> None:
        """Actualiza el control sobre países natales de un jugador."""

        # Se pierde el control de un país natal si se pierde el control de todas las
        # ciudades de éste. Una guarnición no basta para controlar una ciudad
        for home_country in player.home_countries[:]:
            target_hc = self.game.scenario.home_countries.get(home_country)
            if target_hc:
                controls_any_city = any(
                    p in player.controlled_locations
                    and self.game.map.provinces[p].city in ("city", "fortified")
                    for p in target_hc.provinces
                )
            else:
                controls_any_city = False

            if not controls_any_city:
                self.game.add_event(
                    TurnEvent(
                        type=EventType.LOSE_HOME_COUNTRY,
                        data={"player": player.player_id, "home_country": home_country},
                    )
                )
                player.home_countries.remove(home_country)

        # Se gana el control de un país natal si se controlan
        # todas las provincias y ciudades de éste
        for home_country in self.game.scenario.home_countries:
            if home_country not in player.home_countries:
                missing_province = any(
                    p not in player.controlled_locations
                    for p in self.game.scenario.home_countries[home_country].provinces
                )
                if not missing_province:
                    self.game.add_event(
                        TurnEvent(
                            type=EventType.GET_HOME_COUNTRY,
                            data={
                                "player": player.player_id,
                                "home_country": home_country,
                            },
                        )
                    )
                    player.home_countries.append(home_country)

    def check_player_status(self, player: Player) -> None:
        """Comprueba si el jugador es eliminado o cumple las condiciones de victoria."""
        if not player.home_countries:
            self.game.add_event(
                TurnEvent(
                    type=EventType.PLAYER_ELIMINATED, data={"player": player.player_id}
                )
            )
        else:
            cities = sum(
                self.game.map.provinces[p].city in ("city", "fortified")
                for p in player.controlled_locations
            )
            hc = len(player.home_countries)
            victory_conditions = self.game.scenario.victory_conditions
            if (
                cities >= victory_conditions.cities
                and hc >= victory_conditions.home_countries
            ):
                self.game.add_event(
                    TurnEvent(
                        type=EventType.PLAYER_WON,
                        data={
                            "player": player.player_id,
                            "cities": cities,
                            "home_countries": hc,
                        },
                    )
                )

    def subphase_control_adjustment(self) -> None:
        """Ajusta el control y comprueba condiciones de victoria."""

        # Para cada jugador, comprobamos su control sobre provincias y países natales
        for player in self.game.players:
            self.control_changes(player)
            self.hc_control_changes(player)
            self.check_player_status(player)

        # Y cambiamos de estación
        year = self.game.scenario.year + self.game.turn_number // 4
        season = self.game.turn_number % 4

        self.game.add_event(
            TurnEvent(
                type=EventType.SEASON_START, data={"year": year, "season": season}
            )
        )

    def plague_provinces(self) -> list[str]:
        """Calcula las provincias en las que se producirán plagas."""

        plague_severity = self.rng.randint(0, 5)
        # Calculo si he de lanzar en filas, columnas o ambas
        dice, _ = GameTables.disasters[plague_severity]

        plague_provinces = set()
        if dice in ("row", "both"):
            row_roll = self.rng.randint(0, 5) + self.rng.randint(0, 5)
            row = GameTables.plague[row_roll]
            plague_provinces.update(
                province_id
                for province_id in row
                if province_id in self.game.map.provinces
            )
        if dice in ("column", "both"):
            column_roll = self.rng.randint(0, 5) + self.rng.randint(0, 5)
            column = [r[column_roll] for r in GameTables.plague]
            plague_provinces.update(
                province_id
                for province_id in column
                if province_id in self.game.map.provinces
            )

        provinces = list(plague_provinces)

        # Añado el evento
        self.game.add_event(
            TurnEvent(
                type=EventType.PLAGUE_PLACES,
                data={"severity": plague_severity, "provinces": provinces},
            )
        )
        return provinces

    def plague_death(self, plague_provinces: list[str]):
        """Elimina las unidades en provincias con plaga."""

        # Para cada jugador busco qué unidades hay en una de las provincias con plaga
        for player in self.game.players:
            player_deaths = []
            for army in [a for a in player.armies if a in plague_provinces]:
                player.armies.remove(army)
                player_deaths.append(f"A {army}")
            for fleet in [f for f in player.fleets if f.split()[0] in plague_provinces]:
                player.fleets.remove(fleet)
                player_deaths.append(f"F {fleet}")
            for garrison in [g for g in player.garrisons if g in plague_provinces]:
                player.garrisons.remove(garrison)
                player_deaths.append(f"G {garrison}")

            if player_deaths:
                self.game.add_event(
                    TurnEvent(
                        type=EventType.PLAGUE_DEATH,
                        data={"player": player.player_id, "units": player_deaths},
                    )
                )

        # También las guarniciones independientes
        independent_deaths = []
        for garrison in [
            g for g in self.game.independent_garrisons if g in plague_provinces
        ]:
            self.game.independent_garrisons.remove(garrison)
            independent_deaths.append(f"G {garrison}")
        if independent_deaths:
            self.game.add_event(
                TurnEvent(
                    type=EventType.PLAGUE_DEATH,
                    data={"player": None, "units": independent_deaths},
                )
            )

    def subphase_plague(self) -> None:
        """Ejecuta la subfase eliminación del hambre y la aparición de plagas"""
        season = self.game.turn_number % 4

        # Esta fase solo se ejecuta en verano (season=2)
        if season != 2:
            return

        # Elimina el hambre
        if self.game.famine:
            self.game.add_event(
                TurnEvent(
                    type=EventType.FAMINE_END, data={"provinces": self.game.famine}
                )
            )
            self.game.famine = []

        # Calcula dónde aparecen las plagas
        plague_provinces = self.plague_provinces()

        # Y elimino las unidades afectadas
        self.plague_death(plague_provinces=plague_provinces)
