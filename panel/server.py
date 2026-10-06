"""
panel/server.py — Servidor HTTP
================================
Rutas:

  GET  /healthz                  → "ok" (sondeo, sin auth, sin BD)
  GET  /api/shell/state          → JSON del contrato del banner (sin sesión)
  GET  /robots.txt               → robots que bloquea todo (no hay nada público)

  ── Ficha pública (sin sesión; el token ES la autorización) ──
  GET  /<slug>                   → la ficha
  GET  /<slug>/contacto.vcf      → vCard para guardar el contacto

  ── Panel privado (sesión por cookie) ──
  GET  /admin                    → lista de usuarios + emisión de tokens
  POST /admin/login              → login
  POST /admin/logout             → logout
  POST /admin/emitir             → emite o reactiva la ficha de un usuario
  POST /admin/revocar            → da de baja la ficha
  POST /admin/empresa            → guarda los datos de la empresa

Server: `http.server` de la biblioteca estándar. Es deliberado: la app pública
recibe un GET y devuelve HTML o un vCard, y el panel son formularios POST. Meter
FastAPI/uvicorn sería un framework y un proceso más para no ganar nada.

Rate limit
----------
`RateLimit` es el freno LOCAL: 40 peticiones por IP y por minuto. No es la
defensa principal — esa es el WAF de Cloudflare, que filtra antes de que la
petición llegue aquí, y es la que hay que configurar en el túnel (§3 del manual).
Este límite existe para dos casos: el WAF todavía no está puesto, y el tráfico
de una IP concreta se sale de control.
"""
import hmac
import json
import os
import secrets
import sys
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from panel import config, db, plantillas, tokens
from panel.lugar import lugar_de
from panel.vcard import construir_vcard

MAX_BODY = 256 * 1024        # un formulario de empresa da kilobytes, no megas
COOKIE_SESION = "colab_sesion"


# ─────────────────────────────────────────────────────────────────────────────
# Rate limit por IP
# ─────────────────────────────────────────────────────────────────────────────
class RateLimit:
    """Ventana deslizante por IP, en memoria.

    Es memoria y no tabla a propósito: si el contenedor se reinicia, el contador
    vuelve a cero, y eso es aceptable — el WAF es quien debe aguantar un
    barrido de verdad. Lo que sí importa es que sea thread-safe, porque
    ThreadingHTTPServer atiende cada petición en su hilo y una lista sin candado
    se corrompe con dos escrituras a la vez.
    """

    def __init__(self, maximo, ventana):
        self.maximo = maximo
        self.ventana = ventana
        self._hits = {}
        self._lock = __import__("threading").Lock()

    def permitido(self, ip):
        ahora = time.monotonic()
        with self._lock:
            lista = [t for t in self._hits.get(ip, []) if ahora - t < self.ventana]
            if len(lista) >= self.maximo:
                self._hits[ip] = lista
                return False
            lista.append(ahora)
            self._hits[ip] = lista
            # Poda: sin esto el dict crece con cada IP vista para siempre y un
            # escáner de IPs distintas lo vuelve un problema de memoria.
            if len(self._hits) > 4096:
                for k in [k for k, v in self._hits.items()
                          if not any(ahora - t < self.ventana for t in v)]:
                    del self._hits[k]
            return True


RATE = RateLimit(config.MAX_INTENTOS_POR_VENTANA, config.VENTANA_SEGUNDOS)


# ─────────────────────────────────────────────────────────────────────────────
# Sesión del panel
# ─────────────────────────────────────────────────────────────────────────────
def _sesion_valida(cookie):
    """True si la cookie es el secreto del panel (comparación en tiempo constante).

    `hmac.compare_digest` y no `==`: con `==` el tiempo de respuesta depende de
    cuántos caracteres correctos lleva, y eso filtra el secreto byte a byte.
    """
    secreto = config.admin_secret()
    if not secreto or not cookie:
        return False
    return hmac.compare_digest(str(cookie), secreto)


def nueva_sesion():
    """Token de sesión nuevo. Se regenera al hacer login, no es estático."""
    return secrets.token_urlsafe(32)


