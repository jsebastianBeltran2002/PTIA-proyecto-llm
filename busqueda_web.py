"""Búsqueda de vacantes REALES en internet con la herramienta web_search de Claude.

Flujo: CV -> Claude busca ofertas publicadas en la web -> reporta cada una con la
herramienta `reportar_vacantes` (esquema estricto) -> se verifica que cada URL haya
salido de un resultado real de búsqueda.
"""
import os
import re

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


PROMPT_CONSULTAS = """Analiza esta hoja de vida para buscar ofertas de empleo en {ubicacion}.
Ten en cuenta el nivel de experiencia real de la persona.

HOJA DE VIDA:
{cv}

Responde SOLO con JSON con esta forma exacta:
{{"perfil_detectado": "resumen en una frase del perfil profesional",
  "cargos": ["4 nombres de cargo cortos en español a los que puede aplicar, p. ej. 'analista de datos junior'"]}}"""

PROMPT_SELECCION = """Eres un reclutador. Abajo hay ofertas de empleo REALES (cada una con su enlace directo)
encontradas en portales de empleo, y una hoja de vida.
Elige hasta {cantidad} ofertas que encajen con la persona y que sean en {ubicacion} (o remotas para {ubicacion}).
Descarta ofertas de otros países (p. ej. enlaces cl.linkedin.com, pe.linkedin.com, mx.linkedin.com) y
cargos que no tengan relación con el perfil o exijan mucha más experiencia de la que tiene.
Usa SOLO la información del título y el fragmento: no inventes empresas ni requisitos.
Si la empresa no aparece, pon "No especificada".
En "titulo" pon solo el nombre limpio del cargo (p. ej. "Analista BI Junior"), sin textos del portal
como "Oferta de trabajo de", "Se necesita urgente", nombres de portales, fechas o cantidades.

HOJA DE VIDA:
{cv}

OFERTAS:
{resultados}

Responde SOLO con JSON con esta forma exacta:
{{"vacantes": [{{"indice": 0, "titulo": "...", "empresa": "...", "ubicacion": "...",
  "descripcion": "requisitos y funciones según el fragmento", "por_que_encaja": "una frase"}}]}}"""

# Portales y patrón de URL de una oferta INDIVIDUAL (no de un listado de resultados).
PORTALES = [
    ("Computrabajo", "co.computrabajo.com", re.compile(r"computrabajo\.com/ofertas-de-trabajo/oferta-de-trabajo-de-")),
    ("LinkedIn", "linkedin.com/jobs/view", re.compile(r"linkedin\.com/jobs/view/")),
    ("elempleo", "elempleo.com", re.compile(r"elempleo\.com/co/ofertas-trabajo/[^/?#]+-\d+")),
    ("Jooble", "co.jooble.org/desc", re.compile(r"jooble\.org/desc/\d+")),
    ("Indeed", "co.indeed.com", re.compile(r"indeed\.com/(viewjob|rc/clk)\?|indeed\.com/.*[?&]vjk=[0-9a-f]+")),
]


LIMITE_SEGUNDOS = 50  # tope para todas las búsquedas web juntas


def _url_directa(url: str) -> tuple[str, str] | None:
    """Si `url` es una oferta individual, devuelve (portal, url_directa); si es un listado, None."""
    if "bing.com/aclick" in url or "/aclick?" in url:
        return None  # anuncios
    for nombre, _, patron in PORTALES:
        if patron.search(url):
            if nombre == "Indeed":
                jk = re.search(r"[?&](?:vjk|jk)=([0-9a-f]+)", url)
                if not jk:
                    return None
                dominio = re.match(r"https?://[^/]+", url).group(0)
                return nombre, f"{dominio}/viewjob?jk={jk.group(1)}"
            return nombre, url.split("#")[0]
    return None


def _buscar_web_gratis(consulta: str, maximo: int = 10) -> list:
    """DuckDuckGo/Bing vía `ddgs` (gratis, sin clave). Devuelve [{title, href, body}]."""
    from ddgs import DDGS
    for backend in ("google", "bing"):
        try:
            res = DDGS(timeout=6).text(consulta, region="wt-wt", backend=backend, max_results=maximo)
            if res:
                return res
        except Exception:
            continue
    return []


