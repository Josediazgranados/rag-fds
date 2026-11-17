"""
Prueba de recuperacion SIN LLM: ¿los documentos correctos aparecen entre los k primeros fragmentos?

Para cada pregunta con documentos esperados mide si al menos uno / todos aparecen en el top-k y la
posicion del primero (rango). Para las preguntas sin respuesta muestra el puntaje del mejor fragmento,
util para calibrar el umbral de 'evidencia insuficiente' (usar las preguntas de DESARROLLO, no las finales).

Uso: python prueba_recuperacion.py [--archivo ../../evaluacion/preguntas_desarrollo.json] [-k 3 6]
"""
import argparse, json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from indice import buscar   # noqa: E402

RAIZ = Path(__file__).resolve().parents[2]


def main():
    """Ejecuta la prueba para cada k pedido e imprime una tabla.
    param : --archivo : json de preguntas; -k : lista de valores de top-k
    return: None
    """
    ap = argparse.ArgumentParser()
    ap.add_argument("--archivo", default=str(RAIZ / "evaluacion" / "preguntas_desarrollo.json"))
    ap.add_argument("-k", type=int, nargs="+", default=[3, 6])
    ap.add_argument("--modo", default="hibrido", choices=["hibrido", "denso"])
    a = ap.parse_args()
    preguntas = json.load(open(a.archivo, encoding="utf-8"))["preguntas"]
    for k in a.k:
        print(f"\n===== top-k = {k} =====")
        todos = parcial = n = 0
        for p in preguntas:
            r = buscar(p["pregunta"], k, modo=a.modo)
            docs = [x["doc_id"] for x in r]
            esperados = p["documentos_esperados"]
            if esperados:
                n += 1
                hit_todos = all(d in docs for d in esperados)
                hit_alguno = any(d in docs for d in esperados)
                todos += hit_todos; parcial += hit_alguno
                rango = min((docs.index(d) + 1 for d in esperados if d in docs), default=None)
                print(f"{p['id']:4s} todos={'SI' if hit_todos else 'no'} alguno={'SI' if hit_alguno else 'no'} rango1={rango} "
                      f"mejor={r[0]['puntaje']} | docs={docs}")
            else:
                print(f"{p['id']:4s} (sin respuesta) mejor puntaje={r[0]['puntaje']} | {r[0]['doc_id']} sec {r[0]['seccion']}")
        print(f"-> con documentos esperados: {n}; todos en top-{k}: {todos}; al menos uno: {parcial}")


if __name__ == "__main__":
    main()
