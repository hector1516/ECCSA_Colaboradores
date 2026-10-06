"""
panel/plantillas.py — El HTML de la app (tema oscuro ECCSA)
==========================================================
HTML generado en Python, sin motor de plantillas: la app son dos pantallas
(ficha pública y panel) y meter Jinja para eso sería una dependencia más que
mantener. Los templates del shell (`banner.py.html`, `actions.py.html`) se
respetan como contrato de markup y CSS, pero aquí el shell se pinta en el
servidor, como hace el panel de WorkersAdmon.

CSS: `panel/shell.css` (canónico del shell, propagado por sync_shell.py, NO se
edita a mano) + `panel/ficha.css` (lo propio de esta app).
"""
import html
import os
import urllib.parse

from panel import config
from panel.lugar import lugar_de_ip

_CSS_FILES = ("shell.css", "ficha.css")


def _leer_css():
    base = os.path.dirname(os.path.abspath(__file__))
    out = []
    for nombre in _CSS_FILES:
        try:
            with open(os.path.join(base, nombre), encoding="utf-8") as fh:
                out.append(fh.read())
        except OSError:
            pass
    return "\n\n".join(out)


CSS = _leer_css()


def esc(valor):
    """Escapa para texto y para atributos. Todo dato de la BD pasa por aquí."""
    return html.escape(str(valor if valor is not None else ""), quote=True)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers de enlace
# ─────────────────────────────────────────────────────────────────────────────
def solo_digitos(telefono):
    """Deja el número pelado: '818 123 4567' → '8181234567'.

    Es lo que exigen los enlaces de WhatsApp y los vCard: un espacio o un paréntesis
    hace que wa.me devuelva 404 en el móvil.
    """
    return "".join(c for c in (telefono or "") if c.isdigit())


def url_whatsapp(numero, mensaje=None):
    """Enlace wa.me, o '' si el número no sirve.

    `wa.me` necesita el número con clave de país y sin '+'. Se pone 52 (México)
    cuando el número no trae clave, porque ECCSA solo opera aquí.
    """
    digitos = solo_digitos(numero)
    if not digitos:
        return ""
    if len(digitos) == 10:
        digitos = "52" + digitos
    elif len(digitos) < 10:
        return ""
    url = f"https://wa.me/{digitos}"
    if mensaje:
        url += "?text=" + urllib.parse.quote(mensaje[:200])
    return url


def url_mapa(lat, lon, direccion):
    """Enlace de mapa: coordenadas si las hay, búsqueda por dirección si no.

    Se prefiere el link de búsqueda de Apple sobre el de Google porque en iPhone
    abre la app Mapas nativa, que además tiene la empresa ya guardada de visita
    anterior para varias personas del equipo.
    """
    if lat and lon:
        return (f"https://maps.apple.com/?q={urllib.parse.quote(str(lat))},"
                f"{urllib.parse.quote(str(lon))}")
    if direccion:
        return "https://maps.apple.com/?q=" + urllib.parse.quote(direccion)
    return ""


def url_instagram(usuario):
    """Instagram acepta usuario o URL completa."""
    valor = (usuario or "").strip()
    if not valor:
        return ""
    if valor.startswith("http"):
        return valor
    return "https://instagram.com/" + valor.lstrip("@").strip("/")


def url_facebook(usuario):
    valor = (usuario or "").strip()
    if not valor:
        return ""
    if valor.startswith("http"):
        return valor
    return "https://facebook.com/" + valor.lstrip("@").strip("/")


# ─────────────────────────────────────────────────────────────────────────────
# Chrome común
# ─────────────────────────────────────────────────────────────────────────────
def _cabeza(titulo, descripcion=None, robots=False):
    """<head> con el CSS del shell inline.

    El CSS va inline a propósito: la ficha se abre desde una tarjeta NFC, a
    veces con datos móviles agotados. Un `<link>` externo a un CDN o a un
    archivo aparte es una petición de más que puede fallar y dejar la página
    sin estilos justo en el primer contacto con el cliente.
    """
    meta_robots = ""
    if robots:
        # La ficha no debe indexarse: no es un directorio público, son
        # contactos individuales y no hay nada que un buscador deba listar.
        meta_robots = '<meta name="robots" content="noindex, nofollow">'
    desc = f'<meta name="description" content="{esc(descripcion)}">' if descripcion else ""
    return (
        "<!DOCTYPE html>\n"
        '<html lang="es-MX">\n<head>\n'
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1, '
        'viewport-fit=cover">\n'
        f"{meta_robots}\n{desc}\n"
        '<meta name="theme-color" content="#0F172A">\n'
        '<meta name="apple-mobile-web-app-capable" content="yes">\n'
        f"<title>{esc(titulo)}</title>\n"
        f"<style>\n{CSS}\n</style>\n"
        "</head>\n"
    )


