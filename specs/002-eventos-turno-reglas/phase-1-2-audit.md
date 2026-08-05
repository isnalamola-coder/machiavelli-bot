# Auditoría de las fases 1 y 2

Fecha de verificación: 2026-08-04  
Intérprete: CPython 3.13.9  
Revisión base anterior a las fases: `aeaa87523322e8dd55a5a6b67d6fa690e37ff3e1`

Este registro conserva la línea base real, las correcciones previas necesarias para
que la puerta de calidad sea interpretable y la evidencia roja-verde de T002-T004.
Todas las ejecuciones indicadas usaron `py -3.13` para evitar el Python 3.11
predeterminado del entorno.

## T001: línea base anterior a la feature

La línea base se reprodujo en un worktree limpio basado exactamente en la revisión
`aeaa87523322e8dd55a5a6b67d6fa690e37ff3e1`, antes de aplicar las pruebas o la
implementación de Phase 2.

### Pytest

Comando:

```text
py -3.13 -m pytest -q tests/machiavelli/test_game.py tests/machiavelli/game tests/machiavelli/engine tests/machiavelli/services tests/machiavelli/repositories tests/machiavelli/db/test_database.py tests/machiavelli/test_discord.py tests/machiavelli/test_architecture.py
```

Resultado:

```text
369 passed, 1 skipped, 88 subtests passed in 10.86s
```

La ejecución de la misma selección sobre el árbol de trabajo de Phase 2, que ya
incluía las dos pruebas nuevas de T002, daba `371 passed, 1 skipped, 88 subtests
passed in 11.25s`. La diferencia de dos casos corresponde exclusivamente a esas
pruebas.

### Ruff

Comando:

```text
py -3.13 -m ruff check machiavelli tests
```

Resultado preexistente:

```text
F811 Redefinition of unused `test_run_campaign_season_2` from line 130
  tests/machiavelli/engine/test_core.py:222:9
  previous definition: tests/machiavelli/engine/test_core.py:130:9
Found 1 error.
```

El fallo bloqueaba la línea base: la segunda definición sustituía a la primera
durante la creación de la clase de prueba, por lo que pytest no ejecutaba ambos
casos y Ruff no podía finalizar con código 0.

### Mypy

Comando:

```text
py -3.13 -m mypy machiavelli
```

Resultado preexistente:

```text
machiavelli/engine/maintenance.py:78: error: Item "None" of "Scenario | None" has no attribute "province_home_country"  [union-attr]
machiavelli/engine/maintenance.py:78: error: Unsupported operand types for in ("str | Any | None" and "list[str]")  [operator]
machiavelli/engine/maintenance.py:80: error: Item "None" of "Map | None" has no attribute "provinces"  [union-attr]
machiavelli/engine/maintenance.py:80: error: Unsupported operand types for in ("str | Any | None" and "tuple[str, str]")  [operator]
machiavelli/engine/maintenance.py:90: error: Item "None" of "Map | None" has no attribute "provinces"  [union-attr]
machiavelli/engine/income.py:52: error: Item "None" of "Map | None" has no attribute "provinces"  [union-attr]
machiavelli/engine/income.py:52: error: Unsupported operand types for in ("str | Any | None" and "tuple[str, str]")  [operator]
machiavelli/engine/income.py:56: error: Item "None" of "Map | None" has no attribute "provinces"  [union-attr]
machiavelli/engine/income.py:56: error: Generator has incompatible item type "int | Any"; expected "bool"  [misc]
machiavelli/engine/income.py:62: error: Item "None" of "Scenario | None" has no attribute "variable_income_home_countries"  [union-attr]
machiavelli/engine/income.py:69: error: Item "None" of "Scenario | None" has no attribute "variable_income_provinces"  [union-attr]
Found 11 errors in 2 files (checked 38 source files)
```

Estos diagnósticos también bloqueaban la feature: `income.py` y `maintenance.py`
serán modificados en fases posteriores, por lo que una lista no resuelta de errores
en esos mismos archivos impediría distinguir diagnósticos nuevos de los anteriores.

