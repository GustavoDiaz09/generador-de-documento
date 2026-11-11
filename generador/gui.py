"""Lanzador de la interfaz del generador de protocolos.

La interfaz es web (HTML/CSS/JS en generador/web/) y se muestra en una
ventana propia con pywebview (WebView2). La logica vive en api.py y core/.
Este modulo solo crea la ventana; run_generador.py lo invoca.
"""
from __future__ import annotations

import sys
from pathlib import Path

import webview

BASE = Path(__file__).resolve().parent
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))

from api import Api  # noqa: E402

WEB = BASE / "web" / "index.html"
ICONO = BASE / "assets" / "iapp.ico"


def main() -> None:
    api = Api()
    ventana = webview.create_window(
        "Generador de Protocolos — Diseño De Sitio Web",
        url=str(WEB),
        js_api=api,
        width=1120,
        height=800,
        min_size=(900, 640),
        background_color="#F4F5FB",
        text_select=True,
    )
    api._vincular(ventana)
    icono = str(ICONO) if ICONO.exists() else None
    webview.start(gui="edgechromium", icon=icono)


if __name__ == "__main__":
    main()
