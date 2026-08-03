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
  la primera. `UnresolvedMilitaryConflict` recibe un `CycleDiagnostic` inmutable en
  el atributo `diagnostic`. Los errores del gestor externo que no sean ya
  `MilitaryResolutionError` se encadenan como `MilitaryResolutionError`.
- Definir `type DislodgementResolver = Callable[[MilitaryResolution],
  Mapping[UnitKey, str | None]]` y conservar exactamente la firma pública
  `MilitaryResolver(game).run(dislodgement_resolver: DislodgementResolver | None =
  None) -> MilitaryResolution`.
- Usar `@dataclass(frozen=True, slots=True)` para `UnitKey`, `MilitaryUnit`,
  `MilitaryOrder`, `ResolutionState`, `CycleDiagnostic`, `UnitOutcome` y
  `MilitaryResolution`. Sus campos y tipos son exactamente los de `data-model.md`:
  los conjuntos de
  `ResolutionState` son `frozenset` y `effective_positions` es
  `tuple[tuple[UnitKey, str | None], ...]` ordenada; no usar colecciones mutables.
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
  objetos. `CycleDiagnostic` conserva exactamente esa firma, la etapa agotada, las
  iteraciones de primera aparición/repetición y los conflictos pendientes ordenados.
- Parsear Support solo como `<lugar>` o `<lugar> (<potencia>)`, retirando los
  paréntesis para `supported_faction`; parsear Transport solo como `A <origen>` y
  resolverlo mediante `army_by_origin`. Cualquier otra gramática produce Hold
  inválido para el emisor.
- Las pruebas de `tests/machiavelli/engine/test_military.py` comprueban resultados
  públicos y snapshots completos. Solo prueban directamente los métodos privados de
  índice, compilación y firma cuando eso evita construir una campaña completa.
- Reemplazar las pruebas actuales acopladas al `MilitaryUnit` mutable y a
  `conflicts_map`; no conservarlas junto a las nuevas porque fijan el comportamiento
  que esta feature elimina.
- Reutilizar una sola factoría de escenarios y una sola función de snapshot en
  `tests/machiavelli/engine/helpers.py`; no crear una fixture o clase por regla.
- El evento militar usa `EventType.MILITARY_RESOLUTION` y un único
  `TurnEvent.military_resolution(...)`. Su `data` contiene las seis listas primitivas
  definidas en `data-model.md`; `TurnEvent.to_record()` devuelve
  `military_resolution|` más JSON compacto con claves ordenadas y Unicode sin
  escapar. Para cualquier tipo anterior devuelve exactamente `str(event.type)`.
- `Game.add_event()` añade `turn_event.to_record()` a `game.turn_events`; así los
  eventos anteriores no cambian y el militar conserva su payload. El registro se
  construye y valida antes del commit y la nueva lista `turn_events` forma parte de
  la misma asignación final que las colecciones militares.
- No implementar selección de retiradas, persistencia de retiradas ni política de
  guarniciones independientes. El callable externo debe devolver también una
  decisión explícita para cada independiente desalojada; sin gestor o entrada, el
  resolver aborta y conserva el snapshot, sin crear una colección de pendientes.
- Extraer en `machiavelli/discord.py` una función síncrona privada que abra SQLite,
  cargue `Game`, ejecute `GameEngine`, construya el reporte, guarde y devuelva
  `tuple[str, ...]`; `run_game` la invoca una sola vez con `asyncio.to_thread()`.
  Conexión, `Game`, `Player` y gestor permanecen en el worker y ninguna API Discord
  se invoca desde él.
- Traducir las excepciones militares solo en el límite Discord: todas usan el prefijo
  común de atomicidad y una orientación específica para estado inválido, ciclo,
  gestor ausente o error militar genérico. El dominio no contiene mensajes Discord.

---

## Phase 1: Setup y línea base

**Purpose**: Confirmar el estado inicial sin cambiar configuración ni dependencias.

- [X] T001 Ejecutar `python -m pytest -q tests/machiavelli/engine/test_military.py tests/machiavelli/engine/test_core.py tests/machiavelli/test_game.py` y `ruff check .` desde la raíz; registrar qué fallos ya existen antes de modificar `machiavelli/engine/military.py`

