"""Módulo de razonamiento: adaptación y reestructuración del CV con la API de Claude."""
import os

MODEL = os.getenv("CLAUDE_MODEL", "claude-opus-5-5")

PROMPT_SUGERENCIAS = """Eres un asesor de hojas de vida. Tienes el CV de una persona y una vacante.

CV:
{cv}

VACANTE: {titulo}
{descripcion}

Habilidades de la vacante que NO aparecen en el CV: {brechas}

Responde en español, conciso y accionable, con este formato:
1. Qué resaltar: 3 puntos del CV que más conectan con la vacante.
2. Qué reescribir: 3 cambios concretos (da una frase reescrita de ejemplo en cada uno).
3. Brechas: para cada habilidad faltante, di si conviene mencionarla SOLO si el CV ya da evidencia real; no inventes experiencia.
Nunca agregues logros, cargos o habilidades que no estén en el CV."""

PROMPT_REESTRUCTURAR = """Reestructura esta hoja de vida para postularse a la vacante indicada.

HOJA DE VIDA ORIGINAL:
{cv}

VACANTE: {titulo}{empresa}
{descripcion}

Habilidades que pide la vacante y no aparecen en el CV: {brechas}

Instrucciones:
- Devuelve la hoja de vida COMPLETA en Markdown, lista para copiar, en español.
- Estructura: nombre/encabezado (usa los datos del original; si faltan, deja [Nombre], [Correo], [Teléfono]),
  Perfil profesional (3-4 líneas orientadas a la vacante), Habilidades (agrupadas, primero las que pide
  la vacante), Experiencia/Proyectos (viñetas con verbo de acción + qué hiciste + herramienta + resultado),
  Educación, Idiomas.
- Usa las palabras clave de la vacante SOLO donde el original da evidencia real.
- PROHIBIDO inventar empleos, cargos, fechas, cifras, certificaciones o habilidades. Si un resultado no
  tiene cifra en el original, no la pongas; puedes dejar [agregar métrica] como sugerencia.
- Las brechas no van en el CV. Al final, después de una línea `---`, agrega "Notas para ti" con
  máximo 4 viñetas: qué datos faltan completar y cómo cerrar las brechas."""


def _llamar(prompt: str, api_key: str | None) -> str:
    import anthropic
    client = anthropic.Anthropic(api_key=api_key or os.getenv("ANTHROPIC_API_KEY"))
    msg = client.beta.messages.create(
        model=MODEL,
        max_tokens=16000,
        output_config={"effort": "medium"},
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        messages=[{"role": "user", "content": prompt}],
    )
    if msg.stop_reason == "refusal":
        raise RuntimeError("El modelo rechazó la solicitud.")
    return "".join(b.text for b in msg.content if b.type == "text")


def _campos(vacante: dict) -> dict:
    return {
        "titulo": vacante["titulo"],
        "empresa": f" — {vacante['empresa']}" if vacante.get("empresa") else "",
        "descripcion": vacante["descripcion"],
        "brechas": ", ".join(vacante.get("brechas", [])) or "ninguna",
    }


def sugerir_adaptacion(cv: str, vacante: dict, api_key: str | None = None) -> str:
    c = _campos(vacante)
    return _llamar(PROMPT_SUGERENCIAS.format(cv=cv, titulo=c["titulo"], descripcion=c["descripcion"],
                                             brechas=c["brechas"]), api_key)


def reestructurar_cv(cv: str, vacante: dict, api_key: str | None = None) -> str:
    return _llamar(PROMPT_REESTRUCTURAR.format(cv=cv, **_campos(vacante)), api_key)
