# Especificación de feature: Resolución militar atómica

**Feature Branch**: `N/A (001-resolver-ordenes-encadenadas)`

**Created**: 2026-08-02

**Status**: Draft

**Input**: Plan definitivo y notas prioritarias para transportes, órdenes Advance
encadenadas, conflictos, rebeliones, asedios y retiradas.

## Clarifications

### Session 2026-08-02

- Q: ¿Qué Hold puede someter una rebelión provincial? → A: Cualquier Hold efectivo
  —explícito, por ausencia de orden o derivado de una orden inválida—; una orden
  cancelada nunca.
- Q: ¿Cómo se integra la fase de retiradas cuando hay desalojos? → A: Las retiradas
  se resuelven inmediatamente en la misma campaña mediante un gestor de desalojos
  cuya implementación queda fuera del alcance de esta feature.
- Q: ¿Qué localizaciones quedan prohibidas como destino de retirada? → A: Solo los
  espacios disputados efectivamente por dos o más facciones; un cruce registra sus
  dos extremos.
- Q: ¿En qué espacio aporta fuerza una rebelión urbana? → A: Solo en el conflicto
  provincial; en la ciudad únicamente bloquea acciones y requiere asedio.
- Q: ¿Qué ataque cancela un Support al romper una dependencia circular? → A:
  Cualquier Advance válido, activo y no cancelado contra quien apoya, directo o por
  convoy disponible, cuyo origen sea distinto del lugar apoyado.
- Q: ¿Qué formato persistido usan Support y Transport? → A: Support usa
  `<lugar>` o `<lugar> (<potencia>)`; Transport usa `A <origen>` y se enlaza al
  ejército único que ocupaba ese origen en el snapshot.
- Q: ¿Qué parte de Support pertenece al MVP de US1? → A: Compilación, geometría y
  fuerza de Supports no dependientes; cortes, propagación y ciclos permanecen en
  US3.
- Q: ¿Qué ocurre con una guarnición independiente desalojada sin política externa?
  → A: La resolución aborta y conserva el snapshot completo; solo un gestor que
  devuelva una decisión explícita para ella permite aplicar el turno.
- Q: ¿Dónde se bloquea la contratación en una ciudad rebelde? → A: En el flujo de
  reclutamiento de mantenimiento ya existente, además de bloquear Convert en la
  adjudicación militar.
- Q: ¿Cuándo se registra el evento militar? → A: Se construye y valida antes del
  commit y su registro auditable se incluye en la misma sustitución atómica que el
  estado militar.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Resolver una campaña sin estados parciales (Priority: P1)

Como participante, quiero que todas las órdenes militares del turno se interpreten
antes de cambiar el tablero, para que el resultado sea coherente aunque varios
conflictos dependan entre sí.

**Why this priority**: Es la garantía básica de integridad del turno y evita que el
orden de lectura de jugadores u órdenes cambie el resultado.

**Independent Test**: Puede verificarse con una campaña que contenga movimientos,
apoyos y conversiones encadenados, comprobando que el resultado final es único y
que cualquier error conserva íntegro el estado inicial.

**Acceptance Scenarios**:

1. **Given** varias unidades con órdenes relacionadas, **When** se resuelve la fase
   militar, **Then** cada unidad aporta una única orden lógica y el estado físico se
   sustituye una sola vez después de obtener un resultado completo.
2. **Given** las mismas órdenes cargadas con jugadores o colecciones internas en un
   orden diferente, **When** se resuelve la campaña, **Then** se obtiene exactamente
   el mismo resultado, los mismos conflictos registrados y las mismas retiradas.
3. **Given** un estado inicial militar duplicado o una dependencia que no puede
   resolverse de forma determinista, **When** se intenta adjudicar, **Then** no se
   aplica ningún cambio militar parcial y el fallo queda diagnosticado.

---

### User Story 2 - Ejecutar un convoy encadenado y atómico (Priority: P1)

Como jugador, quiero expresar una ruta de transporte mediante varios Advance del
mismo ejército, para que una o varias flotas puedan llevarlo hasta un único destino
sin ocupar los tramos intermedios.

**Why this priority**: Es la capacidad central solicitada y requiere preservar la
identidad y el origen de todas las unidades durante la adjudicación.

**Independent Test**: Puede verificarse con un ejército, una ruta de dos mares y dos
flotas transportadoras; el ejército debe aparecer solo en destino si todo el convoy
tiene éxito y solo en origen si cualquier dependencia falla.

**Acceptance Scenarios**:

