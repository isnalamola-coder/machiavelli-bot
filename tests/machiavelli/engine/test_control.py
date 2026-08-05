# test/machiavelli/engine/test_control.py

import unittest
from unittest.mock import Mock, call, patch

from machiavelli.engine.control import ControlManager
from machiavelli.events import EventType, TurnEvent
from machiavelli.game.game import Game


class TestProvincesWithOwnUnits(unittest.TestCase):
    def setUp(self):
        self.mock_game = Mock()
        self.manager = ControlManager(game=self.mock_game)

        # Mapa con provincias base y nodos de costa explícitos
        self.mock_game.map.provinces = {
            "pisa": Mock(),
            "pisa N": Mock(),
            "pisa S": Mock(),
            "flore": Mock(),
            "rome": Mock(),
        }

        # Mock del jugador
        self.player = Mock()
        self.player.armies = []
        self.player.fleets = []
        self.player.garrisons = []

    def test_provinces_with_own_units(self):
        """Recoge correctamente ejércitos y guarniciones."""
        self.player.armies = ["flore"]
        self.player.garrisons = ["rome"]

        result = self.manager._provinces_with_own_units(self.player)
        self.assertEqual(result, {"flore", "rome"})

    def test_provinces_with_own_units_coastal_fleets(self):
        """Si la flota está en 'pisa N', verifica su existencia y devuelve 'pisa'."""
        self.player.fleets = ["pisa N"]

        result = self.manager._provinces_with_own_units(self.player)
        self.assertEqual(result, {"pisa"})

    def test_provinces_with_own_units_not_in_map(self):
        """Ignora flotas cuya ubicación no exista en map.provinces."""
        self.player.fleets = ["unknown_sea N"]

        result = self.manager._provinces_with_own_units(self.player)
        self.assertEqual(result, set())

    def test_provinces_with_own_units_no_duplicates(self):
        """Deduplica si hay guarnición en 'pisa' y flota en 'pisa S'."""
        self.player.fleets = ["pisa S"]
        self.player.garrisons = ["pisa"]

        result = self.manager._provinces_with_own_units(self.player)
        self.assertEqual(result, {"pisa"})


class TestProvincesWithOthersUnits(unittest.TestCase):
    def setUp(self):
        self.mock_game = Mock()
        self.manager = ControlManager(game=self.mock_game)

        # Mapa con provincias base y nodos de costa
        self.mock_game.map.provinces = {
            "pisa": Mock(),
            "pisa N": Mock(),
            "flore": Mock(),
            "rome": Mock(),
            "naple": Mock(),
            "venic": Mock(),
        }

        # Jugador actual (Florencia)
        self.current_player = Mock()
        self.current_player.player_id = "FLORENCE"
        self.current_player.armies = ["flore"]
        self.current_player.fleets = []
        self.current_player.garrisons = []

        # Otro jugador (Milán)
        self.other_player = Mock()
        self.other_player.player_id = "MILAN"
        self.other_player.armies = ["pisa"]
        self.other_player.fleets = ["pisa N"]
        self.other_player.garrisons = ["rome"]

        self.mock_game.players = [self.current_player, self.other_player]
        self.mock_game.independent_garrisons = []

    def test_provinces_with_others_units_own_unit(self):
        """No incluye la provincia 'flore' porque la unidad pertenece al jugador."""
        result = self.manager._provinces_with_others_units(self.current_player)

        self.assertNotIn("flore", result)

    def test_provinces_with_others_units(self):
        """Recoge ejércitos, flotas y guarniciones de otros jugadores."""
        result = self.manager._provinces_with_others_units(self.current_player)

        # 'pisa' viene del ejército y la flota 'pisa N'; 'rome' viene de la guarnición
        self.assertEqual(result, {"pisa", "rome"})

    def test_provinces_with_others_units_independent_garrisons(self):
        """Incluye las provincias presentes en independent_garrisons."""
        self.mock_game.independent_garrisons = ["naple", "venic"]

        result = self.manager._provinces_with_others_units(self.current_player)

        self.assertIn("naple", result)
        self.assertIn("venic", result)


