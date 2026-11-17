"""
Pipeline RAG: recuperar -> construir prompt -> generar con LLM local (Ollama) -> citar fuentes.

Trazabilidad: las FUENTES se arman en codigo desde los metadatos de los fragmentos recuperados
(fabricante, producto, documento, paginas, seccion); el LLM solo decide cuales fragmentos usa
mediante marcas [n], y nunca escribe los datos de la cita. Asi la cita no puede inventarse.

Evidencia insuficiente: (1) el prompt exige una frase fija cuando los fragmentos no contienen la
respuesta; (2) opcionalmente un umbral de similitud del mejor fragmento evita llamar al modelo.

Uso:  python generar.py "pregunta" [-k 3] [--modelo qwen2.5:3b]
"""
import argparse, json, re, sys, time, urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from indice import buscar   # noqa: E402

OLLAMA = "http://localhost:11434/api/chat"
MODELO_LLM = "qwen2.5:3b"
FRASE_INSUFICIENTE = "No hay evidencia suficiente en las fichas de datos de seguridad recuperadas para responder esta pregunta."

SISTEMA = f"""Eres un asistente tecnico que responde preguntas sobre Fichas de Datos de Seguridad (FDS) de pinturas y recubrimientos.
Reglas estrictas:
1. Responde SOLO con la informacion de los fragmentos numerados que se te entregan. No uses conocimiento propio ni inventes valores.
2. Responde en espanol, de forma breve y precisa. Conserva cifras, unidades y nombres exactamente como aparecen en los fragmentos.
3. Cada afirmacion debe llevar al final la marca del fragmento que la respalda, por ejemplo [1] o [2][3]. Si comparas productos, indica el valor de cada uno con su marca.
4. Si los fragmentos no contienen la respuesta, responde exactamente: "{FRASE_INSUFICIENTE}" y nada mas.
5. Si el dato pedido no esta para un producto concreto, dilo para ese producto; no lo supongas a partir de otro.
6. Escribe una respuesta en oraciones completas que nombre el producto EXACTAMENTE como figura en el fragmento y el dato, y termina cada oracion con su marca. Formato: "El <dato> de <nombre del producto> es <valor> [n]."
7. Copia el valor completo tal como aparece en el fragmento, incluyendo palabras como "No inflamable", signos como ">" o "<", rangos y unidades. No lo resumas ni lo recortes.
8. Responde unicamente lo que se pregunta; no agregues informacion adicional."""


def formatear_contexto(frags):
    """Numera los fragmentos con su procedencia para el prompt.
    param : frags : list[dict] salida de indice.buscar
    return: str con los fragmentos [1]..[k]
    """
    bloques = []
    for i, f in enumerate(frags, 1):
        pags = f"{f['pagina_inicio']}" if f["pagina_inicio"] == f["pagina_fin"] else f"{f['pagina_inicio']}-{f['pagina_fin']}"
        bloques.append(f"[{i}] Fabricante: {f['fabricante']} | Producto: {f['producto']} | Documento: {f['documento']} | "
                       f"Pagina: {pags} | Seccion {f['seccion']}: {f['seccion_nombre']}\n{f['texto']}")
    return "\n\n".join(bloques)


def llamar_llm(mensajes, modelo=MODELO_LLM, num_ctx=6144, max_tokens=450):
    """Llama a Ollama (chat, temperatura 0) y devuelve el texto generado.
    param : mensajes : list[dict role/content]; modelo : str; num_ctx : int; max_tokens : int
    return: str respuesta del modelo
    """
    cuerpo = json.dumps(dict(model=modelo, messages=mensajes, stream=False, keep_alive="30m",
                             options=dict(temperature=0, num_ctx=num_ctx, num_predict=max_tokens, seed=42))).encode()
    req = urllib.request.Request(OLLAMA, data=cuerpo, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=900) as r:
        return json.loads(r.read())["message"]["content"].strip()


def fuentes(frags, respuesta):
    """Arma la lista de fuentes desde los metadatos (solo los fragmentos citados con [n]).
    param : frags : list[dict]; respuesta : str con marcas [n]
    return: list[dict] con n, fabricante, producto, documento, paginas, seccion, chunk_id
    """
    citados = sorted({int(n) for n in re.findall(r"\[(\d+)\]", respuesta) if 1 <= int(n) <= len(frags)})
    if FRASE_INSUFICIENTE in respuesta:
        citados = []
    return [dict(n=i, fabricante=frags[i - 1]["fabricante"], producto=frags[i - 1]["producto"],
                 documento=frags[i - 1]["documento"],
                 paginas=(str(frags[i - 1]["pagina_inicio"]) if frags[i - 1]["pagina_inicio"] == frags[i - 1]["pagina_fin"]
                          else f"{frags[i - 1]['pagina_inicio']}-{frags[i - 1]['pagina_fin']}"),
                 seccion=f"{frags[i - 1]['seccion']}. {frags[i - 1]['seccion_nombre']}",
                 chunk_id=frags[i - 1]["chunk_id"]) for i in citados]


def responder(pregunta, k=3, modelo=MODELO_LLM, umbral=None):
    """Responde una pregunta con RAG y devuelve todo lo necesario para evaluar y auditar.
    param : pregunta : str; k : int top-k; modelo : str; umbral : float o None (similitud minima del mejor fragmento)
    return: dict(user_input, retrieved_contexts, response, sources, retrieved, top_k, modelo, segundos)
    """
    t0 = time.time()
    frags = buscar(pregunta, k)
    if umbral is not None and (not frags or frags[0]["puntaje"] < umbral):
        resp = FRASE_INSUFICIENTE
    else:
        resp = llamar_llm([dict(role="system", content=SISTEMA),
                           dict(role="user", content=f"Fragmentos:\n\n{formatear_contexto(frags)}\n\nPregunta: {pregunta}")], modelo)
    if FRASE_INSUFICIENTE in resp:                 # frase exacta, sin marcas ni texto adicional
        resp = FRASE_INSUFICIENTE
    return dict(user_input=pregunta, retrieved_contexts=[f["texto"] for f in frags], response=resp,
                sources=fuentes(frags, resp),
                retrieved=[dict(n=i, chunk_id=f["chunk_id"], puntaje=f["puntaje"]) for i, f in enumerate(frags, 1)],
                top_k=k, modelo=modelo, segundos=round(time.time() - t0, 1))


def imprimir(r):
    """Muestra una respuesta con sus fuentes en consola.
    param : r : dict salida de responder
    return: None
    """
    print(f"\nPregunta: {r['user_input']}\n\n{r['response']}\n")
    if r["sources"]:
        print("Fuentes:")
        for s in r["sources"]:
            print(f"  [{s['n']}] {s['fabricante']} - {s['producto']} | {s['documento']} | pag. {s['paginas']} | Seccion {s['seccion']}")
    print(f"\n(top-k={r['top_k']}, {r['modelo']}, {r['segundos']} s)")


def main():
    """CLI: responde una pregunta.
    param : argumentos de linea de comandos
    return: None
    """
    ap = argparse.ArgumentParser()
    ap.add_argument("pregunta"); ap.add_argument("-k", type=int, default=3)
    ap.add_argument("--modelo", default=MODELO_LLM); ap.add_argument("--umbral", type=float)
    a = ap.parse_args()
    imprimir(responder(a.pregunta, a.k, a.modelo, a.umbral))


if __name__ == "__main__":
    main()
