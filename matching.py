"""Módulo de emparejamiento semántico CV-vacante (componente principal).

Flujo: embeddings normalizados -> similitud coseno -> brechas de habilidades -> ranking.
"""
import re
import unicodedata
from functools import lru_cache

import numpy as np

MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"

# Vocabulario controlado de habilidades (técnicas y blandas). Ampliable.
SKILLS = [
    "python", "java", "javascript", "typescript", "sql", "nosql", "mongodb", "postgresql",
    "mysql", "react", "node", "django", "flask", "fastapi", "spring", "docker", "kubernetes",
    "aws", "azure", "gcp", "git", "linux", "ci/cd", "devops", "api rest", "microservicios",
    "machine learning", "deep learning", "nlp", "pandas", "numpy", "scikit-learn",
    "tensorflow", "pytorch", "power bi", "tableau", "excel", "estadistica",
    "analisis de datos", "ingenieria de datos", "etl", "spark", "airflow", "scrum", "agile",
    "pruebas unitarias", "testing", "ingles", "comunicacion", "trabajo en equipo",
    "liderazgo", "resolucion de problemas", "gestion de proyectos", "pensamiento critico",
]

# Sinónimos / variantes -> término canónico (ES/EN)
ALIASES = {
    "data analytics": "analisis de datos", "analitica de datos": "analisis de datos",
    "aprendizaje automatico": "machine learning", "aprendizaje de maquina": "machine learning",
    "restful": "api rest", "rest api": "api rest", "apis rest": "api rest",
    "teamwork": "trabajo en equipo", "english": "ingles", "leadership": "liderazgo",
    "problem solving": "resolucion de problemas", "project management": "gestion de proyectos",
    "unit testing": "pruebas unitarias", "data engineering": "ingenieria de datos",
    "metodologias agiles": "agile", "nodejs": "node", "node.js": "node", "postgres": "postgresql",
}


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in text if not unicodedata.combining(c))


def _contains(text_norm: str, term: str) -> bool:
    return re.search(r"(?<![a-z0-9])" + re.escape(term) + r"(?![a-z0-9])", text_norm) is not None


def extract_skills(text: str) -> set:
    t = _norm(text)
    found = {s for s in SKILLS if _contains(t, s)}
    for alias, canon in ALIASES.items():
        if _contains(t, alias):
            found.add(canon)
    return found


@lru_cache(maxsize=1)
def get_model():
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(MODEL_NAME)


def embed(texts, model=None):
    model = model or get_model()
    return model.encode(list(texts), normalize_embeddings=True, convert_to_numpy=True)


def rank_vacancies(cv_text: str, vacancies: list, model=None) -> list:
    """vacancies: lista de dicts {titulo, descripcion}. Retorna lista ordenada desc por score."""
    if not cv_text.strip() or not vacancies:
        return []
    texts = [cv_text] + [f"{v['titulo']}. {v['descripcion']}" for v in vacancies]
    vecs = embed(texts, model)
    # vectores normalizados -> producto punto = similitud coseno
    sims = vecs[1:] @ vecs[0]
    cv_skills = extract_skills(cv_text)
    results = []
    for v, s in zip(vacancies, sims):
        job_skills = extract_skills(f"{v['titulo']} {v['descripcion']}")
        results.append({
            **v,  # conserva campos extra (empresa, url, verificada...) de vacantes reales
            "score": float(np.clip(s, 0.0, 1.0)),
            "habilidades_vacante": sorted(job_skills),
            "habilidades_cubiertas": sorted(job_skills & cv_skills),
            "brechas": sorted(job_skills - cv_skills),
        })
    return sorted(results, key=lambda r: r["score"], reverse=True)


def top_k_accuracy(ranking_titles: list, afines: set, k: int = 3) -> float:
    """Fracción de vacantes afines que quedan en el top-k (objetivo cuantitativo: >= 0.8)."""
    if not afines:
        return 0.0
    return len(set(ranking_titles[:k]) & afines) / len(afines)