---

## Phase 2: Infraestructura de pruebas compartida

**Purpose**: Proporcionar un único constructor legible y una comparación completa
del estado militar para todas las historias.

**⚠️ CRITICAL**: Esta fase bloquea las matrices de aceptación posteriores.

- [X] T002 Añadir a `tests/machiavelli/engine/helpers.py` `create_military_game(...)`, que construya `Game` y `Player` reales con mapa inyectado, órdenes y todas las colecciones militares, y `military_snapshot(game)`, que devuelva una tupla primitiva ordenada de ejércitos, flotas, guarniciones, guarniciones independientes, asedios, rebeliones y eventos; definir además `MilitaryOrdering` como `@dataclass(frozen=True, slots=True)`, una colección acotada de variantes de orden incidental y `iter_military_orderings(factory)`, que cree un `Game` fresco por variante y pueda invertir jugadores y colecciones físicas sin alterar el orden relativo de los Advance de un mismo actor; mantener intactos los helpers usados por otras suites

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

- [X] T003 [US1] Reemplazar en `tests/machiavelli/engine/test_military.py` las pruebas de `conflicts_map` por `TestMilitaryModelsAndIndex` con subtests que verifiquen igualdad/hash de `UnitKey`, conservación de costa, índices de ejército/flota/guarnición independiente, separación provincia/`G provincia`, y `InvalidMilitaryState` para clave duplicada, ocupación provincial normalizada duplicada y dos guarniciones en la misma ciudad
- [X] T004 [US1] Añadir en `tests/machiavelli/engine/test_military.py` `TestOrderCompilation` con casos para los siete códigos `A/B/H/L/S/T/C`, Support propio `<lugar>`, Support ajeno `<lugar> (<potencia>)`, paréntesis/potencia/componentes inválidos, Transport `A <origen>` propio/ajeno y gramática inválida, Hold por ausencia de fila, Hold más `invalid_orders` para código/target/combinación inválida de actor existente, y fila huérfana posterior a compra, desbandada o cambio de propiedad cuya clave `(player_id, actor)` no existe en `actor_to_unit`; afirmar que esta última se descarta sin entrar en `invalid_orders`, sin transferirse al nuevo propietario y sin afectar a otras unidades, y que una unidad actual sin orden válida propia recibe Hold; cubrir además Advance directo `LAND`/`SEA`, conversiones, costa exacta y cero mutaciones durante índice/compilación
- [X] T005 [US1] Añadir `TestAtomicResolution` en `tests/machiavelli/engine/test_military.py` con victoria, empate, conversión ganadora/perdedora y conversión empatada contra un Advance enemigo de igual fuerza; en este último caso afirmar que ambas órdenes se cancelan, la guarnición conserva tipo y ciudad, el atacante conserva su origen y no hay ocupaciones finales duplicadas; incluir también Support no dependiente que decide fuerza, permutación de jugadores/colecciones, snapshot corrupto y fallos inyectados al construir y serializar el evento; inyectar además un `ResolutionState` incompleto devuelto por `_resolve_conflicts()` con al menos un conflicto efectivo pendiente y afirmar que `run()` lanza `MilitaryResolutionError` antes de llamar al gestor, construir o añadir el evento o sustituir colecciones; añadir en `tests/machiavelli/test_game.py` un round-trip que guarde/cargue `military_resolution|<JSON>` y recupere las seis listas; afirmar un `UnitOutcome` por unidad, evento idéntico entre permutaciones y estado/eventos iniciales intactos en cada fallo

### Implementation for User Story 1

