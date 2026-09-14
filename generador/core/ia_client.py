"""Cliente IA (OpenAI y compatibles / OpenRouter / Groq / Gemini): redaccion del contenido."""
from __future__ import annotations

import json
import os
import re
import time
from collections.abc import Callable

from openai import OpenAI

URLS = {
    "openai": "https://api.openai.com/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "groq": "https://api.groq.com/openai/v1",
    "google": "https://generativelanguage.googleapis.com/v1beta/openai/",
}

# Variables de entorno por proveedor (primer valor = preferida)
ENV_CLAVE = {
    "openai": ["OPENAI_API_KEY"],
    "openrouter": ["OPENROUTER_API_KEY"],
    "groq": ["GROQ_API_KEY"],
    "google": ["GEMINI_API_KEY", "GOOGLE_API_KEY", "GOOGLE_AI_STUDIO_KEY"],
}

MODELO_POR_DEFECTO = {
    "openai": "gpt-4o-mini",
    "openrouter": "gpt-4o-mini",
    "groq": "llama-3.3-70b-versatile",
    "google": "gemini-3.6-flash",
}

ESQUEMA_REQUERIDO = [
    "descripcion",
    "palabras_claves",
    "objetivos",
    "conceptos",
    "resumen",
    "conclusiones",
    "bibliografia",
]

PROGRESO = Callable[[str], None]


class ErrorSinClave(Exception):
    pass


def _clave_env(proveedor: str) -> str | None:
    for var in ENV_CLAVE.get(proveedor, []):
        valor = os.environ.get(var)
        if valor:
            return valor
    return None


def _proveedor_por_url(base_url: str | None) -> str | None:
    if not base_url:
        return None
    for nombre, url in URLS.items():
        if base_url.startswith(url):
            return nombre
    return None


def resolver_credenciales(
    proveedor: str | None = None,
    *,
    base_url: str | None = None,
    modelo: str | None = None,
) -> tuple[str | None, str, str]:
    """Devuelve (clave_de_entorno_o_None, base_url, modelo).

    - proveedor: None/"auto" elige el primero con clave en el entorno
      (OpenRouter, OpenAI, Groq, Gemini).
    - base_url explicito gana a la URL del proveedor (para proveedores
      personalizados).
    - No lanza por clave ausente: eso lo decide quien la llama (la clave
      tambien puede venir explicita).
    """
    if proveedor in (None, "", "auto"):
        for nombre in ("openrouter", "openai", "groq", "google"):
            clave = _clave_env(nombre)
            if clave:
                proveedor = nombre
                break
    if proveedor not in (None,) and proveedor not in URLS:
        proveedor = "openai"  # proveedor desconocido -> endpoint OpenAI por defecto

    base = base_url or URLS.get(proveedor, URLS["openai"])
    clave = _clave_env(proveedor) if proveedor else None
    modelo_final = (
        modelo
        or os.environ.get("PROTOCOLO_MODELO")
        or MODELO_POR_DEFECTO.get(proveedor, "gpt-4o-mini")
    )
    return clave, base, modelo_final


def _extract_campos(p: dict) -> str:
    return ", ".join(sorted(k for k in p if p[k] not in (None, "", [], {})))


def _texto_plantilla_referencia(path_plantilla: str) -> str:
    """Texto legible del protocolo de la 1a Unidad como muestra de estilo."""
    try:
        from docx import Document

        doc = Document(path_plantilla)
        partes = []
        for tabla in doc.tables:
            for fila in tabla.rows:
                for celda in fila.cells:
                    for para in celda.paragraphs:
                        if para.text.strip():
                            partes.append(para.text.strip())
        cuerpo = "\n".join(partes)
        return cuerpo if cuerpo.strip() else ""
    except Exception:
        return ""


def _prompt_sistema(path_plantilla: str) -> str:
    referencia = _texto_plantilla_referencia(path_plantilla)
    ref_bloque = (
        "\n\nProtocolo de la 1a Unidad (muestra de tono, estructura y "
        f"vocabulario; imitalo):\n{referencia}"
        if referencia
        else ""
    )
    return (
        "Eres un redactor academico universitario en espanol, encargado de "
        "redactar Protocolos Individuales de la asignatura Diseño De Sitio Web. "
        "Reglas: redacta parrafos fluidos de 90-180 palabras; usa la "
        "terminologia exacta del modulo; NO inventes datos ni temas que no "
        "aparezcan en el texto recibido; la 'descripcion' debe comenzar "
        "literalmente con 'El siguiente protocolo trata sobre'; responde SOLO "
        "un JSON valido, sin markdown, sin comentarios ni texto fuera del JSON."
        f"{ref_bloque}"
    )


