# tests/machiavelli/engine/test_military.py

import unittest
from collections import defaultdict
from unittest.mock import Mock, patch

from machiavelli.engine.military import MilitaryResolver, MilitaryUnit
from machiavelli.game.map import MovementMode


class TestBuildConflictsMap(unittest.TestCase):
    def setUp(self):
        self.mock_game = Mock()
        self.resolver = MilitaryResolver(game=self.mock_game)

        # Mock de Jugador 1
        self.player_1 = Mock()
        self.player_1.armies = ["flore", "pisa"]
        self.player_1.fleets = ["naple S"]
        self.player_1.garrisons = ["flore"]

        # Mock de Jugador 2
        self.player_2 = Mock()
        self.player_2.armies = ["rome"]
        self.player_2.fleets = []
        self.player_2.garrisons = []

        self.mock_game.players = [self.player_1, self.player_2]
        self.mock_game.independent_garrisons = ["sienn", "lucca"]

    def test_build_conflicts_map(self):
        """Verifica que todas las unidades del jugador se mapean."""
        self.resolver._build_conflicts_map()

        # Armadas de Player 1
        self.assertIn("flore", self.resolver.conflicts_map)
        unit_florence = self.resolver.conflicts_map["flore"][0]
        self.assertEqual(unit_florence.unit_type, "A")
        self.assertEqual(unit_florence.player, self.player_1)

        # Flotas de Player 1 (Comprueba parseo de split())
        self.assertIn("naple", self.resolver.conflicts_map)
        unit_fleet = self.resolver.conflicts_map["naple"][0]
        self.assertEqual(unit_fleet.unit_type, "F")
        self.assertEqual(unit_fleet.player, self.player_1)

        # Guarniciones independientes
        self.assertIn("G sienn", self.resolver.conflicts_map)
        independent_unit = self.resolver.conflicts_map["G sienn"][0]

        self.assertEqual(independent_unit.unit_type, "G")
        self.assertIsNone(independent_unit.player)
        self.assertEqual(independent_unit.origin, "sienn")

    def test_build_conflicts_map_clear(self):
        """Verifica que .clear() elimina datos anteriores y no acumula duplicados."""
        self.resolver._build_conflicts_map()
        self.assertEqual(len(self.resolver.conflicts_map["flore"]), 1)

        # Segunda ejecución sin cambios
        self.resolver._build_conflicts_map()
        self.assertEqual(len(self.resolver.conflicts_map["flore"]), 1)

    def test_multiple_units_can_coexist_in_same_location_list(self):
        """Verifica que dos unidades en la misma localización se acumulen."""
        # Supongamos que player_2 también tiene un ejército en florence
        self.player_2.armies = ["flore"]

        self.resolver._build_conflicts_map()

        units_in_florence = self.resolver.conflicts_map["flore"]
        self.assertEqual(len(units_in_florence), 2)
        self.assertEqual(units_in_florence[0].player, self.player_1)
        self.assertEqual(units_in_florence[1].player, self.player_2)


class TestValidActor(unittest.TestCase):
    def setUp(self):
        self.mock_game = Mock()
        # Mapeo simulado de provincias y mares
        self.mock_game.map.provinces = ["flore", "pisa", "prove S"]
        self.mock_game.map.seas = ["ETS"]
        self.player = Mock()
        self.player.armies = ["flore"]
        self.player.fleets = ["prove S", "ETS"]

        self.resolver = MilitaryResolver(game=self.mock_game)

    def test_valid_actor_army(self):
        """Un ejército en una provincia válida devuelve ('A', 'flore')."""
        result = self.resolver._valid_actor(self.player, "A flore")
        self.assertEqual(result, ("A", "flore"))

    def test_valid_actor_fleet(self):
        """Una flota en una provincia costera válida preserva la sub-costa."""
        result = self.resolver._valid_actor(self.player, "F prove S")
        self.assertEqual(result, ("F", "prove S"))

    def test_valid_actor_sea(self):
        """Una flota en un mar válido devuelve ('F', 'ETS')."""
        result = self.resolver._valid_actor(self.player, "F ETS")
        self.assertEqual(result, ("F", "ETS"))

    def test_valid_actor_invalid_type(self):
        """Tipos de unidad desconocidos (ej: 'X') devuelven None."""
        result = self.resolver._valid_actor(self.player, "X flore")
        self.assertIsNone(result)

    def test_valid_actor_not_owner(self):
        """Tipos de unidad que no son del jugador devuelven None."""
        result = self.resolver._valid_actor(self.player, "F venic")
        self.assertIsNone(result)

    def test_valid_actor_invalid_location(self):
        """Ubicaciones no registradas en el mapa devuelven None."""
        result = self.resolver._valid_actor(self.player, "A unkno")
        self.assertIsNone(result)

    def test_valid_actor_malformed(self):
        """Cadenas sin espacio o con un solo token devuelven None."""
        self.assertIsNone(self.resolver._valid_actor(self.player, "A"))
        self.assertIsNone(self.resolver._valid_actor(self.player, "Aflore"))