1. **Given** varios Advance ordenados para un ejército, una provincia de destino y
   una flota con Transport correcto en cada posición intermedia, **When** ninguna
   transportadora es desalojada y el ejército gana su conflicto final, **Then** el
   ejército termina en la provincia final sin ocupar ninguna posición intermedia.
2. **Given** un convoy válido cuya transportadora pierde y es desalojada, **When** se
   recalculan los conflictos, **Then** se cancela el convoy completo, el ejército
   permanece físicamente en su origen y deja de participar en el destino final.
3. **Given** una transportadora atacada cuyo conflicto termina en empate o victoria
   defensiva, **When** se resuelve el convoy, **Then** el transporte sigue disponible.
4. **Given** una ruta que repite una posición o transportadora, **When** todos sus
   tramos y órdenes Transport son válidos, **Then** la repetición por sí sola no
   invalida el convoy.

---

### User Story 3 - Resolver dependencias y cancelaciones (Priority: P1)

Como participante, quiero que los conflictos independientes se resuelvan primero y
que sus cancelaciones se propaguen, para que apoyos, transportes y regresos alteren
correctamente los conflictos restantes.

**Why this priority**: Sin esta propagación, un convoy roto, un apoyo cortado o una
unidad desalojada pueden producir un ganador incorrecto en otra localización.

**Independent Test**: Puede verificarse con una cadena donde el primer conflicto
desaloja una flota Transport, rompe un convoy y cambia el empate o ganador tanto en
el origen como en el destino del ejército.

**Acceptance Scenarios**:

1. **Given** conflictos independientes y dependientes, **When** se adjudica una
   iteración, **Then** se resuelven primero los independientes, se cancelan las
   órdenes derrotadas o afectadas y se reconstruyen los conflictos pendientes sin
   ejecutar las órdenes canceladas.
2. **Given** una orden Advance cancelada, **When** la unidad vuelve físicamente a su
   origen, **Then** puede defender su ocupación pero no ejecuta un Hold ni somete una
   rebelión.
3. **Given** una dependencia circular sin conflictos independientes, **When** se
   aplica el desempate circular, **Then** primero se cancelan los apoyos atacados
   por cualquier Advance válido, activo y no cancelado —directo o por convoy
   disponible— cuyo origen sea distinto del lugar apoyado, sin exigir una fuerza
   mínima; si no basta, se cancelan todos los apoyos y se continúa la adjudicación.
4. **Given** un ciclo que persiste incluso después del desempate completo, **When**
   no existe una siguiente resolución determinista, **Then** la fase falla sin
   aplicar resultados.

---

### User Story 4 - Aplicar rebeliones y asedios (Priority: P2)

Como participante, quiero que rebeliones y asedios modifiquen fuerzas y control sin
convertirse en unidades ficticias, para que sus efectos respeten las reglas de la
campaña.

**Why this priority**: Estas reglas cambian la fuerza de los conflictos, restringen
órdenes válidas y pueden eliminar guarniciones o rebeliones.

**Independent Test**: Puede verificarse con una provincia rebelde, una ciudad
fortificada y una guarnición, recorriendo pacificación, sometimiento, liberación,
inicio de asedio, asedio completo y levantamiento.

**Acceptance Scenarios**:

1. **Given** una rebelión provincial contra su controlador, **When** varias facciones
   disputan la provincia, **Then** cada participante salvo el controlador recibe un
   punto adicional y la rebelión no crea por sí misma un conflicto ni bloquea el
   movimiento.
2. **Given** una rebelión urbana, **When** se disputan simultáneamente provincia y
   ciudad, **Then** añade un punto a los participantes elegibles de la provincia,
   pero no modifica la fuerza del conflicto de ciudad.
3. **Given** una rebelión provincial, **When** el controlador completa con éxito un
   Hold efectivo y no cancelado, ya sea explícito, por ausencia de orden o derivado
   de una orden inválida, **Then** la rebelión queda sometida.
4. **Given** una rebelión, **When** otra facción avanza con éxito a la provincia,
   **Then** la rebelión queda liberada; **When** se paga el gasto de pacificación
   aplicable, **Then** queda pacificada.
5. **Given** una ciudad rebelde, **When** el controlador intenta convertir o contratar
   una guarnición, **Then** la acción es inválida; **When** completa un asedio como
   contra una guarnición, **Then** la rebelión termina.
6. **Given** una guarnición o rebelión de ciudad elegible, **When** una unidad inicia
   y después completa el asedio, **Then** el primer asedio registra la ciudad y el
   segundo elimina al objetivo y termina el asedio.
