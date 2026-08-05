# Especificación de feature: Eventos de turno y reglas de escenario

**Feature Branch**: `codex/turn-events-rules-spec`

**Created**: 2026-08-04

**Status**: Draft

**Input**: Sustituir los mensajes construidos durante la ejecución por eventos de
turno abstractos, persistir su tipo y datos, generar su representación legible para
Discord fuera del motor, corregir los límites entre Discord, servicios, persistencia
y motor, y aplicar las reglas activas del escenario.

## Clarifications

### Session 2026-08-04

- Q: ¿Cuándo se genera hambre? → A: En setup solo si `famine_active` y
  `first_turn_famine` están activas; en campañas con `season == 0` si
  `famine_active` está activa; mantenimiento nunca genera hambre.
- Q: ¿Las fortalezas activas reciben guarniciones independientes automáticamente?
  → A: No; solo las ciudades `fortified` las reciben en setup. Una `fortress` activa
  puede recibir guarnición posteriormente.
- Q: ¿Qué ocurre si el escenario declara una guarnición en una fortaleza inactiva?
  → A: El setup aborta con un error claro de configuración.
- Q: ¿Qué ocurre con un evento persistido inválido? → A: La carga o el reporte
  abortan con un error tipado que identifica la fila y el tipo.
- Q: ¿Cuándo se sustituye la tabla histórica `game_events`? → A: Durante la
  actualización canónica del esquema se elimina y recrea la tabla sin convertir
  filas.
- Q: ¿Qué ocurre con los métodos históricos que duplican la ejecución? → A: Se
  eliminan completamente cuando no tengan consumidores productivos.
- Q: ¿Cuándo se valida el payload de un evento? → A: Al crear el evento y al
  reconstruirlo desde persistencia, usando el mismo contrato.
- Q: ¿Qué tiradas conservan los eventos de hambre y plaga? → A: Solo la tirada de
  severidad y las provincias finales; las tiradas auxiliares pueden registrarse a
  nivel `INFO` cuando sean necesarias para diagnóstico.
- Q: ¿Cuánto detalle muestra la resolución militar? → A: Una línea por resultado,
  agrupada por categoría, omitiendo únicamente categorías vacías.
- Q: ¿Cuándo se reemplaza el historial anterior? → A: Solo después de que ejecución,
  validación, reporte y guardado hayan concluido correctamente.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Producir un historial de turno estructurado (Priority: P1)

Como mantenedor del juego, quiero que cada cambio relevante del turno se registre
como un evento tipado con datos estructurados, para poder conservar y reutilizar el
resultado sin depender de un texto preparado para un canal concreto.

**Why this priority**: Es el contrato del que dependen tanto la persistencia como
los reportes y elimina la mezcla actual de objetos, nombres de evento y Markdown.

**Independent Test**: Puede ejecutarse un turno de inicio, uno de mantenimiento y
uno de campaña y comprobar que el historial contiene exclusivamente eventos del
catálogo, en orden, con payloads JSON válidos y sin texto de presentación.

**Acceptance Scenarios**:

1. **Given** una fase que cambia el estado del juego, **When** termina cada acción
   relevante, **Then** se añade un evento con un tipo conocido y únicamente los
   datos de dominio necesarios para describir el resultado.
2. **Given** cualquier camino histórico que hoy añade una cadena al historial,
   **When** se ejecuta tras el cambio, **Then** produce un evento estructurado
   equivalente y no construye Markdown, menciones ni frases de Discord.
3. **Given** una resolución que falla antes de consolidarse, **When** se revierte el
   estado de la fase, **Then** tampoco queda persistido ningún evento parcial de esa
   resolución.

---

### User Story 2 - Leer un reporte de turno comprensible en Discord (Priority: P1)

Como participante, quiero ver una descripción legible y contextual de cada evento
junto al reporte de situación, para entender qué ocurrió sin conocer los códigos
internos del motor.