class TestValidCommand(unittest.TestCase):
    def setUp(self):
        self.mock_game = Mock()
        self.resolver = MilitaryResolver(game=self.mock_game)

    @patch("machiavelli.engine.military.GameTables")
    def test_valid_commands_from_dict_keys(self, mock_game_tables):
        """Verifica que las claves del diccionario de órdenes sean reconocidas."""
        mock_game_tables.military_orders = {
            "A": {"text": "Avanzar a Provincia o Mar", "target_type": "location"},
            "H": {"text": "Mantener", "target_type": None},
        }

        self.assertEqual(self.resolver._valid_command("A"), "A")
        self.assertEqual(self.resolver._valid_command("H"), "H")
        self.assertIsNone(self.resolver._valid_command("X"))


class TestGetUnitFromConflictsMap(unittest.TestCase):
    def setUp(self):
        self.mock_game = Mock()
        self.resolver = MilitaryResolver(game=self.mock_game)
        self.resolver.conflicts_map = defaultdict(list)

        self.player_1 = Mock(name="Player1")
        self.player_2 = Mock(name="Player2")

        # Poblamos el mapa manualmente con casos de prueba
        self.unit_army = MilitaryUnit(
            unit_type="A", origin="flore", player=self.player_1
        )
        self.unit_fleet = MilitaryUnit(
            unit_type="F", origin="prove S", player=self.player_1
        )
        self.unit_garrison = MilitaryUnit(
            unit_type="G", origin="pisa", player=self.player_1
        )

        self.resolver.conflicts_map["flore"].append(self.unit_army)
        self.resolver.conflicts_map["prove"].append(self.unit_fleet)
        self.resolver.conflicts_map["G pisa"].append(self.unit_garrison)

    def test_get_unit_from_conflicts_map(self):
        """Recupera un ejército por su clave exacta de provincia."""
        result = self.resolver._get_unit_from_conflicts_map(
            self.player_1, ("A", "flore")
        )
        self.assertIsNotNone(result)
        key, unit = result
        self.assertEqual(key, "flore")
        self.assertEqual(unit, self.unit_army)

    def test_get_unit_from_conflicts_map_coast(self):
        """Recupera una flota separando la costa de la localización principal."""
        result = self.resolver._get_unit_from_conflicts_map(
            self.player_1, ("F", "prove S")
        )
        self.assertIsNotNone(result)
        key, unit = result
        self.assertEqual(key, "prove")
        self.assertEqual(unit, self.unit_fleet)

    def test_get_unit_from_conflicts_map_garrison(self):
        """Recupera una guarnición añadiendo el prefijo 'G ' automáticamente."""
        result = self.resolver._get_unit_from_conflicts_map(
            self.player_1, ("G", "pisa")
        )
        self.assertIsNotNone(result)
        key, unit = result
        self.assertEqual(key, "G pisa")
        self.assertEqual(unit, self.unit_garrison)

    def test_get_unit_from_conflicts_map_not_owner(self):
        """Devuelve None si la unidad pertenece a otro jugador."""
        result = self.resolver._get_unit_from_conflicts_map(
            self.player_2, ("A", "flore")
        )
        self.assertIsNone(result)

    def test_get_unit_from_conflicts_map_no_location(self):
        """Devuelve None si la localización no existe en el mapa."""
        result = self.resolver._get_unit_from_conflicts_map(
            self.player_1, ("A", "rome")
        )
        self.assertIsNone(result)


