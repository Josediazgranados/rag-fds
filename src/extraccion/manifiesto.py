"""
Manifiesto del corpus de FDS: procedencia, version y datos de identificacion de cada ficha.

Lee los metadatos del PDF ORIGINAL (primeras paginas, via pdftotext) y los registra tal como
aparecen. No infiere: si un dato no aparece en el documento queda vacio y la ficha se marca
en la columna 'revisar' para comprobacion manual.

Salida: data/corpus.csv   (una fila por FDS)
Uso: python manifiesto.py
"""
import csv, re, subprocess, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from extraer import PDF_DIR, RAIZ, identificar, sha256   # mismo identificador FDS_NNN

SALIDA = RAIZ / "data" / "corpus.csv"
PAGINAS_META = "3"          # los datos de version/emision estan en las primeras paginas

# Alias de fabricante (regla explicita y revisable; se aplica a proveedor y nombre de archivo)
ALIAS = [
    ("Pintuco (AkzoNobel)", r"pintuco|compa[ñn][ií]a global de pinturas|akzo|aksonobel|international"),
    ("Corona", r"corlanc|corona"),
    ("Sika", r"\bsika\b"),
    ("PPG", r"\bppg\b"),
    ("Invesa", r"invesa|sapolin"),
    ("Pintuland", r"pintuland"),
    ("Bler", r"\bbler\b|pintubler"),
    ("Axalta", r"axalta"),
]
FECHA = r"(\d{4}[/\-.]\d{1,2}[/\-.]\d{1,2}|\d{1,2}[/\-.]\d{1,2}[/\-.]\d{2,4}|\d{1,2}\s+(?:de\s+)?[A-Za-záéíóú]+\s+(?:de\s+)?\d{4}|[A-Za-záéíóú]+\s+de\s+\d{4})"


def texto_pdf(pdf, ultima=PAGINAS_META):
    """Texto de las primeras paginas y numero total de paginas del PDF.
    param : pdf : Path; ultima : str ultima pagina a leer
    return: tupla (texto, paginas)
    """
    info = subprocess.run(["pdfinfo", str(pdf)], capture_output=True, text=True).stdout
    paginas = int(re.search(r"Pages:\s+(\d+)", info).group(1))
    txt = subprocess.run(["pdftotext", "-layout", "-f", "1", "-l", ultima, str(pdf), "-"],
                         capture_output=True, text=True).stdout
    return txt, paginas


def primero(patron, texto, flags=re.I):
    """Primer grupo capturado por un patron, limpio de espacios.
    param : patron : regex con un grupo; texto : str
    return: str ('' si no hay coincidencia)
    """
    m = re.search(patron, texto, flags)
    return re.sub(r"\s+", " ", m.group(1)).strip(" :.-") if m else ""


def proveedor(texto):
    """Proveedor/empresa tal como figura en el documento.
    param : texto : str de las primeras paginas
    return: str ('' si no se encuentra)
    """
    v = primero(r"^\s*(?:Empresa|Compa[ñn][ií]a|Proveedor|Raz[oó]n social)\s*:\s*([^\n]{3,80})", texto, re.I | re.M)
    if v:
        return v
    v = primero(r"Datos (?:sobre el|del) proveedor(?: o)?\s*:\s*([^\n]{3,80})", texto)   # formato Axalta
    if v:
        return v
    m = re.search(r"Datos (?:sobre el|del) proveedor[^\n]*\n(?:\s*\n)*\s*([^\n]{3,80})", texto, re.I)
    return re.sub(r"\s+", " ", m.group(1)).strip() if m else ""


def fabricante(prov, nombre_archivo):
    """Fabricante normalizado por reglas de alias; si no hay alias usa el proveedor del documento.
    param : prov : str proveedor en el documento; nombre_archivo : str
    return: tupla (fabricante, fuente)
    """
    for nombre, patron in ALIAS:
        if re.search(patron, prov, re.I):
            return nombre, "proveedor_documento"
    for nombre, patron in ALIAS:
        if re.search(patron, nombre_archivo, re.I):
            return nombre, "nombre_archivo"
    return (prov, "proveedor_documento") if prov else ("", "")