**Why this priority**: Un historial estructurado no aporta valor al jugador si el
canal público muestra solo nombres técnicos o JSON.

**Independent Test**: Puede entregarse al generador un evento válido de cada tipo y
comprobar que todos producen al menos una línea legible, con nombres de potencias,
provincias y unidades cuando exista ese contexto.

**Acceptance Scenarios**:

1. **Given** los eventos persistidos del último turno, **When** se solicita el
   reporte, **Then** se presentan en el mismo orden, traducidos a descripciones en
   español y seguidos del reporte de situación vigente.
2. **Given** un evento que referencia identificadores de jugador, potencia,
   provincia o unidad, **When** se representa para Discord, **Then** se usan el
   nombre o mención públicos correspondientes y no se expone el JSON crudo.
3. **Given** un evento militar agregado, **When** se representa, **Then** quedan
   descritos sus movimientos o conversiones, cancelaciones, convoyes rotos,
   desalojos, cambios de rebelión y cambios de asedio sin perder ningún resultado.
4. **Given** un tipo desconocido o datos que incumplen su contrato, **When** se
   intenta cargar o representar, **Then** el fallo queda identificado de forma
   explícita y el evento no se omite silenciosamente.

---

### User Story 3 - Conservar eventos sin conservar presentación (Priority: P1)

Como operador, quiero que el historial efímero del turno guarde por separado el
tipo y los datos JSON de cada evento, para reconstruirlo fielmente y cambiar la
presentación sin reescribir el motor ni interpretar textos antiguos.

**Why this priority**: La tabla actual guarda mensajes y pierde los payloads de casi
todos los eventos; eso impide generar reportes fiables después de recargar.

**Independent Test**: Puede guardarse y recargarse un evento de cada contrato y
comparar tipo, payload, orden y valores JSON con los originales.

**Acceptance Scenarios**:

1. **Given** un turno con varios eventos, **When** se guarda la partida, **Then**
   cada fila contiene el tipo estable y los datos serializados como JSON, ligados a
   la partida y en el orden de emisión.
2. **Given** una partida recargada, **When** se consulta su último turno, **Then** se
   reconstruye la misma secuencia de eventos tipados y se genera el mismo contenido
   legible.
3. **Given** una instalación cuya tabla aún contiene la columna histórica de
   mensajes, **When** se adopta el nuevo contrato, **Then** la tabla efímera se
   reinicia vacía sin intentar convertir ni conservar sus filas anteriores.

---

### User Story 4 - Respetar los límites de aplicación (Priority: P2)

Como mantenedor, quiero que el adaptador de Discord solo gestione interacciones y
envíos, para que la apertura de base de datos, los repositorios, la ejecución del
turno y la presentación del dominio tengan propietarios claros y comprobables.

**Why this priority**: Discord abre conexiones directamente y conoce dependencias
internas del motor, lo que duplica responsabilidades y filtra decisiones técnicas
entre capas.

**Independent Test**: Puede invocarse el comando de turno usando solo la interfaz
de aplicación y comprobar que la sesión de persistencia nace, se usa y se cierra en
el mismo worker, mientras Discord recibe únicamente líneas inmutables o una
excepción pública.

**Acceptance Scenarios**:

1. **Given** cualquier comando de Discord que necesite datos, **When** se ejecuta,
   **Then** obtiene un servicio de aplicación mediante el gestor canónico de base de
   datos y no crea conexiones ni repositorios directamente.
2. **Given** la ejecución síncrona de un turno, **When** Discord la delega a un
   worker, **Then** conexión, carga, motor, reporte y guardado permanecen en ese
   worker y la conexión se cierra incluso si ocurre un error.
3. **Given** una campaña con posibles desalojos, **When** se inicia desde Discord o
   desde el servicio de juego, **Then** ninguna de esas capas recibe ni reenvía un
   resolvedor de desalojos; esa política pertenece exclusivamente al motor.
