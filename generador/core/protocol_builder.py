"""Ensamblador de protocolos: contenido estructurado (JSON) -> DOCX.

Tecnica de clonado: se copian parrafos existentes de cada celda (deepcopy
de los elementos <w:p>) y solo se sustituye el texto, heredando pPr/rPr
exactos (sangrias, tabs, negritas, numeracion numId=7) y los docDefaults
(Times New Roman 12 pt, interlineado 1.5, primera linea 284).

Todas las operaciones trabajan a nivel de lxml (elementos CT_P/CT_R), que
es lo que deepcopy clona de forma fiable.
"""
from __future__ import annotations

import copy
import re
import shutil
from pathlib import Path

from docx import Document
from docx.oxml.ns import qn

FILAS = {
    1: "DESCRIPCION DEL TEXTO",
    2: "PALABRAS CLAVES",
    3: "OBJETIVOS DE LAS LECTURAS",
    4: "CONCEPTOS CLAVES Y DEFINICIONES",
    5: "RESUMEN DE LAS LECTURAS",
    6: "METODOLOGIA DE TRABAJO",
    7: "CONCLUSIONES DE LA LECTURA",
    8: "BIBLIOGRAFIA",
}

_W_T = qn("w:t")
_W_R = qn("w:r")
_W_P = qn("w:p")
_W_RPR = qn("w:rPr")
_W_B = qn("w:b")


def _normaliza(texto: str) -> str:
    return texto.strip().upper()


def _ps(tc) -> list:
    """Elementos <w:p> de la celda."""
    return tc.findall(_W_P)


def _run_texto(r) -> str:
    return "".join(t.text or "" for t in r.findall(_W_T))


def _parrafo_texto(p) -> str:
    return "".join(_run_texto(r) for r in p.findall(_W_R))


def _parrafo_negrita(p) -> bool:
    for r in p.findall(_W_R):
        rpr = r.find(_W_RPR)
        if rpr is not None and rpr.find(_W_B) is not None:
            return True
    return False


def _set_run_texto(r, texto: str) -> None:
    """Reemplaza el w:t de un w:r forzando xml:space=\"preserve\"."""
    for t in r.findall(_W_T):
        r.remove(t)
    t = r.makeelement(_W_T, {qn("xml:space"): "preserve"})
    t.text = texto
    r.append(t)


def _set_parrafo_texto(p, texto: str) -> None:
    """Deja un solo run (conserva su rPr) con el texto dado."""
    runs = p.findall(_W_R)
    for r in runs[1:]:
        p.remove(r)
    if not runs:
        r = p.makeelement(_W_R, {})
        p.append(r)
        runs = [r]
    _set_run_texto(runs[0], texto)


def _set_parrafo_termdef(p, termino: str, definicion: str) -> None:
    """run[0] = termino en negrita con ':'; run[-1] = definicion normal.

    Los runs intermedios se eliminan salvo que contengan un <w:tab>
    real entre termino y definicion.
    """
    runs = p.findall(_W_R)
    if not runs:
        return
    _W_TAB = qn("w:tab")
    for r in runs[1:-1]:
        if r.find(_W_TAB) is None:
            p.remove(r)
    runs = p.findall(_W_R)
    _set_run_texto(runs[0], f"{termino}:")
    if len(runs) > 1:
        _set_run_texto(runs[-1], definicion)
    else:
        _set_run_texto(runs[0], f"{termino}: {definicion}")


def _modelos(nueva_celda, titulo: str):
    """Devuelve (modelo_parrafo, modelo_subtitulo) segun el tipo de celda."""
    ps = _ps(nueva_celda)[1:]
    if titulo == _normaliza(FILAS[5]):  # RESUMEN
        subs = [p for p in ps if _parrafo_negrita(p)]
        normales = [p for p in ps if not _parrafo_negrita(p)]
        sub = subs[0] if subs else None
        texto = normales[0] if normales else (subs[0] if subs else None)
        return texto, sub
    return (ps[0] if ps else None), None


def _clear_content(nueva_celda) -> None:
    ps = _ps(nueva_celda)
    for p in ps[1:]:
        nueva_celda.remove(p)


