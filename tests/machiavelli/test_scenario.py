# tests/machiavelli/test_scenario.py
import unittest
from unittest.mock import mock_open, patch

from machiavelli.scenario import (
    HomeCountry,
    Power,
    Rules,
    Scenario,
    VictoryConditions,
)


class TestScenario(unittest.TestCase):
    """Pruebas unitarias para la clase Scenario y la carga de datos."""

    def setUp(self):
        """Prepara datos de ejemplo para instanciar escenarios manualmente."""
        self.home_countries = {
            "M": HomeCountry(provinces=["milan", "pavia"]),
            "V": HomeCountry(provinces=["venic", "padua"]),
        }
        self.powers = {
            "M": Power(
                home_countries=["M"],
                armies=["milan"],
                extra_provinces=["genoa"],
            ),
            "V": Power(
                home_countries=["V"],
                fleets=["venic"],
            ),
        }
        self.vc = VictoryConditions(cities=15, home_countries=2)
        self.rules = Rules(fortress_active=False)

    @patch("machiavelli.scenario.GameTables")
    def test_scenario_post_init(self, mock_tables):
        """Verifica que __post_init__ asigna el nombre y añade provincias extra."""
        mock_tables.powers = {"M": "Milan", "V": "Venice"}

        scenario = Scenario(
            name="Test Scenario",
            year=1454,
            victory_conditions=self.vc,
            rules=self.rules,
            home_countries=self.home_countries,
            powers=self.powers,
        )

        # Nombre asignado desde GameTables
        self.assertEqual(scenario.powers["M"].name, "Milan")
        self.assertEqual(scenario.powers["V"].name, "Venice")

        # Asignación de controlled_provinces (país natal + extra_provinces)
        self.assertEqual(
            scenario.powers["M"].controlled_provinces, ["milan", "pavia", "genoa"]
        )
        self.assertEqual(scenario.powers["V"].controlled_provinces, ["venic", "padua"])

    def test_province_home_country(self):
        """Verifica que province_home_country devuelve el ID del país natal o None."""
        scenario = Scenario(
            name="Test Scenario",
            year=1454,
            victory_conditions=self.vc,
            home_countries=self.home_countries,
            powers={},
        )

        self.assertEqual(scenario.province_home_country("milan"), "M")
        self.assertEqual(scenario.province_home_country("padua"), "V")
        self.assertIsNone(scenario.province_home_country("rome"))

    @patch("machiavelli.scenario.GameTables")
    @patch("builtins.open", new_callable=mock_open)
    @patch("json.load")
    def test_load_scenarios_parses_json_structure(
        self, mock_json_load, mock_file, mock_tables
    ):
        """Verifica que load_scenarios parsea correctamente el JSON."""
        mock_tables.powers = {
            "M": "Milan",
            "V": "Venice",
            "L": "Florence",
            "P": "Papacy",
            "N": "Naples",
            "T": "Turks",
        }

        # Mock de la estructura del JSON enviada previamente
        sample_json_data = {
            "Be": {
                "name": "The balance of power",
                "year": 1454,
                "victory_conditions": {"cities": 15, "home_countries": 2},
                "rules": {"fortress_active": False},
                "home_countries": {
                    "M": ["pavia", "milan"],
                    "V": ["padua", "venic"],
                },
                "powers": {
                    "M": {
                        "home_countries": ["M"],
                        "armies": ["pavia", "milan"],
                        "extra_provinces": ["genoa"],
                    },
                    "V": {
                        "home_countries": ["V"],
                        "armies": ["padua"],
                        "fleets": ["venic"],
                    },
                },
                "excluded_locations": ["hunga"],
                "variable_income_home_countries": ["M", "V"],
                "variable_income_provinces": ["milan"],
            }
        }
        mock_json_load.return_value = sample_json_data

        scenarios = Scenario.load_scenarios()

        self.assertIn("Be", scenarios)
        sc = scenarios["Be"]

        # Verificaciones generales del escenario
        self.assertEqual(sc.name, "The balance of power")
        self.assertEqual(sc.year, 1454)
        self.assertFalse(sc.rules.fortress_active)
        self.assertTrue(sc.rules.assassinations_active)  # Valor por defecto

        # Verificación de home_countries como dict
        self.assertIn("M", sc.home_countries)
        self.assertEqual(sc.home_countries["M"].provinces, ["pavia", "milan"])

        # Verificación de potencias y extra_provinces
        self.assertIn("M", sc.powers)
        self.assertEqual(sc.powers["M"].extra_provinces, ["genoa"])
        self.assertEqual(
            sc.powers["M"].controlled_provinces, ["pavia", "milan", "genoa"]
        )


if __name__ == "__main__":
    unittest.main()
