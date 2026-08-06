# ADR 0003: Preservación de la resolución militar

- Estado: Aceptado
- Fecha: 2026-08-04

## Contexto

La resolución militar encadenada define comportamiento crítico y transaccional. El cierre de la refactorización modular debe eliminar duplicaciones arquitectónicas sin sustituir, simplificar ni rebajar la implementación ya validada.

## Decisión

La especificación `specs/001-resolver-ordenes-encadenadas` se conserva íntegramente como norma de la resolución militar.

El cierre modular no modifica sus reglas, incluidas la resolución atómica, las dependencias encadenadas, convoyes, apoyos, transportes, conversiones, rebeliones, asedios, desalojos, retiradas, determinismo, rollback y conservación del orden persistido.

También forman parte de la semántica válida las validaciones compatibles añadidas posteriormente:

- rechazo de una ruta de convoy con algún `target=None`;
- rechazo explícito de una transportadora inexistente;
- acceso obligatorio al mapa mediante `Game.require_map()`;
- soporte de unidades o guarniciones sin jugador asociado;
- ajustes de tipos necesarios para Python 3.13 y mypy.

Cualquier cambio militar futuro debe disponer de una especificación propia o una ampliación normativa explícita y de tests de regresión específicos.

Los cambios militares no se mezclan en el mismo commit con CI, formato, lint, tipado, empaquetado o documentación.

## Consecuencias

- La refactorización arquitectónica no puede usarse para alterar reglas militares.
- No se permiten `skip`, `xfail`, exclusiones ni límites relajados para ocultar regresiones.
- La suite militar y su prueba de rendimiento de referencia siguen siendo barreras obligatorias.
- Un cambio futuro debe demostrar atomicidad, rollback, determinismo y compatibilidad persistida antes de integrarse.