- [X] T006 [US1] Sustituir `MilitaryUnit` mutable y añadir la jerarquía de errores, `UnitKey`, `MilitaryUnit`, `MilitaryOrder`, `ResolutionState`, `CycleDiagnostic`, `UnitOutcome`, `MilitaryResolution` y `DislodgementResolver` definidos en el contrato cerrado dentro de `machiavelli/engine/military.py`; `UnresolvedMilitaryConflict` debe exigir y conservar `diagnostic`, usar tipos modernos de Python 3.13, excepciones específicas y ningún `except` genérico silencioso
- [X] T007 [US1] Implementar `conflict_location()` y `MilitaryResolver._build_unit_index()` en `machiavelli/engine/military.py`; poblar sin sobrescrituras `units_by_key`, `actor_to_unit`, `army_by_origin` y `fleet_by_conflict_location`, validar duplicados antes de leer `player.commands` y ordenar claves mediante `(player_id or "", unit_type, origin)`
- [X] T008 [US1] Implementar `_compile_orders()` y la validación no dependiente de convoy en `_link_and_validate_orders()` dentro de `machiavelli/engine/military.py`; consultar `actor_to_unit` antes de agrupar cada fila por `(player_id, actor)`, conservar el orden relativo de las filas válidas y descartar las huérfanas sin añadirlas a `invalid_orders` ni atribuirlas a otro jugador; producir después exactamente un `MilitaryOrder` por unidad, parsear la gramática exacta de Support/Transport, validar geometría de Support con `LAND`/`SEA` y guarnición en su provincia, representar los siete códigos, aplicar Hold a toda unidad actual sin orden válida y conservar en `invalid_orders` únicamente el motivo de una orden inválida asociada a una unidad existente
- [X] T009 [US1] Implementar en `machiavelli/engine/military.py` la evaluación básica de posiciones, Advance directos, Hold, Convert y Supports válidos cuyos emisores no dependan de conflictos pendientes; separar ciudad/provincia, sumar fuerza base + Support, resolver empate de máximos y validar `UnitOutcome`; reutilizar el mismo constructor de conflictos para obtener de forma canónica las claves efectivas no incluidas en `resolved_conflicts`; construir listas finales locales y rechazar conflictos pendientes, unidad sin outcome, ejército en mar, costa inválida, convoy parcial u ocupación final duplicada mediante errores militares tipados
- [X] T010 [P] [US1] Añadir `EventType.MILITARY_RESOLUTION`, `TurnEvent.military_resolution(...)` y `TurnEvent.to_record()` en `machiavelli/events.py`; producir exactamente las seis listas primitivas de `data-model.md`, serializar solo el evento militar con prefijo `military_resolution|`, claves ordenadas, separadores compactos y `ensure_ascii=False`, y devolver `str(type)` sin payload para todos los eventos anteriores
- [X] T011 [US1] Implementar `_build_resolution()`, `_build_final_collections()`, `_apply_final_collections()` y `run()` sin desalojos en `machiavelli/engine/military.py`, y cambiar `Game.add_event()` en `machiavelli/game.py` para usar `TurnEvent.to_record()`; inmediatamente después de `_resolve_conflicts()`, validar que no queda ningún conflicto efectivo pendiente y lanzar `MilitaryResolutionError` antes de outcomes, gestor, evento o colecciones finales si la resolución está incompleta; construir y validar el registro antes del commit, incluir la nueva lista de eventos en la misma asignación final que todas las colecciones y registrar con `logging.getLogger(__name__)` el contexto reproducible sin datos sensibles

**Checkpoint**: Esta fase entrega el núcleo atómico de US1 con Support
geométricamente válido y no dependiente. La aceptación completa de US1 permanece
bloqueada por la propagación y los ciclos de US3 y por la retirada inmediata de US5;
se verifica en la puerta integrada de Phase 9.

---

## Phase 4: User Story 2 - Ejecutar un convoy encadenado y atómico (Priority: P1)

**Goal**: Compilar varios Advance de un ejército como una única ruta y moverlo solo
entre origen y destino final cuando todas las transportadoras siguen disponibles.

**Independent Test**: Un ejército, dos mares y dos flotas terminan solo en destino o
solo en origen; nunca ocupan tramos intermedios ni generan cruces de convoy.

### Tests for User Story 2

- [X] T012 [US2] Añadir `TestConvoyCompilationAndResolution` en `tests/machiavelli/engine/test_military.py` con subtests para una/dos flotas, transportadora extranjera, filas intercaladas, ruta repetida finita, T inversa correcta, T ausente/equivocada/duplicada, tramo no adyacente, destino marítimo, único Advance no terrestre, flota solo en destino, convoy opuesto a movimiento directo y transportadora atacada con cuatro resultados separados: desalojada, empate, ataque fallido y victoria defensiva; afirmar que solo el desalojo rompe el convoy, además de ruta completa, dependencias únicas, cero conflicto intermedio y ausencia de cruce

