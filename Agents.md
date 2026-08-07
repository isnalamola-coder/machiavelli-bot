# AGENTS.md

## 1. Aclara antes de implementar

Antes de programar, identifica y comunica las suposiciones, ambigüedades y posibles interpretaciones. Expón las alternativas relevantes y sus implicaciones. Cuando una duda pueda modificar el resultado, solicita aclaración antes de continuar. Señala también cualquier enfoque más sencillo que satisfaga los requisitos.

## 2. Aplica la mínima complejidad necesaria

- Implementa únicamente lo exigido por la especificación mediante la solución más sencilla, directa y mantenible que cumpla íntegramente los requisitos.
- No añadas funcionalidades, configuraciones, abstracciones ni indirecciones especulativas.
- No diseñes para casos de uso que no se hayan solicitado.
- No añadas gestión para escenarios que no puedan producirse.
- Si la implementación es considerablemente más extensa o compleja de lo necesario, simplifícala.

## 3. Limita estrictamente el alcance de los cambios

- Modifica únicamente los archivos, componentes y comportamientos necesarios para cumplir la especificación.
- Respeta el estilo y la estructura existentes.
- **No reformatees, limpies ni refactorices código ajeno al cambio.**
- Si detectas problemas no relacionados, documéntalos sin modificarlos.
- Limpia únicamente los residuos introducidos por tu propia implementación.
- Esta prohibido traducir docstrings.
- Esta prohibido eliminar/modificar comentarios pre-existentes, a no ser que el codigo al que fuera asociados se haya eliminado/modificado.

## 4. Desarrolla de forma incremental y sostenible

- Construye primero la versión funcional más pequeña que cubra el flujo completo. Añade capacidades posteriores sobre una base que permanezca operativa en cada etapa.
- La solución inicial debe ser sencilla, pero no provisional ni deliberadamente desechable. Debe encajar en la arquitectura prevista y poder mantenerse sin requerir una sustitución inmediata.

## 5. Reutiliza antes de implementar

Sigue este orden de preferencia:

1º Utiliza las funciones y dependencias que ya existan en el proyecto.
2º Comprueba su documentación, tipos y capacidades antes de descartarlas.
3º Cuando sea necesario añadir una dependencia, elige una biblioteca consolidada y correctamente mantenida.
4º Implementa una solución propia únicamente cuando las alternativas anteriores no sean adecuadas y exista una justificación clara.

## 6. Mantén una arquitectura modular

- Conserva responsabilidades claramente separadas y componentes con límites definidos. 
- Introduce modularidad cuando reduzca la complejidad real, facilite las pruebas o permita separar responsabilidades, pero evita abstracciones creadas únicamente para anticipar necesidades futuras.

## 7. Elimina la compatibilidad obsoleta

- No conserves compatibilidad con versiones, rutas o formatos retirados, salvo que la especificación lo exija expresamente.
- Elimina las rutas obsoletas en lugar de añadir capas de compatibilidad, soluciones alternativas o conversiones de datos heredados. 

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


