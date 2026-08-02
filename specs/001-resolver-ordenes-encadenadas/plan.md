# Implementation Plan: Resolución militar atómica

**Branch**: `001-resolver-ordenes-encadenadas` | **Date**: 2026-08-02 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from
`/specs/001-resolver-ordenes-encadenadas/spec.md`

## Summary

Sustituir la ejecución incremental de filas `Command` por un adjudicador que toma un
snapshot militar, compila una orden lógica inmutable por unidad, valida convoyes y
dependencias, resuelve primero conflictos independientes y aplica un único estado
final. Las órdenes encadenadas de un ejército forman un convoy atómico; las
cancelaciones nunca se convierten en Hold; los apoyos, rebeliones, asedios,
conversiones, cruces y desalojos se recalculan hasta obtener un resultado
determinista.

La implementación reutiliza el módulo y las estructuras actuales: dataclasses
tipadas, diccionarios, tuplas y conjuntos de la biblioteca estándar. No añade una
librería de grafos ni cambia el esquema. Un contrato síncrono entrega los desalojos
y lugares disputados a un gestor externo; si ese gestor no existe o falla, el
resolver no aplica el estado militar ni permite continuar la campaña.

## Technical Context

**Language/Version**: Python 3.13 o superior

**Primary Dependencies**: Biblioteca estándar (`dataclasses`, `collections`,
`logging`, `typing`), `discord.py` existente; sin nuevas dependencias de runtime

**Storage**: SQLite existente para partidas, jugadores, órdenes y eventos; listas de
estado militar en `Game` y `Player`; sin cambio de esquema ni migración

**Testing**: Suite existente ejecutada con `pytest`, pruebas `unittest` y mocks;
`ruff check .` como puerta de calidad

**Target Platform**: Bot de Discord y motor de dominio ejecutado como proceso Python

**Project Type**: Paquete Python único con motor de dominio, persistencia SQLite y
adaptador Discord

**Performance Goals**: Resolver en menos de 1 segundo una campaña con 30 unidades,
60 filas de orden, 20 lugares de conflicto y un convoy de 5 transportadoras

**Constraints**: Resultado determinista, aplicación militar atómica, líneas de 88
caracteres, costas exactas conservadas, sin movimientos parciales, sin dependencia
del orden incidental y sin activar desalojos sin gestor

**Scale/Scope**: Un tablero cargado en memoria; recalculado global por iteración. El
coste se acota por unidades, órdenes, conflictos y firmas de estado observadas

## Constitution Check

*GATE inicial: aprobado. Se reevalúa después del diseño de Phase 1.*

- [x] Las reglas, snapshots, evaluación y aplicación permanecen en `machiavelli/`.
      Discord y SQLite son límites; el resultado militar emite un `TurnEvent`
      determinista y registra contexto técnico sin datos sensibles.
- [x] El plan añade pruebas para carga ordenada, todas las reglas modificadas,
      errores, atomicidad, orden de campaña y regresiones de mutación incremental.
- [x] `run_game` mantiene confirmación pública de éxito, difiere la interacción y
      traduce fallos militares a “No se pudo resolver la fase militar; no se aplicó
      ningún cambio.” sin detalles internos; el fallo se responde de forma efímera.
- [x] No hay cambio de esquema: `commands.id` ya existe y solo se usa para ordenar.
      Por tanto, migración, rollback de migración y prueba de migración no aplican.
- [x] La carga representativa y el presupuesto de menos de 1 segundo están definidos
      y se verifican con una prueba de rendimiento determinista.

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
├── events.py                      # tipo de evento resumen militar
├── game.py                        # carga de Command ordenada por id
└── engine/
    ├── core.py                    # orden de campaña y barrera de desalojos
    └── military.py                # modelos, fases, resolución y aplicación atómica

tests/machiavelli/
├── test_discord.py                # respuesta pública/efímera de run_game
├── test_game.py                   # persistencia y orden estable de Command
└── engine/
    ├── helpers.py                 # fixtures mínimas reutilizables
    ├── test_core.py               # orden y parada antes de fases posteriores
    └── test_military.py           # reglas y resultados públicos del adjudicador
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

1. Agrupar `player.commands` por actor conservando su orden relativo.
2. Generar exactamente un `MilitaryOrder` por unidad. Una unidad sin orden o con una
   combinación inválida recibe un Hold efectivo y se registra en `invalid_orders`.
3. Compilar varios Advance del mismo ejército como una ruta única marcada convoy
   antes de validarla.
4. Enlazar Transport desde la flota al ejército por tipo y origen; enlazar la ruta
   inversa desde el convoy a todas sus transportadoras.
5. Validar geometría, tipos, apoyos, conversiones y restricciones de asedio. Una
   orden individual inválida se convierte en Hold; un snapshot corrupto aborta.

### 3. Conflictos y resolución determinista

1. Construir en cada evaluación las posiciones efectivas desde snapshot, órdenes y
   cancelaciones. Un convoy candidato aparece solo en su destino final.
