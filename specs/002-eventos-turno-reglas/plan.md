# Implementation Plan: Eventos de turno y reglas de escenario

**Branch**: `codex/turn-events-rules-spec` | **Date**: 2026-08-04 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from
`/specs/002-eventos-turno-reglas/spec.md`

## Summary

Sustituir `Game.turn_events: list[str]` por una secuencia de `TurnEvent` validada,
persistir `event_type` y `data_json` en columnas separadas y generar el texto de
Discord mediante un `TurnReporter` de servicios. La misma entrega elimina los
algoritmos históricos de `Game`, centraliza la sesión SQLite fuera de Discord y
aplica los cinco interruptores de escenario en los puntos de entrada de cada
mecánica. Se reutilizan `GameRepository`, `GameService`, `DatabaseManager` y el
resolver militar actuales; no se añaden dependencias ni otro repositorio. El cambio
de catálogo, productores, agregado y esquema se ejecuta como un único corte vertical,
sin checkpoint intermedio con consumidores incompatibles.

## Technical Context

**Language/Version**: Python 3.13 o superior, con anotaciones modernas y
`dataclass(frozen=True, slots=True)` para valores de dominio inmutables

**Primary Dependencies**: biblioteca estándar (`dataclasses`, `enum`, `json`,
`sqlite3`, `contextlib`, `random`) y dependencias instaladas `discord.py` y
`python-dotenv`; sin dependencias nuevas

**Storage**: SQLite, esquema canónico v4; escenarios y mapa en JSON empaquetado

**Testing**: pytest 8+, Ruff, mypy y pruebas de migración SQLite

**Target Platform**: bot de Discord ejecutado con CPython 3.13 en Linux o Windows;
puerta de rendimiento en Ubuntu 24.04

**Project Type**: aplicación de bot con dominio, motor, servicios y persistencia
SQLite en un único paquete Python

**Performance Goals**: conservar el presupuesto militar existente de menos de un
segundo y completar 10 ciclos guardar-cargar-renderizar de un historial de 100
eventos en menos de un segundo en el job Ubuntu 24.04/CPython 3.13 de referencia

**Constraints**: historial y estado reemplazados en una sola transacción; JSON
nativo determinista y UTF-8; presentación fuera del motor; E/S fuera del event loop;
errores tipados sin datos internos en Discord; líneas de 88 caracteres

**Scale/Scope**: una partida en memoria de hasta 8 jugadores, 30 unidades, 60
órdenes y 100 eventos por turno; coste lineal en eventos y sin retener historiales
anteriores

## Constitution Check

*GATE inicial: aprobado. Se reevalúa después del diseño de Phase 1.*

- [x] Las reglas y productores permanecen en `machiavelli/engine/` o en el dominio;
      `TurnReporter` presenta en servicios y Discord solo coordina interacciones.
- [x] El plan cubre catálogo, productores, persistencia, migración, reporte,
      atomicidad, reglas activas y regresiones de los métodos históricos.
- [x] `run_game` y `game_report` difieren la interacción, ejecutan el trabajo
      bloqueante en un worker y traducen fallos de eventos a español, de forma
      efímera y sin JSON ni trazas.
- [x] La migración v4 elimina y recrea únicamente la tabla efímera `game_events`
      dentro de una transacción; un fallo restaura la tabla anterior y una prueba
      verifica tanto el reinicio intencional como el rollback.
- [x] Se conservan dos cargas representativas independientes: resolución militar
      con 30 unidades y 60 órdenes, y pipeline de 10 ciclos con 100 eventos. Cada
      presupuesto tiene su propia puerta medible en el mismo entorno de referencia.

## Project Structure

### Documentation (this feature)

```text
specs/002-eventos-turno-reglas/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── turn-events.md
└── tasks.md                       # generado después por /speckit-tasks
```

### Source Code (repository root)

