# Optimizador de CV con IA (PTIA – Hito 2)

    python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
    export GEMINI_API_KEY=tu_clave        # gratis en aistudio.google.com/apikey (Windows: set GEMINI_API_KEY=...)
    # o, con saldo en Anthropic: export ANTHROPIC_API_KEY=tu_clave
    .venv/bin/streamlit run app.py

Flujo: CV (PDF, Word .docx/.doc, TXT o texto pegado) → búsqueda de vacantes **reales** en internet → ranking por afinidad
→ brechas de habilidades → CV reestructurado para la vacante elegida (descargable).

- `busqueda_web.py`: Claude con la herramienta `web_search` busca ofertas publicadas y las entrega
  con un esquema estricto (título, empresa, URL, descripción). Cada URL se marca como verificada si
  salió de un resultado real de la búsqueda.
- `matching.py`: embeddings (paraphrase-multilingual-MiniLM-L12-v2), similitud coseno, brechas de habilidades.
- `llm_helper.py`: reestructuración completa del CV (sin inventar experiencia) y sugerencias.
- `app.py`: interfaz Streamlit. Modo "Archivo JSON (demo)" para probar sin internet con `vacantes_ejemplo.json`.

Modelo por defecto: `claude-opus-5-5` (cambiable con la variable `CLAUDE_MODEL`).
La búsqueda web debe estar habilitada en la organización de la Console de Anthropic.

### Motor gratuito (Gemini)
En la barra lateral se elige el motor de IA. Con **Gemini (gratis)** la búsqueda usa `ddgs`
(DuckDuckGo/Bing, sin clave) para obtener resultados reales y Gemini solo elige y estructura
las ofertas: cada URL proviene del buscador, nunca del modelo. `gemini_helper.py` elige el
modelo Flash estable más reciente (cambiable con `GEMINI_MODEL`).

### Validación (Hito 3)
    .venv/bin/python evaluacion/evaluacion.py          # ranking, habilidades y tiempos (sin API key)
    .venv/bin/python evaluacion/evaluacion.py --llm    # + CV reestructurado y búsqueda web (requiere clave)

Documento del hito: [`docs/hito3.md`](docs/hito3.md).
`evaluacion/dataset_eval.json`: 6 CV (español e inglés) × 20 vacantes con relevancia etiquetada a mano.
Compara el MVP (embeddings) con TF-IDF, Jaccard de habilidades y un orden aleatorio; guarda `evaluacion/resultados.json`.
