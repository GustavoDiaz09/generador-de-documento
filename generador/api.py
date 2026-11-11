"""API expuesta a la interfaz web (pywebview).

La interfaz (generador/web/) llama a los metodos de Api mediante
window.pywebview.api. Las operaciones lentas (extraccion, IA, generacion)
corren en hilos y avisan a la pagina con eventos (window.appEvento).

Toda la logica de negocio vive en core/; este modulo solo la conecta.
"""
from __future__ import annotations

import json
import os
import re
import sys
import threading
from pathlib import Path

import webview

BASE = Path(__file__).resolve().parent
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))

from core import ia_client, pdf_utils, protocol_builder, verificador  # noqa: E402
from core.esquema import errores_contenido  # noqa: E402

PLANTILLA = BASE / "plantilla" / "Protocolo_Plantilla.docx"
SALIDA = BASE / "salida"
CONFIG_IA = BASE / ".config_ia.json"
PREF_UI = BASE / ".ui.json"
NOMBRE_ESTUDIANTE = "Gustavo Alonso Díaz Mercado"
PROVEEDORES = ["auto", "openai", "openrouter", "groq", "google", "personalizado"]
TEMAS = ("claro", "oscuro")


def _leer_json(ruta: Path, por_defecto):
    try:
        return json.loads(ruta.read_text(encoding="utf-8"))
    except Exception:
        return por_defecto


def _escribir_json(ruta: Path, datos) -> None:
    ruta.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")


def _nombre_seguro(nombre: str) -> str:
    nombre = re.sub(r'[\\/:*?"<>|]', " ", nombre).strip()
    return nombre or "Protocolo.docx"


def _primer_valor(valor):
    """create_file_dialog devuelve lista o None; normalizamos a str o None."""
    if not valor:
        return None
    return valor[0] if isinstance(valor, (list, tuple)) else valor