def _buscar_vacantes_gemini(cv: str, ubicacion: str, cantidad: int, api_key: str | None) -> dict:
    from concurrent.futures import ThreadPoolExecutor, TimeoutError, as_completed
    import gemini_helper

    plan = gemini_helper.generar_json(PROMPT_CONSULTAS.format(cv=cv, ubicacion=ubicacion), api_key)
    if isinstance(plan, list):
        plan = plan[0] if plan and isinstance(plan[0], dict) else {}
    cargos = [c.strip() for c in plan.get("cargos", []) if isinstance(c, str) and c.strip()][:3]
    if not cargos:
        raise RuntimeError("No se pudieron deducir cargos a partir del CV.")

    # Una búsqueda por cargo y portal, en paralelo.
    consultas = [f"site:{sitio} {cargo} {ubicacion}" for cargo in cargos for _, sitio, _ in PORTALES]
    lotes = []
    ex = ThreadPoolExecutor(max_workers=8)
    futuros = [ex.submit(_buscar_web_gratis, c) for c in consultas]
    try:
        for f in as_completed(futuros, timeout=LIMITE_SEGUNDOS):
            lotes.append(f.result())
    except TimeoutError:
        pass  # se usan las búsquedas que alcanzaron a terminar
    finally:
        ex.shutdown(wait=False, cancel_futures=True)

    ofertas, vistos = [], set()
    for lote in lotes:
        for r in lote:
            directa = _url_directa(r.get("href", ""))
            if directa and _norm_url(directa[1]) not in vistos:
                vistos.add(_norm_url(directa[1]))
                ofertas.append({**r, "portal": directa[0], "href": directa[1]})
    if not ofertas:
        raise RuntimeError("No se encontraron ofertas individuales. Prueba otra ubicación o intenta de nuevo.")

    # Mezcla portales para que la IA vea variedad aunque haya muchas de uno solo.
    por_portal = {}
    for o in ofertas:
        por_portal.setdefault(o["portal"], []).append(o)
    mezcla = []
    while any(por_portal.values()) and len(mezcla) < 45:
        for lista in por_portal.values():
            if lista:
                mezcla.append(lista.pop(0))
    ofertas = mezcla

    listado = "\n".join(f"[{i}] ({o['portal']}) {o.get('title', '')}\nURL: {o['href']}\n{o.get('body', '')}"
                        for i, o in enumerate(ofertas))
    sel = gemini_helper.generar_json(PROMPT_SELECCION.format(
        cantidad=cantidad, ubicacion=ubicacion, cv=cv, resultados=listado), api_key)

    if isinstance(sel, dict):
        sel = sel.get("vacantes", [])
    vacantes, usados = [], set()
    for v in sel if isinstance(sel, list) else []:
        if not isinstance(v, dict):
            continue
        try:
            i = int(v["indice"])
            o = ofertas[i]
        except (KeyError, ValueError, TypeError, IndexError):
            continue  # índice inexistente: se descarta en vez de inventar
        if i in usados:
            continue
        usados.add(i)
        vacantes.append({
            "titulo": v.get("titulo") or o.get("title", ""),
            "empresa": v.get("empresa", ""),
            "ubicacion": v.get("ubicacion", ubicacion),
            "url": o["href"],  # enlace directo real, nunca escrito por el modelo
            "portal": o["portal"],
            "descripcion": v.get("descripcion") or o.get("body", ""),
            "por_que_encaja": v.get("por_que_encaja", ""),
            "verificada": True,
        })
    return {"perfil_detectado": plan.get("perfil_detectado", ""),
            "vacantes": vacantes[:cantidad], "consultas": consultas}


def buscar_vacantes(cv: str, ubicacion: str = "Colombia", cantidad: int = 8,
                    api_key: str | None = None, proveedor: str = "claude") -> dict:
    """Busca en internet vacantes afines al CV.

    proveedor="gemini": buscador gratuito (ddgs) + Gemini para elegir y estructurar.
    proveedor="claude": herramienta web_search de Claude.

    Retorna {"perfil_detectado": str, "vacantes": [ {titulo, empresa, ubicacion, url,
    descripcion, por_que_encaja, verificada} ], "consultas": [str]}.
    """
    if proveedor == "gemini":
        return _buscar_vacantes_gemini(cv, ubicacion, cantidad, api_key)
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