7. **Given** un asedio activo, **When** la unidad asediadora levanta el asedio o es
   desalojada, **Then** el asedio termina sin eliminar la guarnición.

---

### User Story 5 - Conservar retiradas y lugares disputados (Priority: P2)

Como participante desalojado, quiero que mi unidad y los lugares donde hubo
conflicto se entreguen inmediatamente al gestor de desalojos, para completar la
retirada antes de que continúen las fases posteriores de la campaña.

**Why this priority**: La adjudicación no está completa si un desalojo borra la
identidad de la unidad o permite retirarse a un lugar que estuvo en conflicto.

**Independent Test**: Puede verificarse provocando un desalojo y comprobando que el
gestor recibe la unidad y los lugares disputados antes de hambre, control o cambio
de estación, y que la campaña no continúa hasta que termina.

**Acceptance Scenarios**:

1. **Given** una unidad desalojada, **When** finaliza la adjudicación, **Then** deja de
   ocupar el tablero, conserva identidad, propietario, tipo y origen, y queda en la
   colección entregada inmediatamente al gestor de desalojos.
2. **Given** uno o varios conflictos durante la fase, **When** se prepara la retirada,
   **Then** cada espacio disputado efectivamente por dos o más facciones queda
   registrado como destino no válido; un cruce registra ambos extremos.
3. **Given** una guarnición independiente desalojada, **When** el gestor no existe o
   no devuelve una decisión explícita para ella, **Then** la resolución completa
   aborta, conserva íntegramente el snapshot militar inicial y los eventos previos,
   y no crea ninguna colección persistida o transitoria de pendientes.
4. **Given** una adjudicación con desalojos y un gestor no disponible o fallido,
   **When** se intenta continuar la campaña, **Then** no se ejecutan hambre, control
   ni cambio de estación y no se consolida un estado militar incompleto.
5. **Given** que el administrador ejecuta el turno desde Discord, **When** se cargan
   la partida, el motor y el guardado, **Then** la operación síncrona completa se
   ejecuta fuera del event loop; la conexión SQLite y el `Game` permanecen en ese
   worker y solo regresan el reporte inmutable o una excepción tipada.

---

### User Story 6 - Preservar el orden declarado (Priority: P3)

Como jugador, quiero que mis Advance encadenados se reconstruyan en el mismo orden
en que fueron guardados, para que el convoy represente exactamente la ruta enviada.

**Why this priority**: La ruta depende del orden relativo de varias filas, aunque
pertenezcan al mismo actor y estén intercaladas con otras órdenes.

**Independent Test**: Puede verificarse guardando, cargando y volviendo a guardar
órdenes de dos actores y dos jugadores varias veces; cada ruta debe permanecer
idéntica.

**Acceptance Scenarios**:

1. **Given** tres Advance del mismo ejército intercalados con órdenes ajenas, **When**
   se cargan y compilan, **Then** conservan su secuencia persistida relativa.
2. **Given** dos cargas consecutivas o un ciclo guardar-cargar-guardar, **When** se
   comparan las órdenes, **Then** no cambia la ruta de ningún actor ni se mezclan
   órdenes entre jugadores.

### Edge Cases

- Una unidad sin orden recibe Hold; una combinación incompatible se considera
  inválida y sigue la política existente de Hold. Ambos Holds efectivos pueden
  someter una rebelión, pero una orden cancelada durante la resolución nunca se
  transforma en Hold.
- Un único Advance de ejército hacia mar, o hacia una provincia no alcanzable por
  tierra, no constituye un convoy y no se ejecuta parcialmente.
- El destino final de un convoy de ejército nunca puede ser mar.
- Una flota extranjera puede transportar un ejército si ambas declaraciones
  coinciden; una flota solo puede declarar un ejército transportado.
- El `target` persistido de Transport es exactamente `A <origen>`; no incluye
  potencia porque el snapshot admite un único ejército en ese origen. El `target`
  de Support es `<lugar>` para la facción propia o `<lugar> (<potencia>)` para otra
  facción, con un único espacio antes del paréntesis.
- Una flota en la provincia final no convierte un movimiento terrestre normal en
  convoy ni cuenta como punto intermedio.
- Los cruces solo se aplican a movimientos directos. Dos unidades del mismo jugador
  pueden intercambiar posiciones y ese cruce no es autoconflicto.
- Un destino no disputado de Advance o Convert y una posición evaluada con una sola
  facción no se consideran lugares de conflicto para las retiradas.
