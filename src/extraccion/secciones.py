"""
Deteccion de las 16 secciones de cada FDS, en el PDF original y en el Markdown extraido.

Compara (a) el texto del PDF (pdftotext, pagina a pagina) con (b) el Markdown generado:
  presente          : la seccion aparece en el PDF y en el Markdown
  presente_sin_numero: aparece como titulo pero sin numero en el PDF o en el Markdown (revisar)
  presente_en_parrafo: el titulo esta en el Markdown pero incrustado en un parrafo (estructura perdida)
  fallo_extraccion  : aparece en el PDF pero NO en el Markdown
  ausente_original  : no aparece ni en el PDF ni en el Markdown (no se completa por inferencia)
  solo_markdown     : aparece en el Markdown pero no en el texto del PDF (revisar a mano)
Limitacion: si el PDF tiene el encabezado solo como imagen, pdftotext no lo ve y se
reportaria como ausente; por eso toda 'ausente_original' se debe confirmar visualmente.

Salida: data/markdown/_secciones.csv  y  data/markdown/_secciones_resumen.csv
Uso: python secciones.py
"""
import csv, re, subprocess
from pathlib import Path

RAIZ = Path.home() / "rag-fds"
MD_DIR = RAIZ / "data" / "markdown"
PDF_DIR = RAIZ / "data" / "pdf"

# Clasificacion de una seccion por su TITULO (orden importa: lo mas especifico primero).
# Algunas FDS (formato antiguo NTC 4435) numeran distinto: ej. "2. Composicion" y
# "3. Identificacion de riesgos". Se guarda el numero del documento y la seccion canonica SGA.
TITULOS = [
    (4,  r"primeros auxilios"),
    (5,  r"incendio"),
    (6,  r"vertido|derrame|liberaci.n(es)? accidental|escape accidental"),
    (7,  r"manejo|manipulaci.n|almacen"),
    (8,  r"controles? de (la )?exposici.n|protecci.n personal|l.mites de exposici.n"),
    (9,  r"propiedades f.sicas|propiedades fisicoqu.micas"),
    (10, r"estabilidad|reactividad"),
    (12, r"ecol.gic|ecotoxic"),          # antes que 11: "ecotoxicologica" contiene "toxicolog"
    (11, r"toxicol.gic|toxicidad"),
    (13, r"eliminaci.n|disposici.n|residuos|desecho"),
    (14, r"transporte"),
    (15, r"reglament|normativ|regulaci.n"),
    (16, r"otras? informaci.n|otras informaciones|informaci.n adicional|otros datos"),
    (1,  r"identificaci.n de la (sustancia|mezcla|preparaci.n)|identificaci.n del (producto|preparado)"),  # antes que 2: contiene "peligrosa"
    (3,  r"composici.n|ingredientes|componentes"),
    (2,  r"riesgos?|peligros?"),
    (1,  r"identificaci.n|identificacion"),
]
LIMPIA = re.compile(r"^[\s#>*|_\-]+|[\s*|_]+$")


def normaliza(linea):
    """Quita marcas de markdown y pasa a minusculas.
    param : linea : str
    return: str limpio
    """
    return LIMPIA.sub("", linea).lower()


def seccion_en_linea(linea):
    """Interpreta una linea como encabezado de seccion de FDS.
    param : linea : str de texto
    return: tupla (numero_en_documento, seccion_canonica, titulo) o None
    """
    if "|" in linea:    # encabezado dentro de una fila de tabla: se usa la primera celda con texto
        celdas = [c for c in linea.split("|") if c.strip()]
        linea = celdas[0] if celdas else linea
    t = normaliza(linea)
    m = re.match(r"^(?:secci.n\s*)?(\d{1,2})\s*[.:)\-–—]?\s*(.{3,110})$", t)
    if not m:
        return None
    num, resto = int(m.group(1)), m.group(2).strip()
    if not 1 <= num <= 16 or re.match(r"^\d", resto):   # 1.1, 3.2 ... son subsecciones
        return None
    for canon, patron in TITULOS:
        if re.search(patron, resto):
            # Coherencia: solo 2 y 3 se permutan en el formato antiguo NTC 4435 (2=Composicion, 3=Riesgos).
            # Para el resto el numero del documento debe coincidir; si no, es una subseccion (ej. 8 ... higiene).
            if canon not in (2, 3) and num != canon:
                return None
            return num, canon, resto
    return None