class Handler(BaseHTTPRequestHandler):
    server_version = "ECCSA_Colaboradores/0.1"

    # El log por defecto escribe una línea por petición CON la ruta completa, y
    # la ruta ES el token. Los tokens acabarían en el log del contenedor, que
    # es un sitio donde se leen más ojos de los que deberían. Se registra el
    # método, el código y la IP, nunca la ruta.
    def log_message(self, fmt, *args):
        pass

    def _log(self, metodo, codigo, ip, detalle=""):
        print(f"[http] {metodo} {codigo} ip={ip} {detalle}", flush=True)

    # ── respuestas ───────────────────────────────────────────────────────────
    def _enviar(self, codigo, cuerpo, ctype="text/html; charset=utf-8", extra=None):
        datos = cuerpo if isinstance(cuerpo, bytes) else cuerpo.encode("utf-8")
        cabeceras = [
            ("Content-Type", ctype),
            ("Content-Length", str(len(datos))),
            # La ficha es de una persona viva: ni el navegador ni un proxy
            # intermedio deben guardarse una copia en un disco.
            ("Cache-Control", "no-store, max-age=0"),
            ("X-Content-Type-Options", "nosniff"),
            # DENY y no SAMEORIGIN: nadie mete esta ficha en un iframe de otra
            # web para hacer clic-jacking sobre el botón de llamar.
            ("X-Frame-Options", "DENY"),
            ("Referrer-Policy", "no-referrer"),
            # El token viaja en la URL; si esta respuesta se guarda en una
            # caché compartida, el token queda en un disco que no controlamos.
            ("Vary", "Cookie"),
        ]
        for k, v in (extra or []):
            cabeceras.append((k, v))
        self.send_response(codigo)
        for k, v in cabeceras:
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(datos)

    def _redirigir(self, destino, cookie=None):
        extra = [("Location", destino)]
        if cookie:
            extra.append(("Set-Cookie", cookie))
        self._enviar(303, "", extra=extra)

    def _error(self, codigo, ip, detalle=""):
        self._log(self.command, codigo, ip, detalle)

    def _cookies(self):
        cruda = self.headers.get("Cookie") or ""
        salida = {}
        for trozo in cruda.split(";"):
            if "=" in trozo:
                k, _, v = trozo.partition("=")
                salida[k.strip()] = v.strip()
        return salida

    def _leer_form(self):
        largo = int(self.headers.get("Content-Length") or 0)
        if largo <= 0 or largo > MAX_BODY:
            return {}
        crudo = self.rfile.read(largo).decode("utf-8", "replace")
        return {k: v[0] for k, v in urllib.parse.parse_qs(crudo, keep_blank_values=True).items()}

    # ── GET ───────────────────────────────────────────────────────────────────
    def do_GET(self):
        ip = lugar_de(self.headers, self.client_address[0])[1]
        ruta = urllib.parse.urlparse(self.path).path

        if ruta == "/healthz":
            # Sin BD a propósito: un sondeo que se cuelga por la base reporta
            # la app como caída cuando lo que está caído es SQL Server.
            return self._enviar(200, "ok", "text/plain; charset=utf-8")

        if ruta == "/robots.txt":
            # No hay nada público que indexar. Las fichas son de personas
            # concretas y viven detrás de un token.
            return self._enviar(
                200,
                "User-agent: *\nDisallow: /\n",
                "text/plain; charset=utf-8")

        if ruta == "/api/shell/state":
            return self._enviar(200, _shell_state(self.headers, ip),
                                "application/json; charset=utf-8")

        if not RATE.permitido(ip):
            return self._enviar(429, _error_page("Demasiadas peticiones"),
                                extra=[("Retry-After", "60")])

        if ruta == "/admin":
            return self._admin()

        if ruta == "/" or ruta == "":
            # La raíz NO lista a nadie. El alcance acordado es "solo fichas
            # individuales": un índice público expondría el roster completo a
            # quien llegara por el dominio.
            return self._enviar(404, _error_page(), extra=[("Retry-After", "60")])

        # /<slug> y /<slug>/contacto.vcf
        partes = [p for p in ruta.split("/") if p]
        if not partes:
            return self._enviar(404, _error_page())
        slug = partes[0]
        if not tokens.slug_valido(slug):
            # No se distingue "slug con forma rara" de "no existe": mismo 404.
            return self._enviar(404, _error_page())

        ficha = db.obtener_ficha(slug)
        if not ficha:
            return self._enviar(404, _error_page())

        db.registrar_acceso(slug)
        ip_real = ficha.get("_ip") or ip

        if len(partes) == 1:
            empresa = db.obtener_empresa()
            return self._enviar(200, plantillas.ficha_page(ficha, empresa))

        if len(partes) == 2 and partes[1] == "contacto.vcf":
            empresa = db.obtener_empresa()
            vcf = construir_vcard(
                nombre=ficha.get("Nombre"),
                email=ficha.get("Email"),
                telefono=ficha.get("Telefono"),
                empresa=empresa.get("colab_empresa_nombre"),
                direccion=empresa.get("colab_empresa_direccion"),
                sitio=None,
                foto=ficha.get("Foto"),
            )
            return self._enviar(
                200, vcf.encode("utf-8"),
                'text/vcard; charset=utf-8',
                extra=[("Content-Disposition",
                        f'attachment; filename="contacto.vcf"')])

        return self._enviar(404, _error_page())

    def do_HEAD(self):
        self.do_GET()

    # ── POST (todo el panel) ──────────────────────────────────────────────────
    def do_POST(self):
        ip = lugar_de(self.headers, self.client_address[0])[1]
        ruta = urllib.parse.urlparse(self.path).path

        if not RATE.permitido(ip):
            return self._enviar(429, _error_page("Demasiadas peticiones"))

        if ruta == "/admin/login":
            return self._login(ip)
        if ruta == "/admin/logout":
            return self._redirigir("/admin", cookie=f"{COOKIE_SESION}=; Path=/; Max-Age=0")

        # Todo lo demás exige sesión. Se comprueba ANTES de leer el cuerpo, para
        # que un POST sin sesión ni siquiera consuma el request.
        if not _sesion_valida(self._cookies().get(COOKIE_SESION)):
            return self._enviar(401, _error_page("Sin sesión"))
        form = self._leer_form()

        if ruta == "/admin/emitir":
            tokens.emitir(int(form.get("id", 0) or 0))
            return self._redirigir("/admin")
        if ruta == "/admin/revocar":
            tokens.revocar(int(form.get("id", 0) or 0))
            return self._redirigir("/admin")
        if ruta == "/admin/reactivar":
            tokens.reactivar(int(form.get("id", 0) or 0))
            return self._redirigir("/admin")
        if ruta == "/admin/empresa":
            tokens.guardar_empresa(form)
            return self._redirigir("/admin")

        return self._enviar(404, _error_page())

    # ── panel ────────────────────────────────────────────────────────────────
    def _admin(self):
        """El panel: lista de usuarios, emisión de tokens y datos de empresa.

        Es un método (y no una función suelta) porque necesita `self` para leer
        la cookie y para enviar la respuesta.
        """
        if not _sesion_valida(self._cookies().get(COOKIE_SESION)):
            return self._enviar(401, _login_page())
        filas = tokens.listar_usuarios()
        empresa = db.obtener_empresa()
        return self._enviar(200, _admin_page(filas, empresa))

    # ── login ────────────────────────────────────────────────────────────────
    def _login(self, ip):
        form = self._leer_form()
        dado = (form.get("secret") or "").strip()
        secreto = config.admin_secret()
        # Comparación en tiempo constante también en el login, para no filtrar
        # el secreto por el tiempo de respuesta.
        if not secreto or not hmac.compare_digest(dado, secreto):
            self._log("POST", 401, ip, "login fallido")
            return self._enviar(401, _error_page("Secreto incorrecto"))
        cookie = f"{COOKIE_SESION}={nueva_sesion()}; Path=/; HttpOnly; SameSite=Strict"
        return self._redirigir("/admin", cookie=cookie)


