"""Interfaz Streamlit: CV -> búsqueda real de vacantes en internet -> ranking -> brechas -> CV reestructurado."""
import html
import json
import os
from pathlib import Path

import streamlit as st

import busqueda_web
import llm_helper
import matching

BASE = Path(__file__).parent
ENV_FILE = BASE / ".env"  # claves guardadas localmente (está en .gitignore)


def _cargar_env():
    if not ENV_FILE.exists():
        return
    for linea in ENV_FILE.read_text(encoding="utf-8").splitlines():
        if "=" in linea and not linea.lstrip().startswith("#"):
            k, v = linea.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def _guardar_env(nombre: str, valor: str):
    lineas = ENV_FILE.read_text(encoding="utf-8").splitlines() if ENV_FILE.exists() else []
    lineas = [l for l in lineas if not l.split("=", 1)[0].strip() == nombre]
    lineas.append(f"{nombre}={valor.strip()}")
    ENV_FILE.write_text("\n".join(lineas) + "\n", encoding="utf-8")
    os.environ[nombre] = valor.strip()


_cargar_env()
st.set_page_config(page_title="Ajuste · Optimizador de hojas de vida", page_icon=":material/description:",
                   layout="wide", initial_sidebar_state="collapsed")

# Evita que Chrome/Google Translate traduzca la página: al traducir modifica el DOM
# y React falla con "removeChild ... no es un hijo de este nodo".
st.html("""<script>
const d = document;
d.documentElement.lang = "es";
d.documentElement.setAttribute("translate", "no");
d.documentElement.classList.add("notranslate");
if (!d.querySelector('meta[name="google"]')) {
  const m = d.createElement("meta"); m.name = "google"; m.content = "notranslate"; d.head.appendChild(m);
}
</script>""", unsafe_allow_javascript=True)

# ---------------------------------------------------------------- estilos
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:opsz,wght@14..32,400..700&display=swap');

:root {
  --paper: #F5F5F7; --surface: #FFFFFF; --ink: #1D1D1F; --ink-2: #424245; --muted: #6E6E73;
  --line: #E3E3E8; --line-2: #EDEDF0;
  --accent: #0071E3; --accent-2: #0A84FF; --accent-soft: #E8F1FD;
  --warn: #C4520F; --warn-soft: #FDF0E7;
  --ease: cubic-bezier(.22, .61, .36, 1);
  --sans: -apple-system, BlinkMacSystemFont, 'SF Pro Text', 'SF Pro Display', 'Inter', 'Segoe UI', sans-serif;
  --serif: var(--sans);
}
html, body, .stApp, [class*="css"], .stMarkdown, button, input, textarea, select, label {
  font-family: var(--sans) !important; -webkit-font-smoothing: antialiased; letter-spacing: -0.01em;
}
.stApp { background: var(--paper); color: var(--ink); }
[data-testid="stHeader"] { background: transparent; }
[data-testid="stAppDeployButton"], footer, [data-testid="stDecoration"] { display: none; }
.block-container { padding-top: 2.5rem; padding-bottom: 6rem; max-width: 1080px; }
[data-testid="stSidebar"] { background: var(--surface); border-right: 1px solid var(--line); }
[data-testid="stSidebar"] .block-container { padding-top: 2rem; }

/* animaciones */
@keyframes rise { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: none; } }
@keyframes grow { from { width: 0; } }
@keyframes fade { from { opacity: 0; } to { opacity: 1; } }
.rise { animation: rise .55s var(--ease) both; }
[data-testid="stElementContainer"], [data-testid="stVerticalBlockBorderWrapper"] { animation: fade .35s var(--ease) both; }
@media (prefers-reduced-motion: reduce) { *, *::before, *::after { animation: none !important; transition: none !important; } }

/* encabezado */
.masthead { padding: .5rem 0 2.2rem 0; border-bottom: 1px solid var(--line); margin-bottom: 2rem; }
.eyebrow { font-size: .74rem; letter-spacing: .14em; text-transform: uppercase; color: var(--muted); font-weight: 500; }
.masthead h1 { font-family: var(--sans) !important; font-weight: 700; font-size: clamp(2.3rem, 5vw, 3.4rem);
  line-height: 1.05; letter-spacing: -.035em; color: var(--ink); margin: .7rem 0 .9rem 0; padding: 0; }
