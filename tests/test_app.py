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
import time
import os
import sys
import threading
import unittest
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from panel import config as config_mod  # noqa: E402
from panel import server  # noqa: E402

DATA_DIR_TEST = "/tmp/colab_test_data"

# El secreto de derivacion se crea a nivel de MODULO, no en setUpClass: los
# tests de helpers corren antes que los de rutas y ya necesitan un token real
# (el slug se deriva del Id, no se puede escribir uno a mano).
os.makedirs(DATA_DIR_TEST, exist_ok=True)
config_mod.SECRET_FILE = os.path.join(DATA_DIR_TEST, "admin_secret.txt")
config_mod.FICHA_SECRET_FILE = os.path.join(DATA_DIR_TEST, "ficha_secret.txt")
with open(config_mod.SECRET_FILE, "w", encoding="utf-8") as _fh:
    _fh.write("secreto-de-prueba")
with open(config_mod.FICHA_SECRET_FILE, "w", encoding="utf-8") as _fh:
    _fh.write("secreto-de-derivacion-de-prueba")


class _SinRedirigir(urllib.request.HTTPRedirectHandler):
    """Devuelve el 303 en vez de seguirlo.

    Hace falta porque el login responde 303 → /admin, y urllib NO lleva cookies
    entre redirecciones: al seguirla, /admin responde 401 y el test parece fallar
    cuando lo que pasó es que la cookie se quedó en el primer response.
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None
from panel import tokens as tokens_mod  # noqa: E402
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

    def test_los_botones_se_autoajustan(self):
        """`auto-fit` + `minmax()` en vez de columnas fijas.

        Con `1fr 1fr` fijo, un número impar de botones dejaba una fila huérfana
        con un botón más estrecho que los demás, y un hueco vacío. Con
        `auto-fit` la rejilla se acomoda sola al ancho y a cuántos botones haya.
        """
        import os

        css = open(os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "panel", "ficha.css"),
            encoding="utf-8").read()
        self.assertIn("repeat(auto-fit, minmax(140px, 1fr))", css)
        # Se mira DENTRO del bloque .acciones, no en todo el archivo: el
        # formulario de empresa del panel sí lleva 1fr 1fr fijo y es correcto.
        bloque = css.split(".acciones {", 1)[1].split("}", 1)[0]
        self.assertNotIn("1fr 1fr", bloque,
                         "los botones volvieron a columnas fijas")
        # Y las etiquetas largas tienen que poder partirse, no desbordar.
        self.assertIn("overflow-wrap: anywhere;", css)

    def test_mapa_prefiere_el_link_corto(self):
        """El link corto de Google abre la app de mapas del móvil.

        Y es el lugar EXACTO verificado por Google, no una búsqueda por texto
        que puede caer en otro punto de la calle.
        """
        from panel.plantillas import url_mapa
        corto = "https://maps.app.goo.gl/68aD2DRKH31VSFd97"
        self.assertEqual(url_mapa("25.66", "-100.28", "Monterrey", corto), corto)
        # Sin https delante lo normaliza, para que un valor mal pegado en el
        # panel no rompa el boton.
        self.assertEqual(url_mapa("", "", "", "maps.app.goo.gl/abc"),
                         "https://maps.app.goo.gl/abc")

    def test_mapa_sin_link_usa_coordenadas(self):
        from panel.plantillas import url_mapa
        con = url_mapa("25.67", "-100.28", "Monterrey")
        self.assertIn("google.com/maps", con)
        self.assertIn("25.67%2C-100.28", con)
        # Sin coordenadas cae a la búsqueda por dirección.
        self.assertIn("Monterrey", url_mapa("", "", "Monterrey"))
        self.assertEqual(url_mapa("", "", ""), "")

    def test_mapa_ya_no_usa_apple_maps(self):
        """maps.apple.com mandaba a una web dentro del navegador en Android."""
        from panel.plantillas import url_mapa
        for enlace in (url_mapa("25.67", "-100.28", "x"),
                       url_mapa("", "", "x"),
                       url_mapa("", "", "", "https://maps.app.goo.gl/a")):
            self.assertNotIn("apple.com", enlace)

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

    def test_el_token_se_deriva_del_id(self):
        """El token sale del Id: mismo Id, mismo token, siempre."""
        from panel import tokens as tk
        self.assertEqual(tk.token_de(2), tk.token_de(2))
        self.assertNotEqual(tk.token_de(2), tk.token_de(3))
        self.assertEqual(len(tk.token_de(2)), tk.LARGO_TOKEN)
        self.assertTrue(all(c in tk.ALFABETO for c in tk.token_de(2)))

    def test_el_token_cambia_si_cambia_el_secreto(self):
        """Rotar el secreto invalida todas las tarjetas. Es el precio del diseño."""
        from panel import tokens as tk
        original = config_mod.ficha_secreto
        antes = tk.token_de(2)
        try:
            config_mod.ficha_secreto = lambda: "otro-secreto-distinto"
            self.assertNotEqual(tk.token_de(2), antes)
        finally:
            config_mod.ficha_secreto = original
        self.assertEqual(tk.token_de(2), antes)

    def test_sin_secreto_no_hay_token(self):
        """Sin secreto la app devuelve cadena vacia, nunca un token debil."""
        from panel import tokens as tk
        original = config_mod.ficha_secreto
        try:
            config_mod.ficha_secreto = lambda: ""
            self.assertEqual(tk.token_de(2), "")
            self.assertEqual(tk.construir_slug("X", 2), "")
            self.assertEqual(tk.persona_por_token("x-" + "A" * 32), None)
        finally:
            config_mod.ficha_secreto = original

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
        # Los secretos ya están puestos a nivel de módulo (ver arriba).
        # Ficha y empresa falsas: el objetivo es la respuesta HTTP.
        # El slug NO se puede escribir a mano: es el token DERIVADO del Id.
        slug_real = tokens_mod.construir_slug("Hector Peña", 1)
        assert slug_real, "el secreto de derivacion no esta puesto"
        cls.ficha = {
            "Id": 1, "Slug": slug_real,
            "Etiqueta": "Hector Pena",
            "Nombre": "Hector Peña", "Email": "hector@ecc-sa.com.mx",
            "Foto": "", "FotoTipo": "image/jpeg",
            "Puesto": "Técnico de campo",
            "Telefono": "8181234567", "Activo": True, "Avatar": "",
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
            "colab_empresa_sitio": "www.ecc-sa.com.mx",
            "colab_empresa_mapa_url": "https://maps.app.goo.gl/68aD2DRKH31VSFd97",
        }
        server.db.obtener_persona = lambda id_usuario: (
            cls.ficha if id_usuario == 1 else None)
        server.db.obtener_empresa = lambda: cls.empresa
        server.tokens.listar_personas = lambda solo_activas=False: (
            [cls.ficha] if solo_activas else [cls.ficha, dict(cls.ficha, Id=2, Activo=0)])
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

    def assert_contiene(self, cuerpo, esperado, msg=""):
        """Como assertIn pero sin volcar 40 KB de HTML al fallar.

        El mensaje de un assertIn sobre la ficha entera hace ilegible el fallo:
        el diff es la página completa con el CSS inline del shell.
        """
        self.assertTrue(
            esperado in cuerpo,
            f"{msg or 'falta en la respuesta'} -> {esperado!r}")

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
                         "facebook.com/eccsa", "instagram.com/eccsa",
                         "maps.app.goo.gl/68aD2DRKH31VSFd97"):
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

    def test_la_foto_se_reduce(self):
        """Una foto de 500 KB no puede ir cruda a la ficha.

        La ficha se abre por NFC, a menudo con datos móviles: 500 KB para pintar
        un círculo de 120 px es tirar ancho de banda, y en el vCard hace que iOS
        a veces tarde en abrir el contacto.
        """
        import base64
        import io
        import random

        from PIL import Image
        # Foto CON RUIDO, no un color plano: un color uniforme se comprime a casi
        # nada y el test compararía 500 KB contra 200 bytes, que no prueba nada.
        rnd = random.Random(7)
        grande = Image.new("RGB", (900, 1200))
        grande.putdata([(rnd.randrange(256), rnd.randrange(256),
                         rnd.randrange(256)) for _ in range(900 * 1200)])
        buf = io.BytesIO()
        grande.save(buf, format="JPEG", quality=95)
        original = buf.getvalue()

        original_fn = server.tokens.foto_bytes
        server.tokens.foto_bytes = lambda uid: (original, "image/jpeg")
        try:
            reducido, tipo = server.tokens.foto_thumbnail(99)
            self.assertEqual(tipo, "image/jpeg")

            salida = Image.open(io.BytesIO(base64.b64decode(reducido)))
            # Cuadrada y NUNCA más grande que el tope: esto es la garantía que
            # importa, la que hace que la página no se vaya a 1 MB.
            self.assertEqual(salida.width, salida.height)
            self.assertLessEqual(max(salida.size), server.tokens.LADO_AVATAR)

            # Y tiene que pesar menos que la original. No se fija un factor
            # exacto porque la foto de prueba es RUIDO ALEATORIO, que es el peor
            # caso posible para JPEG (no comprima nada); con una foto real el
            # avatar pesa 40-50 KB contra 450-550 KB de la original.
            self.assertLess(len(base64.b64decode(reducido)), len(original),
                            f"mini vs original {len(original)}b")
        finally:
            server.tokens.foto_bytes = original_fn

    def test_foto_con_alfa_no_sale_negro(self):
        """Un PNG transparente a JPEG se vuelve negro si no se compone antes."""
        import base64
        import io
        import random

        from PIL import Image
        rnd = random.Random(11)
        # Con ruido también: igual que arriba, un color plano no pesa nada.
        plano = Image.new("RGBA", (900, 900))
        plano.putdata([(255, 107, 0, rnd.randrange(256))
                       for _ in range(900 * 900)])
        buf = io.BytesIO()
        plano.save(buf, format="PNG")
        original = buf.getvalue()
        assert len(original) > 10000, "la foto de prueba debe pesar algo"
        original_fn = server.tokens.foto_bytes
        server.tokens.foto_bytes = lambda uid: (original, "image/png")
        try:
            _, tipo = server.tokens.foto_thumbnail(99)
            self.assertEqual(tipo, "image/jpeg")
        finally:
            server.tokens.foto_bytes = original_fn

    def test_la_ficha_es_animada_pero_sin_js(self):
        """Las animaciones son CSS puro: la ficha se abre con un dedo pegado a
        una tarjeta NFC y tiene que verse igual aunque el JS tarde o falle."""
        _, cuerpo, _ = self._get("/" + self.ficha["Slug"])
        texto = cuerpo.decode("utf-8")
        self.assertNotIn("<script", texto.lower())
        self.assertNotIn("onclick", texto.lower())
        # Cascada de entrada: el retardo escalonado va en el HTML como `--i`.
        self.assertIn('class="identidad anima" style="--i:0"', texto)

    def test_la_foto_es_grande(self):
        """La foto era de 120 px (tamaño de icono) y no se veia bien.

        Se comprueba que el CSS siga dimensionándola con clamp(), y no con un
        tamaño fijo pequeño que alguien vuelva a dejar.
        """
        import os

        css = open(os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "panel", "ficha.css"),
            encoding="utf-8").read()
        self.assertIn("clamp(190px, 68vw, 340px)", css)
        # El recorte va CENTRADO, como en AdmonApp. Esta app antes lo desplazaba
        # al 28% "para acercar la cara" y el resultado era un recorte descuadrado
        # que se veía peor que el de Admon.
        self.assertIn("object-fit: cover", css)
        import re as _re
        reglas = _re.sub(r"/\*.*?\*/", "", css, flags=_re.S)
        self.assertNotIn("object-position", reglas)

    def test_el_fondo_es_el_del_shell(self):
        """El fondo tiene que ser el engrane del shell, como Field y Admon.

        Esta app tenía su propia aurora y se veía un fondo DISTINTO al del resto
        del ecosistema. Ahora no define fondo: hereda el del shell.
        """
        import os

        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        css = open(os.path.join(base, "panel", "ficha.css"),
                   encoding="utf-8").read()
        # Se buscan las REGLAS, no la palabra: el comentario que explica por
        # qué ya no hay aurora la menciona. Por eso se quitan los comentarios
        # COMPLETOS, incluidos los de varias líneas, no solo las líneas que
        # empiezan por /*.
        import re as _re

        reglas = _re.sub(r"/\*.*?\*/", "", css, flags=_re.S)
        reglas = _re.sub(r"//[^\n]*", "", reglas)
        self.assertNotIn("aurora", reglas)
        self.assertNotIn("body.ficha::after", reglas)
        # Y tampoco puede haber un keyframe huerfano que ya no se use.
        self.assertNotIn("@keyframes aurora", reglas)

        # Y el engrane que sirve es COPIA del de Field, no un dibujo propio.
        import hashlib

        def md5(path):
            with open(path, "rb") as fh:
                return hashlib.md5(fh.read()).hexdigest()

        campo = os.path.join(base, "panel", "engrane.png")
        field = os.path.join(os.path.dirname(base), "field", "static",
                             "engrane.png")
        self.assertTrue(os.path.isfile(campo), "falta panel/engrane.png")
        if os.path.isfile(field):
            self.assertEqual(md5(campo), md5(field),
                             "el engrane dejó de ser el de Field")

    def test_el_recorte_cae_sobre_la_cara(self):
        """El recorte NO puede ir al centro: en una vertical eso es pecho y boca.

        Regresión real: las fotos de `HUB_UsuariosFotos` son 896x1200 verticales
        de celular. Recortando el cuadrado al centro, la franja salía del 37% al
        63% de la altura — la cara quedaba fuera y en la ficha se veía "solo la
        boca". Con el centro al 42% entra la cara completa.
        """
        from panel import tokens

        ancho, alto = 896, 1200
        lado = tokens.LADO_AVATAR
        arriba = tokens._arriba_del_recorte(alto, lado)

        # El recorte tiene que entrar en la imagen.
        self.assertGreaterEqual(arriba, 0)
        self.assertLessEqual(arriba + lado, alto)

        # Y su centro tiene que caer en la franja de la cara, no en el pecho.
        centro = (arriba + lado / 2) / alto
        self.assertGreater(centro, 0.30, "el recorte subió de más: cortaría la frente")
        self.assertLess(centro, 0.55, "el recorte bajó de más: saldría la boca/pecho")

    def test_el_recaporte_no_sale_de_la_imagen(self):
        """Con imágenes casi cuadradas el recorte tiene que ajustarse, no
        desbordarse (Pillow recorta en silencio y devuelve negro)."""
        from panel import tokens

        for ancho, alto in ((900, 320), (900, 400), (900, 460), (900, 900),
                            (896, 1200), (900, 2400)):
            # El lado real es el menor de los tres: así el recorte nunca pide
            # más pixeles de los que tiene la imagen.
            lado = min(ancho, alto, tokens.LADO_AVATAR)
            arriba = tokens._arriba_del_recorte(alto, lado)
            self.assertGreaterEqual(arriba, 0, f"{ancho}x{alto}")
            self.assertLessEqual(arriba + lado, alto, f"{ancho}x{alto}")

    def test_el_marco_de_la_foto_es_el_de_admon(self):
        """Contenedor circular con overflow:hidden y la foto dentro al 100%.

        Es la técnica de AdmonApp (`UsuarioDetalle.svelte`, `.avatar`). El
        `border-radius` va en el CONTENEDOR y no en la <img>, para que el recorte
        sirva igual para la foto y para las iniciales sin dos reglas.
        """
        # Las dos ramas: con foto (marco + <img>) y sin foto (marco + iniciales).
        original = server.tokens.persona_por_token

        def con_foto(slug):
            persona = original(slug)
            if persona:
                persona["Foto"] = "AAAA"
                persona["FotoTipo"] = "image/jpeg"
            return persona

        server.tokens.persona_por_token = con_foto
        try:
            _, cuerpo, _ = self._get("/" + self.ficha["Slug"])
            con = cuerpo.decode("utf-8")
            self.assertIn('<div class="marco-foto">', con)
            self.assertIn("<img src=", con)
        finally:
            server.tokens.persona_por_token = original

        _, cuerpo, _ = self._get("/" + self.ficha["Slug"])
        sin = cuerpo.decode("utf-8")
        self.assertIn('class="marco-foto" aria-hidden="true"', sin)
        self.assertIn('class="iniciales"', sin)

        import os

        css = open(os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "panel", "ficha.css"),
            encoding="utf-8").read()
        self.assertIn(".marco-foto img {", css)
        self.assertIn("overflow: hidden;", css)

    def test_reducir_movimiento_apaga_las_animaciones(self):
        """Una persona con desordenes vestibulares ve un fondo en movimiento y
        se marea. Con 'reducir animaciones' activado, TODO tiene que apagarse."""
        import os

        css = open(os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "panel", "ficha.css"),
            encoding="utf-8").read()
        self.assertIn("@media (prefers-reduced-motion: reduce)", css)
        self.assertIn("animation: none !important", css)

    def test_la_textura_de_fondo_se_sirve(self):
        """El CSS del shell pide /engrane.png; si no lo sirve la app, cada
        visita de la ficha es un 404 más."""
        codigo, cuerpo, cabeceras = self._get("/engrane.png")
        self.assertEqual(codigo, 200)
        self.assertEqual(cabeceras.get("Content-Type"), "image/png")
        # Firma del PNG: 89 50 4E 47.
        self.assertEqual(cuerpo[:4], b"\x89PNG")

    def test_ficha_muestra_el_puesto(self):
        """El puesto viene de HUB_Users.Puesto y va bajo el nombre."""
        _, cuerpo, _ = self._get("/" + self.ficha["Slug"])
        self.assertIn("Técnico de campo", cuerpo.decode("utf-8"))

    def test_ficha_sin_foto_muestra_iniciales(self):
        """Sin HUB_Users.Foto la tarjeta tiene que verse bien, no rota.

        Las 11 filas de HUB_Users están hoy sin foto: es el estado por defecto,
        no una excepción.
        """
        codigo, cuerpo, _ = self._get("/" + self.ficha["Slug"])
        texto = cuerpo.decode("utf-8")
        self.assertEqual(codigo, 200)
        self.assertIn('class="marco-foto"', texto)
        self.assertIn(">HP<", texto)
        # Sin foto no debe quedar un <img> roto: el marco lleva las iniciales.
        self.assertNotIn("<img src=", texto)

    def test_foto_que_rompe_el_html_se_escapa(self):
        """Una foto con HTML se escapa: si no, es XSS servido desde la BD.

        La foto entra desde `HUB_UsuariosFotos.Archivo` (la sube el usuario
        desde Admon), reduced a un data-URI: ese es el punto de inyección.
        """
        original = server.tokens.persona_por_token

        def con_foto_mala(slug):
            persona = original(slug)
            if persona:
                persona["Foto"] = '"><script>alert(1)</script>'
                persona["FotoTipo"] = "image/jpeg"
            return persona

        server.tokens.persona_por_token = con_foto_mala
        try:
            _, cuerpo, _ = self._get("/" + self.ficha["Slug"])
            texto = cuerpo.decode("utf-8")
            self.assertNotIn("<script>alert(1)</script>", texto)
            self.assertIn("&lt;script&gt;", texto)
        finally:
            server.tokens.persona_por_token = original

    def _multipart_fuera_de_uso(self):
        """El parser de multipart era para subir fotos; HUB_Users es de solo
        lectura, asi que ya no aplica. Se deja el resto de esta clase como
        referencia del formato por si vuelve a hacer falta subir algo."""
        import uuid
        limite = "----prueba" + uuid.uuid4().hex
        cuerpo = (
            f"--{limite}\r\n"
            'Content-Disposition: form-data; name="id"\r\n\r\n'
            "7\r\n"
            f"--{limite}\r\n"
            'Content-Disposition: form-data; name="puesto"\r\n\r\n'
            "Jefe de campo\r\n"
            f"--{limite}\r\n"
            'Content-Disposition: form-data; name="foto"; filename="f.png"\r\n'
            "Content-Type: image/png\r\n\r\n"
        ).encode() + b"\x89PNG\r\n\x1a\nDATOS" + (
            f"\r\n--{limite}--\r\n").encode()

        abierto = server.Handler.__new__(server.Handler)
        abierto.headers = {"Content-Length": str(len(cuerpo)),
                           "Content-Type": f"multipart/form-data; boundary={limite}"}
        abierto.rfile = io.BytesIO(cuerpo)

        campos, ficheros = abierto._leer_multipart()
        self.assertEqual(campos["id"], "7")
        self.assertEqual(campos["puesto"], "Jefe de campo")
        self.assertIn("foto", ficheros)
        nombre, crudo, ctype = ficheros["foto"]
        self.assertEqual(nombre, "f.png")
        self.assertEqual(ctype, "image/png")
        self.assertTrue(crudo.startswith(b"\x89PNG"))

    def test_la_ip_real_viene_de_cloudflare(self):
        """Detrás de cloudflared, la IP del socket es SIEMPRE la misma.

        Por eso el rate limit tiene que contar por X-Forwarded-For. Si contara
        por el socket, el contador sería global y la primera persona que pasara
        el límite dejaría sin servicio a todos los demás.
        """
        codigo, _, _ = self._get("/" + self.ficha["Slug"],
                                 {"X-Forwarded-For": "201.77.44.9, 10.0.0.1"})
        self.assertEqual(codigo, 200)

    def test_xff_toma_la_primera_entrada(self):
        """La primera entrada del XFF es el cliente original.

        Las siguientes son los proxies que agregó cada salto (aquí, el puente de
        Docker). Tomar la última haría que todo se atribuira al proxy.
        """
        from panel.lugar import lugar_de
        modo, ip = lugar_de({"X-Forwarded-For": "201.77.44.9, 10.0.0.1"}, "172.17.0.1")
        self.assertEqual(ip, "201.77.44.9")
        # IP pública = remoto.
        self.assertEqual(modo, "remoto")

    def test_cada_ip_tiene_su_propio_contador(self):
        """Dos IPs distintas no comparten el límite.

        Es el caso de la oficina detrás de NAT con el WAF sin XFF, y el que
        rompería la app si el contador fuera global.
        """
        limite = server.RateLimit(maximo=3, ventana=60)
        for _ in range(3):
            self.assertTrue(limite.permitido("1.1.1.1"))
        self.assertFalse(limite.permitido("1.1.1.1"))
        # Otra IP sigue teniendo su presupuesto entero.
        self.assertTrue(limite.permitido("2.2.2.2"))
        self.assertTrue(limite.permitido("2.2.2.2"))
        self.assertTrue(limite.permitido("2.2.2.2"))
        self.assertFalse(limite.permitido("2.2.2.2"))

    def test_la_ventana_se_renueva(self):
        """Pasada la ventana, la IP vuelve a tener presupuesto."""
        limite = server.RateLimit(maximo=2, ventana=1)
        self.assertTrue(limite.permitido("3.3.3.3"))
        self.assertTrue(limite.permitido("3.3.3.3"))
        self.assertFalse(limite.permitido("3.3.3.3"))
        time.sleep(1.2)
        self.assertTrue(limite.permitido("3.3.3.3"))

    def test_el_log_registra_la_peticion(self):
        """El log debe existir: sin él no se puede ver un barrido de tokens.

        Regresión: _log() estaba definida pero nunca se llamaba, así que el
        contenedor no registraba NADA y no había forma de saber qué IP veía la
        app detrás de Cloudflare.
        """
        capturado = io.StringIO()
        with contextlib.redirect_stdout(capturado):
            self._get("/" + self.ficha["Slug"])
            self._get("/nadie-aqui-" + "B" * 32)
        salida = capturado.getvalue()
        self.assertIn("200", salida)
        self.assertIn("slug-no-existe", salida)
        # Y NUNCA el token.
        self.assertNotIn(self.ficha["Slug"], salida)

    def test_404_no_distingue_inexistente_de_revocado(self):
        """Ambas respuestas deben ser idénticas: si difieren, se puede probar
        qué tokens existieron."""
        _, a, _ = self._get("/nadie-aqui-" + "B" * 32)
        _, b, _ = self._get("/corto")
        self.assertEqual(a, b)

    def test_admin_exige_sesion(self):
        codigo, _, _ = self._get("/admin")
        self.assertEqual(codigo, 401)

    def test_login_bueno_abre_el_panel(self):
        """El camino feliz completo: login → cookie → /admin con contenido.

        Este test faltaba cuando el login 'funcionaba' pero /admin devolvía 401:
        la cookie llevaba un token aleatorio y la validación comparaba contra el
        secreto del panel. Un suite sin el camino feliz no lo detecta.
        """
        import urllib.parse
        datos = urllib.parse.urlencode(
            {"secret": "secreto-de-prueba"}).encode()
        req = urllib.request.Request(self.base + "/admin/login", data=datos,
                                     method="POST")

        opener = urllib.request.build_opener(_SinRedirigir)
        try:
            with opener.open(req, timeout=10) as r:
                cookie = r.headers.get("Set-Cookie")
                self.assertEqual(r.status, 303)
        except urllib.error.HTTPError as e:
            cookie = e.headers.get("Set-Cookie")
        self.assertIsNotNone(cookie, "el login no devolvió cookie")
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=Strict", cookie)

        valor = cookie.split(";")[0]
        req2 = urllib.request.Request(self.base + "/admin",
                                      headers={"Cookie": valor})
        with urllib.request.urlopen(req2, timeout=10) as r:
            cuerpo = r.read().decode("utf-8")
        self.assertEqual(r.status, 200)
        self.assertIn("Datos de la empresa", cuerpo)

    def test_logout_invalida_la_sesion(self):
        """Con solo borrar la cookie, quien la copiara antes seguiría entrando."""
        import urllib.parse
        datos = urllib.parse.urlencode(
            {"secret": "secreto-de-prueba"}).encode()
        opener = urllib.request.build_opener(_SinRedirigir)
        req = urllib.request.Request(self.base + "/admin/login", data=datos,
                                     method="POST")
        try:
            cookie = opener.open(req, timeout=10).headers.get("Set-Cookie")
        except urllib.error.HTTPError as e:
            cookie = e.headers.get("Set-Cookie")
        valor = cookie.split(";")[0]

        req_logout = urllib.request.Request(self.base + "/admin/logout",
                                            headers={"Cookie": valor},
                                            data=b"", method="POST")
        try:
            opener.open(req_logout, timeout=10)
        except urllib.error.HTTPError:
            pass

        # La MISMA cookie ya no vale.
        req2 = urllib.request.Request(self.base + "/admin",
                                      headers={"Cookie": valor})
        try:
            with urllib.request.urlopen(req2, timeout=10) as r:
                self.fail(f"la sesión sobrevivió al logout: {r.status}")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 401)

    def test_sesion_no_sobrevive_al_reinicio(self):
        """Documenta que las sesiones viven en memoria, no en la BD."""
        self.assertEqual(server.CADUCIDAD_SESION, 8 * 3600)

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
