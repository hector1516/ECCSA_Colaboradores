"""
config_db.py — Resolución de credenciales de la BD (ECCSA_Admon)
==================================================================
Copia del patrón de HUB/field/WorkersAdmon: el orden de precedencia es

    variables de entorno  >  secretos_local.py  >  defaults

Las variables de entorno son lo que usa el contenedor (`app.conf` las pasa con
APP_REQUIRES_ENV), y `secretos_local.py` sirve para correr local sin docker.
`secretos_local.py` está en .gitignore y NUNCA se sube: las credenciales de
producción no viven en el repo.

Mismo orden que config_db.py de HUB y de Field a propósito: las tres apps leen
la misma base y un orden distinto haría que unainek working en local se
comportara distinto en el contenedor.
"""
import os


def _first(*vals):
    """Primer valor-truthy (no vacío, no None), o None."""
    for v in vals:
        if v is not None and str(v).strip():
            return v
    return None


def load_db_config():
    """Devuelve {server, user, password, database} para ECCSA_Admon."""
    default = {
        "server": "10.188.141.15",
        "user": "sa",
        "password": "",
        "database": "ECCSA_Admon",
    }
    try:
        from secretos_local import DB_CONFIG_LOCAL
        default.update(DB_CONFIG_LOCAL)
    except Exception:
        pass
    cfg = {
        "server": _first(os.environ.get("HUB_DB_SERVER"), default["server"]),
        "user": _first(os.environ.get("HUB_DB_USER"), default["user"]),
        "password": _first(os.environ.get("HUB_DB_PASSWORD"), default["password"]),
        # La app nueva tiene su propia BD de pruebas, pero comparte el esquema:
        # `ECCSA_Admon_Pruebas` es un clon independiente con las mismas tablas.
        "database": _first(os.environ.get("HUB_DB_DATABASE"), default["database"]),
    }
    if not cfg.get("password"):
        print("[config_db] WARNING: sin password de BD. Define HUB_DB_PASSWORD "
              "o crea secretos_local.py.")
    return cfg
