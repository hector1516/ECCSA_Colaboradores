"""
panel/db.py — Acceso a los datos de la ficha pública
=====================================================
Solo lectura sobre `ECCSA_Admon`. Tres fuentes distintas y por qué:

  · HUB_Users          → nombre, correo y FOTO de la persona. La foto ya vive
                         ahí como base64 (migración 0020), no se duplica.
  · MAC.Telefono       → el celular. Es la única fuente de teléfonos que ya
                         usan HUB y Field (`get_user_phone`), así que la ficha
                         muestra el mismo número que el resto del sistema y no
                         una copia que se puede desincronizar.
  · HUB_ColaboradorFicha → el token de la URL y la telemetría de la tarjeta
                         (migración 0057).

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
# Un solo SELECT para la ficha completa: menos viajes a un SQL Server que está
# al otro lado de la red interna, y además evita que la página se renderice a
# medio camino si la BD va lenta.
#
# El subconsulto de MAC trae el teléfono de una fila suelta (Telefono IS NOT
# NULL y <> '') con el ORDER BY de la tabla: varias personas pueden tener
# renglones repetidos en MAC y sin ese filtro ganaría el primero, que a veces
# es el más viejo.
FICHA_SQL = """
SELECT
    f.Id,
    f.Slug,
    f.Etiqueta,
    f.Creado,
    f.NumAccesos,
    u.Nombre,
    u.Email,
    u.Foto,
    (
        SELECT TOP 1 LTRIM(RTRIM(m.Telefono))
        FROM   dbo.MAC m
        WHERE  LTRIM(RTRIM(m.Nombre)) = LTRIM(RTRIM(u.Nombre))
          AND  m.Telefono IS NOT NULL
          AND  LTRIM(RTRIM(m.Telefono)) <> ''
        ORDER BY m.Telefono DESC
    ) AS Telefono
FROM   dbo.HUB_ColaboradorFicha f
JOIN   dbo.HUB_Users u ON u.Id = f.IdUsuario
WHERE  f.Slug = %s
  AND  f.Activo = 1
  AND  u.Activo = 1
"""


def obtener_ficha(slug):
    """Datos de la ficha por slug, o None si no existe / está dada de baja.

    Devuelve None (no una excepción) para los tres casos porque la app los trata
    igual: responde 404 sin distinguir. Saber si una tarjeta existe pero está
    desactivada es información que no se le da a quien escanea URLs.
    """
    if not slug:
        return None
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor(as_dict=True)
        cur.execute(FICHA_SQL, (slug,))
        return cur.fetchone()
    except Exception as exc:
        print(f"[db] error leyendo ficha: {exc}", file=sys.stderr)
        return None
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def registrar_acceso(slug):
    """Suma un acceso y anota la fecha. Nunca rompe la respuesta.

    La telemetría es lo que permite saber que una tarjeta está perdida (0
    accesos en meses) o que una tarjeta robada está siendo usada. Por eso el
    UPDATE va en su propio try/except: si falla, la ficha se sigue mostrando.
    """
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "UPDATE dbo.HUB_ColaboradorFicha "
            "SET NumAccesos = NumAccesos + 1, UltimoAcceso = GETDATE() "
            "WHERE Slug = %s AND Activo = 1",
            (slug,),
        )
        conn.commit()
    except Exception as exc:
        print(f"[db] no se pudo registrar el acceso: {exc}", file=sys.stderr)
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
