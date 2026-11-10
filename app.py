"""Interfaz Streamlit: CV -> búsqueda real de vacantes en internet -> ranking -> brechas -> CV reestructurado."""
import json
import os
from pathlib import Path

import pandas as pd
import streamlit as st

import busqueda_web
import llm_helper
import matching

BASE = Path(__file__).parent
st.set_page_config(page_title="Optimizador de CV con IA", page_icon="📄", layout="wide")
st.title("📄 Recomendación y optimización de hojas de vida con IA")
st.caption("Proyecto PTIA · Escuela Colombiana de Ingeniería Julio Garavito")


@st.cache_resource(show_spinner="Cargando modelo de embeddings...")
def load_model():
    return matching.get_model()


def _leer_docx(archivo) -> str:
    from docx import Document
    doc = Document(archivo)
    partes = [p.text for p in doc.paragraphs]
    # Muchas hojas de vida usan tablas para organizar secciones
    for tabla in doc.tables:
        for fila in tabla.rows:
            celdas = []
            for c in fila.cells:
                if c.text.strip() and c.text not in celdas:  # evita duplicar celdas combinadas
                    celdas.append(c.text.strip())
            partes.append(" | ".join(celdas))
    return "\n".join(p for p in partes if p.strip())


def _leer_doc(datos: bytes) -> str:
    """Word 97-2003 (.doc): se convierte con la herramienta disponible en el sistema."""
    import shutil
    import subprocess
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        origen = Path(tmp) / "cv.doc"
        origen.write_bytes(datos)
        if shutil.which("textutil"):  # macOS
            subprocess.run(["textutil", "-convert", "txt", str(origen)], check=True, capture_output=True)
        elif shutil.which("soffice") or shutil.which("libreoffice"):
            exe = shutil.which("soffice") or shutil.which("libreoffice")
            subprocess.run([exe, "--headless", "--convert-to", "txt:Text", "--outdir", tmp, str(origen)],
                           check=True, capture_output=True, timeout=120)
        elif shutil.which("antiword"):
            return subprocess.run(["antiword", str(origen)], check=True, capture_output=True,
                                  text=True).stdout
        else:
            raise RuntimeError("Para leer .doc instala LibreOffice o guarda el archivo como .docx o PDF.")
        return (Path(tmp) / "cv.txt").read_text(encoding="utf-8", errors="ignore")


def leer_cv(archivo) -> str:
    nombre = archivo.name.lower()
    if nombre.endswith(".pdf"):
        from pypdf import PdfReader
        return "\n".join(p.extract_text() or "" for p in PdfReader(archivo).pages)
    if nombre.endswith(".docx"):
        return _leer_docx(archivo)
    if nombre.endswith(".doc"):
        return _leer_doc(archivo.read())
    return archivo.read().decode("utf-8", errors="ignore")


with st.sidebar:
    st.header("Configuración")
    api_key = st.text_input("API key de Anthropic", type="password",
                            help="O define la variable ANTHROPIC_API_KEY") or None
    tiene_key = bool(api_key or os.getenv("ANTHROPIC_API_KEY"))
    if not tiene_key:
        st.warning("Falta la API key. Créala en console.anthropic.com → API Keys y pégala aquí.")
    fuente = st.radio("Fuente de vacantes", ["Buscar en internet", "Archivo JSON (demo)"])
    if fuente == "Buscar en internet":
        ubicacion = st.text_input("Ubicación", "Colombia")
        cantidad = st.slider("Vacantes a buscar", 3, 15, 8)

# ---------- 1. CV ----------
st.subheader("1. Tu hoja de vida")
archivo_cv = st.file_uploader("Sube tu CV (PDF, Word o TXT) o pégalo abajo",
                              type=["pdf", "docx", "doc", "txt"])
cv_inicial = (BASE / "cv_ejemplo.txt").read_text(encoding="utf-8")
if archivo_cv:
    try:
        cv_inicial = leer_cv(archivo_cv)
        if not cv_inicial.strip():
            st.warning("No se encontró texto en el archivo (¿es un escaneo?). Pega el CV abajo.")
    except Exception as e:
        st.error(f"No se pudo leer el archivo: {e}")
cv_text = st.text_area("Texto del CV", value=cv_inicial, height=220)