```text
machiavelli/
├── db/database.py                 # esquema v4 y migración de game_events
├── discord.py                     # interacción, worker y mensajes públicos seguros
├── events.py                      # catálogo, tipos JSON y validación única
├── game/
│   ├── game.py                    # historial tipado y persistencia del agregado
│   ├── player.py                  # asignación condicional de fichas
│   └── scenario.py                # reglas y plaza defendible activa
├── services/
│   ├── __init__.py                # API de servicios
│   ├── game_service.py            # sesión canónica y transacción del turno
│   ├── player_interaction_service.py
│   └── turn_reporter.py           # presentación completa de eventos y situación
└── engine/
    ├── core.py                    # historial nuevo, orden de fases y gates
    ├── disasters.py              # hambre, plaga y eventos
    ├── expenditure.py            # gastos de mecánicas activas
    ├── income.py                  # ingreso auditable
    ├── maintenance.py             # resultado por orden y resumen
    ├── military.py               # evento tipado dentro del commit militar
    ├── rebellions.py              # propietario y clase de rebelión
    └── setup.py                   # configuración inicial y reglas

tests/machiavelli/
├── db/test_database.py
├── engine/
│   ├── test_core.py
│   ├── test_disasters.py
│   ├── test_expenditure.py
│   ├── test_income.py
│   ├── test_maintenance.py
│   ├── test_military.py
│   ├── test_rebellions.py
│   └── test_setup.py
├── game/test_scenario.py
├── repositories/test_game_repository.py
├── services/
│   ├── test_game_service.py
│   ├── test_player_interaction_service.py
│   └── test_turn_reporter.py
├── test_architecture.py
├── test_discord.py
└── test_events.py

.github/workflows/
└── military-performance.yml       # amplía la puerta de referencia, sin otro job
```

**Structure Decision**: Mantener un único paquete. `events.py` conserva el contrato
de dominio, `Game` persiste el agregado mediante el repositorio existente y un solo
`TurnReporter` nuevo asume la presentación que sale de `Game.turn_report()`. No se
crea `EventRepository`, registro dinámico, subclase por tipo ni paquete adicional.

## Phase 0: Research Decisions

Las decisiones y alternativas están consolidadas en [research.md](./research.md).
No quedan `NEEDS CLARIFICATION`.

## Phase 1: Design and Contracts

- [data-model.md](./data-model.md) define eventos, filas persistidas, reporte,
  historial atómico y reglas de escenario.
- [contracts/turn-events.md](./contracts/turn-events.md) fija las APIs Python, el
  esquema SQLite y el comportamiento de errores y presentación.
- [quickstart.md](./quickstart.md) contiene escenarios ejecutables para catálogo,
  migración, atomicidad, límites, reglas y rendimiento.

## Implementation Strategy

### 1. Preparación segura

1. Registrar la línea base y retirar `Game.initial_setup()` y `Game.spring_start()`
   mediante pruebas específicas, sin modificar todavía `EventType`, `TurnEvent`,
   `Game.turn_events`, SQLite v3 ni `Game.turn_report()`.
2. Mantener un checkpoint verde después de esa retirada. Esta es la única preparación
   independiente permitida antes del cambio de contrato, porque no introduce una ruta
   de compatibilidad ni altera consumidores del historial.
3. Escribir después todas las pruebas rojas del catálogo, migración, agregado,
   productores, militar y orden de fases antes de iniciar la implementación.

### 2. Corte vertical atómico de eventos y persistencia

1. Aplicar en un único changeset el catálogo exacto de 26 `EventType`, el valor
   `TurnEvent`, todos los productores, `Game.turn_events`, `Game.add_event()`,
   guardado/carga y SQLite v4. No se admite un checkpoint entre la retirada de
   `to_record()`, `player_income`, `player_maintenance`, `bribe_set` o `message` y la
   migración de todos sus consumidores.
2. Mantener `TurnEvent` como `@dataclass(frozen=True, slots=True)` y validar en
   `__post_init__` claves exactas, tipos —excluyendo `bool` donde se espera entero—,
   enums cerrados, rangos y colecciones militares canónicas. Copiar y congelar
   recursivamente con `MappingProxyType` y tuplas; `to_json()` materializa copias
   `dict`/`list` y `from_persisted()` repite el mismo contrato.
3. Reutilizar los validadores militares actuales y una tabla directa
   `EventType -> validator`; no crear clases por evento, Pydantic, aliases temporales
   ni registros dinámicos. `InvalidTurnEventError` conserva `row_id` y tipo bruto,
   encadena la causa y nunca incluye el payload.
4. Cambiar `Game.turn_events` a `list[TurnEvent]`; `add_event()` almacena el objeto y
   el resolver militar lo añade dentro de su frontera de commit. `GameEngine.run()`
   sustituye la lista una sola vez antes de elegir startup, mantenimiento o campaña.