4. **Given** que la gestión de retiradas aún no está implementada, **When** aparece
   un desalojo que la requiere, **Then** el motor conserva su fallo tipado y atómico
   sin exponer una dependencia incompleta como parámetro público.

---

### User Story 5 - Aplicar las reglas activas del escenario (Priority: P1)

Como participante, quiero que las mecánicas habilitadas por el escenario gobiernen
todas las fases del turno, para que una regla desactivada no produzca recursos,
acciones, unidades, desastres ni eventos residuales.

**Why this priority**: Las reglas ya forman parte del escenario, pero varias fases
las ignoran o solo las aplican en algunos caminos.

**Independent Test**: Puede ejecutarse la misma situación dos veces, alternando una
sola regla, y verificar que solo aparecen el estado y los eventos permitidos por esa
regla.

**Acceptance Scenarios**:

1. **Given** `fortress_active=false`, **When** se evalúa una provincia cuyo tipo de
   ciudad es `fortress`, **Then** se comporta como si no tuviera ciudad: no admite
   guarnición, conversión, rebelión urbana ni asedio.
2. **Given** `fortress_active=true`, **When** se evalúa una fortaleza, **Then** puede
   alojar guarniciones y participar en conversiones, rebeliones urbanas y asedios,
   pero nunca genera ingreso urbano ni permite reclutar una unidad allí; el setup no
   le asigna automáticamente una guarnición independiente.
3. **Given** `assassinations_active=false`, **When** se prepara y ejecuta una
   partida, **Then** no se reparten fichas de asesinato ni se ejecuta la fase de
   asesinatos.
4. **Given** `famine_active=false`, **When** transcurre cualquier turno, **Then** no
   se alivia, genera, resuelve ni limpia hambre y no se emiten eventos de hambre.
5. **Given** `famine_active=true` y `first_turn_famine=false`, **When** se ejecuta el
   inicio de partida, **Then** no se genera hambre inicial; una campaña posterior
   con `season == 0` sí puede generarla.
6. **Given** `famine_active=true` y `first_turn_famine=true`, **When** se ejecuta el
   inicio de partida, **Then** se realiza una única generación de hambre inicial;
   el mantenimiento posterior no realiza ninguna.
7. **Given** una campaña con `season == 0`, **When** `famine_active=true`, **Then**
   genera hambre una sola vez; cualquier otra campaña o mantenimiento no la genera.
8. **Given** `plague_active=false`, **When** llega la fase estacional de plaga,
   **Then** no se genera plaga, no mueren unidades por ella y no se emiten eventos
   de plaga.

### Edge Cases

- Un evento con `data={}` sigue siendo válido solo cuando su contrato lo permita;
  la serialización nunca convierte `None`, listas o booleanos en texto informal.
- Un `military_resolution` con las seis colecciones vacías sigue siendo válido y se
  representa mediante una única línea `Sin cambios militares.`, sin encabezados de
  categorías vacías.
- Los eventos repetidos son válidos y conservan su orden; no se deduplican por tipo
  ni por payload.
- Los identificadores desconocidos se muestran como códigos de dominio con Markdown
  y menciones neutralizados; valores como `@everyone`, `<@123>`, backticks, asteriscos
  o guiones bajos nunca generan menciones ni formato activo. Un payload incompleto o
  con forma incorrecta se considera corrupto.
- Un jugador nulo en un evento de desastre identifica una guarnición independiente,
  no un jugador desconocido.
- Las cabeceras del turno, la fecha, el siguiente plazo y los títulos de fase se
  derivan del contexto del reporte; no se guardan como falsos eventos de dominio.
- Una lista vacía de afectados no genera un evento de desastre ni un evento de
  control sin cambios.
- `famine_active=false` tiene precedencia sobre `first_turn_famine=true`.
- Solo una ciudad `fortified` no controlada recibe una guarnición independiente
  automática en setup. Una `fortress` activa puede recibirla después mediante las
  acciones permitidas, pero nunca comienza con una por esta regla.
