# Quickstart: Validación de la resolución militar atómica

## Prerequisites

- Python 3.13 o superior.
- Dependencias del proyecto y de desarrollo instaladas.
- Ejecutar desde la raíz del repositorio.

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
- Las costas exactas y el snapshot permanecen intactos.

## 3. Convoyes y conflictos

```powershell
python -m pytest -q tests/machiavelli/engine/test_military.py -k "convoy or transport or conflict or crossing"
```

Resultado esperado:

- Convoy válido de una o varias flotas termina solo en destino final.
- Convoy inválido o roto termina solo en origen.
- Una transportadora empatada sigue disponible; una desalojada rompe toda la ruta.
- Convoyes no forman cruces; unidades propias sí pueden intercambiar posiciones.

## 4. Apoyos, ciclos, rebeliones y asedios

```powershell
python -m pytest -q tests/machiavelli/engine/test_military.py -k "support or cycle or rebellion or siege or conversion"
```

Resultado esperado:

- Se resuelven primero conflictos independientes.
- Los dos escalones de cancelación de Support rompen dependencias circulares.
- Una orden cancelada no actúa como Hold.
- Rebeliones urbanas y provinciales aportan fuerza solo al conflicto provincial.
- Asedios y conversiones respetan ciudad, puerto, restricciones y desalojo.

## 5. Atomicidad y desalojos

```powershell
python -m pytest -q tests/machiavelli/engine/test_military.py -k "atomic or dislodg or retreat or unresolved"
python -m pytest -q tests/machiavelli/engine/test_core.py -k "military or dislodg or order"
```

Resultado esperado:

- Excepciones y ciclos conservan el snapshot militar.
- Un gestor válido se invoca antes de aplicar y antes de fases posteriores.
- Gestor ausente, fallido o incompleto impide aplicar y detiene la campaña.
- Los lugares disputados contienen solo conflictos reales y ambos extremos de cruces.

## 6. Límite Discord

```powershell
python -m pytest -q tests/machiavelli/test_discord.py -k "run_game"
```

Resultado esperado:

- El éxito publica el reporte.
- Un error militar responde efímeramente con el texto aprobado.
- El detalle técnico solo queda en logging.

## 7. Rendimiento y determinismo

```powershell
python -m pytest -q tests/machiavelli/engine/test_military.py -k "representative_resolution_budget"
```

Resultado esperado:

- Cinco ejecuciones de 30 unidades, 60 filas, 20 conflictos y convoy de 5 flotas
  producen exactamente la misma resolución.
- Cada ejecución tarda menos de 1 segundo en el entorno de referencia.

## 8. Puertas completas

```powershell
python -m pytest -q
ruff check .
```

Ambos comandos deben finalizar sin fallos antes de integrar.
