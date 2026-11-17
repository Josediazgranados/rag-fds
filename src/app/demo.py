"""
Demo web (Gradio) del RAG sobre las FDS: pregunta -> respuesta con fuentes verificables.

Muestra: la respuesta, la tabla de fuentes citadas (fabricante, producto, documento, pagina, seccion),
los fragmentos recuperados con su puntaje y el tiempo de respuesta. El top-k es seleccionable (3 o 6).

Uso:  python demo.py            # abre http://localhost:7860  (en el servidor: --host 0.0.0.0)
      python demo.py --host 0.0.0.0 --puerto 7860
Requiere: indice construido (python ../rag/indice.py construir) y Ollama con qwen2.5:3b.
"""
import argparse, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "rag"))
from generar import responder, MODELO_LLM   # noqa: E402

EJEMPLOS = [
    ["¿Cuál es el punto de inflamación del Sellador Industrial Nitrocelulósico (código 40030020) de Química Cosmos?", 3],
    ["¿Qué medios de extinción se pueden utilizar para el Dimetcote 302H Green Resin de PPG y cuál no se debe usar?", 3],
    ["Entre el Sigmadur One Buff 3142 y el Dimetcote 302H Green Resin, ambos de PPG, ¿cuál tiene el punto de inflamación más bajo?", 6],
    ["¿Cuál es el rendimiento en metros cuadrados por galón de la pintura Koraza Pro 550 Blanco de Pintuco?", 3],
]


def consultar(pregunta, k):
    """Ejecuta el RAG y da formato a los resultados para la interfaz.
    param : pregunta : str; k : int top-k
    return: tupla (respuesta str, fuentes list[list], fragmentos str, estado str)
    """
    if not pregunta or not pregunta.strip():
        return "Escribe una pregunta.", [], "", ""
    r = responder(pregunta.strip(), int(k))
    fuentes = [[s["n"], s["fabricante"], s["producto"], s["documento"], s["paginas"], s["seccion"]] for s in r["sources"]]
    frags = "\n\n".join(f"[{x['n']}] {x['chunk_id']} (puntaje {x['puntaje']})\n{t[:700]}"
                        for x, t in zip(r["retrieved"], r["retrieved_contexts"]))
    return r["response"], fuentes, frags, f"top-k={r['top_k']} | modelo {r['modelo']} | {r['segundos']} s"


def main():
    """Lanza la interfaz Gradio.
    param : --host, --puerto
    return: None
    """
    import gradio as gr
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1"); ap.add_argument("--puerto", type=int, default=7860)
    a = ap.parse_args()
    with gr.Blocks(title="RAG sobre Fichas de Datos de Seguridad") as demo:
        gr.Markdown("# RAG sobre 101 Fichas de Datos de Seguridad (pinturas y recubrimientos)\n"
                    "Responde solo con la evidencia de las fichas y cita fabricante, producto, documento, página y sección. "
                    "Si no hay evidencia suficiente, lo dice. Modelo local: " + MODELO_LLM + " (CPU; tarda del orden de minutos).")
        with gr.Row():
            pregunta = gr.Textbox(label="Pregunta", lines=2, scale=4)
            k = gr.Radio([3, 6], value=3, label="top-k (fragmentos recuperados)", scale=1)
        boton = gr.Button("Consultar", variant="primary")
        respuesta = gr.Textbox(label="Respuesta", lines=4)
        fuentes = gr.Dataframe(headers=["n", "Fabricante", "Producto", "Documento", "Página", "Sección"],
                               label="Fuentes citadas (armadas desde los metadatos del fragmento)", wrap=True)
        estado = gr.Markdown()
        with gr.Accordion("Fragmentos recuperados", open=False):
            frags = gr.Textbox(lines=14, show_label=False)
        boton.click(consultar, [pregunta, k], [respuesta, fuentes, frags, estado])
        gr.Examples(EJEMPLOS, [pregunta, k])
    demo.launch(server_name=a.host, server_port=a.puerto)


if __name__ == "__main__":
    main()
