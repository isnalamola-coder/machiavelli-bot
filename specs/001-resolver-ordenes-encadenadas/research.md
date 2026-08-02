# Research: Resolución militar atómica

## 1. Frontera del adjudicador

**Decision**: Reemplazar el flujo actual de `MilitaryResolver` dentro de
`machiavelli/engine/military.py`, manteniendo métodos privados por fase y un único
punto público `run()`.

**Rationale**: El módulo actual ya es el consumidor de `Game`, `Player`, `Command` y
`Map`. Mantenerlo evita imports circulares y fronteras prematuras; separar las fases
en métodos basta para probarlas.

**Alternatives considered**:

- Dividir modelos, órdenes y conflictos en tres módulos: rechazado hasta que exista
  un segundo consumidor o el archivo sea realmente inmanejable.
- Crear un motor genérico de reglas: rechazado por no aportar valor a una sola fase.

## 2. Modelos Python

**Decision**: Usar dataclasses con `slots=True`; hacer inmutables `UnitKey`,
`MilitaryOrder`, `ResolutionState`, `UnitOutcome` y `MilitaryResolution`. Mantener
`MilitaryUnit` como snapshot pequeño asociado a `Player | None`.

**Rationale**: Las dataclasses dan nombres legibles, igualdad determinista y claves
hashables sin factories ni clases base. La inmutabilidad impide mezclar origen,
intención y resultado, y `slots` mantiene bajo el coste de miles de evaluaciones.

**Alternatives considered**:

- Alias de tupla para `UnitKey`: más corto, pero facilita intercambiar tipo y origen
  y empeora diagnósticos.
- Una subclase por cada orden: rechazada; la dataclass común cubre los siete códigos.
- Diccionarios sin tipos para todo el estado: rechazados para el estado que cruza
  varias funciones; se mantienen para índices locales simples.

## 3. Orden persistido de Command

**Decision**: Cargar por `commands.id ASC`.

**Rationale**: La tabla actual ya contiene `id INTEGER PRIMARY KEY AUTOINCREMENT` y
`Player.save_commands()` elimina y reinserta siguiendo `player.commands`. El cambio
recupera exactamente ese orden sin tocar guardado ni esquema.

**Alternatives considered**:

- Añadir una columna de secuencia: rechazada porque duplica información existente y
  exigiría migración.
- Ordenar por actor o destino: rechazado porque altera rutas encadenadas.

## 4. Identidad y normalización

**Decision**: `UnitKey(player_id, unit_type, origin)` conserva la localización exacta;
`conflict_location()` normaliza exclusivamente plazas de conflicto.

**Rationale**: El código actual usa `split()[0]` en varios lugares y pierde costas.
Una sola función evita discrepancias entre ocupación, convoy y aplicación mientras
la identidad sigue distinguiendo `prove S` de `prove N`.

**Alternatives considered**:

- Normalizar el origen al crear la unidad: rechazado porque impide validar rutas
  marítimas y reconstruir el destino exacto de una flota.
- Añadir índices exactos preventivos: rechazado hasta que exista un consumidor.

## 5. Compilación y validación

**Decision**: Compilar primero todas las filas por actor, parsear Support como
`<lugar>` o `<lugar> (<potencia>)`, enlazar Transport desde `A <origen>` y validar
por último. Una orden individual inválida produce Hold efectivo con un motivo de
texto; un snapshot corrupto lanza `InvalidMilitaryState`.

**Rationale**: El enlace de una ruta necesita conocer todas las órdenes de flotas y
ejércitos. Separar error de orden y error de estado permite continuar con jugadores
no afectados sin esconder duplicados físicos.

**Alternatives considered**:

- Ejecutar una fila al leerla: rechazado; es la causa de pérdida de identidad y
  convoyes parciales.
- Enum pública de motivos inválidos: diferida hasta que exista más de un consumidor.

## 6. Resolución de dependencias

**Decision**: Recalcular todo el tablero en cada iteración con diccionarios y
conjuntos. Cada conflicto declara dependencias sobre apoyos y transportadoras en
conflictos pendientes. Se resuelven claves independientes en orden estable, se
cancelan órdenes y se reconstruye.

**Rationale**: El tablero es pequeño y las dependencias atraviesan ubicaciones. El
recalculo global es más verificable que una cola incremental y cumple el presupuesto
sin una librería de grafos.

**Alternatives considered**:

- `networkx`: rechazado; sets y dicts cubren dependencia, firmas y ciclos.
- Cola `dirty_locations`: diferida hasta que una medición demuestre necesidad.
- Evaluación recursiva: rechazada por ciclos y por depender del orden de llamada.

## 7. Círculos, estabilidad y diagnóstico

**Decision**: Aplicar tres etapas deterministas: conflictos independientes; cancelar
apoyos atacados desde otro origen; cancelar todos los apoyos. Comparar después una
firma primitiva completa y abortar solo si reaparece una firma no consecutiva sin
una regla de desempate restante. El aborto construye un `CycleDiagnostic` inmutable
con etapa agotada, iteraciones, conflictos pendientes ordenados y la firma canónica
exacta, que se adjunta a `UnresolvedMilitaryConflict`.

**Rationale**: Implementa las aclaraciones sin escoger arbitrariamente un punto fijo.
La firma incluye todas las relaciones que pueden cambiar un resultado y el objeto
estructurado permite comparar diagnósticos entre permutaciones sin depender de texto,
`repr()`, hashes de proceso ni identidad de objetos.

**Alternatives considered**:

- Abortar al primer círculo: rechazado por la regla prioritaria de cancelación de
  apoyos.
- Elegir el primer punto fijo encontrado: rechazado por no ser auditable.
- Guardar solo un mensaje textual: rechazado porque dificulta pruebas estructuradas y
  puede incorporar orden incidental o representaciones no reproducibles.