2. Registrar como lugar disputado únicamente un espacio con al menos dos facciones;
   un cruce directo registra sus dos extremos.
3. Calcular dependencias de cada conflicto pendiente sobre apoyos y transportadoras
   situados en conflictos aún pendientes. Resolver en orden estable todos los
   conflictos independientes y reconstruir el tablero completo.
4. Cancelar Advance y Convert perdedores, todos los máximos empatados, órdenes de
   unidades desalojadas y apoyos cortados. Una cancelación conserva presencia física
   pero nunca produce efectos de Hold u otra orden.
5. Si no hay conflicto independiente, cancelar primero los apoyos atacados por un
   Advance válido, activo y no cancelado desde un origen distinto del lugar apoyado,
   incluyendo convoyes disponibles. Si sigue el círculo, cancelar todos los apoyos.
6. Comparar firmas primitivas completas. Una firma consecutiva igual es estabilidad;
   una firma anterior no consecutiva después de los dos desempates aborta.

### 4. Resultados, rebeliones, asedios y eventos

1. Traducir el punto fijo a un `UnitOutcome` por unidad inicial. Las flotas conservan
   costa exacta y los desalojados conservan identidad con localización militar nula.
2. Aplicar la fuerza rebelde únicamente al conflicto provincial; un Hold efectivo
   puede someterla y una orden cancelada no. Resolver liberación y ciudad cerrada.
3. Calcular inicio, continuación, finalización y levantamiento de asedios desde el
   estado estable, incluidas restricciones de flota, guarnición y desalojo.
4. Construir en variables locales todas las colecciones finales de jugadores,
   guarniciones independientes, asedios y rebeliones. Validarlas antes de asignar.
5. Emitir un único `TurnEvent` resumen con listas ordenadas de resultados,
   cancelaciones, convoyes rotos, desalojos, rebeliones y asedios; registrar el mismo
   contexto en logging para diagnóstico reproducible.

### 5. Desalojos y activación segura

1. `MilitaryResolver.run()` acepta opcionalmente el callable definido en el contrato
   de desalojos. El resolver calcula primero un `MilitaryResolution` inmutable.
2. Si hay desalojados y no existe callable, lanzar un error específico antes de
   asignar colecciones. Si existe, obtener todas las decisiones de retirada de forma
   síncrona y validar que cubren exactamente las unidades desalojadas.
3. Combinar resultados militares y decisiones de retirada y aplicar una única vez.
   Si el gestor falla o devuelve datos inválidos, conservar el snapshot militar.
4. `GameEngine` conserva un punto de inyección opcional para el gestor futuro y no
   ejecuta hambre, control ni cambio de estación cuando el resolver falla.
5. La implementación concreta del gestor, sus reglas de selección y la política de
   guarniciones independientes quedan fuera de esta feature.

### 6. Límite Discord

1. Capturar únicamente la jerarquía de errores militares esperados en `run_game` y
   registrar internamente la excepción.
2. Diferir la interacción de manera que el éxito pueda publicarse en el canal y el
   fallo militar pueda editar la respuesta efímera con el texto aprobado.
3. Mantener el manejo separado de partida inexistente y de errores inesperados; no
   exponer trazas ni localizaciones de código al usuario.

## Test Strategy

- Añadir primero regresiones de carga no ordenada, mutación durante compilación y
  aplicación parcial; deben fallar con el flujo actual.
- Migrar pruebas privadas que fijan `conflicts_map` a pruebas de índices, órdenes y
  resultados. El comportamiento mutable antiguo no es contrato y no se conserva.
- Usar subtests/parametrización para transportadoras ausentes, rutas, costas,
  órdenes, apoyos y asedios; evitar una clase de fixture por regla.
- Verificar resultados públicos e invariantes de `Game` antes/después. Usar métodos
  privados solo para aislar compilación, firma y normalización cuando reduzca el
  escenario.
- Añadir pruebas de orden de `GameEngine`, parada ante gestor ausente/fallido y
  llamada al gestor antes de hambre/control.
- Añadir una prueba del comando Discord para éxito público y error militar efímero
  sin detalles internos.
- Ejecutar el escenario representativo cinco veces; cada ejecución debe quedar bajo
  1 segundo y producir la misma firma y resultado. El umbral se evalúa por ejecución,
  no por promedio que pueda ocultar una regresión.

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
- [x] UX: éxito público, fallo militar efímero, español de España y logging interno.
- [x] Persistencia: consulta ordenada sobre una columna existente; sin migración ni
      cambio del formato almacenado.
- [x] Rendimiento: recalculado global medido con la carga y presupuesto aprobados.

## Agent Context Update

La instalación local de Spec Kit no contiene un script `update-agent-context` en
`.specify/scripts/`. No se ha inventado una ruta ni modificado un contexto de agente
desconocido. El contexto técnico necesario queda registrado en este plan y en
`research.md`.

## Complexity Tracking

No hay violaciones constitucionales ni excepciones de complejidad. Se descartan
módulos adicionales, librerías de grafos, jerarquías por código de orden y
persistencia de retiradas.
