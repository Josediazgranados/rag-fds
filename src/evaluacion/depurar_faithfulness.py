"""
Depuracion de faithfulness: muestra las afirmaciones que extrae el evaluador y los veredictos (con su razon).
Sirve para saber si un 0.0 viene del modelo evaluador (NLI debil) o de la forma de pedir la salida.
Uso: python depurar_faithfulness.py --resultados ../../evaluacion/resultados_k3.json --id Q01 [--modelo qwen2.5:3b]
"""
import argparse, asyncio, json, re, sys, warnings
from pathlib import Path

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parent))
from evaluar_ragas import crear_llm   # noqa: E402


async def correr(fila, modelo, con_formato_json=True):
    """Ejecuta los dos pasos de Faithfulness y devuelve (afirmaciones, veredictos).
    param : fila : dict user_input/response/retrieved_contexts; modelo : str
    return: tupla (StatementGeneratorOutput, NLIStatementOutput o None)
    """
    from evaluar_ragas import crear_metricas
    m = crear_metricas()["faithfulness"]      # incluye la nota de idioma
    m.llm = crear_llm(modelo)
    st = await m._create_statements(fila, None)
    print("AFIRMACIONES:", [s for s in st.statements])
    if not st.statements:
        return st, None
    vd = await m._create_verdicts(fila, st.statements, None)
    for v in vd.statements:
        print(f"  veredicto={v.verdict} | {v.statement[:90]} | razon: {v.reason[:160]}")
    return st, vd


def main():
    """CLI de depuracion.
    param : --resultados, --id, --modelo
    return: None
    """
    ap = argparse.ArgumentParser()
    ap.add_argument("--resultados", required=True); ap.add_argument("--id", required=True)
    ap.add_argument("--modelo", default="qwen2.5:3b")
    a = ap.parse_args()
    r = next(x for x in json.load(open(a.resultados, encoding="utf-8")) if x["id"] == a.id)
    fila = dict(user_input=r["user_input"], retrieved_contexts=r["retrieved_contexts"],
                response=re.sub(r"\s*\[\d+\]", "", r["response"]).strip(), reference=r["reference"])
    print("RESPUESTA EVALUADA:", fila["response"])
    asyncio.run(correr(fila, a.modelo))


if __name__ == "__main__":
    main()