.masthead h1 em { color: var(--accent); font-style: normal; }
.masthead p { color: var(--ink-2); font-size: 1.05rem; max-width: 620px; line-height: 1.55; margin: 0; }

/* progreso */
.tracker { display: grid; grid-template-columns: repeat(4, 1fr); gap: .6rem; margin: 0 0 2.6rem 0; }
.tracker .t { position: relative; padding-top: .8rem; font-size: .82rem; color: var(--muted); }
.tracker .t::before { content: ""; position: absolute; top: 0; left: 0; right: 0; height: 3px; border-radius: 3px;
  background: var(--line); }
.tracker .t::after { content: ""; position: absolute; top: 0; left: 0; height: 3px; border-radius: 3px; width: 0;
  background: var(--accent); transition: width .6s var(--ease); }
.tracker .t.done::after { width: 100%; }
.tracker .t.now::after { width: 45%; }
.tracker .t b { display: block; font-weight: 500; color: var(--ink); font-size: .9rem; margin-top: .1rem; }
.tracker .t.pending b { color: var(--muted); }

/* secciones */
.sec { display: grid; grid-template-columns: 3.2rem 1fr; gap: .4rem 1rem; align-items: baseline; margin: 3.2rem 0 1.2rem 0; }
.sec .n { font-size: 1rem; font-weight: 600; color: var(--accent); line-height: 1; font-variant-numeric: tabular-nums; }
.sec h2 { font-family: var(--sans) !important; font-weight: 700; font-size: 1.7rem; letter-spacing: -.03em;
  margin: 0; padding: 0; color: var(--ink); line-height: 1.1; }
.sec p { grid-column: 2; margin: 0; color: var(--muted); font-size: .95rem; }

.muted { color: var(--muted); font-size: .9rem; line-height: 1.5; }
.label { font-size: .72rem; letter-spacing: .12em; text-transform: uppercase; color: var(--muted); font-weight: 500; margin-bottom: .5rem; }

/* etiquetas */
.chips { display: flex; flex-wrap: wrap; gap: .35rem; }
.chip { padding: .28rem .7rem; border-radius: 999px; font-size: .8rem; border: 1px solid var(--line);
  background: var(--surface); color: var(--ink-2); transition: all .2s var(--ease); }
.chip.ok { background: var(--accent-soft); border-color: transparent; color: var(--accent); }
.chip.gap { background: var(--warn-soft); border-color: transparent; color: var(--warn); }
.chip:hover { transform: translateY(-1px); }

/* tarjetas de vacantes */
.job { background: var(--surface); border: 1px solid var(--line); border-radius: 16px; padding: 1.25rem 1.3rem 1.1rem;
  transition: border-color .25s var(--ease), box-shadow .25s var(--ease), transform .25s var(--ease); }
.job:hover { border-color: #CDCDD3; box-shadow: 0 14px 30px -20px rgba(29,29,31,.3); transform: translateY(-2px); }
.job.sel { border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-soft); }
.job .head { display: flex; gap: 1rem; align-items: flex-start; }
.job .title { font-weight: 600; font-size: 1.02rem; color: var(--ink); line-height: 1.3; }
.job .company { color: var(--muted); font-size: .85rem; margin-top: .2rem; }
.job .score { margin-left: auto; text-align: right; flex-shrink: 0; }
.job .score .v { font-weight: 700; letter-spacing: -.03em; font-size: 1.9rem; line-height: .9; color: var(--ink); }
.job .score .v small { font-size: 1rem; color: var(--muted); }
.job .score .k { font-size: .68rem; letter-spacing: .1em; text-transform: uppercase; color: var(--muted); }
.bar { height: 4px; background: var(--line-2); border-radius: 99px; margin: 1rem 0 .85rem; overflow: hidden; }
.bar > div { height: 100%; border-radius: 99px; background: var(--accent); animation: grow 1s var(--ease) both; }
.job .meta { display: flex; gap: 1.1rem; align-items: center; font-size: .82rem; color: var(--ink-2); flex-wrap: wrap; }
.job .meta a { margin-left: auto; color: var(--accent); font-weight: 500; text-decoration: none;
  border-bottom: 1px solid transparent; transition: border-color .2s var(--ease); }
