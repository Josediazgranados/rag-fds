"""
Verificacion automatica de la extraccion: cobertura de texto PDF -> Markdown por pagina.

Para cada pagina compara las palabras (>=4 letras, sin tildes, en minuscula) que pdftotext ve en el
PDF con las que aparecen en la pagina correspondiente del Markdown. La cobertura es la fraccion de
palabras del PDF (contando repeticiones) que se encuentran en el Markdown. Una cobertura baja indica
texto perdido o desplazado; una cobertura alta NO prueba por si sola que las tablas conserven su
estructura (eso se revisa a mano, ver verificacion_manual).

Limitacion: el texto que esta solo dentro de imagenes no lo ve pdftotext y no se mide aqui.

Salida: data/markdown/_verificacion_paginas.csv  y  data/markdown/_verificacion_docs.csv
Uso: python verificacion.py [--umbral 0.90]
"""
import argparse, csv, re, subprocess, unicodedata
from collections import Counter
from pathlib import Path

RAIZ = Path.home() / "rag-fds"
MD_DIR = RAIZ / "data" / "markdown"
PDF_DIR = RAIZ / "data" / "pdf"


def palabras(texto):
    """Palabras normalizadas (minuscula, sin tildes, >=4 letras) de un texto.
    param : texto : str
    return: Counter palabra -> repeticiones
    """
    t = unicodedata.normalize("NFD", texto.lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return Counter(re.findall(r"[a-z]{4,}", t))


def cobertura(ref, obs):
    """Fraccion de palabras de 'ref' (con repeticiones) presentes en 'obs'.
    param : ref : Counter del PDF; obs : Counter del Markdown
    return: tupla (cobertura, palabras_ref, palabras_faltantes Counter)
    """
    total = sum(ref.values())
    falta = Counter({w: n - obs.get(w, 0) for w, n in ref.items() if n > obs.get(w, 0)})
    return ((total - sum(falta.values())) / total if total else 1.0), total, falta


def cifras(texto):
    """Cifras y datos tecnicos de un texto: numeros, numeros CAS y numero+unidad.
    Se normaliza la coma decimal a punto y se ignoran los espacios dentro de 'numero unidad'.
    param : texto : str
    return: tupla (Counter numeros, Counter CAS, Counter numero+unidad)
    """
    t = texto.replace(" ", " ")
    cas = Counter(re.findall(r"\b\d{2,7}-\d{2}-\d\b", t))
    t2 = re.sub(r"(?<=\d),(?=\d)", ".", t)
    nums = Counter(re.findall(r"(?<![\w.])\d+(?:\.\d+)?", t2))
    uni = Counter(re.sub(r"\s+", "", m).lower() for m in re.findall(
        r"\d+(?:\.\d+)?\s?(?:%|°\s?[CF]|mg/[lm3]+|g/(?:cm3|cm³|l|ml)|kg/m3|mm?hg|kpa|pa|cp|cst|mpa\.?s|ppm|µm|\bl\b|ml|kg|g)\b", t2, re.I))
    return nums, cas, uni


def sin_repetidas(textos, frac=0.4):
    """Quita de cada pagina las lineas que se repiten (encabezados/pies) en >= frac de las paginas.
    Las lineas se comparan con los digitos enmascarados ('Pagina 3 de 12' == 'Pagina 4 de 12').
    param : textos : list[str] texto de cada pagina del PDF; frac : float
    return: tupla (list[str] textos sin repetidas, list[str] lineas repetidas quitadas)
    """
    def clave(l):
        return re.sub(r"\s+", " ", re.sub(r"\d", "#", l)).strip().lower()
    cuenta = Counter()
    for t in textos:
        cuenta.update({clave(l) for l in t.splitlines() if len(clave(l)) > 3})
    umbral = max(3, frac * len(textos))
    rep = {k for k, n in cuenta.items() if n >= umbral}
    return ["\n".join(l for l in t.splitlines() if clave(l) not in rep) for t in textos], sorted(rep)


def paginas_md(md):
    """Divide el Markdown en {pagina: texto} segun los marcadores <!-- pagina N -->.
    param : md : str
    return: dict
    """
    partes = re.split(r"<!-- pagina (\d+) -->", md)
    return {int(partes[i]): partes[i + 1] for i in range(1, len(partes) - 1, 2)}


def main():
    """Calcula la cobertura por pagina y por documento para todos los .md.
    param : --umbral : float, cobertura minima aceptable por pagina
    return: None
    """
    ap = argparse.ArgumentParser()
    ap.add_argument("--umbral", type=float, default=0.90)
    umbral = ap.parse_args().umbral
    filas, docs = [], []
    for f in sorted(MD_DIR.glob("FDS_*.md")):
        md = f.read_text(encoding="utf-8")
        pdf = PDF_DIR / re.search(r'ruta_pdf: "(.+)"', md).group(1)
        pmd = paginas_md(md)
        ref_doc, obs_doc = Counter(), Counter()
        cif_ref, cif_obs = [Counter(), Counter(), Counter()], [Counter(), Counter(), Counter()]
        orden = sorted(pmd)
        crudo = [subprocess.run(["pdftotext", "-layout", "-f", str(p), "-l", str(p), str(pdf), "-"],
                                capture_output=True, text=True).stdout for p in orden]
        cuerpo, repetidas = sin_repetidas(crudo)
        cif_ref_t = [Counter(), Counter(), Counter()]; cif_obs_t = [Counter(), Counter(), Counter()]
        for p, txt_c, txt in zip(orden, crudo, cuerpo):
            ref, obs = palabras(txt), palabras(pmd[p])
            cob, total, falta = cobertura(ref, obs)
            ref_doc.update(ref); obs_doc.update(obs)
            for k, (a, b) in enumerate(zip(cifras(txt), cifras(pmd[p]))):
                cif_ref[k].update(a); cif_obs[k].update(b)
            for k, (a, b) in enumerate(zip(cifras(txt_c), cifras(pmd[p]))):
                cif_ref_t[k].update(a); cif_obs_t[k].update(b)
            filas.append(dict(id=f.stem, pagina=p, palabras_pdf=total, cobertura=round(cob, 3),
                              bajo_umbral="si" if cob < umbral else "",
                              faltantes_ejemplo=" ".join(w for w, _ in falta.most_common(8))))
        cob, total, _ = cobertura(ref_doc, obs_doc)
        cn_t, _, _ = cobertura(cif_ref_t[0], cif_obs_t[0])
        cn, tn, fn = cobertura(cif_ref[0], cif_obs[0])
        cc, tc, fc = cobertura(cif_ref[1], cif_obs[1])
        cu, tu, fu = cobertura(cif_ref[2], cif_obs[2])
        docs.append(dict(id=f.stem, paginas=len(pmd), palabras_pdf=total, cobertura_doc_cuerpo=round(cob, 3),
                         paginas_bajo_umbral=sum(1 for r in filas if r["id"] == f.stem and r["bajo_umbral"]),
                         numeros_pdf=tn, cobertura_numeros=round(cn, 3), cobertura_numeros_con_encabezados=round(cn_t, 3),
                         lineas_encabezado_quitadas=len(repetidas),
                         cas_pdf=tc, cobertura_cas=round(cc, 3), cas_faltantes=" ".join(list(fc)[:6]),
                         unidades_pdf=tu, cobertura_unidades=round(cu, 3)))
    for nombre, datos in (("_verificacion_paginas.csv", filas), ("_verificacion_docs.csv", docs)):
        with open(MD_DIR / nombre, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(datos[0])); w.writeheader(); w.writerows(datos)
    print(f"{len(docs)} documentos, {len(filas)} paginas; paginas < {umbral}: {sum(1 for r in filas if r['bajo_umbral'])}")


if __name__ == "__main__":
    main()
