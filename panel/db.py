"""
panel/db.py — Acceso a los datos de la ficha pública
=====================================================
Solo lectura sobre `ECCSA_Admon`. Tres fuentes distintas y por qué:

  · HUB_Users          → nombre, correo y PUESTO. SOLO LECTURA: esta app no
                         escribe nada en la tabla de usuarios.
  · HUB_UsuariosFotos  → la FOTO real, que el usuario sube desde Admon. Es
                         VARBINARY en tabla aparte (migración 0045 de AdmonApp,
                         creada justo para que otra app la pidiera por
                         IdUsuario). Pesa 450-550 KB: se pide SOLO al abrir una
                         ficha y se reduce a 320x320 antes de pintar.
  · el token de la URL  → NO está en la base: se deriva con un secreto del
                         volumen (panel/tokens.py). Nada que sincronizar.
  · MAC.Telefono       → el celular. Es la única fuente de teléfonos que ya
                         usan HUB y Field (`get_user_phone`), así que la ficha
                         muestra el mismo número que el resto del sistema y no
                         una copia que se puede desincronizar.
Y los datos de la EMPRESA salen de HUB_Config (claves `colab_empresa_*`): son
los mismos para todas las fichas y editarlos en un solo lugar evita que unas
muestren la dirección vieja y otras la nueva.

Reglas de pymssql que se respetan aquí (ver MANUAL-CREAR-APP-ECCSA.md §4):
  · NO hay placeholders `?`: se usa `%s` con tupla, o interpolación.
  · NO se usa TRIM() (no existe en SQL Server 2014): LTRIM(RTRIM(...)).
  · Cada consulta abre y cierra su conexión. La app es de tráfico bajo y
    bajo carga, así que no vale la pena cachear conexiones entre hilos.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pymssql  # noqa: E402

from config_db import load_db_config  # noqa: E402


def get_connection():
    """Conexión nueva a ECCSA_Admon. El caller la cierra."""
    cfg = load_db_config()
    return pymssql.connect(
        server=cfg["server"],
        user=cfg["user"],
        password=cfg["password"],
        database=cfg["database"],
        login_timeout=10,
    )


# ─────────────────────────────────────────────────────────────────────────────
# La ficha
# ─────────────────────────────────────────────────────────────────────────────
# La ficha se resuelve en DOS consultas a propósito:
#
#   1. La persona: HUB_Users (nombre, correo, puesto) + MAC.Telefono. Es ligera.
#   2. La foto: HUB_UsuariosFotos, SOLO si se está abriendo la ficha.
#
# Unirlo todo en un SELECT sería un error de diseño: las fotos pesan 450-550 KB
# cada una, así que un solo JOIN traería ~5 MB en CADA visita, y en el panel
# (que lista a todos) serían 5 MB para mostrar una tabla.
#
# `HUB_Users` se LEE, nunca se escribe: esta app no toca la tabla de usuarios.
#
# El subconsulto de MAC trae el teléfono de una fila suelta (Telefono IS NOT
# NULL y <> '') con el ORDER BY de la tabla: varias personas pueden tener
# renglones repetidos en MAC y sin ese filtro ganaría el primero, que a veces
# es el más viejo.
FICHA_SQL = """
SELECT
    u.Id,
    u.Nombre,
    u.Email,
    u.Puesto,
    (
        SELECT TOP 1 LTRIM(RTRIM(m.Telefono))
        FROM   dbo.MAC m
        WHERE  LTRIM(RTRIM(m.Nombre)) = LTRIM(RTRIM(u.Nombre))
          AND  m.Telefono IS NOT NULL
          AND  LTRIM(RTRIM(m.Telefono)) <> ''
        ORDER BY m.Telefono DESC
    ) AS Telefono
FROM   dbo.HUB_Users u
WHERE  u.Id = %s
  AND  u.Activo = 1
"""


def obtener_persona(id_usuario):
    """Datos de una persona por Id. None si no existe o está de baja.

    Devuelve None (no una excepción) para los dos casos porque la app los trata
    igual: responde 404 sin distinguir. Saber que un Id existe pero está
    desactivado es información que no se le da a quien escanea URLs.
    """
    if not id_usuario:
        return None
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor(as_dict=True)
        cur.execute(FICHA_SQL, (id_usuario,))
        return cur.fetchone()
    except Exception as exc:
        print(f"[db] error leyendo persona: {exc}", file=sys.stderr)
        return None
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


# ─────────────────────────────────────────────────────────────────────────────
# Datos de la empresa (HUB_Config)
# ─────────────────────────────────────────────────────────────────────────────
def obtener_empresa():
    """Las 8 claves `colab_empresa_*` como diccionario. Vacío si no hay config.

    Se siembran vacías a propósito (migración 0057): son datos públicos que
    alguien tiene que confirmar. La app muestra "—" en vez de inventar.
    """
    claves = (
        "colab_empresa_nombre",
        "colab_empresa_direccion",
        "colab_empresa_sitio",
        "colab_empresa_telefono",
        "colab_empresa_whatsapp",
        "colab_empresa_facebook",
        "colab_empresa_instagram",
        "colab_empresa_latitud",
        "colab_empresa_longitud",
    )
    conn = None
    out = {k: "" for k in claves}
    try:
        conn = get_connection()
        cur = conn.cursor()
        # IN con placeholders: la lista es una constante del código, nunca
        # entrada del usuario.
        marcadores = ",".join(["%s"] * len(claves))
        cur.execute(
            f"SELECT Clave, Valor FROM dbo.HUB_Config WHERE Clave IN ({marcadores})",
            claves,
        )
        for clave, valor in cur.fetchall():
            out[clave] = (valor or "").strip()
    except Exception as exc:
        print(f"[db] error leyendo config de empresa: {exc}", file=sys.stderr)
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
    return out
