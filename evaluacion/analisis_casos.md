# Análisis de casos (verificación manual contra los PDF originales)

Casos elegidos: 3 respondibles (incluye el de menor puntaje) y las 2 preguntas sin respuesta.
Las páginas son las del PDF (verificadas con `pdftotext -layout` sobre cada página).

## Caso A — Q07 (comparativa, el de menor puntaje: context precision 0,0 con k=3 y k=6)
**Pregunta:** ¿Cuál tiene mayor punto de inflamación: el Esmalte Maestro de Pinturas Bler o el Esmalte Metal Master Premium de Corona?
**Referencia (verificada):** Corona 60 ºC (FDS 94, p.7, sec. 9) frente a Bler 41 ºC (FDS 100, p.7, sec. 9).

| | Respuesta | Fuente citada | Veredicto |
|---|---|---|---|
| k=3 | Bler 200 ºC, Corona 60 ºC | `[1]` FDS 94, p.7, sec. 9 | **Incorrecta.** 200 ºC es la *temperatura de auto-inflamación de Corona* (FDS 94 p.7); el punto de inflamación de Bler es 41 ºC y no se usó. |
| k=6 | Bler 60 ºC, Corona "no especificado" | `[1]` FDS 94, p.7, sec. 9 | **Incorrecta.** Atribuye a Bler el valor de Corona y dice que falta el de Corona, que está en la fuente citada. |

**Diagnóstico:** la recuperación funcionó (ambos documentos y la sección 9 están entre los fragmentos; `doc_recall` = 1,0). El fallo es del generador de 3 B: mezcla las dos fichas cuando los contextos son cercanos y casi homónimos. Context precision 0,0 porque el evaluador no considera útiles los fragmentos de la ficha de Bler. **Aumentar k no lo arregla** (cambia el error, no lo corrige). La cita sí es trazable (documento, página y sección existen y son los de Corona), pero respalda un dato distinto del afirmado para Bler.

## Caso B — Q09 (comparativa, respuesta vacía: resp_cubre_ref = 0,0 con k=3 y k=6)
**Pregunta:** ¿Los componentes Part A y Part B del Sikafloor-2430 tienen el mismo número ONU? Indica cuál es.
**Referencia (verificada):** sí, ambos UN 1263 (Part A: FDS 71, p.10–11, sec. 14; Part B: FDS 72, p.10, sec. 14).

| | Respuesta | Fuente citada | Veredicto |
|---|---|---|---|
| k=3 y k=6 | `[1]` (solo la marca de cita, sin texto) | FDS 71, p.10–11, sec. 14 | **Incorrecta / vacía.** |

**Diagnóstico:** los fragmentos correctos de ambos componentes (FDS_071_s14_01 y FDS_072_s14_01) están en los dos contextos; el modelo no redactó la respuesta. Es un fallo de generación, no de recuperación. Se registra tal cual (no se reintentó ni se editó la respuesta). La fuente citada sí contiene UN 1263.

## Caso C — Q02 (directa; el único en que k=6 mejora a k=3)
**Pregunta:** CAS del dióxido de titanio en Pintura Coolguard (Corona) y rango de concentración.
**Referencia (verificada):** CAS 13463-67-7; 20 - <30 % (FDS 92, p.2, sec. 3).

| | Respuesta | Fuente citada | Veredicto |
|---|---|---|---|
| k=3 | CAS 13463-67-7 (sin rango) | `[3]` FDS 92, p.8, sec. 11 | Incompleta (1 de 2 datos). Context recall 0,5. |
| k=6 | CAS 13463-67-7 y 20 - <30 % | `[3]` FDS 92, p.8, sec. 11 | Completa, pero con **cita imprecisa**. |

**Diagnóstico:** con k=6 entra el fragmento de la sección 3 (p.2) que trae el rango, y la respuesta se completa. El CAS también aparece en la p.8 (sec. 11, líneas IARC y DL50), de modo que esa cita respalda el CAS; **el rango 20 - <30 % solo está en p.2 (sec. 3) y no se cita**. Es una debilidad de trazabilidad: la cita apunta a un fragmento que no contiene todo lo afirmado.

## Preguntas sin respuesta (Q11 rendimiento m²/galón, Q12 brillo a 60°)
Revisadas en las dos configuraciones: respuesta exacta "No hay evidencia suficiente…", sin fuentes inventadas. Verificado que ninguna de las 101 FDS contiene rendimiento ni brillo (ver `verificacion_referencias.md`). Rechazo correcto en 4/4 casos.

## Conclusión de la revisión
- El principal cuello de botella es el generador/evaluador de 3 B, no la recuperación (`doc_recall` = 1,0).
- k=6 aporta más cobertura (ref_en_contextos 0,946 frente a 0,896) pero también más ruido; la mejora se ve en preguntas que necesitan dos secciones (Q02) y no en las comparativas.
- Trazabilidad: las fuentes citadas siempre existen y son del documento esperado, pero una cita puede respaldar solo parte de lo afirmado (Caso C) o un dato de otro producto (Caso A).