class TestControlChanges(unittest.TestCase):
    def setUp(self):
        self.mock_game = Mock()
        self.manager = ControlManager(game=self.mock_game)

        # Mock del jugador
        self.player = Mock()
        self.player.player_id = "FLORENCE"
        self.player.controlled_locations = ["flore"]

    def test_control_changes_uncontested_new_province(self):
        """Gana el control de una provincia si tiene unidades y no hay otros."""
        with (
            patch.object(
                self.manager,
                "_provinces_with_own_units",
                return_value={"pisa", "flore"},
            ),
            patch.object(
                self.manager, "_provinces_with_others_units", return_value=set()
            ),
        ):
            self.manager.control_changes(self.player)

            # Debe haber añadido 'pisa' a las localizaciones controladas
            self.assertIn("pisa", self.player.controlled_locations)
            self.assertIn("flore", self.player.controlled_locations)

            # Evento GET_CONTROL emitido
            self.mock_game.add_event.assert_called_once()
            event = self.mock_game.add_event.call_args[0][0]
            self.assertIsInstance(event, TurnEvent)
            self.assertEqual(event.type, EventType.GET_CONTROL)
            self.assertEqual(
                dict(event.data), {"player": "FLORENCE", "provinces": ("pisa",)}
            )

    def test_control_changes_lose_control(self):
        """Pierde el control de una provincia si hay presencia de unidades ajenas."""
        # Tenía 'flore', pero entra un enemigo a 'flore'
        with (
            patch.object(
                self.manager, "_provinces_with_own_units", return_value={"flore"}
            ),
            patch.object(
                self.manager, "_provinces_with_others_units", return_value={"flore"}
            ),
        ):
            self.manager.control_changes(self.player)

            # Pierde 'flore'
            self.assertNotIn("flore", self.player.controlled_locations)

            # Evento LOSE_CONTROL emitido
            self.mock_game.add_event.assert_called_once()
            event = self.mock_game.add_event.call_args[0][0]
            self.assertEqual(event.type, EventType.LOSE_CONTROL)
            self.assertEqual(
                dict(event.data), {"player": "FLORENCE", "provinces": ("flore",)}
            )

    def test_control_changes_emits_sorted_gain_before_sorted_loss(self):
        self.player.controlled_locations = ["rome", "flore", "milan"]

        with (
            patch.object(
                self.manager,
                "_provinces_with_own_units",
                return_value={"venic", "pisa"},
            ),
            patch.object(
                self.manager,
                "_provinces_with_others_units",
                return_value={"rome", "milan"},
            ),
        ):
            self.manager.control_changes(self.player)

        events = [call.args[0] for call in self.mock_game.add_event.call_args_list]
        self.assertEqual(
            [event.type for event in events],
            [EventType.GET_CONTROL, EventType.LOSE_CONTROL],
        )
        self.assertEqual(events[0].data["provinces"], ("pisa", "venic"))
        self.assertEqual(events[1].data["provinces"], ("milan", "rome"))
        self.assertEqual(self.player.controlled_locations, ["flore", "pisa", "venic"])

    def test_control_changes_retain_control(self):
        """Mantiene el control de una provincia vacía si no hay unidades ajenas."""
        # 'flore' estaba controlada, ya no tiene unidades allí pero tampoco el enemigo
        with (
            patch.object(self.manager, "_provinces_with_own_units", return_value=set()),
            patch.object(
                self.manager, "_provinces_with_others_units", return_value=set()
            ),
        ):
            self.manager.control_changes(self.player)

            # 'flore' se mantiene en controlled_locations
            self.assertEqual(self.player.controlled_locations, ["flore"])
            # No se emite ningún evento
            self.mock_game.add_event.assert_not_called()

    def test_control_changes_contested_province(self):
        """No gana control de una provincia nueva si hay otras unidades disputándola."""
        with (
            patch.object(
                self.manager, "_provinces_with_own_units", return_value={"pisa"}
            ),
            patch.object(
                self.manager, "_provinces_with_others_units", return_value={"pisa"}
            ),
        ):
            self.manager.control_changes(self.player)

            # No añade 'pisa' a controladas
            self.assertNotIn("pisa", self.player.controlled_locations)
            self.mock_game.add_event.assert_not_called()


