# ETAPA 7E - Fix SQL para `v_propiedades_frontend_mapa`

Fecha: 2026-06-09

## Resultado

Se preparo el SQL final revisable para corregir la fuente de `inmobiliaria_nombre` en `public.v_propiedades_frontend_mapa`.

No se ejecuto SQL. No se toco Supabase. No se tocaron datos, frontend, `.env`, publish queue, imports ni geocoding.

Archivo SQL:

`reports/scraping_runs/import_controlado_20260608/etapa7e_fix_v_propiedades_frontend_mapa.sql`

## Causa raiz

La definicion real de la vista usa:

```sql
LEFT JOIN inmobiliarias_scraping i ON i.id = p.inmobiliaria_id
```

Pero las propiedades publicadas usan `propiedades.inmobiliaria_id` como ID canonico de `inmobiliarias_main`.

Efecto observado en el piloto:

- Pagliaro aparece como `Re/Max Jardin`.
- SV aparece como `NULL`.
- Mendocasa aparece como `Agostina Garofalo`.

## Cambio exacto

Unico cambio logico permitido:

```sql
LEFT JOIN inmobiliarias_scraping i ON i.id = p.inmobiliaria_id
```

por:

```sql
LEFT JOIN inmobiliarias_main i ON i.id = p.inmobiliaria_id
```

Se preserva:

- columnas;
- orden de columnas;
- alias;
- `WHERE`;
- join a `v_propiedades_location_ready`;
- logica de `imagen_principal_real`;
- logica de `tiene_imagen_real`;
- nombres que consume el frontend.

## Por que es seguro

El cambio no modifica `propiedades`, no cambia filtros ni agrega filas por si mismo. Solo cambia la tabla desde donde se resuelven los campos:

- `inmobiliaria_nombre`
- `inmobiliaria_web`
- `inmobiliaria_telefono`
- `inmobiliaria_email`

La evidencia previa indica que `p.inmobiliaria_id` ya coincide con `inmobiliarias_main.id` para el piloto.

## SQL final

```sql
create or replace view public.v_propiedades_frontend_mapa as
SELECT p.id,
    p.inmobiliaria_id,
    p.url,
    p.titulo,
    p.descripcion,
    p.precio,
    p.moneda,
    p.precio_usd,
    p.precio_ars,
    p.expensas,
    p.expensas_moneda,
    p.tipo_propiedad,
    p.operacion,
    p.ambientes,
    p.dormitorios,
    p.banos,
    p.toilettes,
    p.cocheras,
    p.antiguedad,
    p.piso,
    p.superficie_total,
    p.superficie_cubierta,
    p.superficie_terreno,
    p.direccion,
    p.barrio,
    p.ciudad AS ciudad_original,
    p.provincia AS provincia_original,
    plr.ciudad_final,
    plr.provincia_final,
    p.pais,
    p.latitud,
    p.longitud,
    p.imagenes,
    p.video_url,
    p.plano_url,
    p.amenities,
    p.agente_nombre,
    p.agente_telefono,
    p.fuente_extraccion,
    p.cms_origen,
    p.fecha_publicacion,
    p.estado,
    p.created_at,
    p.updated_at,
    p.apto_credito,
    i.nombre AS inmobiliaria_nombre,
    i.web AS inmobiliaria_web,
    i.telefono_principal AS inmobiliaria_telefono,
    i.email_principal AS inmobiliaria_email,
        CASE
            WHEN p.imagenes IS NOT NULL AND array_length(p.imagenes, 1) > 0 AND p.imagenes[1] !~~ '%static.tokkobroker.com/tfw/img/prop-icons%'::text AND p.imagenes[1] !~~* '%unsplash.com%'::text AND p.imagenes[1] !~~* '%placeholder%'::text AND p.imagenes[1] !~~* '%no-photo%'::text AND p.imagenes[1] !~~* '%sin-imagen%'::text AND p.imagenes[1] !~~* '%360%'::text AND p.imagenes[1] !~~* '%tour%'::text AND p.imagenes[1] !~~* '%virtual%'::text THEN p.imagenes[1]
            ELSE NULL::text
        END AS imagen_principal_real,
        CASE
            WHEN p.imagenes IS NOT NULL AND array_length(p.imagenes, 1) > 0 AND p.imagenes[1] !~~ '%static.tokkobroker.com/tfw/img/prop-icons%'::text AND p.imagenes[1] !~~* '%unsplash.com%'::text AND p.imagenes[1] !~~* '%placeholder%'::text AND p.imagenes[1] !~~* '%no-photo%'::text AND p.imagenes[1] !~~* '%sin-imagen%'::text AND p.imagenes[1] !~~* '%360%'::text AND p.imagenes[1] !~~* '%tour%'::text AND p.imagenes[1] !~~* '%virtual%'::text THEN true
            ELSE false
        END AS tiene_imagen_real
   FROM propiedades p
     JOIN v_propiedades_location_ready plr ON plr.id = p.id
     LEFT JOIN inmobiliarias_main i ON i.id = p.inmobiliaria_id
  WHERE p.latitud IS NOT NULL AND p.longitud IS NOT NULL AND COALESCE(p.estado, 'activo'::text) = 'activo'::text AND p.url !~~* '%inmocapital.test%'::text AND p.url !~~* '%localhost%'::text AND p.url !~~* '%example.com%'::text;
```

## Validaciones a ejecutar despues

```sql
select count(*) as total_view_rows
from public.v_propiedades_frontend_mapa;

select id, count(*)
from public.v_propiedades_frontend_mapa
group by id
having count(*) > 1;

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

- Pagliaro -> `Juan I. Pagliaro Propiedades`.
- SV -> `SV Inmobiliaria`.
- Mendocasa -> `INMOBILIARIA & GESTORIA MENDOCASA LAVALLE`.
- Piloto visible: 41.
- Sin duplicados por `id`.

Validacion adicional recomendada:

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

Comparar contra las 51 columnas esperadas y confirmar que no cambio el orden.

## Rollback

Rollback conceptual: reaplicar la misma definicion, cambiando el join de vuelta a `inmobiliarias_scraping`:

```sql
create or replace view public.v_propiedades_frontend_mapa as
-- misma definicion completa, con:
-- LEFT JOIN inmobiliarias_scraping i ON i.id = p.inmobiliaria_id
;
```

Antes de ejecutar el fix, guardar la definicion actual completa desde `pg_views` para rollback exacto.

## Estado final

El SQL esta listo para pegar manualmente en Supabase SQL Editor. Codex no lo ejecuto.
