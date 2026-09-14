"""Utilidades PDF: extraccion de texto, deduccion de unidad, bibliografia y OCR."""
from __future__ import annotations

import re
from pathlib import Path

from pypdf import PdfReader

UMBRAL_MIN_CARACTERES = 300
ENCABEZADOS_BIBLIO = re.compile(
    r"^\s*(bibliograf[ií]a|referencias|bibliography|references)\s*[:.]?\s*$",
    re.IGNORECASE,
)
PATRON_UNIDAD = re.compile(r"modulo\s*(\d+)\.pdf", re.IGNORECASE)


def deducir_unidad(fichero: str) -> int | None:
    """Regla 'Modulo N.pdf' -> N (case-insensitive, tolera espacios)."""
    m = PATRON_UNIDAD.search(Path(fichero).name)
    return int(m.group(1)) if m else None


def extraer_pdf(path: str) -> str:
    """Concatena el texto de todas las paginas del PDF."""
    try:
        reader = PdfReader(path)
    except Exception as e:
        raise ValueError(f"No se pudo abrir el PDF: {e}") from e
    partes = []
    for pagina in reader.pages:
        try:
            texto = pagina.extract_text() or ""
        except Exception:
            texto = ""
        partes.append(texto)
    return "\n".join(partes)


def ocr_pdf(path: str, tesseract_path: str | None = None) -> str:
    """Fallback OCR pagina a pagina con pytesseract."""
    import pytesseract  # import tardio: dependencia opcional

    if tesseract_path:
        pytesseract.pytesseract.tesseract_cmd = tesseract_path
    partes = []
    try:
        from pdf2image import convert_from_path

        imagenes = convert_from_path(path, dpi=200)
        for img in imagenes:
            partes.append(pytesseract.image_to_string(img))
    except ImportError:
        from PIL import Image
        from io import BytesIO

        reader = PdfReader(path)
        for pagina in reader.pages:
            if pagina.images:
                img = Image.open(BytesIO(pagina.images[0].data))
                partes.append(pytesseract.image_to_string(img))
    return "\n".join(partes)


def texto_probablemente_inutil(texto: str) -> bool:
    """True si el texto extraido es casi vacio (posible PDF escaneado)."""
    return len(texto.strip()) < UMBRAL_MIN_CARACTERES


def extraer_bibliografia(texto: str) -> list[str]:
    """Heuristica: bloque tras encabezado 'Bibliografia/Referencias/...'."""
    lineas = texto.splitlines()
    resultado: list[str] = []
    en_biblio = False
    for linea in lineas:
        limpia = linea.strip()
        if not limpia:
            if en_biblio:
                break
            continue
        if ENCABEZADOS_BIBLIO.match(limpia):
            en_biblio = True
            continue
        if en_biblio:
            if any(enc in limpia.lower() for enc in ("bibliograf", "index", "contenido")):
                continue
            if re.search(r"[A-Za-z]\s*\d{4}", limpia) or "://" in limpia:
                resultado.append(limpia)
    return resultado


def extraer_texto(path: str, tesseract_path: str | None = None) -> tuple[str, bool]:
    """Extrae texto con OCR de respaldo si es necesario.

    Devuelve (texto, usado_ocr).
    """
    texto = extraer_pdf(path)
    if texto_probablemente_inutil(texto):
        try:
            return ocr_pdf(path, tesseract_path), True
        except Exception:
            pass
    return texto, False