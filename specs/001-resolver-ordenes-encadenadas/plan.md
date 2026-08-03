# Implementation Plan: Resolución militar atómica

**Branch**: `001-resolver-ordenes-encadenadas` | **Date**: 2026-08-02 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from
`/specs/001-resolver-ordenes-encadenadas/spec.md`

## Summary

Sustituir la ejecución incremental de filas `Command` por un adjudicador que toma un
snapshot militar, compila una orden lógica inmutable por unidad, valida convoyes y
dependencias, resuelve primero conflictos independientes y aplica un único estado
final junto con su registro auditable. Las órdenes encadenadas de un ejército forman un convoy atómico; las
cancelaciones nunca se convierten en Hold; los apoyos, rebeliones, asedios,
conversiones, cruces y desalojos se recalculan hasta obtener un resultado
determinista.

La implementación reutiliza el módulo y las estructuras actuales: dataclasses
tipadas, diccionarios, tuplas y conjuntos de la biblioteca estándar. No añade una
librería de grafos ni cambia el esquema. Un contrato síncrono entrega los desalojos
y lugares disputados a un gestor externo; si ese gestor no existe o falla, el
resolver no aplica el estado militar ni permite continuar la campaña. La operación
síncrona completa de carga SQLite, motor, reporte y guardado se ejecuta en un worker
de biblioteca estándar para no bloquear el event loop de Discord.

## Technical Context

**Language/Version**: Python 3.13 o superior

**Primary Dependencies**: Biblioteca estándar (`asyncio`, `dataclasses`,
`collections`, `logging`, `os`, `platform`, `time`, `typing`), `discord.py`
existente; sin nuevas dependencias de runtime

**Storage**: SQLite existente para partidas, jugadores, órdenes y eventos; listas de
estado militar en `Game` y `Player`; sin cambio de esquema ni migración

**Testing**: Suite existente ejecutada con `pytest`, pruebas `unittest` y mocks;
`ruff check .` como puerta de calidad

**Target Platform**: Bot de Discord y motor de dominio ejecutado como proceso Python

**Project Type**: Paquete Python único con motor de dominio, persistencia SQLite y
adaptador Discord

**Performance Goals**: Resolver en menos de 1 segundo una campaña con 30 unidades,
60 filas de orden, 20 lugares de conflicto, un convoy de 5 transportadoras y dos
desalojos —una retirada y una eliminación— en el job dedicado de referencia con
Ubuntu 24.04 y CPython 3.13; verificar el determinismo funcional en cualquier entorno

**Constraints**: Resultado determinista, aplicación militar atómica, líneas de 88
caracteres, costas exactas conservadas, sin movimientos parciales, sin dependencia
del orden incidental, sin activar desalojos sin gestor y sin ejecutar carga, motor o
guardado síncronos directamente en el event loop de Discord

**Scale/Scope**: Un tablero cargado en memoria; recalculado global por iteración. El
coste se acota por unidades, órdenes, conflictos y firmas de estado observadas. El
resolver no realiza `deepcopy(Game)`, no conserva snapshots completos de jugadores
por ronda y retiene únicamente las firmas únicas necesarias para detectar estabilidad
o ciclos

## Constitution Check

*GATE inicial: aprobado. Se reevalúa después del diseño de Phase 1.*

- [x] Las reglas, snapshots, evaluación y aplicación permanecen en `machiavelli/`.
      Discord y SQLite son límites; el resultado militar emite un `TurnEvent`
      determinista y registra contexto técnico sin datos sensibles.
- [x] El plan añade pruebas para carga ordenada, todas las reglas modificadas,
      errores, atomicidad, orden de campaña y regresiones de mutación incremental.
- [x] `run_game` mantiene confirmación pública de éxito, difiere la interacción,
      ejecuta fuera del event loop la transacción síncrona completa y traduce cada
      categoría de fallo militar a un mensaje efímero, accionable y sin detalles
      internos.
- [x] No hay cambio de esquema: `commands.id` ya existe y solo se usa para ordenar.
      Por tanto, migración, rollback de migración y prueba de migración no aplican.
