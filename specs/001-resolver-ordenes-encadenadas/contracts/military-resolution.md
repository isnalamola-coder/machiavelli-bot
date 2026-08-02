# Contract: Military resolution and dislodgement handoff

## Scope

Contrato interno entre `GameEngine`, `MilitaryResolver`, el futuro gestor de
desalojos y la frontera de orquestación de Discord. No es una API pública ni un
formato persistido.

## Resolver entry point

```python
MilitaryResolver(game).run(
    dislodgement_resolver: DislodgementResolver | None = None,
) -> MilitaryResolution
```

### Preconditions

- Gastos, rebeliones por gasto, sobornos y asesinatos ya se han procesado.
- `Game` contiene el snapshot militar autoritativo de la campaña.
- Las órdenes de cada jugador están en orden persistido.
- El callable de desalojos, cuando exista, es síncrono, no modifica `Game` y se
  ejecuta dentro del mismo worker síncrono que contiene la resolución del turno.

### Success without dislodgements

1. El resolver compila y adjudica sin mutar el snapshot.
2. Valida todos los outcomes, colecciones finales y el registro serializado del
   evento resumen.
3. Sustituye el estado militar y añade el registro del evento en una única frontera
   de commit en memoria.
4. Devuelve `MilitaryResolution`.

### Success with dislodgements

1. El resolver construye `MilitaryResolution` sin mutar `Game`.
2. Llama exactamente una vez al gestor con la resolución completa.
3. El gestor devuelve un mapping para todas las unidades desalojadas.
4. El resolver valida cobertura, destinos finales y ausencia de duplicados.
5. Construye y valida el registro serializado del evento resumen.
6. Aplica conjuntamente resultados militares, retiradas y evento.
7. Devuelve la resolución militar original como registro de adjudicación.

## Dislodgement resolver

```python
type DislodgementResolver = Callable[
    [MilitaryResolution],
    Mapping[UnitKey, str | None],
]
```

### Required behavior

- No muta `Game`, `MilitaryResolution`, órdenes ni outcomes.
- Devuelve exactamente una entrada por `UnitOutcome.dislodged`.
- No devuelve unidades que no estén desalojadas.
- Incluye una decisión explícita para cada guarnición independiente desalojada; si
  todavía no dispone de política para ella, no debe invocarse como gestor válido.
- Interpreta `None` como eliminación conforme a sus propias reglas.
- Rechaza como destino cualquier `contested_locations` y resuelve colisiones entre
  retiradas.
- Decide la política de guarniciones independientes; esta feature no la define.

## Failure behavior

| Condición | Resultado | Orientación pública segura |
|---|---|---|
| Snapshot duplicado o incompatible | `InvalidMilitaryState` | Revisar duplicados y ocupaciones incompatibles antes de reintentar |
| Ciclo sin regla determinista restante | `UnresolvedMilitaryConflict` con `CycleDiagnostic` | Revisar las órdenes y escalar si se reproduce con las mismas entradas |
| Hay desalojos y no hay gestor | `DislodgementResolverRequired` | Activar la gestión de retiradas antes de reintentar |
| El gestor lanza o devuelve mapping incompleto/inválido | `MilitaryResolutionError` encadenado | Reintentar y comunicar el fallo si persiste |
| El evento resumen no puede construirse o serializarse | `MilitaryResolutionError` encadenado | Reintentar y comunicar el fallo si persiste |

En todos los fallos:

- No se asigna ninguna colección militar final.
- No se emite evento de éxito militar.
- `GameEngine` no ejecuta hambre, control ni cambio de estación.
- El límite Discord registra el detalle y responde de forma efímera con el prefijo
  “No se pudo resolver la fase militar; no se aplicó ningún cambio.” seguido de la
  orientación pública correspondiente. No muestra clases, trazas, rutas, líneas ni
  el `CycleDiagnostic`.

## Cycle diagnostic

`UnresolvedMilitaryConflict` recibe un `CycleDiagnostic` inmutable con:

- etapa de desempate agotada;
- iteración de primera aparición;
- iteración de repetición;
- conflictos pendientes ordenados;
- `ResolutionSignature` canónica usada para detectar el ciclo.

El texto base de la excepción es estable y breve. La información reproducible vive
en `error.diagnostic`, no en un mensaje construido desde `repr()` ni desde el orden
incidental de colecciones. El diagnóstico solo se usa en pruebas y logging interno.

## Discord execution boundary

`run_game` delega mediante `asyncio.to_thread()` una única función síncrona privada
que recibe `db_path`, `channel_id` y, cuando proceda, el gestor de desalojos. Esa
función:

1. abre y cierra la conexión SQLite dentro del worker;
2. carga el `Game` dentro del worker;
3. ejecuta `GameEngine`, incluido el gestor síncrono;
4. construye el reporte;
5. guarda la partida en la misma conexión;
6. devuelve exclusivamente `tuple[str, ...]` o propaga una excepción tipada.

La conexión, `Game`, `Player`, el resolver y cualquier colección mutable no cruzan
la frontera entre hilos. El worker no invoca APIs de Discord. La coroutine solo
difiere la interacción, espera el resultado, traduce excepciones y publica el
reporte.

## Atomicity boundary

El callable produce decisiones, no efectos. `MilitaryResolver` conserva la única
responsabilidad de construir las colecciones finales y el registro del evento. Los
valida antes de usar una única asignación final para estado militar, retiradas y
`game.turn_events`. Un fallo anterior, incluido el del evento, conserva el snapshot
y los eventos previos.

## Determinism

- Outcomes, claves de conflicto y datos de evento se ordenan mediante valores
  primitivos.
- El evento militar se registra como `military_resolution|` seguido de JSON compacto
  con claves ordenadas; los registros de tipos de evento existentes no cambian.
- La misma entrada y las mismas decisiones de desalojo producen el mismo resultado.
- Un ciclo semánticamente igual produce el mismo `CycleDiagnostic` estructurado.
- El orden de jugadores, diccionarios o sets no forma parte del contrato.

## Out of scope

- Implementación del gestor.
- Interfaz para que los jugadores seleccionen retirada.
- Persistencia de retiradas.
- Reglas de retirada de guarniciones independientes; mientras falten, su desalojo
  aborta el turno salvo que el gestor inyectado entregue una decisión explícita.
