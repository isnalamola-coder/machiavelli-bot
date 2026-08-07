# Tasks: Eventos de turno y reglas de escenario

**Input**: Documentos de diseño de `specs/002-eventos-turno-reglas/`

**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`,
`contracts/turn-events.md`, `quickstart.md`

**Tests**: TDD obligatorio para reglas, estado, persistencia, validación y comandos.
Cada tarea de prueba que cambia comportamiento debe ejecutarse y fallar por el motivo
esperado antes de su tarea de implementación. Las pruebas de caracterización se
identifican expresamente y deben pasar antes y después del cambio.

**Organization**: Las fases aparecen en orden topológico. Cuando el grafo abre ramas,
una fase posterior puede avanzar en paralelo con la anterior solo si sus tareas lo
declaran explícitamente. Toda tarea raíz declara su dependencia; los encabezados y
checkpoints describen el grafo, pero nunca sustituyen una dependencia. El cambio de catálogo, agregado,
productores y SQLite se aplica en un único corte vertical sin checkpoint intermedio,
porque retirar `to_record()`, los tipos históricos o la columna `message` antes de
migrar todos sus consumidores dejaría el producto inoperativo. No se añaden
repositorios, subclases de evento, registros dinámicos ni rutas de compatibilidad.

## Formato: `[ID] [P?] [Story] Descripción`

- **[P]**: Puede ejecutarse en paralelo únicamente después de completar todas sus
  dependencias explícitas y cuando modifica archivos distintos de las demás tareas
  paralelas.
- **[Story]**: Historia de usuario trazada desde `spec.md`.
- Todas las rutas son relativas a la raíz del repositorio.
- Una tarea sin `[P]` se ejecuta en exclusiva respecto de las tareas que comparten
  cualquiera de sus archivos.

---

## Phase 1: Setup y línea base

**Purpose**: Confirmar una base conocida sin crear infraestructura ni dependencias.

- [x] T001 Ejecutar `python -m pytest -q tests/machiavelli/test_game.py tests/machiavelli/game tests/machiavelli/engine tests/machiavelli/services tests/machiavelli/repositories tests/machiavelli/db/test_database.py tests/machiavelli/test_discord.py tests/machiavelli/test_architecture.py`, `python -m ruff check machiavelli tests` y `python -m mypy machiavelli`; registrar cualquier fallo preexistente antes de modificar `machiavelli/` o `tests/machiavelli/` y no continuar si impide distinguir una regresión de esta feature
  - Evidencia y fallos conocidos aceptados: [baseline-phase-1.md](./baseline-phase-1.md).

**Checkpoint**: La línea base está registrada; `pyproject.toml` conserva Python
3.13+, pytest, Ruff y mypy, sin dependencias nuevas.

---

## Phase 2: Preparación segura y retirada de algoritmos duplicados

**Purpose**: Eliminar los dos algoritmos históricos sin tocar todavía el catálogo,
`Game.turn_events`, SQLite v3 ni el reporter vigente. Esta fase deja el producto
operativo y crea una base limpia para el corte vertical de Phase 3.

- [ ] T002 Escribir en `tests/machiavelli/game/test_game.py` pruebas fallidas que exijan que `initial_setup` y `spring_start` no existan tras retirar sus algoritmos duplicados, sin cambiar todavía expectativas de `turn_report`, `turn_events`, `Game.add_event()` ni SQL v3 (depende de T001)
- [ ] T003 Eliminar por completo `initial_setup()` y `spring_start()` de `machiavelli/game/game.py` junto con sus imports exclusivos, sin modificar todavía `machiavelli/events.py`, `turn_report()`, `turn_events`, `Game.add_event()`, `Game.save()`, `Game.load_game()` ni el esquema v3 (depende de T002)
- [ ] T004 Ejecutar `python -m pytest -q tests/machiavelli/game/test_game.py tests/machiavelli/test_game.py` y `python -m ruff check machiavelli/game/game.py tests/machiavelli/game/test_game.py tests/machiavelli/test_game.py`; corregir solo esos archivos hasta código 0 y confirmar que guardar, cargar y reportar el formato vigente siguen funcionando (depende de T003)

**Checkpoint**: No quedan algoritmos históricos duplicados y el producto sigue
funcionando íntegramente con el contrato y esquema vigentes.

---

## Phase 3: Corte vertical atómico — US1 + US3 (Priority: P1) MVP

**Purpose**: Preparar primero todas las pruebas rojas y aplicar después, en una sola
tarea indivisible, el catálogo cerrado, los productores, el agregado tipado y SQLite
v4. No existe un estado admitido con tipos nuevos sobre consumidores antiguos, ni con
`TurnEvent` sobre el esquema v3.

**Independent Test**: Ejecutar startup, mantenimiento y campaña, guardar y recargar el
resultado y comprobar que el historial contiene exclusivamente los 26 `TurnEvent`
validados, en orden y sin presentación. Una v3 se actualiza a v4 reiniciando solo
`game_events`; cualquier fila corrupta o fallo SQL aborta sin persistencia parcial.

### Pruebas previas al corte

- [x] T005 [P] Crear en `tests/machiavelli/conftest.py` una fixture con exactamente un payload válido para cada uno de los 26 tipos y escribir en `tests/machiavelli/test_events.py` pruebas fallidas que exijan el catálogo exacto, `JSONValue` nativo, claves exactas, strings no vacíos, enums cerrados, enteros que rechazan `bool`, tiradas 1–6, listas y tuplas militares válidas, aceptación de `military_resolution` con sus seis colecciones vacías, rechazo de payload no objeto, `FrozenInstanceError` al reasignar `event.type` o `event.data`, copia defensiva, inmutabilidad anidada y JSON compacto/determinista con Unicode, `null`, booleanos y listas anidadas (depende de T004)
- [x] T006 [P] [US3] Ampliar `tests/machiavelli/db/test_database.py` con pruebas fallidas para creación limpia v4; upgrade v3→v4 que elimina `message`, crea exactamente `id/game_id/event_type/data_json`, deja `game_events` vacío y conserva games/players/commands; segunda ejecución idempotente; y fallos inyectados después de `DROP TABLE`, después de `CREATE TABLE` y después de fijar `PRAGMA user_version=4` pero antes del commit, comprobando con una conexión nueva que tabla, filas y `PRAGMA user_version=3` quedan restaurados (depende de T004)
- [x] T007 [P] [US3] Ampliar `tests/machiavelli/game/test_game.py` y `tests/machiavelli/repositories/test_game_repository.py` con pruebas fallidas que exijan `Game.turn_events: list[TurnEvent]`, `add_event()` que conserve objeto y orden y rechace cadenas, save/load de eventos repetidos y ordenados con Unicode/`null`/booleanos/listas, columnas separadas y `ORDER BY id ASC`; insertar por SQL tipo desconocido, JSON malformado, JSON no objeto y payload inválido y exigir aborto en la primera fila con `InvalidTurnEventError.row_id/event_type` y causa encadenada (depende de T004)
- [x] T008 [P] [US1] Añadir en `tests/machiavelli/engine/test_setup.py` pruebas fallidas para un único `start_game {scenario}` seguido de un `start_game_power_assigned {player_id, discord_id, power_id}` por jugador en orden de asignación, sin strings ni títulos de fase y con asignación reproducible mediante el `Random` inyectado (depende de T004)
- [x] T009 [P] [US1] Añadir en `tests/machiavelli/engine/test_income.py` pruebas fallidas para un `income_collected` por jugador con provincias y ciudades deterministas, subtotales, total aplicado y una entrada `VariableIncome` por tirada pública 1–6; cubrir `home_country`, `province`, exclusión por hambre/rebelión y ausencia de agregados históricos (depende de T004)
- [x] T010 [P] [US1] Añadir en `tests/machiavelli/engine/test_maintenance.py` pruebas fallidas parametrizadas para cada `MaintenanceResult`, una orden `M` efectiva cuando falte orden explícita, exactamente un `maintenance_order_resolved` por intento en orden, coste correcto para éxito/rechazo/disolución y un `maintenance_summary` por jugador (depende de T004)
- [x] T011 [P] [US1] Añadir en `tests/machiavelli/engine/test_disasters.py` pruebas fallidas para `famine_spawn`/`plague_spawn` con `severity_roll` 1–6 y provincias finales, `famine_relief` solo tras reducción real, `famine_attrition`/`plague_death` con jugador o `None`, `famine_end` con provincias retiradas y ausencia de eventos cuando no hay afectados (depende de T004)
- [x] T012 [P] [US1] Actualizar `tests/machiavelli/engine/test_expenditure.py` con pruebas fallidas para los payloads exactos de `expense`, `expense_no_funds` y `expense_syntax_error`, incluidos `target=None` y `amount` entero|string, sin strings en el historial (depende de T004)
- [x] T013 [P] [US1] Actualizar `tests/machiavelli/engine/test_bribes.py` con pruebas fallidas que exijan solo `bribe_executed {player, expense, target, amount}` al consolidar un soborno y prohíban cualquier productor o referencia a `bribe_set` (depende de T004)
- [x] T014 [P] [US1] Actualizar `tests/machiavelli/engine/test_rebellions.py` con pruebas fallidas para que `rebellion_pacify` incluya propietario y `kind=province|city`, y para que `rebellion_province`/`rebellion_city` incluyan siempre jugador y provincia sin transiciones inexistentes (depende de T004)
- [x] T015 [P] [US1] Añadir en `tests/machiavelli/engine/test_control.py` pruebas fallidas para `get_control`, `lose_control`, `get_home_country`, `lose_home_country`, `player_eliminated`, `player_won` y `start_season`, exigiendo orden estable, listas no vacías y payloads válidos conforme al catálogo nuevo (depende de T004)
- [x] T016 [P] [US1] Actualizar `tests/machiavelli/engine/test_military.py` con pruebas fallidas que exijan que el commit militar añada el objeto `TurnEvent` validado —no un record string— dentro de la misma frontera atómica, conserve las seis colecciones y restaure estado y eventos si falla construcción o commit (depende de T004)
- [x] T017 [P] [US1] Añadir en `tests/machiavelli/engine/test_core.py` pruebas fallidas que exijan sustituir `turn_events` por una lista nueva exactamente una vez al entrar en `GameEngine.run()` para startup, mantenimiento y campaña, conservar el orden relativo de fases y no avanzar el turno si cualquier fase falla (depende de T004)

### Implementación indivisible

- [x] T018 Aplicar el corte vertical completo en un único changeset, sin ejecutar ni aceptar un checkpoint parcial, después de confirmar que T005–T017 fallan por los requisitos nuevos (depende de T005, T006, T007, T008, T009, T010, T011, T012, T013, T014, T015, T016 y T017):
  1. En `machiavelli/events.py`, implementar `JSONValue`, `FrozenJSONValue`, los 26 `EventType`, `InvalidTurnEventError`, validadores directos, `TurnEvent` profundamente inmutable, `to_json()` y `from_persisted()`; renombrar ingreso/mantenimiento, añadir `famine_relief` y eliminar `bribe_set`, `to_record()` y `tipo|json`.
  2. En `machiavelli/db/database.py`, elevar `_SCHEMA_VERSION` a 4 y ejecutar `DROP TABLE game_events`, `CREATE TABLE` y `PRAGMA user_version=4` dentro de una única transacción explícita reversible, sin copiar `message` ni tocar otras tablas.
  3. En `machiavelli/game/game.py`, cambiar conjuntamente `turn_events`, `add_event()`, `save()` y `load_game()` para aceptar, insertar y reconstruir solo `TurnEvent`, con columnas separadas y orden por `id`; no conservar lector ni SQL de `message`.
  4. En `machiavelli/engine/setup.py`, `income.py`, `maintenance.py`, `disasters.py`, `expenditure.py`, `bribes.py`, `rebellions.py` y `control.py`, migrar todos los productores al catálogo y payloads exactos, eliminar retornos o presentación sin consumidor, ordenar solo colecciones nacidas de sets y omitir eventos vacíos.
  5. En `machiavelli/engine/military.py`, construir `TurnEvent.military_resolution()` antes del commit, añadir el objeto en la asignación atómica y conservar `MilitaryResolutionError` con causa.
  6. En `machiavelli/engine/core.py`, reemplazar el historial una sola vez al inicio común de `run()`, retirar el reset exclusivo de campaña y no capturar fallos de fase ni guardar desde el motor.
  7. No crear aliases temporales, rutas duales, compatibilidad v3, `EventRepository`, Pydantic, registry dinámico ni checkpoint con consumidores incompatibles.

### Cierre del corte

- [x] T019 [US3] Añadir en `tests/machiavelli/repositories/test_game_repository.py` una prueba de 10 ciclos consecutivos save/load con la fixture de 26 tipos, incluidos repetidos, comparando la lista completa tras cada ciclo y confirmando reemplazo en vez de acumulación (depende de T018)
- [x] T020 [US3] Añadir en `tests/machiavelli/repositories/test_game_repository.py` una prueba de fallo SQL durante la inserción del segundo evento que recargue con una conexión nueva y compare games, players, commands y eventos con el snapshot anterior; conservar una sola frontera transaccional en `GameRepository.save()` y corregirla solo si la prueba lo exige (depende de T018)
- [x] T021 [US1] Añadir en `tests/machiavelli/engine/test_core.py` un test integrado parametrizado de startup/mantenimiento/campaña con managers reales que reconstruya cada evento mediante `TurnEvent(type=event.type, data=event.data)`, compruebe orden y repetidos y falle ante `str`, Markdown, menciones o tipos fuera de catálogo (depende de T018)
- [x] T022 Ejecutar `python -m pytest -q tests/machiavelli/test_events.py tests/machiavelli/game/test_game.py tests/machiavelli/db/test_database.py tests/machiavelli/repositories/test_game_repository.py tests/machiavelli/engine/test_setup.py tests/machiavelli/engine/test_income.py tests/machiavelli/engine/test_maintenance.py tests/machiavelli/engine/test_disasters.py tests/machiavelli/engine/test_expenditure.py tests/machiavelli/engine/test_bribes.py tests/machiavelli/engine/test_rebellions.py tests/machiavelli/engine/test_control.py tests/machiavelli/engine/test_military.py tests/machiavelli/engine/test_core.py` y después Ruff sobre todos los archivos modificados en Phase 3; corregir únicamente el corte hasta código 0 (depende de T019, T020 y T021)

**Checkpoint MVP**: El producto vuelve a estar verde con catálogo cerrado, productores
estructurados, historial tipado y SQLite v4. Startup, mantenimiento y campaña pueden
ejecutarse, guardarse y recargarse de extremo a extremo.

---

## Phase 4: User Story 2 — Reporte comprensible y errores seguros (Priority: P1)

**Prerequisite**: Todas las tareas raíz dependen explícitamente de T022. Las pruebas
y la implementación interna del reporter pueden avanzar en paralelo con sus pruebas
de servicio y Discord, pero la integración pública espera al cierre del MVP.

**Independent Test**: Entregar al reporter un evento válido de cada tipo y comprobar
salida española no vacía, orden cabecera → fecha → eventos → situación, nombres
públicos o códigos seguros, y detalle completo de las seis colecciones militares.

- [x] T023 [P] [US2] Crear `tests/machiavelli/services/test_turn_reporter.py` con pruebas fallidas para los 26 tipos, orden general, preservación de orden y repetidos, ausencia de mutación, resolución de mención/potencia/provincia/unidad y prohibición de JSON crudo, clases Python o líneas vacías; incluir identificadores adversariales y exigir `escape_markdown(..., as_needed=False)` seguido de `escape_mentions()` (depende de T022)
- [x] T024 [US2] Crear `TurnReporter.generate(game) -> list[str]` en `machiavelli/services/turn_reporter.py` con `match` exhaustivo, helpers mínimos y composición cabecera/fecha/eventos/`game.report_status()` en ese orden (depende de T023)
- [x] T025 [US2] Ampliar `tests/machiavelli/services/test_turn_reporter.py` con pruebas fallidas para `military_resolution`: una línea por item y grupos no vacíos en orden outcomes, cancelled_orders, broken_convoys, dislodgements, rebellions, sieges; cubrir las seis colecciones vacías con exactamente `Sin cambios militares.` (depende de T023)
- [x] T026 [US2] Implementar el render militar detallado sin perder propietario, tipo, origen, costa, destino ni estado de desalojo y sin resumir elementos; omitir solo grupos vacíos (depende de T024 y T025)
- [x] T027 [P] [US2] Actualizar `tests/machiavelli/services/test_game_service.py` con pruebas fallidas que exijan que `get_turn_report()` y `run_turn()` llamen a `TurnReporter.generate()`, devuelvan sus líneas y no llamen a `GameRepository.save()` si falla el reporter (depende de T022)
- [x] T028 [US2] Inyectar el uso directo de `TurnReporter` en `machiavelli/services/game_service.py`, reexportarlo desde `machiavelli/services/__init__.py` y eliminar `Game.turn_report()` y su último consumidor sin interfaz o registry adicional (depende de T024, T026, T027 y T022)
- [x] T029 [P] [US2] Añadir en `tests/machiavelli/test_discord.py` pruebas fallidas para que `run_game` y `game_report` traduzcan `InvalidTurnEventError` a una respuesta española, efímera y accionable, registren solo `row_id`/`event_type`, no expongan payload, excepción o traza y sigan usando `_chunk_lines()` (depende de T022)
- [x] T030 [US2] Añadir en `machiavelli/discord.py` la captura específica y logging contextual de `InvalidTurnEventError`, conservar traducciones militares y `_chunk_lines()` y eliminar interpolaciones públicas de excepciones internas en esos caminos (depende de T029)

**Checkpoint**: T028 y T030 están completos; todos los eventos tienen presentación y
los fallos de historial son seguros para Discord.

---

## Phase 5: User Story 5 — Reglas activas del escenario (Priority: P1)

**Prerequisite**: Las caracterizaciones parten del MVP T022. Esta fase puede avanzar
en paralelo con la rama de reporte de Phase 4, pero ningún cambio de gate puede
comenzar antes de capturar y ejecutar con éxito los snapshots activos.

**Independent Test**: Ejecutar la misma situación alternando una regla y comparar
estado+eventos; cubrir las cuatro combinaciones de hambre y hambre inicial sin alterar
los snapshots con las cinco reglas activas.

### Barrera de caracterización y contrato de escenario

- [x] T031 [US5] Capturar y ejecutar como pruebas verdes, antes de cambiar cualquier gate, caracterizaciones completas, deterministas y versionadas en `test_income.py`, `test_control.py`, `test_maintenance.py`, `test_player_interaction_service.py` y `test_core.py`: `fortress` excluida de ingreso/país natal/victoria/reclutamiento y snapshots de startup, mantenimiento y campaña con las cinco reglas activas, incluido `first_turn_famine=true`, cubriendo jugadores, unidades, control, ducados, hambre inicial, asedios, órdenes, turno y eventos (depende de T022)
- [x] T032 [US5] Ampliar `tests/machiavelli/game/test_scenario.py` con pruebas fallidas separadas para defaults `True` de las cinco reglas y el helper mínimo de plaza defendible, sin modificar ni regrabar las caracterizaciones de T031 (depende de T031)
- [x] T033 [US5] Implementar en `machiavelli/game/scenario.py` el helper de plaza defendible y mantener el parsing de `Rules` con defaults `True`, sin reescribir el mapa ni crear otra jerarquía (depende de T032)

### Ramas de reglas

- [x] T034 [P] [US5] Ampliar `tests/machiavelli/engine/test_setup.py` con pruebas fallidas para abortar antes del primer evento/asignación si una potencia declara guarnición en `fortress` inactiva, aceptar la declarada si está activa, crear independientes automáticas solo en `fortified` no controladas y dejar `ass_counters=[]` cuando asesinatos está inactivo (depende de T031 y T033)
- [x] T035 [US5] Validar al principio de `SetupManager.run()` todas las guarniciones iniciales mediante el helper y pasar a `Player.assign_power_from_scenario()` la secuencia normal o vacía según `assassinations_active`; conservar automáticas solo para `fortified` (depende de T034 y T033)
- [x] T036 [P] [US5] Ampliar `tests/machiavelli/services/test_player_interaction_service.py` con pruebas fallidas para ocultar gasto `E A` si hambre está inactiva, `E E` si asesinatos está inactivo, y Convert/rebelión/asedio/guarnición sobre `fortress` inactiva; permitir esas acciones cuando está activa sin ofrecer reclutamiento ni ingreso (depende de T031 y T033)
- [x] T037 [US5] Aplicar los gates de T036 en `machiavelli/services/player_interaction_service.py`, filtrando opciones antes de construirlas y manteniendo reclutamiento limitado a `city|fortified` (depende de T036 y T033)
- [x] T038 [P] [US5] Ampliar `tests/machiavelli/engine/test_expenditure.py` con pruebas fallidas que carguen comandos obsoletos `E A` y `E E` bajo su regla inactiva y exijan descarte sin cobro, comando ejecutable ni eventos derivados, preservando orden y coste de los demás gastos (depende de T031)
- [x] T039 [US5] Filtrar al inicio de `_process_player_expenses()` los códigos `A` y `E` desactivados antes de parsear, cobrar o emitir, sin alterar las órdenes restantes (depende de T038)
- [x] T040 [P] [US5] Ampliar `tests/machiavelli/engine/test_disasters.py` con la matriz activa/inactiva de todos los métodos públicos: hambre sin alivio/spawn/attrition/clear/eventos cuando está inactiva, plaga sin spawn/muertes/eventos cuando está inactiva y comportamiento vigente cuando están activas (depende de T031)
- [x] T041 [US5] Añadir guards de entrada en `DisastersManager` para que cada método público sea no-op bajo su regla antes de mutar, cobrar o emitir; `famine_active=false` prevalece sobre `first_turn_famine=true` (depende de T040)
- [x] T042 [P] [US5] Ampliar `tests/machiavelli/engine/test_core.py` con pruebas fallidas de orden y conteo de fases: startup genera hambre una vez solo con ambas reglas y `turn_number=0`; mantenimiento nunca; campaña genera una vez con `season=0`; `season=2` resuelve/limpia hambre y genera plaga solo si procede; asesinatos se omite por completo cuando está inactivo (depende de T031)
- [x] T043 [US5] Aplicar en `machiavelli/engine/core.py` los gates y timing de T042 antes de instanciar o llamar cada resolver, conservar el orden relativo restante y limitar `first_turn_famine` al startup (depende de T041 y T042)
- [x] T044 [P] [US5] Ampliar `tests/machiavelli/engine/test_rebellions.py` con pruebas fallidas para impedir pacificación/creación urbana en `fortress` inactiva y permitirla en activa, manteniendo rebeliones provinciales (depende de T031 y T033)
- [x] T045 [P] [US5] Ampliar `tests/machiavelli/engine/test_military.py` con pruebas fallidas para guarnición, Convert y asedio en `fortress`: rechazo equivalente a `city=None` cuando inactiva, aceptación cuando activa y ausencia de estado residual incompatible (depende de T031 y T033)
- [x] T046 [US5] Sustituir comprobaciones locales de plaza defendible en `machiavelli/engine/rebellions.py` por el helper de `Scenario`, sin usarlo para rebeliones provinciales (depende de T044 y T033)
- [x] T047 [US5] Sustituir `_defensible_city_types()` y comprobaciones equivalentes de guarnición, Convert, rebelión urbana y asedio en `machiavelli/engine/military.py` por el helper, tanto en validación como en colecciones finales (depende de T045 y T033)

### Join de reglas

- [x] T048 [US5] Volver a ejecutar, sin regrabar ni suavizar expectativas, todas las caracterizaciones de T031 y exigir equivalencia exacta con las cinco reglas activas, incluida la generación inicial de hambre y la exclusión permanente de `fortress` en ingreso/país natal/victoria/reclutamiento (depende de T035, T037, T039, T041, T043, T046 y T047)
- [x] T049 [US5] Añadir en `tests/machiavelli/engine/test_core.py` un test integrado de cada regla inactiva que compare snapshot de estado y tipos de evento, compruebe ausencia total de tipos prohibidos y preserve el orden relativo de las demás fases; ejecutar también los tres casos activos sin actualizar sus valores esperados (depende de T048)
- [x] T050 [US5] Ejecutar `python -m pytest -q tests/machiavelli/game/test_scenario.py tests/machiavelli/services/test_player_interaction_service.py tests/machiavelli/engine/test_setup.py tests/machiavelli/engine/test_core.py tests/machiavelli/engine/test_disasters.py tests/machiavelli/engine/test_expenditure.py tests/machiavelli/engine/test_income.py tests/machiavelli/engine/test_maintenance.py tests/machiavelli/engine/test_control.py tests/machiavelli/engine/test_rebellions.py tests/machiavelli/engine/test_military.py` y corregir solo los gates cubiertos hasta código 0 (depende de T049)

**Checkpoint**: Las cinco reglas están cubiertas en ambos valores y las
caracterizaciones activas permanecen idénticas.

---

## Phase 6: User Story 4 — Límites de aplicación y atomicidad extremo a extremo (Priority: P2)

**Prerequisite**: Todas las tareas raíz declaran dependencia de T050 y de los joins
públicos T028/T030. Así, ninguna modificación concurrente de `core.py`, servicios o
Discord puede solaparse con las reglas o el reporter.

**Independent Test**: Invocar el worker solo con `db_path` y `channel_id`; conexión,
carga, motor, reporter y guardado ocurren en el mismo worker, la sesión siempre se
cierra y ninguna API externa acepta un resolvedor de desalojos.

- [ ] T051 [US4] Añadir en `tests/machiavelli/services/test_game_service.py` pruebas fallidas para `game_service_session(str|Path)`: usa `DatabaseManager.get_connection()`, construye repositorio y servicio una vez y cierra exactamente una vez en éxito y excepción (depende de T050, T028 y T030)
- [ ] T052 [US4] Implementar `game_service_session()` con `@contextmanager` en `machiavelli/services/game_service.py`, usando `DatabaseManager` y `try/finally`, y reexportarlo desde `machiavelli/services/__init__.py`; no abrir conexión global ni hacer async SQLite (depende de T051)
- [ ] T053 [US4] Ampliar `tests/machiavelli/services/test_game_service.py` con pruebas fallidas para firmas `run_turn(channel_id)` y `GameEngine(game)` sin `dislodgement_resolver`, orden estricto load→engine→reporter→save y persistencia anterior intacta al fallar motor, evento, reporter o save; el desalojo propaga `DislodgementResolverRequired` antes del commit (depende de T052, T028, T022 y T050)
- [ ] T054 [US4] Eliminar `dislodgement_resolver` de `GameService.run_turn()` y `GameEngine.__init__()`, llamar `MilitaryResolver.run()` sin argumento, conservar su seam interno de pruebas y preservar load→run→render→save (depende de T053)
- [ ] T055 [P] [US4] Actualizar `tests/machiavelli/test_discord.py` con pruebas fallidas para que todos los helpers síncronos usen `game_service_session`, `_execute_game_turn(db_path, channel_id)` no acepte resolver, `run_game` haga una sola llamada `asyncio.to_thread`, todo el pipeline síncrono permanezca dentro del callable y una coroutine testigo avance mientras el worker está bloqueado con `threading.Event` (depende de T052, T054, T030 y T050)
- [ ] T056 [P] [US4] Ampliar `tests/machiavelli/test_architecture.py` con pruebas AST fallidas si `machiavelli/discord.py` importa `sqlite3`, `machiavelli.db`, `machiavelli.repositories` o acepta `dislodgement_resolver`, o si Game/productores/motor construyen Markdown o `tipo|json`; comprobar también ausencia de `Game.initial_setup`, `Game.spring_start` y `Game.turn_report` (depende de T052, T054, T028 y T050)
- [ ] T057 [US4] Sustituir `_service_session` en `machiavelli/discord.py` por la API de servicios, eliminar imports directos de persistencia, retirar el resolver de `_execute_game_turn`, mantener defer, privacidad, chunking y envíos fuera del worker, y hacer pasar T055/T056 sin mover E/S al event loop (depende de T055 y T056)
- [ ] T058 [US4] Ejecutar `python -m pytest -q tests/machiavelli/services/test_game_service.py tests/machiavelli/test_discord.py tests/machiavelli/test_architecture.py tests/machiavelli/engine/test_core.py tests/machiavelli/engine/test_military.py` y corregir solo las fronteras hasta código 0 sin implementar retiradas (depende de T057)

**Checkpoint**: Discord es únicamente adaptador, el pipeline es atómico y el fallo
tipado de retiradas no filtra política fuera del motor.

---

## Phase 7: Polish y validación transversal

**Purpose**: Verificar rendimiento, documentación ejecutable y puerta completa.

- [ ] T059 Añadir en `tests/machiavelli/services/test_game_service.py` el caso funcional siempre activo de 10 ciclos save/load/render con 100 eventos y el presupuesto independiente `turn_event_pipeline_budget` condicionado por `MACHIAVELLI_REFERENCE_PERF=1`, con `time.perf_counter()` y límite de 1 segundo, sin framework nuevo ni carga combinada con militar (depende de T058)
- [ ] T060 Actualizar `.github/workflows/military-performance.yml` para ejecutar en el mismo job los presupuestos independientes `representative_resolution_budget` y `turn_event_pipeline_budget` en Ubuntu 24.04/CPython 3.13 con `MACHIAVELLI_REFERENCE_PERF=1` (depende de T059)
- [ ] T061 Ejecutar en orden todos los bloques de `specs/002-eventos-turno-reglas/quickstart.md`, incluidos contrato, migración, productores/reporte, atomicidad, reglas y rendimiento; corregir código o una expectativa documental solo si está demostrablemente desalineada con `spec.md` (depende de T050, T058 y T060)
- [ ] T062 Ejecutar `python -m ruff format --check .`, `python -m ruff check .`, `python -m mypy machiavelli` y `python -m pytest`; exigir código 0 y cobertura global >=71%, sin omitir tests, relajar tipos ni bajar umbrales (depende de T061)

---

## Dependencies & Execution Order

### Dependencias de fases

```text
Phase 1: T001
  -> Phase 2: T002 -> T003 -> T004
       -> Phase 3 tests: T005..T017
            -> corte atómico T018
                 -> cierre T019 + T020 + T021 -> T022
                      -> Phase 4: reporter/servicio/Discord -> T028 + T030
                      -> Phase 5: T031..T050

