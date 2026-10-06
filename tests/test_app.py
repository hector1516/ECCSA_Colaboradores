"""
tests/test_app.py — Pruebas de la app sin BD y sin servidor
==========================================================
Levanta el servidor real en un hilo y le pega con urllib. Es una prueba de
integración de verdad: si el HTML está roto o una ruta está mal cableada, salta
aquí y no en el móvil de un cliente.

Corre:  python3 tests/test_app.py
"""
import base64
import contextlib
import io
import json
import os
import sys
import threading
import unittest
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from panel import config, server  # noqa: E402
from panel.vcard import construir_vcard  # noqa: E402


class TestHelpers(unittest.TestCase):
    """Lo que se puede probar sin tocar la BD."""

    def test_whatsapp_normaliza(self):
        from panel.plantillas import url_whatsapp
        # 10 dígitos: se le pone clave de país.
        self.assertEqual(url_whatsapp("812 345 6789"), "https://wa.me/528123456789")
        # Con clave ya, no se duplica el 52.
        self.assertEqual(url_whatsapp("+52 81 2345 6789"),
                         "https://wa.me/528123456789")
        # Basura → vacío (y la plantilla no pinta el botón).
        self.assertEqual(url_whatsapp(""), "")
        self.assertEqual(url_whatsapp("123"), "")

    def test_mapa_prefiere_coordenadas(self):
        from panel.plantillas import url_mapa
        self.assertIn("25.67,-100.28", url_mapa("25.67", "-100.28", "Monterrey"))
        # Sin coordenadas cae a la búsqueda por dirección.
        self.assertIn("Monterrey", url_mapa("", "", "Monterrey"))
        self.assertEqual(url_mapa("", "", ""), "")

    def test_redes_aceptan_usuario_o_url(self):
        from panel.plantillas import url_facebook, url_instagram
        self.assertEqual(url_instagram("@eccsa"), "https://instagram.com/eccsa")
        self.assertEqual(url_instagram("https://instagram.com/x"),
                         "https://instagram.com/x")
        self.assertEqual(url_facebook("eccsa"), "https://facebook.com/eccsa")
        self.assertEqual(url_facebook(""), "")

    def test_slugify_no_pierde_letras(self):
        """La eñe y los acentos deben SOBREVIVIR, no borrarse.

        Regresión: encode("ascii","ignore") convertía 'ángel' en 'ngel'.
        """
        from panel.tokens import slugify
        self.assertEqual(slugify("Hector Peña Ruiz"), "hector-pena-ruiz")
        self.assertEqual(slugify("Ángel Pérez"), "angel-perez")
        self.assertEqual(slugify("José María Ñuño"), "jose-maria-nuno")
        self.assertEqual(slugify("  "), "colaborador")

    def test_token_es_largo_y_del_alfabeto(self):
        from panel.tokens import ALFABETO, LARGO_TOKEN, generar_token
        t = generar_token()
        self.assertEqual(len(t), LARGO_TOKEN)
        self.assertTrue(all(c in ALFABETO for c in t))
        # Dos tokens distintos: si salieran iguales, el PRNG está roto.
        self.assertNotEqual(generar_token(), generar_token())

    def test_slug_valido_rechaza_basura(self):
        from panel.tokens import slug_valido
        self.assertTrue(slug_valido("hector-pena-" + "A" * 32))
        self.assertFalse(slug_valido(""))
        self.assertFalse(slug_valido("hector-pena"))
        self.assertFalse(slug_valido("hector-pena-CORTO"))
        # I, L, O y U no están en el alfabeto (Crockford): no son tokens válidos.
        self.assertFalse(slug_valido("hector-" + "I" * 32))

    def test_vcard_dobla_lineas_largas(self):
        """La RFC 2426 corta a 75 octetos. Sin esto, la foto se pierde al
        importar y el contacto se guarda sin ella."""
        foto = "data:image/png;base64," + base64.b64encode(b"x" * 3000).decode()
        vcf = construir_vcard("Hector Peña", telefono="8181234567", foto=foto)
        for linea in vcf.split("\r\n"):
            self.assertLessEqual(len(linea.encode()), 75)
        self.assertIn("PHOTO;ENCODING=b;TYPE=JPEG:", vcf)
        # El prefijo del data-URI NO debe colarse en el vCard.
        self.assertNotIn("data:image", vcf)

    def test_vcard_parte_apellidos(self):
        vcf = construir_vcard("Hector Peña Ruiz")
        self.assertIn("N:Ruiz;Hector Peña;;;", vcf)
        self.assertIn("FN:Hector Peña Ruiz", vcf)

    def test_vcard_omite_campos_vacios(self):
        """Un TEL: vacío hace que el móvil ofrezca guardar un número en blanco."""
        vcf = construir_vcard("Solo Nombre")
        self.assertNotIn("TEL;", vcf)
        self.assertNotIn("EMAIL;", vcf)
        self.assertNotIn("PHOTO;", vcf)

    def test_vcard_escapa_delimitadores(self):
        """Un ';' o un '\\' sin escapar rompe el archivo entero."""
        vcf = construir_vcard("García; Juan\\ Carlos")
        self.assertIn("FN:García\\; Juan\\\\ Carlos", vcf)