### Implementation for User Story 2

- [X] T013 [US2] Extender `_compile_orders()` en `machiavelli/engine/military.py` para convertir dos o más Advance del mismo ejército en un `MilitaryOrder(is_convoy=True, path=(origen, *targets))`; un único Advance conserva semántica directa, y cualquier combinación múltiple distinta produce Hold sin ejecutar prefijos
- [X] T014 [US2] Extender `_link_and_validate_orders()` en `machiavelli/engine/military.py` para resolver cada punto intermedio contra la flota inicial y su única orden Transport, aceptar facciones distintas, validar adyacencia de cada tramo y destino provincial, mantener repeticiones en `path` y deduplicar solo `transporters` para dependencias
- [X] T015 [US2] Integrar convoyes en la evaluación de `machiavelli/engine/military.py`: el ejército participa únicamente en el conflicto del destino final, las flotas Transport permanecen y reciben fuerza/apoyos normales, solo un `UnitOutcome` exitoso mueve origen→destino y los convoyes nunca se incluyen en la detección de cruces
- [X] T016 [US2] Propagar en `machiavelli/engine/military.py` el desalojo de cualquier transportadora a la cancelación del convoy completo y reconstruir posiciones/conflictos; conservar el convoy ante empate, ataque fallido o victoria defensiva y añadir la clave del ejército a `broken_convoys` del evento solo cuando una transportadora requerida queda desalojada

**Checkpoint**: US2 demuestra SC-001 para rutas válidas, inválidas y rotas.

---

## Phase 5: User Story 3 - Resolver dependencias y cancelaciones (Priority: P1)

**Goal**: Resolver primero conflictos independientes, recalcular tras cancelaciones y
romper círculos con las dos reglas de Support antes de declarar un ciclo irresoluble.

**Independent Test**: El desalojo de una Transport rompe el convoy y cambia los
conflictos de origen/destino; un círculo se resuelve por Support atacado, por
cancelación de todos los Supports o aborta sin commit si reaparece una firma previa.

### Tests for User Story 3

- [X] T017 [US3] Añadir `TestConflictConstructionAndSupport` en `tests/machiavelli/engine/test_military.py` con destino de una facción, disputa de dos facciones, autoconflicto, intercambio directo propio, cruce enemigo, provincia frente a ciudad, Support con facción omitida/explícita, guarnición apoyando provincia, apoyos distintos por extremo de cruce, Support cortado por ataque empatado y excepción cuando apoya el origen del atacante; añadir un escenario causal donde un conflicto independiente desaloja al emisor de un Support y, tras reconstruir globalmente, ese Support desaparece y convierte la victoria apoyada en empate o derrota, afirmando desalojo único, orden cancelada, ausencia en `active_supports`, resultado físico y evento; añadir también un autoconflicto de Convert donde una guarnición intenta convertirse en ejército en una provincia ya ocupada por otro ejército propio, y afirmar que Convert queda en `cancelled_by_self_conflict`, ambas unidades conservan sus espacios, el caso no añade una disputa entre facciones y `contested_locations` permanece exacto
- [X] T018 [US3] Añadir `TestDependencyResolution` en `tests/machiavelli/engine/test_military.py` con una cadena independiente→Transport desalojada→convoy roto, una dependencia de Support, reconstrucción global y orden de entrada permutado; afirmar que solo se resuelven claves sin dependencias pendientes y que la resolución/cancelaciones finales no dependen del orden incidental
- [X] T019 [US3] Añadir `TestCyclesAndCancellationSemantics` en `tests/machiavelli/engine/test_military.py` con ataque directo y convoy disponible contra Support desde origen distinto, ataque desde el lugar apoyado, primera etapa insuficiente, segunda etapa cancelando todos los Supports, firma consecutiva estable y firma repetida pendiente tras targeted/all; afirmar que una orden cancelada defiende físicamente pero no hace Hold, Support, Transport, Besiege, Lift siege, Convert ni somete rebelión; ejecutar el ciclo irresoluble con orden normal, jugadores/colecciones permutados y carga sucesiva, capturar `UnresolvedMilitaryConflict` y comparar por igualdad su `CycleDiagnostic`, incluidas etapa, iteraciones, conflictos pendientes ordenados y firma formada solo por valores primitivos; afirmar además snapshot/eventos intactos y ausencia de direcciones, `repr()` o hashes de proceso

