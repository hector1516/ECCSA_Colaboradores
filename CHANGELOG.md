# CHANGELOG — ECCSA_Colaboradores

Todos los cambios de esta app. Formato: qué cambió, en qué archivos y por qué.

- `panel/…` → la app (Python sin build)
- `migrations/0057…` → migración de esquema (vive en el repo **HUB**)
- `deploy/app.conf` → definición del contenedor en WebbApps

## 0.5.1 — 2026-10-09

### Changed

- **Menos zoom en el retrato** (`panel/ficha.css`): el `scale` base baja de
  `1.07` a `1.03` y el máximo de `1.13` a `1.08`, y el balanceo se reduce a
  ~0.7 %. Se ve más de la foto; el margen de 1.5 % por lado sigue evitando que
  el desplazamiento descubra bordes vacíos dentro del círculo.

## 0.5.0 — 2026-10-09

### Added

- **El retrato "vive"** (`panel/ficha.css`, `panel/plantillas.py`): la foto de la
  ficha ya no es una imagen fija. Se mueve en bucle, muy lento, como un cuadro
  encantado, y todo es CSS puro (la ficha sigue sin una línea de JavaScript):

    · **La foto respira** — se acerca y se aleja y se balancea (`retrato-vivo`,
      26 s). Nunca baja de `scale(1.07)`, así que al desplazarse no descubre
      bordes vacíos dentro del círculo; la rotación es de menos de medio grado.
    · **Una luz la recorre** — una franja diagonal cálida cruza el rostro cada
      11 s, como el brillo de una vela (`luz-viva`).
    · **Motas doradas** — chispas que ascienden y se desvanecen (`brasas`).

  La capa de efectos va en un `<span class="vida">` DENTRO del marco, para
  heredar el recorte circular, y solo se pinta cuando hay foto: las iniciales
  de quien no subió foto se quedan quietas.

- **`prefers-reduced-motion` oculta los efectos** en vez de congelarlos: una
  mota fija o una franja de luz parada sobre la cara se vería como un defecto.
  La foto vuelve a su tamaño normal.

### Tests

51 → 52. El nuevo comprueba que la rama con foto lleve la capa `.vida` y que
el CSS traiga los tres `@keyframes` del retrato vivo.

## 0.4.1 — 2026-10-06

### Changed

- **Los botones se autoajustan** (`panel/ficha.css`): `repeat(auto-fit,
  minmax(140px, 1fr))` en vez de `1fr 1fr` fijo. La rejilla se acomoda sola al
  ancho de la pantalla y a cuántos botones haya:
    · 320 px -> 2 columnas
    · 420 px -> 2 columnas con aire
    · 560 px o más -> 3 o 4 columnas

  Con las columnas fijas, un número impar de botones dejaba una fila huérfana
  con un botón más estrecho que los demás, o un hueco vacío. Las etiquetas
  largas ("Guardar contacto") ahora pueden partirse en dos líneas en vez de
  desbordar la celda (`overflow-wrap: anywhere` + `min-width: 0`).

### Tests

50 → 51. El nuevo mira el bloque `.acciones` y no todo el archivo, porque el
formulario de empresa del panel sí lleva `1fr 1fr` fijo y ahí sí es correcto.

## 0.4.0 — 2026-10-06

### Changed

- **"Cómo llegar" abre Google Maps** (`panel/plantillas.py:url_mapa`).
  Antes usaba `maps.apple.com`, que en Android manda a una página web dentro del
  navegador en vez de a la app de mapas. Ahora:
    1. usa `colab_empresa_mapa_url`, el link corto al lugar exacto
       (`https://maps.app.goo.gl/68aD2DRKH31VSFd97`, migración `0061`), que abre
       la app nativa del móvil y apunta al negocio ya verificado por Google, con
       su ficha y sus horarios, en vez de a una búsqueda por texto que puede caer
       en otro punto de la calle;
    2. si no hay link, cae a las coordenadas en Google Maps;
    3. y si tampoco, a la búsqueda por dirección.

  El link corto se deja TAL CUAL, sin reescribirlo a `google.com/maps/search`:
  al reescribirlo se pierde el redireccionado que decide qué app se abre.

  Las coordenadas exactas (25.6621268, -100.2820189) salieron de resolver el
  propio enlace, que redirige a `place/ECCSA+Automation/@25.6621268,-100.2820189`.

### Added

- Clave `colab_empresa_mapa_url` en `HUB_Config` y en el panel (migración
  `0061`), editable sin redesplegar.

### Tests

48 → 50. Los nuevos comprueban que el link corto tiene prioridad, que se
normaliza si le falta el `https`, que el respaldo va a Google Maps y que no
vuelve a aparecer `maps.apple.com` en ningún caso.

## 0.3.4 — 2026-10-06

