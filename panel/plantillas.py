"""
panel/plantillas.py — El HTML de la app (rediseño premium)
==========================================================
HTML generado en Python, sin motor de plantillas.

CSS: panel/shell.css (canónico) + panel/ficha.css + panel/ficha_premium.css
"""

import html
import os
import urllib.parse
import math

from panel import config
from panel.lugar import lugar_de_ip


_CSS_FILES = ("shell.css", "ficha.css", "ficha_premium.css")


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
    """Escapa para texto y para atributos."""
    return html.escape(str(valor if valor is not None else ""), quote=True)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers de enlace
# ─────────────────────────────────────────────────────────────────────────────
def solo_digitos(telefono):
    return "".join(c for c in (telefono or "") if c.isdigit())


def url_whatsapp(numero, mensaje=None):
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


def url_mapa(lat, lon, direccion, enlace_corto=""):
    if enlace_corto:
        return enlace_corto if enlace_corto.startswith("http") \
            else "https://" + enlace_corto
    if lat and lon:
        return ("https://www.google.com/maps/search/?api=1&query="
                + urllib.parse.quote(f"{lat},{lon}"))
    if direccion:
        return ("https://www.google.com/maps/search/?api=1&query="
                + urllib.parse.quote(direccion))
    return ""


def url_instagram(usuario):
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
    meta_robots = ""
    if robots:
        meta_robots = '<meta name="robots" content="noindex, nofollow">'
    desc = f'<meta name="description" content="{esc(descripcion)}">' if descripcion else ""
    return (
        "<!DOCTYPE html>\n"
        '<html lang="es-MX">\n<head>\n'
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1, '
        'viewport-fit=cover">\n'
        f"{meta_robots}\n{desc}\n"
        '<meta name="theme-color" content="#0c1222">\n'
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
    """Tarjeta de presentación premium — rediseño completo."""
    nombre = ficha.get("Nombre") or ""
    email = (ficha.get("Email") or "").strip()
    telefono = (ficha.get("Telefono") or "").strip()
    direccion = empresa.get("colab_empresa_direccion", "")
    nombre_empresa = empresa.get("colab_empresa_nombre", "")
    lat = empresa.get("colab_empresa_latitud", "")
    lon = empresa.get("colab_empresa_longitud", "")
    foto = ficha.get("Foto") or ""
    foto_tipo = ficha.get("FotoTipo") or "image/jpeg"

    slug = ficha.get("Slug") or ""

    wa = url_whatsapp(empresa.get("colab_empresa_whatsapp") or telefono,
                      f"Hola, te escribo de parte de {nombre}.")
    mapa = url_mapa(lat, lon, direccion,
                    (empresa.get("colab_empresa_mapa_url") or "").strip())
    sitio = (empresa.get("colab_empresa_sitio") or "").strip()
    if sitio and not sitio.startswith("http"):
        sitio = "https://" + sitio
    ig = url_instagram(empresa.get("colab_empresa_instagram"))
    fb = url_facebook(empresa.get("colab_empresa_facebook"))
    tel_oficina = empresa.get("colab_empresa_telefono", "")

    # ── Identidad ──
    if foto:
        identidad = (f'<div class="marco-foto">'
                     f'<img src="data:{esc(foto_tipo)};base64,{esc(foto)}" '
                     f'alt="Fotografía de {esc(nombre)}">'
                     f'<span class="vida" aria-hidden="true"></span></div>')
    else:
        iniciales = "".join(p[0] for p in nombre.split()[:2]).upper() or "?"
        identidad = (f'<div class="marco-foto" aria-hidden="true">'
                     f'<span class="iniciales">{esc(iniciales)}</span></div>')

    # ── Botones de acción ──
    acciones = []
    if telefono:
        acciones.append(
            f'<a class="accion principal" href="tel:{esc(solo_digitos(telefono))}">'
            f'<span class="accion-icon">📞</span><span>Llamar</span></a>')
    if wa:
        acciones.append(
            f'<a class="accion" href="{esc(wa)}" target="_blank" rel="noopener">'
            f'<span class="accion-icon">💬</span><span>WhatsApp</span></a>')
    acciones.append(
        f'<a class="accion" href="/{esc(slug)}/contacto.vcf" download="{esc(nombre)}.vcf">'
        f'<span class="accion-icon">👤</span><span>Guardar</span></a>')
    if mapa:
        acciones.append(
            f'<a class="accion" href="{esc(mapa)}" target="_blank" rel="noopener">'
            f'<span class="accion-icon">📍</span><span>Cómo llegar</span></a>')
    for i, a in enumerate(acciones):
        acciones[i] = a.replace('<a class="accion',
                                f'<a style="--i:{i}" class="accion')
    acciones_html = "\n".join(acciones)

    # ── Datos de contacto ──
    contact_items = []
    if email:
        contact_items.append(
            f'<div class="contact-item">'
            f'<div class="contact-icon">✉️</div>'
            f'<div class="contact-info">'
            f'<div class="contact-label">Correo</div>'
            f'<a class="contact-value" href="mailto:{esc(email)}">{esc(email)}</a>'
            f'</div></div>')
    if telefono:
        contact_items.append(
            f'<div class="contact-item">'
            f'<div class="contact-icon">📱</div>'
            f'<div class="contact-info">'
            f'<div class="contact-label">Móvil</div>'
            f'<a class="contact-value" href="tel:{esc(solo_digitos(telefono))}">{esc(telefono)}</a>'
            f'</div></div>')
    if tel_oficina:
        contact_items.append(
            f'<div class="contact-item">'
            f'<div class="contact-icon">☎️</div>'
            f'<div class="contact-info">'
            f'<div class="contact-label">Oficina</div>'
            f'<a class="contact-value" href="tel:{esc(solo_digitos(tel_oficina))}">{esc(tel_oficina)}</a>'
            f'</div></div>')
    if direccion:
        contact_items.append(
            f'<div class="contact-item">'
            f'<div class="contact-icon">🏢</div>'
            f'<div class="contact-info">'
            f'<div class="contact-label">Dirección</div>'
            f'<span class="contact-value">{esc(direccion)}</span>'
            f'</div></div>')
    contact_html = "\n".join(contact_items)

    # ── Stats ──
    stats = ficha.get("Stats") or {}
    ovr = stats.get("ovr", 50)
    posicion = stats.get("posicion", "Colaborador")
    tier = stats.get("tier", "Bronce")
    anos_empresa = stats.get("anos_empresa", 0)
    experiencia = stats.get("experiencia", 0)

    attrs = [
        ("PRO", stats.get("productividad", 50), "Productividad"),
        ("VEN", stats.get("ventas", 50), "Ventas"),
        ("ASI", stats.get("asistencia", 50), "Asistencia"),
        ("PUN", stats.get("puntualidad", 50), "Puntualidad"),
        ("KM", stats.get("kilometros", 50), "Kilómetros"),
        ("LEG", stats.get("legends", 50), "Legends"),
        ("COL", stats.get("colaboracion", 50), "Colaboración"),
        ("EFI", stats.get("eficiencia", 50), "Eficiencia"),
    ]

    # Stat bars HTML
    stat_bars = ""
    for code, val, name in attrs:
        cls = "teal" if code in ("KM", "LEG", "COL") else ""
        stat_bars += (
            f'<div class="stat-bar">'
            f'<div class="stat-bar-header">'
            f'<span class="stat-bar-code">{code}</span>'
            f'<span class="stat-bar-name">{name}</span>'
            f'<span class="stat-bar-value">{val}</span>'
            f'</div>'
            f'<div class="stat-bar-track">'
            f'<div class="stat-bar-fill {cls}" style="width:{val}%"></div>'
            f'</div></div>\n'
        )

    # ── Empresa ──
    redes = []
    if fb:
        redes.append(f'<a class="red" href="{esc(fb)}" target="_blank" rel="noopener" aria-label="Facebook">f</a>')
    if ig:
        redes.append(f'<a class="red" href="{esc(ig)}" target="_blank" rel="noopener" aria-label="Instagram">ig</a>')
    if sitio:
        redes.append(f'<a class="red" href="{esc(sitio)}" target="_blank" rel="noopener" aria-label="Sitio web">🌐</a>')
    redes_html = "\n".join(redes) if redes else '<span style="color:var(--text-muted);font-size:0.75rem;">Sin redes</span>'

    empresa_html = ""
    puesto = (ficha.get("Puesto") or "").strip()
    if nombre_empresa or direccion or puesto:
        empresa_html = (
            f'<div class="empresa">'
            f'<div class="emp-nombre">{esc(nombre_empresa)}</div>'
            f'<div class="emp-dir">{esc(direccion)}</div>'
            f'<div class="redes">{redes_html}</div>'
            f'</div>')

    # ── Hero experience ──
    experience_html = ""
    if anos_empresa > 0:
        experience_html = (
            f'<div class="hero-experience">'
            f'<span class="exp-num">{anos_empresa}</span>'
            f'<span>años en ECCSA</span>'
            f'</div>')

    return (
        _cabeza(nombre or "Colaborador",
                descripcion=f"Perfil profesional de {nombre} - ECCSA Automation",
                robots=True)
        + '<body class="profile-page">\n'
        + '<div class="profile-bg" aria-hidden="true"></div>\n'
        + '<div class="particulas" aria-hidden="true">\n'
        + '<span class="particula"></span>\n'
        + '<span class="particula"></span>\n'
        + '<span class="particula"></span>\n'
        + '<span class="particula"></span>\n'
        + '<span class="particula"></span>\n'
        + '</div>\n'
        + '<main class="profile-container">\n'
        # === HERO ===
        + '  <div class="hero">\n'
        + f'    <div class="hero-avatar"><div class="ring"></div>{identidad}</div>\n'
        + f'    <h1 class="hero-name">{esc(nombre)}</h1>\n'
        + (f'    <p class="hero-puesto">{esc(puesto)}</p>\n' if puesto else "")
        + (f'    <p class="hero-empresa">{esc(nombre_empresa)}</p>\n' if nombre_empresa else "")
        + f'    <div class="hero-tier tier-{tier.lower()}">{tier}</div>\n'
        + experience_html + '\n'
        + '  </div>\n'
        # === STATS ===
        + '  <div class="stats-section">\n'
        + '    <div class="stats-header">\n'
        + '      <span class="stats-title">Estadísticas</span>\n'
        + '      <div class="ovr-badge">\n'
        + f'        <span class="ovr-number">{ovr}</span>\n'
        + f'        <div><span class="ovr-label">OVR</span><br><span class="ovr-position">{esc(posicion)}</span></div>\n'
        + '      </div>\n'
        + '    </div>\n'
        + stat_bars
        + '    <div class="extra-stats">\n'
        + f'      <span>🔥 Racha: {stats.get("racha", 0)}d</span>\n'
        + f'      <span>📋 {stats.get("reportes_mes", 0)} reportes</span>\n'
        + f'      <span>⭐ {stats.get("nivel_legends", "Bronce")}</span>\n'
        + '    </div>\n'
        + '  </div>\n'
        # === ACTIONS ===
        + '  <div class="profile-actions">\n'
        + f'    {acciones_html}\n'
        + '  </div>\n'
        # === CONTACT ===
        + (f'  <div class="profile-contact">\n{contact_html}\n  </div>\n' if contact_html else "")
        + (f'  {empresa_html}\n' if empresa_html else "")
        + '</main>\n'
        + '<footer class="pie">\n'
        + '<span>Colaboradores v0.5.1</span>\n'
        + '</footer>\n'
        + _pie()
    )


def no_encontrado_page():
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