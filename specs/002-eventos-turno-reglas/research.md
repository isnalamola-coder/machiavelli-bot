# Research: Eventos de turno y reglas de escenario

## Decisión 1: Un solo valor `TurnEvent` con validación por tipo

**Decision**: Mantener una `dataclass(frozen=True, slots=True)`, validar su objeto
JSON mediante una tabla explícita de funciones por `EventType` tanto al crear como
al cargar, copiar la entrada y congelar recursivamente mappings con
`MappingProxyType` y listas con `tuple`.

**Rationale**: El repositorio ya tiene `TurnEvent`, validadores militares y Python
3.13. Completar ese punto único satisface el catálogo sin duplicar serialización ni
introducir dependencias. `frozen=True` no protege diccionarios ni listas anidadas;
la congelación profunda evita que una mutación posterior invalide un evento ya
validado. `to_json()` materializa copias JSON nativas.

**Alternatives considered**: Una subclase por evento añade 26 clases sin
comportamiento propio. Pydantic añade una dependencia para validaciones pequeñas.
Confiar solo en anotaciones no valida JSON persistido.

## Decisión 2: JSON separado y determinista

**Decision**: Persistir `event_type` y `data_json`; serializar con `ensure_ascii=False`,
`sort_keys=True` y separadores compactos. El orden del historial lo proporciona el
`id` secuencial, no el orden de claves JSON.

**Rationale**: Se preservan tipos JSON nativos, Unicode y comparación estable. El
formato histórico `tipo|json` y los mensajes sueltos desaparecen por completo.

**Alternatives considered**: Un blob único conserva el acoplamiento actual. Una
columna por campo no encaja con payloads heterogéneos. Conservar `message` junto al
nuevo esquema permitiría dos contratos incompatibles.

## Decisión 3: Migración v4 que reinicia solo el historial efímero

**Decision**: Añadir una migración secuencial que elimina y recrea `game_events`
dentro de una única transacción explícita que también fija
`PRAGMA user_version=4`, sin copiar `message` y sin tocar las demás tablas. La v4 no
usa una secuencia `executescript()` más escritura exterior de versión que pueda
confirmar el esquema antes que el número de versión.

**Rationale**: La spec declara el historial efímero y exige no interpretar textos
antiguos. Una transacción protege tabla, filas y versión si falla después de `DROP`,
después de `CREATE` o antes del commit; pruebas con una conexión nueva verifican la
pérdida deliberada solo cuando la migración completa termina correctamente.
Esto es evolución canónica del esquema, no una ruta de compatibilidad: después de
v4 no queda lector, columna ni conversor para el formato retirado.

**Alternatives considered**: Inferir tipos desde mensajes es ambiguo e incumple la
spec. Añadir columnas a la tabla antigua deja filas inválidas y contrato dual.
Recrear toda la base perdería estado de partida fuera de alcance.

## Decisión 4: Reutilizar la persistencia del agregado

**Decision**: Adaptar `Game.save()`/`Game.load_game()` y `GameRepository`; no crear
un `EventRepository`.

**Rationale**: Los eventos se reemplazan con el resto del agregado en una sola
transacción. Separar el repositorio crearía coordinación transaccional adicional sin
otro ciclo de vida ni consultas independientes.

**Alternatives considered**: Un repositorio de eventos sería útil solo si hubiera
historial largo, paginación o escritura independiente, ninguno de los cuales está en
alcance.

## Decisión 5: Un `TurnReporter` de servicios

**Decision**: Crear un renderer único y exhaustivo en `services/turn_reporter.py`,
siguiendo `PlayerReporter`, y eliminar `Game.turn_report()` solo cuando el servicio
nuevo esté integrado. Los identificadores desconocidos se neutralizan con
`discord.utils.escape_markdown(..., as_needed=False)` y después
`discord.utils.escape_mentions(...)`; solo usuarios conocidos generan menciones.

**Rationale**: El renderer necesita mapa, potencias, jugadores y formato Discord,
pero no debe alterar el juego. Un `match` directo sobre el enum hace visible la
cobertura del catálogo y evita registros dinámicos. El escape explícito impide que
códigos persistidos como `@everyone` o `<@123>` activen menciones o Markdown.