- [x] La carga representativa incluye retiradas reales; el determinismo se verifica
      en cualquier entorno y el presupuesto de menos de 1 segundo se aplica solo al
      job dedicado de referencia definido.

## Project Structure

### Documentation (this feature)

```text
specs/001-resolver-ordenes-encadenadas/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── military-resolution.md
└── tasks.md                       # generado posteriormente por /speckit-tasks
```

### Source Code (repository root)

```text
machiavelli/
├── discord.py                     # límite UX para fallos militares
├── events.py                      # tipo y registro determinista del resumen militar
├── game.py                        # Command ordenado, evento y contratación bloqueada
└── engine/
    ├── core.py                    # orden de campaña y barrera de desalojos
    └── military.py                # modelos, fases, resolución y aplicación atómica

tests/machiavelli/
├── test_discord.py                # worker, respuesta pública/efímera de run_game
├── test_game.py                   # Command, evento persistido y contratación
└── engine/
    ├── helpers.py                 # fixtures mínimas reutilizables
    ├── test_core.py               # orden y parada antes de fases posteriores
    └── test_military.py           # reglas, diagnóstico y rendimiento funcional

.github/workflows/
└── military-performance.yml       # puerta temporal en entorno de referencia
```

**Structure Decision**: Mantener el adjudicador completo en
`machiavelli/engine/military.py`. Las fronteras entre compilación, validación,
resolución y aplicación se expresan como métodos privados, no como módulos nuevos.
Solo `game.py`, `events.py`, `core.py` y el límite Discord cambian por contratos que
ya consumen el flujo militar.

## Phase 0: Research Decisions

Las decisiones y alternativas están consolidadas en [research.md](./research.md).
No quedan aclaraciones técnicas pendientes.

## Phase 1: Design and Contracts

- [data-model.md](./data-model.md) define identidades, órdenes, estado de resolución,
  resultados, índices e invariantes.
- [contracts/military-resolution.md](./contracts/military-resolution.md) fija el
  contrato de `MilitaryResolver.run`, el gestor externo de desalojos y los errores.
- [quickstart.md](./quickstart.md) define la validación ejecutable de persistencia,
  convoyes, ciclos, atomicidad, UX y rendimiento.

## Implementation Strategy

### 1. Orden persistido y snapshot inicial

1. Añadir orden ascendente por `commands.id` a `Command.load_commands()` sin tocar
   `Command.save()`, `Player.save_commands()` ni el esquema.
2. Sustituir `_build_conflicts_map()` por `_build_unit_index()`. Construir primero
   todas las identidades e índices y detectar duplicados antes de interpretar una
   orden.
3. Centralizar la equivalencia territorial en `conflict_location()` sin perder la
   costa exacta de una flota.

### 2. Compilación y enlace

1. Construir `actor_to_unit` desde el snapshot autoritativo posterior a gastos,
   rebeliones, sobornos y asesinatos.
2. Recorrer `player.commands` conservando su orden relativo y agrupar solo las filas
   cuya clave `(player_id, actor)` exista en `actor_to_unit`.
3. Descartar una fila huérfana sin añadirla a `invalid_orders`, sin transferirla al
   propietario actual de la unidad y sin afectar a las demás unidades.
4. Generar exactamente un `MilitaryOrder` por unidad. Una unidad actual sin orden o
   con una combinación inválida recibe un Hold efectivo; solo la orden inválida de
   una unidad existente se registra en `invalid_orders`.
5. Compilar varios Advance del mismo ejército como una ruta única marcada convoy
   antes de validarla.
6. Enlazar Transport desde la flota al ejército por tipo y origen; enlazar la ruta
   inversa desde el convoy a todas sus transportadoras.
7. Parsear Support únicamente como `<lugar>` o `<lugar> (<potencia>)` y Transport
   únicamente como `A <origen>`, reutilizando los valores generados por
   `Player.cmd_available_targets()`.