- Una configuración inicial incompatible con `fortress_active=false` falla de forma
  explícita antes de consolidar el turno, en lugar de ignorar una guarnición ilegal.
- La desactivación de una regla no cambia el orden relativo de las demás fases.

## Requirements *(mandatory)*

### Functional Requirements

#### Contrato de eventos

- **FR-001**: El historial activo de una partida DEBE contener exclusivamente
  eventos con un tipo del catálogo y un objeto de datos compatible con ese tipo.
  Tras la construcción, el evento y todo su árbol de payload DEBEN ser inmutables:
  no se pueden reasignar `type` ni `data`, el constructor copia defensivamente la
  entrada y ningún consumidor puede alterar diccionarios o listas anidadas ya
  validados.
- **FR-002**: El motor y el dominio DEBEN registrar hechos y resultados de juego sin
  generar Markdown, menciones, emojis, títulos ni frases dependientes de Discord.
- **FR-003**: Todos los productores canónicos de inicio, ingresos o mantenimiento
  DEBEN producir eventos estructurados equivalentes o dejar de registrar aquello
  que solo era presentación; los métodos históricos duplicados sin consumidores
  productivos DEBEN eliminarse, no mantenerse como un segundo algoritmo.
- **FR-004**: La secuencia de eventos DEBE conservar exactamente el orden de emisión
  y DEBE reemplazarse al comenzar el siguiente turno conforme al comportamiento
  efímero vigente.
- **FR-005**: Cada turno DEBE construir un historial nuevo en memoria y reemplazar
  el persistido solo después de completar ejecución, validación, reporte y guardado;
  cualquier fallo DEBE conservar el historial anterior y no dejar eventos parciales.
- **FR-006**: Cada tipo emitido DEBE tener un único contrato de payload documentado;
  no DEBEN coexistir representaciones antiguas en texto o `tipo|json`.
- **FR-007**: Los tipos declarados sin productor ni significado actual no DEBEN
  formar parte del contrato público; en particular, `bribe_set` se elimina mientras
  no exista un hecho de dominio que lo emita.

#### Catálogo y payloads

La siguiente tabla es el contrato completo requerido. `string|null` y las listas se
serializan como valores JSON nativos. Los identificadores conservan los códigos
canónicos actuales del juego.

| Tipo | Payload `data` |
|------|----------------|
| `start_game` | `{scenario: string}` |
| `start_game_power_assigned` | `{player_id: string, discord_id: integer\|null, power_id: string}` |
| `start_season` | `{year: integer, season: integer}` donde `season` conserva el índice estacional canónico |
| `famine_spawn` | `{severity_roll: integer, provinces: string[]}` con tirada entre 1 y 6 |
| `famine_relief` | `{player: string, province: string}` |
| `famine_attrition` | `{player: string\|null, units: string[]}` |
| `famine_end` | `{provinces: string[]}` |
| `plague_spawn` | `{severity_roll: integer, provinces: string[]}` con tirada entre 1 y 6 |
| `plague_death` | `{player: string\|null, units: string[]}` |
| `rebellion_pacify` | `{player: string, province: string, kind: "province"\|"city"}` |
| `rebellion_province` | `{player: string, province: string}` |
| `rebellion_city` | `{player: string, province: string}` |
| `expense` | `{player: string, expense: string, target: string\|null, amount: integer\|string}` |
| `expense_no_funds` | `{player: string, expense: string, target: string\|null, amount: integer\|string}` |
| `expense_syntax_error` | `{player: string, expense: string, target: string\|null, amount: integer\|string}` |
| `bribe_executed` | `{player: string, expense: string, target: string, amount: integer}` |
| `income_collected` | `{player: string, provinces: string[], province_income: integer, cities: string[], city_income: integer, variable_income: VariableIncome[], total_income: integer}` |
| `maintenance_order_resolved` | `{player: string, actor: string, order: "D"\|"M"\|"R", target: string\|null, result: MaintenanceResult, cost: integer}` |
| `maintenance_summary` | `{player: string, initial_ducats: integer, expenses: integer, remaining_ducats: integer}` |
| `get_control` | `{player: string, provinces: string[]}` |
| `lose_control` | `{player: string, provinces: string[]}` |
| `get_home_country` | `{player: string, home_country: string}` |
| `lose_home_country` | `{player: string, home_country: string}` |
| `player_eliminated` | `{player: string}` |
| `player_won` | `{player: string, cities: integer, home_countries: integer}` |
| `military_resolution` | `{outcomes: Outcome[], cancelled_orders: UnitKey[], broken_convoys: UnitKey[], dislodgements: UnitKey[], rebellions: RebellionTransition[], sieges: SiegeTransition[]}` |

