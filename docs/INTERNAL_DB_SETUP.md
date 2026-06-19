# Internal DB Setup (Neon u otro Postgres dedicado al scraper)

Guía para preparar y activar la **base interna opcional** de ERETZ Propiedades.
La base interna aloja **solo** las tablas de cola, geocoding cache y staging
del scraper. La base **pública (Supabase)** sigue siendo la fuente única de
verdad para `propiedades`, `inmobiliarias_main` y las vistas que consume el
frontend.

> Esta guía **no activa nada en producción**. Solo deja preparada la
> infraestructura. La DB interna queda inactiva hasta que se setee
> `USE_INTERNAL_DB=true` explícitamente.

---

## 1. Por qué una base interna separada

El frontend público (Next.js) solo necesita leer una vista liviana de
`propiedades`. El scraper, en cambio, hace muchísimo I/O sobre tablas de
cola (`scraping_run_items` con `metadata` JSONB pesado), retries, geocoding
y repairs. Cuando ambos comparten la misma instancia, los picos de scraping
pueden saturar la base y afectar la latencia del frontend.

Separar resuelve eso:

- **Supabase** sigue sirviendo `propiedades`, `inmobiliarias_main` y vistas
  públicas (lectura del frontend, sin presión de writes).
- **Neon** (o cualquier Postgres dedicado) aloja:
  - `scraping_runs`
  - `scraping_run_items`
  - `geocoding_results`
  - `inmobiliarias_staging`

El scraper escribe en una u otra base según corresponda. `propiedades` y
`inmobiliarias_main` **siempre** van a Supabase.

---

## 2. Crear el proyecto Neon

