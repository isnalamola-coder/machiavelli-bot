"""Helpers for loading JSON resources shipped with the Machiavelli package."""

from __future__ import annotations

import json
from importlib.resources import files


class PackageResourceError(RuntimeError):
    """Raised when a packaged JSON resource cannot be read or decoded."""


def read_package_json(filename: str) -> object:
    """Read and decode a UTF-8 JSON resource from the installed package.

    Args:
        filename: Resource name relative to the top-level ``machiavelli`` package.

    Raises:
        PackageResourceError: If the resource is missing, unreadable, or invalid JSON.
    """
    resource = files("machiavelli").joinpath(filename)

    try:
        with resource.open("r", encoding="utf-8") as stream:
            return json.load(stream)
    except json.JSONDecodeError as exc:
        raise PackageResourceError(
            f"El recurso JSON del paquete {filename!r} no contiene JSON válido"
        ) from exc
    except (OSError, UnicodeError) as exc:
        raise PackageResourceError(
            f"No se pudo leer el recurso JSON del paquete {filename!r}"
        ) from exc
