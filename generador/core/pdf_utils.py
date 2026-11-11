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


def extraer_pdf(path: str, avisos: list[str] | None = None) -> str:
    """Concatena el texto de todas las paginas del PDF.

    Si una pagina no se puede leer se anade un aviso a `avisos` (si se pasa)
    en vez de descartarla en silencio.
    """
    try:
        reader = PdfReader(path)
    except Exception as e:
        raise ValueError(f"No se pudo abrir el PDF: {e}") from e
    partes = []
    for n, pagina in enumerate(reader.pages, start=1):
        try:
            texto = pagina.extract_text() or ""
        except Exception as e:
            texto = ""
            if avisos is not None:
                avisos.append(f"Página {n} no se pudo leer: {e}")
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
            # Acepta formato APA "Autor (2019)" y "Autor 2019"; antes exigia letra pegada al año.
            if re.search(r"\b(?:19|20)\d{2}\b", limpia) or "://" in limpia:
                resultado.append(limpia)
    return resultado


def extraer_texto(path: str, tesseract_path: str | None = None,
                  avisos: list[str] | None = None) -> tuple[str, bool]:
    """Extrae texto con OCR de respaldo si es necesario.

    Devuelve (texto, usado_ocr). Los problemas no fatales (paginas ilegibles,
    OCR no disponible) se describen en `avisos` si se pasa la lista.
    """
    texto = extraer_pdf(path, avisos)
    if texto_probablemente_inutil(texto):
        try:
            return ocr_pdf(path, tesseract_path), True
        except Exception as e:
            if avisos is not None:
                avisos.append(
                    f"El PDF parece escaneado y el OCR falló ({e}). "
                    "Se usa el texto nativo, que puede estar vacío.")
    return texto, False