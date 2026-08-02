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
- Un convoy contiene al menos origen, una posición intermedia y provincia final.
- Cada posición intermedia se enlaza a una flota Transport del ejército correcto.
- Una flota solo puede tener un `transported_army`.

## ResolutionState

Punto de evaluación inmutable.

| Campo | Tipo lógico | Significado |
|---|---|---|
| `active_supports` | conjunto de `UnitKey` | Support todavía eficaz |
| `available_convoys` | conjunto de `UnitKey` | Ejércitos con todas sus flotas disponibles |
| `successful_moves` | conjunto de `UnitKey` | Advance ganadores |
| `successful_conversions` | conjunto de `UnitKey` | Convert ganadores |
| `dislodged_units` | conjunto de `UnitKey` | Unidades que perdieron su ocupación |
| `cancelled_orders` | conjunto de `UnitKey` | Órdenes que ya no se ejecutan |
| `cancelled_by_self_conflict` | conjunto de `UnitKey` | Subconjunto cancelado por facción propia |
| `effective_positions` | pares `UnitKey → str | None` | Posición usada en la iteración |
| `resolved_conflicts` | conjunto de `str` | Espacios ya decididos |

La firma incluye todos los campos anteriores convertidos a tuplas primitivas
ordenadas. La evaluación produce un objeto nuevo.

## UnitOutcome

Resultado militar físico previo a la retirada.

| Campo | Tipo | Regla |
|---|---|---|
| `unit` | `UnitKey` | Identidad original |
| `final_unit_type` | `str` | Tipo después de Convert |
| `final_location` | `str | None` | Destino/origen; `None` si desalojada |
| `dislodged` | `bool` | Conserva la unidad para el gestor |

Una unidad no desalojada aparece una vez en origen o destino. Una desalojada no
ocupa el tablero militar y mantiene su identidad en el paquete de resolución.

## MilitaryResolution

Contrato inmutable entre adjudicador, orquestación y gestor de desalojos.

| Campo | Tipo | Regla |
|---|---|---|
| `outcomes` | `tuple[UnitOutcome, ...]` | Un resultado por unidad inicial |
| `contested_locations` | `frozenset[str]` | Solo conflictos efectivos de dos o más facciones; un cruce aporta dos extremos |

Las unidades desalojadas se obtienen filtrando `outcomes`. El resultado no contiene
decisiones de retirada ni muta `Game` por sí solo.

## Decisiones de desalojo externas

El gestor devuelve un mapping:

| Clave | Valor | Significado |
|---|---|---|
| `UnitKey` desalojada | `str` | Destino de retirada elegido |
| `UnitKey` desalojada | `None` | Unidad eliminada por las reglas del gestor |

El mapping debe contener exactamente todas las unidades desalojadas y ninguna otra.
La política de destino, colisiones entre retiradas y guarniciones independientes
pertenece al gestor externo.

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
  → MilitaryResolution
  → decisiones del gestor si hay desalojos
  → colecciones finales validadas
  → asignación atómica a Game/Player
```

Un error en cualquier transición anterior a la última conserva todas las
colecciones militares del snapshot.

## Estado persistido afectado

- `commands`: solo cambia el orden de lectura por el `id` existente.
- `players.armies`, `players.fleets`, `players.garrisons`, rebeliones: se guardan con
  el mecanismo existente después de completar la campaña.
- `games.independent_garrisons` y `games.besieges`: se reconstruyen y guardan con el
  mecanismo existente.
- No se crea tabla o columna para retiradas.
