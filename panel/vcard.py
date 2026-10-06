"""
panel/vcard.py — La ficha como contacto del teléfono
=====================================================
Genera un vCard 3.0 para el botón "Guardar contacto": el usuario lo abre en el
móvil y el teléfono lo ofrece para guardarlo en sus contactos, CON FOTO.

Por qué vCard y no un formulario web: guardar un contacto desde una página web
obliga a teclear el número a mano. El vCard lo hace en un toque y de paso
sobrevive a que la tarjeta NFC se quede sin Internet el mes que viene.

vCard 3.0 y no 4.0 a propósito: es el formato que Android, iOS, Outlook y
Google Contacts aceptan todos. El 4.0 es más correcto en el papel y falla en
la mitad de los móviles.

La foto va EMBEBIDA en base64, no como URL: la mitad de los móviles no
descargan la imagen de un vCard y guardan el contacto sin foto, que es
justamente el motivo por el que existe el botón.
"""
import base64
import re

# vCard escapa con backslash: \, ; y salto de línea. Sin esto, un nombre con
# punto y coma rompe el archivo entero y el móvil no lo abre.
_ESCAPE_RE = re.compile(r"([\\;,\n\r])")


def _escapar(valor):
    return _ESCAPE_RE.sub(r"\\\1", str(valor or ""))


def _doblar(linea):
    """Pega las líneas a 75 octetos como manda la RFC 2426.

    Sin esto, algunos importadores cortan los campos largos (típicamente la
    foto, que son miles de caracteres) y la persona se guarda vacía o sin foto.
    """
    b = linea.encode("utf-8")
    if len(b) <= 75:
        return linea
    # Primer trozo: 75 bytes. Los siguientes: 74, porque se pega un espacio
    # delante y ese espacio también cuenta para el tope de la RFC.
    trozos = [b[:75]] + [b[i:i + 74] for i in range(75, len(b), 74)]
    return "\r\n ".join(t.decode("utf-8", "ignore") for t in trozos)


def _foto_vcard(foto):
    """Foto como `PHOTO;ENCODING=b;TYPE=JPEG:<base64>`, o '' si no hay.

    `HUB_Users.Foto` es un data-URI (base64 con el prefijo `data:image/png;...`),
    no el base64 pelado, y el prefijo hay que quitarlo antes de meterlo en el
    vCard: si se cuela, el importador lo trata como si fuera imagen y guarda
    basura o rechaza la tarjeta.
    """
    if not foto:
        return ""
    datos = foto
    if datos.startswith("data:"):
        _, _, datos = datos.partition(",")
    try:
        # Se valida al decodificar: si no es base64, mejor sin foto que con una
        # línea corrupta que rompe el importador del móvil.
        base64.b64decode(datos, validate=True)
    except Exception:
        return ""
    return "PHOTO;ENCODING=b;TYPE=JPEG:" + datos


def construir_vcard(nombre, email=None, telefono=None, empresa=None,
                    puesto=None, direccion=None, sitio=None, foto=None):
    """vCard 3.0 de una persona.

    Los parámetros opcionales se omiten del todo cuando vienen vacíos, porque
    un `TEL:` con valor vacío hace que algunos móviles ofrezcan "guardar un
    número en blanco" y ensucien la agenda.
    """
    partes = ["BEGIN:VCARD", "VERSION:3.0"]

    # N: apellido;nombre;additional;prefix;suffix
    # El nombre completo se parte por el ÚLTIMO espacio: en español el
    # apellido es el de atrás ("Hector Peña Ruiz" → apellido "Peña Ruiz").
    nombre = (nombre or "").strip()
    if " " in nombre:
        primero, _, ultimo = nombre.rpartition(" ")
        partes.append(f"N:{_escapar(ultimo)};{_escapar(primero)};;;")
    else:
        partes.append(f"N:;{_escapar(nombre)};;;")

    partes.append(f"FN:{_escapar(nombre)}")

    if empresa:
        partes.append(f"ORG:{_escapar(empresa)}")
    if puesto:
        partes.append(f"TITLE:{_escapar(puesto)}")
    if telefono:
        # TYPE=CELL en vez de WORK: la tarjeta NFC es para localizar a la
        # persona, y el número de MAC.Telefono es el móvil. Guardarlo como
        # "trabajo" hace que la agenda lo agrupe con la oficina y que nadie lo
        # marque desde el coche.
        partes.append(f"TEL;TYPE=CELL,VOICE:{_escapar(telefono)}")
    if email:
        partes.append(f"EMAIL;TYPE=INTERNET:{_escapar(email)}")
    if direccion:
        # ADR:TYPE=WORK:;;calle;localidad;region;codigo postal; pais
        partes.append(f"ADR;TYPE=WORK:;;{_escapar(direccion)};;;;MX")
    if sitio:
        partes.append(f"URL:{_escapar(sitio)}")

    foto_v = _foto_vcard(foto)
    if foto_v:
        partes.append(foto_v)

    partes.append("REV:" + _revision())
    partes.append("END:VCARD")

    # CRLF es lo que pide la spec y lo que Algunos importadores de iOS exigen.
    return "\r\n".join(_doblar(p) for p in partes) + "\r\n"


def _revision():
    """Timestamp vCard (YYYYMMDDTHHMMSSZ) para que el móvil sepa qué es nuevo."""
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
