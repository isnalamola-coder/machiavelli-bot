# ADR 0002: Propiedad de las migraciones SQLite

- Estado: Aceptado
- Fecha: 2026-08-04

## Contexto

El proyecto mantuvo dos módulos con responsabilidades solapadas de esquema y migración. Esa duplicación permitía que la API pública y la infraestructura interna evolucionaran de forma distinta y hacía ambiguo qué ruta debía inicializar una base existente.

## Decisión

`machiavelli/db/database.py` es la única implementación canónica de:

- `_SCHEMA_VERSION`;
- `_UPGRADES`;
- `upgrade_connection()`;
- `upgrade()`;
- `DatabaseManager`.

`machiavelli/database.py` se mantiene como fachada pública compatible y solo reexporta `DatabaseManager`, `upgrade` y `upgrade_connection`.

Las tablas `_UPGRADES` y `_SCHEMA_VERSION` son detalles privados y no se reexportan desde la fachada.

Las migraciones ya publicadas son inmutables. No se modifican sentencias existentes, números de versión ni su orden. Una nueva evolución del esquema se añade al final de la secuencia.

`DatabaseManager.init_db()` debe delegar en `upgrade_connection()` y no mantener un segundo bucle de migración.

## Consecuencias

- Todas las rutas de inicialización y actualización usan la misma implementación.
- La API histórica continúa disponible sin duplicar comportamiento.
- Los tests deben comprobar identidad de funciones, unicidad de las tablas privadas, migración desde versiones históricas, idempotencia y rollback.
- El código interno de infraestructura importa desde `machiavelli.db.database`; los consumidores públicos pueden usar `machiavelli.database`.
