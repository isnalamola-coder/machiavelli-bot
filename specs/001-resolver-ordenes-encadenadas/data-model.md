# Data Model: Resolución militar atómica

## Principios

- La identidad, la intención, el estado iterativo y el resultado son objetos
  diferentes.
- El origen de una unidad nunca cambia durante la adjudicación.
- Los modelos que atraviesan fases son inmutables y usan valores hashables.
- Las colecciones de `Game` y `Player` solo se sustituyen al aplicar un resultado
  completo.

## UnitKey

Identidad estable de una unidad durante la campaña.

| Campo | Tipo | Regla |
|---|---|---|
| `player_id` | `str | None` | `None` solo para guarnición independiente |
| `unit_type` | `str` | Uno de `A`, `F`, `G` |
| `origin` | `str` | Localización exacta inicial; conserva costa |

**Unicidad**: No pueden existir dos `UnitKey` iguales. Tampoco dos unidades de
campaña en la misma provincia normalizada ni dos guarniciones en la misma ciudad.

**Orden estable**: Las firmas convierten la clave en
`(player_id or "", unit_type, origin)`; no dependen del orden de objetos.

## MilitaryUnit

Snapshot físico inicial.

| Campo | Tipo | Regla |
|---|---|---|
| `key` | `UnitKey` | Identidad autoritativa |
| `player` | `Player | None` | Referencia para reconstruir colecciones |

No almacena ruta, éxito, destino provisional, desalojo ni retirada.

## MilitaryOrder

Orden lógica compilada e inmutable.

| Campo | Tipo | Regla |
|---|---|---|
| `unit` | `UnitKey` | Unidad ejecutora |
| `order_type` | `str` | `A`, `B`, `H`, `L`, `S`, `T` o `C` |
| `target_location` | `str | None` | Destino, lugar apoyado o tipo convertido |
| `path` | `tuple[str, ...]` | Origen, pasos y destino de Advance |
| `transporters` | `tuple[UnitKey, ...]` | Flotas requeridas, con repeticiones eliminadas solo para dependencia |
| `transported_army` | `UnitKey | None` | Ejército declarado por una flota Transport |
| `supported_faction` | `str | None` | Facción beneficiaria del Support |
| `is_convoy` | `bool` | Se fija al compilar varios Advance |

**Validación**:

- Una orden inválida se reemplaza por una nueva orden Hold; no se muta la original.
- Support acepta exactamente `<lugar>` o `<lugar> (<potencia>)`; se retiran los
  paréntesis al guardar `supported_faction`. Transport acepta exactamente
  `A <origen>` y se resuelve contra `army_by_origin`.
- Un convoy contiene al menos origen, una posición intermedia y provincia final.
- Cada posición intermedia se enlaza a una flota Transport del ejército correcto.
- Una flota solo puede tener un `transported_army`.

## ResolutionState

Punto de evaluación inmutable.

| Campo | Tipo lógico | Significado |
|---|---|---|
| `active_supports` | `frozenset[UnitKey]` | Support todavía eficaz |
| `available_convoys` | `frozenset[UnitKey]` | Ejércitos con todas sus flotas disponibles |
| `successful_moves` | `frozenset[UnitKey]` | Advance ganadores |
| `successful_conversions` | `frozenset[UnitKey]` | Convert ganadores |
| `dislodged_units` | `frozenset[UnitKey]` | Unidades que perdieron su ocupación |
| `cancelled_orders` | `frozenset[UnitKey]` | Órdenes que ya no se ejecutan |
| `cancelled_by_self_conflict` | `frozenset[UnitKey]` | Subconjunto cancelado por facción propia |
| `effective_positions` | `tuple[tuple[UnitKey, str | None], ...]` | Pares ordenados por clave de unidad |
| `resolved_conflicts` | `frozenset[str]` | Espacios ya decididos |

La firma incluye todos los campos anteriores convertidos a tuplas primitivas
ordenadas. La evaluación produce un objeto nuevo.

## ResolutionSignature

Representación canónica de un `ResolutionState`. Es una tupla anidada ordenada que
contiene exclusivamente `str`, `int`, `bool`, `None` y otras tuplas primitivas. Cada
campo aparece con un nombre estable y los `UnitKey` se representan como
`(player_id or "", unit_type, origin)`.

La firma no puede contener objetos `Player`, diccionarios, sets sin ordenar,
`repr()`, valores de `hash()` ni identidad de objetos. Se usa tanto para detectar
estabilidad/ciclos como para construir el diagnóstico reproducible.

## CycleDiagnostic

Diagnóstico interno e inmutable de un ciclo sin regla determinista restante.

| Campo | Tipo | Regla |
|---|---|---|
| `stage` | `str` | `targeted-support-cancellation-exhausted` o `all-support-cancellation-exhausted` |
| `first_seen_iteration` | `int` | Primera iteración en la que apareció la firma repetida |
| `repeated_iteration` | `int` | Iteración posterior que vuelve a producirla; mayor que la anterior |
| `pending_conflicts` | `tuple[str, ...]` | Claves de conflicto pendientes, ordenadas y sin duplicados |
| `state_signature` | `ResolutionSignature` | Firma canónica exacta usada para detectar el ciclo |

Se implementa con `@dataclass(frozen=True, slots=True)`. Forma parte de
`UnresolvedMilitaryConflict` como atributo `diagnostic`, se registra solo en logging
y nunca se muestra al usuario de Discord. Entradas semánticamente iguales deben
producir un `CycleDiagnostic` igual aunque cambie el orden de jugadores,
colecciones, diccionarios o cargas sucesivas.