def producto_archivo(nombre):
    """Nombre de producto segun el nombre del archivo (sin prefijo 'FDS N -' ni extension).
    param : nombre : str nombre del PDF
    return: str
    """
    t = re.sub(r"\.pdf$", "", nombre, flags=re.I)
    t = re.sub(r"^FDS\s*\d+\s*[-–_]*\s*", "", t)
    return re.sub(r"\s+", " ", t).strip()


def main():
    """Construye data/corpus.csv para todos los PDF.
    param : ninguno
    return: None
    """
    pdfs = sorted(PDF_DIR.rglob("*.pdf"), key=lambda p: (int(re.match(r"FDS\s*(\d+)", p.name).group(1)), p.name))
    usados, filas = {}, []
    for pdf in pdfs:
        ident = identificar(pdf, usados)
        txt, paginas = texto_pdf(pdf)
        prov = proveedor(txt)
        fab, fuente = fabricante(prov, pdf.name)
        version = primero(r"Versi[oó]n\s*:?\s*(\d+(?:[.,]\d+)?(?:\s*\(sustituye a [^)]+\))?)", txt)
        emision = primero(r"(?:Fecha de )?Emisi[oó]n(?:/Fecha de revisi[oó]n)?\s*:?\s*" + FECHA, txt)
        revision = primero(r"(?<!/)Revisi[oó]n\s*:?\s*" + FECHA, txt)
        actualiz = primero(r"Fecha de actualizaci[oó]n\s*:?\s*" + FECHA, txt)
        otra = ""
        if not (emision or revision or actualiz):    # buscar en todo el documento antes de dejar vacio
            todo, _ = texto_pdf(pdf, "9999")
            m = re.search(r"(Fecha(?: de)? (?:elaboraci[oó]n|emisi[oó]n|revisi[oó]n|actualizaci[oó]n|impresi[oó]n)[^:\n]{0,20})\s*:?\s*" + FECHA, todo, re.I)
            otra = f"{re.sub(chr(32)+'+', chr(32), m.group(1)).strip()}: {m.group(2)}" if m else ""
        prod_doc = primero(r"(?:Nombre comercial|Nombre del producto|Identificador SGA del producto|Identificador del producto)\s*:?\s*([^\n]{3,100})", txt)
        v_arch = primero(r"Versi[oó]n\s*(\d+)", pdf.name)
        fila = dict(id=ident, anio_carpeta=pdf.parent.name.replace("FDS ", ""), archivo=pdf.name,
                    ruta_pdf=str(pdf.relative_to(PDF_DIR.parent)), sha256=sha256(pdf), paginas=paginas,
                    proveedor_en_documento=prov, fabricante=fab, fuente_fabricante=fuente,
                    producto_nombre_archivo=producto_archivo(pdf.name), producto_en_documento=prod_doc,
                    version_documento=version, fecha_emision=emision, fecha_revision=revision,
                    fecha_actualizacion=actualiz, fecha_otra=otra, version_en_nombre_archivo=v_arch)
        faltan = [k for k in ("fabricante", "version_documento") if not fila[k]]
        if not (emision or revision or actualiz or otra):
            faltan.append("fecha")
        fila["revisar"] = ";".join(faltan)
        filas.append(fila)
    with open(SALIDA, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(filas[0])); w.writeheader(); w.writerows(filas)
    print(f"{len(filas)} fichas -> {SALIDA}")
    for campo in ("fabricante", "version_documento", "fecha_emision", "fecha_revision", "fecha_actualizacion", "fecha_otra", "producto_en_documento"):
        print(f"  {campo:22s} vacios: {sum(1 for f in filas if not f[campo])}")
    print("  fichas a revisar:", sum(1 for f in filas if f["revisar"]))
    print("  fabricantes:", {k: sum(1 for f in filas if f['fabricante'] == k) for k in sorted({f['fabricante'] for f in filas})})


if __name__ == "__main__":
    main()
