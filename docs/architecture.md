# Arquitectura canónica de Machiavelli

## Propósito

La arquitectura soportada mantiene una única identidad para las entidades de dominio y un único flujo de ejecución y persistencia:

```text
Discord → Services → Game / Engine → Repositories → SQLite
```

Cada capa tiene una responsabilidad explícita. No se permiten implementaciones paralelas de entidades, motor, repositorios ni migraciones.

## `machiavelli.game`

`machiavelli.game` contiene las entidades y reglas básicas del dominio.

- `Player` se define únicamente en `machiavelli/game/player.py`.
- `Command` se define únicamente en `machiavelli/game/command.py`.
- `machiavelli.game` reexporta esas clases como API pública sin crear tipos alternativos.
- Los identificadores de persistencia son atributos derivados del almacenamiento; no constituyen entidades de dominio paralelas.
- La capa de dominio no contiene una implementación alternativa de repositorios.

## `machiavelli.engine`

`machiavelli.engine` contiene las reglas de ejecución de la partida.

- `GameEngine` se define únicamente en `machiavelli/engine/core.py` y se reexporta desde `machiavelli.engine`.
- La resolución militar atómica permanece en `machiavelli/engine/military.py`.
- La especificación normativa de la resolución militar es `specs/001-resolver-ordenes-encadenadas`.
- No existe el módulo sombreado `machiavelli/engine.py`.

Los cambios del motor deben conservar atomicidad, rollback, determinismo y orden persistido. Una modificación militar requiere especificación y tests propios.

## `machiavelli.repositories`

Los repositorios traducen agregados y entidades de dominio a filas SQLite y reconstruyen esos objetos al leerlos.

- `GameRepository` persiste el agregado completo dentro de una única transacción.
- Los repositorios subordinados respetan una transacción ya abierta y no realizan commits parciales.
- `CommandRepository` conserva el orden relativo de las órdenes mediante el orden persistido.
- La capa no redefine `Game`, `Player` ni `Command`.

## `machiavelli.services`

Los servicios orquestan casos de uso entre dominio, motor y repositorios.

- `GameService` es la interfaz principal usada por el adaptador de Discord.
- La ejecución de un turno carga el agregado, ejecuta `GameEngine` y persiste el resultado completo.
- Las validaciones de aplicación se realizan antes de persistir cambios.
- Los servicios no contienen una segunda implementación del esquema SQLite.

## `machiavelli.db.database`

`machiavelli/db/database.py` es la implementación canónica de infraestructura SQLite.

- Contiene el esquema y las migraciones reales.
- Es la única fuente de verdad para `_UPGRADES` y `_SCHEMA_VERSION`.
- `upgrade_connection()` aplica migraciones ordenadas sobre una conexión abierta.
- `upgrade()` administra la apertura y cierre de la conexión.
- `DatabaseManager.init_db()` delega en la misma ruta de migración.

Las migraciones publicadas son inmutables. Las nuevas migraciones se añaden al final de la secuencia.

## `machiavelli.database`

`machiavelli/database.py` es una fachada pública de compatibilidad.

- Reexporta únicamente `DatabaseManager`, `upgrade` y `upgrade_connection`.
- No implementa esquema ni migraciones.
- No expone `_UPGRADES` ni `_SCHEMA_VERSION`.

El código interno de infraestructura debe importar desde `machiavelli.db.database`. Los consumidores públicos pueden continuar usando `machiavelli.database`.

## `machiavelli.discord`

`machiavelli.discord` es un adaptador de entrada.

- Traduce interacciones de Discord a llamadas de servicios.
- No contiene sentencias SQL.
- Importar el módulo no inicia una conexión ni crea una base de datos.
- Las sesiones SQLite se abren únicamente durante la ejecución de un caso de uso.
- Las operaciones síncronas, incluida la ejecución de turnos, se ejecutan mediante `asyncio.to_thread()` fuera del event loop.
- Los nombres, parámetros y visibilidad de los slash commands forman parte de la interfaz pública.

## Barreras arquitectónicas

Los tests deben impedir que reaparezcan las duplicaciones eliminadas:

- identidad única de `Player`, `Command` y `GameEngine`;
- identidad entre la fachada SQLite y la implementación canónica;
- una sola definición de `_UPGRADES` y `_SCHEMA_VERSION`;
- ausencia de `machiavelli/engine.py`, `database.py` raíz y `cli.log`;
- contenido permitido y prohibido del wheel.

Cualquier excepción a estas reglas requiere una decisión arquitectónica explícita, tests de regresión y un commit separado de los cambios de CI o estilo.
