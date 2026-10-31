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


def calcular_stats_usuario(id_usuario):
    """Calcula estadisticas tipo FIFA para un usuario basadas en datos reales."""
    stats = {
        "ovr": 50,
        "productividad": 50, "ventas": 50, "asistencia": 50, "puntualidad": 50,
        "kilometros": 50, "legends": 50, "colaboracion": 50, "eficiencia": 50,
        "posicion": "Colaborador", "racha": 0, "mejor_racha": 0,
        "reportes_mes": 0, "cotizaciones_mes": 0, "km_mes": 0,
        "nivel_legends": "Bronce", "puntos_legends": 0,
    }
    if not id_usuario:
        return stats
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor(as_dict=True)

        # Reportes firmados (ultimos 30 dias)
        cur.execute("""
            SELECT COUNT(*) AS cnt FROM ReportesServicio
            WHERE Tecnico LIKE (SELECT Nombre FROM HUB_Users WHERE Id = %s)
              AND Estatus = 'FIRMADO'
              AND Fecha >= DATEADD(day, -90, GETDATE())
        """, (id_usuario,))
        row = cur.fetchone()
        reportes = row["cnt"] if row else 0
        stats["reportes_mes"] = reportes
        stats["productividad"] = min(99, reportes * 10)  # 10 reportes = 100

        # Cotizaciones creadas (ultimos 30 dias)
        cur.execute("""
            SELECT COUNT(*) AS cnt FROM IndiceMateriales
            WHERE Autor = (SELECT Nombre FROM HUB_Users WHERE Id = %s)
              AND Fecha >= DATEADD(day, -90, GETDATE())
        """, (id_usuario,))
        row = cur.fetchone()
        cotizaciones = row["cnt"] if row else 0
        stats["cotizaciones_mes"] = cotizaciones
        stats["ventas"] = min(99, cotizaciones * 15)  # 7 cotizaciones = 100+

        # Kilometros (ultimos 30 dias)
        cur.execute("""
            SELECT ISNULL(MAX(Kilometros), 0) AS total FROM HUB_RegistroKilometros
            WHERE IdUsuario = %s
              AND FechaHora >= DATEADD(day, -90, GETDATE())
        """, (id_usuario,))
        row = cur.fetchone()
        km = float(row["total"]) if row else 0
        stats["km_mes"] = round(km)
        stats["kilometros"] = min(99, int(km / 5000))  # 5000 km = 1 punto FIFA

        # Legends points
        cur.execute("""
            SELECT PuntuacionTotal, Nivel, RachaDias FROM HUB_UserScores WHERE IdUsuario = %s
        """, (id_usuario,))
        row = cur.fetchone()
        if row:
            pts = row.get("PuntuacionTotal", 0) or 0
            stats["puntos_legends"] = pts
            stats["legends"] = min(99, pts // 5)  # 5 pts = 1 punto FIFA
            stats["nivel_legends"] = row.get("Nivel", "Bronce") or "Bronce"
            stats["racha"] = row.get("RachaDias", 0) or 0
            stats["mejor_racha"] = row.get("RachaDias", 0) or 0

        # Asistencia (ultimos 30 dias)
        cur.execute("""
            SELECT COUNT(DISTINCT CAST(p.FechaHora AS DATE)) AS dias
            FROM HUB_NetworkPresence p
            JOIN HUB_NetworkDevices d ON d.Id = p.IdDispositivo
            WHERE d.IdUsuario = %s AND p.FechaHora >= DATEADD(day, -90, GETDATE())
        """, (id_usuario,))
        row = cur.fetchone()
        dias_asist = row["dias"] if row else 0
        stats["asistencia"] = min(99, int((dias_asist / 22) * 100))  # 22 dias laborales = 100

        # Colaboracion (notas creadas)
        cur.execute("""
            SELECT COUNT(*) AS cnt FROM HUB_Notas WHERE IdUsuario = %s
        """, (id_usuario,))
        row = cur.fetchone()
        notas = row["cnt"] if row else 0
        stats["colaboracion"] = min(99, notas * 10)

        # Eficiencia: horas por reporte (menos = mejor, inverso)
        cur.execute("""
            SELECT AVG(DATEDIFF(minute, FechaHoraInicio, FechaHoraFin) / 60.0) AS avg_h
            FROM ReportesServicio
            WHERE Tecnico LIKE (SELECT Nombre FROM HUB_Users WHERE Id = %s)
              AND Estatus = 'FIRMADO'
              AND FechaHoraInicio IS NOT NULL AND FechaHoraFin IS NOT NULL
        """, (id_usuario,))
        row = cur.fetchone()
        avg_h = row["avg_h"] if row and row["avg_h"] else 5
        stats["eficiencia"] = min(99, max(10, int(100 - (avg_h * 5))))  # 5h = 75, 10h = 50

        # OVR (promedio ponderado)
        stats["ovr"] = round(
            stats["productividad"] * 0.20 +
            stats["ventas"] * 0.15 +
            stats["asistencia"] * 0.15 +
            stats["puntualidad"] * 0.10 +
            stats["kilometros"] * 0.10 +
            stats["legends"] * 0.15 +
            stats["colaboracion"] * 0.05 +
            stats["eficiencia"] * 0.10
        )

        # Posicion
        max_attr = max(stats["productividad"], stats["ventas"], stats["asistencia"],
                       stats["legends"], stats["colaboracion"])
        if stats["productividad"] == max_attr:
            stats["posicion"] = "Tecnico"
        elif stats["ventas"] == max_attr:
            stats["posicion"] = "Comercial"
        elif stats["legends"] == max_attr:
            stats["posicion"] = "Leyenda"
        elif stats["asistencia"] == max_attr:
            stats["posicion"] = "Puntual"
        else:
            stats["posicion"] = "Colaborador"

    except Exception as exc:
        print(f"[stats] error calculando stats: {exc}", file=sys.stderr)
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
    return stats


def obtener_config(clave):
    """Un valor suelto de `HUB_Config`, o '' si no existe o falla la BD.

    Se usa para leer el secreto de derivación de los tokens. Que viva en
    HUB_Config y no en un archivo del contenedor es lo que permite que Admon
    calcule el mismo enlace (misma derivación, mismo secreto compartido).
    """
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT Valor FROM dbo.HUB_Config WHERE Clave = %s", (clave,))
        fila = cur.fetchone()
        conn.close()
        return ((fila[0] or "").strip() if fila else "")
    except Exception as exc:
        print(f"[db] error leyendo config {clave}: {exc}", file=sys.stderr)
        return ""


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
        "colab_empresa_mapa_url",
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