- Un autoconflicto sí ocurre cuando dos unidades de la misma facción disputan
  efectivamente el mismo espacio distinto de un intercambio válido.
- Provincia y ciudad fortificada son espacios de conflicto diferentes y pueden
  estar ocupados simultáneamente.
- Cualquier rebelión de la localización modifica únicamente el conflicto provincial;
  una rebelión urbana no añade fuerza al conflicto de ciudad.
- Una flota conserva su costa exacta para movimiento e identidad, aunque el conflicto
  territorial agrupe las costas de una misma provincia.
- Una conversión compite por el espacio de destino, puede empatar o perder, y es
  inválida bajo asedio o frente a una ciudad rebelde cerrada.
- Una guarnición bajo asedio solo puede hacer Hold o apoyar su provincia; la unidad
  asediadora solo puede asediar, hacer Hold o levantar el asedio.
- Una flota solo puede asediar o convertirse donde la ciudad tenga puerto.
- Un ataque empatado contra una unidad que apoya corta el apoyo salvo cuando el
  apoyo se dirige al origen de ese ataque.
- Al romper una dependencia circular, basta cualquier Advance válido, activo y no
  cancelado contra quien apoya desde un origen distinto del lugar apoyado; puede ser
  directo o por convoy disponible y no necesita alcanzar una fuerza mínima.
- Un estado inicial con ocupaciones incompatibles aborta antes de interpretar
  órdenes y no se degrada silenciosamente a Hold.

## Requirements *(mandatory)*

### Functional Requirements

#### Identidad, compilación y validación

- **FR-001**: El sistema DEBE capturar un estado militar inicial inmutable para toda
  la adjudicación y asignar una identidad estable a cada unidad, incluidas las
  guarniciones independientes.
- **FR-002**: El sistema DEBE detectar antes de interpretar órdenes cualquier unidad
  duplicada u ocupación inicial incompatible de un mismo espacio militar y abortar
  sin cambios.
- **FR-003**: El sistema DEBE preservar la costa exacta de cada flota en su identidad,
  desplazamiento y resultado, usando la provincia equivalente solo para ocupación y
  conflicto territorial.
- **FR-004**: El sistema DEBE compilar exactamente una orden lógica por unidad a
  partir de todas las órdenes cargadas, sin ejecutar ninguna fila durante la carga.
- **FR-005**: El sistema DEBE representar explícitamente Advance, Besiege, Hold,
  Lift siege, Support, Transport y Convert.
- **FR-006**: El sistema DEBE asignar Hold a una unidad sin orden y a una combinación
  individual inválida conforme a la política de validación, registrando el motivo;
  estos Holds efectivos PUEDEN someter una rebelión si tienen éxito.
- **FR-007**: El sistema DEBE cargar las órdenes en su secuencia persistida de
  creación y conservar el orden relativo por actor, jugador y ciclos sucesivos de
  guardado y carga.
- **FR-008**: El sistema DEBE rechazar una combinación de varias órdenes para una
  unidad salvo que sea un ejército y todas sean Advance; esas órdenes compatibles
  DEBEN formar un único convoy ordenado.
- **FR-009**: Una orden individual inválida DEBE afectar solo a su unidad; un estado
  militar inválido DEBE abortar toda la adjudicación.

#### Movimientos, transportes y conversiones

- **FR-010**: Un movimiento directo DEBE ser válido solo si el tipo de unidad puede
  recorrer el tramo exacto y el destino permitido según el mapa.
- **FR-011**: Un convoy DEBE identificarse al compilar varios Advance de un ejército,
  antes de comprobar la presencia o supervivencia de transportadoras.
- **FR-012**: La ruta de convoy DEBE incluir el origen inmutable, todos los puntos
  intermedios en orden y una provincia como destino final.
- **FR-013**: Cada tramo consecutivo del convoy DEBE ser adyacente en el sentido
  declarado y cada punto intermedio DEBE contener al inicio una flota con Transport
  dirigido al ejército correcto.
- **FR-014**: Una flota Transport DEBE permanecer en su origen, conservar fuerza y
  apoyos normales, poder ser atacada y transportar como máximo a un ejército. Su
  `target` DEBE tener el formato exacto `A <origen>` y enlazarse a la identidad única
  del ejército que ocupaba ese origen en el snapshot.
- **FR-015**: Un ejército PUEDE depender de varias flotas, incluidas flotas de otras
  facciones, siempre que la ruta y cada Transport coincidan en ambos sentidos.
- **FR-016**: La repetición de localizaciones o de una misma transportadora NO DEBE
  invalidar por sí sola una ruta finita válida.
