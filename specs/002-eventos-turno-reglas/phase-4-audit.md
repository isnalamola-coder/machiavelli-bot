# Auditoría de la fase 4

Fecha de verificación: 2026-08-05  
Intérprete: CPython 3.13.9  
Revisión Git actual: `2ef6b37ff1c7144285d31ab76547b4c01337dfd6`

## Alcance

Este documento separa el estado funcional verificable de T023–T030 de la secuencia
histórica TDD exigida por T023, T025, T027 y T029. No presenta una reproducción
retrospectiva como prueba de que las pruebas originales se ejecutaron en rojo antes
de la implementación productiva.

## Límite de certificación histórica

No existe una revisión Git inmutable que represente exactamente el estado posterior
a T022 y anterior a las pruebas de fase 4. Tampoco se conservaron:

- un worktree con únicamente T023, T025, T027 y T029;
- la salida roja original de esas cuatro tareas;
- un commit de pruebas separado de T024, T026, T028 y T030;
- un registro de comandos fechado que demuestre el orden rojo → implementación →
  verde.

Los tests, el reporter, la integración de servicio, los cambios de Discord y las
marcas de tareas coexistían en el árbol de trabajo. Por tanto, T023, T025, T027 y
T029 permanecen sin marcar en `tasks.md`, aunque su cobertura actual sea verde. Las
tareas productivas T024, T026, T028 y T030 están implementadas, pero el checkpoint de
fase no se considera históricamente certificado mientras sus pruebas predecesoras no
tengan evidencia verificable.

Crear ahora una base antigua y ejecutar allí las pruebas demostraría capacidad de
detección, no la cronología original. Esta auditoría no fabrica ni retrofecha esa
evidencia.

## Correcciones de cobertura verificables

La revisión actual refuerza las pruebas en los puntos que antes no estaban protegidos:

- `game_report` y `run_game` parchean `_chunk_lines()`, comprueban una única llamada
  con el reporte del worker y verifican el envío ordenado de cada chunk con
  `ephemeral=True` y `ephemeral=False`, respectivamente.
- Una tabla exhaustiva `EventType -> tuple[str, ...]` contiene las líneas españolas
  completas esperadas para el payload fixture de cada uno de los 26 tipos. La prueba
  compara por igualdad los conjuntos de la tabla, el fixture y `EventType`, y después
  compara exactamente las líneas renderizadas; una salida genérica o en inglés ya no
  puede satisfacer T023.
- Cada tipo de evento mantiene además la prohibición de incluir el payload completo
  como JSON compacto, JSON con separadores normales, representación del mapping
  congelado, materialización superficial o representación Python del árbol JSON
  nativo.
- La resolución de identificadores conocidos se comprueba en dos líneas completas y
  separadas. La asignación exige exactamente `<@101> (Florence) recibe la potencia
  Florence.` y el soborno usa `A milan`, exigiendo exactamente la mención, el jugador,
  la potencia, el gasto, `Ejército` y `Milan` por sus rutas semánticas respectivas.
- El caso militar compara por igualdad la lista completa de siete líneas: dos
  outcomes, orden cancelada, convoy roto, desalojo, rebelión y asedio. Esto protege
  una línea por elemento, el orden de los seis grupos y todos los campos públicos,
  incluida `Croatia (N)`.

## Ejecución roja real durante esta corrección

Al añadir la aserción completa de costa se ejecutó, antes de modificar el renderer:

```text
py -3.13 -m pytest -q tests/machiavelli/services/test_turn_reporter.py tests/machiavelli/services/test_game_service.py tests/machiavelli/test_discord.py

FAILED tests/machiavelli/services/test_turn_reporter.py::test_military_resolution_renders_every_item_in_canonical_group_order
Esperado: Croatia (N)
Obtenido: Croatia
1 failed, 38 passed, 57 warnings, 4 subtests passed in 1.21s
```

La causa era que `_location()` resolvía primero la clave exacta `croat N` y devolvía
solo su nombre público, descartando el sufijo de costa. Se corrigió la ruta exacta
para conservar `(<costa>)` después de neutralizar el código.

Esta ejecución roja es evidencia de la corrección puntual realizada el 2026-08-04.
No certifica que T025 se ejecutara en rojo antes de la implementación original de la
fase 4, ni cubre retrospectivamente la cronología de T023, T027 o T029.

## Estado verde reproducible

Puerta focalizada de fase 4 tras la corrección:

```text
py -3.13 -m pytest -q tests/machiavelli/services/test_turn_reporter.py tests/machiavelli/services/test_game_service.py tests/machiavelli/test_discord.py
39 passed, 58 warnings, 4 subtests passed in 1.02s
```

Calidad estática y formato de los archivos afectados:

```text
py -3.13 -m ruff format --check machiavelli/services/turn_reporter.py tests/machiavelli/services/test_turn_reporter.py tests/machiavelli/test_discord.py
3 files already formatted

py -3.13 -m ruff check .
All checks passed!

py -3.13 -m mypy machiavelli
Success: no issues found in 39 source files
```

Puerta completa del repositorio:

```text
py -3.13 -m pytest -q
469 passed, 1 skipped, 59 warnings, 88 subtests passed in 18.16s
```

Las advertencias proceden de `discord.utils.escape_markdown()` en la versión instalada
de `discord.py`; no son fallos de la fase.

## Estado de certificación

- T023: cobertura funcional actual exhaustiva para los 26 tipos, idioma español,
  identificadores y ausencia de representaciones técnicas; secuencia roja original
  no certificable.
- T024: implementación funcional presente y verde.
- T025: cobertura militar actual compara las siete líneas completas y los seis grupos;
  existe una ejecución roja real para la corrección de costa, pero no evidencia
  completa de la cronología original.
- T026: implementación militar corregida y verde.
- T027: cobertura funcional actual verde; secuencia roja original no certificable.
- T028: integración de servicio funcional y verde.
- T029: cobertura de errores y chunking actual reforzada y verde; secuencia roja
  original no certificable.
- T030: manejo seguro de errores en Discord funcional y verde.

En consecuencia, las pruebas actuales demuestran íntegramente los requisitos
funcionales de T023–T030 y el producto cumple el contrato comprobado. La fase 4 no se
declara cerrada únicamente como checkpoint TDD histórico, porque no existe evidencia
conservada de la secuencia roja original de T023, T025, T027 y T029.
