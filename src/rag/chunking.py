"""
Chunking por seccion de las FDS (Markdown -> fragmentos con metadatos de trazabilidad).

Reglas (todas documentadas para el informe):
  1. Un fragmento NUNCA cruza de una seccion a otra: se corta primero por seccion (las 16 del SGA)
     y luego por tamano dentro de cada seccion.
  2. La seccion se detecta por el titulo (reutiliza secciones.py, que tambien cubre el formato antiguo
     NTC 4435 con 2/3 intercambiadas) y, para FDS_100/101, por titulos incrustados en un parrafo.
  3. Tamano maximo ~1500 caracteres (~450 tokens); solape ~250 caracteres (~80 tokens) arrastrando
     bloques completos. Las tablas se parten por filas repitiendo su encabezado, nunca a mitad de fila.
  4. Cada fragmento guarda: documento, fabricante, producto, version, paginas, seccion e imagenes
     enlazadas. El texto que se EMBEBE lleva un encabezado contextual; el texto que se le PASA al
     generador es solo el cuerpo (la cita sale de los metadatos, no del texto).
  5. Solo se normaliza el espaciado de las tablas (espacios y guiones de relleno); no se altera contenido.

Salida: data/chunks.jsonl  y  data/chunks_resumen.csv
Uso: python chunking.py [--max-chars 1500 --solape 250]
"""
import argparse, csv, html, json, re, sys, statistics
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "src" / "extraccion"))
from secciones import seccion_en_linea, seccion_sin_numero   # noqa: E402

MD_DIR = RAIZ / "data" / "markdown"
SALIDA = RAIZ / "data" / "chunks.jsonl"
RESUMEN = RAIZ / "data" / "chunks_resumen.csv"

NOMBRES = {0: "Encabezado del documento", 1: "Identificacion del producto y del proveedor", 2: "Identificacion de los peligros",
           3: "Composicion / informacion sobre los componentes", 4: "Primeros auxilios",
           5: "Medidas de lucha contra incendios", 6: "Medidas en caso de vertido accidental",
           7: "Manipulacion y almacenamiento", 8: "Controles de exposicion / proteccion personal",
           9: "Propiedades fisicas y quimicas", 10: "Estabilidad y reactividad", 11: "Informacion toxicologica",
           12: "Informacion ecologica", 13: "Consideraciones sobre la eliminacion", 14: "Informacion relativa al transporte",
           15: "Informacion reglamentaria", 16: "Otra informacion"}
INLINE = re.compile(r"\s+(?=SECCI[OÓ]N\s+\d{1,2}\s*:\s*[A-ZÁÉÍÓÚ])")      # titulo incrustado en un parrafo
TITULO_PEGADO = re.compile(r"^(SECCI[OÓ]N\s+\d{1,2}\s*:\s*[A-ZÁÉÍÓÚÑ ,/]+?)\s+(?=\d{1,2}\.\d)")
IMG = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")


def leer_md(ruta):
    """Lee un .md y devuelve su cabecera YAML y la lista de (pagina, linea) del cuerpo.
    param : ruta : Path del Markdown
    return: tupla (dict cabecera, list[(int pagina, str linea)])
    """
    texto = ruta.read_text(encoding="utf-8")
    m = re.match(r"---\n(.*?)\n---\n", texto, re.S)
    cab = dict(re.findall(r"^(\w+):\s*(.*)$", m.group(1), re.M)) if m else {}
    pagina, lineas = 1, []
    for linea in texto[m.end():].splitlines() if m else texto.splitlines():
        mp = re.match(r"<!-- pagina (\d+) -->", linea)
        if mp:
            pagina = int(mp.group(1)); continue
        linea = html.unescape(linea)               # Docling escapa '<' como &lt; (cambia el sentido de '<99')
        for parte in INLINE.split(linea):          # parte titulos incrustados (FDS_100/101)
            if re.fullmatch(r"\s*#+\s*", parte):   # encabezado vacio
                continue
            # "SECCION 5: MEDIDAS DE LUCHA... 5.1 Medios..." -> el titulo en mayusculas queda en su propia linea
            parte = TITULO_PEGADO.sub(r"\1\n", parte)
            for sub in parte.split("\n"):
                lineas.append((pagina, sub))
    return cab, lineas


def normaliza_tabla(linea):
    """Compacta el relleno de una fila de tabla Markdown (no cambia el contenido de las celdas).
    param : linea : str
    return: str
    """
    linea = re.sub(r"-{3,}", "---", linea)
    return re.sub(r"[ \t]{2,}", " ", linea).strip()


