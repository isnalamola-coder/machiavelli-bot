# Quickstart: Validar eventos de turno y reglas de escenario

## Requisitos

```powershell
python --version
python -m pip install -e ".[dev]"
```

La versión debe ser Python 3.13 o superior. No se requieren servicios externos ni
credenciales de Discord para las pruebas.

## 1. Contrato de eventos

```powershell
python -m pytest -q tests/machiavelli/test_events.py
```

Resultado esperado:

- El catálogo coincide exactamente con los tipos de la spec y no contiene
  `bribe_set`, `player_income` ni `player_maintenance`.
- Cada payload válido se copia y congela en profundidad; reasignar `event.type` o
  `event.data` produce `FrozenInstanceError`, y mutar la entrada original o intentar
  modificar mappings/secuencias anidados no altera el evento.
- `to_json()` vuelve a materializar valores JSON nativos.
- Claves ausentes/extra, bool en enteros, tiradas fuera de 1–6 y estructuras
  militares inválidas producen `InvalidTurnEventError`.

## 2. Persistencia y migración

```powershell
python -m pytest -q `
  tests/machiavelli/db/test_database.py `
  tests/machiavelli/repositories/test_game_repository.py
```

Resultado esperado:

- Una base v3 conserva partidas, jugadores y órdenes, reinicia solo `game_events` y
  termina en v4 con `event_type` y `data_json`.
- Fallos inyectados después de `DROP`, después de `CREATE` y antes del commit
  conservan tabla, filas y versión v3 con una conexión nueva.
- Una muestra de todos los tipos sobrevive a 10 ciclos de save/load sin cambiar
  orden, Unicode, `null`, booleanos ni listas.
- Tipo, JSON o payload corruptos abortan con fila y tipo identificados.

## 3. Productores y reporte

```powershell
python -m pytest -q `
  tests/machiavelli/game/test_game.py `
  tests/machiavelli/engine/test_setup.py `
  tests/machiavelli/engine/test_income.py `
  tests/machiavelli/engine/test_maintenance.py `
  tests/machiavelli/engine/test_disasters.py `
  tests/machiavelli/engine/test_expenditure.py `
  tests/machiavelli/engine/test_bribes.py `
  tests/machiavelli/engine/test_rebellions.py `
  tests/machiavelli/engine/test_control.py `
  tests/machiavelli/engine/test_military.py `
  tests/machiavelli/services/test_turn_reporter.py `
  tests/machiavelli/test_architecture.py
```

Resultado esperado:

- Setup, ingresos, mantenimiento y campaña contienen solo `TurnEvent` del catálogo.
- Ingreso incluye cada tirada variable y mantenimiento un resultado por orden más
  un resumen por jugador.
- Alivio, rebeliones y desastres contienen propietario, clase, tirada y afectados
  requeridos.
- Cada tipo produce texto español no vacío. El evento militar muestra una línea por
  elemento en las seis categorías, omite solo categorías vacías y, si las seis están
  vacías, produce exactamente `Sin cambios militares.`.
- Identificadores adversariales como `@everyone`, `<@123>`, Markdown y backticks se
  muestran inertes; solo usuarios conocidos producen menciones reales.
- `Game.initial_setup`, `Game.spring_start` y `Game.turn_report` ya no existen.

## 4. Atomicidad y límite Discord

```powershell
python -m pytest -q `
  tests/machiavelli/engine/test_core.py `
  tests/machiavelli/services/test_game_service.py `
  tests/machiavelli/test_discord.py `
  tests/machiavelli/test_architecture.py
```

Resultado esperado:

- Fallos de motor, evento, renderer o save conservan estado e historial persistidos
  del turno anterior.
- Setup, mantenimiento y campaña empiezan con historial nuevo.
- La sesión se cierra en éxito y error; Discord no importa SQLite ni repositorios.
- El turno completo usa una llamada a `asyncio.to_thread`, una coroutine testigo
  progresa mientras el worker permanece bloqueado mediante `threading.Event` y
  ninguna API externa acepta un resolver de desalojos.
- Un historial corrupto produce respuesta efímera y accionable sin JSON o traza.

## 5. Matriz de reglas

```powershell
python -m pytest -q `
  tests/machiavelli/game/test_scenario.py `
  tests/machiavelli/services/test_player_interaction_service.py `
  tests/machiavelli/engine/test_setup.py `
  tests/machiavelli/engine/test_core.py `
  tests/machiavelli/engine/test_disasters.py `
  tests/machiavelli/engine/test_expenditure.py `
  tests/machiavelli/engine/test_income.py `
  tests/machiavelli/engine/test_maintenance.py `
  tests/machiavelli/engine/test_control.py `
  tests/machiavelli/engine/test_rebellions.py `
  tests/machiavelli/engine/test_military.py
```

Casos mínimos esperados:

| Regla | Inactiva | Activa |
|-------|----------|--------|
| Fortaleza | configuración ilegal aborta; sin guarnición/Convert/rebelión/asedio | acciones defendibles permitidas, sin ingreso ni reclutamiento |
| Asesinatos | sin fichas, opción, cobro, fase o evento | comportamiento vigente |
| Hambre | sin alivio, spawn, attrition, clear o evento | respeta fase |
| Hambre inicial | setup sin spawn | un spawn si hambre está activa |
| Plaga | sin spawn, muerte o evento | comportamiento estacional vigente |

También debe comprobarse que las cuatro combinaciones
`famine_active/first_turn_famine` respetan la precedencia de `famine_active=false` y
que una campaña con `season == 0` genera hambre aunque `first_turn_famine=false`.
Con las cinco reglas activas, incluido `first_turn_famine=true`, los snapshots
deterministas de startup, mantenimiento y campaña deben coincidir exactamente con
la caracterización previa, incluida la generación inicial de hambre.

## 6. Rendimiento de referencia

La corrección de los 10 ciclos corre siempre. El umbral solo se ejecuta en el job
estable:

```powershell
$env:MACHIAVELLI_REFERENCE_PERF = "1"
python -m pytest -q `
  tests/machiavelli/engine/test_military.py `
  tests/machiavelli/services/test_game_service.py `
  tests/machiavelli/services/test_turn_reporter.py `
  -k "representative_resolution_budget or turn_event_pipeline_budget"
```

Resultado esperado en Ubuntu 24.04/CPython 3.13:

- La resolución militar representativa de 30 unidades/60 órdenes permanece por
  debajo de 1 segundo.
- De forma independiente, diez ciclos save/load/render de 100 eventos terminan en
  menos de 1 segundo; no se interpreta como una carga combinada con la militar.

## 7. Puerta completa

```powershell
python -m ruff format --check .
python -m ruff check .
python -m mypy machiavelli
python -m pytest --cov=machiavelli --cov-report=term-missing --cov-fail-under=71
```

Todos los comandos deben finalizar con código 0. La cobertura global no baja del
umbral configurado del 71 %.
