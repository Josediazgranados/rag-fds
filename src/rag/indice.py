"""
Indice vectorial de las FDS y recuperacion top-k con metadatos de trazabilidad.

Decisiones (para el informe):
  - Embeddings: intfloat/multilingual-e5-small (multilingue, ~118 M parametros; e5-base se descarto: ~50 min en 2 vCPU).
    Se usa el convenio del modelo: prefijo "passage: " en documentos y "query: " en preguntas.
    Se embebe 'texto_indexado' (cuerpo + encabezado contextual fabricante/producto/seccion).
  - Almacen: ChromaDB persistente, distancia coseno, vectores normalizados.
  - Recuperacion HIBRIDA: denso (coseno) + lexica BM25 sobre el mismo texto indexado, fusionadas con
    Reciprocal Rank Fusion (RRF, c=60). Motivo (medido con las preguntas de desarrollo): con e5-small el nombre del
    producto, repetido en el encabezado de todos sus fragmentos, hacia que el recuperador acertara el documento pero
    no la seccion; BM25 aporta las palabras discriminantes (ej. "inflamacion", "ONU", "CAS").
  - top-k configurable en cada consulta (la evaluacion compara k=3 y k=6; es lo UNICO que cambia).

Uso:
  python indice.py construir                      # lee data/chunks.jsonl y crea data/indice/
  python indice.py buscar "pregunta" -k 3 [--fabricante Sika] [--seccion 9]
"""
import argparse, json, sys, time
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
CHUNKS = RAIZ / "data" / "chunks.jsonl"
RUTA_INDICE = RAIZ / "data" / "indice"
COLECCION = "fds"
MODELO = "intfloat/multilingual-e5-small"
_modelo = None


def cargar_modelo():
    """Carga (una sola vez) el modelo de embeddings en CPU.
    param : ninguno
    return: SentenceTransformer
    """
    global _modelo
    if _modelo is None:
        import os, torch
        torch.set_num_threads(os.cpu_count() or 1)      # el entorno dejaba torch en 1 hilo (mitad de la CPU)
        from sentence_transformers import SentenceTransformer
        _modelo = SentenceTransformer(MODELO, device="cpu")
        _modelo.max_seq_length = 512
    return _modelo


def embeber(textos, prefijo, lote=16):
    """Calcula embeddings normalizados de una lista de textos.
    param : textos : list[str]; prefijo : 'passage: ' o 'query: '; lote : int
    return: ndarray (n, dim)
    """
    return cargar_modelo().encode([prefijo + t for t in textos], batch_size=lote,
                                  normalize_embeddings=True, show_progress_bar=len(textos) > 50)


def coleccion(crear=False):
    """Abre la coleccion Chroma (la recrea si crear=True).
    param : crear : bool
    return: coleccion de chromadb
    """
    import chromadb
    cli = chromadb.PersistentClient(path=str(RUTA_INDICE))
    if crear:
        try:
            cli.delete_collection(COLECCION)
        except Exception:
            pass
        return cli.create_collection(COLECCION, metadata={"hnsw:space": "cosine", "modelo": MODELO})
    return cli.get_collection(COLECCION)


def construir():
    """Embebe todos los fragmentos de chunks.jsonl y los guarda en Chroma.
    param : ninguno
    return: None
    """
    import numpy as np
    chunks = [json.loads(l) for l in open(CHUNKS, encoding="utf-8")]
    t0 = time.time()
    # Puntos de control: cada TAM fragmentos se guarda en disco, asi un corte de sesion no pierde el avance
    TAM = 200
    cache = RUTA_INDICE / "_embeddings"
    cache.mkdir(parents=True, exist_ok=True)
    partes = []
    for i in range(0, len(chunks), TAM):
        f = cache / f"{MODELO.split('/')[-1]}_{i:05d}_{len(chunks)}.npy"
        if not f.exists():
            np.save(f, embeber([c["texto_indexado"] for c in chunks[i:i + TAM]], "passage: "))
            print(f"  {min(i + TAM, len(chunks))}/{len(chunks)} fragmentos ({time.time() - t0:.0f} s)", flush=True)
        partes.append(np.load(f))
    emb = np.vstack(partes)
    col = coleccion(crear=True)
    for i in range(0, len(chunks), 500):
        lote = chunks[i:i + 500]
        col.add(ids=[c["chunk_id"] for c in lote], embeddings=emb[i:i + 500].tolist(),
                documents=[c["texto"] for c in lote],
                metadatas=[dict(doc_id=c["doc_id"], documento=c["documento"], fabricante=c["fabricante"],
                                producto=c["producto"], version=c["version"], fecha=c["fecha"],
                                seccion=c["seccion"], seccion_nombre=c["seccion_nombre"],
                                pagina_inicio=c["pagina_inicio"], pagina_fin=c["pagina_fin"],
                                imagenes="|".join(c["imagenes"])) for c in lote])
    print(f"{len(chunks)} fragmentos indexados en {time.time() - t0:.0f} s ({MODELO}) -> {RUTA_INDICE}")


