"""
Piloto de extraccion PDF -> Markdown: compara PyMuPDF4LLM y Docling
sobre un subconjunto variado de FDS. Mide tiempo, tamano, tablas y
cobertura de texto frente a pdftotext. No modifica los PDF originales.
"""
import sys, time, json, re, subprocess
from pathlib import Path

RAIZ = Path.home() / "rag-fds"
PDF_DIR = RAIZ / "data" / "pdf" / "FDS EVALUADAS"
SALIDA = RAIZ / "data" / "markdown" / "piloto"
PILOTO = ["FDS 71 ", "FDS 63 ", "FDS 5 ", "FDS 51 ", "FDS 49 ", "FDS 66 "]


def buscar_pdfs():
    """Devuelve la lista de PDF del piloto (por prefijo de nombre)."""
    todos = sorted(PDF_DIR.rglob("*.pdf"))
    return [p for pre in PILOTO for p in todos if p.name.startswith(pre)][:len(PILOTO)]


def contar_tablas(md):
    """Cuenta bloques de tabla markdown (filas separadoras |---|)."""
    return len(re.findall(r"^\|[\s:|-]*-[\s:|-]*\|\s*$", md, flags=re.M))


def texto_base(pdf):
    """Texto plano de pdftotext, usado como linea base de cobertura."""
    out = subprocess.run(["pdftotext", "-layout", str(pdf), "-"], capture_output=True, text=True).stdout
    return re.sub(r"\s+", "", out)


def con_pymupdf(pdf):
    import pymupdf4llm
    return pymupdf4llm.to_markdown(str(pdf))


_conv = None
def con_docling(pdf):
    global _conv
    if _conv is None:
        from docling.document_converter import DocumentConverter, PdfFormatOption
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import PdfPipelineOptions
        opt = PdfPipelineOptions(do_ocr=False, do_table_structure=True)
        _conv = DocumentConverter(format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=opt)})
    return _conv.convert(str(pdf)).document.export_to_markdown()


def main():
    SALIDA.mkdir(parents=True, exist_ok=True)
    filas = []
    for pdf in buscar_pdfs():
        base = texto_base(pdf)
        for nombre, fn in (("pymupdf4llm", con_pymupdf), ("docling", con_docling)):
            t0 = time.time()
            try:
                md = fn(pdf); error = ""
            except Exception as e:
                md = ""; error = repr(e)[:200]
            seg = round(time.time() - t0, 1)
            d = SALIDA / nombre; d.mkdir(exist_ok=True)
            (d / (pdf.stem[:60] + ".md")).write_text(md, encoding="utf-8")
            plano = re.sub(r"\s+", "", md)
            fila = dict(pdf=pdf.name[:60], herramienta=nombre, segundos=seg, chars=len(plano),
                        chars_pdftotext=len(base), tablas=contar_tablas(md), error=error)
            filas.append(fila); print(json.dumps(fila, ensure_ascii=False), flush=True)
    (SALIDA / "resumen.json").write_text(json.dumps(filas, ensure_ascii=False, indent=1), encoding="utf-8")
    print("PILOTO_TERMINADO", flush=True)


if __name__ == "__main__":
    main()
