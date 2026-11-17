"""
Evaluacion RAGAS (faithfulness, context precision, context recall) con evaluador LLM LOCAL (Ollama).

Reglas (del enunciado):
  - Solo las preguntas RESPONDIBLES (las 2 sin respuesta quedan fuera de las metricas).
  - Un fallo del evaluador se registra como FALLO (con su motivo), nunca como 0.
  - Cada celda (pregunta x metrica) se evalua por separado y se guarda al terminar; es reanudable.
  - Las referencias vienen del archivo de resultados (copiadas ahi por correr_preguntas.py).

Metricas (RAGAS 0.4):
  faithfulness      : ¿cada afirmacion de la respuesta se apoya en los contextos recuperados?
  context_precision : LLMContextPrecisionWithReference: ¿los contextos utiles quedan en los primeros puestos?
  context_recall    : LLMContextRecall: ¿los contextos recuperados cubren lo que dice la referencia?

Uso:
  python evaluar_ragas.py --resultados ../../evaluacion/resultados_k3.json --salida ../../evaluacion/ragas_k3.json
  python evaluar_ragas.py ... --solo Q01 Q06        # prueba del evaluador en 2 casos
"""
import argparse, json, math, re, sys, time, warnings
from pathlib import Path

warnings.filterwarnings("ignore")
MODELO_EVAL = "qwen2.5:3b"
METRICAS = ["faithfulness", "context_precision", "context_recall"]
# Hallazgo (prueba en Q01): sin esta nota el evaluador 3B reescribia las afirmaciones en ingles y traducia mal el
# producto ("Sellador" -> "Adhesive"), y luego dictaminaba que el contexto no hablaba de el (faithfulness 0.0 injusto).
NOTA_IDIOMA = (" IMPORTANT NOTE: the questions, answers, references and contexts are written in SPANISH. Write any text you "
               "generate in Spanish. Do NOT translate or rename product names, codes, numbers or units: copy them exactly "
               "as they appear.")


def crear_metricas():
    """Instancia las tres metricas de RAGAS.
    param : ninguno
    return: dict nombre -> metrica
    """
    from ragas.metrics import Faithfulness, LLMContextPrecisionWithReference, LLMContextRecall
    mets = {"faithfulness": Faithfulness(), "context_precision": LLMContextPrecisionWithReference(),
            "context_recall": LLMContextRecall()}
    for m in mets.values():                    # los prompts de RAGAS estan en ingles; ver NOTA_IDIOMA
        for p in m.get_prompts().values():
            if NOTA_IDIOMA not in p.instruction:
                p.instruction = p.instruction + NOTA_IDIOMA
    return mets


def crear_llm(modelo):
    """Evaluador local: ChatOllama (temperatura 0, salida JSON) envuelto para RAGAS.
    param : modelo : str nombre del modelo en Ollama
    return: LangchainLLMWrapper
    """
    from langchain_ollama import ChatOllama
    from ragas.llms import LangchainLLMWrapper
    return LangchainLLMWrapper(ChatOllama(model=modelo, temperature=0, num_ctx=8192, format="json",
                                          keep_alive="30m", seed=42))


def evaluar_celda(metrica, muestra, llm):
    """Evalua una metrica sobre una pregunta; devuelve valor o fallo con motivo.
    param : metrica : objeto metrica RAGAS; muestra : dict con los 4 campos; llm : str nombre del modelo evaluador
    return: tupla (float o None, str motivo del fallo o '')
    """
    from ragas import evaluate, EvaluationDataset
    from ragas.run_config import RunConfig
    try:
        llm = crear_llm(llm)      # cliente NUEVO por celda: RAGAS cierra su bucle asincrono tras cada evaluate()
        res = evaluate(EvaluationDataset.from_list([muestra]), metrics=[metrica], llm=llm, raise_exceptions=True,
                       show_progress=False, run_config=RunConfig(timeout=1500, max_workers=1, max_retries=1))
        df = res.to_pandas()
        v = float(df[metrica.name].iloc[0]) if metrica.name in df.columns else float(df.iloc[0, -1])
        if math.isnan(v):
            return None, "valor NaN devuelto por RAGAS (el evaluador no produjo una salida utilizable)"
        return v, ""
    except Exception as e:                                       # fallo del evaluador: se registra, no se rellena con 0
        return None, f"{type(e).__name__}: {str(e)[:250]}"


def main():
    """Evalua las preguntas respondibles de un archivo de resultados.
    param : --resultados, --salida, --modelo, --solo
    return: None
    """
    ap = argparse.ArgumentParser()
    ap.add_argument("--resultados", required=True); ap.add_argument("--salida", required=True)
    ap.add_argument("--modelo", default=MODELO_EVAL); ap.add_argument("--solo", nargs="*")
    a = ap.parse_args()
    res = [r for r in json.load(open(a.resultados, encoding="utf-8")) if r["tipo"] != "sin_respuesta"]
    if a.solo:
        res = [r for r in res if r["id"] in a.solo]
    salida = Path(a.salida)
    hechos = {r["id"]: r for r in json.load(open(salida, encoding="utf-8"))} if salida.exists() else {}
    llm, mets = a.modelo, crear_metricas()      # 'llm' es el nombre del modelo; evaluar_celda crea el cliente
    for r in res:
        fila = hechos.setdefault(r["id"], dict(id=r["id"], top_k=r["top_k"], evaluador=a.modelo, scores={}, fallos={}, segundos={}))
        muestra = dict(user_input=r["user_input"], retrieved_contexts=r["retrieved_contexts"],
                       response=re.sub(r"\s*\[\d+\]", "", r["response"]).strip(),   # sin marcas [n]: son citas, no afirmaciones
                       reference=r["reference"])
        for nombre in METRICAS:
            if nombre in fila["scores"] or nombre in fila["fallos"]:
                continue
            t0 = time.time()
            v, motivo = evaluar_celda(mets[nombre], muestra, llm)
            fila["segundos"][nombre] = round(time.time() - t0, 1)
            if v is None:
                fila["fallos"][nombre] = motivo
            else:
                fila["scores"][nombre] = round(v, 4)
            salida.write_text(json.dumps(list(hechos.values()), ensure_ascii=False, indent=1), encoding="utf-8")
            print(f"{r['id']} k={r['top_k']} {nombre}: {v if v is not None else 'FALLO ' + motivo[:80]} ({fila['segundos'][nombre]} s)", flush=True)
    print("FIN_RAGAS", flush=True)


if __name__ == "__main__":
    sys.exit(main())