# ---------- 2. Vacantes ----------
st.subheader("2. Vacantes")
if fuente == "Buscar en internet":
    if st.button("🔎 Buscar vacantes reales en internet", type="primary", disabled=not tiene_key):
        try:
            with st.spinner("Claude está buscando ofertas en la web (puede tardar 1-2 min)..."):
                res = busqueda_web.buscar_vacantes(cv_text, ubicacion, cantidad, api_key)
            st.session_state["vacantes"] = res["vacantes"]
            st.session_state["perfil"] = res["perfil_detectado"]
            st.session_state["consultas"] = res["consultas"]
            for k in ("ranking", "cv_nuevo", "elegida"):
                st.session_state.pop(k, None)
        except Exception as e:
            st.error(f"No se pudo completar la búsqueda: {e}")
    if "perfil" in st.session_state:
        st.info(f"Perfil detectado: {st.session_state['perfil']}")
        with st.expander("Búsquedas que hizo Claude"):
            st.write(st.session_state["consultas"])
else:
    subido = st.file_uploader("JSON con {titulo, descripcion}", type="json")
    raw = subido.read().decode("utf-8") if subido else (BASE / "vacantes_ejemplo.json").read_text(encoding="utf-8")
    st.session_state["vacantes"] = json.loads(raw)

vacantes = st.session_state.get("vacantes")
if vacantes:
    if st.button("Analizar afinidad", type="primary" if fuente != "Buscar en internet" else "secondary"):
        st.session_state["ranking"] = matching.rank_vacancies(cv_text, vacantes, load_model())
        st.session_state.pop("cv_nuevo", None)
elif fuente == "Buscar en internet":
    st.caption("Pulsa el botón para buscar.")

# ---------- 3. Ranking ----------
ranking = st.session_state.get("ranking")
if ranking:
    st.subheader("3. Ranking por afinidad con tu CV")
    st.dataframe(pd.DataFrame([{
        "Vacante": r["titulo"], "Empresa": r.get("empresa", ""),
        "Similitud": round(r["score"], 3),
        "Cubiertas": len(r["habilidades_cubiertas"]), "Brechas": len(r["brechas"]),
        "Enlace": r.get("url", ""),
        "URL verificada": {True: "✅", False: "⚠️"}.get(r.get("verificada"), ""),
    } for r in ranking]), hide_index=True, use_container_width=True,
        column_config={"Enlace": st.column_config.LinkColumn("Enlace", display_text="Ver oferta")})
    if any(r.get("verificada") is False for r in ranking):
        st.caption("⚠️ = la URL no coincidió exactamente con un resultado de búsqueda; ábrela para confirmar.")

    opciones = [f"{i + 1}. {r['titulo']}" + (f" — {r['empresa']}" if r.get("empresa") else "")
                for i, r in enumerate(ranking)]
    idx = st.selectbox("Vacante objetivo (por defecto, la más afín)", range(len(ranking)),
                       format_func=lambda i: opciones[i])
    elegida = ranking[idx]

    st.subheader(f"4. {elegida['titulo']}")
    if elegida.get("por_que_encaja"):
        st.write(elegida["por_que_encaja"])
    c1, c2 = st.columns(2)
    c1.success("Habilidades que ya tienes: " + (", ".join(elegida["habilidades_cubiertas"]) or "—"))
    c2.warning("Brechas detectadas: " + (", ".join(elegida["brechas"]) or "ninguna"))

    # ---------- 5. CV reestructurado ----------
    st.subheader("5. Tu CV reestructurado para esta vacante")
    if st.button("✍️ Reestructurar mi CV", type="primary", disabled=not tiene_key):
        try:
            with st.spinner("Reescribiendo tu hoja de vida..."):
                st.session_state["cv_nuevo"] = llm_helper.reestructurar_cv(cv_text, elegida, api_key)
                st.session_state["elegida"] = elegida["titulo"]
        except Exception as e:
            st.error(f"No se pudo llamar a la API: {e}")
    if "cv_nuevo" in st.session_state:
        st.caption(f"Adaptado a: {st.session_state['elegida']}")
        st.markdown(st.session_state["cv_nuevo"])
        st.download_button("⬇️ Descargar CV (Markdown)", st.session_state["cv_nuevo"],
                           file_name="cv_reestructurado.md", mime="text/markdown")