def _error_page(mensaje="No encontrado"):
    return (plantillas.no_encontrado_page() if mensaje == "No encontrado"
            else plantillas.error_page(mensaje))


def _shell_state(headers, ip):
    """GET /api/shell/state — contrato del banner (docs/CONTRATO.md).

    Sin sesión, como el kiosco del Dashboard (§2b del contrato): la ficha es
    pública y no hay usuario. `user` va en null y el banner omite ese bloque.

    `headers` se pasa como argumento (y no se usa `self`) para que esta
    función sea un módulo aparte y no dependa de una instancia de Handler.
    """
    lugar = lugar_de(headers, "0.0.0.0")[0]
    estado = {
        "app": {"id": config.APP_ID, "nombre": config.APP_NAME,
                "version": config.APP_VERSION},
        "shell": {"version": config.shell_version()},
        "user": None,
        "sync": {"estado": "idle", "pendientes": 0, "ultimo": None},
        "lugar": {"modo": lugar, "ip": ip},
    }
    return json.dumps(estado, ensure_ascii=False)


def _login_page():
    return (
        plantillas._cabeza("Panel · Colaboradores", robots=True)
        + '<body class="panel"><main class="login">'
        + '<h1>🔐 Panel de fichas</h1>'
        + '<form method="post" action="/admin/login">'
        + '<label>Secreto<input type="password" name="secret" autofocus required></label>'
        + '<button class="btn">Entrar</button>'
        + '</form></main></body></html>'
    )