`VariableIncome` contiene `{source_type: "home_country"|"province", source: string,
roll: integer, amount: integer}`. `MaintenanceResult` admite únicamente
`disbanded`, `unit_not_found`, `maintained`, `disbanded_no_funds`, `recruited`,
`recruitment_no_funds`, `invalid_home_or_control`, `space_occupied`,
`port_required`, `rebelled_city` y `fortified_city_required`.

`UnitKey` es `[player|null, unit_type, origin]`; `Outcome` es
`[UnitKey, final_unit_type, final_location|null, dislodged]`;
`RebellionTransition` es `[player|null, kind, province, transition]`; y
`SiegeTransition` es `[UnitKey, province, transition]`. Se conservan las validaciones
y el orden canónico del evento militar vigente.

- **FR-008**: `income_collected` DEBE reunir en un único evento por jugador todas
  las fuentes y resultados necesarios para explicar y auditar su ingreso del turno.
- **FR-009**: Cada orden de mantenimiento intentada DEBE producir exactamente un
  `maintenance_order_resolved`, con un resultado cerrado y un coste que permita
  distinguir éxito, rechazo y disolución por falta de fondos.
- **FR-010**: Una reducción efectiva de hambre pagada DEBE producir
  `famine_relief`; pagar una orden que no reduce hambre no DEBE fingir ese efecto.
- **FR-011**: Los eventos de rebelión DEBEN identificar tanto el propietario
  afectado como si la rebelión pacificada era provincial o urbana.

#### Presentación del turno

- **FR-012**: Un servicio de reporte DEBE transformar cada evento conocido en una o
  más líneas legibles para Discord usando el contexto de la partida, sin modificar
  el evento ni el estado del juego.
- **FR-013**: El reporte DEBE incluir cabecera de partida y turno, estación y año,
  eventos del turno y reporte de situación, manteniendo ese orden general.
- **FR-014**: El servicio de reporte DEBE resolver nombres de potencias,
  localizaciones, unidades y usuarios a partir de identificadores estructurados. Si
  no existe un nombre público, DEBE mostrar el código neutralizando Markdown y
  menciones mediante `discord.utils.escape_markdown(..., as_needed=False)` seguido
  de `discord.utils.escape_mentions(...)`; solo un `discord_id` conocido PUEDE
  producir una mención `<@...>` real.
- **FR-015**: Todos los tipos del catálogo DEBEN producir una descripción no vacía;
  un tipo o payload inválido DEBE abortar la carga o el reporte mediante un error
  tipado que identifique la fila y el tipo, y nunca desaparecer silenciosamente.
- **FR-016**: El reporte militar DEBE cubrir las seis colecciones del payload y no
  limitarse a mostrar el nombre `military_resolution`; DEBE producir una línea por
  resultado agrupada por categoría y omitir únicamente las categorías vacías. Si
  las seis colecciones están vacías, DEBE producir una única línea
  `Sin cambios militares.`.