def dividir_secciones(lineas):
    """Asigna cada linea a una seccion canonica segun los titulos detectados.
    param : lineas : list[(pagina, linea)]
    return: list[dict(seccion, titulo, lineas)] en orden de aparicion
    """
    secs, actual = [], dict(seccion=0, titulo="", lineas=[])
    for pag, lin in lineas:
        r = seccion_en_linea(lin)
        if r is None and 6 <= len(lin) <= 60 and not lin.lstrip().startswith("|"):
            q = seccion_sin_numero(lin)                       # titulo sin numero (ej. FDS_002 sec. 4)
            if q and q[1] > actual["seccion"] and q[1] <= actual["seccion"] + 2:
                r = (None, q[1], q[2])
        if r and r[1] != actual["seccion"]:
            secs.append(actual)
            actual = dict(seccion=r[1], titulo=re.sub(r"^[#>*\s]+", "", lin).strip(" #*|"), lineas=[])
        actual["lineas"].append((pag, lin))
    secs.append(actual)
    secs = [s for s in secs if any(l.strip() for _, l in s["lineas"])]
    if len(secs) > 1 and secs[0]["seccion"] == 0 and secs[1]["seccion"] == 1:
        secs[1]["lineas"] = secs[0]["lineas"] + secs[1]["lineas"]      # titulo/producto previo a la seccion 1
        secs = secs[1:]
    return secs


def bloques(lineas, imagenes):
    """Agrupa lineas en bloques (parrafos, tablas, encabezados); extrae las imagenes enlazadas.
    param : lineas : list[(pagina, linea)]; imagenes : list donde se agregan las rutas de imagen
    return: list[dict(texto, pagina, tabla)]
    """
    out, buf, tabla = [], [], False

    def cerrar():
        nonlocal buf, tabla
        if buf:
            out.append(dict(texto="\n".join(t for _, t in buf), pagina=buf[0][0], tabla=tabla))
        buf, tabla = [], False

    for pag, lin in lineas:
        for ruta in IMG.findall(lin):
            imagenes.append((pag, ruta))
        lin = IMG.sub("", lin).rstrip()
        if not lin.strip():
            cerrar(); continue
        es_tabla = lin.lstrip().startswith("|")
        if es_tabla != tabla:
            cerrar()
        tabla = es_tabla
        buf.append((pag, normaliza_tabla(lin) if es_tabla else lin.strip()))
    cerrar()
    return out


def trocear(bloque, max_chars):
    """Parte un bloque mayor que max_chars: tablas por filas (repitiendo encabezado), texto por frases.
    param : bloque : dict; max_chars : int
    return: list[dict] de bloques de tamano <= max_chars (salvo una fila/palabra indivisible)
    """
    txt = bloque["texto"]
    if len(txt) <= max_chars:
        return [bloque]
    if bloque["tabla"]:
        filas = txt.split("\n")
        cab = filas[:2] if len(filas) > 2 and re.fullmatch(r"\|[-| :]+\|?", filas[1]) else []
        partes, actual = [], list(cab)
        resto = []
        for f in filas[len(cab):]:                     # fila gigante: se parte por palabras en varias filas
            while len(f) > max_chars - len("\n".join(cab)) - 2:
                lim = max_chars - len("\n".join(cab)) - 2
                corte = f.rfind(" ", 0, lim)
                corte = corte if corte > 0 else lim
                resto.append(f[:corte]); f = "| " + f[corte:].strip()
            resto.append(f)
        for f in resto:
            if len("\n".join(actual + [f])) > max_chars and len(actual) > len(cab):
                partes.append("\n".join(actual)); actual = list(cab)
            actual.append(f)
        partes.append("\n".join(actual))
        trozos = partes
    else:
        frases = re.split(r"(?<=[.;:])\s+(?=[A-ZÁÉÍÓÚ0-9¿¡])", txt)
        trozos, actual = [], ""
        for fr in frases:
            while len(fr) > max_chars:                         # frase interminable: corte por palabras
                corte = fr.rfind(" ", 0, max_chars)
                corte = corte if corte > 0 else max_chars
                if actual: trozos.append(actual); actual = ""
                trozos.append(fr[:corte]); fr = fr[corte:].strip()
            if actual and len(actual) + len(fr) + 1 > max_chars:
                trozos.append(actual); actual = fr
            else:
                actual = f"{actual} {fr}".strip()
        if actual: trozos.append(actual)
    return [dict(texto=t, pagina=bloque["pagina"], tabla=bloque["tabla"]) for t in trozos if t.strip()]