- **FR-017**: Un convoy DEBE disputar únicamente su destino final y NO DEBE ocupar,
  disputar ni producir cruces en posiciones intermedias.
- **FR-018**: El desalojo de cualquier transportadora requerida DEBE cancelar el
  convoy completo; un empate, ataque fallido o victoria de la flota NO DEBE romperlo.
- **FR-019**: Un convoy cancelado o inválido DEBE dejar al ejército en su origen, sin
  aplicar ningún prefijo de la ruta ni participar en el destino.
- **FR-020**: Solo dos avances directos opuestos PUEDEN formar un cruce. Los convoyes
  quedan excluidos aunque su origen y destino sean opuestos a otro movimiento.
- **FR-021**: Un cruce entre unidades de la misma facción NO DEBE generar
  autoconflicto y DEBE permitir que intercambien posiciones si ambos movimientos
  tienen éxito.
- **FR-022**: Una conversión DEBE disputar el espacio de destino correspondiente a
  provincia o ciudad, conservar el origen inicial y poder ganar, empatar, perder o
  ser cancelada por autoconflicto.

#### Conflictos, apoyos y cancelaciones

- **FR-023**: El sistema DEBE construir los conflictos desde las órdenes lógicas sin
  modificar el estado inicial y DEBE separar el espacio provincial del espacio de
  ciudad fortificada.
- **FR-024**: El sistema DEBE registrar todos los lugares donde se adjudicó un
  conflicto efectivo entre dos o más facciones para excluirlos como destinos durante
  las retiradas. Un cruce DEBE registrar sus dos extremos; un destino no disputado o
  una posición con una sola facción NO DEBE registrarse.
- **FR-025**: En cada ronda, el sistema DEBE resolver primero todos los conflictos
  cuyo resultado no dependa de apoyos o transportadoras situados en conflictos aún
  no resueltos.
- **FR-026**: Tras cada resolución, el sistema DEBE cancelar todos los Advance y
  Convert que no resulten ganadores; si las fuerzas máximas empatan, DEBE cancelar
  todos los que disputaban ese máximo. También DEBE cancelar las órdenes de unidades
  desalojadas y los apoyos cortados, y reconstruir los conflictos pendientes.
- **FR-027**: Una orden cancelada NO DEBE ejecutarse ni convertirse en Hold. La
  unidad conserva su presencia física donde corresponda, pero no produce efectos de
  orden, incluidos someter rebelión, apoyar, transportar, asediar o levantar asedio.
- **FR-028**: El sistema DEBE recalcular globalmente las posiciones efectivas,
  autoconflictos, apoyos, fuerzas, transportes, conversiones y desalojos después de
  cada cambio de cancelaciones.
- **FR-029**: Dos unidades de la misma facción que disputen efectivamente el mismo
  espacio DEBEN cancelar sus órdenes implicadas, excepto el intercambio permitido
  por cruce directo.
- **FR-030**: La fuerza de cada participante DEBE incluir su fuerza base, los apoyos
  activos dirigidos a su facción y lugar, y el modificador de rebelión aplicable.
- **FR-031**: Cada apoyo DEBE conservarse como relación individual con facción y
  lugar de destino. Su `target` DEBE ser `<lugar>` para la facción de quien apoya o
  `<lugar> (<potencia>)` para una facción explícita; cualquier cantidad distinta de
  componentes, paréntesis incompletos o potencia inexistente produce Hold inválido
  solo para la unidad emisora.
- **FR-032**: Una guarnición PUEDE apoyar su provincia incluso bajo asedio.
- **FR-033**: El apoyo de una unidad desalojada DEBE cancelarse. Un ataque empatado
  contra quien apoya DEBE cortar el apoyo salvo que estuviera dirigido al origen del
  atacante.
- **FR-034**: En un cruce, cada unidad DEBE usar únicamente los apoyos recibidos en
  su propio destino.
- **FR-035**: Si no quedan conflictos independientes, el sistema DEBE cancelar
  primero todo apoyo cuyo emisor reciba un Advance válido, activo y no cancelado
  desde un lugar distinto del lugar apoyado, y volver a buscar conflictos
  independientes. El Advance PUEDE ser directo o depender de un convoy todavía
  disponible y su fuerza prevista NO condiciona esta cancelación.
- **FR-036**: Si la dependencia circular persiste, el sistema DEBE cancelar todos
  los apoyos restantes y continuar la resolución.
