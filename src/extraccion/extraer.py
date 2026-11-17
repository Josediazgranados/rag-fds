"""
Extraccion PDF -> Markdown de las Fichas de Datos de Seguridad (FDS) con Docling.

Por cada PDF genera:
  data/markdown/FDS_NNN.md          Markdown con marcadores <!-- pagina N -->
  data/imagenes/FDS_NNN/*.png       imagenes tecnicas enlazadas con ruta relativa
  data/imagenes/FDS_NNN/imagenes.json  documento, pagina, tamano y texto OCR por imagen
y agrega una linea a data/markdown/_log_extraccion.jsonl (tiempos, paginas, tablas).

Es reanudable: omite los PDF cuyo .md ya existe (usar --forzar para rehacer).
No infiere ni completa informacion: solo transcribe lo que Docling extrae.

Uso:  python extraer.py [--forzar] [--solo "FDS 5 " "FDS 71 "]
"""
import argparse, hashlib, json, re, subprocess, sys, time
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path

RAIZ = Path.home() / "rag-fds"
PDF_DIR = RAIZ / "data" / "pdf" / "FDS EVALUADAS"
MD_DIR = RAIZ / "data" / "markdown"
IMG_DIR = RAIZ / "data" / "imagenes"
LOG = MD_DIR / "_log_extraccion.jsonl"
MIN_LADO_OCR = 80  # px; por debajo se considera icono/pictograma pequeno


def sha256(ruta):
    """Hash SHA-256 de un archivo.
    param : ruta : Path del archivo
    return: str hexadecimal del hash
    """
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


def identificar(pdf, usados):
    """Construye el identificador estable FDS_NNN a partir del nombre del PDF.
    param : pdf : Path del PDF; usados : dict id->PDF para detectar colisiones
    return: str identificador unico (agrega sufijo a/b si el numero se repite)
    """
    m = re.match(r"FDS\s*(\d+)", pdf.name)
    base = f"FDS_{int(m.group(1)):03d}" if m else "FDS_" + hashlib.md5(pdf.name.encode()).hexdigest()[:6]
    ident, i = base, 0
    while ident in usados and usados[ident] != pdf:
        i += 1
        ident = f"{base}{chr(96 + i)}"
    usados[ident] = pdf
    return ident


def crear_conversor():
    """Crea el DocumentConverter de Docling (tablas y imagenes de figuras, sin OCR global).
    param : ninguno
    return: DocumentConverter
    """
    from docling.document_converter import DocumentConverter, PdfFormatOption
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    opt = PdfPipelineOptions(do_ocr=False, do_table_structure=True,
                             generate_picture_images=True, images_scale=2.0)
    return DocumentConverter(format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=opt)})


def ocr_imagen(ruta):
    """Aplica Tesseract (spa+eng) a una imagen y devuelve el texto limpio.
    param : ruta : Path de la imagen
    return: str con el texto detectado ('' si no hay texto util)
    """
    r = subprocess.run(["tesseract", str(ruta), "stdout", "-l", "spa+eng", "--psm", "6"],
                       capture_output=True, text=True)
    texto = re.sub(r"\s+", " ", r.stdout).strip()
    return texto if len(re.findall(r"[A-Za-zÁÉÍÓÚáéíóúÑñ]", texto)) >= 4 else ""


