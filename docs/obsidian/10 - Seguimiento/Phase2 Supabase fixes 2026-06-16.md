# Phase 2 — Supabase fixes pre-migración (2026-06-16)

Preparación de SQL seguro para ejecutar manualmente en Supabase SQL Editor.
Sin ejecución automática. Sin DELETE, DROP, TRUNCATE. Sin cambios a `public.propiedades`.

Ver también: [[Auditoria Supabase 2026-06-16]]

---

## Resumen ejecutivo

| Step | Archivo SQL | Riesgo | Estado |
|------|-------------|--------|--------|
| 1 | `migrations/phase2_step1_rls_scraping_runs.sql` | Bajo | Listo para ejecutar |
| 2 | `migrations/phase2_step2_fix_frontend_map_view.sql` | Bajo | Listo para ejecutar |
| 3 | `migrations/phase2_step3_create_schemas.sql` | Muy bajo | Listo para ejecutar |

**Orden recomendado:** Step 1 → Step 2 → Step 3. Cada uno es independiente.

---

## Verificaciones previas completadas

### Frontend
- Grep en `/frontend`: **cero archivos** referencian `scraping_runs` o `scraping_run_items`.
- El frontend usa la tabla `propiedades` directamente desde Sprint F.
- La vista `v_propiedades_frontend_mapa` no es referenciada en ningún archivo del frontend.

### Scripts Python
- `scraper/config.py` línea 251: `SUPABASE_KEY = SUPABASE_SERVICE_ROLE_KEY` — el scraper usa service_role siempre.
- `scripts/medir_estado.py` línea 11: `SUPABASE_SERVICE_ROLE_KEY` como primera opción.
- `scripts/export_scraping_errors.py` línea 38: ídem.
- `scripts/create_scraping_run_from_next_batch.py`: `SUPABASE_SERVICE_ROLE_KEY or SUPABASE_KEY or NEXT_PUBLIC_SUPABASE_ANON_KEY` — service_role primero.
- `service_role` bypassea RLS completamente en Supabase → agregar RLS no rompe nada.

### Estado actual confirmado por REST API
| Tabla | service_role | anon | Problema |
|-------|-------------|------|---------|
| scraping_runs | 53 | **53** | anon lee TODO |
| scraping_run_items | 2,904 | **2,904** | anon lee TODO |
| propiedades | 94,834 | 94,834 | OK — no tocar |
| v_propiedades_frontend_mapa | **timeout** | **timeout** | BUG doble |

---

## Step 1 — RLS en scraping_runs y scraping_run_items

**Archivo:** `migrations/phase2_step1_rls_scraping_runs.sql`

### Qué hace
1. `REVOKE SELECT` para `anon` y `authenticated` en ambas tablas.
2. `ENABLE ROW LEVEL SECURITY` en ambas tablas.
3. Sin policies = deny-all para roles no-superuser.
4. `service_role` bypassea RLS → scripts internos sin impacto.

### SQL (completo en el archivo, resumen aquí)

```sql
REVOKE SELECT ON public.scraping_runs FROM anon;
REVOKE SELECT ON public.scraping_run_items FROM anon;
REVOKE SELECT ON public.scraping_runs FROM authenticated;
REVOKE SELECT ON public.scraping_run_items FROM authenticated;
REVOKE INSERT, UPDATE, DELETE ON public.scraping_runs FROM anon;
REVOKE INSERT, UPDATE, DELETE ON public.scraping_run_items FROM anon;
REVOKE INSERT, UPDATE, DELETE ON public.scraping_runs FROM authenticated;
REVOKE INSERT, UPDATE, DELETE ON public.scraping_run_items FROM authenticated;

ALTER TABLE public.scraping_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.scraping_run_items ENABLE ROW LEVEL SECURITY;
```

### Verificación post-ejecución (incluida en el archivo)
```sql
-- Verificar RLS activo
SELECT relname, relrowsecurity FROM pg_class
WHERE relname IN ('scraping_runs', 'scraping_run_items');

-- Verificar que service_role sigue leyendo (debe dar > 0)
SELECT COUNT(*) FROM public.scraping_runs;
SELECT COUNT(*) FROM public.scraping_run_items;
```