T022 + T028 + T030 + T050
  -> Phase 6: T051..T058
       -> Phase 7: T059 -> T060 -> T061 -> T062
```

### Dependencias de historias

- **US1 + US3 (P1, fundamento y MVP)**: se implementan juntas en T018 porque el
  catálogo cerrado, sus productores, `Game.turn_events` y SQLite v4 no admiten un
  checkpoint operativo por separado. T005–T017 son pruebas previas; T022 es el único
  checkpoint posterior al corte.
- **US2 (P1)**: toda raíz depende de T022. T023–T027 y T029 pueden preparar ramas
  separadas; la integración pública concluye solo con T028 y T030.
- **US5 (P1)**: depende de T022. T031 es una barrera verde obligatoria; T032 inicia
  las pruebas rojas del nuevo helper y ninguna rama de gate puede precederla.
- **US4 (P2)**: depende de T050, T028 y T030. Esta barrera impide solapamientos en
  `core.py`, servicios o Discord y valida el producto P1 completo.

### Orden interno obligatorio

- Las pruebas T005–T017 se escriben y ejecutan antes de T018.
- T018 es una tarea indivisible: no se aceptan commits, gates ni handoffs parciales
  entre la retirada de APIs antiguas y la migración de todos sus consumidores.
- T031 debe pasar antes de cualquier cambio de regla; T048 debe volver a pasar sin
  actualizar snapshots después de todas las ramas.
- El reporter precede a T028; T028 precede a los límites de aplicación.
- Los cuatro fallos atómicos se prueban en T053 antes de retirar el parámetro público
  de desalojos en T054.
- Las pruebas de Discord y arquitectura T055/T056 preceden a T057.

### Oportunidades paralelas

- Tras T004, T005–T017 pueden repartirse solo por los archivos indicados.
- Tras T022, T023, T027 y T029 pueden arrancar en paralelo.
- Tras T033 y la barrera T031, las ramas setup, UI, gastos, desastres/core y
  rebeliones/militar pueden repartirse respetando sus dependencias.
- Tras T054, T055 y T056 pueden ejecutarse en paralelo porque modifican archivos de
  prueba distintos.

---

## Parallel Execution Examples

### Preparación del corte vertical

```text
Worker A: T005 (contrato)
Worker B: T006 (migración)
Worker C: T007 (agregado/repositorio)
Workers D-L: T008..T017 (productores y core por módulo)
Join exclusivo: T018
Cierre: T019 + T020 + T021 -> T022
```

### Reporte

```text
Reporter: T023 -> T024 -> T025 -> T026
Servicio: T027
Discord: T029 -> T030
Join de integración: T024 + T026 + T027 + T022 -> T028
```

### Reglas

```text
Barrera verde: T031
Contrato de escenario: T032 -> T033
Setup: T034 -> T035
UI: T036 -> T037
Gastos: T038 -> T039
Desastres/core: T040 -> T041 y T042; join T043
Fortalezas: T044 -> T046 y T045 -> T047
Join: T048 -> T049 -> T050
```

---

## Implementation Strategy

### MVP First

1. Completar T001–T004 sin romper el contrato vigente.
2. Preparar T005–T017 y confirmar el fallo esperado de cada requisito nuevo.
3. Aplicar T018 como un único corte vertical.
4. Cerrar persistencia e integración con T019–T022.
5. Detenerse y ejecutar el Independent Test de US1+US3.

### Entrega incremental

1. **Preparación operativa**: retirar solo algoritmos duplicados.
2. **Corte vertical**: catálogo, productores, agregado y SQLite cambian juntos.
3. **Reporte**: representación completa y errores públicos seguros.
4. **Reglas**: caracterización verde, gates por rama y regresión exacta.
5. **Límites**: sesión, worker y API sin política de desalojos externa.
6. **Polish**: presupuestos independientes y puerta completa.

---

## Traceability Matrix

| Requisitos | Tareas propietarias | Evidencia principal |
|------------|---------------------|--------------------|
| FR-001–FR-007 | T005, T007–T018, T021–T022 | contrato, agregado, productores y core |
| FR-008–FR-011 | T009–T014, T018, T021–T022 | income, maintenance, disasters y rebellions |
| FR-012–FR-017 | T023–T030 | reporter, servicio y Discord |
| FR-018–FR-021 | T006–T007, T018–T020, T022 | migración, round-trip y rollback |
| FR-022–FR-026 | T051–T058 | sesión, servicio, Discord y arquitectura |
| FR-027–FR-038 | T031–T050 | caracterización, gates y matriz integrada |
| SC-001 | T008–T018, T021–T022 | tres tipos de turno con catálogo cerrado |
| SC-002 | T023–T026 | 26 tipos y seis grupos militares |
| SC-003 | T007, T019, T022 | 10 ciclos save/load sin cambios |
| SC-004 | T031–T050 | matriz activa/inactiva y combinaciones de hambre |
| SC-005 | T051–T058 | worker único, cierre y progreso del event loop |
| SC-006 | T053–T058 | API externa sin resolver de desalojos |
| SC-007 | T031, T048–T050, T061 | snapshots activos sin cambios |

---

## Definition of Done

- Las 62 tareas respetan el formato checklist, tienen ID secuencial y dependencias
  explícitas suficientes para reproducir el mismo orden sin interpretar prosa.
- Cada comportamiento modificado tiene test previo; ningún test se elimina, relaja o
  regraba para ocultar una regresión.
- No existe checkpoint entre la retirada de `to_record`, tipos históricos o
  `message` y la migración de todos sus consumidores.
- No existen `message`, `to_record`, `tipo|json`, `bribe_set`, `player_income`,
  `player_maintenance`, `Game.initial_setup`, `Game.spring_start` ni
  `Game.turn_report` en caminos productivos al finalizar.
- Discord no importa SQLite ni repositorios, usa una única llamada worker por turno y
  una prueba sincronizada demuestra que el event loop progresa.
- SQLite v4 migra y revierte tabla, filas y `user_version` dentro de una sola
  transacción probada, sin convertir el historial efímero.
- `TurnEvent` es profundamente inmutable y el reporter neutraliza Markdown y
  menciones en identificadores desconocidos.
- Las cinco reglas impiden estado, opciones, cobros, fases y eventos residuales; con
  todas activas, los tres tipos de turno conservan exactamente sus snapshots.
- Quickstart, pytest, Ruff y mypy finalizan con código 0 y se cumplen ambos
  presupuestos de referencia.
