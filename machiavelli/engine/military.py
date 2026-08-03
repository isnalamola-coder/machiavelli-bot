# machiavelli/engine/military.py

from collections import defaultdict
from dataclasses import dataclass

from ..game.game import Command, Game, Player
from ..game.map import MovementMode
from ..game.tables import GameTables


@dataclass
class MilitaryUnit:
    """Representa una unidad militar y la orden asignada para la fase actual."""

    unit_type: str  # ej: "army", "fleet", "garrison"
    origin: str  # location_id donde inicia el turno
    player: Player | None = None
    order_type: str = "H"
    order_succeed: bool = True
    target_location: str | None = None
    supported_faction: str | None = None


class MilitaryResolver:
    """Responsable de la gestión de las órdenes militares."""

    def __init__(self, game: Game):
        self.game = game
        self.conflicts_map: dict[str, list[MilitaryUnit]] = defaultdict(list)

    def _build_conflicts_map(self) -> None:
        """Crea el mapa de conflictos con la situación inicial."""
        self.conflicts_map.clear()
        for player in self.game.players:
            for army in player.armies:
                self.conflicts_map[army].append(
                    MilitaryUnit(
                        unit_type="A",
                        origin=army,
                        player=player,
                        order_type="H",
                        order_succeed=True,
                    )
                )
            for fleet in player.fleets:
                self.conflicts_map[fleet.split()[0]].append(
                    MilitaryUnit(
                        unit_type="F",
                        origin=fleet,
                        player=player,
                        order_type="H",
                        order_succeed=True,
                    )
                )
            for garrison in player.garrisons:
                self.conflicts_map[f"G {garrison}"].append(
                    MilitaryUnit(
                        unit_type="G",
                        origin=garrison,
                        player=player,
                        order_type="H",
                        order_succeed=True,
                    )
                )
        # Y las guarniciones independientes
        for garrison in self.game.independent_garrisons:
            self.conflicts_map[f"G {garrison}"].append(
                MilitaryUnit(
                    unit_type="G",
                    origin=garrison,
                    player=None,
                    order_type="H",
                    order_succeed=True,
                )
            )

    def _valid_actor(self, player: Player, actor: str) -> tuple[str, str] | None:
        """Devuelve los datos de un actor válido para órdenes militares, o None.

        Los datos los devuelve con un tuple que contiene el tipo de unidad (A/F/G) y
        su localización (incluyendo la costa si fuera el caso para una flota).
        """
        actor_pair = actor.split(maxsplit=1)

        # Al menos debe tener el tipo de unidad y su localización
        if len(actor_pair) < 2:
            return None

        actor_type, actor_location = actor_pair
        is_valid = (actor_type in ("A", "F", "G")) and (
            actor_location in self.game.map.provinces
            or actor_location in self.game.map.seas
        )
        if is_valid:
            if actor_type == "G":
                is_valid = actor_location in player.garrisons
            elif actor_type == "A":
                is_valid = actor_location in player.armies
            elif actor_type == "F":
                is_valid = actor_location in player.fleets

        if is_valid:
            return (actor_type, actor_location)
        else:
            return None

    def _valid_command(self, command: str) -> str | None:
        """Devuelve los datos de un comando válido para órdenes militares, o None.

        El comando es el código tal y como se definen en GameTables.military_orders
        """
        if command in GameTables.military_orders:
            return command
        return None

    def _get_unit_from_conflicts_map(
        self, player: Player, actor: tuple[str, str]
    ) -> tuple[str, MilitaryUnit] | None:
        """Devuelve la localización de la unidad en el conflicts_map, y sus datos"""
        actor_type, actor_origin = actor

        # Determinamos la clave exacta usada en conflictos_map
        if actor_type == "G":
            location_key = f"G {actor_origin}"
        elif actor_type == "F":
            location_key = actor_origin.split()[0]
        else:  # "A"
            location_key = actor_origin

        # Acceso directo O(1) y filtrado por jugador
        units = self.conflicts_map.get(location_key, [])
        for unit in units:
            if unit.unit_type == actor_type and unit.player == player:
                return (location_key, unit)

        return None

    def _process_unit_advance(
        self, player: Player, actor: tuple[str, str], command: Command
    ) -> None:
        """Procesa una orden de avance de una unidad."""
        actor_type, actor_location = actor
        unit_info = self._get_unit_from_conflicts_map(player, actor)

        # Protección contra retorno None
        if unit_info is None:
            return

        location_key, unit = unit_info
        target = command.target

        # Guarniciones no pueden avanzar
        if actor_type == "G":
            return

        # Normalizamos el target por si incluye costas
        target_key = target.split()[0]

        # Validación para Flotas (Vía marítima / costera)
        if actor_type == "F":
            if target in self.game.map.adjacent_locations(
                actor_location, MovementMode.SEA
            ):
                unit.order_type = "A"
                unit.target_location = target

                # Usamos location_key (normalizada) para remover
                self.conflicts_map[location_key].remove(unit)
                # Usamos target_key (normalizada) para añadir al conflicto
                self.conflicts_map[target_key].append(unit)

        # Validación para Ejércitos (Terrestre o Vía Convoy)
        elif actor_type == "A":
            if target in self.game.map.adjacent_locations(
                actor_location, MovementMode.LAND
            ):
                unit.order_type = "A"
                unit.target_location = target

                self.conflicts_map[location_key].remove(unit)
                self.conflicts_map[target_key].append(unit)

    def _process_unit_besiege(
        self, player: Player, actor: tuple[str, str], command: Command
    ) -> None:
        """Procesa la orden de asediar una única unidad."""
        pass

    def _process_unit_hold(
        self, player: Player, actor: tuple[str, str], command: Command
    ) -> None:
        """Procesa la orden de mantener una única unidad."""
        pass

    def _process_unit_lift_besiege(
        self, player: Player, actor: tuple[str, str], command: Command
    ) -> None:
        """Procesa la orden de levantar asedio una única unidad."""
        pass

    def _process_unit_support(
        self, player: Player, actor: tuple[str, str], command: Command
    ) -> None:
        """Procesa la orden de apoyar una única unidad."""
        pass

    def _process_unit_transport(
        self, player: Player, actor: tuple[str, str], command: Command
    ) -> None:
        """Procesa la orden de transportar una única unidad."""
        pass

    def _process_unit_conversion(
        self, player: Player, actor: tuple[str, str], command: Command
    ) -> None:
        """Procesa la orden de convertir una única unidad."""
        actor_type, actor_location = actor
        unit_info = self._get_unit_from_conflicts_map(player, actor)

        # Protección contra retorno None
        if unit_info is None:
            return

        location_key, unit = unit_info
        target = command.target

        if actor_type == "G":
            if (
                target == "A"
                or target == "F"
                and self.game.map.provinces[unit.origin].has_port
            ):
                unit.order_type = "C"
                unit.target_location = target

                self.conflicts_map[location_key].remove(unit)
                self.conflicts_map[unit.origin].append(unit)
        elif actor_type == "A":
            if (
                target == "G"
                and self.game.map.provinces[unit.origin].city == "fortified"
            ):
                unit.order_type = "C"
                unit.target_location = target

                self.conflicts_map[location_key].remove(unit)
                self.conflicts_map[f"G {unit.origin}"].append(unit)
        elif actor_type == "F":
            if (
                target == "G"
                and unit.origin in self.game.map.provinces
                and self.game.map.provinces[unit.origin].city == "fortified"
                and self.game.map.provinces[unit.origin].has_port
            ):
                unit.order_type = "C"
                unit.target_location = target

                self.conflicts_map[location_key].remove(unit)
                self.conflicts_map[f"G {unit.origin}"].append(unit)

    def _process_unit_command(
        self, player: Player, actor: tuple[str, str], command: Command
    ) -> None:
        """Procesa la orden de una única unidad."""
        if command.command == "A":
            self._process_unit_advance(player, actor, command)
        elif command.command == "B":
            self._process_unit_besiege(player, actor, command)
        elif command.command == "H":
            self._process_unit_hold(player, actor, command)
        elif command.command == "L":
            self._process_unit_lift_besiege(player, actor, command)
        elif command.command == "S":
            self._process_unit_support(player, actor, command)
        elif command.command == "T":
            self._process_unit_transport(player, actor, command)
        elif command.command == "C":
            self._process_unit_conversion(player, actor, command)

    def _process_commands(self) -> None:
        """Procesa todos las órdenes y las ejecuta sobre el conflicts_map."""
        for player in self.game.players:
            for cmd in player.commands:
                actor = self._valid_actor(player, cmd.actor)
                command = self._valid_command(cmd.command)
                if actor and command:
                    self._process_unit_command(player, actor, cmd)

    def _resolve_conflicts(self):
        """Resuelve los conflictos en el mapa."""
        pass

    def _do_advance(self, unit: MilitaryUnit) -> None:
        """Consolida una orden de avance."""
        if unit.unit_type == "A":
            if unit.origin in unit.player.armies:
                unit.player.armies.remove(unit.origin)
            unit.player.armies.append(unit.target_location)
        elif unit.unit_type == "F":
            if unit.origin in unit.player.fleets:
                unit.player.fleets.remove(unit.origin)
            unit.player.fleets.append(unit.target_location)

    def _do_besiege(self, unit: MilitaryUnit) -> None:
        """Consolida una orden de asedio."""
        pass

    def _do_hold(self, unit: MilitaryUnit) -> None:
        """Consolida una orden de mantener."""
        pass

    def _do_lift_besiege(self, unit: MilitaryUnit) -> None:
        """Consolida una orden de levantar asedio."""
        pass

    def _do_support(self, unit: MilitaryUnit) -> None:
        """Consolida una orden de apoyar."""
        pass

    def _do_transport(self, unit: MilitaryUnit) -> None:
        """Consolida una orden de transporte."""
        pass

    def _do_conversion(self, unit: MilitaryUnit) -> None:
        """Consolida una orden de conversión."""
        base_origin = unit.origin.split()[0]

        if unit.unit_type == "A":
            if unit.origin in unit.player.armies:
                unit.player.armies.remove(unit.origin)
            unit.player.garrisons.append(base_origin)

        elif unit.unit_type == "F":
            if unit.origin in unit.player.fleets:
                unit.player.fleets.remove(unit.origin)
            elif base_origin in unit.player.fleets:
                unit.player.fleets.remove(base_origin)
            unit.player.garrisons.append(base_origin)

        else:  # Es una guarnición ("G")
            if unit.origin in unit.player.garrisons:
                unit.player.garrisons.remove(unit.origin)
            elif base_origin in unit.player.garrisons:
                unit.player.garrisons.remove(base_origin)

            if unit.target_location == "A":
                unit.player.armies.append(base_origin)
            else:  # Una flota ("F")
                unit.player.fleets.append(unit.origin)

    def _update_from_conflicts_map(self):
        """Una vez resueltos los conflictos, copia el nuevo estado."""
        for unit_list in self.conflicts_map.values():
            if len(unit_list) > 1:
                raise ValueError("Conflicto sin resolver")
            elif unit_list:
                # Tomaremos los datos de la nueva unidad
                unit = unit_list[0]
                if unit.order_type == "A":
                    self._do_advance(unit)
                elif unit.order_type == "B":
                    self._do_besiege(unit)
                elif unit.order_type == "H":
                    self._do_hold(unit)
                elif unit.order_type == "L":
                    self._do_lift_besiege(unit)
                elif unit.order_type == "S":
                    self._do_support(unit)
                elif unit.order_type == "T":
                    self._do_transport(unit)
                elif unit.order_type == "C":
                    self._do_conversion(unit)

    def run(self) -> None:
        """Ejecuta las órdenes militares."""
        self._build_conflicts_map()
        self._process_commands()
        self._resolve_conflicts()
        self._update_from_conflicts_map()
