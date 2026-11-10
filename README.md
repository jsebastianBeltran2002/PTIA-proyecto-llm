# Optimizador de CV con IA (PTIA – Hito 2)

    python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
    export ANTHROPIC_API_KEY=tu_clave     # Windows: set ANTHROPIC_API_KEY=tu_clave
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