def _prompt_usuario(texto: str, unidad: int, biblio: list[str],
                    feedback: str = "") -> str:
    biblio_bloque = "\n".join(f"- {b}" for b in biblio) if biblio else "(No se detecto.)"
    esquema = (
        "Genera el JSON del protocolo con este esquema exacto:\n"
        "{\n"
        '  "descripcion": "string OBLIGATORIA: empieza literalmente con \'El '
        'siguiente protocolo trata sobre\' (90-180 palabras)",\n'
        '  "palabras_claves": "string separada por comas (unas 10 palabras)",\n'
        '  "objetivos": ["string", "string", "string"] (exactamente 3),\n'
        '  "conceptos": [{"termino": "string", "definicion": "string"}] '
        "(8-12 elementos),\n"
        '  "resumen": [{"subtitulo": "string", "parrafos": ["string", ...]}] '
        "(exactamente 3 secciones, 1-3 parrafos cada una),\n"
        '  "conclusiones": "string",\n'
        '  "bibliografia": "string" (maximo 5 fuentes, formato '
        'Autor (Año). Título; prioriza las detectadas)\n'
        "}"
    )
    base = (
        f"Unidad {unidad} (modulo: Modulo {unidad}.pdf).\n\n"
        "Texto del modulo:\n"
        f"{texto}\n\n"
        "Bibliografia detectada en el modulo:\n"
        f"{biblio_bloque}\n\n"
        f"{esquema}"
    )
    if feedback:
        base += (
            "\n\nTu respuesta anterior fue rechazada por este motivo:\n"
            f"{feedback}\n"
            "Corrige solo eso y devuelve el JSON COMPLETO, sin truncar, "
            "terminado con llave de cierre."
        )
    return base


def parse_json(resp: str | None) -> dict:
    """Limpia fences y devuelve el dict; lanza ValueError si no es JSON."""
    texto = (resp or "").strip()
    texto = re.sub(r"^```(?:json)?\s*", "", texto).strip()
    texto = re.sub(r"```\s*$", "", texto).strip()
    return json.loads(texto)


def _recortar_bibliografia(contenido: dict) -> dict:
    biblio = contenido.get("bibliografia", "")
    if isinstance(biblio, str):
        items = [b.strip() for b in re.split(r"[\n;]+", biblio) if b.strip()]
        if len(items) > 5:
            contenido["bibliografia"] = "\n".join(_solo_fuente(i) for i in items[:5])
        else:
            contenido["bibliografia"] = "\n".join(_solo_fuente(i) for i in items)
    return contenido


def _solo_fuente(entrada: str) -> str:
    return re.sub(r"\b(?:https?|ftp)://[^\s)]+", "", entrada).strip().rstrip(",").strip()


def validar_esquema(contenido: dict) -> list[str]:
    """Devuelve errores de cardinalidad/estructura (lista vacia si todo OK)."""
    errores = []
    faltantes = [k for k in ESQUEMA_REQUERIDO if k not in contenido]
    if faltantes:
        return [f"Faltan campos: {', '.join(faltantes)}"]

    if not isinstance(contenido["objetivos"], list) or len(contenido["objetivos"]) != 3:
        errores.append("'objetivos' debe tener exactamente 3 elementos.")
    if not isinstance(contenido["conceptos"], list) or not 8 <= len(contenido["conceptos"]) <= 12:
        errores.append(f"'conceptos' debe tener 8-12 elementos (tiene "
                       f"{len(contenido['conceptos'])}).")
    if not isinstance(contenido["resumen"], list) or len(contenido["resumen"]) != 3:
        errores.append("'resumen' debe tener exactamente 3 secciones.")
    return errores


