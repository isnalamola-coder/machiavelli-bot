# Evidencia de línea base — Phase 1

## Identificación

- Fecha de ejecución: `2026-08-06T23:23:37+02:00`.
- Commit aceptado como línea base: `eeb8a089e40711437c73e04b14c0b18a64036c12`
  (`eeb8a08`, `sync latest upstream engine changes`).
- Intérprete: CPython 3.13.9 desde `.venv/Scripts/python.exe`.
- Estado inicial del working tree:

  ```text
   M Agents.md
   M tests/machiavelli/game/test_game.py
  ```

Los cambios ya presentes en el working tree se registran para no atribuirlos a la
validación de la línea base. Esta ejecución no modificó código productivo ni añadió
dependencias.

## Puerta de T001

Se ejecutaron desde la raíz las órdenes exigidas por `tasks.md` usando Python 3.13.

### Pytest

```powershell
python -m pytest -q tests/machiavelli/test_game.py tests/machiavelli/game tests/machiavelli/engine tests/machiavelli/services tests/machiavelli/repositories tests/machiavelli/db/test_database.py tests/machiavelli/test_discord.py tests/machiavelli/test_architecture.py
```

Resultado registrado:

```text
3 failed, 368 passed, 1 skipped, 88 subtests passed
```

Fallos conocidos de la línea base:

1. `tests/machiavelli/engine/test_core.py::TestGameEngineRunCampaign::test_run_campaign_season_2`
   falla al construir `RetreatHandler` desde `machiavelli/engine/core.py:107`.
2. `tests/machiavelli/engine/test_core.py::TestGameEngineRunCampaign::test_run_campaign_standard_season`
   falla por el mismo trabajo en construcción.
3. `tests/machiavelli/test_architecture.py::test_forbidden_legacy_files_do_not_exist`
   detecta el archivo preexistente `cli.log`.

Los dos primeros fallos pertenecen al trabajo paralelo de retiradas contenido en
`machiavelli/engine/core.py` y `machiavelli/engine/dislodgement.py`. El responsable
del repositorio ha declarado ese trabajo en construcción y fuera del alcance de
`002-eventos-turno-reglas`. El fallo de `cli.log` se registra como una incidencia
arquitectónica preexistente e independiente de la retirada de algoritmos históricos.

Estos fallos no afectan a `Game.initial_setup()`, `Game.spring_start()`, sus imports
exclusivos ni las pruebas limitadas de Phase 2, por lo que permiten distinguir una
regresión causada por esta feature.

### Ruff

```powershell
python -m ruff check machiavelli tests
```

Resultado:

```text
All checks passed!
```

### mypy

```powershell
python -m mypy machiavelli
```

Resultado registrado:

```text
Found 22 errors in 3 files (checked 39 source files)
```

Distribución de los errores conocidos:

- `machiavelli/engine/maintenance.py`: 5 errores.
- `machiavelli/engine/income.py`: 6 errores.
- `machiavelli/engine/dislodgement.py`: 11 errores.

Los errores de `dislodgement.py` pertenecen al trabajo paralelo declarado fuera de
alcance. Los errores de `maintenance.py` e `income.py` quedan registrados como deuda
de tipado preexistente. Ninguno procede de eliminar los dos métodos históricos de
`Game`.

## Configuración conservada

`pyproject.toml` mantiene:

- `requires-python = ">=3.13"`;
- `discord.py` y `python-dotenv` como únicas dependencias de ejecución;
- pytest, Ruff y mypy en las dependencias de desarrollo;
- sin dependencias nuevas para Phase 1 o Phase 2.

## Verificación limitada de Phase 2

Se ejecutó la puerta exacta de T004:

```powershell
python -m pytest -q tests/machiavelli/game/test_game.py tests/machiavelli/test_game.py
python -m ruff check machiavelli/game/game.py tests/machiavelli/game/test_game.py tests/machiavelli/test_game.py
```

Resultado:

```text
23 passed
All checks passed!
```

La comprobación confirma que la retirada de `initial_setup()` y `spring_start()` no
introduce fallos en los archivos propietarios de `Game`, guardado, carga y contrato
vigente cubiertos por T004. Los fallos generales enumerados arriba permanecen como
parte conocida de la línea base y no se consideran regresiones de esta feature.

## Decisión de alcance

El estado de `eeb8a08` se acepta como línea base del repositorio para las fases 1 y 2.
Los fallos localizados en `machiavelli/engine/core.py` y
`machiavelli/engine/dislodgement.py`, así como los errores de tipado asociados,
pertenecen a trabajo en construcción fuera del alcance de
`002-eventos-turno-reglas`. No impiden distinguir regresiones causadas por la retirada
de `Game.initial_setup()` y `Game.spring_start()`.