class TestRutas(unittest.TestCase):
    """Rutas del servidor real, en un hilo, sin base de datos.

    Se monkeypatchea db para que el test no dependa de SQL Server: lo que se
    prueba aquí es el CABLEADO (status, content-type, cabeceras), no el SQL.
    """

    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("DATA_DIR", "/tmp/colab_test_data")
        os.makedirs(os.environ["DATA_DIR"], exist_ok=True)
        with open(os.path.join(os.environ["DATA_DIR"], "admin_secret.txt"),
                  "w", encoding="utf-8") as fh:
            fh.write("secreto-de-prueba")

        # Ficha y empresa falsas: el objetivo es la respuesta HTTP.
        cls.ficha = {
            "Id": 1, "Slug": "hector-pena-" + "A" * 32,
            "Etiqueta": "Hector Pena",
            "Creado": None, "NumAccesos": 0,
            "Nombre": "Hector Peña", "Email": "hector@ecc-sa.com.mx",
            "Foto": "", "Telefono": "8181234567",
        }
        cls.empresa = {
            "colab_empresa_nombre": "ECCSA",
            "colab_empresa_direccion": "Av. Nombre 100, Monterrey",
            "colab_empresa_telefono": "8180000000",
            "colab_empresa_whatsapp": "528181234567",
            "colab_empresa_facebook": "eccsa",
            "colab_empresa_instagram": "@eccsa",
            "colab_empresa_latitud": "25.67",
            "colab_empresa_longitud": "-100.28",
        }
        server.db.obtener_ficha = lambda slug: (
            cls.ficha if slug == cls.ficha["Slug"] else None)
        server.db.obtener_empresa = lambda: cls.empresa
        server.db.registrar_acceso = lambda slug: None
        server.tokens.listar_usuarios = lambda: []
        server.tokens.slug_valido = __import__(
            "panel.tokens", fromlist=["slug_valido"]).slug_valido

        cls.httpd = server.ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        cls.base = "http://127.0.0.1:%d" % cls.httpd.server_address[1]
        cls.hilo = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.hilo.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def _get(self, ruta, cabeceras=None):
        req = urllib.request.Request(self.base + ruta, headers=cabeceras or {})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, r.read(), dict(r.headers)
        except urllib.error.HTTPError as e:
            return e.code, e.read(), dict(e.headers)

    def test_healthz(self):
        codigo, cuerpo, _ = self._get("/healthz")
        self.assertEqual(codigo, 200)
        self.assertEqual(cuerpo, b"ok")

    def test_shell_state_es_json_del_contrato(self):
        codigo, cuerpo, cabeceras = self._get("/api/shell/state")
        self.assertEqual(codigo, 200)
        self.assertIn("json", cabeceras.get("Content-Type", ""))
        d = json.loads(cuerpo)
        # Claves obligatorias del contrato del shell (docs/CONTRATO.md).
        for clave in ("app", "shell", "user", "sync", "lugar"):
            self.assertIn(clave, d)
        self.assertEqual(d["app"]["id"], "colaboradores")
        # Sin sesión → user null, como el kiosco del Dashboard (§2b).
        self.assertIsNone(d["user"])
        self.assertIn(d["lugar"]["modo"], ("oficina", "remoto", "desconocido"))

    def test_robots_bloquea_todo(self):
        codigo, cuerpo, _ = self._get("/robots.txt")
        self.assertEqual(codigo, 200)
        self.assertIn(b"Disallow: /", cuerpo)

    def test_raiz_no_lista_a_nadie(self):
        """El alcance acordado es 'solo fichas individuales'.

        Si la raíz llegara a devolver una tabla de personas, el roster completo
        quedaría expuesto a cualquiera que acertara el dominio.
        """
        codigo, _, _ = self._get("/")
        self.assertEqual(codigo, 404)

    def test_ficha_devuelve_html_con_los_datos(self):
        codigo, cuerpo, cabeceras = self._get("/" + self.ficha["Slug"])
        self.assertEqual(codigo, 200)
        texto = cuerpo.decode("utf-8")
        for esperado in ("Hector Peña", "hector@ecc-sa.com.mx", "Guardar contacto",
                         "WhatsApp", "Cómo llegar", "wa.me/528181234567",
                         "facebook.com/eccsa", "instagram.com/eccsa"):
            self.assertIn(esperado, texto, f"falta {esperado}")
        # El CSS del shell va inline (la tarjeta NFC puede abrir sin datos).
        self.assertIn("--color-primary", texto)
        # Y los datos de la BD van escapados, no interpretados como HTML.
        self.assertNotIn("<script>", texto.lower())

    def test_ficha_no_se_cachea(self):
        _, _, cabeceras = self._get("/" + self.ficha["Slug"])
        self.assertIn("no-store", cabeceras.get("Cache-Control", ""))

    def test_ficha_antiframe_y_referer(self):
        """El token va en la URL: si el Referer se filtra, se filtra el token."""
        _, _, cabeceras = self._get("/" + self.ficha["Slug"])
        self.assertEqual(cabeceras.get("X-Frame-Options"), "DENY")
        self.assertEqual(cabeceras.get("Referrer-Policy"), "no-referrer")

    def test_vcard_se_sirve_como_vcard(self):
        codigo, cuerpo, cabeceras = self._get(
            "/" + self.ficha["Slug"] + "/contacto.vcf")
        self.assertEqual(codigo, 200)
        self.assertIn("vcard", cabeceras.get("Content-Type", ""))
        self.assertIn("BEGIN:VCARD", cuerpo.decode("utf-8"))

    def test_slug_inexistente_da_404(self):
        codigo, _, _ = self._get("/nadie-aqui-" + "B" * 32)
        self.assertEqual(codigo, 404)

    def test_slug_con_forma_mala_da_404(self):
        """Mismo 404 que un slug inexistente: no se revela nada."""
        codigo, _, _ = self._get("/corto")
        self.assertEqual(codigo, 404)

    def test_404_no_distingue_inexistente_de_revocado(self):
        """Ambas respuestas deben ser idénticas: si difieren, se puede probar
        qué tokens existieron."""
        _, a, _ = self._get("/nadie-aqui-" + "B" * 32)
        _, b, _ = self._get("/corto")
        self.assertEqual(a, b)

    def test_admin_exige_sesion(self):
        codigo, _, _ = self._get("/admin")
        self.assertEqual(codigo, 401)

    def test_login_malo_no_entra(self):
        import urllib.parse
        datos = urllib.parse.urlencode({"secret": "equivocado"}).encode()
        req = urllib.request.Request(self.base + "/admin/login", data=datos,
                                     method="POST")
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                self.fail(f"entró con secreto equivocado: {r.status}")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 401)

    def test_post_sin_sesion_es_401(self):
        req = urllib.request.Request(self.base + "/admin/emitir", data=b"id=1",
                                     method="POST")
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                self.fail(f"escribió sin sesión: {r.status}")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 401)

    def test_token_no_aparece_en_el_log(self):
        """El token NUNCA debe quedar escrito en el log del proceso.

        La ruta ES el token, así que el log_request de http.server (que escribe
        la línea completa) está anulado a propósito. Aquí se comprueba que tras
        pedir la ficha no haya aparecido el slug en lo capturado por stdout.
        """
        self._get("/" + self.ficha["Slug"])
        capturado = io.StringIO()
        with contextlib.redirect_stdout(capturado):
            self._get("/" + self.ficha["Slug"])
        salida = capturado.getvalue()
        self.assertNotIn(self.ficha["Slug"], salida,
                         "el token se filtró al log del proceso")


if __name__ == "__main__":
    unittest.main(verbosity=2)
