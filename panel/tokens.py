"""
panel/tokens.py — Emisión y revocación de las fichas (panel privado)
===================================================================
Este módulo es la ÚNICA parte de la app que escribe en la BD, y queda detrás
del login del panel. La ficha pública (`GET /<slug>`) nunca llama a nada de
aquí.

El token
--------
32 caracteres de un alfabeto sin ambigüedad (Crockford: sin I, L, O, U, sin 0
y 1, para que se pueda dictar por teléfono sin confusiones). 32 × log2(32) =
160 bits: niEnumerando todo el espacio alcanzaría el link en la vida del
universo.

El prefijo legible (`hector-pena-`) NO es seguridad, es ergonomía: el slug se
graba en una tarjeta que alguien puede tener que volver a fabricar, y
reconocer de un vistazo a qué persona pertenece vale más que los bits que
aporte. Aunque alguien adivinara el nombre completo, los 32 caracteres
aleatorios siguen siendo la barrera.

Por qué el slug NO es hasheado
-----------------------------
Un token solo sirve si se puede buscar por igualdad, y para eso la BD tiene que
compararlo: hasheado habría que regenerar el token en cada visita, y la tarjeta
NFC física (que no se puede reescribir) dejaría de abrir. Se guarda en claro,
igual que los tokens de sesión que ya viven en esta base.

Aleatoriedad
------------
`secrets.token_bytes` (CSPRNG del sistema), NO `random`. Un token de acceso
público generado con un PRNG no criptográfico se puede predecir a partir de
algunos ejemplos: quien adivina un token puede predecir los siguientes. Aquí
eso no es aceptable.
"""
import base64
import os
import re
import secrets
import sys
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from panel import db  # noqa: E402

# Crockford Base32: sin I, L, O, U (letras que se confunden) ni 0, 1.
# 32 símbolos × 32 caracteres = 160 bits de entropía.
ALFABETO = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
LARGO_TOKEN = 32

PREFIJO_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def generar_token(largo=LARGO_TOKEN):
    """Token aleatorio criptográfico, en mayúsculas."""
    return "".join(secrets.choice(ALFABETO) for _ in range(largo))


def slugify(nombre):
    """'Hector Peña Ruiz' → 'hector-pena-ruiz'.

    Se quitan acentos y eñes ANTES de reemplazar: si no, 'Peña' se volvería
    'pe a' y la tarjeta llevaría un hueco que nadie sabe reescribir a mano.
    """
    texto = (nombre or "").lower()
    # La eñe y la Ñ se traducen ANTES de quitar los acentos. NFKD +Encoding
    # ASCII borra la letra entera en vez de convirtiéndola en n, y "Peña" quedaba
    # "pea" — un slug irreconocible en una tarjeta que alguien tiene que volver
    # a fabricar a mano.
    texto = texto.replace("ñ", "n")
    # Ahora los acentos: se descompone (NFKD) y se quitan SOLO los signos
    # combinantes. La forma obvia —encode("ascii", "ignore")— BORRA la letra
    # acentuada en vez de convertirla: "ángel" salía "ngel" y "pérez" salía
    # "prez". Perder la primera letra de un apellido en una tarjeta que hay que
    # reescribir a mano no es un detalle cosmético.
    texto = "".join(c for c in unicodedata.normalize("NFKD", texto)
                    if not unicodedata.combining(c))
    texto = re.sub(r"[^a-z0-9]+", "-", texto)
    return texto.strip("-") or "colaborador"


def construir_slug(nombre):
    """Slug completo: `hector-pena-<32 aleatorios>`."""
    return f"{slugify(nombre)}-{generar_token()}"


def slug_valido(slug):
    """True si el slug tiene la forma `<prefijo>-<token>`.

    El backend igual compara contra el índice único, así que esto NO es la
    seguridad: es para no gastar una ida a la BD con basura, y para no meter
    caracteres raros en los logs.
    """
    if not slug or len(slug) > 96:
        return False
    partes = slug.split("-")
    if len(partes) < 2:
        return False
    if not PREFIJO_RE.match("-".join(partes[:-1])):
        return False
    token = partes[-1]
    return len(token) == LARGO_TOKEN and all(c in ALFABETO for c in token.upper())


# ─────────────────────────────────────────────────────────────────────────────
# Escrituras (solo desde el panel autenticado)
# ─────────────────────────────────────────────────────────────────────────────
USUARIOS_SQL = """
SELECT u.Id, u.Nombre, u.Email, u.Activo,
       f.Id AS FichaId, f.Slug, f.Etiqueta, f.Activo AS FichaActivo,
       f.Creado, f.NumAccesos, f.UltimoAcceso
FROM   dbo.HUB_Users u
LEFT   JOIN dbo.HUB_ColaboradorFicha f ON f.IdUsuario = u.Id
ORDER  BY u.Nombre
"""