class TestProcessUnitAdvance(unittest.TestCase):
    def setUp(self):
        self.mock_game = Mock()
        self.resolver = MilitaryResolver(game=self.mock_game)
        self.resolver.conflicts_map = defaultdict(list)
        self.player = Mock(name="Player1")

    def test_process_unit_advance_not_found(self):
        """Si _get_unit_from_conflicts_map devuelve None,."""
        mock_command = Mock(target="pisa")

        with patch.object(
            self.resolver, "_get_unit_from_conflicts_map", return_value=None
        ):
            self.resolver._process_unit_advance(
                self.player, ("A", "flore"), mock_command
            )

        self.assertNotIn("pisa", self.resolver.conflicts_map)

    def test_process_unit_advance_garrison(self):
        """Las guarniciones ('G') ignoran la orden de avance."""
        garrison = MilitaryUnit(unit_type="G", origin="pisa", player=self.player)
        self.resolver.conflicts_map["G pisa"].append(garrison)
        mock_command = Mock(target="flore")

        with patch.object(
            self.resolver,
            "_get_unit_from_conflicts_map",
            return_value=("G pisa", garrison),
        ):
            self.resolver._process_unit_advance(
                self.player, ("G", "pisa"), mock_command
            )

        self.assertEqual(garrison.order_type, "H")
        self.assertIn(garrison, self.resolver.conflicts_map["G pisa"])
        self.assertNotIn("flore", self.resolver.conflicts_map)

    def test_process_unit_advance(self):
        """Un ejército que avanza a una provincia adyacente actualiza su estado."""
        army = MilitaryUnit(unit_type="A", origin="flore", player=self.player)
        self.resolver.conflicts_map["flore"].append(army)

        self.mock_game.map.adjacent_locations.return_value = ["pisa", "sienn"]
        mock_command = Mock(target="pisa")

        with patch.object(
            self.resolver, "_get_unit_from_conflicts_map", return_value=("flore", army)
        ):
            self.resolver._process_unit_advance(
                self.player, ("A", "flore"), mock_command
            )

        # Verificaciones
        self.assertEqual(army.order_type, "A")
        self.assertEqual(army.target_location, "pisa")
        self.assertNotIn(army, self.resolver.conflicts_map["flore"])
        self.assertIn(army, self.resolver.conflicts_map["pisa"])
        self.mock_game.map.adjacent_locations.assert_called_once_with(
            "flore", MovementMode.LAND
        )

    def test_process_unit_advance_not_adjacent(self):
        """Si el destino no es adyacente por tierra, el ejército no se mueve."""
        army = MilitaryUnit(unit_type="A", origin="flore", player=self.player)
        self.resolver.conflicts_map["flore"].append(army)

        self.mock_game.map.adjacent_locations.return_value = ["sienn"]
        mock_command = Mock(target="rome")

        with patch.object(
            self.resolver, "_get_unit_from_conflicts_map", return_value=("flore", army)
        ):
            self.resolver._process_unit_advance(
                self.player, ("A", "flore"), mock_command
            )

        self.assertEqual(army.order_type, "H")
        self.assertIn(army, self.resolver.conflicts_map["flore"])
        self.assertNotIn("rome", self.resolver.conflicts_map)

    def test_process_unit_advance_coastal_fleet(self):
        """Una flota actualiza la localización con sub-costa pero agrupa en el mapa."""
        fleet = MilitaryUnit(unit_type="F", origin="ETS", player=self.player)
        self.resolver.conflicts_map["ETS"].append(fleet)

        self.mock_game.map.adjacent_locations.return_value = ["prove S", "naples"]
        mock_command = Mock(target="prove S")

        with patch.object(
            self.resolver, "_get_unit_from_conflicts_map", return_value=("ETS", fleet)
        ):
            self.resolver._process_unit_advance(self.player, ("F", "ETS"), mock_command)

        self.assertEqual(fleet.order_type, "A")
        self.assertEqual(fleet.target_location, "prove S")
        self.assertNotIn(fleet, self.resolver.conflicts_map["ETS"])
        # La clave en el mapa debe ser 'spain', no 'spain south'
        self.assertIn(fleet, self.resolver.conflicts_map["prove"])
        self.mock_game.map.adjacent_locations.assert_called_once_with(
            "ETS", MovementMode.SEA
        )

    def test_process_unit_advance_not_adjacent_sea(self):
        """Si el destino marítimo no es adyacente, la flota no se desplaza."""
        fleet = MilitaryUnit(unit_type="F", origin="ETS", player=self.player)
        self.resolver.conflicts_map["ETS"].append(fleet)

        self.mock_game.map.adjacent_locations.return_value = ["naple"]
        mock_command = Mock(target="venic")

        with patch.object(
            self.resolver,
            "_get_unit_from_conflicts_map",
            return_value=("ETS", fleet),
        ):
            self.resolver._process_unit_advance(self.player, ("F", "ETS"), mock_command)

        self.assertEqual(fleet.order_type, "H")
        self.assertIn(fleet, self.resolver.conflicts_map["ETS"])
        self.assertNotIn("venice", self.resolver.conflicts_map)


