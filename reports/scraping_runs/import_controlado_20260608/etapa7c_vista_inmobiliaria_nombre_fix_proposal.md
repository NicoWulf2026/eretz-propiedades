# ETAPA 7C - Propuesta para corregir `inmobiliaria_nombre` en vista frontend

Fecha: 2026-06-09

## Estado

No se ejecutó SQL. No se hicieron writes en Supabase.

Vista afectada:

- `v_propiedades_frontend_mapa`

Scope auditado:

- 41 propiedades publicadas del piloto.
- 29 Pagliaro.
- 10 SV Estudio.
- 2 Mendocasa.

## Hallazgo

La tabla `propiedades` contiene el `inmobiliaria_id` esperado para las 41 propiedades:

| Dominio fuente | inmobiliaria_id publicado | Nombre correcto en `inmobiliarias_main` | Nombre visible en vista |
|---|---:|---|---|
| `pagliaropropiedades.com.ar` | 4418 | Juan I. Pagliaro Propiedades | Re/Max Jardin |
| `svestudioinmobiliario.com.ar` | 6335 | SV Inmobiliaria | NULL |
| `inmobiliariamendocasa.com.ar` | 3532 | INMOBILIARIA & GESTORIA MENDOCASA LAVALLE | Agostina Garofalo Bienes Raices |

Lecturas REST confirmadas:

- `inmobiliarias_main.id = 4418` -> `Juan I. Pagliaro Propiedades`.
- `inmobiliarias_main.id = 6335` -> `SV Inmobiliaria`.
- `inmobiliarias_main.id = 3532` -> `INMOBILIARIA & GESTORIA MENDOCASA LAVALLE`.
- `inmobiliarias_main.id = 6674` -> `Re/Max Jardin`.
- `inmobiliarias_main.id = 6446` -> `Agostina Garofalo Bienes Raices`.

Conclusión:

El problema no parece estar en `propiedades.inmobiliaria_id` para este piloto. La evidencia apunta a la definición de `v_propiedades_frontend_mapa` o a una resolución/lookup auxiliar usada por esa vista.

## Definición SQL

No se encontró la definición SQL de `v_propiedades_frontend_mapa` en el repo.

Intentos read-only vía REST:

- `pg_views`: no expuesto por PostgREST.
- `information_schema.views`: no expuesto por PostgREST.

Por esa razón, no se incluye un `CREATE OR REPLACE VIEW` completo. Hacerlo sin definición real arriesga romper columnas, filtros, permisos o lógica existente.

## Qué consultar en Supabase SQL Editor

Ejecutar solo lectura:

```sql
select
  schemaname,
  viewname,
  definition
from pg_views
where schemaname = 'public'
  and viewname = 'v_propiedades_frontend_mapa';
```

También conviene revisar dependencias:

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

## Validación esperada del fix

Después de corregir la vista, estas consultas deberían devolver nombres correctos:

```sql
select
  p.id,
  p.inmobiliaria_id,
  p.url_normalizada,
  v.inmobiliaria_nombre,
  v.inmobiliaria_web
from propiedades p
join v_propiedades_frontend_mapa v on v.id = p.id
where p.id in (93537,93538,93539,93540,93541,93542,93543,93544,93545,93546,
               93547,93548,93549,93550,93551,93552,93553,93554,93555,93556,
               93557,93558,93559,93560,93561,93562,93563,93564,93565,93566,
               93567,93568,93569,93570,93571,93572,93573,93574,93575,93576,93577)
order by p.id;
```

Resultado esperado por dominio:

- `pagliaropropiedades.com.ar`: `Juan I. Pagliaro Propiedades`.
- `svestudioinmobiliario.com.ar`: `SV Inmobiliaria`.
- `inmobiliariamendocasa.com.ar`: nombre canónico de Mendocasa.

## Fix conceptual

La vista debería resolver `inmobiliaria_nombre` desde la fuente canónica correcta, preferentemente:

```sql
-- Fragmento conceptual, no ejecutar como reemplazo de vista.
left join public.inmobiliarias_main im
  on im.id = p.inmobiliaria_id
```

y exponer:

```sql
im.nombre as inmobiliaria_nombre,
im.web as inmobiliaria_web,
im.telefono_principal as inmobiliaria_telefono,
im.email_principal as inmobiliaria_email
```

Este fragmento no reemplaza la definición real de la vista. Debe integrarse sobre el SQL existente.

## Riesgos

- `v_propiedades_frontend_mapa` ya tiene columnas y lógica consumidas por frontend.
- Cambiar la vista sin copiar la definición completa puede romper columnas como `ciudad_final`, `provincia_final`, `imagen_principal_real` o `tiene_imagen_real`.
- Si la vista usa reglas de canonicalización adicionales, hay que preservar esa lógica o reemplazarla explícitamente.

## Rollback

Antes de aplicar cualquier cambio:

1. Guardar la definición actual completa desde `pg_views`.
2. Versionarla en un reporte o migración.
3. Aplicar `CREATE OR REPLACE VIEW` solo con la definición completa revisada.

Rollback:

```sql
-- Reaplicar la definición anterior completa guardada desde pg_views.
create or replace view public.v_propiedades_frontend_mapa as
-- definición anterior completa aquí
;
```

## Próximo paso

Abrir Supabase SQL Editor, extraer la definición real de la vista y preparar una migración revisable. No aplicar SQL hasta comparar columnas antes/después contra el frontend.