## UnitOutcome

Resultado militar físico previo a la retirada.

| Campo | Tipo | Regla |
|---|---|---|
| `unit` | `UnitKey` | Identidad original |
| `final_unit_type` | `str` | Tipo después de Convert |
| `final_location` | `str | None` | Destino/origen; `None` si desalojada |
| `dislodged` | `bool` | Conserva la unidad para el gestor |

Una unidad no desalojada aparece una vez en origen o destino. Una desalojada no
ocupa el tablero militar y mantiene su identidad en el paquete de resolución. Como
el modelo no define un estado adicional de «destruida», una guarnición eliminada por
un segundo Besiege usa también `final_location=None` y `dislodged=True`; el gestor
debe devolver `None` para ella y el evento la incluye en `dislodgements`.

## MilitaryResolution

Contrato inmutable entre adjudicador, orquestación y gestor de desalojos.

| Campo | Tipo | Regla |
|---|---|---|
| `outcomes` | `tuple[UnitOutcome, ...]` | Un resultado por unidad inicial |
| `contested_locations` | `frozenset[str]` | Solo conflictos efectivos de dos o más facciones; un cruce aporta dos extremos |

Las unidades desalojadas se obtienen filtrando `outcomes`. El resultado no contiene
decisiones de retirada ni muta `Game` por sí solo.

## MilitaryEventRecord

Registro auditable construido y validado antes de aplicar la resolución. Usa el
campo de texto existente de `game_events`, sin cambio de esquema:

```text
military_resolution|<JSON compacto con claves ordenadas>
```

El JSON contiene exactamente estas listas, también ordenadas:

| Clave | Elemento primitivo |
|---|---|
| `outcomes` | `[[player_id, unit_type, origin], final_unit_type, final_location, dislodged]` |
| `cancelled_orders` | `[player_id, unit_type, origin]` |
| `broken_convoys` | `[player_id, unit_type, origin]` del ejército |
| `dislodgements` | `[player_id, unit_type, origin]` |
| `rebellions` | `[player_id, "province" | "city", location, "subdued" | "liberated"]` |
| `sieges` | `[[player_id, unit_type, origin], location, "started" | "completed" | "lifted"]` |

`player_id` usa `null` para guarniciones independientes. La serialización usa claves
ordenadas, separadores compactos y Unicode sin escapar. Los eventos preexistentes
conservan su representación actual; solo el nuevo evento militar usa este prefijo.

## Decisiones de desalojo externas

El gestor devuelve un mapping:

| Clave | Valor | Significado |
|---|---|---|
| `UnitKey` desalojada | `str` | Destino de retirada elegido |
| `UnitKey` desalojada | `None` | Unidad eliminada por las reglas del gestor |

El mapping debe contener exactamente todas las unidades desalojadas y ninguna otra,
incluidas las guarniciones independientes. La política de destino, colisiones y
retirada de estas guarniciones pertenece al gestor externo, salvo la guarnición
eliminada por asedio completo, cuya única decisión válida es `None`. Si no existe un
gestor con esa política o falta su entrada, la resolución aborta y el snapshot
completo permanece intacto; no se crea una colección persistida de pendientes.

## Índices internos

| Índice | Relación | Invariante |
|---|---|---|
| `units_by_key` | `UnitKey → MilitaryUnit` | Sin sobrescritura |
| `actor_to_unit` | `(player_id, actor) → UnitKey` | Actor exacto con costa |
| `army_by_origin` | `origin → UnitKey` | Un ejército por provincia |
| `fleet_by_conflict_location` | `provincia normalizada → UnitKey` | Una flota por plaza de campaña |
| `transport_by_fleet` | `flota → ejército` | Una flota transporta como máximo uno |
| `orders_by_unit` | `UnitKey → MilitaryOrder` | Una orden lógica por unidad |
| `invalid_orders` | `UnitKey → str` | Diagnóstico interno, no contrato público |

## Espacios de conflicto

| Clave | Espacio |
|---|---|
| `province` | Unidad de campaña y conflicto provincial |
| `G province` | Guarnición, conversión a guarnición y conflicto urbano |

`conflict_location()` normaliza costas solo para la primera clave. Nunca se usa para
identidad, actor, validación marítima o localización final de una flota.

## Transiciones

```text
Game/Player inicial
  → snapshot e índices
  → órdenes compiladas
  → órdenes enlazadas y validadas
  → estados de resolución inmutables
  → ResolutionSignature y CycleDiagnostic si no existe progreso determinista
  → MilitaryResolution
  → decisiones del gestor si hay desalojos
  → colecciones finales y MilitaryEventRecord validados
  → asignación atómica de Game/Player/evento
```

Un error en cualquier transición anterior a la última conserva todas las
colecciones militares del snapshot.

## Estado persistido afectado

- `commands`: solo cambia el orden de lectura por el `id` existente.
- `game_events`: conserva tabla y columna; añade el nuevo registro textual prefijado
  `military_resolution|` con payload determinista.
- `players.armies`, `players.fleets`, `players.garrisons`, rebeliones: se guardan con
  el mecanismo existente después de completar la campaña.
- `games.independent_garrisons` y `games.besieges`: se reconstruyen y guardan con el
  mecanismo existente.
- No se crea tabla o columna para retiradas.