- **FR-037**: La comprobación de estabilidad o ciclo DEBE distinguir apoyos activos,
  convoyes disponibles, movimientos y conversiones exitosos, desalojos,
  autoconflictos cancelados y posiciones efectivas. Si, después del desempate
  completo, reaparece un estado sin progreso determinista, el sistema DEBE abortar,
  conservar el estado militar inicial y producir un `CycleDiagnostic` inmutable con
  la etapa agotada, las iteraciones de primera aparición y repetición, los conflictos
  pendientes ordenados y la firma primitiva canónica del estado repetido.

#### Rebeliones y asedios

- **FR-038**: Una rebelión DEBE ser un modificador de reglas, no una unidad: no se
  mueve, ocupa una plaza adicional, recibe órdenes, provoca conflictos ni se retira.
- **FR-039**: Una rebelión DEBE dirigirse contra la facción controladora y añadir un
  punto a cada participante elegible del conflicto provincial salvo a esa facción.
  Esto se aplica tanto a rebeliones provinciales como urbanas; ninguna rebelión
  añade fuerza al conflicto de ciudad.
- **FR-040**: Una rebelión provincial DEBE terminar por el gasto de pacificación,
  por un Hold efectivo y exitoso de su controlador —explícito, por ausencia de orden
  o derivado de una orden inválida—, o por un Advance exitoso de otra facción que la
  libere.
- **FR-041**: Una orden cancelada, aunque deje físicamente la unidad en la provincia,
  NO DEBE contar como Hold exitoso para someter una rebelión.
- **FR-042**: Una rebelión de ciudad DEBE cerrar la ciudad a conversiones durante la
  campaña y a contratación de guarniciones durante el mantenimiento existente. En
  ambos casos la orden es inválida y no modifica unidades ni ducados. La rebelión
  solo DEBE ser sometida por un asedio completo del controlador o terminada por el
  gasto de pacificación aplicable.
- **FR-043**: Una unidad en una provincia PUEDE asediar una guarnición o rebelión de
  ciudad situada en esa misma provincia; una flota solo PUEDE hacerlo si la ciudad
  tiene puerto.
- **FR-044**: Un Besiege válido DEBE iniciar el asedio si la ciudad no estaba
  asediada; un segundo Besiege válido y exitoso DEBE eliminar el objetivo y terminar
  el asedio.
- **FR-045**: Una unidad que mantiene un asedio solo PUEDE ordenar Besiege, Hold o
  Lift siege; una guarnición asediada solo PUEDE ordenar Hold o Support a su
  provincia.
- **FR-046**: Lift siege DEBE terminar el asedio sin eliminar la guarnición. El
  desalojo de la unidad asediadora también DEBE terminarlo.
- **FR-047**: Una conversión bajo asedio o hacia una ciudad cerrada por rebelión DEBE
  ser inválida.

#### Resultados y aplicación

- **FR-048**: El sistema DEBE producir para cada unidad inicial un resultado físico
  único que indique tipo final, localización final o condición de desalojada, separado
  de la orden que lo causó.
- **FR-049**: Antes de aplicar resultados, el sistema DEBE comprobar que no hay
  ocupaciones finales duplicadas, ejércitos en mar, convoyes parciales, costas
  inválidas, unidades sin resultado ni conflictos pendientes.
- **FR-050**: La aplicación DEBE construir y validar el estado militar, asedios,
  rebeliones afectadas, unidades desalojadas, lugares de conflicto y registro del
  evento completos antes de sustituir el estado del juego una sola vez; el cálculo
  posterior de control DEBE recibir exclusivamente ese estado definitivo. Un fallo
  al construir o serializar el evento conserva también el estado inicial.
- **FR-051**: Toda unidad desalojada DEBE conservarse para la fase de retiradas y no
  ocupar su localización perdida. Si una guarnición independiente queda desalojada,
  el gestor DEBE devolver una decisión explícita para ella; mientras no exista ese
  gestor o falte esa entrada, la resolución completa aborta y el snapshot anterior
  permanece sin cambios, sin crear una colección persistida de pendientes.
- **FR-052**: La fase de retiradas DEBE recibir explícitamente las unidades
  desalojadas y los lugares de conflicto inmediatamente después de la adjudicación.
  La campaña NO DEBE continuar hacia hambre, control o cambio de estación hasta que
  el gestor de desalojos haya terminado; implementar ese gestor queda fuera del
  alcance de esta feature.
- **FR-053**: La persistencia de órdenes DEBE reutilizar la secuencia ya disponible;
  esta feature NO DEBE cambiar el modelo de datos ni requerir migración.

