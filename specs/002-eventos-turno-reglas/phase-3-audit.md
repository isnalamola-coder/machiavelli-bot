# Auditoría de la fase 3

Fecha de verificación: 2026-08-04  
Intérprete: CPython 3.13.9  
Revisión Git actual: `aeaa87523322e8dd55a5a6b67d6fa690e37ff3e1`

## Alcance

Este documento registra la evidencia verificable de T005–T022 y separa el estado
funcional actual de la secuencia histórica exigida por T018. No atribuye al pasado
ejecuciones que no quedaron conservadas en Git, en un worktree o en un registro de
comandos.

## Base posterior a T004

`phase-1-2-audit.md` documenta la reproducción de la revisión base, las pruebas rojas
de T002 y la puerta verde posterior a T004. La puerta registrada después de T004 fue:

```text
py -3.13 -m pytest -q tests/machiavelli/test_game.py tests/machiavelli/game tests/machiavelli/engine tests/machiavelli/services tests/machiavelli/repositories tests/machiavelli/db/test_database.py tests/machiavelli/test_discord.py tests/machiavelli/test_architecture.py
372 passed, 1 skipped, 88 subtests passed in 10.76s

py -3.13 -m ruff check machiavelli tests
All checks passed!

py -3.13 -m mypy machiavelli
Success: no issues found in 38 source files
```

Sin embargo, T001–T004 no se guardaron en una revisión Git independiente. `HEAD`
sigue apuntando a la revisión anterior a la feature y los cambios de las fases 1, 2
y 3 permanecen juntos en el árbol de trabajo. Por tanto, no existe un identificador
Git que represente exactamente «posterior a T004 y anterior a T005».

## Cobertura verificable de T005–T017

El árbol actual contiene pruebas directas para los contratos exigidos. La revisión
posterior a la segunda auditoría añadió específicamente:

- T009: comparación exacta y ordenada de las tuplas completas `provinces` y `cities`,
  con entradas procedentes de control, ejércitos, flotas y guarniciones.
- T011: parametrización de `FAMINE_SPAWN` y `PLAGUE_SPAWN` con resultados no vacíos,
  tiradas límite 1 y 6 y payload completo; parametrización de
  `FAMINE_ATTRITION` y `PLAGUE_DEATH` con eventos de jugador y `player=None`.
- T012: matriz para `EXPENSE`, `EXPENSE_NO_FUNDS` y `EXPENSE_SYNTAX_ERROR`, con
  payload completo, `target=None`, importes enteros y string, objetos `TurnEvent` y
  prohibición de cadenas en la secuencia emitida.
- T015: ganancias y pérdidas múltiples procedentes de sets no ordenados, tuplas
  canónicas, `GET_CONTROL` antes de `LOSE_CONTROL` y orden completo para dos
  jugadores seguido de `START_SEASON`.

Comando de validación focalizada:

```text
py -3.13 -m pytest -q tests/machiavelli/engine/test_income.py tests/machiavelli/engine/test_disasters.py tests/machiavelli/engine/test_expenditure.py tests/machiavelli/engine/test_control.py
52 passed in 0.17s
```

## T018: evidencia histórica disponible y límite de certificación

La tarea exige dos hechos históricos previos a la implementación:

1. que T005–T017 se ejecutaron en rojo contra una base posterior a T004;
2. que T018 se aplicó después como un único corte vertical sin checkpoint
   incompatible.

No se conservó un worktree de pruebas solamente, una salida roja, un commit de T004,
un commit de pruebas T005–T017 ni un identificador del corte T018. El historial Git
no contiene commits posteriores a `aeaa875`; esto demuestra que no existe un
checkpoint **persistido en Git**, pero no demuestra qué estados transitorios se
ejecutaron localmente ni el orden cronológico de esas ejecuciones.

Una reproducción roja creada ahora sería retrospectiva: podría demostrar que unas
pruebas detectan el código antiguo, pero no demostraría que esa ejecución ocurrió
antes de la implementación original. Por esa razón no se fabrica ni se retrofecha
una salida roja. T018 queda marcada como pendiente de certificación histórica en
`tasks.md`.

El diff conjunto actual puede identificarse, en el momento de esta auditoría, con:

```text
git diff | git hash-object --stdin
f4b3be2d562502ddc6e6ca6380502621d54659a5
```

Este hash identifica el diff rastreado completo presente durante la auditoría; no es
un commit ni separa T018 de las correcciones posteriores.

## T019–T022: estado verde reproducible

Puerta específica de fase 3:

```text
py -3.13 -m pytest -q tests/machiavelli/test_events.py tests/machiavelli/game/test_game.py tests/machiavelli/db/test_database.py tests/machiavelli/repositories/test_game_repository.py tests/machiavelli/engine/test_setup.py tests/machiavelli/engine/test_income.py tests/machiavelli/engine/test_maintenance.py tests/machiavelli/engine/test_disasters.py tests/machiavelli/engine/test_expenditure.py tests/machiavelli/engine/test_bribes.py tests/machiavelli/engine/test_rebellions.py tests/machiavelli/engine/test_control.py tests/machiavelli/engine/test_military.py tests/machiavelli/engine/test_core.py
303 passed, 1 skipped, 84 subtests passed in 0.96s
```

Puerta completa del repositorio:

```text
py -3.13 -m pytest -q
452 passed, 1 skipped, 88 subtests passed in 17.82s

py -3.13 -m ruff check .
All checks passed!

py -3.13 -m ruff format --check machiavelli tests
78 files already formatted

py -3.13 -m mypy machiavelli
Success: no issues found in 38 source files

git diff --check
Código de salida 0; solo se mostraron avisos de normalización LF/CRLF.
```

## Estado de certificación

- T005–T017: requisitos funcionales y de cobertura verificables en verde.
- T019–T022: ejecución actual reproducible en verde.
- T018: implementación funcional presente, pero secuencia TDD histórica no
  certificable con los artefactos conservados; permanece sin marcar.

Para certificar estrictamente T018 sería necesario reconstruir una revisión inmutable
posterior a T004, aplicar únicamente las pruebas T005–T017, conservar su ejecución
roja, aplicar después el corte vertical completo y registrar ambos identificadores.
Ese procedimiento sería una nueva reproducción controlada, no evidencia de la
cronología original.
