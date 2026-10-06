# ECCSA_Colaboradores

Fichas públicas de colaborador en tarjeta NFC.

Toca la tarjeta y el móvil abre la ficha: teléfono, correo, WhatsApp, dirección
de la empresa y un botón para guardar el contacto **con la foto**.

- **Repo:** `hector1516/ECCSA_Colaboradores` (privado)
- **Stack:** Python sin build (`http.server` + `pymssql`), tema oscuro ECCSA
- **Tabla de los tokens:** `HUB_ColaboradorFicha` (migración `0057`, repo HUB)
- **Deploy:** WebbApps, puerto `8105` → `8000`

## Cómo se usa

1. `/admin` (secreto de panel) → **Emitir** por cada persona.
2. Copiar el enlace `/<slug>` y **grabarlo en la tarjeta NFC**.
3. Quien toca la tarjeta abre la ficha. Sin instalar nada.

El enlace **no cambia nunca**: por eso el token es aleatorio de 32 caracteres y
no `nombre + últimos 4 del teléfono` (10^4 combinaciones, se barren en
segundos).

## Desarrollo

```bash
python3 tests/test_app.py                      # 25 tests, sin BD
HUB_DB_DATABASE=ECCSA_Admon_Pruebas \
  DATA_DIR=$PWD/data python3 -m panel.server    # en :8000
```

Ver `AGENTS.md` para las reglas de datos, seguridad y deploy.