## 8. Aplicación atómica

**Decision**: Construir todas las listas finales en variables locales y asignarlas
solo tras validar cada outcome, costa, ocupación, asedio, rebelión y decisión de
retirada.

**Rationale**: Las operaciones actuales `remove()`/`append()` pueden dejar estado
parcial. Reemplazar colecciones completas hace innecesario un mecanismo de rollback
interno y preserva el snapshot si algo falla.

**Alternatives considered**:

- Copiar profundamente `Game` y reemplazarlo: rechazado por referencias compartidas
  a jugadores, mapa y escenario.
- Deshacer mutaciones una por una: rechazado por frágil y más largo.

## 9. Contrato con desalojos

**Decision**: `MilitaryResolver.run()` recibe opcionalmente un callable síncrono que
acepta `MilitaryResolution` y devuelve un mapping completo de `UnitKey` desalojada a
destino de retirada o `None`. Si faltan gestor o decisiones, se aborta antes de
aplicar.

El mapping incluye también cualquier guarnición independiente desalojada. Mientras
el gestor no tenga una política para ella, la campaña aborta y conserva el snapshot;
no se crea un estado persistido de pendientes.

**Rationale**: Permite retiradas inmediatas en la misma campaña sin implementar ni
persistir el gestor en esta feature. Un callable tipado es la frontera mínima; no se
necesita un protocolo con una sola implementación futura.

**Alternatives considered**:

- Persistir retiradas pendientes: rechazado por la aclaración y por requerir esquema.
- Aplicar movimientos y llamar después al gestor: rechazado porque un fallo dejaría
  estado parcial.
- Resolver automáticamente destinos: rechazado porque pertenece al gestor externo.

## 10. Eventos y UX

**Decision**: Construir y serializar antes del commit un `TurnEvent` resumen militar
con datos deterministas. El nuevo evento se guarda como
`military_resolution|<JSON compacto>` en la columna de texto existente; los eventos
anteriores conservan su representación. Estado y registro se asignan juntos y el
mismo contexto se registra mediante logging. En Discord, traducir la jerarquía de
errores a un prefijo común que confirme la atomicidad y a una orientación pública
específica: revisar ocupaciones, revisar órdenes y escalar, activar retiradas o
reintentar y comunicar el fallo.

**Rationale**: Reutiliza el patrón de eventos y logging existente, permite auditar la
decisión sin revelar internals y satisface la exigencia constitucional de que los
errores previsibles indiquen cómo corregirlos. La traducción permanece en Discord
para no acoplar el dominio al idioma ni a una interfaz.

**Alternatives considered**:

- Un evento por transición interna: rechazado por ruido y volumen.
- Mostrar la excepción o el `CycleDiagnostic` al usuario: rechazado por filtrar
  detalles técnicos.
- Incluir mensajes públicos en las excepciones del dominio: rechazado por acoplar el
  motor a Discord y al español.
- Cambiar el formato de eventos existentes: rechazado. El prefijo/payload se limita
  al tipo militar nuevo y no requiere migración.

## 11. Estrategia de pruebas y rendimiento

**Decision**: Priorizar escenarios públicos con `pytest` sobre las estructuras
existentes de `unittest`, usar subtests para matrices y separar dos comprobaciones de
la carga representativa. La prueba funcional se ejecuta en cualquier entorno sobre
cinco juegos frescos con dos desalojos y compara resolución, evento y snapshot final.
La puerta temporal se activa solo en un job dedicado con
Ubuntu 24.04 y CPython 3.13, sin cobertura ni paralelismo, y exige menos de un segundo
por cada llamada a `MilitaryResolver.run()` con el gestor determinista incluido.

**Rationale**: El proyecto ya usa ambos estilos y mocks. No hace falta introducir
fixtures o frameworks nuevos. Separar corrección y tiempo evita que una máquina local
o cargada invalide la suite, mientras el runner de referencia mantiene una puerta
reproducible. Incluir una retirada y una eliminación garantiza que el presupuesto
mide también el contrato de desalojos y la aplicación final.

**Alternatives considered**:

- Un único test temporal en todas las máquinas: rechazado por variación de hardware,
  sistema y carga concurrente.
- Promediar cinco ejecuciones: rechazado porque puede ocultar una regresión puntual.
- Microbenchmarks por helper: rechazados porque no prueban el coste end-to-end.
- Hypothesis u otra dependencia: rechazada; permutaciones construidas con stdlib son
  suficientes para el tablero previsto.

## 12. Frontera síncrona de Discord

**Decision**: Extraer una función privada síncrona que abra SQLite, cargue `Game`,
ejecute `GameEngine`, construya el reporte y guarde dentro del mismo hilo. `run_game`
la invoca una sola vez con `asyncio.to_thread()` y recibe únicamente una
`tuple[str, ...]` o una excepción tipada.

**Rationale**: El código actual realiza carga, motor y guardado directamente en la
coroutine. Mover solo el resolver dejaría SQLite y las demás fases bloqueando el event
loop y podría hacer cruzar una conexión u objetos mutables entre hilos. La frontera
completa mantiene conexión, `Game`, `Player` y gestor en el worker y deja a la
coroutine únicamente las APIs de Discord.

**Alternatives considered**:

- Enviar solo `MilitaryResolver.run()` a un hilo: rechazado porque no elimina el resto
  del trabajo síncrono y obliga a compartir `Game` mutable.
- Reutilizar en el worker una conexión creada por la coroutine: rechazado por la
  afinidad de hilo de SQLite y por ampliar el estado compartido.
- Usar procesos: rechazado en esta feature porque exigiría serializar `Game`, mapa,
  escenario y callable; se reconsiderará solo si las mediciones muestran que el GIL
  es un límite real.