**Alternatives considered**: Formatear en cada productor vuelve a mezclar dominio y
Discord. Métodos `render()` en los eventos acoplan el contrato de dominio a una
salida. Un registry/factory es más indirecto que el catálogo cerrado actual.

## Decisión 6: Reemplazo atómico desde el servicio existente

**Decision**: Empezar cada ejecución con una lista nueva en `GameEngine.run()` y
mantener el orden `load -> engine -> render -> repository.save` en `GameService`.

**Rationale**: La instancia cargada es descartable. Si motor o renderer fallan, no
se ejecuta SQL; si save falla, `GameRepository` revierte. No hace falta copiar todo
`Game` ni persistir borradores.

**Alternatives considered**: Guardar eventos a medida que se emiten rompe
atomicidad. Hacer `deepcopy(Game)` duplica un agregado grande. Una tabla temporal de
turno introduce persistencia que el historial efímero no necesita.

## Decisión 7: Sesión canónica fuera de Discord

**Decision**: Exportar desde servicios un context manager que usa
`DatabaseManager.get_connection()`, construye `GameRepository`/`GameService` y cierra
siempre. Discord conserva solo helpers síncronos llamados mediante
`asyncio.to_thread()`.

**Rationale**: Reutiliza la configuración SQLite canónica y elimina imports directos
de persistencia en el adaptador. Conexión, agregado, reporte y guardado permanecen en
el mismo worker.

**Alternatives considered**: Inyección global de servicio complica el ciclo de vida
de SQLite. Abrir en Discord mantiene la violación actual. Hacer asíncrona la capa
SQLite requeriría otra dependencia sin mejorar este flujo.

## Decisión 8: La política de desalojos no cruza el motor

**Decision**: Quitar el parámetro de Discord, `GameService` y `GameEngine`; conservar
la inyección solo en `MilitaryResolver.run()` para su contrato interno y pruebas.

**Rationale**: La política aún no existe. El motor seguirá lanzando
`DislodgementResolverRequired` antes del commit y podrá conectar una política interna
en una feature posterior sin cambiar APIs externas.

**Alternatives considered**: Mantener el parámetro “por si acaso” publica una
dependencia incompleta. Implementar retiradas ahora está expresamente fuera de
alcance.

## Decisión 9: Gate compartido para plazas defendibles

**Decision**: Añadir a `Scenario` un helper mínimo que reconoce `fortified` y,
condicionalmente, `fortress`; reutilizarlo en setup, órdenes, rebeliones y militar.
Ingreso, control, victoria y reclutamiento continúan usando explícitamente solo
`city`/`fortified`.

**Rationale**: La misma regla aparece hoy duplicada y la conversión aún acepta solo
`fortified`. El helper corrige el punto común sin alterar reglas donde `fortress`
siempre debe excluirse.

**Alternatives considered**: Reescribir el mapa para convertir `fortress` a `None`
perdería el dato necesario al activar la regla. Repetir tuplas en cuatro módulos
facilita divergencias.

## Decisión 10: Gates en ejecución y en órdenes obsoletas

**Decision**: Proteger managers públicos y el orden de fases; además, ocultar en la
interacción y descartar sin cobro gastos de hambre o asesinato persistidos cuando la
regla correspondiente esté inactiva.

**Rationale**: El gate de UI protege entradas nuevas, pero una orden ya guardada
puede sobrevivir a un cambio de escenario. El procesador de gastos es la frontera
común que evita efectos y eventos residuales.

**Alternatives considered**: Solo ocultar opciones no cubre datos persistidos. Solo
comprobar después de cobrar evita el efecto pero consume recursos, contradiciendo la
regla desactivada.

## Decisión 11: Rendimiento sin infraestructura nueva

**Decision**: Reutilizar `MACHIAVELLI_REFERENCE_PERF` y el workflow de rendimiento
existente para dos presupuestos independientes: resolución militar con 30
unidades/60 órdenes y 10 ciclos save/load/render con 100 eventos.

**Rationale**: Ambos pipelines son lineales y el job ya fija Ubuntu
24.04/CPython 3.13. La correctitud de los 10 ciclos puede correr siempre; solo los
umbrales temporales dependen del entorno estable. Ejecutarlos en el mismo job no
convierte las dos cargas en una única medición combinada.

**Alternatives considered**: Un framework de benchmarks o workflow nuevo no aporta
precisión necesaria. Un límite temporal en todos los entornos sería inestable.