### Quality, UX & Performance Requirements *(mandatory)*

- **NFR-001**: Esta feature no añade una interacción Discord nueva. El éxito mantiene
  la confirmación de campaña existente. Todo fallo militar visible DEBE responder de
  forma efímera, en español de España, comenzar con “No se pudo resolver la fase
  militar; no se aplicó ningún cambio.” y añadir una acción correctiva segura según
  la categoría: revisar ocupaciones incompatibles, revisar las órdenes y escalar si
  se reproduce, activar la gestión de retiradas, o reintentar y comunicar el fallo si
  persiste. El mensaje NO DEBE exponer clases, trazas, rutas, líneas ni diagnósticos
  internos.
- **NFR-002**: Cada regla modificada DEBE disponer de una prueba de aceptación o
  regresión sobre resultados públicos. La validación previa a integración DEBE
  incluir toda la suite del dominio y sus comprobaciones de calidad sin debilitar
  pruebas existentes.
- **NFR-003**: La carga representativa será una campaña con 30 unidades, 60 filas de
  orden, 20 lugares de conflicto, un convoy de 5 transportadoras y al menos dos
  unidades desalojadas: una retirada a un destino válido y otra eliminada mediante
  una decisión `None`. La prueba funcional DEBE verificar en cualquier entorno la
  igualdad exacta de resolución, evento y snapshot final en cinco juegos frescos. La
  puerta temporal DEBE medir exclusivamente
  `MilitaryResolver.run()` con el gestor determinista incluido y exigir menos de 1
  segundo por ejecución —no por promedio— en el job de referencia dedicado con
  Ubuntu 24.04, CPython 3.13, sin cobertura ni paralelismo. El escenario y las
  decisiones se construyen antes del cronómetro.
- **NFR-004**: No hay cambio de datos persistidos ni migración. Las operaciones de
  carga y guardado DEBEN conservar el orden declarado y, ante error, mantener el
  estado previo íntegro.
- **NFR-005**: Todo resultado y diagnóstico de ciclo DEBE ser reproducible con las
  mismas entradas, independientemente del orden incidental de jugadores,
  colecciones o cargas sucesivas. El diagnóstico DEBE compararse como datos
  estructurados y contener únicamente enteros, cadenas, booleanos, `None` y tuplas
  primitivas ordenadas; no puede depender de `repr`, `hash()`, identidad de objetos,
  diccionarios o sets sin normalizar.
- **NFR-006**: Los cambios de resultado de turno DEBEN dejar, mediante el mecanismo
  persistente de eventos ya existente, un registro auditable que permita reconstruir
  movimientos, cancelaciones, convoyes rotos, desalojos, rebeliones y asedios tras un
  ciclo guardar-cargar, sin registrar secretos ni datos personales innecesarios.
- **NFR-007**: La operación síncrona completa iniciada por `run_game` —abrir SQLite,
  cargar `Game`, ejecutar `GameEngine`, construir el reporte y guardar— DEBE
  ejecutarse fuera del event loop de Discord mediante una única llamada a
  `asyncio.to_thread()`. La conexión y los objetos mutables permanecen en el worker;
  solo puede retornar `tuple[str, ...]` o propagar una excepción tipada. El worker
  NO DEBE
  invocar APIs de Discord.

### Key Entities *(include if feature involves data)*

- **Identidad de unidad**: Referencia estable a propietario opcional, tipo y origen
  exacto al comienzo de la fase; no cambia durante la adjudicación.
- **Unidad militar inicial**: Presencia física del estado inicial asociada a una
  identidad; no contiene intención ni resultado provisional.
- **Orden lógica militar**: Intención única de una unidad, con tipo, destino y, cuando
  corresponda, ruta, facción apoyada o relación de transporte.
- **Resultado de unidad**: Estado físico definitivo de una unidad, con tipo final,
  localización final o marca de desalojo.
- **Conflicto**: Disputa de un espacio provincial o de ciudad, con participantes,
  fuerzas, dependencias y estado resuelto o pendiente.
- **Cancelación**: Inhabilitación de una orden por derrota, empate, desalojo,
  autoconflicto, apoyo cortado o ruptura de convoy; no equivale a Hold.
- **Convoy**: Ruta atómica de un ejército desde su origen a una provincia final,
  dependiente de una o varias transportadoras estacionarias.
- **Rebelión**: Estado provincial o urbano dirigido contra el controlador que
  modifica fuerzas y condiciones de sometimiento, liberación o pacificación.
- **Asedio**: Estado de una ciudad y su unidad asediadora entre el inicio, finalización
  o levantamiento.