def procesar(pdf, ident, conv):
    """Convierte un PDF a Markdown paginado, guarda imagenes y su OCR.
    param : pdf : Path; ident : str; conv : DocumentConverter
    return: dict con metricas del procesamiento
    """
    from docling_core.types.doc import ImageRefMode
    t0 = time.time()
    doc = conv.convert(str(pdf)).document
    img_dir = IMG_DIR / ident
    img_dir.mkdir(parents=True, exist_ok=True)
    paginas = sorted(doc.pages.keys())
    partes, imagenes = [], []
    for n in paginas:
        md_p = doc.export_to_markdown(page_no=n, image_mode=ImageRefMode.REFERENCED,
                                      image_dir=img_dir, image_uri_prefix=f"../imagenes/{ident}/")
        for rel in re.findall(r"!\[[^\]]*\]\(([^)]+)\)", md_p):
            archivo = img_dir / Path(rel).name
            if not archivo.exists():
                continue
            from PIL import Image
            with Image.open(archivo) as im:
                ancho, alto = im.size
            texto = ocr_imagen(archivo) if min(ancho, alto) >= MIN_LADO_OCR else ""
            imagenes.append(dict(archivo=archivo.name, ruta_relativa=rel, documento=pdf.name,
                                 pagina=n, ancho=ancho, alto=alto, texto_ocr=texto,
                                 nota="" if texto else "sin texto OCR; pictograma o grafico no interpretado"))
        partes.append([n, md_p])
    # Imagenes repetidas en >=3 paginas (logotipos/encabezados): se registran pero no se inyecta su OCR al Markdown
    paginas_por_img = {}
    for im in imagenes:
        paginas_por_img.setdefault(im["archivo"], set()).add(im["pagina"])
    for im in imagenes:
        if len(paginas_por_img[im["archivo"]]) >= 3:
            im["nota"] = f"imagen repetida en {len(paginas_por_img[im['archivo']])} paginas (probable logotipo); OCR no incluido en el Markdown"
    for par in partes:
        n, md_p = par
        for im in imagenes:
            if im["pagina"] == n and im["texto_ocr"] and len(paginas_por_img[im["archivo"]]) < 3:
                md_p = md_p.replace(f"]({im['ruta_relativa']})",
                                    f"]({im['ruta_relativa']})\n\n> Texto OCR de la imagen: {im['texto_ocr']}", 1)
        par[1] = md_p
    partes = [f"<!-- pagina {n} -->\n\n{md_p.strip()}\n" for n, md_p in partes]
    cabecera = (f"---\nid: {ident}\ndocumento: \"{pdf.name}\"\nruta_pdf: \"{pdf.relative_to(PDF_DIR.parent)}\"\n"
                f"sha256: {sha256(pdf)}\npaginas: {len(paginas)}\n"
                f"extractor: docling {version('docling')}\nconvertido: {datetime.now(timezone.utc).isoformat(timespec='seconds')}\n---\n\n")
    (MD_DIR / f"{ident}.md").write_text(cabecera + "\n".join(partes), encoding="utf-8")
    (img_dir / "imagenes.json").write_text(json.dumps(imagenes, ensure_ascii=False, indent=1), encoding="utf-8")
    return dict(id=ident, pdf=pdf.name, paginas=len(paginas), tablas=len(doc.tables),
                imagenes=len(imagenes), imagenes_con_ocr=sum(1 for i in imagenes if i["texto_ocr"]),
                segundos=round(time.time() - t0, 1), error="")


def main():
    """Recorre los PDF, convierte los pendientes y registra el resultado.
    param : argumentos de linea de comandos (--forzar, --solo)
    return: None
    """
    ap = argparse.ArgumentParser()
    ap.add_argument("--forzar", action="store_true")
    ap.add_argument("--solo", nargs="*", default=None, help="prefijos de nombre, ej. 'FDS 5 '")
    args = ap.parse_args()
    MD_DIR.mkdir(parents=True, exist_ok=True)
    pdfs = sorted(PDF_DIR.rglob("*.pdf"), key=lambda p: (int(re.match(r"FDS\s*(\d+)", p.name).group(1)), p.name))
    usados = {}
    trabajo = [(p, identificar(p, usados)) for p in pdfs]
    if args.solo:
        trabajo = [(p, i) for p, i in trabajo if any(p.name.startswith(s) for s in args.solo)]
    pendientes = [(p, i) for p, i in trabajo if args.forzar or not (MD_DIR / f"{i}.md").exists()]
    print(f"{len(trabajo)} PDF en alcance, {len(pendientes)} pendientes", flush=True)
    conv = crear_conversor()
    for k, (pdf, ident) in enumerate(pendientes, 1):
        try:
            fila = procesar(pdf, ident, conv)
        except Exception as e:
            fila = dict(id=ident, pdf=pdf.name, error=repr(e)[:300])
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(fila, ensure_ascii=False) + "\n")
        print(f"[{k}/{len(pendientes)}] {json.dumps(fila, ensure_ascii=False)}", flush=True)
    print("EXTRACCION_TERMINADA", flush=True)


if __name__ == "__main__":
    sys.exit(main())