def _tokens(texto):
    """Tokens para BM25: minusculas, sin tildes, solo [a-z0-9] de 2 o mas caracteres.
    param : texto : str
    return: list[str]
    """
    import re, unicodedata
    t = "".join(c for c in unicodedata.normalize("NFD", texto.lower()) if unicodedata.category(c) != "Mn")
    return [w for w in re.findall(r"[a-z0-9]+", t) if len(w) > 1]


class BM25:
    """BM25 (k1=1.5, b=0.75) sobre los fragmentos, implementado con numpy (sin dependencias extra)."""

    def __init__(self, textos):
        """Construye el indice invertido.
        param : textos : list[str] texto de cada fragmento
        """
        import numpy as np
        from collections import Counter, defaultdict
        self.np, self.n = np, len(textos)
        tfs = [Counter(_tokens(t)) for t in textos]
        self.dl = np.array([sum(c.values()) for c in tfs], dtype=float)
        self.avg = self.dl.mean()
        self.post = defaultdict(list)
        for i, c in enumerate(tfs):
            for w, f in c.items():
                self.post[w].append((i, f))

    def puntuar(self, consulta):
        """Puntaje BM25 de todos los fragmentos para una consulta.
        param : consulta : str
        return: ndarray (n,)
        """
        import math
        np, s = self.np, self.np.zeros(self.n)
        for w in set(_tokens(consulta)):
            lista = self.post.get(w)
            if not lista:
                continue
            idf = math.log(1 + (self.n - len(lista) + 0.5) / (len(lista) + 0.5))
            for i, f in lista:
                s[i] += idf * f * 2.5 / (f + 1.5 * (0.25 + 0.75 * self.dl[i] / self.avg))
        return s


_bm25 = None
_chunks = None
_pos = None


def _cargar_lexico():
    """Carga (una vez) los fragmentos y su indice BM25.
    param : ninguno
    return: tupla (list[dict] chunks, BM25)
    """
    global _bm25, _chunks
    if _bm25 is None:
        _chunks = [json.loads(l) for l in open(CHUNKS, encoding="utf-8")]
        _bm25 = BM25([c["texto_indexado"] for c in _chunks])
    return _chunks, _bm25


_doc_idx = None
_bm25_cuerpo = None


def _indice_docs():
    """Carga (una vez) el BM25 a nivel de documento (fabricante + producto + nombre de archivo) y el de cuerpo.
    param : ninguno
    return: tupla (list[str] doc_ids, BM25 de documentos, BM25 de cuerpo de fragmentos)
    """
    global _doc_idx, _bm25_cuerpo
    chunks, _ = _cargar_lexico()
    if _doc_idx is None:
        cat = {}
        for c in chunks:
            cat.setdefault(c["doc_id"], f"{c['fabricante']} {c['producto']} {c['documento']}")
        ids = list(cat)
        _doc_idx = (ids, BM25([cat[i] for i in ids]), cat)
        _bm25_cuerpo = BM25([c["texto"] for c in chunks])
    return _doc_idx[0], _doc_idx[1], _bm25_cuerpo, _doc_idx[2]