- **FR-017**: El envío a Discord DEBE conservar el mecanismo vigente de división en
  mensajes compatibles con el límite del canal.

#### Persistencia y límites

- **FR-018**: Cada fila del historial DEBE almacenar `game_id`, tipo de evento y
  payload JSON en campos separados, además de su identificador secuencial.
- **FR-019**: El mismo contrato de payload DEBE validarse al crear cada evento y al
  reconstruirlo desde persistencia; guardar y recargar DEBE conservar tipo, datos y
  orden, incluidos caracteres no ASCII, valores nulos, booleanos y listas anidadas.
- **FR-020**: La actualización canónica del esquema DEBE eliminar y recrear la tabla
  efímera histórica sin migrar el contenido de `message`.
- **FR-021**: La sustitución de estado de partida y eventos DEBE seguir siendo
  atómica dentro de la transacción del turno.
- **FR-022**: El adaptador de Discord NO DEBE abrir conexiones de base de datos,
  construir repositorios ni importar la biblioteca de persistencia concreta.
- **FR-023**: La creación y cierre de la sesión usada por los servicios DEBE
  centralizarse en las capas de servicios y base de datos ya canónicas.
- **FR-024**: Las operaciones bloqueantes de conexión, carga, ejecución, reporte y
  guardado DEBEN permanecer juntas fuera del bucle de eventos de Discord.
- **FR-025**: Los puntos de entrada de Discord y del servicio de juego NO DEBEN
  aceptar ni propagar un resolvedor de desalojos.
- **FR-026**: Hasta que exista una política interna de retiradas, el motor DEBE
  mantener el fallo tipado y la reversión completa cuando una resolución la
  requiera.

#### Reglas del escenario

- **FR-027**: Las reglas omitidas en un escenario DEBEN conservar el valor activo
  por defecto para compatibilidad, incluida la nueva regla `first_turn_famine`.
- **FR-028**: El motor DEBE consultar las reglas del escenario antes de entrar en
  cada mecánica opcional y no solo dentro de un efecto secundario tardío.
- **FR-029**: Con `fortress_active=false`, una localización `fortress` DEBE ser
  equivalente a `city=null` para setup, guarniciones, conversiones, rebeliones y
  asedios.
- **FR-030**: Con `fortress_active=true`, una `fortress` DEBE admitir guarniciones,
  conversiones, rebeliones urbanas y asedios según las mismas restricciones de una
  plaza defendible.
- **FR-031**: Una `fortress`, activa o no, NO DEBE contar como ciudad para ingresos,
  control de país natal, victoria ni reclutamiento.
- **FR-032**: El setup DEBE crear guarniciones independientes automáticas solo en
  ciudades `fortified` no asignadas. Una `fortress` activa PUEDE recibir guarnición
  después del setup; una guarnición inicial declarada en una `fortress` inactiva
  DEBE abortar el setup con un error de configuración.
- **FR-033**: Con `assassinations_active=false`, el setup DEBE dejar vacías las
  fichas de asesinato y la campaña DEBE omitir por completo el resolvedor de
  asesinatos.
- **FR-034**: Con `famine_active=false`, el motor DEBE omitir reducción pagada,
  atrición, generación y limpieza de hambre en todos los turnos.
- **FR-035**: `first_turn_famine` DEBE gobernar exclusivamente la generación de
  hambre del setup con `turn_number == 0` y solo PUEDE tener efecto si
  `famine_active=true`.
- **FR-036**: Con `famine_active=true`, el setup DEBE generar hambre una sola vez si
  `first_turn_famine=true`, y cada campaña DEBE generarla una sola vez únicamente
  cuando `season == 0`; mantenimiento nunca DEBE generar hambre.
- **FR-037**: Con `plague_active=false`, el motor DEBE omitir la generación de plaga
  y, por tanto, cualquier muerte o evento derivado de ella.
