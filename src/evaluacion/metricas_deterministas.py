"""
Metricas DETERMINISTAS (sin LLM) para complementar RAGAS y contrastar k=3 contra k=6.

Motivo: el evaluador local de 3 B parametros es poco fiable como juez (ver README y el informe: dio
faithfulness 0.0 a una respuesta correcta porque leyo la linea equivocada del contexto). Estas
metricas son transparentes y reproducibles; NO sustituyen a RAGAS, lo complementan.

Por pregunta respondible:
  doc_recall           fraccion de documentos esperados que aparecen entre los fragmentos recuperados
  ref_en_contextos     fraccion de los datos clave de la REFERENCIA presentes en los contextos  (analogo a context recall)
  resp_cubre_ref       fraccion de los datos clave de la REFERENCIA presentes en la RESPUESTA   (completitud / exactitud)
  resp_apoyada         fraccion de las cifras de la RESPUESTA que aparecen en los contextos     (analogo a faithfulness numerica)
  citas_en_doc_esperado fraccion de fuentes citadas que pertenecen a un documento esperado      (trazabilidad)
Por pregunta sin respuesta:
  rechazo_correcto     1 si la respuesta es exactamente la frase de evidencia insuficiente

'Datos clave' = cifras (con decimales, CAS, UN1263...) de la referencia; si la referencia no tiene cifras,
palabras de contenido de 5+ letras. Se normaliza (minusculas, sin tildes, coma decimal -> punto, sin espacios en cifras).
Uso: python metricas_deterministas.py --resultados ../../evaluacion/resultados_k3.json --salida ../../evaluacion/deterministas_k3.json
"""
import argparse, json, re, statistics, sys, unicodedata

FRASE = "No hay evidencia suficiente en las fichas de datos de seguridad recuperadas para responder esta pregunta."
STOP = set("para como donde desde entre sobre tiene tienen cuando cual cuales segun mismo misma ambos ambas debe deben "
           "puede pueden esta este estos estas producto productos ficha fichas datos seguridad indica indican".split())


def norm(t):
    """Minusculas, sin tildes, coma decimal a punto.
    param : t : str
    return: str
    """
    t = "".join(c for c in unicodedata.normalize("NFD", t.lower()) if unicodedata.category(c) != "Mn")
    return re.sub(r"(?<=\d),(?=\d)", ".", t)


def cifras(t):
    """Cifras y codigos de un texto: numeros, CAS, UN#### (sin espacios internos).
    param : t : str
    return: set[str]
    """
    t = norm(re.sub(r"\[\d+\]", " ", t))
    t = re.sub(r"\bun\s+(?=\d{4}\b)", "un", t)                    # 'UN 1263' == 'UN1263'
    return set(re.findall(r"un\d{4}|\d{2,7}-\d{2}-\d|(?<![a-z\d])\d+(?:\.\d+)?", t))   # 'co2' no aporta la cifra 2


def palabras(t):
    """Palabras de contenido (5+ letras, sin stopwords).
    param : t : str
    return: set[str]
    """
    return {w for w in re.findall(r"[a-z]{5,}", norm(t)) if w not in STOP}


def datos_clave(referencia):
    """Datos clave de una referencia: cifras si las hay; si no, palabras de contenido.
    param : referencia : str
    return: tupla (set datos, str tipo 'cifras'|'palabras')
    """
    c = cifras(referencia)
    return (c, "cifras") if c else (palabras(referencia), "palabras")


def fraccion(datos, texto, tipo):
    """Fraccion de 'datos' presentes en 'texto'.
    param : datos : set; texto : str; tipo : 'cifras' o 'palabras'
    return: float o None si no hay datos
    """
    if not datos:
        return None
    base = cifras(texto) if tipo == "cifras" else palabras(texto)
    if tipo == "cifras":                       # una cifra de la referencia puede aparecer incrustada (p. ej. 13463-67-7)
        pegado = norm(texto)
        return sum(1 for d in datos if d in base or d in pegado) / len(datos)
    return sum(1 for d in datos if d in base) / len(datos)


def evaluar(r):
    """Calcula las metricas deterministas de una pregunta.
    param : r : dict resultado de correr_preguntas
    return: dict de metricas
    """
    out = dict(id=r["id"], tipo=r["tipo"], top_k=r["top_k"])
    if r["tipo"] == "sin_respuesta":
        out["rechazo_correcto"] = 1.0 if r["response"].strip() == FRASE else 0.0
        return out
    ctx = " ".join(r["retrieved_contexts"])
    docs = {x["chunk_id"].rsplit("_s", 1)[0] for x in r["retrieved"]}
    esp = r["documentos_esperados"]
    out["doc_recall"] = round(sum(1 for d in esp if d in docs) / len(esp), 3)
    datos, tipo = datos_clave(r["reference"])
    out["tipo_datos"] = tipo
    out["ref_en_contextos"] = round(fraccion(datos, ctx, tipo), 3)
    out["resp_cubre_ref"] = round(fraccion(datos, r["response"], tipo), 3)
    pregunta = cifras(r["user_input"])
    cifras_resp = cifras(r["response"]) - pregunta                   # sin las cifras que ya venian en la pregunta
    ctx_c = norm(ctx)
    out["resp_apoyada"] = (round(sum(1 for c in cifras_resp if c in ctx_c) / len(cifras_resp), 3)) if cifras_resp else None
    citas = [s["chunk_id"].rsplit("_s", 1)[0] for s in r["sources"]]
    out["citas_en_doc_esperado"] = round(sum(1 for d in citas if d in esp) / len(citas), 3) if citas else None
    return out


def main():
    """Evalua todas las preguntas de un archivo y escribe el JSON con el resumen.
    param : --resultados, --salida
    return: None
    """
    ap = argparse.ArgumentParser()
    ap.add_argument("--resultados", required=True); ap.add_argument("--salida", required=True)
    a = ap.parse_args()
    filas = [evaluar(r) for r in json.load(open(a.resultados, encoding="utf-8"))]
    resumen = {}
    for m in ("doc_recall", "ref_en_contextos", "resp_cubre_ref", "resp_apoyada", "citas_en_doc_esperado", "rechazo_correcto"):
        v = [f[m] for f in filas if f.get(m) is not None]
        resumen[m] = dict(n=len(v), media=round(statistics.mean(v), 3) if v else None)
    json.dump(dict(preguntas=filas, resumen=resumen), open(a.salida, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    sys.stdout.reconfigure(encoding="utf-8")
    for f in filas:
        print({k: v for k, v in f.items() if k not in ("tipo_datos",)})
    print("RESUMEN", json.dumps(resumen, ensure_ascii=False))


if __name__ == "__main__":
    main()