def consulta_tema(pregunta, cand, cat):
    """Quita de la pregunta las palabras que ya identifican a los documentos candidatos (fabricante, producto,
    codigo), para que la etapa 2 ordene los fragmentos por TEMA y no por el nombre del producto.
    param : pregunta : str; cand : list[str] doc_id candidatos; cat : dict doc_id -> texto de identificacion
    return: str consulta de tema (la pregunta completa si no queda nada)
    """
    vocab = set()
    for d in cand:
        vocab |= set(_tokens(cat[d]))
    resto = " ".join(w for w in pregunta.split() if not all(t in vocab for t in _tokens(w)))
    return resto if len(_tokens(resto)) >= 2 else pregunta


def buscar(pregunta, k=3, fabricante=None, seccion=None, modo="hibrido", candidatos=40, max_docs=3, rel_doc=0.6):
    """Recupera los k mejores fragmentos.
    modo 'hibrido' (por defecto, DOS ETAPAS): (1) elige hasta max_docs documentos candidatos por coincidencia
    de la pregunta con fabricante/producto/nombre de archivo (BM25 de documento; se aceptan los que alcanzan
    rel_doc x el mejor); (2) dentro de ellos ordena los fragmentos por tema (denso + BM25 de cuerpo, RRF) y
    garantiza que cada documento candidato aporte su mejor fragmento antes de repetir documento.
    modo 'plano': RRF de denso + BM25 sobre todo el indice. modo 'denso': solo embeddings.
    param : pregunta : str; k : int; fabricante, seccion : filtros opcionales; candidatos : int por ranking
    return: list[dict] con texto, metadatos y 'puntaje' (RRF; coseno en modo denso)
    """
    if modo == "denso":
        return buscar_denso(pregunta, k, fabricante, seccion)
    if modo == "plano":
        return buscar_plano(pregunta, k, fabricante, seccion, candidatos)
    chunks, _ = _cargar_lexico()
    ids, bm_doc, bm_cuerpo, cat = _indice_docs()
    sd = bm_doc.puntuar(pregunta)
    orden = [i for i in sd.argsort()[::-1][:max_docs] if sd[i] > 0 and sd[i] >= rel_doc * sd.max()]
    cand = [ids[i] for i in orden]
    if not cand:                                   # sin pista de producto: busqueda plana sobre todo el corpus
        return buscar_plano(pregunta, k, fabricante, seccion, candidatos)
    permitido = [c["doc_id"] in cand and (not fabricante or c["fabricante"] == fabricante)
                 and (not seccion or c["seccion"] == int(seccion)) for c in chunks]
    tema = consulta_tema(pregunta, cand, cat)
    sb = bm_cuerpo.puntuar(tema)
    rank_bm = [i for i in sb.argsort()[::-1][:len(chunks)] if permitido[i] and sb[i] > 0][:candidatos]
    rank_dn = [chunks_ix(r["chunk_id"]) for r in buscar_denso(tema, candidatos, fabricante, seccion, docs=cand)]
    rrf = {}
    for ranking in (rank_dn, rank_bm):
        for pos, i in enumerate(ranking, 1):
            rrf[i] = rrf.get(i, 0) + 1 / (60 + pos)
    ordenados = sorted(rrf, key=rrf.get, reverse=True)
    primeros = []                                  # mejor fragmento de cada documento candidato (orden de relevancia del documento)
    for d in cand:
        mejor = next((i for i in ordenados if chunks[i]["doc_id"] == d), None)
        if mejor is not None:
            primeros.append(mejor)
    primeros.sort(key=lambda i: -rrf[i])
    final = (primeros + [i for i in ordenados if i not in primeros])[:k]
    out = []
    for i in final:
        c = chunks[i]
        out.append(dict(chunk_id=c["chunk_id"], texto=c["texto"], puntaje=round(rrf[i], 5),
                        doc_id=c["doc_id"], documento=c["documento"], fabricante=c["fabricante"], producto=c["producto"],
                        version=c["version"], fecha=c["fecha"], seccion=c["seccion"], seccion_nombre=c["seccion_nombre"],
                        pagina_inicio=c["pagina_inicio"], pagina_fin=c["pagina_fin"], imagenes="|".join(c["imagenes"]),
                        docs_candidatos=",".join(cand)))
    return out


