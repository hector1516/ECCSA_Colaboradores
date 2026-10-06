# AGENTS.md — ECCSA_Colaboradores
> Lo que un agente (humano o IA) necesita saber para trabajar en esta app.
> Los tokens de este chat (leer `secretos_local.example.py`) no van aquí.

# 1 · Qué es

Fichas públicas de colaborador, una por persona, en una URL fija que se
**graba en una tarjeta NFC**. Quien toca la tarjeta con el móvil abre la ficha
y tiene el contacto, el WhatsApp, la dirección y un botón para guardarlo.

- **App pública:** `GET /<slug>` → la ficha. Sin sesión. El token ES la
  autorización.
- **Panel privado:** `/admin` → emitir, revocar y reactivar tokens, y editar
  los datos de la empresa.

Stack: **`plain` (Python sin build)**. El servidor es `http.server` de la
biblioteca estándar. Es deliberado: la app es *un* GET que devuelve HTML o un
vCard, y meter Vite/FastAPI sería complejidad sin beneficio.

## Dónde vive cada dato

**Todo se toma de `HUB_Users`** (menos el teléfono). Verificado contra
producción y pruebas: las columnas existen, pero hoy están **vacías** las 11
filas — la foto y el puesto se suben desde `/admin`.

| Dato | Origen |
|---|---|
| Nombre, correo, **puesto** | `HUB_Users` — **solo lectura**. Esta app no escribe nada ahí |
| **Foto** | `HUB_UsuariosFotos.Archivo` — la sube el usuario desde **Admon** (VARBINARY en tabla aparte, migración `0045` de AdmonApp, creada justo para que otra app la pidiera por `IdUsuario`). Se recorta a 320x320 JPEG al pintar |
| **Teléfono móvil** | `MAC.Telefono` — **NO** está en `HUB_Users`, que no tiene columna de teléfono. Es la misma fuente que usan HUB y Field (`get_user_phone`), para que no haya dos números distintos |
| **Token de la URL**, accesos | `HUB_ColaboradorFicha` — tabla propia, migración `0057` en el repo **HUB** |
| Dirección, redes, WhatsApp, coordenadas | `HUB_Config`, claves `colab_empresa_*` |

> **Por qué la tabla de fichas vive en el repo HUB y no aquí:** todas las apps
> leen `ECCSA_Admon`. Si la tabla estuviera en este repo, `field` o `mailbox`
> no podrían consultarla sin depender de un repo ajeno. Para pegarse desde
> cualquier app:
>
> ```sql
> SELECT f.Slug, u.Nombre, u.Email
> FROM   HUB_ColaboradorFicha f
> JOIN   HUB_Users u ON u.Id = f.IdUsuario
> WHERE  f.Activo = 1;
> ```

## El slug: por qué NO es `usuario + 4 dígitos`

`hectorpena1516` son 10^4 combinaciones y se barren en segundos. Un link en una
tarjeta física no puede cambiar, así que **la seguridad no puede vivir en la
URL**: vive en Cloudflare (WAF + rate limiting + Bot Fight, §3 del manual).

Aun así el slug es `nombre-32-caracteres-aleatorios` (Crockford Base32,
160 bits), porque el nombre legible no cuesta nada y los 32 caracteres sí
protegen. El prefijo es ergonomía, NO seguridad.

## Reglas que no se rompen

1. **El token NUNCA se escribe en un log.** La ruta ES el token, y
   `log_message` está anulado a propósito. El log lleva método, código e IP.
2. **404 idéntico** para token inexistente, revocado y con forma inválida. Si
   difieren, se puede enumerar qué tokens existieron.
3. **`secrets`, nunca `random`**, para generar tokens. Un PRNG no
   criptográfico se predice a partir de unos ejemplos.
4. **El slug va en texto plano**, no hasheado. Un token solo sirve si se puede
   buscar por igualdad; hasheado habría que regenerarlo en cada visita y la NFC
   física dejaría de abrir. Mismo patrón que los tokens de sesión.
5. **`COLLATE ..._BIN2`** en `Slug`: sin eso, `aB3x` y `AB3X` serían el mismo
   token (la collation normal de SQL Server no distingue mayúsculas) y se
   perdería ~1 bit de entropía por carácter.

## Comandos

```bash
# Tests (25, sin BD ni servidor externo)
python3 tests/test_app.py

# Correr local contra la BD de PRUEBAS
HUB_DB_DATABASE=ECCSA_Admon_Pruebas DATA_DIR=$PWD/data python3 -m panel.server

# Emitir tokens (el panel es la vía normal; esto es para empezar)
HUB_DB_DATABASE=ECCSA_Admon_Pruebas python3 -c "
import sys; sys.path.insert(0,'.')
from panel import tokens; print(tokens.emitir(2))"
```

La app **no arranca sin secreto de panel** (`data/admin_secret.txt`, o
`$DATA_DIR`). Se genera con:
`python3 -c "import secrets;print(secrets.token_urlsafe(32))" > data/admin_secret.txt`

## Deploy

```
push a main  →  GitHub Actions (runner en WebbApps)
              →  docker build hector1516/colaboradores
              →  /opt/apps/colaboradores/app.conf  (puerto 8105:8000)
              →  secretos en /etc/colaboradores.env (600, fuera del repo)
```

- **`APP_AUTO_START=0`**: el contenedor queda en `created` y NO arranca hasta
  que alguien lo pida: `sudo bash /opt/apps/_lib/run_app.sh colaboradores`.
- **Nunca `docker rm -v`**: el volumen `colaboradores_data` guarda el secreto
  del panel.
- **Producción = `HUB_DB_DATABASE=ECCSA_Admon`.** Para pruebas,
  `ECCSA_Admon_Pruebas`.
- **Después de un deploy, verificar DENTRO del contenedor** (`grep`), no confiar
  en el "success" del CI: el cache de Docker deja el contenedor viejo.

## Shell (ECCSA)

Alta en `ECCSA-Shell/tools/sync_shell.py` → `APPS` (variante `plain`, CSS en
`panel/shell.css`) + `CANDIDATES`, y en `tools/propagate.py` → `REPOS`
(`hector1516/ECCSA_Colaboradores`, rama `main`).

```bash
python3 ECCSA-Shell/tools/sync_shell.py --target . --variant plain
python3 ECCSA-Shell/tools/sync_shell.py --target . --check   # debe dar OK
```

`panel/shell.css` es **copia canónica**: no se edita a mano. Lo propio de la app
va en `panel/ficha.css`. `GET /api/shell/state` responde sin sesión, como el
kiosco del Dashboard (§2b del contrato): `user` va en `null`.

## Pendiente (no está hecho todavía)

- **Cloudflare**: falta el public hostname `colaboradores` en el túnel
  `b4e86661-8992-4069-b8f1-85ae9de3436a` → `localhost:8105`, y las reglas de WAF
  / Bot Fight / rate limiting. **Es la capa de seguridad principal.**
- **Datos de la empresa**: la dirección y el sitio ya vienen sembrados desde
  `pdf_generator.py` (migración `0058`); WhatsApp, Facebook, Instagram y las
  coordenadas siguen vacías y se llenan desde `/admin`.
- **Los 11 usuarios tienen `Puesto` vacío** en `HUB_Users`; el panel muestra "—"
  y la ficha omite el subtítulo hasta que AdmonApp lo llene.
- **Iconos PWA**: no hay manifest ni iconos (la app no se instala; se abre en
  el navegador desde la NFC).
