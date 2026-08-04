# ADR 0001: Origen único de la versión del paquete

- Estado: Aceptado
- Fecha: 2026-08-04

## Contexto

El proyecto llegó a exponer versiones distintas en los metadatos de distribución, el código Python y la documentación. Mantener literales independientes permite que una instalación informe una versión diferente de la declarada por el wheel o el sdist.

## Decisión

`pyproject.toml`, dentro de `[project].version`, es la única fuente de verdad para la versión distribuida.

En runtime, `machiavelli.__version__` obtiene esa versión mediante:

```python
from importlib.metadata import version

version("machiavelli")
```

`machiavelli.VERSION` se conserva temporalmente como alias de compatibilidad de `machiavelli.__version__`.

Cuando el código se ejecute sin una distribución instalada, se permite un único fallback que coincida con la versión de desarrollo declarada en `pyproject.toml`.

Queda prohibido añadir constantes de versión manuales adicionales o usar `pkg_resources` para esta finalidad.

## Consecuencias

- Los metadatos instalados y la API Python informan la misma versión.
- Un cambio de versión se realiza primero en `pyproject.toml` y actualiza el fallback solo cuando sea necesario para ejecución sin instalación.
- Los tests deben comparar `machiavelli.__version__`, `machiavelli.VERSION` e `importlib.metadata.version("machiavelli")`.