1. Crear cuenta gratis en [neon.tech](https://neon.tech).
2. Crear nuevo proyecto:
   - Nombre sugerido: `inmocapital-scraper-internal`
   - Región: la más cercana a tu Supabase actual (usualmente `aws-us-east-1`)
   - Postgres version: la más reciente disponible (16+)
3. Una vez creado, anotar el **connection string** que muestra Neon. Tiene
   la forma:

   ```
   postgres://USUARIO:PASSWORD@ep-xxxxxxxx.aws.neon.tech/dbname?sslmode=require
   ```

   - `sslmode=require` es obligatorio en Neon. Dejarlo tal como viene.
   - **No** compartir este string ni commitearlo al repo.

---

## 3. Guardar `INTERNAL_DB_URL` en `.env` local

Editar **solo el `.env` local** (nunca el `.env.example`):

```env
# Optional internal PostgreSQL/Neon database for scraper-only tables.
USE_INTERNAL_DB=false
INTERNAL_DB_URL=postgres://USUARIO:PASSWORD@ep-xxxxxxxx.aws.neon.tech/dbname?sslmode=require
```

**Importante:**

- Dejar `USE_INTERNAL_DB=false` por ahora. El scraper seguirá usando
  Supabase para todo. La URL queda solo guardada para validar después.
- **No** commitear `.env`. Está en `.gitignore`.
- El `.env.example` ya documenta estas dos variables. Si alguien clona el
  repo, solo necesita copiar el ejemplo y pegar su URL.

---

## 4. Instalar `psycopg`

El cliente Python `InternalDBClient` usa `psycopg` (versión 3). No se
instala automáticamente para no agregar peso al runtime cuando la DB
interna está apagada.

Cuando vayas a activarla, instalar:

```bash
pip install "psycopg[binary]>=3.1"
```

`psycopg[binary]` incluye la librería nativa precompilada y no requiere
gcc en Windows. Si preferís compilar a mano (Linux server), usar
`psycopg>=3.1` sin el extra `[binary]` y tener instalado `libpq-dev`.

> Mientras `USE_INTERNAL_DB=false`, `psycopg` **no es necesario**. El
> scraper detecta el flag antes de importar la librería y no rompe.

---

## 5. Aplicar el schema a Neon

Una vez configurado `INTERNAL_DB_URL`:

```bash
psql "$INTERNAL_DB_URL" -f internal_db_schema.sql
```

En PowerShell:

```powershell
psql "$env:INTERNAL_DB_URL" -f internal_db_schema.sql
```

El script:

- Crea las 4 tablas (`scraping_runs`, `scraping_run_items`,
  `geocoding_results`, `inmobiliarias_staging`).
- Crea los índices recomendados.
- Crea las 6 funciones RPC que espera `InternalDBClient`.
- **Es idempotente**: usa `CREATE TABLE IF NOT EXISTS` y
  `CREATE OR REPLACE FUNCTION`. Se puede re-ejecutar sin pérdida.
- **No contiene** `DROP`, `TRUNCATE` ni `DELETE`.

---

## 6. Verificar que todo está creado

### Tablas

```bash
psql "$INTERNAL_DB_URL" -c "\dt public.*"
```

Debería listar:

```
 Schema |          Name           | Type  |
--------+-------------------------+-------+
 public | geocoding_results       | table |
 public | inmobiliarias_staging   | table |
 public | scraping_run_items      | table |
 public | scraping_runs           | table |
```

### Funciones

```bash
psql "$INTERNAL_DB_URL" -c "\df public.*"
```

Debería listar las 6:

```
 claim_next_scraping_item
 close_scraping_run_if_finished
 finish_scraping_item_error
 finish_scraping_item_success
 retry_scraping_item
 start_scraping_item
```

### Conexión sana

```bash
psql "$INTERNAL_DB_URL" -c "SELECT now();"
```

Debería responder en menos de 2 segundos.

---

## 7. Prueba futura con `USE_INTERNAL_DB=true` (sesión aislada)

> **No activar el flag en `.env`** todavía. Probar primero en una sesión
> aislada (solo en esa terminal). Si algo falla, no afecta otros procesos.

### En PowerShell

```powershell
cd "D:\INMO CAPITAL\Inmo-Capital-main"
$env:USE_INTERNAL_DB = "true"
# (la variable solo vive en esta sesión; cerrar la terminal la limpia)

# 1) crear una run chiquita en Neon (3 items)
python scripts/create_scraping_run_from_next_batch.py --limit 3 --include-new --commit

# 2) verificar en Neon
psql "$env:INTERNAL_DB_URL" -c "SELECT id, status, total_inmobiliarias_planificadas FROM scraping_runs ORDER BY id DESC LIMIT 1;"
psql "$env:INTERNAL_DB_URL" -c "SELECT count(*) FROM scraping_run_items WHERE scraping_run_id = (SELECT max(id) FROM scraping_runs);"

# 3) procesar 1 item para validar el ciclo completo
python scraper/scraper_propiedades.py --workers 1 --max-items 1

# 4) confirmar que la run cerró
psql "$env:INTERNAL_DB_URL" -c "SELECT id, status, finished_at FROM scraping_runs ORDER BY id DESC LIMIT 1;"

# 5) confirmar que las propiedades aterrizaron en Supabase (no en Neon)
# (usar la consola de Supabase o un select corto contra propiedades).
```

### En Bash

```bash
cd "/d/INMO CAPITAL/Inmo-Capital-main"
USE_INTERNAL_DB=true python scripts/create_scraping_run_from_next_batch.py --limit 3 --include-new --commit
# (cada comando que use USE_INTERNAL_DB necesita el prefijo si no lo exportás)
```

### Qué validar antes de activar permanente

- `scraping_runs` y `scraping_run_items` se crean en **Neon**.
- `claim_next_scraping_item()` devuelve un item válido.
- El item pasa por `running` → `success` (o `error` controlado).
- `close_scraping_run_if_finished` cierra la run.
- Las **propiedades extraídas** siguen llegando a `propiedades` en
  **Supabase** (no en Neon).
- Sin errores `psycopg.OperationalError` ni `column does not exist`.

Si todo lo anterior pasa, se puede setear `USE_INTERNAL_DB=true` en `.env`
de forma permanente.

---

## 8. Cómo desactivar la DB interna

Si la activaste y querés volver al comportamiento 100% Supabase (sin
reiniciar nada destructivo):

1. Editar `.env`:

   ```env
   USE_INTERNAL_DB=false
   # INTERNAL_DB_URL se puede dejar tal como está; el flag lo desactiva igual
   ```

2. Reiniciar el scraper / scripts que estén corriendo.

3. El log del scraper debería mostrar:

   ```
   [internal-db] disabled: USE_INTERNAL_DB is not true; using Supabase for queue
   ```

4. A partir de ese momento, **toda** lectura/escritura de cola vuelve a
   Supabase. La data que quedó en Neon no se pierde, simplemente queda
   inactiva. Si después querés re-activar, los runs antiguos siguen ahí.

> Importante: si activaste Neon y procesaste runs ahí, la cola de Supabase
> quedó "vieja". Al volver a `USE_INTERNAL_DB=false`, el scraper va a
> ignorar lo que pasó en Neon. Sincronizar manualmente solo si es
> necesario (no debería serlo para una vuelta atrás controlada).

---

## 9. Recordatorios de seguridad

- **No commitear `.env`** con la URL real de Neon.
- **No commitear `docs/obsidian/`** ni `docs/obsidian/.obsidian/`. Son
  notas personales del usuario.
- **No correr `psql` con destructivos** (`DROP`, `TRUNCATE`, `DELETE`) en
  la base interna salvo respaldo previo.
- **No copiar la URL** a un canal compartido. Si se filtra, rotarla
  desde el panel de Neon.
- **No usar `INTERNAL_DB_URL` desde el frontend.** El frontend solo
  habla con Supabase vía `NEXT_PUBLIC_SUPABASE_URL` y
  `NEXT_PUBLIC_SUPABASE_ANON_KEY`.

---

## 10. Rollback de schema

El script `internal_db_schema.sql` es idempotente. Si necesitás corregir
una columna agregada incorrectamente:

- Para **agregar** una columna nueva sin perder data: editar el script
  con `ALTER TABLE ... ADD COLUMN IF NOT EXISTS ...` y re-ejecutar.
- Para **renombrar** o **eliminar** columnas: hacer un nuevo SQL aparte,
  con `ALTER TABLE ... RENAME COLUMN ...` o `ALTER TABLE ... DROP COLUMN
  IF EXISTS ...`. Esto **no** está incluido en `internal_db_schema.sql`
  para evitar accidentes.

---

## 11. Próximo paso si todo funciona

Cuando las pruebas pasen y el sistema esté estable con `USE_INTERNAL_DB=true`:

- Fase 2: adaptar `scraper/geocoder.py` para usar Neon (ahora aún apunta
  100% a Supabase para `geocoding_results`).
- Fase 3: documentar el flujo dual en el README principal.
- Fase 4: medir si Supabase libera presión y si los timeouts/522 desaparecen.

Hasta entonces, esta guía deja todo preparado pero **inactivo**.
