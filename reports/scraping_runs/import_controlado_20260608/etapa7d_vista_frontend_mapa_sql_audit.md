# ETAPA 7D - Auditoria SQL de `v_propiedades_frontend_mapa`

Fecha: 2026-06-09

## Resultado

No se pudo obtener la definicion real de `public.v_propiedades_frontend_mapa` desde el entorno disponible.

Por seguridad:

- No se ejecuto SQL.
- No se genero `CREATE OR REPLACE VIEW`.
- No se genero migracion ejecutable.
- No se tocaron datos, schema, Supabase, publish queue, frontend ni `.env`.
- No se tocaron las 43 warning fuerte.

## Preflight

- Branch: `fix/scraping-diagnostics-batch`.
- HEAD inicial: `5d20c75809 fix(scraping): prioritize real property images before publishing`.
- Staged inicial: vacio.
- `.env` / `frontend` staged: no.
- Procesos peligrosos activos: no se detectaron.
- Working tree: sigue sucio por cambios no relacionados ya conocidos (`docs/obsidian`, scratch scripts, reportes viejos, capturas/JSON auxiliares).

## Intentos de obtener definicion

Variables disponibles luego de cargar entorno:

- `INTERNAL_DB_URL`
- `SUPABASE_ANON_KEY`
- `SUPABASE_SERVICE_ROLE_KEY`
- `SUPABASE_TABLE`
- `SUPABASE_URL`

No hay URL de conexion Postgres/Supabase SQL directa en el entorno.

`psql`:

- No disponible como comando detectable en este entorno.

Busqueda en repo:

- No se encontro `CREATE VIEW` ni `CREATE OR REPLACE VIEW` para `v_propiedades_frontend_mapa`.
- Solo hay referencias en reportes, scripts de validacion y frontend.

REST/PostgREST:

- `GET /rest/v1/pg_views`: 404, no expuesto.
- `GET /rest/v1/information_schema.views`: 404, no expuesto.

Conclusion: no hay forma segura de leer `pg_views.definition` desde este entorno.

## Estado auditado hasta ETAPA 7C

Scope publicado validado: 41 propiedades.

| Dominio | Propiedades | `propiedades.inmobiliaria_id` | Nombre correcto en `inmobiliarias_main` | Nombre en vista |
|---|---:|---:|---|---|
| `pagliaropropiedades.com.ar` | 29 | 4418 | Juan I. Pagliaro Propiedades | Re/Max Jardin |
| `svestudioinmobiliario.com.ar` | 10 | 6335 | SV Inmobiliaria | NULL |
| `inmobiliariamendocasa.com.ar` | 2 | 3532 | INMOBILIARIA & GESTORIA MENDOCASA LAVALLE | Agostina Garofalo Bienes Raices |

Evidencia:

- `propiedades.inmobiliaria_id` esta bien para el piloto.
- `inmobiliarias_main` tiene los nombres correctos para `4418`, `6335` y `3532`.
- La vista devuelve nombres de otros IDs o `NULL`.

La causa raiz exacta no puede confirmarse sin la definicion SQL de la vista.

## SQL exacto para ejecutar en Supabase SQL Editor

Ejecutar primero esta consulta read-only y pegar el resultado completo:

```sql
select
  schemaname,
  viewname,
  definition
from pg_views
where schemaname = 'public'
  and viewname = 'v_propiedades_frontend_mapa';
```

Ejecutar tambien dependencias:

```sql
select
  dependent_ns.nspname as dependent_schema,
  dependent_view.relname as dependent_view,
  source_ns.nspname as source_schema,
  source_table.relname as source_table
from pg_depend
join pg_rewrite on pg_depend.objid = pg_rewrite.oid
join pg_class dependent_view on pg_rewrite.ev_class = dependent_view.oid
join pg_class source_table on pg_depend.refobjid = source_table.oid
join pg_namespace dependent_ns on dependent_ns.oid = dependent_view.relnamespace
join pg_namespace source_ns on source_ns.oid = source_table.relnamespace
where dependent_ns.nspname = 'public'
  and dependent_view.relname = 'v_propiedades_frontend_mapa'
order by source_schema, source_table;
```

Ejecutar columnas actuales de la vista:

```sql
select
  ordinal_position,
  column_name,
  data_type
from information_schema.columns
where table_schema = 'public'
  and table_name = 'v_propiedades_frontend_mapa'
order by ordinal_position;
```

Ejecutar chequeo del piloto:

```sql
select
  p.id,
  p.inmobiliaria_id,
  p.url_normalizada,
  v.inmobiliaria_nombre,
  v.inmobiliaria_web,
  v.inmobiliaria_telefono,
  v.inmobiliaria_email,
  v.imagen_principal_real,
  v.tiene_imagen_real,
  v.ciudad_final,
  v.provincia_final
from public.propiedades p
join public.v_propiedades_frontend_mapa v on v.id = p.id
where p.id in (
  93537,93538,93539,93540,93541,93542,93543,93544,93545,93546,
  93547,93548,93549,93550,93551,93552,93553,93554,93555,93556,
  93557,93558,93559,93560,93561,93562,93563,93564,93565,93566,
  93567,93568,93569,93570,93571,93572,93573,93574,93575,93576,
  93577
)
order by p.id;
```

## Como auditar la definicion cuando este disponible

Revisar en el SQL real:

- De donde salen:
  - `inmobiliaria_nombre`
  - `inmobiliaria_web`
  - `inmobiliaria_telefono`
  - `inmobiliaria_email`
  - `imagen_principal_real`
  - `ciudad_final`
  - `provincia_final`
- Si joinea con:
  - `inmobiliarias_main`
  - `inmobiliarias_staging`
  - `inmobiliarias_scraping`
  - otra tabla auxiliar o CTE.
- Si el join usa:
  - `p.inmobiliaria_id`
  - dominio/url
  - alias/canonical id
  - subquery con ranking o fuzzy match.

## Fix conceptual, no ejecutable

Si la vista esta resolviendo nombres desde una fuente incorrecta, el fix conceptual es que los campos visibles de inmobiliaria salgan de `public.inmobiliarias_main` por `p.inmobiliaria_id`:

```sql
-- Fragmento conceptual. NO ejecutar aislado.
left join public.inmobiliarias_main im
  on im.id = p.inmobiliaria_id
```

Campos esperados:

```sql
im.nombre as inmobiliaria_nombre,
im.web as inmobiliaria_web,
im.telefono_principal as inmobiliaria_telefono,
im.email_principal as inmobiliaria_email
```

No se debe reemplazar la vista hasta tener la definicion completa y preservar todas las columnas existentes.

## Validaciones para despues del fix

Una vez aplicada una migracion revisada, validar:

```sql
-- 1. Count total de vista no cae.
select count(*) as total_view_rows
from public.v_propiedades_frontend_mapa;

-- 2. No hay duplicados por id en vista.
select id, count(*)
from public.v_propiedades_frontend_mapa
group by id
having count(*) > 1;

-- 3. Piloto 41 sigue visible.
select count(*) as piloto_visible
from public.v_propiedades_frontend_mapa
where id in (
  93537,93538,93539,93540,93541,93542,93543,93544,93545,93546,
  93547,93548,93549,93550,93551,93552,93553,93554,93555,93556,
  93557,93558,93559,93560,93561,93562,93563,93564,93565,93566,
  93567,93568,93569,93570,93571,93572,93573,93574,93575,93576,
  93577
);

-- 4. Nombres esperados por dominio.
select
  case
    when p.url_normalizada like 'pagliaropropiedades.com.ar/%' then 'pagliaro'
    when p.url_normalizada like 'svestudioinmobiliario.com.ar/%' then 'sv'
    when p.url_normalizada like 'inmobiliariamendocasa.com.ar/%' then 'mendocasa'
    else 'otro'
  end as dominio,
  v.inmobiliaria_nombre,
  count(*) as total
from public.propiedades p
join public.v_propiedades_frontend_mapa v on v.id = p.id
where p.id in (
  93537,93538,93539,93540,93541,93542,93543,93544,93545,93546,
  93547,93548,93549,93550,93551,93552,93553,93554,93555,93556,
  93557,93558,93559,93560,93561,93562,93563,93564,93565,93566,
  93567,93568,93569,93570,93571,93572,93573,93574,93575,93576,
  93577
)
group by 1, 2
order by 1, 2;
```

Resultado esperado:

- Pagliaro: `Juan I. Pagliaro Propiedades`.
- SV: `SV Inmobiliaria`.
- Mendocasa: nombre canónico de Mendocasa.
- Piloto visible: 41.
- Sin duplicados por `id`.

## Rollback esperado

Antes de aplicar cualquier `CREATE OR REPLACE VIEW`, guardar la definicion actual completa:

```sql
select definition
from pg_views
where schemaname = 'public'
  and viewname = 'v_propiedades_frontend_mapa';
```

Rollback:

```sql
-- Reaplicar la definicion anterior completa guardada.
create or replace view public.v_propiedades_frontend_mapa as
-- definicion anterior completa aqui
;
```

Tambien revisar grants si la vista tiene permisos especificos:

```sql
select grantee, privilege_type
from information_schema.role_table_grants
where table_schema = 'public'
  and table_name = 'v_propiedades_frontend_mapa'
order by grantee, privilege_type;
```

## Recomendacion

No aplicar SQL todavia. Pegar el resultado completo de `pg_views.definition` y dependencias en la proxima etapa. Con eso se puede preparar un `CREATE OR REPLACE VIEW` real que preserve todas las columnas consumidas por frontend.
