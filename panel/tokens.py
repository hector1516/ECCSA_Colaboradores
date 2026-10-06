"""
panel/tokens.py — El token de la URL: derivado, no almacenado
=============================================================
El token de cada ficha se CALCULA a partir del Id del usuario y de un secreto
que vive en el volumen del contenedor. No hay tabla de tokens: la única fuente
de datos de personas es `HUB_Users`, y esta app solo la LEE.

Por qué se deriva en vez de guardarse
-------------------------------------
Guardarlo exigiría una tabla (o columnas en `HUB_Users`) con un token por
persona, y eso es una fuente de verdad más que puede desincronizarse del resto
del ecosistema. Derivándolo:

  · No puede quedar huérfano, duplicado ni apuntar a la persona equivocada:
    sale del Id, y el Id no cambia.
  · No hay que "emitir" nada. El enlace de todos existe siempre y es el mismo
    para siempre, que es lo que necesita una tarjeta NFC ya grabada.
  · `HUB_Users` queda intacta: esta app no escribe nada en ella.

Lo que se pierde, y es un precio real
-------------------------------------
  · **No hay baja por persona.** Para dejar de servir una tarjeta hay que rotar
    el secreto, lo que invalida las tarjetas de TODOS. Con una tabla se
    revocaba una a una.
  · **No hay contador de accesos.** No se sabe si una tarjeta está en uso.

Lo que hay que revisar de vez en cuando
---------------------------------------
Si en un par de años esto se vuelve molesto (una tarjeta robada que hay que
dar de baja sin tumbar las demás), la respuesta correcta es una tabla de solo
revocación — sin el token, que sigue derivado — en vez de volver a guardar los
tokens.

El token
--------
32 caracteres de un alfabeto sin ambigüedad (Crockford: sin I, L, O, U, sin 0 y
1, para poder dictarlo por teléfono sin confusiones). 32 x 5 = 160 bits: ni
enumerando todo el espacio alcanzaría el link en la vida del universo.

El prefijo legible (`hector-pena-`) NO es seguridad, es ergonomía: el slug va
grabado en una tarjeta que puede haber que volver a fabricar, y reconocer de un
vistazo a qué persona pertenece vale más que los bits que aporte. Aunque alguien
adivinara el nombre completo, los 32 caracteres siguen siendo la barrera.

Aleatoriedad
------------
`secrets` (CSPRNG) para el secreto, nunca `random`: un secreto con PRNG no
criptográfico se predice a partir de unos ejemplos, y aquí el secreto es la raíz
de todos los tokens.
"""
import hashlib
import hmac
import os
import re
import secrets
import sys
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from panel import config, db  # noqa: E402

# Crockford Base32: sin I, L, O, U (letras que se confunden) ni 0, 1.
ALFABETO = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
LARGO_TOKEN = 32
BITS_POR_CARACTER = 5
BYTES_DE_SEMILLA = (LARGO_TOKEN * BITS_POR_CARACTER) // 8      # 20 bytes

PREFIJO_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

# Etiqueta de dominio dentro del mensaje HMAC. Si el mismo secreto se usara
# para otra cosa, los tokens de las dos cosas serían idénticos.
DOMINIO = b"ficha-nfc-v1:"


def generar_secreto():
    """Secreto nuevo. Solo se usa al crear el archivo por primera vez."""
    return secrets.token_urlsafe(48)


def _clave():
    """Secreto de derivación en bytes. b'' si todavía no se ha creado."""
    secreto = config.ficha_secreto()
    return secreto.encode("utf-8") if secreto else b""