8. Validar geometría, tipos, apoyos, conversiones y restricciones de asedio. Una
   orden individual inválida se convierte en Hold; un snapshot corrupto aborta.

### 3. Conflictos y resolución determinista

1. Construir en cada evaluación las posiciones efectivas desde snapshot, órdenes y
   cancelaciones. Un convoy candidato aparece solo en su destino final.
2. Resolver en el incremento US1 los Supports geométricamente válidos cuyos emisores
   no dependan de conflictos pendientes; reservar corte, propagación y ciclos para
   el incremento US3.
3. Registrar como lugar disputado únicamente un espacio con al menos dos facciones;
   un cruce directo registra sus dos extremos.
4. Calcular dependencias de cada conflicto pendiente sobre apoyos y transportadoras
   situados en conflictos aún pendientes. Resolver en orden estable todos los
   conflictos independientes y reconstruir el tablero completo.
5. Cancelar Advance y Convert perdedores, todos los máximos empatados, órdenes de
   unidades desalojadas y apoyos cortados. Cada desalojo produce un nuevo
   `ResolutionState`: la unidad se incorpora a `dislodged_units` y
   `cancelled_orders`, deja de pertenecer a `active_supports`, se recalculan
   `available_convoys` y `effective_positions` y se reconstruye globalmente el
   tablero. Una cancelación conserva presencia física cuando corresponda, pero nunca
   produce efectos de Hold u otra orden.
6. Si no hay conflicto independiente, cancelar primero los apoyos atacados por un
   Advance válido, activo y no cancelado desde un origen distinto del lugar apoyado,
   incluyendo convoyes disponibles. Si sigue el círculo, cancelar todos los apoyos.
7. Comparar firmas primitivas completas. Solo una firma consecutiva idéntica con cero
   conflictos pendientes es estabilidad; cualquier firma repetida con conflictos
   pendientes después de targeted/all aborta.
8. Al abortar por ciclo, construir `CycleDiagnostic` con etapa agotada, iteraciones,
   conflictos pendientes ordenados y la firma canónica exacta; adjuntarlo a
   `UnresolvedMilitaryConflict` sin interpolar objetos mutables en el mensaje.
9. Después de `_resolve_conflicts()`, reutilizar el constructor canónico de conflictos
   para comprobar que no queda ningún conflicto efectivo fuera de
   `resolved_conflicts`. Una resolución incompleta lanza `MilitaryResolutionError`
   antes de construir outcomes, invocar al gestor, serializar el evento o preparar
   colecciones finales.

### 4. Resultados, rebeliones, asedios y eventos

1. Traducir el punto fijo a un `UnitOutcome` por unidad inicial. Las flotas conservan
   costa exacta y los desalojados conservan identidad con localización militar nula.
2. Aplicar la fuerza rebelde únicamente al conflicto provincial; un Hold efectivo
   puede someterla y una orden cancelada no. Resolver liberación y ciudad cerrada.
3. Calcular inicio, continuación, finalización y levantamiento de asedios desde el
   estado estable, incluidas restricciones de flota, guarnición y desalojo.
4. Construir en variables locales todas las colecciones finales de jugadores,
   guarniciones independientes, asedios, rebeliones y el `TurnEvent` resumen.
5. Serializar el evento antes del commit como `military_resolution|` más JSON
   compacto determinista. Mantener sin cambios el texto de los tipos de evento
   preexistentes y reutilizar la columna `game_events.message`.
6. Validar todas las colecciones y el registro antes de asignar en una única frontera
   el estado militar y `game.turn_events`; registrar el mismo contexto en logging.

### 5. Desalojos y activación segura

1. `MilitaryResolver.run()` acepta opcionalmente el callable definido en el contrato
   de desalojos. El resolver calcula primero un `MilitaryResolution` inmutable.
2. Si hay desalojados y no existe callable, lanzar un error específico antes de
   asignar colecciones. Si existe, obtener todas las decisiones de retirada de forma
   síncrona y validar que cubren exactamente las unidades desalojadas.
