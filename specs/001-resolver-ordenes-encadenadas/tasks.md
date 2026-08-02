---

description: "Tareas ejecutables para la resolución militar atómica"
---

# Tasks: Resolución militar atómica

**Input**: Documentos de diseño de
`/specs/001-resolver-ordenes-encadenadas/`

**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`,
`contracts/military-resolution.md` y `quickstart.md`

**Tests**: Obligatorios. Cada matriz se escribe antes de su implementación y debe
fallar por la carencia que va a corregir. Se ejecutan con `pytest`, usando
`unittest.TestCase`, `subTest`, `Mock` y `IsolatedAsyncioTestCase` ya disponibles;
no se añade ninguna dependencia de pruebas.

**Organization**: Las tareas se agrupan por historia de usuario. Dentro de cada
historia, las pruebas preceden al código y cada checkpoint deja un incremento
verificable.

## Formato: `[ID] [P?] [Story] Descripción`

- **[P]**: Puede ejecutarse en paralelo porque modifica otro archivo y no depende de
  una tarea incompleta.
- **[Story]**: Historia de usuario cubierta (`US1` a `US6`).
- Todas las tareas nombran los archivos exactos que pueden modificar.

## Contrato de implementación cerrado

Estas decisiones forman parte de las tareas y no quedan a elección del
implementador:

- Mantener toda la adjudicación en `machiavelli/engine/military.py`; no crear nuevos
  módulos, librerías de grafos, esquema SQLite, migraciones ni dependencias.
- Definir en `machiavelli/engine/military.py` la jerarquía
  `MilitaryResolutionError`, `InvalidMilitaryState`,
  `UnresolvedMilitaryConflict` y `DislodgementResolverRequired`, todas derivadas de
  la primera. Los errores del gestor externo que no sean ya
  `MilitaryResolutionError` se encadenan como `MilitaryResolutionError`.
- Definir `type DislodgementResolver = Callable[[MilitaryResolution],
  Mapping[UnitKey, str | None]]` y conservar exactamente la firma pública
  `MilitaryResolver(game).run(dislodgement_resolver: DislodgementResolver | None =
  None) -> MilitaryResolution`.
- Usar `@dataclass(frozen=True, slots=True)` para `UnitKey`, `MilitaryUnit`,
  `MilitaryOrder`, `ResolutionState`, `UnitOutcome` y `MilitaryResolution`. Sus
  campos y tipos son exactamente los de `data-model.md`; los valores de colección
  que atraviesan fases son `tuple` o `frozenset`, nunca listas o sets mutables.
- Sustituir `conflicts_map` y la mutación incremental por estos pasos privados, en
  este orden: `_build_unit_index()`, `_compile_orders()`,
  `_link_and_validate_orders()`, `_resolve_conflicts()`, `_build_resolution()`,
  `_build_final_collections()` y `_apply_final_collections()`. `run()` solo coordina
  esos pasos, llama al gestor si procede y realiza un único commit en memoria.
- `conflict_location(location, unit_type)` conserva `G provincia` para ciudad y
  devuelve la provincia base para cualquier costa; nunca se usa para identidad,
  actor, adyacencia o localización final de una flota.
- La firma de estado contiene tuplas primitivas ordenadas para todos los campos de
  `ResolutionState`; no usa hashes de proceso, orden de diccionarios ni identidad de
  objetos.
- Las pruebas de `tests/machiavelli/engine/test_military.py` comprueban resultados
  públicos y snapshots completos. Solo prueban directamente los métodos privados de
  índice, compilación y firma cuando eso evita construir una campaña completa.
- Reemplazar las pruebas actuales acopladas al `MilitaryUnit` mutable y a
  `conflicts_map`; no conservarlas junto a las nuevas porque fijan el comportamiento
  que esta feature elimina.
- Reutilizar una sola factoría de escenarios y una sola función de snapshot en
  `tests/machiavelli/engine/helpers.py`; no crear una fixture o clase por regla.
- El evento militar usa `EventType.MILITARY_RESOLUTION` y un único
  `TurnEvent.military_resolution(...)`. Su `data` contiene listas primitivas
  ordenadas bajo las claves `outcomes`, `cancelled_orders`, `broken_convoys`,
  `dislodgements`, `rebellions` y `sieges`.
- No implementar selección de retiradas, persistencia de retiradas ni política de
  guarniciones independientes. El callable externo decide el mapping; el resolver
  solo valida cobertura exacta, destinos, colisiones y atomicidad.

---

## Phase 1: Setup y línea base

**Purpose**: Confirmar el estado inicial sin cambiar configuración ni dependencias.

- [ ] T001 Ejecutar `python -m pytest -q tests/machiavelli/engine/test_military.py tests/machiavelli/engine/test_core.py tests/machiavelli/test_game.py` y `ruff check .` desde la raíz; registrar qué fallos ya existen antes de modificar `machiavelli/engine/military.py`

---

## Phase 2: Infraestructura de pruebas compartida

**Purpose**: Proporcionar un único constructor legible y una comparación completa
del estado militar para todas las historias.

**⚠️ CRITICAL**: Esta fase bloquea las matrices de aceptación posteriores.

- [ ] T002 Añadir a `tests/machiavelli/engine/helpers.py` `create_military_game(...)`, que construya `Game` y `Player` reales con mapa inyectado, órdenes y todas las colecciones militares, y `military_snapshot(game)`, que devuelva una tupla primitiva ordenada de ejércitos, flotas, guarniciones, guarniciones independientes, asedios, rebeliones y eventos; mantener intactos los helpers usados por otras suites

**Checkpoint**: Todas las historias pueden reutilizar el mismo escenario y demostrar
atomicidad sin comparar objetos `Mock` incompletos.

---

## Phase 3: User Story 1 - Resolver una campaña sin estados parciales (Priority: P1) 🎯 MVP

**Goal**: Capturar un snapshot válido, compilar una intención por unidad, resolver
movimientos directos y conversiones básicas de forma determinista y aplicar el
resultado una sola vez.

**Independent Test**: Una campaña con Hold, Advance, Support y Convert produce los
mismos `MilitaryResolution`, evento y colecciones bajo permutaciones de jugadores y
órdenes; duplicados, resultados inválidos o una excepción dejan idéntico el snapshot.

### Tests for User Story 1

- [ ] T003 [US1] Reemplazar en `tests/machiavelli/engine/test_military.py` las pruebas de `conflicts_map` por `TestMilitaryModelsAndIndex` con subtests que verifiquen igualdad/hash de `UnitKey`, conservación de costa, índices de ejército/flota/guarnición independiente, separación provincia/`G provincia`, y `InvalidMilitaryState` para clave duplicada, ocupación provincial normalizada duplicada y dos guarniciones en la misma ciudad
- [ ] T004 [US1] Añadir en `tests/machiavelli/engine/test_military.py` `TestOrderCompilation` con casos para los siete códigos `A/B/H/L/S/T/C`, Hold por ausencia de fila, Hold más entrada en `invalid_orders` para código/target/combinación inválida de un actor existente, fila de actor inexistente ignorada sin afectar otras unidades, aislamiento del error a una sola unidad, Advance directo por modo `LAND`/`SEA`, conversión `A|F -> G` y `G -> A|F`, costa exacta y ausencia total de mutaciones durante índice/compilación
- [ ] T005 [US1] Añadir en `tests/machiavelli/engine/test_military.py` `TestAtomicResolution` con una victoria, empate de máximos, conversión ganadora/perdedora, una permutación de jugadores y colecciones, snapshot corrupto y excepción inyectada antes del commit; afirmar un `UnitOutcome` por unidad, ausencia de ocupaciones duplicadas, igualdad exacta de resolución/evento entre permutaciones y snapshot inicial intacto en todos los fallos

### Implementation for User Story 1

- [ ] T006 [US1] Sustituir `MilitaryUnit` mutable y añadir la jerarquía de errores, `UnitKey`, `MilitaryUnit`, `MilitaryOrder`, `ResolutionState`, `UnitOutcome`, `MilitaryResolution` y `DislodgementResolver` definidos en el contrato cerrado dentro de `machiavelli/engine/military.py`; usar tipos modernos de Python 3.13, excepciones específicas y ningún `except` genérico silencioso
- [ ] T007 [US1] Implementar `conflict_location()` y `MilitaryResolver._build_unit_index()` en `machiavelli/engine/military.py`; poblar sin sobrescrituras `units_by_key`, `actor_to_unit`, `army_by_origin` y `fleet_by_conflict_location`, validar duplicados antes de leer `player.commands` y ordenar claves mediante `(player_id or "", unit_type, origin)`
- [ ] T008 [US1] Implementar `_compile_orders()` y la validación no dependiente de convoy en `_link_and_validate_orders()` dentro de `machiavelli/engine/military.py`; agrupar filas por `(player_id, actor)` conservando orden, producir exactamente un `MilitaryOrder` por unidad, representar los siete códigos, aplicar Hold efectivo a ausencia/orden individual inválida y conservar el motivo en `invalid_orders`
- [ ] T009 [US1] Implementar en `machiavelli/engine/military.py` la evaluación básica de posiciones, Advance directos, Hold y Convert, incluyendo ciudad/provincia como conflictos distintos, fuerza base, empate de máximos y validación de `UnitOutcome`; construir todas las listas finales en variables locales y rechazar unidad sin outcome, ejército en mar, costa inválida, convoy parcial u ocupación final duplicada
- [ ] T010 [P] [US1] Añadir `EventType.MILITARY_RESOLUTION` y la factoría `TurnEvent.military_resolution(...)` en `machiavelli/events.py`; convertir claves, outcomes y cambios a listas de valores primitivos ordenadas con las seis claves fijadas en el contrato cerrado
- [ ] T011 [US1] Implementar `_build_resolution()`, `_build_final_collections()`, `_apply_final_collections()` y el flujo de `run()` sin desalojos en `machiavelli/engine/military.py`; asignar todas las colecciones una única vez, emitir exactamente un evento después del commit y registrar con `logging.getLogger(__name__)` la misma información reproducible sin datos Discord ni detalles sensibles

**Checkpoint**: US1 pasa por sí sola y constituye el MVP atómico; Support puede estar
compilado, pero sus dependencias avanzadas se completan en US3.

---

## Phase 4: User Story 2 - Ejecutar un convoy encadenado y atómico (Priority: P1)

**Goal**: Compilar varios Advance de un ejército como una única ruta y moverlo solo
entre origen y destino final cuando todas las transportadoras siguen disponibles.

**Independent Test**: Un ejército, dos mares y dos flotas terminan solo en destino o
solo en origen; nunca ocupan tramos intermedios ni generan cruces de convoy.

### Tests for User Story 2

- [ ] T012 [US2] Añadir `TestConvoyCompilationAndResolution` en `tests/machiavelli/engine/test_military.py` con subtests para una/dos flotas, transportadora extranjera, filas intercaladas, ruta repetida finita, declaración T inversa correcta, T ausente/equivocada/duplicada, tramo no adyacente, destino final marítimo, único Advance no terrestre, flota situada solo en destino y convoy opuesto a movimiento directo; afirmar ruta completa, transportadoras únicas para dependencia, cero ocupación/conflicto intermedio y ausencia de cruce para convoy

### Implementation for User Story 2

- [ ] T013 [US2] Extender `_compile_orders()` en `machiavelli/engine/military.py` para convertir dos o más Advance del mismo ejército en un `MilitaryOrder(is_convoy=True, path=(origen, *targets))`; un único Advance conserva semántica directa, y cualquier combinación múltiple distinta produce Hold sin ejecutar prefijos
- [ ] T014 [US2] Extender `_link_and_validate_orders()` en `machiavelli/engine/military.py` para resolver cada punto intermedio contra la flota inicial y su única orden Transport, aceptar facciones distintas, validar adyacencia de cada tramo y destino provincial, mantener repeticiones en `path` y deduplicar solo `transporters` para dependencias
- [ ] T015 [US2] Integrar convoyes en la evaluación de `machiavelli/engine/military.py`: el ejército participa únicamente en el conflicto del destino final, las flotas Transport permanecen y reciben fuerza/apoyos normales, solo un `UnitOutcome` exitoso mueve origen→destino y los convoyes nunca se incluyen en la detección de cruces
- [ ] T016 [US2] Propagar en `machiavelli/engine/military.py` el desalojo de cualquier transportadora a la cancelación del convoy completo y reconstruir posiciones/conflictos; conservar el convoy ante empate, ataque fallido o victoria defensiva y añadir la clave del ejército a `broken_convoys` del evento solo cuando una transportadora requerida queda desalojada

**Checkpoint**: US2 demuestra SC-001 para rutas válidas, inválidas y rotas.

---

## Phase 5: User Story 3 - Resolver dependencias y cancelaciones (Priority: P1)

**Goal**: Resolver primero conflictos independientes, recalcular tras cancelaciones y
romper círculos con las dos reglas de Support antes de declarar un ciclo irresoluble.

**Independent Test**: El desalojo de una Transport rompe el convoy y cambia los
conflictos de origen/destino; un círculo se resuelve por Support atacado, por
cancelación de todos los Supports o aborta sin commit si reaparece una firma previa.

### Tests for User Story 3

- [ ] T017 [US3] Añadir `TestConflictConstructionAndSupport` en `tests/machiavelli/engine/test_military.py` con destino de una facción, disputa de dos facciones, autoconflicto, intercambio directo propio, cruce enemigo, provincia frente a ciudad, Support con facción omitida/explícita, guarnición apoyando provincia, apoyos distintos por extremo de cruce, Support cortado por ataque empatado y excepción cuando apoya el origen del atacante; afirmar fuerzas, cancelaciones y `contested_locations` exactos
- [ ] T018 [US3] Añadir `TestDependencyResolution` en `tests/machiavelli/engine/test_military.py` con una cadena independiente→Transport desalojada→convoy roto, una dependencia de Support, reconstrucción global y orden de entrada permutado; afirmar que solo se resuelven claves sin dependencias pendientes y que la resolución/cancelaciones finales no dependen del orden incidental
- [ ] T019 [US3] Añadir `TestCyclesAndCancellationSemantics` en `tests/machiavelli/engine/test_military.py` con ataque directo y convoy disponible contra Support desde origen distinto, ataque desde el lugar apoyado, primera etapa insuficiente, segunda etapa cancelando todos los Supports, firma consecutiva estable y firma no consecutiva repetida; afirmar que una orden cancelada defiende físicamente pero no hace Hold, Support, Transport, Besiege, Lift siege, Convert ni somete rebelión, y que el último ciclo lanza `UnresolvedMilitaryConflict` sin mutación

### Implementation for User Story 3

- [ ] T020 [US3] Implementar en `machiavelli/engine/military.py` la construcción global de posiciones y conflictos por ronda, detección de cruces solo entre Advance directos, autoconflicto salvo intercambio propio válido, `contested_locations` solo con dos o más facciones y ambos extremos de cruces, y fuerza como base + Supports activos dirigidos a facción/lugar
- [ ] T021 [US3] Implementar en `machiavelli/engine/military.py` dependencias de cada conflicto sobre emisores de Support y flotas Transport situados en conflictos pendientes; resolver todas las claves independientes en orden estable, cancelar Advance/Convert perdedores, todos los máximos empatados, órdenes de desalojados y Supports cortados, y reconstruir el tablero completo tras cada cambio
- [ ] T022 [US3] Implementar en `machiavelli/engine/military.py` el desempate circular y la firma completa: primero cancelar cada Support atacado por Advance válido, activo y no cancelado desde origen distinto del lugar apoyado —directo o con convoy disponible y sin umbral de fuerza—; después cancelar todos los Supports restantes; aceptar solo firma consecutiva idéntica como estabilidad y lanzar `UnresolvedMilitaryConflict` ante firma no consecutiva repetida sin regla restante

**Checkpoint**: Las tres historias P1 forman un adjudicador determinista con
cancelaciones propagadas.

---

## Phase 6: User Story 4 - Aplicar rebeliones y asedios (Priority: P2)

**Goal**: Tratar rebeliones como modificadores y calcular el ciclo completo de
asedios sin crear unidades ficticias ni perder guarniciones.

**Independent Test**: Una provincia y ciudad fortificada recorren fuerza rebelde,
sometimiento/liberación/pacificación, inicio/final/levantamiento de asedio y
restricciones de conversión con resultados y evento exactos.

### Tests for User Story 4

- [ ] T023 [US4] Añadir `TestRebellions` en `tests/machiavelli/engine/test_military.py` con rebelión provincial y urbana para conflicto provincial/urbano, controlador frente a otras facciones, ausencia de conflicto creado solo por rebelión, Hold explícito/por ausencia/por orden inválida, orden cancelada, Advance liberador y estado ya pacificado por gasto; afirmar modificador +1 solo a participantes provinciales elegibles y transiciones exactas de ambas listas de rebelión
- [ ] T024 [US4] Añadir `TestSiegesAndRestrictedConversions` en `tests/machiavelli/engine/test_military.py` con guarnición y rebelión urbana, primer/segundo Besiege, Lift siege, asediador desalojado, flota en ciudad con/sin puerto, conversión bajo asedio, conversión/contratación hacia ciudad rebelde cerrada, órdenes permitidas del asediador y guarnición asediada; afirmar objetivo eliminado solo al segundo Besiege exitoso y conservación en levantamiento/desalojo

### Implementation for User Story 4

- [ ] T025 [US4] Integrar en la fuerza provincial de `machiavelli/engine/military.py` las rebeliones provinciales y urbanas dirigidas contra el controlador; no añadir participantes ni fuerza a `G provincia`, y calcular en colecciones locales pacificación ya aplicada, sometimiento solo por Hold efectivo exitoso y liberación solo por Advance exitoso de otra facción
- [ ] T026 [US4] Implementar en `machiavelli/engine/military.py` la validación y transición de Besiege/Lift siege: ciudad fortificada y objetivo presente, puerto obligatorio para flota, restricciones de órdenes bajo asedio, primer Besiege añade provincia, segundo elimina guarnición/rebelión urbana, Lift o desalojo del asediador quita provincia sin eliminar objetivo
- [ ] T027 [US4] Integrar en `machiavelli/engine/military.py` las restricciones de Convert por asedio y ciudad rebelde cerrada, validar rebeliones/asedios finales antes del commit y rellenar las listas ordenadas `rebellions` y `sieges` del único evento militar sin emitir eventos intermedios

**Checkpoint**: US4 cubre todas las transiciones P2 de rebelión, conversión y asedio.

---

## Phase 7: User Story 5 - Conservar retiradas y lugares disputados (Priority: P2)

**Goal**: Entregar una resolución inmutable al gestor de desalojos antes de aplicar o
continuar la campaña y detener todo el turno ante gestor ausente o inválido.

**Independent Test**: Un desalojo llama una vez al gestor con identidad y espacios
disputados; solo un mapping exacto permite el commit y las fases de hambre/control
ocurren después. Cualquier fallo conserva el snapshot y produce el mensaje seguro.

### Tests for User Story 5

- [ ] T028 [US5] Añadir `TestDislodgementContract` en `tests/machiavelli/engine/test_military.py` con resultado sin desalojos, gestor ausente, gestor que lanza, mapping incompleto, clave extra, destino disputado, dos retiradas al mismo destino, eliminación `None`, retirada válida y guarnición independiente desalojada; afirmar llamada única previa al commit, cobertura exacta, snapshot intacto en fallo, identidad conservada y guarnición pendiente salvo decisión explícita del mapping
- [ ] T029 [P] [US5] Ampliar `tests/machiavelli/engine/test_core.py` con pruebas de `GameEngine(game, dislodgement_resolver=None)`, paso exacto del callable a `MilitaryResolver.run`, orden militar→retirada completada→hambre→control, y parada ante `MilitaryResolutionError`; afirmar que attrition, control, clear_famine y spawn_plague no se invocan tras el error
- [ ] T030 [P] [US5] Crear `tests/machiavelli/test_discord.py` con `unittest.IsolatedAsyncioTestCase`, `AsyncMock` y el callback real de `run_game`: afirmar `interaction.response.defer(ephemeral=True)`; en éxito, guardado, borrado de la respuesta diferida con `delete_original_response()` y publicación del reporte mediante `followup.send(..., ephemeral=False)`; en `GameNotFoundException`, edición separada de la respuesta original; y para cada subclase de `MilitaryResolutionError`, `logger.exception` más `edit_original_response(content="No se pudo resolver la fase militar; no se aplicó ningún cambio.")` sin followup, nombre de error, traceback, archivo ni línea

### Implementation for User Story 5

- [ ] T031 [US5] Completar en `machiavelli/engine/military.py` el flujo de desalojos de `run()`: construir primero `MilitaryResolution`, exigir gestor solo cuando haya `UnitOutcome.dislodged`, invocarlo una vez, validar mapping exacto, prohibir `contested_locations` y colisiones, aceptar `None`, combinar retiradas con las colecciones locales y no emitir evento ni asignar nada hasta superar todas las validaciones
- [ ] T032 [P] [US5] Añadir a `GameEngine.__init__` el parámetro `dislodgement_resolver: DislodgementResolver | None = None`, guardarlo y pasarlo por nombre a `MilitaryResolver.run` en `machiavelli/engine/core.py`; no capturar `MilitaryResolutionError` en el motor para que la excepción detenga de forma natural hambre, control y cambio de estación
- [ ] T033 [P] [US5] Importar `logging` y `MilitaryResolutionError`, crear `logger = logging.getLogger(__name__)` y ajustar `run_game` en `machiavelli/discord.py` para diferir siempre con `ephemeral=True`, borrar la respuesta original antes de publicar por followup el reporte exitoso con `ephemeral=False`, y añadir un `except MilitaryResolutionError` anterior al genérico que use `logger.exception` y `interaction.edit_original_response(content="No se pudo resolver la fase militar; no se aplicó ningún cambio.")` sin `format_error_with_location`; mantener `GameNotFoundException` en su rama propia editando la respuesta original
- [ ] T034 [US5] Ejecutar `python -m pytest -q tests/machiavelli/engine/test_military.py -k "atomic or dislodg or retreat or unresolved"`, `python -m pytest -q tests/machiavelli/engine/test_core.py -k "military or dislodg or order"` y `python -m pytest -q tests/machiavelli/test_discord.py -k "run_game"`; corregir solo código de `machiavelli/engine/military.py`, `machiavelli/engine/core.py` y `machiavelli/discord.py` hasta que los tres grupos pasen

**Checkpoint**: La campaña nunca consolida un estado militar incompleto ni ejecuta
fases posteriores antes de resolver retiradas.

---

## Phase 8: User Story 6 - Preservar el orden declarado (Priority: P3)

**Goal**: Recuperar las filas por su secuencia persistida sin migración ni cambio en
guardado.

**Independent Test**: Tres Advance intercalados con dos actores y dos jugadores
mantienen la misma secuencia tras cargas repetidas y guardar-cargar-guardar.

### Tests for User Story 6

- [ ] T035 [US6] Añadir a `tests/machiavelli/test_game.py` una prueba de consulta que exija literalmente `ORDER BY id ASC` y una prueba de integración con `sqlite3` temporal inicializada mediante `machiavelli.database.upgrade`: insertar órdenes intercaladas de dos actores y dos jugadores, cargar dos veces y ejecutar guardar-cargar-guardar; afirmar igualdad de las tuplas `(actor, command, target)` por jugador y ausencia de migración nueva

### Implementation for User Story 6

- [ ] T036 [US6] Cambiar únicamente el `SELECT` de `Command.load_commands()` en `machiavelli/game.py` para añadir `ORDER BY id ASC`; no modificar `Command.save()`, `Player.save_commands()`, `machiavelli/database.py`, `_SCHEMA_VERSION` ni `_UPGRADES`
- [ ] T037 [US6] Ejecutar `python -m pytest -q tests/machiavelli/test_game.py -k "command and order"` y `python -m pytest -q tests/machiavelli/engine/test_military.py -k "compile or convoy"`; confirmar que la ruta compilada conserva el orden relativo después del round-trip

**Checkpoint**: US6 cumple FR-007/FR-053 usando el `id` existente.

---

## Phase 9: Rendimiento, auditoría y puertas finales

**Purpose**: Verificar el presupuesto aprobado y la cobertura integrada sin añadir
microbenchmarks ni pruebas duplicadas.

- [ ] T038 Añadir `test_representative_resolution_budget` en `tests/machiavelli/engine/test_military.py` con exactamente 30 unidades, 60 filas, 20 lugares de conflicto y un convoy de 5 flotas; construir el escenario una vez, ejecutar cinco resoluciones desde snapshots equivalentes con `time.perf_counter()`, afirmar menos de 1 segundo por ejecución —no promedio— e igualdad exacta de firma, `MilitaryResolution` y evento
- [ ] T039 Ejecutar todos los comandos y comprobar todos los resultados esperados de `specs/001-resolver-ordenes-encadenadas/quickstart.md`; si un selector `-k` no recoge una prueba prevista, renombrar esa prueba en `tests/machiavelli/engine/test_military.py`, `tests/machiavelli/engine/test_core.py`, `tests/machiavelli/test_game.py` o `tests/machiavelli/test_discord.py` sin duplicarla
- [ ] T040 Revisar `tests/machiavelli/engine/test_military.py` contra FR-001–FR-052 y SC-001–SC-008, eliminar únicamente pruebas obsoletas del flujo mutable y confirmar que cada requisito está cubierto una vez por la matriz más cercana; no añadir pruebas equivalentes con distinta preparación
- [ ] T041 Ejecutar `python -m pytest -q` y `ruff check .`; corregir todos los fallos en `machiavelli/engine/military.py`, `machiavelli/engine/core.py`, `machiavelli/events.py`, `machiavelli/game.py`, `machiavelli/discord.py` y sus cinco archivos de prueba, sin debilitar asserts, ampliar alcance ni añadir dependencias

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1** no tiene dependencias.
- **Phase 2** depende de Phase 1 y bloquea todas las matrices.
- **US1** depende de Phase 2 y crea el contrato/base del resolver.
- **US2** depende de US1 porque extiende la compilación y evaluación de Advance.
- **US3** depende de US2 porque las dependencias incluyen Transport y convoyes.
- **US4** depende de US3 porque rebeliones y asedios usan la fuerza y cancelaciones
  estables.
- **US5** depende de US4 porque entrega el resultado militar completo al gestor.
- **US6** solo depende de Phase 2 para su prueba de persistencia, pero se programa
  después de las P1/P2 por prioridad y no bloquea sus pruebas en memoria.
- **Phase 9** depende de todas las historias seleccionadas.

### Within Each User Story

1. Escribir toda la matriz de pruebas indicada.
2. Ejecutarla y confirmar que falla por comportamiento ausente, no por preparación.
3. Implementar las tareas en el orden listado.
4. Ejecutar el checkpoint y la suite de historias anteriores.

### Parallel Opportunities

- T010 puede avanzar en `machiavelli/events.py` mientras T006–T009 trabajan en el
  resolver, usando el contrato de evento ya cerrado.
- T029 y T030 pueden escribirse en paralelo después de US4 porque modifican archivos
  de prueba distintos.
- T032 y T033 pueden implementarse en paralelo después de T031 porque tocan límites
  distintos y consumen el mismo error público ya definido.
- Las historias US1–US5 no deben implementarse simultáneamente en
  `machiavelli/engine/military.py`; comparten el mismo archivo y cada una extiende la
  anterior.

## Parallel Examples

### User Story 1

```text
Task T010: definir el evento en machiavelli/events.py
Task T006-T009: definir modelos, índice, compilación y evaluación en machiavelli/engine/military.py
```

### User Story 5

```text
Task T029: pruebas de orquestación en tests/machiavelli/engine/test_core.py
Task T030: pruebas de UX en tests/machiavelli/test_discord.py

Después de T031:
Task T032: integración del callable en machiavelli/engine/core.py
Task T033: traducción segura del error en machiavelli/discord.py
```

---

## Implementation Strategy

### MVP First

1. Completar Phase 1 y Phase 2.
2. Completar US1 (T003–T011).
3. Ejecutar su checkpoint y detenerse si solo se necesita atomicidad básica.

### Incremental Delivery

1. US1: snapshot, compilación, resolución básica y commit atómico.
2. US2: convoyes encadenados origen→destino.
3. US3: dependencias, Supports, cancelaciones y ciclos.
4. US4: rebeliones, asedios y conversiones restringidas.
5. US5: desalojos, barrera de campaña y UX segura.
6. US6: orden persistido estable.
7. Phase 9: rendimiento, trazabilidad y puertas completas.

## Notes

- `[P]` solo aparece donde no existe colisión de archivo ni dependencia incompleta.
- Los tests nombrados son la suite requerida; no se crea una suite paralela de
  unitarios privados para los mismos comportamientos.
- La política externa de retiradas permanece fuera de alcance; el resolver valida
  su mapping, no elige destinos.
- No se cambia el esquema, no se añade configuración y no se conserva compatibilidad
  con `conflicts_map`, que no era contrato público.