### Implementation for User Story 3

- [X] T020 [US3] Implementar en `machiavelli/engine/military.py` la construcción global de posiciones y conflictos por ronda, detección de cruces solo entre Advance directos, autoconflicto salvo intercambio propio válido, `contested_locations` solo con dos o más facciones y ambos extremos de cruces, y fuerza como base + Supports activos dirigidos a facción/lugar
- [X] T021 [US3] Implementar en `machiavelli/engine/military.py` dependencias de cada conflicto sobre emisores de Support y flotas Transport situados en conflictos pendientes; resolver todas las claves independientes en orden estable y, mediante una transición que produzca un nuevo `ResolutionState`, incorporar toda unidad recién desalojada a `dislodged_units` y `cancelled_orders`, excluirla de `active_supports`, recalcular `available_convoys` y `effective_positions`, cancelar Advance/Convert perdedores, todos los máximos empatados y Supports cortados, y reconstruir el tablero completo tras cada cambio; no ocultar un Support desalojado solo en el cálculo de fuerza ni mutar colecciones compartidas
- [X] T022 [US3] Implementar en `machiavelli/engine/military.py` el desempate circular y la firma completa: primero cancelar cada Support atacado por Advance válido, activo y no cancelado desde origen distinto del lugar apoyado —directo o con convoy disponible y sin umbral de fuerza—; después cancelar todos los Supports restantes; aceptar estabilidad solo con firmas consecutivas idénticas y cero conflictos pendientes; ante cualquier firma repetida con conflictos pendientes tras targeted/all, construir `CycleDiagnostic` con etapa agotada, índices de primera aparición/repetición, conflictos pendientes ordenados y la firma canónica exacta, y lanzar `UnresolvedMilitaryConflict(diagnostic)`

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

- [X] T023 [US4] Añadir `TestRebellions` en `tests/machiavelli/engine/test_military.py` con rebelión provincial y urbana para conflicto provincial/urbano, controlador frente a otras facciones, ausencia de conflicto creado solo por rebelión, Hold explícito/por ausencia/por orden inválida, orden cancelada, Advance liberador y estado ya pacificado por gasto; afirmar modificador +1 solo a participantes provinciales elegibles y transiciones exactas de ambas listas de rebelión
- [X] T024 [US4] Añadir `TestSiegesAndRestrictedConversions` en `tests/machiavelli/engine/test_military.py` con guarnición y rebelión urbana, primer/segundo Besiege, Lift siege, asediador desalojado, flota en ciudad con/sin puerto, Convert bajo asedio o hacia ciudad rebelde y órdenes permitidas del asediador/guarnición; añadir en `tests/machiavelli/test_game.py` una regresión de `spring_maintenance()` donde `R` para `G <provincia>` rebelada no añade guarnición ni descuenta ducados, mientras la misma orden sin rebelión sí recluta y cobra 3

### Implementation for User Story 4

- [X] T025 [US4] Integrar en la fuerza provincial de `machiavelli/engine/military.py` las rebeliones provinciales y urbanas dirigidas contra el controlador; no añadir participantes ni fuerza a `G provincia`, y calcular en colecciones locales pacificación ya aplicada, sometimiento solo por Hold efectivo exitoso y liberación solo por Advance exitoso de otra facción
- [X] T026 [US4] Implementar en `machiavelli/engine/military.py` la validación y transición de Besiege/Lift siege: ciudad fortificada y objetivo presente, puerto obligatorio para flota, restricciones de órdenes bajo asedio, primer Besiege añade provincia, segundo elimina guarnición/rebelión urbana, Lift o desalojo del asediador quita provincia sin eliminar objetivo
- [X] T027 [US4] Integrar en `machiavelli/engine/military.py` las restricciones de Convert por asedio y ciudad rebelde cerrada, validar rebeliones/asedios finales y rellenar `rebellions`/`sieges` del evento; añadir en `Game.spring_maintenance()` de `machiavelli/game.py`, antes de cobrar o añadir una orden `R` de actor `G`, el rechazo cuando `unit_id in player.rebelled_cities`, sin modificar las demás reglas de reclutamiento

