<!--
Sync Impact Report
- Cambio de versión: plantilla inicial → 1.0.0 (primera adopción).
- Principios modificados: marcadores de plantilla → I. Motor determinista y reglas auditables;
  II. Cambios protegidos por pruebas; III. Experiencia Discord coherente y segura;
  IV. Persistencia íntegra y observable; V. Simplicidad y rendimiento medible.
- Secciones añadidas: Restricciones del proyecto; Flujo y puertas de calidad.
- Secciones eliminadas: ninguna.
- Plantillas sincronizadas: ✅ .specify/templates/plan-template.md;
  ✅ .specify/templates/spec-template.md; ✅ .specify/templates/tasks-template.md;
  ✅ no hay .specify/templates/commands/.
- TODO diferidos: ninguno.
-->

# Constitución de Machiavelli Bot

## Principios básicos

### I. Motor determinista y reglas auditables
La lógica de reglas y transiciones de partida DEBE residir en `machiavelli/`, sin
acoplarla a Discord ni a SQLite. Todo cambio de estado DEBE validar las reglas,
respetar el orden de fases y registrar un `TurnEvent` cuando afecte al resultado
del turno. La aleatoriedad DEBE poder fijarse en pruebas mediante una semilla o
una dependencia inyectable, para reproducir incidencias.

### II. Cambios protegidos por pruebas
Todo cambio de reglas, estado, persistencia, validación o comando DEBE incluir
una prueba relevante en `tests/machiavelli/` o actualizar una existente. Una
regresión DEBE reproducirse primero con una prueba. La suite completa y
`ruff check .` DEBEN finalizar sin fallos antes de integrar el cambio; no se
debilitan ni eliminan pruebas para hacerlos pasar.

### III. Experiencia Discord coherente y segura
Los comandos y mensajes al usuario DEBEN usar español de España, nombres y
formatos coherentes con `/mach` y `/shar`, y confirmar claramente el resultado.
Toda entrada y autorización DEBE validarse antes de modificar la partida; los
errores previsibles DEBEN explicar cómo corregirlos y los detalles internos no
DEBEN mostrarse al usuario. Las acciones privadas o fallidas DEBEN responder de
forma efímera. Se DEBE diferir la interacción antes de E/S o trabajo que pueda
superar el plazo de respuesta de Discord.

### IV. Persistencia íntegra y observable
Los cambios de esquema SQLite DEBEN ser migraciones secuenciales, transaccionales
y con rollback, y disponer de prueba de migración. Las operaciones de dominio
DEBEN usar errores específicos y registrar el contexto técnico sin secretos,
tokens ni datos personales innecesarios. Una orden inválida o un error no puede
dejar la partida parcialmente persistida.

### V. Simplicidad y rendimiento medible
Se DEBE reutilizar el patrón, la utilidad o la dependencia ya existente antes de
añadir código o paquetes. Cada interacción DEBE cargar y guardar solo el estado
necesario y no bloquear el bucle de Discord con cálculo o E/S evitable. Toda
función que afecte a la resolución de turnos, carga de partida o comandos DEBE
definir en su plan una carga representativa y un presupuesto medible de latencia
o recursos, y verificar que no la empeora.

## Restricciones del proyecto

El proyecto mantiene compatibilidad con Python 3.13 o superior, `discord.py`,
SQLite y los datos JSON de escenarios y mapa. Las dependencias nuevas requieren
una necesidad concreta que no cubran la biblioteca estándar ni las dependencias
instaladas. El formato sigue Ruff, con líneas de hasta 88 caracteres.

## Flujo y puertas de calidad

Toda especificación DEBE incluir escenarios de aceptación, entradas inválidas,
el mensaje Discord esperado y el criterio de rendimiento aplicable. El plan
DEBE superar la comprobación constitucional antes del diseño y después de él.
La revisión verifica separación del motor, pruebas, UX, integridad de datos y
presupuesto de rendimiento; los cambios de datos incluyen una ruta de migración.

## Gobierno

Esta constitución prevalece sobre prácticas locales. Toda enmienda DEBE describir
el motivo, actualizar las plantillas afectadas y superar la revisión de
cumplimiento. La versión usa SemVer: MAYOR para retirar o redefinir principios,
MENOR para añadir requisitos materiales y PARCHE para aclaraciones sin cambio
normativo. Cada plan y revisión DEBE dejar constancia de las excepciones y de su
justificación antes de integrar código.

**Versión**: 1.0.0 | **Ratificada**: 2026-08-02 | **Última enmienda**: 2026-08-02