### Riesgo: BAJO
- No toca datos. Solo permisos.
- Scripts internos: sin impacto (service_role bypassea RLS).
- Frontend: sin impacto (no usaba estas tablas).
- Reversible: `ALTER TABLE ... DISABLE ROW LEVEL SECURITY; GRANT SELECT ON ... TO anon;`

---

## Step 2 — Fix v_propiedades_frontend_mapa

**Archivo:** `migrations/phase2_step2_fix_frontend_map_view.sql`

### Diagnóstico

La vista tiene **dos problemas simultáneos**:

**Bug 1 — filtro de estado (causa las 0 filas):**
```sql
-- ANTES (roto):
WHERE ... AND COALESCE(p.estado, 'activo'::text) = 'activo'::text
-- Resultado: 0 filas porque todos los registros tienen estado='activa'

-- DESPUÉS (fix):
WHERE ... AND p.estado IN ('activa', 'activo', 'desconocida')
-- Resultado: ~44,552 filas (las que tienen latitud IS NOT NULL)
```

**Bug 2 — JOIN lento (causa el timeout HTTP 500):**
```sql
-- ANTES (lento):
FROM propiedades p
JOIN v_propiedades_location_ready plr ON plr.id = p.id   -- lento, timeout
LEFT JOIN inmobiliarias_main i ON i.id = p.inmobiliaria_id

-- DESPUÉS (fix):
FROM propiedades p
LEFT JOIN inmobiliarias_main i ON i.id = p.inmobiliaria_id
-- Se elimina el JOIN con v_propiedades_location_ready
-- ciudad_final y provincia_final ahora leen de p.ciudad / p.provincia
```

### Columnas: sin cambios de nombre ni orden

Las 51 columnas de la vista se preservan exactamente. El cambio en `ciudad_final` y `provincia_final` es de fuente (antes `plr.ciudad_final`, ahora `p.ciudad`), no de nombre. El contenido en producción actual ya era prácticamente el mismo porque `v_propiedades_location_ready` devolvía los mismos valores de `propiedades` con normalización mínima.

### Resultado esperado post-fix
- `SELECT COUNT(*) FROM v_propiedades_frontend_mapa` → ~44,552
- Sin timeout (el JOIN pesado está eliminado)
- `anon` puede leer la vista (el GRANT se re-aplica en el script)

### Riesgo: BAJO
- `CREATE OR REPLACE VIEW` no toca datos.
- El frontend actualmente usa tabla directa, no esta vista (Sprint F).
- El fix es conservador: acepta `'activa'`, `'activo'` y `'desconocida'`.
- Reversible: ejecutar el SQL anterior con el WHERE original.

---

## Step 3 — Crear schemas futuros

**Archivo:** `migrations/phase2_step3_create_schemas.sql`

### Qué hace
```sql
CREATE SCHEMA IF NOT EXISTS internal_scraping;
CREATE SCHEMA IF NOT EXISTS archive;
CREATE SCHEMA IF NOT EXISTS audit;

REVOKE ALL ON SCHEMA internal_scraping FROM anon;
REVOKE ALL ON SCHEMA archive FROM anon;
REVOKE ALL ON SCHEMA audit FROM anon;
-- (ídem para authenticated y PUBLIC)

GRANT USAGE ON SCHEMA internal_scraping TO service_role;
GRANT USAGE ON SCHEMA archive TO service_role;
GRANT USAGE ON SCHEMA audit TO service_role;
```

### Qué NO hace (comentado en el archivo como referencia futura)
- No mueve tablas (requiere autorización y análisis de dependencias).
- No borra nada.

### Riesgo: MUY BAJO
- `CREATE SCHEMA IF NOT EXISTS` es idempotente y no destructivo.
- Reversible: `DROP SCHEMA internal_scraping; DROP SCHEMA archive; DROP SCHEMA audit;`

---

## Step 4 — Tablas backup en public (clasificación, sin acción hoy)

Las 10 tablas backup ya están bloqueadas para `anon` (confirmado por auditoría: anon=0).
No representan riesgo de seguridad inmediato.