.job .meta a:hover { border-color: var(--accent); }
.dot { display: inline-block; width: 6px; height: 6px; border-radius: 50%; margin-right: .4rem; vertical-align: middle; }
.dot.ok { background: var(--accent-2); } .dot.gap { background: var(--warn); }
.tag { font-size: .7rem; padding: .15rem .5rem; border-radius: 6px; background: var(--line-2); color: var(--muted); }

/* detalle */
.stats { display: grid; grid-template-columns: repeat(3, 1fr); border: 1px solid var(--line); border-radius: 16px;
  background: var(--surface); overflow: hidden; margin-bottom: 1.2rem; }
.stats > div { padding: 1.1rem 1.3rem; border-right: 1px solid var(--line); }
.stats > div:last-child { border-right: none; }
.stats .v { font-weight: 700; letter-spacing: -.035em; font-size: 2.2rem; line-height: 1; color: var(--ink); }
.stats .v.ok { color: var(--accent); } .stats .v.gap { color: var(--warn); }
.panel { background: var(--surface); border: 1px solid var(--line); border-radius: 16px; padding: 1.1rem 1.3rem; height: 100%; }
.note { border-left: 2px solid var(--accent); padding: .2rem 0 .2rem 1rem; color: var(--ink-2); margin: 0 0 1.2rem 0;
  font-size: 1.05rem; line-height: 1.55; }