def empaquetar(bls, max_chars, solape):
    """Junta bloques en fragmentos de <= max_chars con solape de bloques completos.
    param : bls : list[dict]; max_chars : int; solape : int caracteres minimos de solape
    return: list[list[dict]] fragmentos (cada uno es una lista de bloques)
    """
    chunks, actual, n = [], [], 0
    for b in bls:
        if actual and n + len(b["texto"]) + 2 > max_chars:
            chunks.append(actual)
            keep, m = [], 0
            for x in reversed(actual):
                if m >= solape: break
                keep.insert(0, x); m += len(x["texto"])
            if m > max_chars * 0.5 or len(b["texto"]) + m > max_chars:   # solape demasiado grande: se omite
                keep = []
            actual = keep
            n = sum(len(x["texto"]) + 2 for x in actual)
        actual.append(b); n += len(b["texto"]) + 2
    if actual:
        chunks.append(actual)
    return chunks


def fragmentos_de_doc(ruta, meta, max_chars, solape):
    """Genera los fragmentos de una FDS con todos sus metadatos.
    param : ruta : Path del .md; meta : dict fila de corpus.csv; max_chars, solape : int
    return: list[dict] fragmentos
    """
    cab, lineas = leer_md(ruta)
    prod = (meta["producto_en_documento"] or meta["producto_nombre_archivo"]).strip()
    version = meta["version_documento"] or ""
    fecha = meta["fecha_emision"] or meta["fecha_revision"] or meta["fecha_actualizacion"] or meta["fecha_otra"] or ""
    out, contador = [], {}
    for sec in dividir_secciones(lineas):
        imgs = []
        bls = [t for b in bloques(sec["lineas"], imgs) for t in trocear(b, max_chars)]
        for grupo in empaquetar(bls, max_chars, solape):
            n = sec["seccion"]
            contador[n] = contador.get(n, 0) + 1
            cuerpo = "\n\n".join(b["texto"] for b in grupo).strip()
            pags = sorted({b["pagina"] for b in grupo})
            pa, pb = pags[0], pags[-1]
            ref = f"Fabricante: {meta['fabricante']} | Producto: {prod} | Seccion {n}: {NOMBRES[n]}" if n else \
                  f"Fabricante: {meta['fabricante']} | Producto: {prod} | {NOMBRES[0]}"
            imagenes = sorted({r for p, r in imgs if pa <= p <= pb})
            out.append(dict(chunk_id=f"{meta['id']}_s{n:02d}_{contador[n]:02d}", doc_id=meta["id"],
                            documento=meta["archivo"], fabricante=meta["fabricante"], producto=prod,
                            version=version, fecha=fecha, seccion=n, seccion_nombre=NOMBRES[n],
                            seccion_titulo_documento=sec["titulo"], pagina_inicio=pa, pagina_fin=pb,
                            imagenes=imagenes, n_chars=len(cuerpo), texto=cuerpo,
                            texto_indexado=f"{ref}\n\n{cuerpo}"))
    return out


def main():
    """Fragmenta las 101 FDS y escribe chunks.jsonl y chunks_resumen.csv.
    param : --max-chars, --solape
    return: None
    """
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-chars", type=int, default=1500)
    ap.add_argument("--solape", type=int, default=250)
    a = ap.parse_args()
    corpus = {r["id"]: r for r in csv.DictReader(open(RAIZ / "data" / "corpus.csv", encoding="utf-8"))}
    todos = []
    for f in sorted(MD_DIR.glob("FDS_*.md")):
        todos += fragmentos_de_doc(f, corpus[f.stem], a.max_chars, a.solape)
    with open(SALIDA, "w", encoding="utf-8") as fh:
        for c in todos:
            fh.write(json.dumps(c, ensure_ascii=False) + "\n")
    tam = [c["n_chars"] for c in todos]
    por_sec = {n: sum(1 for c in todos if c["seccion"] == n) for n in range(0, 17)}
    docs = {}
    for c in todos:
        docs.setdefault(c["doc_id"], 0); docs[c["doc_id"]] += 1
    with open(RESUMEN, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh); w.writerow(["doc_id", "fragmentos"]); w.writerows(sorted(docs.items()))
    print(f"{len(todos)} fragmentos de {len(docs)} documentos")
    print(f"caracteres: min {min(tam)}  mediana {int(statistics.median(tam))}  media {int(statistics.mean(tam))}  max {max(tam)}")
    print("por seccion:", por_sec)
    print("fragmentos < 150 caracteres:", sum(1 for t in tam if t < 150), "| > max:", sum(1 for t in tam if t > a.max_chars))


if __name__ == "__main__":
    main()
