# RAG sobre 101 Fichas de Datos de Seguridad (FDS) de pinturas

Sistema RAG **100 % local y de código abierto** que responde preguntas sobre 101 FDS del sector de pinturas y recubrimientos (2018–2025, 1134 páginas), con trazabilidad por fabricante, producto, documento, página y sección, y evaluación con RAGAS.

> Resultados de la evaluación (top-k 3 vs 6, RAGAS + métricas deterministas): ver la sección [Resultados](#resultados).

## 1. Arquitectura

```
PDF (101) ──Docling──▶ Markdown paginado + imágenes ──▶ chunking por sección (SGA 1–16)
                                                              │ 3362 fragmentos + metadatos
                       ┌──────────────────────────────────────┘
                       ▼
        embeddings multilingual-e5-small ──▶ ChromaDB (coseno)        BM25 (cuerpo y nombre de documento)
                       └──────────────┬───────────────────────────────────┘
                                      ▼
   Recuperación en 2 etapas: (1) documento(s) candidato(s) por producto/fabricante
                             (2) fragmentos por TEMA (denso + BM25, RRF); cada documento aporta su mejor fragmento
                                      ▼
            prompt con fragmentos numerados ──▶ qwen2.5:3b (Ollama, CPU) ──▶ respuesta con marcas [n]
                                      ▼
   fuentes = metadatos del fragmento citado (fabricante, producto, documento, página, sección)
```

| Componente | Elección | Por qué |
|---|---|---|
| Extracción PDF→MD | **Docling 2.150.1** (tablas, imágenes referenciadas, marcadores de página); OCR Tesseract spa+eng solo para texto en imágenes | En un piloto de 6 fichas conservó las 16 secciones como encabezado y consolidó tablas; PyMuPDF4LLM fragmentó tablas clave‑valor y en una ficha no dejó encabezados |
| Chunking | por sección → ~1500 caracteres (~450 tokens), solape ~250 (~80 tokens), tablas por filas repitiendo encabezado | un fragmento nunca cruza de sección; cita exacta por sección y página |
| Embeddings | `intfloat/multilingual-e5-small` (prefijos `passage:`/`query:`) | `e5-base` midió ~50 min en 2 vCPU; `e5-small` ~12 min |
| Almacén | ChromaDB persistente | metadatos y filtros |
| Recuperación | 2 etapas + BM25 + RRF (c=60) | medido en preguntas de desarrollo: con denso/híbrido plano se acertaba el documento pero no la sección |
| Generador | `qwen2.5:3b` (Ollama, CPU, temperatura 0, semilla 42) | cabe en 8 GiB sin GPU |
| Evaluación | RAGAS 0.4.4: faithfulness, context precision, context recall | evaluador LLM local |

**Trazabilidad:** las fuentes se arman en código desde los metadatos de los fragmentos que el modelo cita con `[n]`; el modelo nunca escribe los datos de la cita. Si los fragmentos no contienen la respuesta, el prompt exige la frase fija *«No hay evidencia suficiente en las fichas de datos de seguridad recuperadas…»*.

## 2. Entorno y reproducibilidad

- **Hardware (medido):** AWS EC2 `t3.large` (2 vCPU, 8 GiB, **sin GPU**), Ubuntu 24.04, disco 50 GiB. Las instancias con GPU y los tamaños `xlarge` están bloqueados en el AWS Academy Learner Lab usado (política `Pvoclabs2`).
- **Versiones:** ver `requirements-freeze.txt` (Python 3.12.3, Docling 2.150.1, torch 2.15.0+cpu, sentence-transformers 6.3.0, chromadb 1.5.9, ragas 0.4.4; Ollama 0.40.16; Tesseract 5.3.4; poppler 24.02.0).
- **Dependencias mínimas:** `requirements.txt`.

```bash
# 0. PDFs en data/pdf/FDS EVALUADAS/ ; Ollama instalado y `ollama pull qwen2.5:3b`
python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt

# 1. Extracción (reanudable; ~2.4 h en t3.large)
python src/extraccion/extraer.py
python src/extraccion/manifiesto.py            # data/corpus.csv (procedencia, versión, fechas)
python src/extraccion/secciones.py             # detección de las 16 secciones (PDF vs Markdown)
python src/extraccion/verificacion.py          # cobertura de texto, números, CAS y unidades

# 2. Índice (reanudable por bloques; ~12 min)
python src/rag/chunking.py
python src/rag/indice.py construir

# 3. Preguntas y evaluación
python src/rag/correr_preguntas.py --preguntas evaluacion/preguntas.json -k 3 --salida evaluacion/resultados_k3.json
python src/rag/correr_preguntas.py --preguntas evaluacion/preguntas.json -k 6 --salida evaluacion/resultados_k6.json
python src/evaluacion/evaluar_ragas.py --resultados evaluacion/resultados_k3.json --salida evaluacion/ragas_k3.json
python src/evaluacion/evaluar_ragas.py --resultados evaluacion/resultados_k6.json --salida evaluacion/ragas_k6.json
python src/evaluacion/metricas_deterministas.py --resultados evaluacion/resultados_k3.json --salida evaluacion/deterministas_k3.json   # idem k6
python src/evaluacion/consolidar.py            # resultados_finales.json/csv y resumen_metricas.csv/json

# 4. Demo
pip install gradio && python src/app/demo.py --host 0.0.0.0     # o: python src/rag/generar.py "pregunta" -k 3
```

### Ejecutar la demo en GitHub Codespaces (sin instalar nada)

1. En la página del repositorio: **Code → Codespaces → Create codespace** (elige la máquina de **4 núcleos / 16 GB**).
2. Espera a que termine la instalación automática (`.devcontainer/instalar.sh`: Ollama, `qwen2.5:3b`, dependencias CPU; ~10 min la primera vez).
3. En la terminal del codespace: `python src/app/demo.py --host 0.0.0.0` y abre el puerto **7860** que ofrece Codespaces.

El índice (`data/indice/`) ya viene en el repositorio; si fallara, se reconstruye con `python src/rag/indice.py construir` (~12 min). Cada consulta tarda unos minutos porque el modelo corre en CPU.

## 3. Estructura del repositorio

```
data/corpus.csv                 manifiesto: procedencia, sha256, fabricante, versión, fechas (101 filas)
data/markdown/FDS_NNN.md        Markdown de cada FDS (cabecera YAML, marcadores <!-- pagina N -->)
data/markdown/_secciones*.csv   estado de las 16 secciones por ficha (presente / en párrafo / sin número / fallo / ausente)
data/markdown/_verificacion_*.csv  cobertura PDF→Markdown por página y por documento
data/imagenes/FDS_NNN/          imágenes con imagenes.json (documento, página, tamaño, texto OCR)
data/chunks.jsonl               3362 fragmentos con metadatos
evaluacion/                     preguntas.json (12), referencias verificadas, resultados y puntajes RAGAS
src/{extraccion,rag,evaluacion,app}
```

## 4. Verificación de la extracción (resultados medidos)

- **Secciones:** 1611 de 1616 presentes; 4 con el título incrustado en un párrafo (FDS_100 sec. 5 y 7, FDS_101 sec. 5 y 15); 1 sin número (FDS_002 sec. 4); **0 ausentes en el original**. 10 fichas (001–004, 009, 013–017) usan el formato antiguo NTC 4435 con las secciones 2 y 3 intercambiadas; se registran con su número original.
- **Cobertura PDF→Markdown (cuerpo, sin encabezados repetidos):** palabras mediana 0,997 (mín. 0,964); números 0,985 (mín. 0,885); **números CAS 100 %** (1568/1568); unidades 1,000 (mediana).
- **Pérdidas sistemáticas conocidas:** Docling descarta encabezado y pie de página (código, fecha, versión y nombre del producto repetidos en cada página; esos datos están en `corpus.csv`) y el párrafo legal final (27 páginas con cobertura < 0,90).
- **Fallo de orden de lectura (FDS_100, pág. 4):** por la marca de agua «COPIA CONTROLADA», el bloque 7.2 (almacenamiento) quedó antes del título «SECCIÓN 7» y se etiqueta como sección 6. No se corrigió a mano.
- **Limitación:** no se guardó el documento intermedio de Docling; reconvertir las 101 fichas tomaría ~2,5 h.

## 5. Preguntas de evaluación

12 preguntas fijas (6 directas, 4 que comparan o integran, 2 sin respuesta) sobre las secciones 3, 4, 5, 7, 9 y 14; referencias verificadas contra el texto de los PDF originales (`evaluacion/verificacion_referencias.md`). Las referencias **no** se indexan ni entran al prompt. Para calibrar el prompt se usó un conjunto de desarrollo distinto (`preguntas_desarrollo.json`).

## Resultados

Las dos configuraciones usan el mismo corpus, fragmentos, embeddings, recuperación, generador, prompt y evaluador; **solo cambia top-k (3 y 6)**. Evaluador RAGAS 0.4.4 con `qwen2.5:3b` local (el mismo modelo que genera: posible sesgo; parámetros en `evaluacion/configuracion_modelos.json`). Se probó antes en 2 casos (Q01, Q02). **10 casos válidos por configuración y 0 fallos del evaluador**; las 2 preguntas sin respuesta (Q11, Q12) se revisan aparte.

| Métrica (promedio de 10 casos válidos) | k = 3 | k = 6 |
|---|---|---|
| RAGAS faithfulness | 0,033 | 0,243 |
| RAGAS context precision | 0,833 | 0,829 |
| RAGAS context recall | 0,950 | 1,000 |
| (determinista) documento esperado recuperado | 1,00 | 1,00 |
| (determinista) datos de la referencia presentes en los contextos | 0,896 | 0,946 |
| (determinista) datos de la referencia presentes en la respuesta | 0,684 | 0,711 |
| (determinista) fuentes citadas del documento esperado | 1,00 | 1,00 |
| (determinista) rechazo correcto en Q11 y Q12 | 2/2 | 2/2 |

Por pregunta (F = faithfulness, P = context precision, R = context recall):

| Pregunta | tipo | F k3 | F k6 | P k3 | P k6 | R k3 | R k6 |
|---|---|---|---|---|---|---|---|
| Q01 | directa | 0,00 | 0,00 | 1,00 | 1,00 | 1,00 | 1,00 |
| Q02 | directa | 0,00 | 0,00 | 1,00 | 1,00 | 0,50 | 1,00 |
| Q03 | directa | 0,00 | 0,00 | 0,33 | 0,42 | 1,00 | 1,00 |
| Q04 | directa | 0,00 | 0,60 | 1,00 | 0,88 | 1,00 | 1,00 |
| Q05 | directa | 0,00 | 0,00 | 1,00 | 1,00 | 1,00 | 1,00 |
| Q06 | directa | 0,00 | 0,50 | 1,00 | 1,00 | 1,00 | 1,00 |
| Q07 | comparativa | 0,00 | 1,00 | 0,00 | 0,00 | 1,00 | 1,00 |
| Q08 | comparativa | 0,33 | 0,33 | 1,00 | 1,00 | 1,00 | 1,00 |
| Q09 | comparativa | 0,00 | 0,00 | 1,00 | 1,00 | 1,00 | 1,00 |
| Q10 | integradora | 0,00 | 0,00 | 1,00 | 1,00 | 1,00 | 1,00 |

**Cómo leer estos números (con honestidad):**
- **Faithfulness es poco fiable aquí.** El evaluador de 3 B da 0,0 a respuestas correctas y verificadas (p. ej. Q01: el contexto dice «Punto de inflamación: 20 ºC» y el evaluador afirma que no) y da 1,0 a una respuesta errónea (Q07 con k=6). La diferencia 0,033 → 0,243 no es evidencia sólida de que k=6 sea más fiel. Las métricas deterministas (sin LLM) coinciden en que **la recuperación no es el problema** (documento esperado recuperado en 10/10 con ambos k) y en una mejora moderada de k=6 en cobertura de datos.
- **k=6 aporta más cobertura** (recall 0,95 → 1,00; datos de la referencia en el contexto 0,896 → 0,946) pero **no mejora la precisión** (0,833 → 0,829) y no corrige los fallos de comparación.
- **Errores del generador (no de la recuperación):** Q07 (mezcla los puntos de inflamación de Bler y Corona), Q09 (respuesta vacía `[1]`), Q08 (omite un producto), Q06 (solo un dato de dos). Detalle y verificación contra los PDF en `evaluacion/analisis_casos.md`.
- Las dos preguntas sin respuesta se rechazaron correctamente en ambas configuraciones, sin fuentes inventadas.

Archivos: `evaluacion/resultados_finales.json|csv` (un registro por pregunta × configuración), `resumen_metricas.csv|json`, `ragas_k3.json`, `ragas_k6.json`, `deterministas_k3|k6.json`, `analisis_casos.md`.

## 6. Limitaciones conocidas

- Modelo generador y evaluador de 3 B parámetros en CPU: respuestas lentas (~2–4 min por pregunta) y errores de generación en comparaciones.
- Un evaluador de 3 B es poco fiable como juez; los puntajes RAGAS deben leerse con esa cautela (ver informe).
- El `top-k` es la única diferencia entre las dos configuraciones evaluadas.
