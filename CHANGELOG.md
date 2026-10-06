# CHANGELOG — ECCSA_Colaboradores

Todos los cambios de esta app. Formato: qué cambió, en qué archivos y por qué.

- `panel/…` → la app (Python sin build)
- `migrations/0057…` → migración de esquema (vive en el repo **HUB**)
- `deploy/app.conf` → definición del contenedor en WebbApps

## 0.1.0 — 2026-10-06

Primera versión.

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
  el token de cada usuario, y editar los 8 datos de la empresa. Detrás de un
  secreto en el volumen; la app **no arranca** sin él.
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
- La foto de las fichas sale de `HUB_Users.Foto`; quien no tenga, muestra
  iniciales.