.status { display: flex; align-items: center; gap: .5rem; font-size: .85rem; color: var(--ink-2); margin: .3rem 0 .8rem; }
.status i { width: 8px; height: 8px; border-radius: 50%; background: #C7C7CC; display: inline-block; }
.status.on i { background: var(--accent-2); box-shadow: 0 0 0 4px var(--accent-soft); }

.empty { text-align: center; padding: 3rem 1rem; border: 1px dashed #D2D2D8; border-radius: 16px; color: var(--muted); }
.empty h3 { font-family: var(--sans) !important; font-weight: 600; font-size: 1.35rem; letter-spacing: -.02em; color: var(--ink); margin: 0 0 .3rem; padding: 0; }

/* controles de Streamlit */
.stButton > button, .stDownloadButton > button {
  border-radius: 10px; font-weight: 500; padding: .55rem 1.15rem; border: 1px solid var(--line);
  background: var(--surface); color: var(--ink);
  transition: background .2s var(--ease), border-color .2s var(--ease), transform .15s var(--ease), box-shadow .2s var(--ease); }
.stButton > button:hover, .stDownloadButton > button:hover { border-color: var(--ink); color: var(--ink); transform: translateY(-1px); }
.stButton > button:active { transform: translateY(0); }
.stButton > button[kind="primary"] { background: var(--ink); color: #fff; border-color: var(--ink); }
.stButton > button[kind="primary"]:hover { background: var(--accent); border-color: var(--accent); color: #fff;
  box-shadow: 0 10px 22px -12px rgba(0,113,227,.6); }
.stButton > button:disabled { opacity: .45; transform: none; }
.stButton > button[kind="tertiary"] { color: var(--accent); padding-left: 0; }
.stTextArea textarea, .stTextInput input { border-radius: 12px !important; background: var(--surface) !important;
  font-size: .9rem; line-height: 1.55; transition: box-shadow .2s var(--ease); }
.stTextArea textarea:focus, .stTextInput input:focus { box-shadow: 0 0 0 3px var(--accent-soft) !important; }
[data-testid="stFileUploaderDropzone"] { border-radius: 16px; background: var(--surface); border: 1px dashed #C7C7CE;
  transition: border-color .2s var(--ease), background .2s var(--ease); padding: 1.6rem 1rem; }
[data-testid="stFileUploaderDropzone"]:hover { border-color: var(--accent); background: #FAFBFD; }
[data-testid="stVerticalBlockBorderWrapper"]:has(> div > [data-testid="stVerticalBlock"]) { border-radius: 16px; }
[data-baseweb="tab-list"] { gap: 1.2rem; border-bottom: 1px solid var(--line); }
[data-baseweb="tab"] { font-weight: 500; }
[data-baseweb="tab-highlight"] { background: var(--accent) !important; }
[data-testid="stExpander"] details { border-radius: 12px; border-color: var(--line); background: var(--surface); }
.cv-doc { background: var(--surface); border: 1px solid var(--line); border-radius: 16px; padding: 2.2rem 2.4rem;
  box-shadow: 0 30px 60px -45px rgba(26,26,23,.45); }

@media (max-width: 720px) {
  .tracker { grid-template-columns: repeat(2, 1fr); }
  .stats { grid-template-columns: 1fr; } .stats > div { border-right: none; border-bottom: 1px solid var(--line); }
  .sec { grid-template-columns: 2.4rem 1fr; }
}
</style>
""", unsafe_allow_html=True)


def esc(t) -> str:
    return html.escape(str(t or ""))


def H(texto: str):
    """Renderiza HTML sin sangrías (evita que Markdown lo tome como bloque de código)."""
    st.markdown(" ".join(l.strip() for l in texto.splitlines() if l.strip()), unsafe_allow_html=True)


def chips(items, kind="", vacio="—") -> str:
    if not items:
        return f'<span class="muted">{esc(vacio)}</span>'
    return '<div class="chips">' + "".join(f'<span class="chip {kind}">{esc(i)}</span>' for i in items) + "</div>"


def seccion(n: int, titulo: str, sub: str = ""):
    H(f'<div class="sec rise"><span class="n">{n:02d}</span><h2>{esc(titulo)}</h2>'
      + (f"<p>{esc(sub)}</p>" if sub else "") + "</div>")


@st.cache_resource(show_spinner="Preparando el modelo de afinidad (solo la primera vez)…")
def load_model():
    return matching.get_model()


# ---------------------------------------------------------------- lectura de archivos
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


def _decodificar(datos: bytes) -> str:
    for cod in ("utf-8-sig", "cp1252"):  # Windows suele guardar .txt en cp1252
        try:
            return datos.decode(cod)
        except UnicodeDecodeError:
            continue
    return datos.decode("utf-8", errors="ignore")


@st.cache_data(show_spinner=False, max_entries=10)
def _leer_bytes(nombre: str, datos: bytes) -> str:
    import io
    nombre = nombre.lower()
    if nombre.endswith(".pdf"):
        from pypdf import PdfReader
        lector = PdfReader(io.BytesIO(datos))
        if lector.is_encrypted:
            try:
                lector.decrypt("")
            except Exception:
                raise RuntimeError("El PDF está protegido con contraseña. Quítala o exporta el CV de nuevo.")
        return "\n".join(p.extract_text() or "" for p in lector.pages)
    if nombre.endswith(".docx"):
        return _leer_docx(io.BytesIO(datos))
    if nombre.endswith(".doc"):
        return _leer_doc(datos)
    return _decodificar(datos)


def leer_cv(archivo) -> str:
    return _leer_bytes(archivo.name, archivo.getvalue())


def _reset_resultados():
    for k in ("ranking", "cv_nuevo", "elegida", "sel"):
        st.session_state.pop(k, None)


def _elegir(i: int):
    st.session_state["sel"] = i


# ---------------------------------------------------------------- ajustes (barra lateral)
with st.sidebar:
    H('<div class="label">Ajustes</div>')
    proveedor_label = st.segmented_control("Motor de IA", ["Gemini · gratis", "Claude"],
                                           default="Gemini · gratis") or "Gemini · gratis"
    proveedor = "gemini" if proveedor_label.startswith("Gemini") else "claude"
    if proveedor == "gemini":
        var_key = "GEMINI_API_KEY"
        api_key = st.text_input("Clave de Gemini", type="password", placeholder="AIza…",
                                help="Gratis en aistudio.google.com/apikey") or None
        tiene_key = bool(api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"))
        ayuda_key = "Créala gratis, sin tarjeta, en aistudio.google.com/apikey."
    else:
        var_key = "ANTHROPIC_API_KEY"
        api_key = st.text_input("Clave de Anthropic", type="password", placeholder="sk-ant-…") or None
        tiene_key = bool(api_key or os.getenv("ANTHROPIC_API_KEY"))
        ayuda_key = "Créala en console.anthropic.com (requiere saldo)."
    if api_key and api_key.strip() != os.getenv(var_key, ""):
        if st.button("Recordar clave en este equipo", use_container_width=True):
            _guardar_env(var_key, api_key)
            st.toast("Clave guardada en este equipo.")
    if tiene_key:
        H('<div class="status on"><i></i>Motor de IA conectado'
          + (" · clave guardada" if os.getenv(var_key) else "") + "</div>")
    else:
        H(f'<div class="status"><i></i>Sin clave</div><div class="muted">{ayuda_key} '
          "Sin ella puedes usar el modo de prueba.</div>")
    st.divider()
    H('<div class="label">Modelo</div>')
    if proveedor == "claude":
        H(f'<div class="muted">{esc(os.getenv("CLAUDE_MODEL", "claude-opus-5-5"))}</div>')
    else:
        H('<div class="muted">Gemini Flash más reciente disponible para tu clave.</div>')

# ---------------------------------------------------------------- encabezado
H("""
<header class="masthead rise">
  <div class="eyebrow">PTIA · Escuela Colombiana de Ingeniería Julio Garavito</div>
  <h1>Tu hoja de vida,<br><em>a la medida</em> de cada vacante.</h1>
  <p>Encuentra ofertas reales que encajan con tu perfil, mira qué te falta para cada una
  y obtén una versión de tu CV escrita para la que elijas.</p>
</header>
""")
tracker = st.empty()

# ---------------------------------------------------------------- 01 · hoja de vida
seccion(1, "Tu hoja de vida", "Sube el archivo o pega el texto. Puedes editarlo antes de continuar.")
col_a, col_b = st.columns([1, 1.45], gap="large")
with col_a:
    archivo_cv = st.file_uploader("Archivo (PDF, Word o TXT)", type=["pdf", "docx", "doc", "txt"])
    cv_inicial = (BASE / "cv_ejemplo.txt").read_text(encoding="utf-8")
    origen = "Ejemplo incluido"
    if archivo_cv:
        try:
            cv_inicial = leer_cv(archivo_cv)
            origen = archivo_cv.name
            if not cv_inicial.strip():
                st.warning("El archivo no tiene texto seleccionable (¿es un escaneo?). Pega el contenido a la derecha.")
        except Exception as e:
            st.error(f"No se pudo leer el archivo: {e}")
with col_b:
    cv_text = st.text_area("Contenido", value=cv_inicial, height=260)
with col_a:
    habilidades_cv = sorted(matching.extract_skills(cv_text))
    H(f'<div class="label" style="margin-top:1rem">Detectado en {esc(origen)}</div>'
      f'<div class="muted" style="margin-bottom:.6rem">{len(cv_text.split())} palabras · '
      f'{len(habilidades_cv)} habilidades</div>' + chips(habilidades_cv, "", "Aún no se detectan habilidades"))

# ---------------------------------------------------------------- 02 · vacantes
seccion(2, "Vacantes", "Busca ofertas reales en internet o usa el conjunto de prueba.")
fuente = st.segmented_control("Fuente", ["Buscar en internet", "Conjunto de prueba"],
                              default="Buscar en internet" if tiene_key else "Conjunto de prueba",
                              label_visibility="collapsed") or "Conjunto de prueba"
web = fuente == "Buscar en internet"

with st.container(border=True):
    if web:
        c1, c2, c3 = st.columns([2, 2, 1.3], vertical_alignment="bottom")
        ubicacion = c1.text_input("Ubicación", "Colombia")
        cantidad = c2.slider("Número de vacantes", 3, 15, 8)
        if c3.button("Buscar", type="primary", disabled=not tiene_key, use_container_width=True,
                     icon=":material/travel_explore:"):
            try:
                with st.spinner("Buscando ofertas publicadas… puede tardar alrededor de un minuto."):
                    res = busqueda_web.buscar_vacantes(cv_text, ubicacion, cantidad, api_key, proveedor)
                _reset_resultados()
                st.session_state.update(vacantes=res["vacantes"], perfil=res["perfil_detectado"],
                                        consultas=res["consultas"], fuente_vac="web")
                if not res["vacantes"]:
                    st.warning("No aparecieron ofertas que encajen. Prueba otra ubicación o ajusta tu CV.")
            except Exception as e:
                st.error(f"No se pudo completar la búsqueda: {e}")
        if not tiene_key:
            H('<div class="muted">Agrega una clave en Ajustes (barra lateral) para buscar en internet. '
              "Gemini es gratis.</div>")
        if st.session_state.get("fuente_vac") == "web" and st.session_state.get("perfil"):
            H(f'<div class="label" style="margin-top:.8rem">Perfil detectado</div>'
              f'<div style="color:var(--ink-2)">{esc(st.session_state["perfil"])}</div>')
            with st.expander("Búsquedas realizadas"):
                H(chips(st.session_state["consultas"]))
    else:
        subido = st.file_uploader("JSON con una lista de {titulo, descripcion}", type="json")
        raw = (subido.read().decode("utf-8") if subido
               else (BASE / "vacantes_ejemplo.json").read_text(encoding="utf-8"))
        try:
            nuevas = json.loads(raw)
            if st.session_state.get("fuente_vac") != "demo" or st.session_state.get("vacantes") != nuevas:
                _reset_resultados()
            st.session_state.update(vacantes=nuevas, fuente_vac="demo")
            H(f'<div class="muted">{len(nuevas)} vacantes de prueba cargadas'
              + ("" if subido else " (vacantes_ejemplo.json)") + ".</div>")
        except json.JSONDecodeError as e:
            st.error(f"El JSON no es válido: {e}")

vacantes = st.session_state.get("vacantes")
fuente_ok = bool(vacantes) and st.session_state.get("fuente_vac") == ("web" if web else "demo")
if fuente_ok:
    if st.button(f"Analizar afinidad con {len(vacantes)} vacantes", type="primary",
                 icon=":material/insights:"):
        with st.spinner("Comparando tu perfil con cada vacante…"):
            st.session_state["ranking"] = matching.rank_vacancies(cv_text, vacantes, load_model())
        st.session_state["sel"] = 0
        st.session_state.pop("cv_nuevo", None)

ranking = st.session_state.get("ranking") if fuente_ok else None


def _pintar_tracker():
    pasos = [("Hoja de vida", bool(cv_text.strip())), ("Vacantes", fuente_ok),
             ("Afinidad", bool(ranking)), ("CV optimizado", "cv_nuevo" in st.session_state)]
    actual = next((i for i, (_, ok) in enumerate(pasos) if not ok), len(pasos))
    celdas = []
    for i, (nombre, ok) in enumerate(pasos):
        clase = "done" if ok else ("now" if i == actual else "pending")
        estado = "Listo" if ok else ("En curso" if i == actual else "Pendiente")
        celdas.append(f'<div class="t {clase}">{estado}<b>{nombre}</b></div>')
    tracker.markdown('<div class="tracker rise">' + "".join(celdas) + "</div>", unsafe_allow_html=True)


if not ranking:
    _pintar_tracker()
    H('<div class="empty rise" style="margin-top:2.4rem"><h3>Aquí verás tus vacantes ordenadas</h3>'
      'Carga vacantes y pulsa “Analizar afinidad”.</div>')
    st.stop()

# ---------------------------------------------------------------- 03 · ranking
seccion(3, "Afinidad", f"{len(ranking)} vacantes ordenadas según cuánto se parecen a tu perfil.")
sel = min(st.session_state.get("sel", 0), len(ranking) - 1)

cols = st.columns(2, gap="medium")
for i, r in enumerate(ranking):
    pct = round(r["score"] * 100)
    verif = r.get("verificada")
    tag = "" if verif is not False else '<span class="tag">Confirma el enlace</span>'
    link = (f'<a href="{esc(r["url"])}" target="_blank" rel="noopener">Ver oferta →</a>'
            if r.get("url") else "")
    sub = " · ".join(x for x in (r.get("empresa"), r.get("ubicacion")) if x)
    with cols[i % 2]:
        H(f"""
        <div class="job {'sel' if i == sel else ''} rise" style="animation-delay:{min(i, 8) * 60}ms">
          <div class="head">
            <div><div class="title">{esc(r['titulo'])}</div><div class="company">{esc(sub) or '&nbsp;'}</div></div>
            <div class="score"><div class="v">{pct}<small>%</small></div><div class="k">afinidad</div></div>
          </div>
          <div class="bar"><div style="width:{max(pct, 2)}%;animation-delay:{150 + min(i, 8) * 60}ms"></div></div>
          <div class="meta"><span><span class="dot ok"></span>{len(r['habilidades_cubiertas'])} coinciden</span>
          <span><span class="dot gap"></span>{len(r['brechas'])} por cubrir</span>{tag}{link}</div>
        </div>""")
        if i == sel:
            st.button("Vacante seleccionada", key=f"sel_{i}", type="tertiary", disabled=True,
                      icon=":material/check_circle:")
        else:
            st.button("Elegir esta vacante", key=f"sel_{i}", type="tertiary", on_click=_elegir, args=(i,))

elegida = ranking[sel]

# ---------------------------------------------------------------- 04 · detalle
seccion(4, elegida["titulo"], " · ".join(x for x in (elegida.get("empresa"), elegida.get("ubicacion")) if x))
H(f"""
<div class="stats rise">
  <div><div class="label">Afinidad</div><div class="v">{round(elegida['score'] * 100)}%</div></div>
  <div><div class="label">Habilidades que tienes</div><div class="v ok">{len(elegida['habilidades_cubiertas'])}</div></div>
  <div><div class="label">Por cubrir</div><div class="v gap">{len(elegida['brechas'])}</div></div>
</div>""")
if elegida.get("por_que_encaja"):
    H(f'<p class="note rise">{esc(elegida["por_que_encaja"])}</p>')
c1, c2 = st.columns(2, gap="medium")
with c1:
    H('<div class="panel rise"><div class="label">Ya las tienes</div>'
      + chips(elegida["habilidades_cubiertas"], "ok", "Ninguna coincidencia directa") + "</div>")
with c2:
    H('<div class="panel rise"><div class="label">Te faltan</div>'
      + chips(elegida["brechas"], "gap", "Ninguna: cubres todo lo detectado") + "</div>")
with st.expander("Descripción de la vacante"):
    st.write(elegida.get("descripcion", ""))
    if elegida.get("url"):
        st.link_button("Abrir la oferta original", elegida["url"], icon=":material/open_in_new:")

# ---------------------------------------------------------------- 05 · CV optimizado
seccion(5, "Tu CV para esta vacante", "Se reorganiza y reescribe sin inventar experiencia.")
b1, b2 = st.columns([1.2, 3], vertical_alignment="center")
etiqueta = "Volver a generar" if st.session_state.get("elegida") == elegida["titulo"] else "Reescribir mi CV"
if b1.button(etiqueta, type="primary", disabled=not tiene_key, use_container_width=True,
             icon=":material/edit_note:"):
    try:
        with st.spinner("Reescribiendo tu hoja de vida…"):
            st.session_state["cv_nuevo"] = llm_helper.reestructurar_cv(cv_text, elegida, api_key, proveedor)
            st.session_state["elegida"] = elegida["titulo"]
    except Exception as e:
        st.error(f"No se pudo generar el CV: {e}")
if not tiene_key:
    b2.markdown('<span class="muted">Requiere una clave en Ajustes. Gemini es gratis.</span>',
                unsafe_allow_html=True)

if "cv_nuevo" in st.session_state:
    if st.session_state.get("elegida") != elegida["titulo"]:
        H(f'<div class="muted" style="margin:.6rem 0">Este CV se generó para '
          f'<b>{esc(st.session_state["elegida"])}</b>. Pulsa el botón para adaptarlo a la vacante actual.</div>')
    tab_v, tab_c = st.tabs(["Documento", "Comparar con el original"])
    with tab_v:
        with st.container(border=True):
            st.markdown(st.session_state["cv_nuevo"])
    with tab_c:
        o, n = st.columns(2, gap="medium")
        with o:
            H('<div class="label">Original</div>')
            st.text(cv_text)
        with n:
            H('<div class="label">Optimizado</div>')
            st.markdown(st.session_state["cv_nuevo"])
    d1, d2, _ = st.columns([1, 1, 2.5])
    d1.download_button("Descargar .md", st.session_state["cv_nuevo"], file_name="cv_optimizado.md",
                       mime="text/markdown", use_container_width=True, icon=":material/download:")
    d2.download_button("Descargar .txt", st.session_state["cv_nuevo"], file_name="cv_optimizado.txt",
                       mime="text/plain", use_container_width=True, icon=":material/download:")

_pintar_tracker()
