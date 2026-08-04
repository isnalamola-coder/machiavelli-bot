# Informe de cierre de la refactorización modular

## Estado de aceptación

La aceptación local de la refactorización modular queda completada sobre la rama `corrective/complete-modular-closure`.

El código validado corresponde al commit:

```text
a459de05ea1f9afd9eb881ff85a313ad4a195f93
```

El commit de aceptación es el commit que contiene este informe. Su publicación remota y la nueva ejecución de CI quedan expresamente fuera de esta operación, porque se solicitó crear únicamente el commit local.

## Identificación

- Fecha de validación: 2026-08-04T07:23:28+02:00.
- Rama: `corrective/complete-modular-closure`.
- Commit de código validado: `a459de05ea1f9afd9eb881ff85a313ad4a195f93`.
- Remoto antes de crear este informe: `origin/corrective/complete-modular-closure` en `a459de05ea1f9afd9eb881ff85a313ad4a195f93`.
- Python: CPython 3.13.9, 64 bits, entorno `.venv-audit-final`.
- Versión de distribución: `0.5.0.dev0`.

## Resultados de calidad

| Comprobación | Resultado |
| --- | --- |
| Instalación editable `pip install -e ".[dev]"` | Correcta |
| `pip check` del entorno de auditoría | Correcto, sin dependencias rotas |
| `compileall` sobre `machiavelli` y `tests` | Correcto |
| `ruff format --check .` | Correcto, 84 archivos ya formateados |
| `ruff check .` | Correcto, sin incidencias |
| `mypy machiavelli` | Correcto, 36 archivos fuente sin incidencias |
| Pytest completo | 369 aprobados, 1 omitido, 0 fallos, 370 recopilados |
| Cobertura | 74,62 %, superior al mínimo de 71 % |
| Prueba militar de referencia | 1 aprobada, 78 deseleccionadas |
| Pruebas de migraciones, repositorios y validación final | 33 aprobadas |
| `git diff --check` | Correcto |

La única omisión de la suite completa corresponde a `test_representative_resolution_budget`, protegida por `MACHIAVELLI_REFERENCE_PERF=1`. La prueba se ejecutó separadamente con esa variable activa y pasó correctamente. No se detectaron marcadores `xfail` ni omisiones añadidas para ocultar fallos.

## Distribuciones

Se construyeron correctamente:

- `machiavelli-0.5.0.dev0-py3-none-any.whl`.
- `machiavelli-0.5.0.dev0.tar.gz`.

Hashes SHA-256 de los artefactos de validación:

```text
d0d76517d51241591f213be5260e8795811e6fbeab7dde33b3b2da6680dfa8dd  machiavelli-0.5.0.dev0-py3-none-any.whl
e404d1020c027586825e2853e997d8e3ee5d5a1134d873c36a2e62251c8ee941  machiavelli-0.5.0.dev0.tar.gz
```

La inspección del wheel confirmó que contiene los recursos y módulos canónicos requeridos, y que no contiene `machiavelli/engine.py`, `database.py` de raíz, `cli.log`, tests, especificaciones, bases de datos ni logs.

El wheel se instaló con éxito en `.venv-wheel-final`; `pip check` no detectó dependencias rotas.

## Verificación externa del paquete

La importación se ejecutó desde fuera del checkout y resolvió el paquete desde:

```text
C:\Users\dewamola\Desktop\machiavelli-bot-main\.venv-wheel-final\Lib\site-packages\machiavelli\__init__.py
```

Se verificó:

- `machiavelli.__version__ == importlib.metadata.version("machiavelli")`.
- La versión efectiva es `0.5.0.dev0`.
- `GameEngine`, `Game`, `Player` y `Command` se importan desde sus implementaciones canónicas.
- `Map.load_map()` carga provincias.
- `Scenario.load_scenarios()` carga escenarios.
- `GameService` se importa correctamente.
- `bot` y `machiavelli.discord` se importan sin crear la base indicada en `DATABASE_PATH`.

## Persistencia y migraciones

Las pruebas específicas de `machiavelli.db`, repositorios y validación final pasaron: 33 pruebas aprobadas.

La validación cubre las migraciones históricas, conservación de datos, orden de comandos, eventos, rollback y equivalencia entre la API pública y la implementación canónica.

La arquitectura final mantiene:

- implementación canónica en `machiavelli/db/database.py`;
- fachada pública en `machiavelli/database.py`;
- una única definición de `_UPGRADES`;
- una única definición de `_SCHEMA_VERSION`;
- detalles privados no expuestos por la fachada pública.

## Resolución militar

La comparación contra `backup/refactor-before-corrections` no mostró diferencias en:

- `machiavelli/engine/military.py`;
- `tests/machiavelli/engine/test_military.py`.