**Checkpoint**: US4 cubre todas las transiciones P2 de rebelión, conversión y asedio.

---

## Phase 7: User Story 5 - Conservar retiradas y lugares disputados (Priority: P2)

**Goal**: Entregar una resolución inmutable al gestor de desalojos antes de aplicar o
continuar la campaña y detener todo el turno ante gestor ausente o inválido.

**Independent Test**: Un desalojo llama una vez al gestor con identidad y espacios
disputados; solo un mapping exacto permite el commit y las fases de hambre/control
ocurren después. Cualquier fallo conserva el snapshot y produce el mensaje seguro.

### Tests for User Story 5

- [X] T028 [US5] Añadir `TestDislodgementContract` en `tests/machiavelli/engine/test_military.py` con resultado sin desalojos, gestor ausente, gestor que lanza, mapping incompleto, clave extra, destino disputado, dos retiradas al mismo destino, eliminación `None`, retirada válida y guarnición independiente desalojada; para esta última probar por separado ausencia de gestor, mapping sin su clave y decisión explícita, afirmando que los dos primeros abortan sin colección de pendientes ni cambio de snapshot y solo el tercero permite aplicar
- [X] T029 [P] [US5] Ampliar `tests/machiavelli/engine/test_core.py` con pruebas de `GameEngine(game, dislodgement_resolver=None)`, paso exacto del callable a `MilitaryResolver.run`, orden militar→retirada completada→hambre→control, y parada ante `MilitaryResolutionError`; usar un `side_effect` del resolver que sustituya las colecciones militares por un estado final reconocible y otro de `ControlManager.run` que capture las colecciones observadas, afirmando que control recibe el estado ya consolidado y nunca el snapshot militar anterior; afirmar además que attrition, control, clear_famine y spawn_plague no se invocan tras el error, sin volver a probar las reglas internas de hambre o control
- [X] T030 [P] [US5] Crear `tests/machiavelli/test_discord.py` con `unittest.IsolatedAsyncioTestCase`, `AsyncMock` y el callback real de `run_game`: probar por separado la función worker síncrona y afirmar que abre/cierra SQLite, carga, ejecuta, genera reporte, guarda y devuelve `tuple[str, ...]`; en la coroutine afirmar `interaction.response.defer(ephemeral=True)` y una sola llamada a `asyncio.to_thread()` con ruta/canal sin pasar conexión, `Game` ni `interaction`; en éxito, borrado de la respuesta diferida y publicación mediante `followup.send(..., ephemeral=False)`; en `GameNotFoundException`, edición separada; y para `InvalidMilitaryState`, `UnresolvedMilitaryConflict`, `DislodgementResolverRequired` y el error base, afirmar `logger.exception` y un mensaje efímero con el prefijo común más la orientación específica, sin followup, clase, traceback, archivo, línea ni `CycleDiagnostic`

### Implementation for User Story 5