def buscar_plano(pregunta, k=3, fabricante=None, seccion=None, candidatos=40):
    """Hibrido plano (una etapa): RRF de denso + BM25 sobre todo el indice (se conserva para ablacion).
    param : pregunta : str; k : int; fabricante, seccion : filtros; candidatos : int
    return: list[dict]
    """
    chunks, bm = _cargar_lexico()
    permitido = [(not fabricante or c["fabricante"] == fabricante) and (not seccion or c["seccion"] == int(seccion))
                 for c in chunks]
    sb = bm.puntuar(pregunta)
    rank_bm = [i for i in sb.argsort()[::-1][:candidatos * 3] if permitido[i] and sb[i] > 0][:candidatos]
    rank_dn = [chunks_ix(r["chunk_id"]) for r in buscar_denso(pregunta, candidatos, fabricante, seccion)]
    rrf = {}
    for ranking in (rank_dn, rank_bm):
        for pos, i in enumerate(ranking, 1):
            rrf[i] = rrf.get(i, 0) + 1 / (60 + pos)
    out = []
    for i in sorted(rrf, key=rrf.get, reverse=True)[:k]:
        c = chunks[i]
        out.append(dict(chunk_id=c["chunk_id"], texto=c["texto"], puntaje=round(rrf[i], 5),
                        doc_id=c["doc_id"], documento=c["documento"], fabricante=c["fabricante"], producto=c["producto"],
                        version=c["version"], fecha=c["fecha"], seccion=c["seccion"], seccion_nombre=c["seccion_nombre"],
                        pagina_inicio=c["pagina_inicio"], pagina_fin=c["pagina_fin"], imagenes="|".join(c["imagenes"]),
                        en_denso=i in rank_dn, en_bm25=i in rank_bm))
    return out


def chunks_ix(chunk_id):
    """Posicion de un chunk_id en la lista de fragmentos (indice para el RRF).
    param : chunk_id : str
    return: int
    """
    global _pos
    if _pos is None:
        _pos = {c["chunk_id"]: i for i, c in enumerate(_cargar_lexico()[0])}
    return _pos[chunk_id]


def buscar_denso(pregunta, k=3, fabricante=None, seccion=None, docs=None):
    """Recupera los k fragmentos mas cercanos por embeddings (coseno).
    param : pregunta : str; k : int; fabricante : str o None (filtro exacto); seccion : int o None;
            docs : list[str] doc_id permitidos o None
    return: list[dict] con texto, metadatos y 'puntaje' (similitud coseno, 1 = identico), por orden
    """
    filtros = []
    if fabricante: filtros.append({"fabricante": fabricante})
    if seccion: filtros.append({"seccion": int(seccion)})
    if docs: filtros.append({"doc_id": {"$in": list(docs)}})
    where = None if not filtros else (filtros[0] if len(filtros) == 1 else {"$and": filtros})
    q = embeber([pregunta], "query: ")[0].tolist()
    r = coleccion().query(query_embeddings=[q], n_results=k, where=where)
    out = []
    for i in range(len(r["ids"][0])):
        m = r["metadatas"][0][i]
        out.append(dict(chunk_id=r["ids"][0][i], texto=r["documents"][0][i],
                        puntaje=round(1 - r["distances"][0][i], 4), **m))
    return out


def main():
    """Interfaz de linea de comandos: construir | buscar.
    param : argumentos de linea de comandos
    return: None
    """
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("construir")
    b = sub.add_parser("buscar")
    b.add_argument("pregunta"); b.add_argument("-k", type=int, default=3)
    b.add_argument("--fabricante"); b.add_argument("--seccion", type=int)
    a = ap.parse_args()
    if a.cmd == "construir":
        construir()
    else:
        for r in buscar(a.pregunta, a.k, a.fabricante, a.seccion):
            print(f"[{r['puntaje']}] {r['fabricante']} | {r['producto']} | {r['documento']} | p.{r['pagina_inicio']}-{r['pagina_fin']} | sec {r['seccion']} {r['seccion_nombre']}")
            print("    " + r["texto"][:220].replace("\n", " "))


if __name__ == "__main__":
    sys.exit(main())