## Correcciones separadas de la línea base

Antes de considerar T001 completada se aplicaron dos correcciones independientes del
cambio funcional de Phase 2:

1. Se renombró la primera definición duplicada a
   `test_run_campaign_season_2_runs_disaster_steps`. Las dos pruebas se recopilan y
   ejecutan ahora; no se modificó ninguna expectativa.
2. `IncomeManager` y `MaintenanceResolver` guardan `game.map` y `game.scenario` en
   variables locales estrechadas exclusivamente con `typing.cast`. `cast()` no
   realiza comprobaciones en tiempo de ejecución, por lo que esta corrección elimina
   los diagnósticos de mypy sin añadir validaciones, excepciones ni comportamiento
   funcional distinto al de la línea base.

Validación específica de estas correcciones:

```text
py -3.13 -m pytest -q tests/machiavelli/engine/test_core.py tests/machiavelli/engine/test_income.py tests/machiavelli/engine/test_maintenance.py
23 passed, 13 subtests passed in 0.14s

py -3.13 -m ruff check tests/machiavelli/engine/test_core.py machiavelli/engine/income.py machiavelli/engine/maintenance.py
All checks passed!

py -3.13 -m mypy machiavelli
Success: no issues found in 38 source files
```

## T002: evidencia roja anterior a T003

La prueba roja se reprodujo en un worktree independiente basado en la revisión base
`aeaa87523322e8dd55a5a6b67d6fa690e37ff3e1`. En ese worktree se añadieron únicamente
los dos casos de `TestRetiredGameAlgorithms`; `machiavelli/game/game.py` conservaba
`initial_setup()` y `spring_start()`.

Comando:

```text
py -3.13 -m pytest -q tests/machiavelli/game/test_game.py::TestRetiredGameAlgorithms::test_initial_setup_is_not_part_of_game_api tests/machiavelli/game/test_game.py::TestRetiredGameAlgorithms::test_spring_start_is_not_part_of_game_api
```

Resultado rojo esperado:

```text
FAILED ...::test_initial_setup_is_not_part_of_game_api
E AssertionError: True is not false

FAILED ...::test_spring_start_is_not_part_of_game_api
E AssertionError: True is not false

2 failed in 0.31s
```

Los dos fallos demuestran que las pruebas detectaban exactamente la presencia de las
APIs históricas antes de ejecutar T003.

## T003-T004: implementación y estado verde

T003 eliminó solamente `Game.initial_setup()`, `Game.spring_start()` y sus imports
exclusivos `random` y `GameTables`. No cambió el contrato vigente de eventos,
reporte o SQLite v3.

Puerta específica de T004:

```text
py -3.13 -m pytest -q tests/machiavelli/game/test_game.py tests/machiavelli/test_game.py
23 passed in 0.19s

py -3.13 -m ruff check machiavelli/game/game.py tests/machiavelli/game/test_game.py tests/machiavelli/test_game.py
All checks passed!
```

## Puerta final de T001-T004

Después de las correcciones de línea base y de Phase 2 se ejecutaron de nuevo los
tres comandos de T001:

```text
py -3.13 -m pytest -q tests/machiavelli/test_game.py tests/machiavelli/game tests/machiavelli/engine tests/machiavelli/services tests/machiavelli/repositories tests/machiavelli/db/test_database.py tests/machiavelli/test_discord.py tests/machiavelli/test_architecture.py
372 passed, 1 skipped, 88 subtests passed in 10.76s

py -3.13 -m ruff check machiavelli tests
All checks passed!

py -3.13 -m mypy machiavelli
Success: no issues found in 38 source files
```

El aumento desde 369 a 372 pruebas corresponde a las dos pruebas de T002 y a la
recuperación de la prueba que antes quedaba oculta por la redefinición F811. Con esta
puerta verde, los fallos anteriores ya no pueden ocultar regresiones de las fases
posteriores.
