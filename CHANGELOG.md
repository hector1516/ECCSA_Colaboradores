# CHANGELOG — ECCSA_Colaboradores

Todos los cambios de esta app. Formato: qué cambió, en qué archivos y por qué.

- `panel/…` → la app (Python sin build)
- `migrations/0057…` → migración de esquema (vive en el repo **HUB**)
- `deploy/app.conf` → definición del contenedor en WebbApps

## 0.1.2 — 2026-10-06

Primera versión pública (ya está en `colaboradores.ecc-sa.com.mx`).

### Fixed

- **El log del contenedor estaba vacío.** `_log()` estaba definida pero no se
  llamaba en ninguna ruta: la app no registraba ni una petición. Sin traza no
  hay forma de ver un barrido de tokens ni de saber qué IP ve la app detrás de
  Cloudflare. Ahora `_enviar()` deja traza del método, el código, la IP y el
  motivo (nunca la ruta, que es el token).

### Changed

- Rate limit de 40 a **60 peticiones por minuto** por IP. Medido en producción:
  a 40, un barrido de 50 requests dejó bloqueada también a la persona legítima
  que estaba usando el sitio. 60 deja margen para la oficina entera detrás de
  NAT sin abrirle la puerta a un escáner (que sí lo frena el WAF de Cloudflare,
  que ve la IP real sin pasar por el proxy).

### Verified

- Ficha pública, vCard, 404 indistinguible, `robots.txt` bloqueando todo y
  `noindex`: comprobado por el dominio público, no solo en local.

### Added

- **Ficha pública por persona** (`panel/server.py`, `panel/plantillas.py`,
  `panel/ficha.css`) — `GET /<slug>` devuelve la tarjeta: foto (o iniciales),
  nombre, botones de llamar / WhatsApp / guardar contacto / mapa, correo,
  dirección y redes sociales de la empresa.
- **Guardar contacto con foto** (`panel/vcard.py`) — vCard 3.0 con la foto
  embebida en base64 y las líneas dobladas a 75 octetos como pide la RFC 2426.
  Sin doblar, algunos importadores cortan el campo y guardan el contacto sin
  foto, que es justo para lo que existe el botón.
- **Panel privado** (`/admin`, `panel/tokens.py`) — emitir, revocar y reactivar
  el token de cada usuario, editar los 8 datos de la empresa, y **subir la foto
  y el puesto de cada persona**. Detrás de un secreto en el volumen; la app
  **no arranca** sin él.
- **Foto y puesto de cada persona, desde el panel** (`panel/server.py`) —
  escriben en `HUB_Users.Foto` y `HUB_Users.Puesto`, columnas que YA existían:
  cero migración nueva. La foto se sube como fichero binario y se guarda como
  data-URI, que es el formato que ya usa esa columna para el avatar del HUB.
- **Parser de `multipart/form-data`** (`panel/server.py`) — a mano, porque
  `cgi.FieldStorage` se eliminó de la biblioteca estándar en Python 3.13.
- **Token aleatorio de 32 caracteres** (`panel/tokens.py`) — Crockford Base32,
  160 bits de entropía, con prefijo legible del nombre.
- **Migración `0057_colaborador_ficha.sql`** (repo HUB) — tabla
  `HUB_ColaboradorFicha` (token, etiqueta, accesos, baja lógica) + las 8 claves
  `colab_empresa_*` en `HUB_Config` y su catálogo. Aditiva: ningún `ALTER TABLE`
  sobre tablas existentes.
- **Tests** (`tests/test_app.py`) — 25 pruebas sin BD ni servidor externo.
- `AGENTS.md`, `deploy/app.conf`, `Dockerfile`, `static/changelog.json`.
- Alta en `ECCSA-Shell` (`APPS`, `CANDIDATES`, `REPOS`, `CHANGELOG`) y
  propagación del shell v1.11.0 en variante `plain`.

### Fixed

- **La sesión del panel no funcionaba.** El login devolvía 303 y ponía cookie,
  pero `/admin` respondía 401 siempre: la cookie llevaba un token aleatorio y la
  validación la comparaba contra el *secreto* del panel. Ahora los tokens de
  sesión viven en un conjunto en memoria (con caducidad de 8 h), el logout los
  invalida de verdad, y hay test del camino feliz login → cookie → panel.
- **`get_connection()`aba el nombre real.** `server._shell_state` se llamaba
  como método de `Handler` cuando era una función suelta: reventaba con
  `AttributeError` y `/api/shell/state` devolvía 500.
- **`slugify` perdía la primera letra de los acentos.** `encode("ascii",
  "ignore")` borra la letra acentuada en vez de convertirla: "ángel" salía
  "ngel" y "pérez" salía "prez". Ahora se quitan solo los signos combinantes.
- **El parser de multipart ignoraba el `Content-Type`** de la parte, así que
  la imagen llegaba sin tipo y no se podía distinguir una foto de un HTML.

### Security

- El token **nunca** se escribe en el log: la ruta ES el token, y
  `log_message` está anulado (`panel/server.py`).
- **404 idéntico** para token inexistente, revocado o mal formado — no se puede
  enumerar qué tokens existieron.
- Rate limit local de 40 peticiones por IP por minuto, con poda para que el
  diccionario no crezca sin límite.
- Cabeceras `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`,
  `Cache-Control: no-store` (el token está en la URL y en un Referer se
  filtraría a Facebook/WhatsApp al pulsar esos botones).
- `robots.txt` bloquea todo y la ficha lleva `noindex`: no es un directorio
  público, son contactos individuales detrás de un token.
- La raíz `/` da 404: **no hay listado de colaboradores**.
- Comparaciones de secreto con `hmac.compare_digest` (login y sesión), no con
  `==`, para no filtrar el secreto byte a byte por tiempo de respuesta.
- Los datos de la empresa solo se guardan por una lista de claves en el código:
  un endpoint que aceptara el nombre de la clave permitiría escribir cualquier
  fila de `HUB_Config`, y ahí hay tokens de Telegram y contraseñas de SMB.

### Known issues

- **Sin host en Cloudflare todavía.** El WAF + Bot Fight + rate limiting del
  túnel es la capa de seguridad PRINCIPAL y aún no está configurada (§3 del
  manual). Hasta entonces el token es lo único que protege las fichas.
- Los 8 valores de `colab_empresa_*` están **vacíos**: se llenan desde `/admin`.
- Sin manifest ni iconos PWA (la app no se instala; se abre en el navegador).
- `HUB_Users.Foto` y `HUB_Users.Puesto` están **vacías en las 11 filas de
  `HUB_Users`** (verificado en producción y en pruebas). Hasta que se suban
  desde `/admin`, las fichas muestran iniciales y sin puesto.
- El teléfono sale de `MAC.Telefono`, NO de `HUB_Users`: es la única columna
  con teléfonos de la base (22 renglones) y la misma que usan HUB y Field.