La suite militar pasó y la prueba de rendimiento de referencia pasó sin ampliar su límite. Se conserva la implementación de `specs/001-resolver-ordenes-encadenadas`, incluidos atomicidad, rollback, determinismo, convoyes encadenados, apoyos, transportes, conversiones, rebeliones, asedios, desalojos, retiradas y orden persistido.

## Arquitectura final

Quedan establecidas las siguientes decisiones:

- `Player` solo se define en `machiavelli/game/player.py`.
- `Command` solo se define en `machiavelli/game/command.py`.
- `GameEngine` solo se define en `machiavelli/engine/core.py`.
- `machiavelli/engine.py` no existe.
- `machiavelli/db/database.py` contiene la implementación real de esquema y migraciones.
- `machiavelli/database.py` es una fachada de compatibilidad.
- El flujo soportado es `Discord → Services → Game/Engine → Repositories → SQLite`.
- Los archivos heredados `database.py` de raíz y `cli.log` no existen en el repositorio.
- No hay logs, bases locales, coberturas ni caches versionados.

## Diferencias respecto al backup

Las diferencias contra `backup/refactor-before-corrections` corresponden exclusivamente a las categorías previstas:

- validación de CI;
- versión canónica;
- eliminación del motor heredado sombreado;
- consolidación de SQLite;
- eliminación de archivos heredados;
- documentación y ADR;
- tests de arquitectura, distribución y validación.

No se detectaron cambios inesperados en las reglas militares.

## CI y publicación

Por instrucción expresa del responsable, la Fase 8 se considera aceptada y no se reacredita en este cierre.

Los workflows presentes configuran:

- calidad en `ubuntu-latest` con Python 3.13;
- calidad en `windows-latest` con Python 3.13;
- rendimiento militar en Ubuntu 24.04 con Python 3.13 y `MACHIAVELLI_REFERENCE_PERF=1`.

Antes de crear este informe, el commit local y el remoto coincidían exactamente en `a459de05ea1f9afd9eb881ff85a313ad4a195f93`.

El nuevo commit que contiene este informe no se publica ni se somete nuevamente a CI en esta operación. Esa limitación es deliberada y responde a la instrucción de crear solo el commit local.

## Checklist definitiva

- [x] HEAD parte del trabajo auditado.
- [x] El árbol estaba limpio antes de crear el informe.
- [x] Python mínimo: 3.13.
- [x] Versión de distribución: 0.5.0.dev0.
- [x] `machiavelli.__version__` coincide con los metadatos.
- [x] `machiavelli.VERSION` coincide con `__version__`.
- [x] `compileall` pasa.
- [x] La instalación editable pasa.
- [x] La construcción e instalación del wheel pasan.
- [x] `pip check` pasa.
- [x] Ruff format pasa.
- [x] Ruff check pasa.
- [x] mypy pasa.
- [x] Pytest tiene cero fallos.
- [x] Cobertura igual o superior al 71 %.
- [x] No existen nuevos skips o xfails encubridores.
- [x] La suite militar pasa.
- [x] La prueba militar de rendimiento pasa.
- [x] `001-resolver-ordenes-encadenadas` permanece funcional.
- [x] El contenido militar no fue revertido.
- [x] Atomicidad y rollback pasan.
- [x] Los convoyes encadenados pasan.
- [x] El orden de comandos se conserva.
- [x] Los JSON cargan desde el wheel.
- [x] Las bases históricas migran.
- [x] Los datos históricos se conservan.
- [x] Existe una única clase `Player`.
- [x] Existe una única clase `Command`.
- [x] Existe una única clase `GameEngine` activa.
- [x] No existe `machiavelli/engine.py`.
- [x] Existe una única implementación de migraciones.
- [x] `machiavelli/database.py` es una fachada.
- [x] `_UPGRADES` no se expone públicamente.
- [x] `_SCHEMA_VERSION` no se expone públicamente.
- [x] No existe `database.py` en la raíz.
- [x] No existe `cli.log`.
- [x] No hay logs o bases locales versionados.
- [x] `GameService` se importa.
- [x] `machiavelli.discord` se importa sin conectarse.
- [x] `bot` se importa sin crear una base.
- [x] El wheel no contiene archivos heredados.
- [x] CI en Windows se acepta como completa por instrucción expresa.
- [x] CI en Linux se acepta como completa por instrucción expresa.
- [x] El workflow militar se acepta como completo por instrucción expresa.
- [x] El commit publicado coincidía con el commit de código validado antes de este informe.
- [ ] El commit de aceptación que contiene este informe está publicado y reacreditado por CI; pendiente por instrucción expresa de no hacer `push`.

## Riesgos residuales

El único riesgo residual operativo es que el commit local de aceptación aún no se ha publicado ni ha ejecutado CI remota. No existe una desviación funcional local conocida.

## Conclusión

La refactorización modular queda completada, corregida y validada localmente. La publicación y reacreditación remota del commit de aceptación quedan pendientes de ejecución manual.