3. Una guarnición independiente exige también una decisión explícita. Si el gestor
   no dispone todavía de política o no devuelve su clave, abortar y conservar el
   snapshot completo; no crear persistencia de pendientes.
4. Combinar resultados militares y decisiones de retirada y aplicar una única vez.
   Si el gestor falla o devuelve datos inválidos, conservar el snapshot militar.
5. `GameEngine` conserva un punto de inyección opcional para el gestor futuro y no
   ejecuta hambre, control ni cambio de estación cuando el resolver falla.
6. La implementación concreta del gestor, sus reglas de selección y la política de
   guarniciones independientes quedan fuera de esta feature.

### 6. Mantenimiento de ciudades rebeldes

1. Mantener la restricción de Convert en `MilitaryResolver`.
2. Añadir en `Game.spring_maintenance()` el mismo guard antes de cobrar o añadir una
   guarnición: una orden `R` con actor `G <provincia>` se rechaza si la provincia está
   en `player.rebelled_cities`.
3. No cambiar los demás costes, actores ni reglas de reclutamiento.

### 7. Límite Discord

1. Extraer una función síncrona privada que reciba `db_path`, `channel_id` y el gestor
   opcional; dentro de ella abrir SQLite, cargar `Game`, ejecutar `GameEngine`, crear
   el reporte, guardar y devolver `tuple[str, ...]`.
2. Invocar esa función una sola vez mediante `asyncio.to_thread()`. La conexión y el
   estado mutable se crean, usan y destruyen dentro del worker; ninguna API de Discord
   se llama desde él.
3. Capturar únicamente la jerarquía de errores militares esperados en `run_game` y
   registrar internamente la excepción y su diagnóstico estructurado.
4. Traducir `InvalidMilitaryState`, `UnresolvedMilitaryConflict`,
   `DislodgementResolverRequired` y el error base a mensajes con el prefijo común de
   atomicidad y una acción correctiva específica, sin nombres de clase ni detalles
   internos.
5. Diferir siempre de forma efímera; borrar la respuesta diferida antes de publicar
   el éxito y editarla en los fallos. Mantener separadas partida inexistente y
   excepciones inesperadas.

## Test Strategy

- Añadir primero regresiones de carga no ordenada, mutación durante compilación y
  aplicación parcial; deben fallar con el flujo actual.
- Migrar pruebas privadas que fijan `conflicts_map` a pruebas de índices, órdenes y
  resultados. El comportamiento mutable antiguo no es contrato y no se conserva.
- Usar subtests/parametrización para transportadoras ausentes, rutas, costas,
  órdenes, apoyos y asedios; evitar una clase de fixture por regla.
- Probar expresamente que una transportadora desalojada rompe el convoy y que empate,
  ataque fallido y victoria defensiva lo conservan.
- Añadir una regresión causal donde un conflicto independiente desaloje al emisor de
  un Support y la reconstrucción global convierta una victoria apoyada en empate o
  derrota; comprobar cancelación, ausencia en `active_supports`, resultado físico y
  evento, no solo una marca interna.
- Probar la gramática exacta de Support y Transport, incluido paréntesis/potencia
  inválidos y ejército de otra facción enlazado por origen.
- Verificar resultados públicos e invariantes de `Game` antes/después. Usar métodos
  privados solo para aislar compilación, firma y normalización cuando reduzca el
  escenario.
- Probar Convert ganador, perdedor, empatado y cancelado por autoconflicto; en los dos
  últimos casos afirmar tipos, localizaciones, cancelaciones y lugares disputados.
- Probar una fila huérfana tras compra o desbandada por soborno: no se ejecuta bajo el
  propietario anterior ni se transfiere al nuevo, y una unidad actual sin orden propia
  recibe Hold.
- Probar que un fallo al construir o serializar el evento conserva estado y eventos,
  y que guardar-cargar recupera los seis grupos del registro militar.
- Inyectar mediante la API pública un `ResolutionState` incompleto con conflictos
  pendientes y comprobar que el resolver aborta antes del gestor, del evento y del
  commit, conservando exactamente el snapshot y los eventos previos.