- [X] T031 [US5] Completar en `machiavelli/engine/military.py` el flujo de desalojos de `run()`: construir `MilitaryResolution`, exigir e invocar una vez el gestor ante cualquier desalojada incluida independiente, validar mapping exacto, prohibir `contested_locations` y colisiones, aceptar `None`, combinar retiradas, construir/serializar el evento y no asignar colecciones ni eventos hasta superar todas las validaciones
- [X] T032 [P] [US5] Añadir a `GameEngine.__init__` el parámetro `dislodgement_resolver: DislodgementResolver | None = None`, guardarlo y pasarlo por nombre a `MilitaryResolver.run` en `machiavelli/engine/core.py`; no capturar `MilitaryResolutionError` en el motor para que la excepción detenga de forma natural hambre, control y cambio de estación
- [X] T033 [P] [US5] Importar `asyncio`, `logging` y la jerarquía militar, crear `logger = logging.getLogger(__name__)`, `_execute_game_turn(db_path, channel_id, *, dislodgement_resolver=None) -> tuple[str, ...]` y `_military_error_message(error) -> str` en `machiavelli/discord.py`; el worker debe abrir/cerrar SQLite, cargar, ejecutar `GameEngine`, generar reporte y guardar completamente en su hilo; ajustar `run_game` para diferir siempre con `ephemeral=True`, invocar una sola vez `await asyncio.to_thread(_execute_game_turn, ...)`, borrar la respuesta original antes de publicar el éxito con `ephemeral=False` y capturar `MilitaryResolutionError` antes del genérico usando `logger.exception` más `edit_original_response` con prefijo común y orientación por subclase; mantener `GameNotFoundException` separada y no usar `format_error_with_location` para errores militares
- [X] T034 [US5] Ejecutar `python -m pytest -q tests/machiavelli/engine/test_military.py -k "atomic or dislodg or retreat or unresolved"`, `python -m pytest -q tests/machiavelli/engine/test_core.py -k "military or dislodg or order"` y `python -m pytest -q tests/machiavelli/test_discord.py -k "run_game"`; corregir solo código de `machiavelli/engine/military.py`, `machiavelli/engine/core.py` y `machiavelli/discord.py` hasta que los tres grupos pasen

**Checkpoint**: La campaña nunca consolida un estado militar incompleto ni ejecuta
fases posteriores antes de resolver retiradas.

---

## Phase 8: User Story 6 - Preservar el orden declarado (Priority: P3)

**Goal**: Recuperar las filas por su secuencia persistida sin migración ni cambio en
guardado.

**Independent Test**: Tres Advance intercalados con dos actores y dos jugadores
mantienen la misma secuencia tras cargas repetidas y guardar-cargar-guardar.

### Tests for User Story 6

- [X] T035 [US6] Añadir a `tests/machiavelli/test_game.py` una prueba de consulta que exija literalmente `ORDER BY commands.id ASC` y una integración con `tempfile.TemporaryDirectory`, `sqlite3` y `machiavelli.database.upgrade`: insertar órdenes intercaladas de dos actores/jugadores, cargar dos veces y ejecutar guardar-cargar-guardar; afirmar igualdad de `(actor, command, target)` por jugador y ausencia de migración nueva

### Implementation for User Story 6

- [X] T036 [US6] Cambiar únicamente el `SELECT` de `Command.load_commands()` en `machiavelli/game.py` para añadir `ORDER BY commands.id ASC`; no modificar `Command.save()`, `Player.save_commands()`, `machiavelli/database.py`, `_SCHEMA_VERSION` ni `_UPGRADES`
- [X] T037 [US6] Ejecutar `python -m pytest -q tests/machiavelli/test_game.py -k "command and order"` y `python -m pytest -q tests/machiavelli/engine/test_military.py -k "compile or convoy"`; confirmar que la ruta compilada conserva el orden relativo después del round-trip

**Checkpoint**: US6 cumple FR-007/FR-053 usando el `id` existente.

---

## Phase 9: Rendimiento, auditoría y puertas finales

**Purpose**: Verificar el presupuesto aprobado y la cobertura integrada sin añadir
microbenchmarks ni pruebas duplicadas.