def _admin_page(filas, empresa):
    base = plantillas._cabeza("Panel · Colaboradores", robots=True)
    cuerpo = ['<body class="panel"><main class="admin">']
    cuerpo.append('<h1>🎴 Fichas de colaborador</h1>')

    filas_html = []
    for f in filas:
        slug = f.get("Slug")
        estado = ("🟢 Activa" if f.get("FichaActivo")
                  else ("⚪ Inactiva" if f.get("FichaId") else "— sin ficha"))
        persona_activa = "Activo" if f.get("Activo") else "🔴 Baja"
        if slug:
            url = f"/{slug}"
            acciones = (
                f'<a class="token" href="{url}" target="_blank">{slug}</a>'
                + (f'<a class="btn mini" href="/{slug}/contacto.vcf">vCard</a>')
                + (f'<form method="post" action="/admin/revocar">'
                   f'<input type="hidden" name="id" value="{f["Id"]}">'
                   f'<button class="btn mini peligro">Revocar</button></form>'
                   if f.get("FichaActivo") else
                   f'<form method="post" action="/admin/reactivar">'
                   f'<input type="hidden" name="id" value="{f["Id"]}">'
                   f'<button class="btn mini">Reactivar</button></form>')
            )
        else:
            acciones = (f'<form method="post" action="/admin/emitir">'
                        f'<input type="hidden" name="id" value="{f["Id"]}">'
                        f'<button class="btn mini">Emitir</button></form>')
        filas_html.append(
            f'<tr><td>{plantillas.esc(f.get("Nombre"))}</td>'
            f'<td>{plantillas.esc(f.get("Email"))}</td>'
            f'<td>{persona_activa}</td><td>{estado}</td>'
            f'<td>{plantillas.esc(f.get("NumAccesos") or 0)}</td>'
            f'<td class="acciones">{acciones}</td></tr>')

    cuerpo.append('<table class="tabla"><thead><tr>'
                  '<th>Nombre</th><th>Correo</th><th>Usuario</th><th>Ficha</th>'
                  '<th>Accesos</th><th>Enlace</th></tr></thead><tbody>'
                  + "\n".join(filas_html) + '</tbody></table>')

    # Formulario de empresa
    def campo(clave, etiqueta, tipo="text"):
        valor = plantillas.esc(empresa.get(clave, ""))
        return (f'<label>{etiqueta}<input type="{tipo}" name="{clave}" '
                f'value="{valor}"></label>')

    cuerpo.append('<h2>🏢 Datos de la empresa</h2>')
    cuerpo.append('<form method="post" action="/admin/empresa" class="empresa-form">'
                  + campo("colab_empresa_nombre", "Nombre")
                  + campo("colab_empresa_direccion", "Dirección")
                  + campo("colab_empresa_telefono", "Teléfono oficina")
                  + campo("colab_empresa_whatsapp", "WhatsApp (con clave de país)")
                  + campo("colab_empresa_facebook", "Facebook")
                  + campo("colab_empresa_instagram", "Instagram")
                  + campo("colab_empresa_latitud", "Latitud", "text")
                  + campo("colab_empresa_longitud", "Longitud", "text")
                  + '<button class="btn">Guardar</button></form>')

    cuerpo.append('<form method="post" action="/admin/logout">'
                  '<button class="btn secundario">Salir</button></form>')
    cuerpo.append('</main></body></html>')
    return base + "\n".join(cuerpo)


# ─────────────────────────────────────────────────────────────────────────────
def main():
    secreto = config.admin_secret()
    if not secreto:
        # Preferible que la app NO levante a que quede emitiendo tokens con una
        # cadena vacía: el login sería público para quien adivine el usuario.
        print(f"[server] ABORTADO: no hay secreto de panel en {config.SECRET_FILE}")
        print("[server] Crea el archivo con un token aleatorio:")
        print(f"[server]   mkdir -p {config.DATA_DIR} && "
              f"python3 -c \"import secrets;print(secrets.token_urlsafe(32))\" "
              f"> {config.SECRET_FILE}")
        sys.exit(1)

    servidor = ThreadingHTTPServer(("0.0.0.0", config.PORT), Handler)
    print(f"[server] {config.APP_NAME} v{config.APP_VERSION} en :{config.PORT}",
          flush=True)
    print(f"[server] shell v{config.shell_version()}", flush=True)
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        servidor.server_close()


if __name__ == "__main__":
    main()
