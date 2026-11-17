"""
Consolida los resultados de evaluacion en los archivos finales (JSON y CSV).

Une, por pregunta y configuracion (top-k): los campos del pipeline (user_input, retrieved_contexts, response,
reference, sources), los puntajes RAGAS (con sus fallos) y las metricas deterministas.

Salidas (en evaluacion/):
  resultados_finales.json     un registro por pregunta x configuracion, con todos los campos
  resultados_finales.csv      version plana (contextos unidos con ' ||| ')
  resumen_metricas.csv        por metrica y configuracion: promedio sobre casos VALIDOS, n validos, fallos, pendientes
  resumen_metricas.json       lo mismo en JSON

Reglas: un fallo del evaluador NUNCA se convierte en 0 (queda 'fallo' con su motivo y no entra al promedio);
una celda aun no evaluada queda 'pendiente'.
Uso: python consolidar.py
"""
import csv, json, statistics
from pathlib import Path

EV = Path(__file__).resolve().parents[2] / "evaluacion"
KS = (3, 6)
RAGAS = ("faithfulness", "context_precision", "context_recall")
DETER = ("doc_recall", "ref_en_contextos", "resp_cubre_ref", "resp_apoyada", "citas_en_doc_esperado", "rechazo_correcto")


def cargar(nombre):
    """Lee un JSON de evaluacion como dict id -> registro ({} si no existe).
    param : nombre : str nombre de archivo en evaluacion/
    return: dict
    """
    p = EV / nombre
    if not p.exists():
        return {}
    d = json.load(open(p, encoding="utf-8"))
    d = d["preguntas"] if isinstance(d, dict) else d
    return {x["id"]: x for x in d}


def fmt_fuentes(fuentes):
    """Texto legible de las fuentes citadas.
    param : fuentes : list[dict]
    return: str
    """
    return " ; ".join(f"[{s['n']}] {s['fabricante']} | {s['producto']} | {s['documento']} | p.{s['paginas']} | sec. {s['seccion']}"
                      for s in fuentes)


def main():
    """Genera los archivos consolidados y el resumen por metrica.
    param : ninguno
    return: None
    """
    registros = []
    for k in KS:
        res, rag, det = cargar(f"resultados_k{k}.json"), cargar(f"ragas_k{k}.json"), cargar(f"deterministas_k{k}.json")
        for i, r in res.items():
            reg = {c: r[c] for c in ("id", "tipo", "top_k", "user_input", "retrieved_contexts", "response", "reference",
                                     "sources", "retrieved", "documentos_esperados", "modelo", "segundos")}
            g = rag.get(i)
            if r["tipo"] == "sin_respuesta":
                reg["ragas"] = "no aplica (pregunta sin respuesta: se revisa por separado)"
            else:
                reg["ragas"] = {m: ({"estado": "valido", "valor": g["scores"][m]} if g and m in g["scores"] else
                                    {"estado": "fallo", "motivo": g["fallos"][m]} if g and m in g["fallos"] else
                                    {"estado": "pendiente"}) for m in RAGAS}
                if g:
                    reg["evaluador"] = g.get("evaluador")
            reg["deterministas"] = {m: det[i][m] for m in DETER if i in det and det[i].get(m) is not None}
            registros.append(reg)
    json.dump(registros, open(EV / "resultados_finales.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    with open(EV / "resultados_finales.csv", "w", newline="", encoding="utf-8-sig") as fh:
        cols = ["id", "tipo", "top_k", "user_input", "response", "reference", "fuentes", "retrieved_contexts",
                *[f"ragas_{m}" for m in RAGAS], "ragas_estado", *[f"det_{m}" for m in DETER]]
        w = csv.DictWriter(fh, fieldnames=cols); w.writeheader()
        for r in registros:
            fila = dict(id=r["id"], tipo=r["tipo"], top_k=r["top_k"], user_input=r["user_input"], response=r["response"],
                        reference=r["reference"], fuentes=fmt_fuentes(r["sources"]),
                        retrieved_contexts=" ||| ".join(r["retrieved_contexts"]))
            if isinstance(r["ragas"], dict):
                est = []
                for m in RAGAS:
                    c = r["ragas"][m]
                    fila[f"ragas_{m}"] = c.get("valor", "")
                    est.append(f"{m}:{c['estado']}")
                fila["ragas_estado"] = "; ".join(est)
            else:
                fila["ragas_estado"] = "no aplica"
            for m in DETER:
                fila[f"det_{m}"] = r["deterministas"].get(m, "")
            w.writerow(fila)

    resumen = []
    for k in KS:
        for fam, mets in (("ragas", RAGAS), ("determinista", DETER)):
            for m in mets:
                vals, fallos, pend = [], 0, 0
                for r in registros:
                    if r["top_k"] != k:
                        continue
                    if fam == "ragas":
                        if not isinstance(r["ragas"], dict):
                            continue
                        c = r["ragas"][m]
                        if c["estado"] == "valido": vals.append(c["valor"])
                        elif c["estado"] == "fallo": fallos += 1
                        else: pend += 1
                    elif m in r["deterministas"]:
                        vals.append(r["deterministas"][m])
                resumen.append(dict(top_k=k, familia=fam, metrica=m, promedio=round(statistics.mean(vals), 3) if vals else None,
                                    casos_validos=len(vals), fallos=fallos, pendientes=pend))
    json.dump(resumen, open(EV / "resumen_metricas.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    with open(EV / "resumen_metricas.csv", "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(resumen[0])); w.writeheader(); w.writerows(resumen)
    for r in resumen:
        print(r)


if __name__ == "__main__":
    main()
