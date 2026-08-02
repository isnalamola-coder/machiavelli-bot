# Contract: Military resolution and dislodgement handoff

## Scope

Contrato interno entre `GameEngine`, `MilitaryResolver` y el futuro gestor de
desalojos. No es una API Discord ni un formato persistido.

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
- El callable de desalojos, cuando exista, es síncrono y no modifica `Game`.

### Success without dislodgements

1. El resolver compila y adjudica sin mutar el snapshot.
2. Valida todos los outcomes y colecciones finales.
3. Sustituye el estado militar una sola vez.
4. Emite el evento resumen.
5. Devuelve `MilitaryResolution`.

### Success with dislodgements

1. El resolver construye `MilitaryResolution` sin mutar `Game`.
2. Llama exactamente una vez al gestor con la resolución completa.
3. El gestor devuelve un mapping para todas las unidades desalojadas.
4. El resolver valida cobertura, destinos finales y ausencia de duplicados.
5. Aplica conjuntamente resultados militares y retiradas.
6. Devuelve la resolución militar original como registro de adjudicación.

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
- Interpreta `None` como eliminación conforme a sus propias reglas.
- Rechaza como destino cualquier `contested_locations` y resuelve colisiones entre
  retiradas.
- Decide la política de guarniciones independientes; esta feature no la define.

## Failure behavior

| Condición | Resultado |
|---|---|
| Snapshot duplicado o incompatible | `InvalidMilitaryState` |
| Ciclo sin regla determinista restante | `UnresolvedMilitaryConflict` |
| Hay desalojos y no hay gestor | error militar específico de gestor requerido |
| El gestor lanza o devuelve mapping incompleto/inválido | `MilitaryResolutionError` |

En todos los fallos:

- No se asigna ninguna colección militar final.
- No se emite evento de éxito militar.
- `GameEngine` no ejecuta hambre, control ni cambio de estación.
- El límite Discord registra el detalle y responde: “No se pudo resolver la fase
  militar; no se aplicó ningún cambio.”

## Atomicity boundary

El callable produce decisiones, no efectos. `MilitaryResolver` conserva la única
responsabilidad de construir y asignar las colecciones finales. Esto mantiene una
sola frontera de commit en memoria.

## Determinism

- Outcomes, claves de conflicto y datos de evento se ordenan mediante valores
  primitivos.
- La misma entrada y las mismas decisiones de desalojo producen el mismo resultado.
- El orden de jugadores, diccionarios o sets no forma parte del contrato.

## Out of scope

- Implementación del gestor.
- Interfaz para que los jugadores seleccionen retirada.
- Persistencia de retiradas.
- Reglas de retirada de guarniciones independientes.