class TestProcessUnitConversion(unittest.TestCase):
    def setUp(self):
        self.mock_game = Mock()
        self.resolver = MilitaryResolver(game=self.mock_game)
        self.resolver.conflicts_map = defaultdict(list)
        self.player = Mock(name="Player1")

        # Configuración del mapa según las reglas de Machiavelli
        self.mock_game.map.provinces = {
            "flore": Mock(city="fortified", has_port=False),
            "pisa": Mock(city="fortified", has_port=True),
            "prove S": Mock(city=None, has_port=False),  # Doble costa sin ciudad
        }

    def test_process_unit_conversion_to_army(self):
        """Una guarnición en ciudad interior puede convertirse en Ejército."""
        garrison = MilitaryUnit(unit_type="G", origin="flore", player=self.player)
        self.resolver.conflicts_map["G flore"].append(garrison)
        mock_command = Mock(target="A")

        with patch.object(
            self.resolver,
            "_get_unit_from_conflicts_map",
            return_value=("G flore", garrison),
        ):
            self.resolver._process_unit_conversion(
                self.player, ("G", "flore"), mock_command
            )

        self.assertEqual(garrison.order_type, "C")
        self.assertEqual(garrison.target_location, "A")
        self.assertNotIn(garrison, self.resolver.conflicts_map["G flore"])
        self.assertIn(garrison, self.resolver.conflicts_map["flore"])

    def test_process_unit_conversion_to_fleet_fails(self):
        """Una guarnición no puede convertirse en Flota si la ciudad no tiene puerto."""
        garrison = MilitaryUnit(unit_type="G", origin="flore", player=self.player)
        self.resolver.conflicts_map["G flore"].append(garrison)
        mock_command = Mock(target="F")

        with patch.object(
            self.resolver,
            "_get_unit_from_conflicts_map",
            return_value=("G flore", garrison),
        ):
            self.resolver._process_unit_conversion(
                self.player, ("G", "flore"), mock_command
            )

        self.assertEqual(garrison.order_type, "H")
        self.assertIn(garrison, self.resolver.conflicts_map["G flore"])

    def test_process_unit_conversion_in_sea(self):
        """Una flota en mar abierto ignora la orden sin lanzar KeyError."""
        fleet = MilitaryUnit(unit_type="F", origin="ETS", player=self.player)
        self.resolver.conflicts_map["ETS"].append(fleet)
        mock_command = Mock(target="G")

        with patch.object(
            self.resolver,
            "_get_unit_from_conflicts_map",
            return_value=("ETS", fleet),
        ):
            self.resolver._process_unit_conversion(
                self.player, ("F", "ETS"), mock_command
            )

        self.assertEqual(fleet.order_type, "H")


class TestUpdateFromConflictsMap(unittest.TestCase):
    def setUp(self):
        self.mock_game = Mock()
        self.resolver = MilitaryResolver(game=self.mock_game)
        self.resolver.conflicts_map = defaultdict(list)
        self.player = Mock(name="Player1")

    def test_update_from_conflicts_map_conflicts(self):
        """Lanza ValueError si han quedado 2 o más unidades en la misma casilla."""
        unit1 = MilitaryUnit(unit_type="A", origin="flore", player=self.player)
        unit2 = MilitaryUnit(unit_type="A", origin="sienn", player=self.player)

        # Simulamos un conflicto no resuelto en 'florence'
        self.resolver.conflicts_map["flore"] = [unit1, unit2]

        with self.assertRaises(ValueError) as ctx:
            self.resolver._update_from_conflicts_map()

        self.assertEqual(str(ctx.exception), "Conflicto sin resolver")

    def test_update_from_conflicts_map_advance(self):
        """Si la unidad tiene order_type 'A', invoca _do_advance."""
        unit = MilitaryUnit(unit_type="A", origin="florence", player=self.player)
        unit.order_type = "A"
        self.resolver.conflicts_map["pisa"] = [unit]

        with patch.object(self.resolver, "_do_advance") as mock_do_advance:
            self.resolver._update_from_conflicts_map()
            mock_do_advance.assert_called_once_with(unit)

    def test_update_from_conflicts_map_conversion(self):
        """Si la unidad tiene order_type 'C', invoca _do_conversion."""
        unit = MilitaryUnit(unit_type="G", origin="pisa", player=self.player)
        unit.order_type = "C"
        self.resolver.conflicts_map["pisa"] = [unit]

        with patch.object(self.resolver, "_do_conversion") as mock_do_conversion:
            self.resolver._update_from_conflicts_map()
            mock_do_conversion.assert_called_once_with(unit)

    def test_update_from_conflicts_map_empty(self):
        """Las casillas vacías en conflicts_map no generan acciones ni errores."""
        self.resolver.conflicts_map["rome"] = []

        with patch.object(self.resolver, "_do_hold") as mock_do_hold:
            self.resolver._update_from_conflicts_map()
            mock_do_hold.assert_not_called()