def _pie(scripts=""):
    return (f"{scripts}</body>\n</html>\n")


# ─────────────────────────────────────────────────────────────────────────────
# Ficha pública  (GET /<slug>)
# ─────────────────────────────────────────────────────────────────────────────
def ficha_page(ficha, empresa):
    """La tarjeta de presentación que ve quien toca la NFC."""
    nombre = ficha.get("Nombre") or ""
    email = (ficha.get("Email") or "").strip()
    telefono = (ficha.get("Telefono") or "").strip()
    direccion = empresa.get("colab_empresa_direccion", "")
    nombre_empresa = empresa.get("colab_empresa_nombre", "")
    lat = empresa.get("colab_empresa_latitud", "")
    lon = empresa.get("colab_empresa_longitud", "")
    foto = ficha.get("Foto") or ""
    foto_tipo = ficha.get("FotoTipo") or "image/jpeg"

    # El slug va en la URL de la foto del vCard y en el canonical; el token es
    # un secreto y no debe filtrarse a un tercero por Referer.
    slug = ficha.get("Slug") or ""

    wa = url_whatsapp(empresa.get("colab_empresa_whatsapp") or telefono,
                      f"Hola, te escribo de parte de {nombre}.")
    mapa = url_mapa(lat, lon, direccion)
    sitio = (empresa.get("colab_empresa_sitio") or "").strip()
    if sitio and not sitio.startswith("http"):
        sitio = "https://" + sitio
    ig = url_instagram(empresa.get("colab_empresa_instagram"))
    fb = url_facebook(empresa.get("colab_empresa_facebook"))
    tel_oficina = empresa.get("colab_empresa_telefono", "")

    # ── Identidad ──
    # Markup idéntico al de AdmonApp (UsuarioDetalle.svelte): un contenedor
    # circular con overflow:hidden y la foto dentro al 100% con object-fit:cover.
    # El recorte al centro es lo que deja la cara bien colocada; esta app antes
    # desplazaba el recorte al 28% "para acercar la cara" y quedaba descuadrada.
    if foto:
        # Viene de HUB_UsuariosFotos reducida a 320x320 JPEG, como data-URI: la
        # ficha es una sola página y así no hay una segunda petición por la
        # imagen.
        identidad = (f'<div class="marco-foto">'
                     f'<img src="data:{esc(foto_tipo)};base64,{esc(foto)}" '
                     f'alt="Fotografía de {esc(nombre)}"></div>')
    else:
        # Sin foto: iniciales. Es lo que evita que la tarjeta se vea rota si el
        # usuario nunca subió su foto desde Admon.
        iniciales = "".join(p[0] for p in nombre.split()[:2]).upper() or "?"
        identidad = (f'<div class="marco-foto" aria-hidden="true">'
                     f'<span class="iniciales">{esc(iniciales)}</span></div>')

    # ── Botones de acción ──
    acciones = []
    if telefono:
        acciones.append(
            f'<a class="accion principal" href="tel:{esc(solo_digitos(telefono))}">'
            f'<span classico>📞</span><span>Llamar</span></a>')
    if wa:
        acciones.append(
            f'<a class="accion" href="{esc(wa)}" target="_blank" rel="noopener">'
            f'<span classico>💬</span><span>WhatsApp</span></a>')
    # Guardar contacto: el vCard. `download` es lo que hace que iOS lo ofrezca
    # para agregar en vez de abrirlo como texto.
    acciones.append(
        f'<a class="accion" href="/{esc(slug)}/contacto.vcf" download="{esc(nombre)}.vcf">'
        f'<span classico>👤</span><span>Guardar contacto</span></a>')
    if mapa:
        acciones.append(
            f'<a class="accion" href="{esc(mapa)}" target="_blank" rel="noopener">'
            f'<span classico>📍</span><span>Cómo llegar</span></a>')
    # `--i` es el retardo escalonado de la animación de entrada (ver ficha.css).
    # Sin esto todo saldría a la vez y se pierde el efecto de cascada.
    for i, a in enumerate(acciones):
        acciones[i] = a.replace('<a class="accion',
                                f'<a style="--i:{i}" class="accion')
    acciones_html = "\n".join(acciones)

    # ── Datos de contacto ──
    datos = []
    if email:
        datos.append(
            f'<li><span class="rot">✉️ Correo</span>'
            f'<a class="val" href="mailto:{esc(email)}">{esc(email)}</a></li>')
    if telefono:
        datos.append(
            f'<li><span class="rot">📱 Móvil</span>'
            f'<a class="val" href="tel:{esc(solo_digitos(telefono))}">{esc(telefono)}</a></li>')
    if direccion:
        datos.append(f'<li><span class="rot">🏢 Dirección</span>'
                     f'<span class="val">{esc(direccion)}</span></li>')
    if tel_oficina:
        datos.append(
            f'<li><span class="rot">☎️ Oficina</span>'
            f'<a class="val" href="tel:{esc(solo_digitos(tel_oficina))}">'
            f'{esc(tel_oficina)}</a></li>')
    datos_html = "\n".join(datos)

    # ── Redes ──
    redes = []
    if fb:
        redes.append(f'<a style="--i:0" class="red" href="{esc(fb)}" '
                     f'target="_blank" rel="noopener" aria-label="Facebook">f</a>')
    if ig:
        redes.append(f'<a style="--i:1" class="red ig" href="{esc(ig)}" '
                     f'target="_blank" rel="noopener" aria-label="Instagram">ig</a>')
    if sitio:
        redes.append(f'<a style="--i:2" class="red web" href="{esc(sitio)}" '
                     f'target="_blank" rel="noopener" aria-label="Sitio web">🌐</a>')
    redes_html = ("\n".join(redes)
                  if redes else '<span class="sin-redes">Sin redes configuradas</span>')

    empresa_html = ""
    puesto = (ficha.get("Puesto") or "").strip()
    if nombre_empresa or direccion or puesto:
        empresa_html = (
            f'<div class="empresa">'
            f'<div class="emp-nombre">{esc(nombre_empresa)}</div>'
            f'<div class="emp-dir">{esc(direccion)}</div>'
            f'<div class="redes">{redes_html}</div>'
            f'</div>')

    return (
        _cabeza(nombre or "Colaborador",
                descripcion=f"Datos de contacto de {nombre} en {nombre_empresa}",
                robots=True)
        + '<body class="ficha">\n'
        + '<main class="tarjeta">\n'
        # Los retardos escalonados (0…4) van en el HTML porque la animación es
        # CSS puro: sin JavaScript, `--i` es la única forma de escalonar.
        + f'  <div class="identidad anima" style="--i:0">{identidad}'
        + f'<h1 class="nombre">{esc(nombre)}</h1>'
        + (f'<p class="puesto">{esc(puesto)}</p>' if puesto else "")
        + (f'<p class="empresa-nombre">{esc(nombre_empresa)}</p>'
           if nombre_empresa else "")
        + '</div>\n'
        + f'  <div class="acciones" style="--i:1">{acciones_html}</div>\n'
        + (f'  <ul class="datos anima" style="--i:2">{datos_html}</ul>\n'
           if datos else "")
        + (f'  {empresa_html}\n' if empresa_html else "")
        + '</main>\n'
        + '<footer class="pie">'
        + f'<span>{esc(config.APP_NAME)} v{esc(config.APP_VERSION)}</span>'
        + '</footer>\n'
        # Sin JS. La ficha se abre con un dedo pegado a una tarjeta; si el JS
        # falla o tarda, la página tiene que servirse igual.
        + _pie()
    )


def no_encontrado_page():
    """404.

    Es la MISMA respuesta para un token que no existe y para uno dado de baja.
    Distinguirlas confirmaría a quien escanea URLs que ese token existió, y por
    ende que hubo una persona ahí.
    """
    return (
        _cabeza("No encontrado", robots=True)
        + '<body class="ficha error">\n'
        + '<main class="tarjeta">\n'
        + '  <div class="identidad"><div class="marco-foto">'
        + '<span class="iniciales">?</span></div>'
        + '<h1 class="nombre">Ficha no encontrada</h1>'
        + '<p class="puesto">El enlace puede no ser válido o la tarjeta haber '
        + 'sido dada de baja.</p></div>\n'
        + '</main>\n'
        + _pie()
    )


def error_page(mensaje="Algo salió mal"):
    return (
        _cabeza("Error", robots=True)
        + '<body class="ficha error">\n'
        + '<main class="tarjeta"><div class="identidad">'
        + '<div class="marco-foto"><span class="iniciales">!</span></div>'
        + f'<h1 class="nombre">{esc(mensaje)}</h1>'
        + '<p class="puesto">Intenta de nuevo en un momento.</p>'
        + '</div></main>\n'
        + _pie()
    )
