"""Validación del Optimizador de CV (Hito 3).

Uso (desde la raíz del proyecto):
    .venv/bin/python evaluacion/evaluacion.py           # ranking, habilidades y tiempos (sin internet ni API key)
    .venv/bin/python evaluacion/evaluacion.py --llm     # además: CV reestructurado y búsqueda web (requiere clave)

Resultados: evaluacion/resultados.json y una tabla en consola.
"""
import argparse
import json
import math
import random
import re
import sys
import time
from pathlib import Path

import numpy as np

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
import matching  # noqa: E402

AQUI = Path(__file__).resolve().parent
K = 3


def cargar_env():
    """Lee las claves guardadas por la app (botón "Recordar clave en este equipo")."""
    import os
    archivo = RAIZ / ".env"
    if archivo.exists():
        for linea in archivo.read_text(encoding="utf-8").splitlines():
            if "=" in linea and not linea.lstrip().startswith("#"):
                k, v = linea.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


# ---------- métricas de ranking ----------
def precision_at_k(orden, rel, k=K, umbral=1):
    return sum(rel.get(v, 0) >= umbral for v in orden[:k]) / k


def ndcg_at_k(orden, rel, k=5):
    dcg = sum((2 ** rel.get(v, 0) - 1) / math.log2(i + 2) for i, v in enumerate(orden[:k]))
    ideal = sorted(rel.values(), reverse=True)[:k]
    idcg = sum((2 ** g - 1) / math.log2(i + 2) for i, g in enumerate(ideal))
    return dcg / idcg if idcg else 0.0


def mrr(orden, rel):
    for i, v in enumerate(orden):
        if rel.get(v, 0) == 2:
            return 1 / (i + 1)
    return 0.0


def topk_acc(orden, rel, k=K):
    """La métrica objetivo del proyecto (matching.top_k_accuracy): vacantes muy afines dentro del top-k."""
    afines = {v for v, g in rel.items() if g == 2}
    return matching.top_k_accuracy(orden, afines, k)


METRICAS = {"top3_acc": topk_acc, "p@3": precision_at_k, "ndcg@5": ndcg_at_k, "mrr": mrr}


# ---------- métodos a comparar ----------
def texto_vacante(v):
    return f"{v['titulo']}. {v['descripcion']}"


def orden_embeddings(cv, vacantes, modelo):
    ranking = matching.rank_vacancies(cv, vacantes, modelo)
    return [r["id"] for r in ranking]


def orden_jaccard(cv, vacantes, _=None):
    s_cv = matching.extract_skills(cv)
    def jac(v):
        s_v = matching.extract_skills(texto_vacante(v))
        return len(s_cv & s_v) / len(s_cv | s_v) if s_cv | s_v else 0.0
    return [v["id"] for v in sorted(vacantes, key=jac, reverse=True)]


def orden_tfidf(cv, vacantes, _=None):
    from sklearn.feature_extraction.text import TfidfVectorizer
    textos = [matching._norm(cv)] + [matching._norm(texto_vacante(v)) for v in vacantes]
    m = TfidfVectorizer().fit_transform(textos)
    sims = (m[1:] @ m[0].T).toarray().ravel()
    return [vacantes[i]["id"] for i in np.argsort(-sims, kind="stable")]


def evaluar_aleatorio(cvs, vacantes, repeticiones=2000):
    rng = random.Random(42)
    ids = [v["id"] for v in vacantes]
    acum = {m: 0.0 for m in METRICAS}
    for _ in range(repeticiones):
        for c in cvs:
            orden = ids[:]
            rng.shuffle(orden)
            for m, f in METRICAS.items():
                acum[m] += f(orden, c["relevancia"])
    return {m: acum[m] / (repeticiones * len(cvs)) for m in METRICAS}


# ---------- extracción de habilidades ----------
def evaluar_habilidades(cvs):
    tp = fp = fn = 0
    detalle = []
    for c in cvs:
        pred, oro = matching.extract_skills(c["texto"]), set(c["habilidades"])
        tp += len(pred & oro)
        fp += len(pred - oro)
        fn += len(oro - pred)
        detalle.append({"cv": c["id"], "faltaron": sorted(oro - pred), "sobraron": sorted(pred - oro)})
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    return {"precision": p, "recall": r, "f1": 2 * p * r / (p + r) if p + r else 0.0,
            "tp": tp, "fp": fp, "fn": fn, "detalle": detalle}


