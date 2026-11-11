"""Tests de la API web (api.py) sin abrir ventana.

Las rutas de configuracion se redirigen a una carpeta temporal para no
tocar .config_ia.json ni .ui.json reales.
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))

import api  # noqa: E402


class ApiTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        tmp = Path(self._tmp.name)
        self._orig = (api.CONFIG_IA, api.PREF_UI)
        api.CONFIG_IA = tmp / "config.json"
        api.PREF_UI = tmp / "ui.json"
        self.api = api.Api()

    def tearDown(self):
        api.CONFIG_IA, api.PREF_UI = self._orig
        self._tmp.cleanup()

    def test_inicio_valores_por_defecto(self):
        datos = self.api.inicio()
        self.assertEqual(datos["tema"], "claro")
        self.assertEqual(datos["config"]["proveedor"], "auto")
        self.assertFalse(datos["config"]["recordar"])
        self.assertIn("personalizado", datos["proveedores"])

    def test_set_tema_persiste_y_rechaza_valores_invalidos(self):
        self.assertTrue(self.api.set_tema("oscuro"))
        self.assertEqual(self.api.inicio()["tema"], "oscuro")
        self.assertFalse(self.api.set_tema("neon"))
        self.assertEqual(self.api.inicio()["tema"], "oscuro")

    def test_guardar_config_solo_si_recordar(self):
        cfg = {"proveedor": "groq", "modelo": "m", "clave": "k", "base_url": "", "recordar": True}
        self.assertTrue(self.api.guardar_config(cfg)["ok"])
        self.assertEqual(json.loads(api.CONFIG_IA.read_text(encoding="utf-8"))["clave"], "k")
        cfg["recordar"] = False
        self.api.guardar_config(cfg)
        self.assertFalse(api.CONFIG_IA.exists())

    def test_validar_devuelve_errores(self):
        self.assertTrue(self.api.validar({}))

    def test_redactar_sin_texto_falla_sin_hilo(self):
        r = self.api.redactar({"unidad": 1})
        self.assertFalse(r["ok"])

    def test_extraer_texto_valida_ruta(self):
        r = self.api.extraer_texto(str(BASE / "no_existe.pdf"))
        self.assertFalse(r["ok"])

    def test_generar_rechaza_contenido_incompleto(self):
        r = self.api.generar({"descripcion": "x"}, 1, "Materia")
        self.assertFalse(r["ok"])
        self.assertTrue(r["errores"])


if __name__ == "__main__":
    unittest.main()