class Api:
    def __init__(self):
        self._window = None
        self._texto = ""

    def _vincular(self, window) -> None:
        self._window = window

    # ---------- eventos hacia la pagina ----------
    def _emitir(self, tipo: str, **datos) -> None:
        if self._window is None:
            return
        payload = json.dumps({"tipo": tipo, **datos}, ensure_ascii=False)
        try:
            self._window.evaluate_js(f"window.appEvento && window.appEvento({payload})")
        except Exception:
            pass  # la ventana pudo cerrarse mientras trabajaba un hilo

    def _log(self, mensaje: str, nivel: str = "info") -> None:
        self._emitir("log", mensaje=mensaje, nivel=nivel)

    # ---------- arranque y preferencias ----------
    def inicio(self) -> dict:
        prefs = _leer_json(PREF_UI, {})
        cfg = _leer_json(CONFIG_IA, {})
        tema = prefs.get("tema") if prefs.get("tema") in TEMAS else "claro"
        return {
            "tema": tema,
            "config": {
                "proveedor": cfg.get("proveedor", "auto"),
                "modelo": cfg.get("modelo", ""),
                "clave": cfg.get("clave", ""),
                "base_url": cfg.get("base_url", ""),
                "recordar": bool(cfg.get("clave")),
            },
            "proveedores": PROVEEDORES,
            "materia": protocol_builder.MATERIA_POR_DEFECTO,
            "salida": str(SALIDA),
        }

    def set_tema(self, tema: str) -> bool:
        if tema not in TEMAS:
            return False
        _escribir_json(PREF_UI, {"tema": tema})
        return True

    def guardar_config(self, cfg: dict) -> dict:
        """Guarda la config de IA solo si el usuario marco 'recordar'."""
        try:
            if cfg.get("recordar"):
                _escribir_json(CONFIG_IA, {
                    "proveedor": cfg.get("proveedor", "auto"),
                    "modelo": cfg.get("modelo", ""),
                    "clave": cfg.get("clave", ""),
                    "base_url": cfg.get("base_url", ""),
                })
            elif CONFIG_IA.exists():
                CONFIG_IA.unlink()
            return {"ok": True}
        except OSError as e:
            return {"ok": False, "mensaje": f"No se pudo guardar la configuración: {e}"}

    # ---------- modulo PDF ----------
    def seleccionar_pdf(self) -> dict | None:
        if self._window is None:
            return None
        ruta = _primer_valor(self._window.create_file_dialog(
            webview.FileDialog.OPEN, file_types=("Módulo PDF (*.pdf)",)))
        if not ruta:
            return None
        return {"ruta": ruta, "nombre": Path(ruta).name,
                "unidad": pdf_utils.deducir_unidad(ruta)}

    def extraer_texto(self, ruta: str) -> dict:
        if not ruta or not Path(ruta).exists():
            return {"ok": False, "mensaje": "Selecciona primero un PDF válido."}
        threading.Thread(target=self._run_extraer, args=(ruta,), daemon=True).start()
        return {"ok": True}

    def _run_extraer(self, ruta: str) -> None:
        avisos: list[str] = []
        try:
            texto, ocr = pdf_utils.extraer_texto(ruta, avisos=avisos)
        except Exception as e:
            self._emitir("error", contexto="extraer", mensaje=f"No se pudo extraer el texto: {e}")
            return
        for aviso in avisos:
            self._log(aviso, "aviso")
        self._texto = texto
        self._emitir("extraido", caracteres=len(texto), ocr=ocr,
                     vista=texto[:1500], biblio=pdf_utils.extraer_bibliografia(texto))

    # ---------- redaccion con IA ----------
    def redactar(self, opts: dict) -> dict:
        if not self._texto:
            return {"ok": False, "mensaje": "Primero extrae el texto del módulo."}
        threading.Thread(target=self._run_ia, args=(dict(opts), self._texto),
                         daemon=True).start()
        return {"ok": True}

    def _run_ia(self, opts: dict, texto: str) -> None:
        unidad = int(opts.get("unidad") or 1)
        materia = (opts.get("materia") or "").strip() or protocol_builder.MATERIA_POR_DEFECTO
        proveedor = opts.get("proveedor") or "auto"
        if proveedor in ("auto", "personalizado"):
            proveedor = None
        try:
            contenido = ia_client.redactar_contenido(
                texto, unidad, pdf_utils.extraer_bibliografia(texto),
                proveedor=proveedor,
                modelo=opts.get("modelo") or None,
                clave=opts.get("clave") or None,
                base_url=opts.get("base_url") or None,
                path_plantilla=str(PLANTILLA),
                materia=materia,
                progreso=lambda m: self._log(m),
            )
        except ia_client.ErrorSinClave as e:
            self._emitir("falta_clave", mensaje=str(e))
            return
        except Exception as e:
            self._emitir("error", contexto="ia", mensaje=f"Error de IA: {e}")
            return
        self._emitir("contenido", contenido=contenido)
        self._log("Contenido redactado. Revísalo antes de generar.", "ok")

    def listar_modelos(self, opts: dict) -> dict:
        threading.Thread(target=self._run_modelos, args=(dict(opts),), daemon=True).start()
        return {"ok": True}

    def _run_modelos(self, opts: dict) -> None:
        proveedor = opts.get("proveedor") or "auto"
        if proveedor in ("auto", "personalizado"):
            proveedor = None
        try:
            nombres = ia_client.lista_modelos(
                proveedor, clave=opts.get("clave") or None,
                base_url=opts.get("base_url") or None)
        except Exception as e:
            self._emitir("error", contexto="modelos", mensaje=f"Error al listar modelos: {e}")
            return
        self._emitir("modelos", nombres=nombres)

    # ---------- contenido manual / JSON ----------
    def validar(self, contenido: dict) -> list[str]:
        return errores_contenido(contenido)

    def cargar_json(self) -> dict | None:
        if self._window is None:
            return None
        ruta = _primer_valor(self._window.create_file_dialog(
            webview.FileDialog.OPEN, file_types=("Contenido JSON (*.json)",)))
        if not ruta:
            return None
        try:
            with open(ruta, encoding="utf-8") as f:
                return {"ok": True, "contenido": json.load(f)}
        except Exception as e:
            return {"ok": False, "mensaje": f"No se pudo leer el JSON: {e}"}

    def guardar_json(self, contenido: dict) -> dict | None:
        if self._window is None:
            return None
        ruta = _primer_valor(self._window.create_file_dialog(
            webview.FileDialog.SAVE, save_filename="contenido.json",
            file_types=("Contenido JSON (*.json)",)))
        if not ruta:
            return None
        try:
            with open(ruta, "w", encoding="utf-8") as f:
                json.dump(contenido, f, ensure_ascii=False, indent=2)
            return {"ok": True, "ruta": ruta}
        except Exception as e:
            return {"ok": False, "mensaje": f"No se pudo guardar: {e}"}

    # ---------- generacion del DOCX ----------
    def generar(self, contenido: dict, unidad, materia: str) -> dict:
        errores = errores_contenido(contenido)
        if errores:
            return {"ok": False, "errores": errores}
        materia = (materia or "").strip() or protocol_builder.MATERIA_POR_DEFECTO
        threading.Thread(target=self._run_generar,
                         args=(contenido, int(unidad or 1), materia), daemon=True).start()
        return {"ok": True}

    def _run_generar(self, contenido: dict, unidad: int, materia: str) -> None:
        nombre = f"Protocolo Individual - {unidad}° Unidad - {materia} - {NOMBRE_ESTUDIANTE}.docx"
        salida = SALIDA / _nombre_seguro(nombre)
        try:
            self._log(f"Ensamblando DOCX (unidad {unidad}, {materia})…")
            ruta = protocol_builder.build_protocol(
                str(PLANTILLA), contenido, str(salida), unidad, materia)
            self._log(f"DOCX generado: {Path(ruta).name}")
            self._log("Verificando formato…")
            errores = verificador.verificar(ruta, materia=materia)
        except Exception as e:
            self._emitir("error", contexto="generar", mensaje=f"Error al generar: {e}")
            return
        if errores:
            for e in errores:
                self._log("  - " + e, "error")
            self._emitir("error", contexto="verificar",
                         mensaje="El DOCX se generó pero la verificación encontró problemas.")
            return
        self._log("Verificación OK: formato idéntico a la plantilla.", "ok")
        self._emitir("listo", ruta=ruta, nombre=Path(ruta).name)

    def abrir_archivo(self, ruta: str) -> dict:
        if not ruta or not Path(ruta).exists():
            return {"ok": False, "mensaje": "El archivo ya no existe."}
        os.startfile(ruta)
        return {"ok": True}

    def abrir_salida(self) -> dict:
        SALIDA.mkdir(exist_ok=True)
        os.startfile(str(SALIDA))
        return {"ok": True}
