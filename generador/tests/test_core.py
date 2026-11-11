"""Tests de la logica de core/ (sin GUI ni llamadas reales a la IA).

Ejecutar desde la carpeta generador/:
    python -m unittest discover -s tests -v
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))

from core import ia_client, pdf_utils, protocol_builder, verificador  # noqa: E402
from core.esquema import errores_contenido  # noqa: E402

PLANTILLA = BASE / "plantilla" / "Protocolo_Plantilla.docx"


def contenido_valido() -> dict:
    return {
        "descripcion": "El siguiente protocolo trata sobre HTML5.",
        "palabras_claves": "html, web, estructura",
        "objetivos": ["Objetivo 1", "Objetivo 2", "Objetivo 3"],
        "conceptos": [{"termino": f"T{i}", "definicion": f"D{i}"} for i in range(8)],
        "resumen": [{"subtitulo": f"S{i}", "parrafos": ["Parrafo."]} for i in range(3)],
        "conclusiones": "Conclusion.",
        "bibliografia": "Autor (2020). Titulo.",
    }


class EsquemaTests(unittest.TestCase):
    def test_contenido_valido_no_tiene_errores(self):
        self.assertEqual(errores_contenido(contenido_valido()), [])

    def test_faltan_campos(self):
        c = contenido_valido()
        del c["conclusiones"]
        errores = errores_contenido(c)
        self.assertEqual(len(errores), 1)
        self.assertIn("conclusiones", errores[0])

    def test_cardinalidad_objetivos(self):
        c = contenido_valido()
        c["objetivos"] = ["solo uno"]
        self.assertTrue(any("objetivos" in e for e in errores_contenido(c)))

    def test_cardinalidad_conceptos_limites(self):
        c = contenido_valido()
        c["conceptos"] = c["conceptos"][:7]
        self.assertTrue(any("conceptos" in e for e in errores_contenido(c)))
        c["conceptos"] = [{"termino": "t", "definicion": "d"}] * 13
        self.assertTrue(any("conceptos" in e for e in errores_contenido(c)))

    def test_concepto_sin_definicion(self):
        c = contenido_valido()
        c["conceptos"][0] = {"termino": "t", "definicion": " "}
        self.assertTrue(any("término y definición" in e for e in errores_contenido(c)))

    def test_descripcion_vacia(self):
        c = contenido_valido()
        c["descripcion"] = "   "
        self.assertTrue(any("descripcion" in e for e in errores_contenido(c)))

    def test_resumen_seccion_sin_parrafos(self):
        c = contenido_valido()
        c["resumen"][1]["parrafos"] = []
        self.assertTrue(any("resumen" in e for e in errores_contenido(c)))


class ParseYValidacionIATests(unittest.TestCase):
    def test_parse_json_quita_fences(self):
        data = ia_client.parse_json('```json\n{"a": 1}\n```')
        self.assertEqual(data, {"a": 1})

    def test_parse_json_invalido_lanza_valueerror(self):
        with self.assertRaises(ValueError):
            ia_client.parse_json("no es json")

    def test_validar_esquema_es_el_mismo_que_el_compartido(self):
        c = contenido_valido()
        c["objetivos"] = []
        self.assertEqual(ia_client.validar_esquema(c), errores_contenido(c))


class CredencialesTests(unittest.TestCase):
    def test_proveedor_desconocido_sin_url_lanza_error(self):
        # Antes caia a OpenAI y enviaba la clave a ese endpoint.
        with self.assertRaises(ValueError):
            ia_client.resolver_credenciales("proveedorfalso")

    def test_proveedor_conocido(self):
        _, base, _ = ia_client.resolver_credenciales("google")
        self.assertTrue(base.startswith("https://generativelanguage.googleapis.com"))

    def test_url_personalizada_con_proveedor_desconocido(self):
        _, base, _ = ia_client.resolver_credenciales("mi-proveedor", base_url="http://localhost:1234/v1")
        self.assertEqual(base, "http://localhost:1234/v1")


class PdfUtilsTests(unittest.TestCase):
    def test_deducir_unidad(self):
        self.assertEqual(pdf_utils.deducir_unidad("C:/x/Modulo 2.pdf"), 2)
        self.assertEqual(pdf_utils.deducir_unidad("modulo 10.PDF"), 10)
        self.assertIsNone(pdf_utils.deducir_unidad("Apuntes.pdf"))

    def test_extraer_bibliografia(self):
        texto = "Intro\nBibliografía\nGarcia J. (2019). Web moderna.\n\nOtro texto"
        self.assertEqual(pdf_utils.extraer_bibliografia(texto), ["Garcia J. (2019). Web moderna."])

    def test_texto_inutil(self):
        self.assertTrue(pdf_utils.texto_probablemente_inutil("   "))
        self.assertFalse(pdf_utils.texto_probablemente_inutil("x" * 400))


class ProtocolBuilderTests(unittest.TestCase):
    def test_validar_contenido_lanza_con_todos_los_errores(self):
        c = contenido_valido()
        c["objetivos"] = []
        c["resumen"] = []
        with self.assertRaises(ValueError) as ctx:
            protocol_builder.validar_contenido(c)
        self.assertIn("objetivos", str(ctx.exception))
        self.assertIn("resumen", str(ctx.exception))

    @unittest.skipUnless(PLANTILLA.exists(), "falta la plantilla")
    def test_docx_generado_pasa_el_verificador(self):
        with tempfile.TemporaryDirectory() as tmp:
            salida = Path(tmp) / "protocolo.docx"
            protocol_builder.build_protocol(str(PLANTILLA), contenido_valido(),
                                            str(salida), unidad=2)
            self.assertTrue(salida.exists())
            errores = verificador.verificar(str(salida))
            self.assertEqual(errores, [])


if __name__ == "__main__":
    unittest.main()