def _rellenar(nueva_celda, titulo: str, items, modo: str) -> None:
    """Rellena una celda clonando el modelo por cada item.

    modo: "texto", "objetivos", "conceptos" o "resumen".
    """
    modelo, modelo_sub = _modelos(nueva_celda, titulo)
    if modelo is None:
        raise ValueError(f"La celda '{titulo}' no tiene parrafos modelo.")

    nuevos = []

    if modo == "texto":
        p = copy.deepcopy(modelo)
        _set_parrafo_texto(p, items)
        nuevos.append(p)

    elif modo == "objetivos":
        for obj in items:
            p = copy.deepcopy(modelo)
            _set_parrafo_texto(p, obj)
            nuevos.append(p)

    elif modo == "conceptos":
        for item in items:
            p = copy.deepcopy(modelo)
            _set_parrafo_termdef(p, item["termino"], item["definicion"])
            nuevos.append(p)

    elif modo == "resumen":
        for i, seccion in enumerate(items):
            if modelo_sub is not None:
                p = copy.deepcopy(modelo_sub)
                _set_parrafo_texto(p, seccion["subtitulo"])
                nuevos.append(p)
            for para in seccion["parrafos"]:
                p = copy.deepcopy(modelo)
                _set_parrafo_texto(p, para)
                nuevos.append(p)
            if i < len(items) - 1:
                vacio = copy.deepcopy(modelo)
                _set_parrafo_texto(vacio, "")
                nuevos.append(vacio)

    _clear_content(nueva_celda)
    titulo_p = _ps(nueva_celda)[0]
    for el in reversed(nuevos):
        titulo_p.addnext(el)


def _cambiar_unidad(nueva_celda, unidad: int) -> None:
    """Fila 0: sustituye el numero de unidad en el bloque de titulo."""
    for p in _ps(nueva_celda):
        for r in p.findall(_W_R):
            texto = _run_texto(r)
            if "1°" in texto or "2°" in texto:
                _set_run_texto(r, re.sub(r"[12]°", f"{unidad}°", texto, count=1))
                return


def validar_contenido(contenido: dict) -> None:
    """Valida el esquema minimo antes de ensamblar. Lanza ValueError."""
    obligatorias = [
        "descripcion", "palabras_claves", "objetivos", "conceptos",
        "resumen", "conclusiones", "bibliografia",
    ]
    faltantes = [k for k in obligatorias if k not in contenido]
    if faltantes:
        raise ValueError(f"Faltan campos en el contenido: {', '.join(faltantes)}")
    if not isinstance(contenido["objetivos"], list) or not contenido["objetivos"]:
        raise ValueError("'objetivos' debe ser una lista no vacia.")
    if not isinstance(contenido["conceptos"], list) or not contenido["conceptos"]:
        raise ValueError("'conceptos' debe ser una lista no vacia.")
    if not isinstance(contenido["resumen"], list) or not contenido["resumen"]:
        raise ValueError("'resumen' debe ser una lista no vacia.")


def build_protocol(plantilla: str, contenido: dict, salida: str, unidad: int) -> str:
    """Genera el DOCX final sobre una copia de la plantilla."""
    plantilla = Path(plantilla)
    salida = Path(salida)
    salida.parent.mkdir(parents=True, exist_ok=True)

    validar_contenido(contenido)

    shutil.copyfile(plantilla, salida)
    doc = Document(str(salida))

    tabla = doc.tables[0]
    if len(tabla.rows) != 9:
        raise ValueError(f"La plantilla no tiene 9 filas (tiene {len(tabla.rows)}).")

    def celda(n):
        return tabla.rows[n].cells[0]._tc

    _cambiar_unidad(celda(0), unidad)

    _rellenar(celda(1), _normaliza(FILAS[1]), contenido["descripcion"], "texto")
    _rellenar(celda(2), _normaliza(FILAS[2]), contenido["palabras_claves"], "texto")
    _rellenar(celda(3), _normaliza(FILAS[3]), contenido["objetivos"], "objetivos")
    _rellenar(celda(4), _normaliza(FILAS[4]), contenido["conceptos"], "conceptos")
    _rellenar(celda(5), _normaliza(FILAS[5]), contenido["resumen"], "resumen")
    # Fila 6 (METODOLOGIA) se copia tal cual, sin tocar.

    _rellenar(celda(7), _normaliza(FILAS[7]), contenido["conclusiones"], "texto")
    _rellenar(celda(8), _normaliza(FILAS[8]), contenido["bibliografia"], "texto")

    doc.save(str(salida))
    return str(salida)