# ---------- pruebas con LLM (opcionales) ----------
def sin_notas(texto):
    """Quita las "Notas para ti" del final (van después del último `---` previo a ese título)."""
    i = texto.lower().rfind("notas para ti")
    if i < 0:
        return texto
    corte = texto.rfind("\n---", 0, i)
    return texto[:corte] if corte >= 0 else texto[:i]


def evaluar_llm(cvs, vacantes, modelo, proveedor, reusar=False):
    import llm_helper
    carpeta = AQUI / "salidas_llm"
    carpeta.mkdir(exist_ok=True)
    filas = []
    for c in cvs:
        mejor = matching.rank_vacancies(c["texto"], vacantes, modelo)[0]
        archivo = carpeta / f"{c['id']}.md"
        seg = None
        if reusar and archivo.exists():
            nuevo = archivo.read_text(encoding="utf-8")
        else:
            t0 = time.perf_counter()
            nuevo = llm_helper.reestructurar_cv(c["texto"], mejor, proveedor=proveedor)
            seg = time.perf_counter() - t0
            archivo.write_text(nuevo, encoding="utf-8")
        cuerpo = sin_notas(nuevo)
        # Los espacios por completar ("[Inglés: nivel]") no afirman nada: se excluyen.
        afirmado = re.sub(r"\[[^\]]*\]", " ", cuerpo)
        nuevas = matching.extract_skills(afirmado) - matching.extract_skills(c["texto"])
        despues = matching.rank_vacancies(cuerpo, [mejor], modelo)[0]["score"]
        pedidas = set(mejor["habilidades_vacante"])
        filas.append({"cv": c["id"], "vacante": mejor["titulo"], "afinidad_antes": mejor["score"],
                      "afinidad_despues": despues, "habilidades_nuevas": sorted(nuevas),
                      "pedidas_por_vacante": len(pedidas),
                      "cubiertas_antes": len(pedidas & matching.extract_skills(c["texto"])),
                      "cubiertas_despues": len(pedidas & matching.extract_skills(afirmado)),
                      "segundos": seg})
    return filas


