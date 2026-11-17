"""
Corre un conjunto de preguntas por el pipeline RAG con un top-k dado y guarda los resultados.

Por pregunta se guardan los campos que pide el enunciado: user_input, retrieved_contexts, response,
reference, sources (mas los fragmentos recuperados con su puntaje, tiempos y configuracion).
La referencia se lee del archivo de preguntas SOLO aqui para guardarla junto al resultado; nunca
llega al indice ni al prompt (el pipeline solo recibe la pregunta).

Es reanudable: si el JSON de salida ya tiene una pregunta, no se repite (util si se corta la sesion).

Uso: python correr_preguntas.py --preguntas ../../evaluacion/preguntas.json -k 3 --salida ../../evaluacion/resultados_k3.json
"""
import argparse, json, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from generar import responder, MODELO_LLM   # noqa: E402


def main():
    """Ejecuta las preguntas y escribe el JSON de resultados (guardando tras cada pregunta).
    param : --preguntas, -k, --salida, --modelo, --umbral
    return: None
    """
    ap = argparse.ArgumentParser()
    ap.add_argument("--preguntas", required=True); ap.add_argument("-k", type=int, required=True)
    ap.add_argument("--salida", required=True); ap.add_argument("--modelo", default=MODELO_LLM)
    ap.add_argument("--umbral", type=float)
    a = ap.parse_args()
    preguntas = json.load(open(a.preguntas, encoding="utf-8"))["preguntas"]
    salida = Path(a.salida)
    hechos = {r["id"]: r for r in json.load(open(salida, encoding="utf-8"))} if salida.exists() else {}
    t0 = time.time()
    for p in preguntas:
        if p["id"] in hechos:
            continue
        r = responder(p["pregunta"], a.k, a.modelo, a.umbral)
        r.update(id=p["id"], tipo=p["tipo"], reference=p["referencia"],
                 documentos_esperados=p["documentos_esperados"], umbral=a.umbral)
        hechos[p["id"]] = r
        salida.write_text(json.dumps(list(hechos.values()), ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"{p['id']} k={a.k} {r['segundos']} s | {r['response'][:110]!r}", flush=True)
    print(f"FIN k={a.k}: {len(hechos)} preguntas en {time.time() - t0:.0f} s -> {salida}")


if __name__ == "__main__":
    main()