def _llamar(client: OpenAI, modelo: str, texto: str, biblio: list[str],
            unidad: int, path_plantilla: str, json_mode: bool = True,
            max_tokens: int = 8192, feedback: str = "") -> str:
    kwargs = dict(
        model=modelo,
        messages=[
            {"role": "system", "content": _prompt_sistema(path_plantilla)},
            {"role": "user", "content": _prompt_usuario(texto, unidad, biblio, feedback)},
        ],
        temperature=0.3,
        max_tokens=max_tokens,
    )
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    try:
        respuesta = client.chat.completions.create(**kwargs)
        return respuesta.choices[0].message.content
    except Exception as e:
        if json_mode and "response_format" not in str(e) and "400" in str(e):
            # algunos proveedores gratuitos rechazan response_format
            return _llamar(client, modelo, texto, biblio, unidad,
                           path_plantilla, json_mode=False,
                           max_tokens=max_tokens, feedback=feedback)
        raise e


def redactar_contenido(
    texto: str,
    unidad: int,
    biblio: list[str] | None = None,
    *,
    proveedor: str | None = None,
    modelo: str | None = None,
    clave: str | None = None,
    base_url: str | None = None,
    path_plantilla: str = "",
    progreso: PROGRESO | None = None,
) -> dict:
    """Redacta el JSON del protocolo con la IA y lo valida/ajusta.

    - Reintentos: 2 para fallos de red/API con backoff; 1 con feedback del
      error si el JSON es invalido.
    """
    biblio = biblio or []
    clave_env, base, modelo_env = resolver_credenciales(
        proveedor, base_url=base_url, modelo=modelo)
    clave = clave or clave_env
    modelo = modelo or modelo_env
    base = base_url or base
    if not clave:
        raise ErrorSinClave(
            f"No hay clave de API configurada para el proveedor "
            f"'{proveedor or 'auto'}'. Pégala en la pestaña 3 (y guárdala con "
            "'Recordar clave'), o define la variable de entorno correspondiente."
        )

    client = OpenAI(api_key=clave, base_url=base)
    errores_red = 0
    json_invalido = False
    feedback_json = ""
    fallback_modelo = False

    cliente_url = base_url or base
    modelo_original = (MODELO_POR_DEFECTO.get(_proveedor_por_url(cliente_url))
                       or None)

    while True:
        tokens = 8192
        try:
            if progreso:
                progreso(f"Llamando a la IA ({modelo})...")
            contenido_raw = _llamar(client, modelo, texto, biblio, unidad,
                                    path_plantilla, max_tokens=tokens,
                                    feedback=feedback_json)
        except Exception as e:
            status = getattr(e, "status_code", None) or getattr(
                e, "status", None)
            nombre_modelo = getattr(e, "model", None)
            if (status == 404 and not fallback_modelo
                    and ("model" in (str(nombre_modelo) + str(e)).lower())
                    and modelo_original and modelo != modelo_original):
                fallback_modelo = True
                modelo = modelo_original
                if progreso:
                    progreso(f"Modelo no disponible (404). Reintentando con {modelo}...")
                continue
            errores_red += 1
            if errores_red < 3:
                espera = 2 ** errores_red
                if progreso:
                    progreso(f"Fallo de red/API ({e}). Reintento en {espera}s...")
                time.sleep(espera)
                continue
            raise

        try:
            contenido = parse_json(contenido_raw)
        except Exception as e:
            if not json_invalido:
                json_invalido = True
                feedback_json = str(e)
                if progreso:
                    progreso("JSON invalido. Reintentando con feedback...")
                continue
            raise ValueError(f"La IA no devolvio JSON valido: {e}") from e

        errores = validar_esquema(contenido)
        if errores:
            if not json_invalido:
                json_invalido = True
                feedback_json = " | ".join(errores)
                if progreso:
                    progreso("Esquema invalido. Reintentando con feedback...")
                continue
            # aun con feedback falla: ajustamos aqui y seguimos
            contenido = ajustar_contenido(contenido)
            break
        break

    contenido = _recortar_bibliografia(contenido)
    if progreso:
        progreso(f"Contenido listo ({_extract_campos(contenido)}).")
    return contenido


def ajustar_contenido(contenido: dict) -> dict:
    """Trunca/ajusta silenciosamente para cumplir la cardinalidad."""
    contenido = dict(contenido)
    obj = contenido.get("objetivos")
    if isinstance(obj, list):
        contenido["objetivos"] = obj[:3]
    conc = contenido.get("conceptos")
    if isinstance(conc, list):
        contenido["conceptos"] = conc[:12]
    res = contenido.get("resumen")
    if isinstance(res, list):
        contenido["resumen"] = res[:3]
    return contenido