# Verificación de las referencias contra los PDF originales

Cada referencia de `preguntas.json` se comprobó leyendo el texto del **PDF original** (`pdftotext -layout`, no el Markdown extraído), para que la evaluación no dependa de errores de la propia extracción. Las páginas son las del PDF.

| Pregunta | Documento (PDF) | Pág. | Sección | Texto literal en el PDF |
|---|---|---|---|---|
| Q01 | FDS 66 – Sellador Industrial Nitrocelulósico 40030020 (Química Cosmos) | 8 | 9 | `Punto de inflamación: 20 ºC` |
| Q02 | FDS 92 – Pintura Coolguard (Corona) | 2 | 3 | `Dioxido de titanio (diámetro aerodinámico ≤ 10 μm)   20 - <30%` / `CAS: 13463-67-7` (la fila siguiente, `CAS: 13463-41-7`, es otro componente: piritionato cíncico, <5 %) |
| Q03 | FDS 100 – Esmalte Maestro (Bler) | 3 | 4 | `Por ingestión/aspiración: Requerir asistencia médica inmediata, mostrándole la FDS de este producto. No inducir al vómito, en el caso de que se produzca mantener inclinada la cabeza hacia delante para evitar la aspiración. En el caso de pérdida de consciencia no administrar nada por vía oral hasta la supervisión del médico. Enjuagar la boca y la garganta (…) Mantener al afectado en reposo.` |
| Q04 | FDS 47 – Dimetcote 302H Green Resin (PPG) | 4 | 5 | `Medios de extinción apropiados: Utilizar polvo químico seco, CO₂, agua pulverizada o espuma (neblina).` / `Medios no apropiados: No usar chorro de agua.` |
| Q05 | FDS 66 – Sellador Industrial Nitrocelulósico (Química Cosmos) | 15 | 14 | `14.1 Número ONU: UN1263` (la sección 14 empieza en la pág. 14) |
| Q06 | FDS 100 – Esmalte Maestro (Bler) | 4 | 7 | `7.2 … Temperatura mínima: 4 ºC / Temperatura máxima: 35 ºC / Tiempo máximo: 12 meses` |
| Q07 | FDS 100 – Esmalte Maestro (Bler); FDS 94 – Esmalte Metal Master Premium (Corona) | 7; 7 | 9 | `Punto de inflamación: 41 ºC` (Bler); `Punto de inflamación: 60 ºC` (Corona) |
| Q08 | FDS 47 – Dimetcote 302H; FDS 65 – Sigmadur One Buff 3142 (PPG) | 7; 8 | 9 | `Punto de inflamación: Vaso cerrado: 37°C (98.6°F)` (Dimetcote); `Vaso cerrado: 43°C (109.4°F)` (Sigmadur) |
| Q09 | FDS 71 – Sikafloor-2430 Part A; FDS 72 – Sikafloor-2430 Part B | 10; 10 | 14 | `Número ONU: UN 1263` en ambas |
| Q10 | FDS 94 – Esmalte Metal Master Premium (Corona) | 7; 11 | 9 y 14 | `Punto de inflamación: 60 ºC`; `14.1 Número ONU: UN1263` |
| Q11 | (ninguno) | – | – | Búsqueda de `rendimiento`, `cobertura teórica` y `m²/galón` en el texto de las 101 FDS: **0 coincidencias** |
| Q12 | (ninguno) | – | – | Búsqueda de `brillo` y `gloss` en el texto de las 101 FDS: **0 coincidencias** |

## Cobertura de secciones
Secciones 3, 4, 5, 7, 9 y 14 (6 secciones; el enunciado exige al menos 4). Distribución: 6 directas (Q01–Q06), 4 que integran o comparan (Q07–Q10), 2 sin respuesta (Q11–Q12); 10 respondibles para RAGAS.

## Notas
- Q07–Q09 comparan documentos distintos: ponen a prueba si el recuperador trae fragmentos de ambos con `top-k = 3`.
- Q09 enfrenta dos fichas casi idénticas (Part A y Part B), un caso difícil de desambiguar.
- Q03 y Q06 caen en FDS_100, la ficha donde la marca de agua "COPIA CONTROLADA" fusionó secciones durante la extracción (ver `data/markdown/_secciones.csv`): sirven además de prueba de que el chunker recupera esa estructura.
- Las preguntas sin respuesta se eligieron sobre temas plausibles en una pintura (rendimiento, brillo) pero que una FDS no incluye.
