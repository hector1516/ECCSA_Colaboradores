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
APP_VERSION = "0.1.1"

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

# Intentos por IP por ventana. No es la defensa principal (esa es el WAF de
# Cloudflare, que filtra antes de llegar aquí) sino el freno local para cuando
# el WAF no está puesto o se salta.
MAX_INTENTOS_POR_VENTANA = 40
VENTANA_SEGUNDOS = 60