class TestHomeCountryControlLoses(unittest.TestCase):
    def setUp(self):
        self.mock_game = Mock()
        self.manager = ControlManager(game=self.mock_game)

        # Configuración de provincias en el mapa
        self.flore_prov = Mock(city="city")
        self.pisa_prov = Mock(city="fortified")
        self.rural_prov = Mock(city=None)

        self.mock_game.map.provinces = {
            "flore": self.flore_prov,
            "pisa": self.pisa_prov,
            "rural": self.rural_prov,
        }

        # Configuración del País Natal
        self.target_hc = Mock()
        self.target_hc.provinces = ["flore", "pisa", "rural"]
        self.mock_game.scenario.home_countries = {"L": self.target_hc}

        # Mock del jugador
        self.player = Mock()
        self.player.player_id = "FLORENCE"
        self.player.home_countries = ["L"]
        self.player.controlled_locations = []

    def test_home_country_control_loses_keeps_a_city(self):
        """Retiene el país natal si controla al menos una ciudad."""
        self.player.controlled_locations = ["flore"]

        self.manager.home_country_control_loses(self.player)

        self.assertIn("L", self.player.home_countries)
        self.mock_game.add_event.assert_not_called()

    def test_home_country_control_loses_keeps_a_fortified_city(self):
        """Retiene el país natal si controla al menos una ciudad fortificada."""
        self.player.controlled_locations = ["pisa"]

        self.manager.home_country_control_loses(self.player)

        self.assertIn("L", self.player.home_countries)
        self.mock_game.add_event.assert_not_called()

    def test_home_country_control_loses_keeps_no_city(self):
        """Pierde el país natal si solo controla provincias sin ciudad."""
        self.player.controlled_locations = ["rural"]

        self.manager.home_country_control_loses(self.player)

        # Debe eliminarse de home_countries y emitir evento
        self.assertNotIn("L", self.player.home_countries)
        self.mock_game.add_event.assert_called_once()

        event = self.mock_game.add_event.call_args[0][0]
        self.assertIsInstance(event, TurnEvent)
        self.assertEqual(event.type, EventType.LOSE_HOME_COUNTRY)
        self.assertEqual(event.data, {"player": "FLORENCE", "home_country": "L"})

    def test_home_country_control_loses_keeps_no_province(self):
        """Pierde el país natal si no controla ninguna localización del país natal."""
        self.player.controlled_locations = []

        self.manager.home_country_control_loses(self.player)

        self.assertNotIn("L", self.player.home_countries)
        self.mock_game.add_event.assert_called_once()