def evaluar_busqueda(cvs, proveedor, pausa=8):
    import urllib.error
    import urllib.parse
    import urllib.request
    import busqueda_web
    filas = []
    for c in cvs:
        time.sleep(pausa)  # el buscador gratuito limita las peticiones seguidas
        t0 = time.perf_counter()
        try:
            res = busqueda_web.buscar_vacantes(c["texto"], "Colombia", 6, proveedor=proveedor)
        except Exception as e:  # sin resultados o buscador caído: se registra como 0
            res = {"vacantes": [], "error": str(e)}
        seg = time.perf_counter() - t0
        vs = res["vacantes"]
        codigos = []
        for v in vs:
            url = urllib.parse.quote(v["url"], safe=":/?&=%#")
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                codigos.append(urllib.request.urlopen(req, timeout=10).status)
            except urllib.error.HTTPError as e:
                codigos.append(e.code)
            except Exception:
                codigos.append(None)
        filas.append({"cv": c["id"], "vacantes": len(vs),
                      "verificadas": sum(bool(v.get("verificada")) for v in vs),
                      "http_200": codigos.count(200),
                      "http_403_bloqueo_bots": codigos.count(403),
                      "http_404": codigos.count(404),
                      "codigos": codigos, "portales": [v.get("portal") for v in vs],
                      "segundos": seg})
    return filas


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--llm", action="store_true", help="incluye pruebas que llaman a la API")
    ap.add_argument("--reusar", action="store_true",
                    help="con --llm: usa los CV ya generados en salidas_llm/ y no repite la búsqueda web")
    ap.add_argument("--proveedor", default="gemini", choices=["gemini", "claude"])
    args = ap.parse_args()
    cargar_env()

    datos = json.loads((AQUI / "dataset_eval.json").read_text(encoding="utf-8"))
    cvs, vacantes = datos["cvs"], datos["vacantes"]

    t0 = time.perf_counter()
    modelo = matching.get_model()
    carga = time.perf_counter() - t0
    orden_embeddings(cvs[0]["texto"], vacantes, modelo)  # calentamiento

    resultados = {"n_cvs": len(cvs), "n_vacantes": len(vacantes), "k": K, "metodos": {}, "por_cv": []}
    tiempos = []
    for nombre, f in [("embeddings (MVP)", orden_embeddings), ("tf-idf", orden_tfidf),
                      ("jaccard habilidades", orden_jaccard)]:
        suma = {m: 0.0 for m in METRICAS}
        for c in cvs:
            t = time.perf_counter()
            orden = f(c["texto"], vacantes, modelo)
            if nombre.startswith("embeddings"):
                tiempos.append(time.perf_counter() - t)
            vals = {m: g(orden, c["relevancia"]) for m, g in METRICAS.items()}
            for m in METRICAS:
                suma[m] += vals[m]
            if nombre.startswith("embeddings"):
                titulos = {v["id"]: v["titulo"] for v in vacantes}
                resultados["por_cv"].append({"cv": c["id"], "perfil": c["perfil"], **vals,
                                             "top3": [titulos[i] for i in orden[:3]]})
        resultados["metodos"][nombre] = {m: suma[m] / len(cvs) for m in METRICAS}
    resultados["metodos"]["aleatorio"] = evaluar_aleatorio(cvs, vacantes)

    # Robustez: los mismos CV escritos en inglés contra vacantes en español.
    resultados["cv_en_ingles"] = {}
    for nombre, f in [("embeddings (MVP)", orden_embeddings), ("tf-idf", orden_tfidf),
                      ("jaccard habilidades", orden_jaccard)]:
        suma = {m: 0.0 for m in METRICAS}
        for c in cvs:
            orden = f(c["texto_en"], vacantes, modelo)
            for m, g in METRICAS.items():
                suma[m] += g(orden, c["relevancia"])
        resultados["cv_en_ingles"][nombre] = {m: suma[m] / len(cvs) for m in METRICAS}
    resultados["habilidades"] = evaluar_habilidades(cvs)
    resultados["tiempos"] = {"carga_modelo_s": carga,
                             "ranking_20_vacantes_ms": 1000 * float(np.mean(tiempos))}

    if args.llm:
        previos = {}
        if args.reusar and (AQUI / "resultados.json").exists():
            previos = json.loads((AQUI / "resultados.json").read_text(encoding="utf-8"))
        anteriores = {f["cv"]: f["segundos"] for f in previos.get("reestructuracion", [])}
        resultados["reestructuracion"] = evaluar_llm(cvs, vacantes, modelo, args.proveedor, args.reusar)
        for f in resultados["reestructuracion"]:
            if f["segundos"] is None:
                f["segundos"] = anteriores.get(f["cv"])
        if args.reusar and "busqueda_web" in previos:
            resultados["busqueda_web"] = previos["busqueda_web"]
        else:
            resultados["busqueda_web"] = evaluar_busqueda(cvs, args.proveedor)

    (AQUI / "resultados.json").write_text(json.dumps(resultados, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n{len(cvs)} CV x {len(vacantes)} vacantes\n")
    print(f"{'Método':<22}" + "".join(f"{m:>10}" for m in METRICAS))
    for nombre, vals in resultados["metodos"].items():
        print(f"{nombre:<22}" + "".join(f"{vals[m]:>10.3f}" for m in METRICAS))
    print("\nCV en inglés vs vacantes en español:")
    for nombre, vals in resultados["cv_en_ingles"].items():
        print(f"{nombre:<22}" + "".join(f"{vals[m]:>10.3f}" for m in METRICAS))
    print("\nPor CV (embeddings):")
    for f in resultados["por_cv"]:
        print(f"  {f['cv']:<14} top3_acc={f['top3_acc']:.2f} ndcg@5={f['ndcg@5']:.2f}  top3={f['top3']}")
    h = resultados["habilidades"]
    print(f"\nHabilidades: P={h['precision']:.2f} R={h['recall']:.2f} F1={h['f1']:.2f}")
    for d in h["detalle"]:
        print(f"  {d['cv']:<14} faltaron={d['faltaron']} sobraron={d['sobraron']}")
    print(f"\nTiempos: carga modelo {carga:.1f} s, ranking {resultados['tiempos']['ranking_20_vacantes_ms']:.0f} ms")
    for clave in ("reestructuracion", "busqueda_web"):
        if clave in resultados:
            print(f"\n{clave}:")
            for f in resultados[clave]:
                print("  ", f)


if __name__ == "__main__":
    main()
