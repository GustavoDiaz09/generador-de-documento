"""Verificador: reabre el DOCX generado y valida el formato contra la plantilla."""
from __future__ import annotations

from pathlib import Path

from docx import Document
from docx.oxml.ns import qn


def verificar(archivo: str) -> list[str]:
    """Devuelve una lista de errores; vacia = todo correcto."""
    errores = []
    ruta = Path(archivo)
    if not ruta.exists():
        return [f"No existe el archivo: {ruta}"]

    doc = Document(str(ruta))

    if len(doc.tables) == 0:
        errores.append("El documento no contiene tablas.")
        return errores
    tabla = doc.tables[0]
    if len(tabla.rows) != 9:
        errores.append(f"La tabla debe tener 9 filas (tiene {len(tabla.rows)}).")

    secciones = [
        "DESCRIPCIÓN DEL TEXTO.", "PALABRAS CLAVES.", "OBJETIVOS DE LAS LECTURAS.",
        "CONCEPTOS CLAVES Y DEFINICIONES.", "RESUMEN DE LAS LECTURAS.",
        "METODOLOGÍA DE TRABAJO.", "CONCLUSIONES DE LA LECTURA.", "BIBLIOGRAFÍA.",
    ]
    for i, fila in enumerate(tabla.rows[1:], start=1):
        celda = fila.cells[0]
        titulo = (celda.paragraphs[0].text or "").strip()
        if titulo != secciones[i - 1]:
            errores.append(f"Fila {i}: titulo inesperado '{titulo}' (se esperaba "
                           f"'{secciones[i - 1]}').")
        contenido = "".join(p.text for p in celda.paragraphs[1:]).strip()
        if not contenido:
            errores.append(f"Fila {i} ({titulo}): sin contenido.")

    # Fila 0: bloque de titulo (unidad presente)
    titulo_bloque = "".join(p.text for p in tabla.rows[0].cells[0].paragraphs)
    if "Unidad" not in titulo_bloque and "°" not in titulo_bloque:
        errores.append("Fila 0: no se encontro la unidad en el bloque de titulo.")

    # OBJETIVOS debe conservar numeracion numId=7
    objetivos = tabla.rows[3].cells[0]._tc.findall(qn("w:p"))
    num_id = None
    for p in objetivos:
        numpr = p.find(qn("w:pPr"))
        if numpr is None:
            continue
        num = numpr.find(qn("w:numPr"))
        if num is not None:
            num_id = num.find(qn("w:numId"))
            break
    if num_id is None or num_id.get(qn("w:val")) != "7":
        errores.append("Fila 3 (OBJETIVOS): no conserva la numeracion numId=7.")

    # Header/footer con imagenes (marca de agua y strip)
    for parte, seccion in (("encabezado", doc.sections[0].header),
                           ("pie", doc.sections[0].footer)):
        xml = seccion._element.xml
        if "<w:drawing" not in xml and "blip" not in xml.lower():
            errores.append(f"{parte}: no contiene imagenes (marca de agua/strip).")

    return errores


def resumen_verificacion(errores: list[str]) -> str:
    if not errores:
        return "Verificacion OK: formato del DOCX identico a la plantilla."
    return "Errores encontrados:\n" + "\n".join(f"  - {e}" for e in errores)