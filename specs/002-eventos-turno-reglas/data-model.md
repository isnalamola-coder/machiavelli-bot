# Data Model: Eventos de turno y reglas de escenario

## JSONValue y FrozenJSONValue

`JSONValue` describe la entrada y la representación serializada nativa:

```text
JSONValue = null | bool | int | float | string |
            list[JSONValue] | dict[string, JSONValue]
```

Tras validar, `TurnEvent` copia y congela recursivamente el árbol:

```text
FrozenJSONValue = null | bool | int | float | string |
                  tuple[FrozenJSONValue, ...] |
                  read-only mapping[string, FrozenJSONValue]
```

La implementación usa únicamente biblioteca estándar, por ejemplo
`types.MappingProxyType` para mappings y `tuple` para listas. `to_json()` materializa
una copia nativa `dict`/`list` antes de serializar. Los validadores restringen el
conjunto general con claves exactas, tipos, rangos y valores cerrados. Un booleano no
satisface un campo entero aunque `bool` herede de `int` en Python.

## EventType

Enum estable compuesto exclusivamente por los 26 tipos de la tabla de contratos de
la especificación:

```text
start_game
start_game_power_assigned
start_season
famine_spawn
famine_relief
famine_attrition
famine_end
plague_spawn
plague_death
rebellion_pacify
rebellion_province
rebellion_city
expense
expense_no_funds
expense_syntax_error
bribe_executed
income_collected
maintenance_order_resolved
maintenance_summary
get_control
lose_control
get_home_country
lose_home_country
player_eliminated
player_won
military_resolution
```

FR-007 elimina `bribe_set`. Este conjunto cerrado, no los nombres históricos, es la
fuente de verdad que deben comparar las pruebas.

## TurnEvent

| Campo | Tipo | Reglas |
|-------|------|--------|
| `type` | `EventType` | Debe pertenecer al catálogo cerrado |
| `data` | `Mapping[str, FrozenJSONValue]` | Objeto validado, copiado y congelado según `type`; sin claves extra |

### Invariantes

- Se valida al construir y al reconstruir desde SQLite.
- La dataclass es frozen/slotted y el payload se congela en profundidad. Mutar el
  diccionario o una lista originales después de construir no cambia el evento; los
  mappings expuestos rechazan asignaciones y las secuencias son tuplas.
- Listas militares se canonicalizan con los validadores vigentes antes de congelar.
- Las demás listas preservan orden de dominio; se ordenan al producir solo cuando
  proceden de sets o diccionarios sin orden semántico.
- La serialización descongela hacia copias JSON nativas; es válida, compacta,
  determinista y conserva Unicode.
- Un evento válido puede repetirse; no existe identidad ni deduplicación en memoria.

## Contratos de payload compuestos

### VariableIncome

| Campo | Tipo | Regla |
|-------|------|-------|
| `source_type` | string | `home_country` o `province` |
| `source` | string | Identificador no vacío |
| `roll` | integer | Tirada pública 1–6 |
| `amount` | integer | Resultado aplicado |

### MaintenanceResult

Uno de `disbanded`, `unit_not_found`, `maintained`, `disbanded_no_funds`,
`recruited`, `recruitment_no_funds`, `invalid_home_or_control`, `space_occupied`,
`port_required`, `rebelled_city` o `fortified_city_required`.

### UnitKey y Outcome

```text
UnitKey = [player|null, unit_type, origin]
Outcome = [UnitKey, final_unit_type, final_location|null, dislodged]
```

`unit_type` y `final_unit_type` pertenecen a `A|F|G`. Un resultado desalojado tiene
`final_location=null`; uno no desalojado conserva una localización no vacía.

### RebellionTransition y SiegeTransition

```text
RebellionTransition = [player|null, province|city, province, subdued|liberated]
SiegeTransition = [UnitKey, province, started|completed|lifted]
```

## TurnEventRecord

| Columna | Tipo SQLite | Regla |
|---------|-------------|-------|
| `id` | INTEGER PK AUTOINCREMENT | Orden de emisión persistido |
| `game_id` | INTEGER NOT NULL FK | Partida propietaria; cascade delete |
| `event_type` | TEXT NOT NULL | Valor de `EventType` |
| `data_json` | TEXT NOT NULL | Objeto JSON serializado |

No existe `message`. La migración v4 reinicia esta tabla sin transformar filas. El
orden de reconstrucción es `ORDER BY id ASC`.

## InvalidTurnEventError

| Atributo | Tipo | Regla |
|----------|------|-------|
| `row_id` | `int | None` | Presente al fallar una fila persistida |
| `event_type` | `str | None` | Tipo bruto, incluso si es desconocido |

Encadena el error de enum, JSON o payload. El mensaje técnico identifica fila y
tipo, pero nunca incorpora `data_json`.

## Game.turn_events

Secuencia ordenada `list[TurnEvent]` del último turno completado o del turno nuevo en
construcción. No mezcla cadenas ni conserva varias campañas.

### Transición de estado

```text
historial persistido anterior
  -> cargar Game
  -> GameEngine.run: sustituir por []
  -> productores añaden TurnEvent validados
  -> TurnReporter valida cobertura y genera líneas
  -> GameRepository.save: reemplazo transaccional de estado + filas
  -> nuevo historial persistido
```

Si falla cualquier paso anterior al commit, el historial persistido anterior no
cambia. Si falla el SQL, el rollback restaura tanto estado como eventos.

## TurnReport

Valor de salida `list[str]` generado sin mutación:

1. Cabecera con partida y número de turno.
2. Estación y año derivados.
3. Descripciones de `turn_events` en orden.
4. Reporte de situación posterior.

Identificadores conocidos se resuelven a nombres o menciones. Los desconocidos se
mantienen como códigos neutralizados con `discord.utils.escape_markdown` y
`discord.utils.escape_mentions`; solo usuarios conocidos producen `<@...>`. Un
payload corrupto aborta; no produce una línea vacía ni se omite.

## Scenario Rules

| Regla | Default | Efecto al estar inactiva |
|-------|---------|--------------------------|
| `fortress_active` | `true` | `fortress` no admite guarnición, Convert, rebelión urbana ni asedio |
| `assassinations_active` | `true` | Sin fichas, opciones, cobros ni fase de asesinato |
| `famine_active` | `true` | Sin alivio, generación, atrición, limpieza ni eventos |
| `first_turn_famine` | `true` | Suprime solo la generación del setup; depende de hambre activa |
| `plague_active` | `true` | Sin generación, muertes ni eventos de plaga |

### Plaza defendible

```text
fortified -> siempre defendible
fortress  -> defendible solo si fortress_active
otro/null -> no defendible
```

Este concepto se usa en guarniciones, conversiones, rebeliones urbanas y asedios.
No se usa para ingresos, control de país natal, victoria ni reclutamiento, donde una
`fortress` se excluye con independencia de la regla.

### Hambre por fase

```text
setup turn_number=0:
  famine_active AND first_turn_famine -> spawn una vez

mantenimiento:
  nunca spawn

campaña:
  season=0 AND famine_active -> spawn una vez
  season=2 AND famine_active -> attrition y clear
```

## Historial y reglas: invariantes conjuntas

- Una mecánica inactiva no cambia estado, no cobra una orden obsoleta y no emite
  eventos.
- Desactivar una regla no reordena las demás fases.
- Una configuración inicial con guarnición en fortaleza inactiva falla antes del
  primer evento o asignación.
- Una `fortress` activa puede recibir guarnición declarada o por acciones posteriores,
  pero nunca independiente automática ni reclutada.