| Tabla | Filas | Clasificación | Acción recomendada |
|-------|-------|---------------|-------------------|
| backup_propiedades_inmobiliaria_id_20260518 | 9,016 | Archivo | Mover a `archive` schema (Step 3 habilitado) |
| propiedades_backup_pre_quality_fix | 4,492 | Archivo | Mover a `archive` schema |
| backup_propiedades_run32_ubicacion_20260519 | 330 | Archivo | Mover a `archive` schema |
| backup_propiedades_sin_provincia_20260520 | 133 | Archivo | Mover a `archive` schema |
| backup_propiedades_run36_ciudad_20260520 | 130 | Archivo | Mover a `archive` schema |
| backup_propiedades_run32_ciudad_detectada_20260519 | 45 | Archivo | Mover a `archive` schema |
| backup_propiedades_duplicadas_url_20260518 | 78 | Archivo | Mover a `archive` schema |
| backup_propiedades_duplicadas_url_normalizada_20260518 | 34 | Archivo | Mover a `archive` schema |
| backup_propiedades_run34_encoding_20260520 | 31 | Archivo | Mover a `archive` schema |
| backup_propiedades_coordenadas_invalidas_20260519 | 2 | Archivo | Mover a `archive` schema |

**Todos protegidos para anon (sin urgencia).** El SQL de mover está comentado en `phase2_step3_create_schemas.sql` como referencia. Requiere autorización explícita antes de ejecutar.

---

## Step 5 — tipos_cambio (informe, sin acción)

### Estado actual
| id | tipo | valor | fecha |
|----|------|-------|-------|
| 1 | oficial | 950 ARS/USD | 2026-05-09 |
| 2 | blue | 1,200 ARS/USD | 2026-05-09 |
| 3 | mep | 1,150 ARS/USD | 2026-05-09 |
| 4 | ccl | 1,180 ARS/USD | 2026-05-09 |

**Datos de más de 5 semanas, muy desactualizados.**

### Uso detectado
- Frontend: grep en `/frontend` → sin referencias directas a `tipos_cambio`.
- Scripts: grep en `/scripts` → sin referencias directas.
- La tabla `propiedades` tiene columnas `precio_usd` y `precio_ars` ya calculadas al momento de publicación. Los tipos de cambio de esta tabla no se usan en el pipeline actual.

### Recomendación
- Mantener en `public` por ahora (no es un riesgo de seguridad).
- Si se implementa conversión de moneda en tiempo real: actualizar con fuente automática (BCRA, Ambito, etc.) o manual antes de activar esa funcionalidad.
- No borrar: hay una FK potencial desde funciones de conversión.

---

## Orden de ejecución recomendado

```
Supabase Dashboard → SQL Editor → ejecutar en este orden:

1. Abrir: migrations/phase2_step1_rls_scraping_runs.sql
   → Copiar todo → Ejecutar
   → Verificar: SELECT COUNT(*) FROM scraping_runs → debe dar > 0
   → Verificar por REST con ANON_KEY → debe dar 0 filas

2. Abrir: migrations/phase2_step2_fix_frontend_map_view.sql
   → Copiar todo → Ejecutar
   → Verificar: SELECT COUNT(*) FROM v_propiedades_frontend_mapa → ~44,552

3. Abrir: migrations/phase2_step3_create_schemas.sql
   → Copiar todo → Ejecutar
   → Verificar: SELECT schema_name FROM information_schema.schemata
     WHERE schema_name IN ('internal_scraping', 'archive', 'audit')
```

---

## Qué requiere ejecución manual en SQL Editor

| Acción | Motivo |
|--------|--------|
| Steps 1, 2, 3 | DDL: ALTER TABLE, CREATE OR REPLACE VIEW, CREATE SCHEMA — no disponibles via REST |
| pg_policies (verificación) | Solo accesible desde SQL Editor directo |
| relrowsecurity (verificación) | Solo accesible desde pg_class directo |

Nada de esto se puede ejecutar via REST API.

---

## Qué NO se ejecutó

- No se ejecutó ningún SQL en Supabase en esta sesión.
- No se tocaron datos de `propiedades`.
- No se desactivó ningún RLS existente.
- No se movieron tablas.
- No se borraron datos.
- No se hizo push.
- No se modificó `.env`.
- No se avanzó hacia Batch 100.
- No se migró Neon.
