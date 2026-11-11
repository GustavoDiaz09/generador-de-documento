"""Esquema del contenido del protocolo: fuente unica de verdad.

Lo usan la IA (ia_client), el formulario manual y el ensamblador
(protocol_builder). Si cambias una cardinalidad o un campo, cambialo aqui.
"""
from __future__ import annotations

ESQUEMA_REQUERIDO = [
    "descripcion",
    "palabras_claves",
    "objetivos",
    "conceptos",
    "resumen",
    "conclusiones",
    "bibliografia",
]

N_OBJETIVOS = 3
CONCEPTOS_MIN = 8
CONCEPTOS_MAX = 12
N_SECCIONES_RESUMEN = 3
CAMPOS_NO_VACIOS = ("descripcion", "palabras_claves", "conclusiones")


def errores_contenido(contenido: dict) -> list[str]:
    """Lista de errores de estructura y cardinalidad (vacia = valido)."""
    faltantes = [k for k in ESQUEMA_REQUERIDO if k not in contenido]
    if faltantes:
        return [f"Faltan campos: {', '.join(faltantes)}"]

    errores: list[str] = []
    for campo in CAMPOS_NO_VACIOS:
        if not str(contenido[campo]).strip():
            errores.append(f"'{campo}' no puede estar vacío.")

    objetivos = contenido["objetivos"]
    if not isinstance(objetivos, list) or len(objetivos) != N_OBJETIVOS:
        n = len(objetivos) if isinstance(objetivos, list) else 0
        errores.append(f"'objetivos' debe tener exactamente {N_OBJETIVOS} elementos (tiene {n}).")

    conceptos = contenido["conceptos"]
    if not isinstance(conceptos, list) or not CONCEPTOS_MIN <= len(conceptos) <= CONCEPTOS_MAX:
        n = len(conceptos) if isinstance(conceptos, list) else 0
        errores.append(f"'conceptos' debe tener {CONCEPTOS_MIN}-{CONCEPTOS_MAX} elementos (tiene {n}).")
    elif not all(isinstance(c, dict) and str(c.get("termino", "")).strip()
                 and str(c.get("definicion", "")).strip() for c in conceptos):
        errores.append("Cada concepto necesita término y definición.")

    resumen = contenido["resumen"]
    if not isinstance(resumen, list) or len(resumen) != N_SECCIONES_RESUMEN:
        n = len(resumen) if isinstance(resumen, list) else 0
        errores.append(f"'resumen' debe tener exactamente {N_SECCIONES_RESUMEN} secciones (tiene {n}).")
    elif not all(isinstance(s, dict) and str(s.get("subtitulo", "")).strip()
                 and s.get("parrafos") for s in resumen):
        errores.append("Cada sección del resumen necesita subtítulo y al menos un párrafo.")

    return errores