### Changed

- **Encuadre de la foto, más abierto**: de 460 px @ 42% a **660 px @ 48%**.
  Ahora entra la cara completa CON cabeza y hombros, que es lo que pedía
  "que se logre ver un poco más": la ficha se abre al tocar una tarjeta y
  conviene reconocer a la persona de cuerpo, no verle solo la cara enormous.
  Verificado con los 10 avatares: el encuadre sirve para todos.
- Cuesta 48 KB de media contra los 31 KB de antes (la ficha pasa de 97 KB a
  ~115 KB). 700 px solo sumaba 3 KB más por un encuadre casi idéntico, así que
  660 es el punto.

### Tests

El test de reducción fijaba un factor de compresión sobre una foto de RUIDO
ALEATORIO, que es el peor caso para JPEG y no representa una foto real. Ahora
comprueba lo que importa: que el avatar nunca exceda `LADO_AVATAR` en píxeles y
que pese menos que la original.

## 0.3.3 — 2026-10-06

### Fixed

- **La ficha mostraba "solo la boca".** El recorte no era del CSS sino de la
  miniatura que se genera en `panel/tokens.py`. Las fotos de
  `HUB_UsuariosFotos` son todas 896x1200 **verticales de celular**, y recortar
  el cuadrado al centro tomaba la franja del 37% al 63% de la altura: pecho y
  boca. La cara quedaba fuera.

  Calibrado contra las fotos reales: centro al 50% → boca; 0.30 → frente y
  ojos pero cortando la barbilla; **0.42 → la cara completa**, que es el valor.
  Y el lado del recorte pasa de 320 a 460 px, porque con 320 la cara no cabía
  entera ni con el centro bien puesto.

  `CENTRO_ROSTRO_VERTICAL` y `LADO_AVATAR` quedan documentados como el número
  que hay que ajustar si algún día se suben retratos ya encuadrados.

### Tests

46 → 48. Los dos nuevos fijan que el recorte cae sobre la cara (entre 30% y 55%
de la altura) y que nunca se sale de la imagen. También se corrigió el test de
reducción, que comparaba contra una imagen de color plano —que se comprime a
casi nada— y por eso medía una cosa que no era la real.

## 0.3.2 — 2026-10-06

### Fixed

- **El recorte de la foto, copiado de AdmonApp.** Esta app ponía el
  `border-radius` y el `object-position` directamente en la `<img>` y desplazaba
  el recorte al 28% vertical "para acercar la cara". El resultado era un
  recorte descuadrado y se veía peor que en Admon, que sí lo hace bien.
  Ahora es la misma técnica que `UsuarioDetalle.svelte`: un contenedor
  `.marco-foto` circular con `overflow: hidden`, y la foto dentro al 100% con
  `object-fit: cover` **centrado**. El `border-radius` va en el contenedor, lo
  que además hace que el mismo marco sirva para las iniciales sin dos reglas.
- Las iniciales sin foto usan fondo neutro y texto en color de acento, como
  Admon; estaban en naranja sólido y se veían como un avatar de juego.
- El anillo girando y la sombra que respira se mueven al `.marco-foto` (el
  `::before` sobre la `<img>` quedaba detrás de la foto y no se veía).

### Changed

- Foto a `clamp(190px, 68vw, 340px)` (era `clamp(168px, 62vw, 300px)`).
  Admon usa 7rem/9rem; aquí es bastante más grande porque la ficha entera es la
  foto.

### Tests

45 → 46. El nuevo comprueba el markup de las dos ramas (con foto y sin foto) y
que el CSS no vuelva a meter un `object-position`.

## 0.3.1 — 2026-10-06

### Fixed

- **El fondo vuelve a ser el del ecosistema.** Esta app tenía su propia aurora
  animada y se veía un fondo DISTINTO al de Field y Admon. Ahora no define
  fondo: hereda el engrane del shell (`body::before`, 5%). Y
  `panel/engrane.png` es copia del de Field (mismo md5), no el dibujo que se
  había hecho para esta app: así la textura es idéntica píxel a píxel.
- **Foto más grande**: de `clamp(132px, 40vw, 210px)` a
  `clamp(168px, 62vw, 300px)`. Los nombres y los puestos también crecen.

### Tests

44 → 45. El nuevo comprueba que la ficha no define fondo propio y que el
engrane que sirve sigue siendo el de Field.

## 0.3.0 — 2026-10-06

La ficha se ve como una tarjeta de presentación de verdad.

### Changed

- **La foto pasa de 120 px a `clamp(132px, 40vw, 210px)`** (`panel/ficha.css`).
  120 px es del tamaño de un icono de WhatsApp: la cara de la persona se veía
  diminuta y no cumplía su función, que es reconocer a quién tienes enfrente.
  El `clamp` tiene suelo y tope porque en un móvil de 320 px un tamaño en `vw`
  se iría de la pantalla, y en una tablet un 40 vw sería un cartel.