class TestDoAdvance(unittest.TestCase):
    def setUp(self):
        self.mock_game = Mock()
        self.resolver = MilitaryResolver(game=self.mock_game)
        self.player = Mock(name="Player1")

    def test_do_advance_army(self):
        """Un avance de ejército elimina el origen y añade el destino."""
        self.player.armies = ["flore", "sienn"]
        army = MilitaryUnit(unit_type="A", origin="flore", player=self.player)
        army.target_location = "pisa"

        self.resolver._do_advance(army)

        self.assertNotIn("flore", self.player.armies)
        self.assertIn("pisa", self.player.armies)
        self.assertEqual(len(self.player.armies), 2)

    def test_do_advance_fleet(self):
        """Un avance de flota elimina el origen y añade el destino."""
        self.player.fleets = ["ETS"]
        fleet = MilitaryUnit(unit_type="F", origin="ETS", player=self.player)
        fleet.target_location = "naple"

        self.resolver._do_advance(fleet)

        self.assertNotIn("ETS", self.player.fleets)
        self.assertIn("naple", self.player.fleets)
        self.assertEqual(len(self.player.fleets), 1)

    def test_do_advance_missing_origin(self):
        """Si el origen no estaba registrado en la lista del jugador."""
        self.player.armies = ["sienn"]
        army = MilitaryUnit(unit_type="A", origin="rome", player=self.player)
        army.target_location = "venic"

        # No debe lanzar ValueError
        self.resolver._do_advance(army)

        self.assertIn("venic", self.player.armies)
        self.assertIn("sienn", self.player.armies)


class TestDoConversion(unittest.TestCase):
    def setUp(self):
        self.mock_game = Mock()
        self.resolver = MilitaryResolver(game=self.mock_game)
        self.player = Mock(name="Player1")

    def test_do_conversion_from_army(self):
        """Un ejército se elimina de armies y añade su provincia a garrisons."""
        self.player.armies = ["flore"]
        self.player.garrisons = []
        army = MilitaryUnit(unit_type="A", origin="flore", player=self.player)

        self.resolver._do_conversion(army)

        self.assertNotIn("flore", self.player.armies)
        self.assertIn("flore", self.player.garrisons)

    def test_do_conversion_from_fleet(self):
        """Una flota en sub-costa se elimina de fleets y se añade a garrisons."""
        self.player.fleets = ["prove S"]
        self.player.garrisons = []
        fleet = MilitaryUnit(unit_type="F", origin="prove S", player=self.player)

        self.resolver._do_conversion(fleet)

        self.assertNotIn("prove S", self.player.fleets)
        self.assertIn("prove", self.player.garrisons)

    def test_do_conversion_to_army(self):
        """Una guarnición se elimina de garrisons y añade la provincia a armies."""
        self.player.garrisons = ["pisa"]
        self.player.armies = []
        garrison = MilitaryUnit(unit_type="G", origin="pisa", player=self.player)
        garrison.target_location = "A"

        self.resolver._do_conversion(garrison)

        self.assertNotIn("pisa", self.player.garrisons)
        self.assertIn("pisa", self.player.armies)

    def test_do_conversion_to_fleet(self):
        """Una guarnición se elimina de garrisons y añade la provincia fleets."""
        self.player.garrisons = ["pisa"]
        self.player.fleets = []
        garrison = MilitaryUnit(unit_type="G", origin="pisa", player=self.player)
        garrison.target_location = "F"

        self.resolver._do_conversion(garrison)

        self.assertNotIn("pisa", self.player.garrisons)
        self.assertIn("pisa", self.player.fleets)

    def test_do_conversion_missing(self):
        """Si la unidad no estaba registrada, no lanza ValueError."""
        self.player.armies = []
        self.player.garrisons = []
        army = MilitaryUnit(unit_type="A", origin="rome", player=self.player)

        # No debe lanzar ValueError
        self.resolver._do_conversion(army)

        self.assertIn("rome", self.player.garrisons)