class TestHomeCountryControlGains(unittest.TestCase):
    def setUp(self):
        self.mock_game = Mock()
        self.manager = ControlManager(game=self.mock_game)

        # Configuración del escenario con 2 países natales
        self.hc_florence = Mock()
        self.hc_florence.provinces = ["flore", "pisa"]

        self.hc_milan = Mock()
        self.hc_milan.provinces = ["milan", "pavia"]

        self.mock_game.scenario.home_countries = {
            "L": self.hc_florence,
            "M": self.hc_milan,
        }

        # Mock del jugador
        self.player = Mock()
        self.player.player_id = "FLORENCE"
        self.player.home_countries = []
        self.player.controlled_locations = []

    def test_home_country_control_gains_gain(self):
        """Gana el país natal si controla el 100% de sus provincias."""
        self.player.controlled_locations = ["flore", "pisa"]

        self.manager.home_country_control_gains(self.player)

        # Debe añadir FLORENCE_HC y emitir evento GET_HOME_COUNTRY
        self.assertIn("L", self.player.home_countries)
        self.mock_game.add_event.assert_called_once()

        event = self.mock_game.add_event.call_args[0][0]
        self.assertIsInstance(event, TurnEvent)
        self.assertEqual(event.type, EventType.GET_HOME_COUNTRY)
        self.assertEqual(event.data, {"player": "FLORENCE", "home_country": "L"})

    def test_home_country_control_gains_not_gain(self):
        """No gana el país natal si le falta controlar alguna de sus provincias."""
        # Solo controla 1 de las 2 provincias de FLORENCE_HC
        self.player.controlled_locations = ["flore"]

        self.manager.home_country_control_gains(self.player)

        self.assertNotIn("L", self.player.home_countries)
        self.mock_game.add_event.assert_not_called()

    def test_home_country_control_already_owned(self):
        """Si el jugador ya posee el país natal, no hace nada ni duplica eventos."""
        self.player.home_countries = ["L"]
        self.player.controlled_locations = ["flore", "pisa"]

        self.manager.home_country_control_gains(self.player)

        # Mantiene la lista intacta con 1 solo elemento y sin eventos
        self.assertEqual(self.player.home_countries, ["L"])
        self.mock_game.add_event.assert_not_called()

    def test_home_country_control_multiple_countries(self):
        """Evalúa todos los países natales del escenario y otorga los completados."""
        # Controla todo FLORENCE_HC y solo parte de MILAN_HC
        self.player.controlled_locations = ["flore", "pisa", "milan"]

        self.manager.home_country_control_gains(self.player)

        self.assertEqual(self.player.home_countries, ["L"])
        self.mock_game.add_event.assert_called_once()
        event = self.mock_game.add_event.call_args[0][0]
        self.assertEqual(event.data["home_country"], "L")


class TestCheckPlayerStatus(unittest.TestCase):
    def setUp(self):
        self.mock_game = Mock()
        self.manager = ControlManager(game=self.mock_game)

        # Configuración de mapa con ciudades y fortificaciones
        self.flore_prov = Mock(city="city")
        self.pisa_prov = Mock(city="fortified")
        self.rural_prov = Mock(city=None)

        self.mock_game.map.provinces = {
            "flore": self.flore_prov,
            "pisa": self.pisa_prov,
            "rural": self.rural_prov,
        }

        # Condiciones de victoria del escenario (ej. 2 ciudades y 1 país natal)
        self.mock_game.scenario.victory_conditions.cities = 2
        self.mock_game.scenario.victory_conditions.home_countries = 1

        # Mock del jugador
        self.player = Mock()
        self.player.player_id = "FLORENCE"
        self.player.home_countries = ["FL"]
        self.player.controlled_locations = ["flore", "pisa"]

    def test_check_player_status_no_home_countries(self):
        """Elimina al jugador si se queda sin ningún país natal."""
        self.player.home_countries = []

        self.manager.check_player_status(self.player)

        self.mock_game.add_event.assert_called_once()
        event = self.mock_game.add_event.call_args[0][0]
        self.assertIsInstance(event, TurnEvent)
        self.assertEqual(event.type, EventType.PLAYER_ELIMINATED)
        self.assertEqual(event.data, {"player": "FLORENCE"})

    def test_check_player_status_winner(self):
        """Victoria cuando el número de ciudades y países natales alcanza el umbral."""
        self.manager.check_player_status(self.player)

        self.mock_game.add_event.assert_called_once()
        event = self.mock_game.add_event.call_args[0][0]
        self.assertIsInstance(event, TurnEvent)
        self.assertEqual(event.type, EventType.PLAYER_WON)
        self.assertEqual(
            event.data,
            {
                "player": "FLORENCE",
                "cities": 2,
                "home_countries": 1,
            },
        )

    def test_check_player_status_missing_cities(self):
        """No emite eventos si el jugador conserva su país natal pero no gana."""
        # Solo controla 1 ciudad ('flore'), pero se necesitan 2 para ganar
        self.player.controlled_locations = ["flore", "rural"]

        self.manager.check_player_status(self.player)

        self.mock_game.add_event.assert_not_called()

    def test_check_player_status_missing_home_countries(self):
        """No emite victoria si cumple ciudades pero no países natales."""
        self.mock_game.scenario.victory_conditions.home_countries = 2
        # Solo tiene 1 país natal
        self.player.home_countries = ["L"]

        self.manager.check_player_status(self.player)

        self.mock_game.add_event.assert_not_called()


