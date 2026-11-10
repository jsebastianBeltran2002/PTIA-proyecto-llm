"""Búsqueda de vacantes REALES en internet con la herramienta web_search de Claude.

Flujo: CV -> Claude busca ofertas publicadas en la web -> reporta cada una con la
herramienta `reportar_vacantes` (esquema estricto) -> se verifica que cada URL haya
salido de un resultado real de búsqueda.
"""
import os

MODEL = os.getenv("CLAUDE_MODEL", "claude-opus-5-5")
MAX_CONTINUACIONES = 5

SISTEMA = """Eres un reclutador que busca ofertas de empleo REALES y vigentes en internet.
Reglas:
- Usa la búsqueda web. Prioriza portales de empleo (LinkedIn, Computrabajo, elempleo,
  Indeed, Magneto, sitios de carreras de empresas) y ofertas publicadas recientemente.
- Solo reporta ofertas que hayas visto en los resultados de búsqueda, con su URL exacta.
  Nunca inventes empresas, cargos ni URLs. Si no encuentras suficientes, reporta menos.
- Prefiere la URL de la oferta individual sobre la de un listado general.
- Cuando termines, llama UNA vez a la herramienta `reportar_vacantes` con todas las ofertas."""

HERRAMIENTA_REPORTE = {
    "name": "reportar_vacantes",
    "description": "Entrega la lista final de ofertas de empleo reales encontradas en la web.",
    "strict": True,
    "input_schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["perfil_detectado", "vacantes"],
        "properties": {
            "perfil_detectado": {
                "type": "string",
                "description": "Resumen en una frase del perfil profesional del CV.",
            },
            "vacantes": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["titulo", "empresa", "ubicacion", "url", "descripcion", "por_que_encaja"],
                    "properties": {
                        "titulo": {"type": "string"},
                        "empresa": {"type": "string"},
                        "ubicacion": {"type": "string"},
                        "url": {"type": "string", "description": "URL exacta vista en los resultados."},
                        "descripcion": {
                            "type": "string",
                            "description": "Requisitos y funciones de la oferta, según la fuente.",
                        },
                        "por_que_encaja": {"type": "string"},
                    },
                },
            },
        },
    },
}


def _cliente(api_key: str | None):
    import anthropic
    return anthropic.Anthropic(api_key=api_key or os.getenv("ANTHROPIC_API_KEY"))


def _urls_de_resultados(content) -> set:
    """URLs que la búsqueda web devolvió de verdad (para validar las reportadas)."""
    urls = set()
    for block in content:
        if block.type == "web_search_tool_result" and isinstance(block.content, list):
            urls.update(r.url for r in block.content if getattr(r, "url", None))
    return urls


def _norm_url(u: str) -> str:
    return u.strip().rstrip("/").split("#")[0].lower()


def buscar_vacantes(cv: str, ubicacion: str = "Colombia", cantidad: int = 8,
                    api_key: str | None = None) -> dict:
    """Busca en internet vacantes afines al CV.

    Retorna {"perfil_detectado": str, "vacantes": [ {titulo, empresa, ubicacion, url,
    descripcion, por_que_encaja, verificada} ], "consultas": [str]}.
    """
    client = _cliente(api_key)
    tools = [
        {
            "type": "web_search_20260209",
            "name": "web_search",
            "max_uses": 8,
            "user_location": {"type": "approximate", "country": "CO"}
            if ubicacion.strip().lower() in ("colombia", "bogota", "bogotá", "medellin", "medellín", "cali")
            else None,
        },
        HERRAMIENTA_REPORTE,
    ]
    if tools[0]["user_location"] is None:
        del tools[0]["user_location"]

    messages = [{
        "role": "user",
        "content": (
            f"Busca en internet {cantidad} ofertas de empleo reales y vigentes en {ubicacion} "
            f"que encajen con esta hoja de vida. Ten en cuenta el nivel de experiencia real "
            f"de la persona.\n\nHOJA DE VIDA:\n{cv}"
        ),
    }]

    urls_vistas, consultas = set(), []
    for _ in range(MAX_CONTINUACIONES + 1):
        response = client.beta.messages.create(
            model=MODEL,
            max_tokens=16000,
            system=SISTEMA,
            tools=tools,
            tool_choice={"type": "auto"},
            output_config={"effort": "medium"},
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            messages=messages,
        )
        urls_vistas |= _urls_de_resultados(response.content)
        consultas += [b.input.get("query", "") for b in response.content
                      if b.type == "server_tool_use" and b.name == "web_search"]

        if response.stop_reason == "refusal":
            raise RuntimeError("El modelo rechazó la solicitud.")

        reporte = next((b for b in response.content
                        if b.type == "tool_use" and b.name == "reportar_vacantes"), None)
        if reporte:
            datos = dict(reporte.input)
            vistas = {_norm_url(u) for u in urls_vistas}
            for v in datos["vacantes"]:
                v["verificada"] = _norm_url(v["url"]) in vistas
            datos["consultas"] = consultas
            return datos

        if response.stop_reason == "pause_turn":
            # El bucle de búsqueda del servidor se pausó: reenviar para que continúe.
            messages.append({"role": "assistant", "content": response.content})
            continue

        # Terminó sin llamar a la herramienta: pedírselo explícitamente.
        messages.append({"role": "assistant", "content": response.content})
        messages.append({"role": "user",
                         "content": "Ahora llama a `reportar_vacantes` con las ofertas que encontraste."})

    raise RuntimeError("La búsqueda no terminó tras varios intentos.")