def listar_usuarios():
    """Todos los usuarios con su ficha (o None si aún no tienen).

    Trae también los inactivos a propósito: es la forma de que el panel muestre
    a quién hay que dar de baja, y de no confesar que un token existe cuando la
    persona ya no trabaja aquí.
    """
    conn = None
    try:
        conn = db.get_connection()
        cur = conn.cursor(as_dict=True)
        cur.execute(USUARIOS_SQL)
        return cur.fetchall()
    except Exception as exc:
        print(f"[tokens] error listando usuarios: {exc}", file=sys.stderr)
        return []
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def emitir(id_usuario, etiqueta=None):
    """Crea (o devuelve) la ficha de un usuario. Devuelve (slug, nuevo).

    `nuevo=False` significa que la persona ya tenía token: NO se genera otro,
    porque la tarjeta NFC física ya está grabada con el viejo y un token nuevo
    dejaría esa tarjeta muerta sin avisar. Para rotar el token hay que usar
    `revocar()` primero, y eso SÍ inutiliza la tarjeta vieja a propósito.
    """
    conn = None
    try:
        conn = db.get_connection()
        cur = conn.cursor(as_dict=True)

        cur.execute("SELECT Nombre FROM dbo.HUB_Users WHERE Id = %s", (id_usuario,))
        fila = cur.fetchone()
        if not fila:
            return None, False
        nombre = fila["Nombre"]

        cur.execute(
            "SELECT Slug FROM dbo.HUB_ColaboradorFicha WHERE IdUsuario = %s",
            (id_usuario,),
        )
        existente = cur.fetchone()
        if existente:
            return existente["Slug"], False

        slug = construir_slug(nombre)
        cur.execute(
            "INSERT INTO dbo.HUB_ColaboradorFicha (IdUsuario, Slug, Etiqueta, Activo) "
            "VALUES (%s, %s, %s, 1)",
            (id_usuario, slug, etiqueta or nombre),
        )
        conn.commit()
        return slug, True
    except Exception as exc:
        print(f"[tokens] error emitiendo ficha: {exc}", file=sys.stderr)
        return None, False
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def revocar(id_usuario):
    """Desactiva la ficha. NO borra la fila: conserva el historial de accesos.

    Es la diferencia entre "esta tarjeta ya no sirve" y "esta tarjeta nunca
    existió". Con la ficha dada de baja, `GET /<slug>` responde 404 igual que
    un token inventado, así que no se puede usar para probar Tokens.
    """
    conn = None
    try:
        conn = db.get_connection()
        cur = conn.cursor()
        cur.execute(
            "UPDATE dbo.HUB_ColaboradorFicha SET Activo = 0 WHERE IdUsuario = %s",
            (id_usuario,),
        )
        cambiados = cur.rowcount
        conn.commit()
        return cambiados > 0
    except Exception as exc:
        print(f"[tokens] error revocando ficha: {exc}", file=sys.stderr)
        return False
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def reactivar(id_usuario):
    """Vuelve a activar una ficha revocada (mismo token: la tarjeta sirve)."""
    conn = None
    try:
        conn = db.get_connection()
        cur = conn.cursor()
        cur.execute(
            "UPDATE dbo.HUB_ColaboradorFicha SET Activo = 1 WHERE IdUsuario = %s",
            (id_usuario,),
        )
        cambiados = cur.rowcount
        conn.commit()
        return cambiados > 0
    except Exception as exc:
        print(f"[tokens] error reactivando ficha: {exc}", file=sys.stderr)
        return False
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


# ─── Datos de la empresa (edición desde el panel) ────────────────────────────
EMPRESA_TIPO = {
    "colab_empresa_nombre": "text",
    "colab_empresa_direccion": "text",
    "colab_empresa_telefono": "text",
    "colab_empresa_whatsapp": "text",
    "colab_empresa_facebook": "text",
    "colab_empresa_instagram": "text",
    "colab_empresa_latitud": "number",
    "colab_empresa_longitud": "number",
}


def guardar_empresa(valores):
    """Guarda las 8 claves de empresa. Solo las claves conocidas.

    La lista de claves está en el código (EMPRESA_TIPO), no viene del request:
    un endpoint que acepta el nombre de la clave permite escribir cualquier fila
    de HUB_Config, y esa tabla guarda tokens de Telegram y passwords de SMB.
    """
    permitidas = {k: v for k, v in (valores or {}).items() if k in EMPRESA_TIPO}
    if not permitidas:
        return False
    conn = None
    try:
        conn = db.get_connection()
        cur = conn.cursor()
        for clave, valor in permitidas.items():
            texto = (valor or "").strip()
            # Los campos numéricos se validan aquí y no en la vista: si alguien
            # guarda "abc" en latitud, el enlace del mapa queda roto y el error
            # no se ve hasta que alguien lo toca.
            if EMPRESA_TIPO[clave] == "number" and texto:
                try:
                    float(texto)
                except ValueError:
                    print(f"[tokens] {clave} no es un número: {texto!r}")
                    continue
            cur.execute(
                "UPDATE dbo.HUB_Config SET Valor = %s, Actualizado = GETDATE() "
                "WHERE Clave = %s",
                (texto, clave),
            )
            if cur.rowcount == 0:
                cur.execute(
                    "INSERT INTO dbo.HUB_Config (Clave, Valor) VALUES (%s, %s)",
                    (clave, texto),
                )
        conn.commit()
        return True
    except Exception as exc:
        print(f"[tokens] error guardando datos de empresa: {exc}", file=sys.stderr)
        return False
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