class TestControlManagerRun(unittest.TestCase):
    def setUp(self):
        self.mock_game = Mock()
        self.manager = ControlManager(game=self.mock_game)

        # Jugadores de prueba
        self.player_1 = Mock(player_id="FLORENCE")
        self.player_2 = Mock(player_id="MILAN")
        self.mock_game.players = [self.player_1, self.player_2]

        # Año base del escenario
        self.mock_game.scenario.year = 1454

    def test_run(self):
        """Garantiza la secuencia: control_changes -> loses -> gains -> check_status."""
        self.mock_game.turn_number = 0

        with (
            patch.object(self.manager, "control_changes") as mock_control,
            patch.object(self.manager, "home_country_control_loses") as mock_loses,
            patch.object(self.manager, "home_country_control_gains") as mock_gains,
            patch.object(self.manager, "check_player_status") as mock_status,
        ):
            self.manager.run()

            # Comprueba orden de llamadas para player_1
            mock_control.assert_has_calls([call(self.player_1), call(self.player_2)])
            mock_loses.assert_has_calls([call(self.player_1), call(self.player_2)])
            mock_gains.assert_has_calls([call(self.player_1), call(self.player_2)])
            mock_status.assert_has_calls([call(self.player_1), call(self.player_2)])

    def test_run_emits_complete_event_order_for_multiple_players(self):
        scenario = Mock(year=1454)
        game = Game("control order", scenario=scenario, turn_number=2)
        first = Mock(
            player_id="FLORENCE",
            controlled_locations=["rome", "milan"],
        )
        second = Mock(
            player_id="MILAN",
            controlled_locations=["venic", "pisa"],
        )
        game.players = [first, second]
        manager = ControlManager(game)

        def own_provinces(player):
            return {"venic", "pisa"} if player is first else {"rome", "flore"}

        def other_provinces(player):
            return {"rome", "milan"} if player is first else {"venic", "pisa"}

        with (
            patch.object(
                manager,
                "_provinces_with_own_units",
                side_effect=own_provinces,
            ),
            patch.object(
                manager,
                "_provinces_with_others_units",
                side_effect=other_provinces,
            ),
            patch.object(manager, "home_country_control_loses"),
            patch.object(manager, "home_country_control_gains"),
            patch.object(manager, "check_player_status"),
        ):
            manager.run()

        self.assertEqual(
            [event.type for event in game.turn_events],
            [
                EventType.GET_CONTROL,
                EventType.LOSE_CONTROL,
                EventType.GET_CONTROL,
                EventType.LOSE_CONTROL,
                EventType.START_SEASON,
            ],
        )
        self.assertEqual(
            [dict(event.data) for event in game.turn_events],
            [
                {"player": "FLORENCE", "provinces": ("pisa", "venic")},
                {"player": "FLORENCE", "provinces": ("milan", "rome")},
                {"player": "MILAN", "provinces": ("flore", "rome")},
                {"player": "MILAN", "provinces": ("pisa", "venic")},
                {"year": 1454, "season": 2},
            ],
        )

    def test_run_season_and_year(self):
        """Turno 0: Mantiene año base (1454) y estación 0."""
        self.mock_game.turn_number = 0

        with (
            patch.object(self.manager, "control_changes"),
            patch.object(self.manager, "home_country_control_loses"),
            patch.object(self.manager, "home_country_control_gains"),
            patch.object(self.manager, "check_player_status"),
        ):
            self.manager.run()

            event = self.mock_game.add_event.call_args[0][0]
            self.assertEqual(event.type, EventType.START_SEASON)
            self.assertEqual(event.data, {"year": 1454, "season": 0})