- `object-position: 50% 28%`: las fotos de `HUB_UsuariosFotos` son verticales de
  celular, y con el recorte al centro la cara salía cortada por arriba.

### Added

- **Animaciones, todas CSS puro y sin JavaScript** (`panel/ficha.css`):
  entrada escalonada en cascada (`--i` por elemento), anillo cónico girando
  alrededor de la foto, sombra que respira, fondo de aurora en 18 s, "latido"
  del botón Llamar y brillo que recorre los botones al tocarlos.
  Sin JS a propósito: la ficha se abre con un dedo pegado a una tarjeta NFC y
  tiene que verse igual aunque el JS tarde o falle.
- `@property --rotate`, que es lo que permite animar el ángulo del anillo: las
  variables CSS no son animables por defecto y sin esto el degradado no gira.
- **`prefers-reduced-motion`**: con "reducir animaciones" activado se apaga
  TODO. No es decoración: una persona con desórdenes vestibulares ve un fondo en
  movimiento y se marea.
- **`panel/engrane.png`** y su ruta `GET /engrane.png`. El CSS del shell lo pide
  con `url('/engrane.png')` y el archivo no existía en esta app, así que era un
  404 en cada visita. `shell.css` es copia canónica y no se edita: lo que se
  hizo fue generar el archivo y servirlo.
- Estilo para móvil en horizontal (foto achicada, porque si no no cabe).

### Tests

40 → 44. Los nuevos comprueban que la ficha no lleva JS, que la foto sigue
dimensionada con `clamp()`, que `prefers-reduced-motion` apaga todo y que la
textura de fondo se sirve.

## 0.2.0 — 2026-10-06

**Reescritura de dónde salen los datos.** Todo se lee de `HUB_Users` y de las
tablas que las demás apps ya llenan. Esta app deja de crear estructura propia.

### Removed

- **`HUB_ColaboradorFicha` (tabla).** El token ya no se guarda: se **deriva**
  con HMAC-SHA256 del `IdUsuario` y de un secreto del volumen
  (`panel/tokens.py`). Ventajas: no puede quedar huérfano ni duplicado, no hay
  que "emitir" nada, y `HUB_Users` queda intacta. Migraciones `0059` (DROP,
  aborta si hubiera filas) en el repo HUB.
- **Emisión / revocación / reactivación desde el panel.** Con el token derivado
  no hay nada que emitir: el enlace de todos existe siempre y es el mismo para
  siempre.
- **Subida de foto y puesto desde el panel.** Escribirían en `HUB_Users`, y
  `HUB_Users` es de solo lectura para esta app.
- **El parser de multipart/form-data** que existía solo para esa subida.

### Added

- **Fotos reales** (`panel/tokens.py`): `HUB_UsuariosFotos.Archivo`, que es
  donde el usuario las sube desde **Admon** (10 de 11 personas, 450-550 KB).
  Antes se usaba `HUB_UserAvatars`, que son avatares generados por IA — no la
  persona.
- **Reducción de la foto a 320x320 JPEG** antes de pintar: de 450-550 KB a
  ~20-28 KB (95% menos). Sin esto, la ficha —que se abre por NFC, a menudo con
  datos móviles— descargaba medio megabyte para pintar un círculo de 120 px, y
  el vCard se volvía heavyweight para el importador del móvil. Añade `Pillow`.
- **Clave `colab_empresa_sitio`** y siembra de los datos de la empresa desde
  `pdf_generator.py` (migración `0058`), que ya los tenía hardcodeados.

### Fixed

- `AVATARES_SQL` seleccionaba `IdUsuario, AvatarBase64` y se leía `fila[0]`: el
  **Id** en vez de la imagen, así que toda ficha salía con iniciales y la app
  leía 150-375 KB inútilmente.
- `RAISERROR` no admite `+` para concatenar el mensaje (`0059` daba "Incorrect
  syntax near '+'").
- El concatenado implícito de cadenas partido en dos líneas dentro de
  `USING (VALUES …)` tampoco lo aceptaba el servidor (`0058`).

### Security

- El secreto de derivación de tokens es **distinto** del del panel: rotar la
  contraseña del panel no invalida las tarjetas NFC ya impresas.

### Changed

- **El panel ahora es de solo lectura** sobre las personas. Lo único que escribe
  es el formulario de datos de la empresa (`HUB_Config`).

### Precio asumido del diseño

Rotar el secreto de derivación **invalida todas las tarjetas**, porque el token
sale de ahí; y ya no hay contador de accesos por tarjeta. Si molesta, la
solución correcta es una tabla de **solo revocación**, no volver a guardar los
tokens.

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