def token_de(id_usuario):
    """Token de una persona. Determinista: el mismo Id, el mismo token, siempre.

    Es HMAC-SHA256 del Id con el secreto, de los que se toman 20 bytes (160
    bits) y se codifican en Base32. Es un PRF, no un hash: sin el secreto no se
    puede calcular el token ni aunque se conozca el Id.
    """
    clave = _clave()
    if not clave:
        return ""
    mac = hmac.new(clave, DOMINIO + str(int(id_usuario)).encode("ascii"),
                   hashlib.sha256)
    numero = int.from_bytes(mac.digest()[:BYTES_DE_SEMILLA], "big")
    # Se leen los bits de MSB a LSB, de 5 en 5. El desplazamiento baja de 155
    # a 0 porque el primer carácter usa los 5 bits más altos.
    return "".join(
        ALFABETO[(numero >> (BITS_POR_CARACTER * (LARGO_TOKEN - 1 - i))) & 31]
        for i in range(LARGO_TOKEN)
    )


def slugify(nombre):
    """'Hector Peña Ruiz' -> 'hector-pena-ruiz'.

    Los acentos y la eñe se traducen ANTES de filtrar. La forma obvia —
    `encode("ascii", "ignore")`— borra la letra acentuada en vez de convertirla:
    "ángel" salía "ngel" y "pérez" salía "prez", y perder la primera letra de un
    apellido en una tarjeta que hay que reescribir a mano sí es un problema.
    """
    texto = (nombre or "").lower().replace("ñ", "n")
    texto = "".join(c for c in unicodedata.normalize("NFKD", texto)
                    if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "-", texto).strip("-") or "colaborador"


def construir_slug(nombre, id_usuario):
    """Slug completo: `hector-pena-<32 derivados>`."""
    token = token_de(id_usuario)
    return f"{slugify(nombre)}-{token}" if token else ""