def seccion_sin_numero(linea):
    """Detecta un titulo de seccion SIN numero (ej. 'Primeros auxilios:' o 'PRIMEROS AUXILIOS').
    Solo acepta lineas cortas que sean un titulo puro, para limitar falsos positivos.
    param : linea : str de texto
    return: tupla ('', seccion_canonica, titulo) o None
    """
    t = normaliza(linea)
    if not 6 <= len(t) <= 45 or re.search(r"\d", t):
        return None
    if not (t.endswith(":") or linea.strip().lstrip("#*| ").isupper()):
        return None
    for canon, patron in TITULOS:
        if re.fullmatch(r"[^a-z]*(?:" + patron + r")[^a-z]*[a-z ]{0,30}:?", t):
            return "", canon, t
    return None


def secciones_pdf(pdf):
    """Secciones halladas en el PDF (primera aparicion de cada seccion canonica).
    param : pdf : Path
    return: dict {seccion_canonica: (numero_en_documento, titulo, pagina)}
    """
    info = subprocess.run(["pdfinfo", str(pdf)], capture_output=True, text=True).stdout
    paginas = int(re.search(r"Pages:\s+(\d+)", info).group(1))
    hall, sn = {}, {}
    for p in range(1, paginas + 1):
        txt = subprocess.run(["pdftotext", "-layout", "-f", str(p), "-l", str(p), str(pdf), "-"],
                             capture_output=True, text=True).stdout
        for linea in txt.splitlines():
            r = seccion_en_linea(linea)
            if r and r[1] not in hall:
                hall[r[1]] = (r[0], r[2], p)
            q = None if r else seccion_sin_numero(linea)
            if q and q[1] not in sn:
                sn[q[1]] = (q[0], q[2], p)
    for k, v in sn.items():
        hall.setdefault(k, v)
    return hall


def secciones_md(md):
    """Secciones halladas en el Markdown, con la pagina segun los marcadores.
    param : md : str con el contenido del .md
    return: dict {seccion_canonica: (numero_en_documento, titulo, pagina)}
    """
    hall, sn, pagina = {}, {}, 1
    for linea in md.splitlines():
        m = re.match(r"<!-- pagina (\d+) -->", linea)
        if m:
            pagina = int(m.group(1))
            continue
        r = seccion_en_linea(linea)
        if r and r[1] not in hall:
            hall[r[1]] = (r[0], r[2], pagina)
        q = None if r else seccion_sin_numero(linea)
        if q and q[1] not in sn:
            sn[q[1]] = (q[0], q[2], pagina)
    for k, v in sn.items():
        hall.setdefault(k, v)
    return hall


def main():
    """Genera _secciones.csv y _secciones_resumen.csv para todos los .md existentes.
    param : ninguno
    return: None
    """
    filas, resumen = [], []
    for f in sorted(MD_DIR.glob("FDS_*.md")):
        md = f.read_text(encoding="utf-8")
        pdf = PDF_DIR / re.search(r'ruta_pdf: "(.+)"', md).group(1)
        hp, hm = secciones_pdf(pdf), secciones_md(md)
        cuenta = dict(presente=0, presente_sin_numero=0, presente_en_parrafo=0, fallo_extraccion=0, ausente_original=0, solo_markdown=0,
                      numeracion_distinta=0)
        for n in range(1, 17):
            if n in hp and n in hm:
                est = "presente" if (hp[n][0] != "" and hm[n][0] != "") else "presente_sin_numero"
            elif n in hp:
                # el titulo no esta al inicio de linea pero si dentro de un parrafo (bloques fusionados)
                inline = re.search(rf"secci.n\s*{n}\s*[:.]\s*\S", md, re.I)
                est = "presente_en_parrafo" if inline else "fallo_extraccion"
            elif n in hm: est = "solo_markdown"
            else: est = "ausente_original"
            cuenta[est] += 1
            ref = hp.get(n) or hm.get(n)
            distinta = bool(ref and ref[0] != "" and ref[0] != n)
            cuenta["numeracion_distinta"] += distinta
            filas.append(dict(id=f.stem, seccion_canonica=n,
                              numero_en_documento=ref[0] if ref else "", titulo_detectado=ref[1] if ref else "",
                              pagina_pdf=hp[n][2] if n in hp else "", pagina_md=hm[n][2] if n in hm else "",
                              numeracion_distinta="si" if distinta else "", estado=est))
        resumen.append(dict(id=f.stem, **cuenta))
    for nombre, datos in (("_secciones.csv", filas), ("_secciones_resumen.csv", resumen)):
        if datos:
            with open(MD_DIR / nombre, "w", newline="", encoding="utf-8") as fh:
                w = csv.DictWriter(fh, fieldnames=list(datos[0])); w.writeheader(); w.writerows(datos)
    print(f"{len(resumen)} fichas analizadas")
    for r in resumen:
        print(r)


if __name__ == "__main__":
    main()