- **Paquete de retiradas**: Unidades desalojadas y conjunto de lugares disputados que
  la fase posterior necesita para validar destinos.
- **Diagnóstico de ciclo**: Registro inmutable y reproducible de una dependencia
  irresoluble, con etapa agotada, iteraciones, conflictos pendientes ordenados y
  firma canónica del estado; solo se registra internamente.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: El 100 % de los escenarios de convoy de una o varias flotas termina con
  el ejército exactamente en origen o destino final, nunca en posiciones
  intermedias ni duplicado.
- **SC-002**: El 100 % de las permutaciones probadas del orden de jugadores y
  colecciones produce idénticos resultados, cancelaciones, asedios, rebeliones,
  lugares disputados y retiradas.
- **SC-003**: El 100 % de los fallos de estado, ciclos irresolubles, gestor de
  desalojos y construcción o serialización del evento probados conserva sin cambios
  todas las colecciones militares iniciales y el registro de eventos previo.
- **SC-004**: El 100 % de las unidades desalojadas en la matriz de aceptación aparece
  una sola vez en el paquete entregado inmediatamente al gestor y el 100 % de los
  espacios disputados por dos o más facciones —incluidos ambos extremos de un
  cruce— se rechaza como destino de retirada antes de continuar la campaña.
- **SC-005**: Todos los casos de cancelación demuestran que una orden cancelada no
  produce efectos de Hold, Support, Transport, Besiege, Lift siege ni Convert.
- **SC-006**: En el job de referencia definido, cada una de cinco ejecuciones de la
  carga representativa termina en menos de 1 segundo e incluye detección de
  dependencias, dos desalojos, invocación y validación del gestor, una retirada, una
  eliminación, evento y aplicación final. En cualquier otro entorno, la misma carga
  supera la prueba funcional de determinismo sin usar el tiempo como puerta.
- **SC-007**: El 100 % de los mensajes de error visibles introducidos o modificados
  está en español de España, confirma que no hubo cambios parciales, proporciona una
  acción correctiva adecuada a la categoría y no expone detalles internos.
- **SC-008**: La suite de aceptación cubre los siete códigos de orden, movimientos
  directos, cruces, convoyes, apoyos, autoconflictos, conversiones, rebeliones,
  asedios, ciclos, aplicación atómica y retiradas sin resultados no deterministas.
- **SC-009**: Las pruebas del límite Discord demuestran que `run_game` delega una sola
  operación síncrona completa fuera del event loop, que SQLite y `Game` no cruzan la
  frontera y que el éxito retorna un reporte inmutable mientras las excepciones
  tipadas conservan su categoría.

## Assumptions

- Las notas adicionales del solicitante tienen prioridad sobre el plan base cuando
  existe contradicción. En particular, sustituyen el aborto inmediato de ciclos por
  la cancelación escalonada de apoyos y distinguen cancelación de Hold.
- El gasto denominado “B” para pacificar rebeliones pertenece a la fase de gastos y
  es distinto de la orden militar Besiege, aunque compartan una letra en la notación
  existente.
- Una unidad cuya orden se cancela conserva presencia física y defensa normal en su
  posición efectiva, pero no ejecuta ningún efecto propio de la orden cancelada.
- La política definitiva de retirada de guarniciones independientes queda fuera de
  esta feature. Hasta aprobarla, cualquier desalojo de una guarnición independiente
  sin decisión explícita del gestor aborta el turno y conserva el snapshot completo.
- Las retiradas se resuelven inmediatamente dentro de la misma campaña, antes de
  hambre, control y cambio de estación. Esta feature entrega unidades y lugares de
  conflicto y coordina la pausa; la implementación del gestor de desalojos es una
  dependencia externa y queda fuera de alcance.
- Se reutilizan las reglas actuales de mapa, adyacencia, puertos, control, fuerza base
  y formato de órdenes salvo donde esta especificación las sustituye expresamente.
- No se añaden reglas que prohíban rutas finitas repetidas o redundantes.
- La primera entrega recalcula globalmente los conflictos; una optimización
  incremental solo se justificará si una medición incumple el presupuesto.
- No forman parte de esta feature un motor genérico de reglas, nuevas dependencias,
  ejecución parcial de convoyes, la implementación del gestor de desalojos ni
  cambios en el modelo persistido de órdenes.
- La evaluación cualitativa de comprensión por participantes se considera una
  validación de producto posterior y no una puerta automatizable de integración; la
  aceptación de esta feature se rige por SC-001–SC-009.