5. Migrar en el mismo corte setup, ingreso, mantenimiento, desastres, gastos,
   sobornos, rebeliones, control y militar a los payloads exactos. Preservar orden de
   emisión y ordenar únicamente colecciones nacidas de sets o mappings sin orden
   semántico.
6. Añadir SQLite v4 con una única transacción explícita que ejecute `DROP TABLE
   game_events`, `CREATE TABLE game_events(id, game_id, event_type, data_json)` y
   `PRAGMA user_version=4`. No copiar `message` ni tocar otras tablas; cualquier
   fallo restaura tabla, filas y versión v3.
7. Guardar y cargar eventos en orden dentro de la transacción existente de
   `GameRepository`; probar creación limpia, upgrade, rollback, corrupción, Unicode,
   JSON nativo y 10 ciclos consecutivos antes de declarar el nuevo checkpoint verde.

### 3. Reporte fuera del dominio

1. Crear `TurnReporter.generate(game) -> list[str]` siguiendo el patrón directo de
   `PlayerReporter`: cabecera, estación/año, eventos y situación, en ese orden.
2. Usar un `match` exhaustivo sobre `EventType` y helpers mínimos para nombres. Ante
   un identificador desconocido, neutralizar Markdown y menciones; un payload inválido
   nunca llega al renderer.
3. Para `military_resolution`, emitir una línea por elemento de las seis categorías,
   con encabezados solo para grupos no vacíos y `Sin cambios militares.` cuando las
   seis colecciones estén vacías.
4. Permitir que las pruebas del reporter, del servicio y de los errores de Discord se
   preparen en paralelo después del checkpoint atómico, pero integrar `GameService`
   y eliminar `Game.turn_report()` solo cuando el MVP de productores y persistencia
   esté completamente verde.

### 4. Reglas activas del escenario

1. Capturar primero snapshots deterministas de startup, mantenimiento y campaña con
   las cinco reglas activas. Esa caracterización debe pasar antes de cualquier gate y
   volver a pasar sin regrabar expectativas después de todos los cambios.
2. Reutilizar defaults `True` y añadir un helper mínimo para plaza defendible:
   `fortified` siempre y `fortress` solo con `fortress_active`.
3. Usar el helper en setup, opciones, militar y rebeliones. Ingreso, país natal,
   victoria y reclutamiento siguen limitados a `city`/`fortified`.
4. Rechazar antes del primer evento una guarnición inicial ilegal; omitir fichas,
   opciones, cobros y fase de asesinato cuando corresponda.
5. Proteger todos los métodos públicos de desastres y el timing de `GameEngine`:
   hambre inicial solo con ambas reglas, hambre estacional solo en `season == 0`,
   mantenimiento nunca y plaga solo si está activa.
6. Ocultar y descartar sin cobro órdenes obsoletas de mecánicas inactivas, sin
   reordenar las demás fases ni emitir eventos residuales.

### 5. Atomicidad y límites de aplicación

1. Ejecutar esta etapa solo después del reporter, sus errores públicos y todas las
   reglas. Así no se solapan cambios concurrentes en `core.py`, servicios o Discord.
2. En `GameService.run_turn()`, mantener el orden load→engine→reporter→save. Una
   instancia fallida se descarta; `GameRepository.save()` conserva la única
   transacción que reemplaza estado y eventos.
3. Mover `_service_session` a servicios y construir la conexión con
   `DatabaseManager`. Discord importa únicamente la API de servicios.
4. Eliminar `dislodgement_resolver` de Discord, `GameService` y `GameEngine`;
   `MilitaryResolver.run()` conserva solo su seam interno de prueba y el motor mantiene
   `DislodgementResolverRequired` antes del commit.
5. Mantener una única llamada a `asyncio.to_thread()` para el pipeline síncrono y
   comprobar con `threading.Event` que otra coroutine progresa. Traducir fallos de
   eventos de forma efímera y accionable sin payload, excepción ni traza.

## Test Strategy

- Parametrizar un caso válido e inválido por tipo en `test_events.py`: claves extra o
  ausentes, bool-como-int, rangos, enums y estructuras militares. Intentar reasignar
  `event.type` y `event.data`, mutar después los diccionarios/listas de entrada y
  probar mutación anidada sobre `event.data` para demostrar inmutabilidad completa,
  copia defensiva e inmutabilidad profunda.