- **FR-038**: Desactivar una mecánica NO DEBE emitir eventos que afirmen que dicha
  mecánica se ejecutó.

### Key Entities

- **TurnEvent**: Hecho profundamente inmutable del turno compuesto por un tipo
  estable y un árbol JSON congelado conforme al catálogo. La entrada se copia y se
  convierte recursivamente a mappings de solo lectura y tuplas; la serialización
  vuelve a materializar objetos y listas JSON nativos.
- **Event Type Contract**: Define la forma, valores permitidos y significado del
  payload para un tipo de evento.
- **Turn Event Record**: Representación persistida y ordenada de un evento asociada
  a una partida; no contiene texto de presentación.
- **Turn Report**: Composición legible de contexto del turno, descripciones de
  eventos y situación posterior.
- **Scenario Rules**: Interruptores de mecánicas que determinan qué fases y acciones
  pueden producir estado y eventos.

## Assumptions and Dependencies

- El historial de `game_events` es efímero y solo se reemplaza al completar
  correctamente un turno; no se conserva ni convierte el texto ya almacenado cuando
  cambie su esquema.
- Las reglas ausentes en el JSON de escenario valen `true`. Esto incluye
  `first_turn_famine`, y `famine_active=false` siempre prevalece sobre ella.
- La generación posterior de hambre ocurre exclusivamente en campañas con
  `season == 0`; `first_turn_famine` solo añade o suprime la generación del setup y
  mantenimiento nunca genera hambre.
- Las cabeceras, fechas, plazos y títulos son contexto del reporte, no eventos de
  dominio.
- Un único valor `TurnEvent` con contratos explícitos es suficiente; no se requieren
  subclases por tipo mientras no aporten validación o comportamiento propio.
- Los eventos de hambre y plaga conservan la tirada de severidad y las provincias
  finales. Las tiradas auxiliares de selección no forman parte del payload y pueden
  registrarse a nivel `INFO` cuando se necesiten para diagnóstico.
- La resolución de asesinatos todavía no produce efectos y, por tanto, esta feature
  no inventa eventos de asesinato; sí respeta la activación de la fase y el reparto
  de fichas.
- La implementación completa de retiradas queda fuera de alcance. Esta feature solo
  elimina su filtración a Discord y servicios y conserva la barrera atómica actual.

## Out of Scope

- Implementar decisiones o interfaz de usuario para retiradas tras un desalojo.
- Implementar la mecánica de asesinatos que hoy está vacía.
- Conservar o transformar mensajes históricos de turnos anteriores al nuevo esquema.
- Añadir formatos de salida distintos de la representación actual para Discord.
- Añadir tipos de evento especulativos sin un productor actual.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: El 100% de los caminos de inicio, mantenimiento y campaña dejan un
  historial compuesto solo por eventos del catálogo; ninguna prueba encuentra
  cadenas de presentación en el historial activo.
- **SC-002**: El 100% de los tipos emitidos genera al menos una descripción legible
  y el evento militar refleja las seis colecciones de resultados.
- **SC-003**: Una muestra que cubra todos los tipos sobrevive a 10 ciclos consecutivos
  de guardar y recargar sin cambiar tipo, payload ni orden.
- **SC-004**: Las cinco reglas producen el comportamiento esperado en ambos valores
  y las combinaciones `famine_active/first_turn_famine` cubren sus cuatro casos sin
  fases ni eventos residuales.
- **SC-005**: La ejecución completa del turno desde Discord mantiene el bucle de
  interacción disponible y cierra el 100% de las sesiones tanto en éxito como en
  error.
- **SC-006**: Ningún punto de entrada externo al motor requiere conocer o proporcionar
  una política de desalojos.
- **SC-007**: Para los escenarios y turnos donde las cinco reglas siguen activas,
  incluido `first_turn_famine=true`, el estado final del juego permanece
  funcionalmente equivalente al comportamiento previo, incluida la generación
  inicial de hambre.
