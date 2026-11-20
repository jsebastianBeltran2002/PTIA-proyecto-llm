"""Acceso a Google Gemini (plan gratuito) para generar texto y JSON.

La clave se crea gratis en https://aistudio.google.com/apikey (sin tarjeta).
El modelo se elige solo: el "flash" estable más reciente disponible para la clave,
o el que indique la variable de entorno GEMINI_MODEL.
"""
import json
import os
import re
from functools import lru_cache

MODELO_RESPALDO = "gemini-2.5-flash"


def _clave(api_key: str | None) -> str:
    clave = (api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or "").strip()
    if not clave:
        raise RuntimeError("Falta la API key de Gemini (créala gratis en aistudio.google.com/apikey).")
    return clave


TIEMPO_MAXIMO_MS = 40_000  # por llamada; si se pasa, se prueba con un modelo más liviano


@lru_cache(maxsize=4)
def _cliente_para(clave: str):
    # El cliente se guarda (no se crea y descarta en cada llamada): si se recolecta como
    # basura, google-genai cierra su conexión y falla con "the client has been closed".
    # Sin reintentos internos: en el plan gratuito pueden alargar una llamada a minutos;
    # en su lugar se cambia de modelo (ver generar()).
    from google import genai
    from google.genai import types
    return genai.Client(api_key=clave, http_options=types.HttpOptions(
        timeout=TIEMPO_MAXIMO_MS, retry_options=types.HttpRetryOptions(attempts=1)))


def _cliente(api_key: str | None):
    return _cliente_para(_clave(api_key))


@lru_cache(maxsize=4)
def modelos(api_key: str | None = None) -> tuple:
    """Cadena de modelos a probar: primero el Flash-Lite más reciente (el más rápido y estable en el
    plan gratuito) y luego los dos Flash más recientes como respaldo."""
    if os.getenv("GEMINI_MODEL"):
        return (os.environ["GEMINI_MODEL"],)
    flash, lite = [], []
    try:
        for m in _cliente(api_key).models.list():
            nombre = (m.name or "").removeprefix("models/")
            acciones = m.supported_actions or []
            if acciones and "generateContent" not in acciones:
                continue
            if mt := re.fullmatch(r"gemini-(\d+(?:\.\d+)?)-flash", nombre):
                flash.append((float(mt.group(1)), nombre))
            elif mt := re.fullmatch(r"gemini-(\d+(?:\.\d+)?)-flash-lite", nombre):
                lite.append((float(mt.group(1)), nombre))
    except Exception:
        pass
    cadena = [n for _, n in sorted(lite, reverse=True)[:1]] + [n for _, n in sorted(flash, reverse=True)[:2]]
    return tuple(cadena) or (MODELO_RESPALDO,)


def modelo(api_key: str | None = None) -> str:
    return modelos(api_key)[0]


def _mensaje_error(e: Exception) -> str:
    texto = str(e)
    if "429" in texto or "RESOURCE_EXHAUSTED" in texto:
        return "Se agotó la cuota gratuita de Gemini por ahora. Espera un minuto (o hasta mañana) y reintenta."
    if "API_KEY_INVALID" in texto or "API key not valid" in texto:
        return "La API key de Gemini no es válida. Revísala en aistudio.google.com/apikey."
    if "timed out" in texto.lower() or "timeout" in texto.lower():
        return "Gemini está tardando demasiado en este momento (plan gratuito saturado). Intenta en unos minutos."
    return f"Error de Gemini: {texto[:300]}"


def _es_definitivo(e: Exception) -> bool:
    """Errores que no se arreglan cambiando de modelo (p. ej. clave inválida)."""
    t = str(e)
    return "API_KEY_INVALID" in t or "API key not valid" in t or "PERMISSION_DENIED" in t


def generar(prompt: str, api_key: str | None = None, json_salida: bool = False,
            pensamiento: str = "low") -> str:
    """Genera texto. `pensamiento` = nivel de razonamiento ("low" es más rápido, "medium" más cuidadoso)."""
    from google.genai import types
    nivel = {"low": types.ThinkingLevel.LOW, "medium": types.ThinkingLevel.MEDIUM}[pensamiento]
    cliente = _cliente(api_key)
    ultimo_error = None
    for nombre in modelos(api_key):
        config = types.GenerateContentConfig(
            response_mime_type="application/json" if json_salida else "text/plain",
            max_output_tokens=16000,
            thinking_config=types.ThinkingConfig(thinking_level=nivel),
        )
        try:
            resp = cliente.models.generate_content(model=nombre, contents=prompt, config=config)
        except Exception as e:
            if _es_definitivo(e):
                raise RuntimeError(_mensaje_error(e)) from e
            ultimo_error = e
            continue  # lento, sin cuota o no disponible: probar el siguiente modelo
        texto = resp.text or ""
        if texto.strip():
            return texto
        ultimo_error = RuntimeError("respuesta vacía")
    if isinstance(ultimo_error, RuntimeError) and str(ultimo_error) == "respuesta vacía":
        raise RuntimeError("Gemini no devolvió respuesta (posible bloqueo por filtros de seguridad).")
    raise RuntimeError(_mensaje_error(ultimo_error)) from ultimo_error


def generar_json(prompt: str, api_key: str | None = None):
    texto = generar(prompt, api_key, json_salida=True).strip()
    texto = re.sub(r"^```(?:json)?\s*|\s*```$", "", texto)  # por si llega envuelto en ```json
    try:
        return json.loads(texto)
    except json.JSONDecodeError as e:
        raise RuntimeError("Gemini devolvió un JSON inválido; vuelve a intentar.") from e