- Comparar el catálogo exacto con la tabla de la spec y exigir una salida no vacía
  de `TurnReporter` para cada tipo. Para militar, afirmar cada elemento y categoría,
  además de la línea `Sin cambios militares.` cuando las seis colecciones estén
  vacías. Probar códigos adversariales (`@everyone`, `<@123>`, Markdown y backticks) y que
  solo un `discord_id` conocido produzca una mención real.
- Verificar carga/guardado Unicode, `null`, booleanos y listas anidadas; inyectar tipo,
  JSON y payload corruptos y comprobar fila/tipo y ausencia de omisión silenciosa.
- Fallar por separado motor, construcción de evento, renderer y save; tras recargar,
  estado e historial persistidos deben ser byte-a-byte equivalentes a los previos.
- Probar que `Game` ya no contiene los dos algoritmos históricos y que Discord no
  importa `sqlite3` ni repositorios. Comprobar cierre de sesión en éxito y excepción,
  y usar una prueba asíncrona sincronizada para demostrar que otra coroutine avanza
  antes de liberar un worker bloqueado dentro de `asyncio.to_thread()`.
- Probar la matriz activa/inactiva de fortaleza, asesinatos, hambre, hambre inicial y
  plaga, incluidos gastos persistidos obsoletos, configuración inicial ilegal y
  ausencia de eventos. Capturar antes del cambio snapshots de startup, mantenimiento
  y campaña con las cinco reglas activas, incluido `first_turn_famine=true`, y exigir
  equivalencia exacta del estado final y de la generación inicial de hambre.
- Reutilizar los tests de motor existentes y añadir casos en sus archivos; no crear
  una suite paralela por regla.
- Extender el job de referencia existente con dos presupuestos independientes: la
  resolución militar de 30 unidades/60 órdenes y 10 ciclos con 100 eventos. El test
  funcional de ciclos corre siempre sin umbral; ambos umbrales solo se activan con
  `MACHIAVELLI_REFERENCE_PERF=1`.
- Ejecutar `pytest`, `ruff format --check`, `ruff check` y `mypy machiavelli` antes de
  cerrar la implementación.

## Post-Design Constitution Check

- [x] Dominio y reglas no conocen Discord ni SQLite; el renderer conoce el contexto
      de juego pero no modifica el agregado.
- [x] Cada productor, contrato, migración, límite, regla y fallo atómico tiene una
      regresión prevista en el archivo de prueba que ya posee esa responsabilidad.
- [x] Las pruebas del catálogo, agregado, migración y productores preceden a un único
      corte vertical; no existe un checkpoint con APIs retiradas y consumidores
      antiguos, ni con `TurnEvent` sobre SQLite v3.
- [x] Los comandos afectados difieren E/S, conservan éxito público donde corresponde
      y presentan fallos previsibles de forma efímera, española y accionable.
- [x] La v4 es secuencial y reversible ante fallo. La pérdida de filas se limita al
      historial efímero y es un requisito explícito, no una omisión de migración.
- [x] No hay dependencias nuevas ni estructuras especulativas. Los dos presupuestos
      se miden solo en el entorno de referencia y la corrección corre en todos.

## Agent Context Update

La instalación local de Spec Kit no incluye `update-agent-context` en
`.specify/scripts/`; por ello el contexto se ha actualizado directamente en
[`Agents.md`](../../Agents.md), sin inventar un script o formato intermedio. El
archivo registra:

- Python 3.13+, `discord.py`, `python-dotenv`, SQLite, pytest, Ruff y mypy como stack
  activo, sin dependencias nuevas para esta feature.
- `DatabaseManager`/servicios como propietarios de la sesión y Discord como adaptador
  sin acceso directo a persistencia.
- `TurnEvent` validado como único contrato, `TurnReporter` como único renderer y la
  prohibición de mensajes o `tipo|json` en dominio y motor.
- La migración v4 como evolución canónica y reversible que elimina el formato
  retirado sin conversión ni ruta de compatibilidad.
- Los cinco gates de escenario que deben impedir estado, cobros, fases y eventos
  residuales cuando estén desactivados.

Las directrices generales de `Agents.md` también quedan alineadas con la
constitución: se prohíben conversiones y capas de compatibilidad, pero los cambios
obligatorios de esquema siguen usando migraciones SQLite secuenciales,
transaccionales, reversibles y probadas.

## Complexity Tracking

No hay violaciones constitucionales. La pérdida de `game_events` v3 es deliberada,
acotada a una tabla efímera y exigida por FR-020; las demás filas sobreviven a la
migración y el rollback restaura el esquema anterior si falla.