def slug_valido(slug):
    """True si el slug tiene la forma `<prefijo>-<token>`.

    El backend igual compara contra el token derivado, así que esto NO es la
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


def persona_por_token(slug):
    """La persona de un slug, o None.

    Como el token es DERIVADO y no está guardado, no hay un WHERE que lo
    encuentre: se calcula el token de cada usuario activo y se compara. Con 11
    usuarios son 11 HMAC (microsegundos); con 500 serían 500, y aun así es más
    barato que cualquier tabla extra.

    Un ataque de fuerza bruta se paga aquí: cada intento calculates el token de
    todos los usuarios, así que adivinar no gana nada por haber acertado antes.
    """
    if not slug_valido(slug):
        return None
    partes = slug.split("-")
    prefijo, token = "-".join(partes[:-1]), partes[-1].upper()
    for persona in listar_personas(solo_activas=True):
        esperado = construir_slug(persona.get("Nombre"), persona["Id"])
        if not esperado:
            continue
        p_esperado, t_esperado = esperado.rsplit("-", 1)
        # Se comparan las dos mitades por separado: el prefijo legible va en
        # claro a propósito, así que solo el token lleva la comparacion
        # constante.
        if p_esperado == prefijo and hmac.compare_digest(t_esperado, token):
            persona["Slug"] = esperado
            persona["Foto"], persona["FotoTipo"] = foto_thumbnail(persona["Id"])
            return persona
    return None


def coincide(prefijo_slug, token_recibido, id_usuario):
    """True si el token recibido es el DERIVADO de esa persona.

    `hmac.compare_digest` y no `==`: con `==` el tiempo de respuesta depende de
    cuántos caracteres correctos lleva, y eso filtra el token byte a byte.
    """
    esperado = token_de(id_usuario)
    if not esperado or not token_recibido:
        return False
    return hmac.compare_digest(esperado, str(token_recibido).upper())


# ─────────────────────────────────────────────────────────────────────────────
# Lectura de personas (ÚNICA fuente: HUB_Users + HUB_UsuariosFotos + MAC)
# ─────────────────────────────────────────────────────────────────────────────
# `HUB_Users` solo se LEE. La foto sale de `HUB_UsuariosFotos.Archivo`, que es
# donde el usuario la sube desde Admon (10 de 11 personas).
#
# Se hace un solo SELECT de usuarios y la foto va en OTRA consulta, porque son
# 450-550 KB por persona: traerlas todas junto con el listado multiplicaría por
# 5 MB una respuesta que el panel carga entera. La foto se pide SOLO cuando se
# abre una ficha.
PERSONAS_SQL = """
SELECT u.Id, u.Nombre, u.Email, u.Activo, u.Puesto, u.Nickname
FROM   dbo.HUB_Users u
ORDER  BY u.Nombre
"""

# La foto REAL la sube el usuario desde Admon (app AdmonApp). Vive en
# `HUB_UsuariosFotos.Archivo` como VARBINARY, en tabla aparte a propósito: esa
# tabla se creó (migración 0045 de AdmonApp) justamente para que otra app la
# pidiera sola por IdUsuario sin que HUB_Users arrastre binarios en cada login.
#
# NO se usa `HUB_UserAvatars`: son avatares generados por IA, no la foto de la
# persona, y es justo lo que se quiere mostrar en una tarjeta de presentación.
FOTO_SQL = """
SELECT f.Archivo, f.ContentType
FROM   dbo.HUB_UsuariosFotos f
WHERE  f.IdUsuario = %s
"""


def listar_personas(solo_activas=False):
    """Personas con su token derivado. Lista para el panel."""
    filas = []
    conn = None
    try:
        conn = db.get_connection()
        cur = conn.cursor(as_dict=True)
        cur.execute(PERSONAS_SQL)
        for f in cur.fetchall() or []:
            if solo_activas and not f.get("Activo"):
                continue
            f = dict(f)
            f["Slug"] = construir_slug(f.get("Nombre"), f["Id"])
            filas.append(f)
    except Exception as exc:
        print(f"[tokens] error listando personas: {exc}", file=sys.stderr)
        return []
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
    return filas


def foto_bytes(id_usuario):
    """Foto real de la persona: (bytes, content_type). (b'', '') si no tiene.

    Sale de `HUB_UsuariosFotos`, que es donde el usuario la sube desde Admon.
    Se devuelve el BINARIO pelado y no base64 a propósito: la columna es
    VARBINARY justamente para no pagar el 33% extra del base64, y la conversión
    se hace una sola vez, ya reducida, al pintar.
    """
    try:
        conn = db.get_connection()
        cur = conn.cursor()
        cur.execute(FOTO_SQL, (id_usuario,))
        fila = cur.fetchone()
        conn.close()
        if fila and fila[0]:
            return bytes(fila[0]), (fila[1] or "image/jpeg")
    except Exception as exc:
        print(f"[tokens] error leyendo la foto: {exc}", file=sys.stderr)
    return b"", ""


# ─────────────────────────────────────────────────────────────────────────────
# Reducción de la foto
# ─────────────────────────────────────────────────────────────────────────────
# Las fotos que sube el usuario desde Admon pesan 450-550 KB. Eso es demasiado
# en dos sitios:
#
#   · la ficha se abre por NFC, muchas veces con datos móviles: 375 KB de PNG
#     para pintar un círculo de 120 px es tirar ancho de banda;
#   · el vCard va dentro de un archivo que el móvil tiene que parsear entero:
#     375 KB de foto en un contacto hace que iOS a veces tarde en abrirlo.
#
# El lado del recorte. No es el tamaño en que se PINTA (eso lo decide el CSS),
# sino cuánta parte de la foto original entra en el cuadrado.
#
# Historia de este número, medida contra las fotos reales (896x1200):
#   320 px -> frente y ojos, barbilla cortada (la cara no cabía entera)
#   460 px -> la cara completa, pero muy apretada
#   660 px -> cara completa CON cabeza y hombros, que es lo que se pidió: que se
#            vea "un poco más" de la persona y no solo el rostro.
#
# Cuesta 48 KB de media contra los 31 KB de 460. Es el punto dulce: 700 px solo
# suma 3 KB más por un encuadre casi idéntico.
#
# NO se amplía una imagen más pequeña: estirar una foto de 128 px a 660 solo
# añade bytes y se ve borroso.
LADO_AVATAR = 660
CALIDAD_JPEG = 82


# Dónde cae el CENTRO del recorte, en fracción de la altura.
#
# Calibrado a ojo contra las fotos reales (las 10 de `HUB_UsuariosFotos` son
# 896x1200, todas verticales de celular):
#
#   recorte al centro (0.50) -> franja 37%-63% de la altura: PECHO Y BOCA. La
#       cara queda fuera y la ficha mostraba "solo la boca".
#   0.30 -> sube demasiado: frente y ojos bien, pero cuts la BARBILLA.
#   0.42 -> la cara completa (frente, ojos, nariz, boca y barbilla)
#   0.48 -> cara completa más cabeza y hombros, que es el encuadre actual: la
#       ficha se abre al tocar una tarjeta y conviene reconocer a la persona de
#       cuerpo, no solo verle la cara muy grande.
#
# Es un dato de las fotos de ESTA gente, no una regla universal: si algún día se
# suben retratos ya encuadrados, se ajusta este número una vez y se acabó.
CENTRO_ROSTRO_VERTICAL = 0.48


def _arriba_del_recorte(alto, lado):
    """Y del borde superior del recorte cuadrado, sesgado hacia arriba.

    Verticales: el centro del recorte cae al 30% de la altura (donde está la
    cara). El `max(0, …)` evita que en una imagen apenas más alta que el lado se
    salga del borde, y el `min` evita pasarse del final.
    """
    if alto <= lado:
        return 0
    objetivo = int(alto * CENTRO_ROSTRO_VERTICAL)
    arriba = objetivo - lado // 2
    return max(0, min(arriba, alto - lado))


def foto_thumbnail(id_usuario):
    """(base64_jpeg, content_type) de la foto REDUCIDA, o ('', '').

    Las fotos de Admon pesan 450-550 KB (fotos de celular). Para la ficha, que
    se abre por NFC muchas veces con datos móviles, y para el vCard, que el
    móvil tiene que parsear entero, eso es demasiado: 320x320 JPEG quedan en
    ~20 KB con el mismo aspecto.

    Si Pillow no estuviera (imagen de Python sin él), se devuelve la foto
    original tal cual: más pesada, pero la ficha funciona igual.
    """
    crudo, _tipo = foto_bytes(id_usuario)
    if not crudo:
        return "", ""
    try:
        import base64 as _b64
        import io

        from PIL import Image

        img = Image.open(io.BytesIO(crudo))
        # El recorte va al CENTRO: la cara de una foto de carnet está ahí, y
        # recortar por arriba cortaría la frente.
        ancho, alto = img.size
        lado = min(ancho, alto, LADO_AVATAR)
        izquierda = (ancho - lado) // 2
        arriba = _arriba_del_recorte(alto, lado)
        img = img.crop((izquierda, arriba, izquierda + lado, arriba + lado))
        if img.mode not in ("RGB", "L"):
            # Un PNG con canal alfa a JPEG se vuelve negro si no se compone
            # antes: el fondo transparente se interpretaría como color.
            img = img.convert("RGBA")
            fondo = Image.new("RGB", img.size, (15, 23, 42))
            fondo.paste(img, mask=img.split()[-1])
            img = fondo
        elif img.mode == "L":
            img = img.convert("RGB")
        salida = io.BytesIO()
        img.save(salida, format="JPEG", quality=CALIDAD_JPEG,
                 optimize=True, progressive=True)
        return _b64.b64encode(salida.getvalue()).decode("ascii"), "image/jpeg"
    except Exception as exc:
        print(f"[tokens] no se pudo reducir la foto: {exc}", file=sys.stderr)
        return _b64.b64encode(crudo).decode("ascii"), _tipo or "image/jpeg"
