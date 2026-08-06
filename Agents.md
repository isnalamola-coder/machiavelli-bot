# AGENTS.md

- No mantengas la compatibilidad con versiones anteriores. Elimina las rutas
  obsoletas en lugar de añadir capas de compatibilidad, soluciones alternativas o
  conversiones de datos heredados. Los cambios obligatorios del esquema SQLite sí
  usan las migraciones secuenciales, transaccionales y reversibles exigidas por la
  constitución del proyecto, sin conservar formatos retirados salvo que la spec lo
  exija expresamente.

- Elige la implementación más sencilla que cumpla plenamente los requisitos
  actuales. Evita abstracciones, configuraciones e indirecciones especulativas.

- Haz crecer el sistema por capas. Empieza por la versión más pequeña que funcione
  de principio a fin y añade cada nueva capacidad sobre un producto que ya funcione.
  Nunca sacrifiques un producto operativo por una complejidad inacabada.

- Mantén los componentes modulares y las responsabilidades claramente separadas.

- Da preferencia a bibliotecas consolidadas y bien mantenidas cuando reduzcan la
  complejidad global o mejoren la fiabilidad. No vuelvas a implementar
  funcionalidades comunes sin un motivo claro.

- Aprovecha las dependencias que ya existen en el proyecto antes de escribir una
  implementación propia o añadir paquetes. No des por hecho que una biblioteca
  carece de una función sin consultar antes su documentación y sus tipos.

- Toma decisiones arquitectónicas pensando a largo plazo. No aceptes una solución
  provisional que solo funcione por ahora y esté pensada para sustituirse más
  adelante.

## Contexto técnico activo

- Python 3.13 o superior, con tipado moderno; `discord.py` y `python-dotenv` son las
  únicas dependencias de ejecución actuales.
- SQLite es la persistencia canónica. Todo cambio de esquema debe pasar por
  `machiavelli/db/database.py` y disponer de prueba de migración y rollback.
- pytest, Ruff y mypy forman la puerta de calidad. No añadas otra herramienta o
  dependencia si la biblioteca estándar o una dependencia instalada ya resuelve el
  caso.
- Discord es un adaptador: no abre SQLite ni construye repositorios. La E/S, carga,
  ejecución, reporte y guardado síncronos permanecen juntos fuera del event loop.

## Feature activa: eventos de turno y reglas de escenario

- Fuente de diseño: [plan de implementación](specs/002-eventos-turno-reglas/plan.md)
  y [contrato de eventos](specs/002-eventos-turno-reglas/contracts/turn-events.md).
- `TurnEvent` es el único valor de evento. Valida payloads JSON al crear y cargar;
  no introduzcas subclases por tipo, registros dinámicos ni Pydantic.
- `Game.turn_events` contiene objetos `TurnEvent`. No añadas mensajes, Markdown ni
  registros `tipo|json` al dominio o al motor.
- `TurnReporter` pertenece a servicios y es el único propietario de la presentación
  del historial para Discord.
- La evolución v4 elimina y recrea únicamente `game_events`: persiste `event_type` y
  `data_json`, no convierte la columna histórica `message` y no mantiene una ruta de
  lectura antigua.
- Las reglas `fortress_active`, `assassinations_active`, `famine_active`,
  `first_turn_famine` y `plague_active` deben impedir estado, cobros, fases y eventos
  residuales cuando estén desactivadas.