- Añadir una regresión de mantenimiento que rechace `R` para `G <provincia>` cuando
  esa ciudad figure en `rebelled_cities`, sin cobrar ducados.
- Añadir pruebas de orden de `GameEngine`, parada ante gestor ausente/fallido y
  llamada al gestor antes de hambre/control. Capturar además las colecciones observadas
  por `ControlManager` y afirmar que nunca corresponden al snapshot militar anterior.
- Añadir pruebas del comando Discord que verifiquen una sola delegación a
  `asyncio.to_thread()`, que SQLite y `Game` no crucen la frontera, éxito público y
  mensajes militares efímeros, accionables y sin detalles internos.
- Ejecutar un mismo ciclo irresoluble bajo permutaciones y cargas sucesivas y comparar
  el `CycleDiagnostic` completo, no solo el tipo o texto de la excepción.
- Definir en el helper una colección acotada y explícita de variantes de orden
  incidental que cree un `Game` fresco por variante y pueda invertir jugadores y
  colecciones físicas sin alterar el orden relativo de los Advance de un mismo actor;
  evitar permutaciones factoriales y no confundir el orden semántico del convoy con
  el orden incidental.
- Después de US5, ejecutar una aceptación integrada de US1 que combine movimientos
  relacionados, Support dependiente, Convert, convoy, cancelación, rebelión, asedio,
  lugar disputado y retirada. Comparar `MilitaryResolution`, las seis listas del
  evento y el snapshot final bajo todas las variantes acotadas. Los checkpoints de
  US1 anteriores son incrementos técnicos y no cierran sus escenarios de aceptación.
- Construir cinco juegos frescos equivalentes con dos desalojos y decisiones
  deterministas fuera del cronómetro. La prueba funcional compara firma, resolución,
  evento y snapshot final en cualquier entorno; una segunda prueba condicionada al
  job de referencia mide solo `MilitaryResolver.run()` con el gestor incluido y
  exige menos de 1 segundo por ejecución, nunca por promedio.

## Acceptance Gate

US1 se desarrolla de forma incremental, pero no se considera aceptada al terminar su
núcleo técnico. Su cierre requiere haber completado US3 y US5 y superar una prueba
integrada que ejecute una campaña con dependencias, cancelaciones y retirada bajo una
colección acotada de órdenes incidentales distintos. La igualdad se comprueba sobre
`MilitaryResolution`, las seis listas del evento y el snapshot final.

## Activation Gate

El nuevo flujo no se activa para campañas con desalojos hasta que el callable del
gestor externo esté conectado. En ausencia del gestor, esas campañas fallan antes de
la aplicación militar y antes de fases posteriores. Las campañas sin desalojos sí
pueden completar el flujo nuevo porque no requieren esa dependencia.

## Post-Design Constitution Check

- [x] Dominio aislado: el resolver y el contrato de desalojos no dependen de Discord
      ni de SQLite.
- [x] Pruebas: cada cambio de regla, persistencia, orquestación y UX tiene una prueba
      prevista; no se preservan pruebas del comportamiento mutable reemplazado.
- [x] UX: éxito público, fallos militares efímeros y accionables, español de España,
      logging interno y transacción síncrona completa fuera del event loop.
- [x] Persistencia: consulta ordenada sobre una columna existente; sin migración ni
      cambio del formato almacenado.
- [x] Rendimiento: recalculado global con retiradas reales, determinismo universal y
      presupuesto temporal medido únicamente en el entorno de referencia.

## Agent Context Update

La instalación local de Spec Kit no contiene un script `update-agent-context` en
`.specify/scripts/`. No se ha inventado una ruta ni modificado un contexto de agente
desconocido. El contexto técnico necesario queda registrado en este plan y en
`research.md`.

## Complexity Tracking

No hay violaciones constitucionales ni excepciones de complejidad. Se descartan
módulos adicionales, librerías de grafos, jerarquías por código de orden y
persistencia de retiradas.
