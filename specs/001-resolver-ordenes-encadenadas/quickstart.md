# Quickstart: Validación de la resolución militar atómica

## Prerequisites

- Python 3.13 o superior.
- Dependencias del proyecto y de desarrollo instaladas.
- Ejecutar desde la raíz del repositorio.
- La puerta temporal solo es normativa en el job dedicado Ubuntu 24.04 con CPython
  3.13, sin cobertura ni paralelismo; el resto de entornos ejecuta la validación
  funcional sin umbral temporal.

## 1. Persistencia ordenada

```powershell
python -m pytest -q tests/machiavelli/test_game.py -k "command and order"
```

Resultado esperado:

- Un Advance, tres Advance, dos actores y dos jugadores conservan el orden.
- Guardar-cargar-guardar y cargas consecutivas producen las mismas rutas.
- La prueba usa el esquema actual y no ejecuta migración nueva.

## 2. Modelos, compilación y validación

```powershell
python -m pytest -q tests/machiavelli/engine/test_military.py -k "index or compile or valid"
```

Resultado esperado:

- Duplicados abortan antes de compilar.
- Cada unidad obtiene una orden lógica.
- Los siete códigos tienen representación.
- Support acepta `<lugar>`/`<lugar> (<potencia>)` y Transport acepta `A <origen>`;
  las demás variantes producen Hold inválido solo para el emisor.
- Las costas exactas y el snapshot permanecen intactos.

## 3. Convoyes y conflictos

```powershell
python -m pytest -q tests/machiavelli/engine/test_military.py -k "convoy or transport or conflict or crossing"
```

Resultado esperado:

- Convoy válido de una o varias flotas termina solo en destino final.
- Convoy inválido o roto termina solo en origen.
- Empate, ataque fallido y victoria defensiva mantienen la transportadora; solo su
  desalojo rompe toda la ruta.
- Convoyes no forman cruces; unidades propias sí pueden intercambiar posiciones.

## 4. Apoyos, ciclos, rebeliones y asedios

```powershell
python -m pytest -q tests/machiavelli/engine/test_military.py -k "support or cycle or rebellion or siege or conversion"
```

Resultado esperado:

- Se resuelven primero conflictos independientes.
- Si el emisor de un Support es desalojado, su orden se cancela, desaparece de
  `active_supports` y la reconstrucción global modifica correctamente el conflicto
  que recibía esa fuerza.
- Los dos escalones de cancelación de Support rompen dependencias circulares.
- Un ciclo irresoluble produce el mismo `CycleDiagnostic` estructurado bajo
  permutaciones de jugadores, colecciones y cargas sucesivas.
- Una orden cancelada no actúa como Hold.
- Rebeliones urbanas y provinciales aportan fuerza solo al conflicto provincial.
- Asedios y conversiones respetan ciudad, puerto, restricciones y desalojo.

## 5. Atomicidad y desalojos

```powershell
python -m pytest -q tests/machiavelli/engine/test_military.py -k "atomic or dislodg or retreat or unresolved"
python -m pytest -q tests/machiavelli/engine/test_core.py -k "military or dislodg or order"
```

Resultado esperado:

- Excepciones y ciclos conservan el snapshot militar; el diagnóstico del ciclo
  contiene etapa, iteraciones, conflictos pendientes ordenados y firma canónica.
- Fallos al construir o serializar el evento conservan snapshot y eventos previos.
- Un `ResolutionState` inyectado con un conflicto efectivo pendiente lanza un error
  militar tipado antes de invocar al gestor, construir o añadir el evento o sustituir
  colecciones.
- Un gestor válido se invoca antes de aplicar y antes de fases posteriores.
- Gestor ausente, fallido o incompleto impide aplicar y detiene la campaña.
- Una guarnición independiente desalojada exige una decisión explícita del gestor.
- Los lugares disputados contienen solo conflictos reales y ambos extremos de cruces.

## 6. Evento auditable y contratación

```powershell
python -m pytest -q tests/machiavelli/test_game.py -k "military_event or rebelled_city_recruitment"
```

Resultado esperado:

- Guardar-cargar conserva las seis listas del registro `military_resolution|`.
- Una ciudad rebelde rechaza contratar guarnición sin cobrar ducados.
- La misma contratación sin rebelión usa el flujo y coste existentes.

## 7. Límite Discord

```powershell
python -m pytest -q tests/machiavelli/test_discord.py -k "run_game"
```

Resultado esperado:

- `run_game` delega una sola función síncrona mediante `asyncio.to_thread()`.
- La función worker abre y cierra SQLite, carga y guarda el `Game` y devuelve solo
  `tuple[str, ...]`; ni la conexión ni objetos mutables cruzan la frontera.
- El éxito borra la respuesta efímera diferida y publica el reporte.
- Cada categoría de error militar responde efímeramente con el prefijo de atomicidad
  y una acción correctiva específica, sin clases, trazas, rutas, líneas ni
  `CycleDiagnostic`.
- El detalle técnico solo queda en logging.

## 8. Rendimiento y determinismo

Prueba funcional, válida en cualquier entorno:

```powershell
python -m pytest -q tests/machiavelli/engine/test_military.py -k "representative_resolution_determinism"
```

Resultado esperado:

- Cinco juegos frescos de 30 unidades, 60 filas, 20 conflictos, convoy de 5 flotas y
  dos desalojos producen exactamente la misma resolución, evento y snapshot final.
- El gestor determinista aplica una retirada válida y una eliminación `None`.
- Esta prueba no usa el tiempo como puerta.

Puerta temporal del entorno de referencia:

```powershell
$env:MACHIAVELLI_REFERENCE_PERF = "1"
python -m pytest -q tests/machiavelli/engine/test_military.py -k "representative_resolution_budget"
```

Resultado esperado en el job dedicado Ubuntu 24.04 con CPython 3.13, sin cobertura ni
paralelismo:

- Se mide únicamente `MilitaryResolver.run()` con el gestor determinista incluido.
- Cada una de las cinco ejecuciones tarda menos de 1 segundo; no se usa promedio.
- Fuera del job de referencia, esta prueba temporal se omite y la prueba funcional
  anterior sigue siendo obligatoria.

## 9. Aceptación integrada e invariancia de orden

```powershell
python -m pytest -q tests/machiavelli/engine/test_military.py -k "integrated_military_acceptance or incidental_order"
```

Resultado esperado:

- La campaña integrada incluye movimientos relacionados, Support dependiente,
  Convert, convoy, cancelación, rebelión, asedio, lugar disputado y una retirada
  resuelta por un gestor determinista.
- Cada variante crea un `Game` fresco y solo altera el orden incidental de jugadores
  y colecciones físicas; el orden relativo de los Advance de un mismo actor permanece
  intacto.
- Todas las variantes producen exactamente el mismo `MilitaryResolution`, las mismas
  seis listas del evento y el mismo snapshot final.
- Cada unidad tiene un único resultado, el estado se aplica una sola vez y no se
  observa ningún estado intermedio.
- Esta prueba cierra los tres escenarios de aceptación de US1 y demuestra SC-002 para
  cancelaciones, rebeliones, asedios, lugares disputados y retiradas.

## 10. Puertas completas

```powershell
python -m pytest -q
ruff check .
```

Ambos comandos deben finalizar sin fallos antes de integrar.