- [X] T038 Añadir `build_representative_game()`, `test_representative_resolution_determinism` y `test_representative_resolution_budget` en `tests/machiavelli/engine/test_military.py` con exactamente 30 unidades, 60 filas, 20 lugares de conflicto, convoy de 5 flotas y al menos dos desalojos; preparar un mapping inmutable y un gestor determinista que retire una unidad a destino válido y elimine otra con `None`; en la prueba funcional construir cinco `Game` frescos y afirmar igualdad exacta de firma, `MilitaryResolution`, evento y snapshot final sin límite temporal; en la prueba temporal, condicionada a `MACHIAVELLI_REFERENCE_PERF=1`, construir escenario/decisiones antes del cronómetro, medir solo `MilitaryResolver.run(gestor)` y exigir menos de 1 segundo por cada ejecución —no promedio—; incluir duración, máximo, `platform.python_version()`, `platform.platform()`, `platform.machine()` y `os.cpu_count()` en fallos; documentar la puerta en `.github/workflows/military-performance.yml` con Ubuntu 24.04, CPython 3.13, job dedicado, sin cobertura ni paralelismo
- [X] T039 Añadir `TestIntegratedMilitaryAcceptance` en `tests/machiavelli/engine/test_military.py` usando la factoría y `iter_military_orderings(...)`: construir una campaña compacta que combine movimientos relacionados, Support dependiente, Convert, convoy válido o roto, al menos una cancelación, una rebelión sometida o liberada, un asedio iniciado/levantado/completado, un lugar disputado y una unidad desalojada resuelta por un gestor determinista; ejecutar cada variante sobre un `Game` fresco, sin alterar el orden relativo de los Advance de un mismo actor, y comparar por igualdad `MilitaryResolution`, las seis listas del evento y `military_snapshot(game)`; afirmar un único resultado por unidad, una única aplicación final, retirada completada y ausencia de estados intermedios observables. Esta tarea constituye la puerta de aceptación completa de US1 y la cobertura integrada de SC-002 para cancelaciones, asedios, rebeliones, lugares disputados y retiradas
- [X] T040 Ejecutar todos los comandos y comprobar todos los resultados esperados de `specs/001-resolver-ordenes-encadenadas/quickstart.md`; si un selector `-k` no recoge una prueba prevista, renombrar esa prueba en `tests/machiavelli/engine/test_military.py`, `tests/machiavelli/engine/test_core.py`, `tests/machiavelli/test_game.py` o `tests/machiavelli/test_discord.py` sin duplicarla

**Trazabilidad de aceptación de US1**:

> Aclaración US3: estabilidad requiere dos firmas consecutivas idénticas y cero
> conflictos pendientes; una firma repetida pendiente tras targeted/all es deadlock.

| Escenario | Cobertura |
|-----------|-----------|
| Una orden lógica por unidad y sustitución única | T005, T011, T039 |
| Resultado idéntico bajo orden incidental diferente | T039 |
| Snapshot inválido o ciclo irresoluble sin cambios | T003, T019 |

- [X] T041 Revisar `tests/machiavelli/engine/test_military.py`, `tests/machiavelli/test_game.py`, `tests/machiavelli/engine/test_core.py` y `tests/machiavelli/test_discord.py` contra FR-001–FR-053, NFR-001–NFR-007 y SC-001–SC-009; confirmar cobertura explícita de Convert ganador, perdedor, empatado y cancelado por autoconflicto, filas huérfanas, Support emitido por una unidad desalojada con efecto causal, rechazo pre-commit de conflictos pendientes, aceptación integrada de US1, invariancia de cancelaciones/asedios/rebeliones/lugares disputados/retiradas, estado observado por control, `CycleDiagnostic` reproducible, mensajes accionables y frontera `asyncio.to_thread`; revisar además que no exista `deepcopy(Game)` ni copia completa equivalente por iteración, que los estados usen `slots` y colecciones inmutables, que firmas/diagnósticos contengan valores primitivos, que solo se retengan firmas únicas necesarias y que SQLite/`Game` no crucen el worker; eliminar solo pruebas obsoletas del flujo mutable y confirmar cobertura única por la matriz más cercana, sin duplicar preparación
- [X] T042 Ejecutar `python -m pytest -q` y `ruff check .`; en el job de referencia ejecutar además `MACHIAVELLI_REFERENCE_PERF=1 python -m pytest -q tests/machiavelli/engine/test_military.py -k "representative_resolution_budget"`; corregir todos los fallos en `machiavelli/engine/military.py`, `machiavelli/engine/core.py`, `machiavelli/events.py`, `machiavelli/game.py`, `machiavelli/discord.py`, el workflow de rendimiento y sus cinco archivos de prueba, sin debilitar asserts, ampliar alcance ni añadir dependencias

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
2. Completar el núcleo técnico de US1 (T003–T011).
3. Ejecutar su checkpoint y detenerse solo si se necesita una demostración interna de
   atomicidad básica; no declarar aceptada US1 hasta completar US3, US5 y T039.

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
- La aceptación completa de US1 ocurre en T039; los checkpoints anteriores validan
  incrementos técnicos y no sustituyen sus tres escenarios de aceptación.
