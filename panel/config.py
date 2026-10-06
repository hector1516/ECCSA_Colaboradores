"""
panel/config.py — Configuración central de la app
================================================
Único lugar con puertos, rutas, versión y constantes. Todo sobreescribible por
variable de entorno para que el mismo código corra en el contenedor (/app) y en
local (el repo tal cual).
"""
import os

APP_ID = "colaboradores"
APP_NAME = "Colaboradores"
# Versión de la app. Fuente ÚNICA: el banner la lee de aquí y el CHANGELOG la
# tiene que repetir — tools/check_changelog.py falla si no coinciden.
APP_VERSION = "0.3.3"

# Puerto interno del contenedor. El host lo mapea en /opt/apps/colaboradores/app.conf.
PORT = int(os.environ.get("PORT", "8000"))

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PANEL_DIR = os.path.join(BASE, "panel")

# ─── Datos ───────────────────────────────────────────────────────────────────
DATA_DIR = os.environ.get("DATA_DIR", "/data")


def get_data_dir():
    """Directorio persistente, con respaldo a un temporal si /data no existe."""
    for candidate in (DATA_DIR, os.path.join(BASE, "data")):
        try:
            os.makedirs(candidate, exist_ok=True)
            if os.access(candidate, os.W_OK):
                return candidate
        except Exception:
            continue
    return "/tmp"


DATA = get_data_dir()

# El archivo con el secreto de emisión de tarjetas. Vive en el volumen, fuera
# del repo: quien tenga el volumen puede reemitir tokens, quien tenga el repo
# no. Por eso NO se hardcodea aquí.
SECRET_FILE = os.path.join(DATA, "admin_secret.txt")

# Secreto de DERIVACIÓN de los tokens de las fichas. Va aparte del del panel a
# propósito: rotar la contraseña del panel no debe invalidar las tarjetas NFC ya
# impresas, que son plástico y no se reescriben. Y al revés: rotar este
# invalida TODAS las tarjetas, porque el token sale de aquí.
FICHA_SECRET_FILE = os.path.join(DATA, "ficha_secret.txt")


def admin_secret():
    """Secreto del panel, o '' si no hay.

    Sin secreto, el panel NO arranca (ver server.py): es preferible que la app
    no levante a que quede con tokens firmados con una cadena vacía.
    """
    try:
        with open(SECRET_FILE, encoding="utf-8") as fh:
            return fh.read().strip()
    except OSError:
        return ""


def ficha_secreto():
    """Secreto de derivación de los tokens, o '' si no existe.

    Se lee de `HUB_Config` (clave `colab_ficha_secreto`) y NO del archivo del
    volumen, porque Admon tiene que calcular el MISMO token para poder mostrar
    el enlace de cada persona en "Administración de usuarios". Con el secreto
    solo en el volumen, Admon no podría derivarlo y habría que preguntarle a
    esta app por red — con su propio secreto de autenticación y caída si esta
    app no está arriba.

    El archivo del volumen queda como RESPALDO para un despliegue que llegue
    antes que la migración `0060`: sin él, ninguna ficha tendría token.
    """
    try:
        from panel import db as _db
        valor = _db.obtener_config("colab_ficha_secreto")
        if valor:
            return valor
    except Exception:
        pass
    try:
        with open(FICHA_SECRET_FILE, encoding="utf-8") as fh:
            return fh.read().strip()
    except OSError:
        return ""


def shell_version():
    """Versión del shell estampada por tools/sync_shell.py al propagar."""
    try:
        with open(os.path.join(BASE, "ECCSA_SHELL_VERSION"), encoding="utf-8") as fh:
            return fh.read().strip()
    except OSError:
        return "?"


# ─── Límites ─────────────────────────────────────────────────────────────────
# El slug es de 32 caracteres. Poner el tope evita que alguien mande un string
# gigante y lo compare contra el índice.
MAX_SLUG_LEN = 64

# La ficha pública la abre UNA persona, un par de veces: 60/min es de sobra y
# deja margen para un grupo grande detrás de la MISMA IP de NAT (la oficina
# entera comparte una salida a internet; sin X-Forwarded-For, todos
# compartirían el mismo contador).
#
# El freno fuerte NO es este número: es el WAF de Cloudflare (§3 del manual),
# que filtra antes de que la petición llegue al contenedor y ve la IP real sin
# pasar por el proxy. Este límite es la red de seguridad para cuando el WAF no
# está puesto o se salta.
MAX_INTENTOS_POR_VENTANA = 60
VENTANA_SEGUNDOS = 60
