# Auditoría Supabase — 2026-06-16

Sprint G0 — read-only audit previo a migración Neon → Supabase Pro.

**Restricciones absolutas aplicadas:** solo lectura. Sin DELETE, DROP, TRUNCATE, modificaciones de RLS ni cambios de producción.

**Método:** REST API (SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY + SUPABASE_ANON_KEY) con Python urllib.request — no hay URL directa PostgreSQL en .env.

---

## 1. Inventario general

### Schemas expuestos via REST (PostgREST)

Solo el schema `public` está expuesto. No se detectaron schemas `internal_scraping` ni `audit` — pendientes de crear según Decision tomada.

### Tablas en public (25 tablas de datos)

| Tabla | Filas | Notas |
|-------|-------|-------|
| propiedades | **94,834** | Tabla principal de producción |
| inmobiliarias_main | 7,004 | Tabla canónica de agencias |
| inmobiliarias_scraping | 7,004 | Tabla operativa (mismo volumen, campos distintos) |
| inmobiliarias_staging | 11,538 | Candidatas aún no promovidas |
| scraping_runs | 53 | Historial de corridas de scraping |
| scraping_run_items | 2,904 | Ítems por inmobiliaria por corrida |
| geocoding_results | 670 | Cache de geocoding en Supabase |
| historial_precios | 949 | Cambios de precio detectados |
| property_events | 924 | Eventos (price_drop, price_increase, price_change) |
| property_location_corrections | 346 | Correcciones manuales de ubicación |
| city_normalization_rules | 12 | Reglas de normalización de ciudad |
| tipos_cambio | 4 | USD/ARS: oficial, blue, MEP, CCL |
| zona_metrics | 5 | Métricas por zona |
| property_analysis | 0 | Vacía |
| property_scores | 0 | Vacía |
| geography_columns | — | PostGIS system |
| geometry_columns | — | PostGIS system |
| spatial_ref_sys | — | PostGIS system |

### Tablas de backup en public (10 tablas — clasificación D/E)

| Tabla | Filas |
|-------|-------|
| backup_propiedades_inmobiliaria_id_20260518 | 9,016 |
| backup_propiedades_run32_ubicacion_20260519 | 330 |
| backup_propiedades_sin_provincia_20260520 | 133 |
| backup_propiedades_run36_ciudad_20260520 | 130 |
| backup_propiedades_run32_ciudad_detectada_20260519 | 45 |
| backup_propiedades_duplicadas_url_20260518 | 78 |
| backup_propiedades_duplicadas_url_normalizada_20260518 | 34 |
| backup_propiedades_run34_encoding_20260520 | 31 |
| backup_propiedades_coordenadas_invalidas_20260519 | 2 |
| propiedades_backup_pre_quality_fix | 4,492 |

Todas bloqueadas para anon. Son snapshots de operaciones pasadas — candidatas a `archive` schema o eliminación.

### Vistas en public (35 vistas detectadas)

| Vista | Filas | Estado |
|-------|-------|--------|
| v_propiedades_normalizadas | 94,834 | OK |
| v_propiedades_frontend_mapa | **0** | **⚠️ BUG CRÍTICO** |
| v_propiedades_location_ready | 94,834 | timeout para anon |
| v_next_scraping_batch | — | Sin columna `id` (opera por `inmobiliaria_id`) |
| v_scraping_run_dashboard | — | Sin columna `id` (opera por `scraping_run_id`) |
| v_agency_data_quality_summary | 0 | Vacía |
| v_data_quality_summary | 0 | Vacía |
| v_scraping_priority | — | Sin columna `id` |
| v_agency_scraping_priority | — | Sin columna `id` |
| v_agency_scraping_priority_v2 | — | Sin columna `id` |
| v_agency_scraping_priority_v3 | — | Sin columna `id` |
| v_geocoding_priority | — | Sin columna `id` |
| v_geocoding_priority_clean | — | Sin columna `id` |
| v_inmocapital_radar | — | Sin columna `id` |
| v_property_intelligence | — | Sin columna `id` |
| v_property_opportunity_analysis | — | Sin columna `id` |
| v_city_launch_readiness | — | Sin columna `id` |
| v_city_normalization_review | — | Sin columna `id` |
| v_city_normalized_summary | — | Sin columna `id` |
| v_pending_scraping_items | — | Sin columna `id` |
| v_scraping_operations_center | — | Sin columna `id` |
| v_next_geocoding_batch | — | Sin columna `id` |
| v_location_inconsistencies | — | Sin columna `id` |
| v_location_inconsistencies_v2 | — | Sin columna `id` |
| v_post_scraping_quality_dashboard | — | Sin columna `id` |
| v_property_data_quality | — | Sin columna `id` |
| v_property_events_feed | — | Sin columna `id` |
| v_property_price_history_summary | — | Sin columna `id` |
| v_property_currency_analysis | — | Sin columna `id` |

Nota: "Sin columna `id`" no significa que estén rotas — simplemente no exponen un campo `id` (son vistas de resumen/analítica). El REST count por `?select=id` falla pero las vistas funcionan con sus propios campos.

### Funciones RPC expuestas (no-PostGIS)

| Función | Descripción |
|---------|-------------|
| buscar_por_radio | Búsqueda geoespacial por radio |
| buscar_similar | Búsqueda por similitud (pg_trgm) |
| check_inmolink_password / set_inmolink_password | Autenticación InmoLink |
| claim_next_scraping_item | Pipeline scraping |
| close_scraping_run_if_finished | Pipeline scraping |
| finish_scraping_item_error / _success | Pipeline scraping |
| get_existing_hashes | Deduplicación |
| retry_scraping_item / skip_scraping_item | Pipeline scraping |
| sincronizar_scraping_a_inmobiliarias | Sync scraping → main |
| start_scraping_item | Pipeline scraping |

Más 259 funciones PostGIS (st_*, _st_*, geometry_*, geography_*, etc.).

### Extensiones activas

- **PostGIS** (con soporte completo: geometry, geography, spatial_ref_sys, 259 funciones)
- **pg_trgm** (búsqueda por similitud: `buscar_similar`, `show_trgm`)

---

## 2. Auditoría de producción/frontend

### public.propiedades — 46 columnas

**Schema completo:**

| Columna | Tipo | Notas |
|---------|------|-------|
| id | int | PK |
| inmobiliaria_id | int | FK → inmobiliarias_main, siempre presente (100%) |
| url | text | siempre presente (100%) |
| url_normalizada | text | sin dominio + path normalizado |
| id_externo | text | ID en CMS origen |
| hash_dedup | text | MD5 para deduplicación |
| titulo | text | — |
| descripcion | text | — |
| precio | float | — |
| moneda | text | USD/ARS |
| precio_usd | float | convertido |
| precio_ars | float | convertido |
| expensas | float | — |
| expensas_moneda | text | — |
| tipo_propiedad | text | departamento, casa, terreno, local, campo… |
| operacion | text | venta, alquiler, venta_y_alquiler, consultar |
| ambientes | int | — |
| dormitorios | int | — |
| banos | int | — |
| toilettes | int | — |
| cocheras | int | — |
| antiguedad | text | — |
| piso | text | — |
| superficie_total | float | — |
| superficie_cubierta | float | — |
| superficie_terreno | float | — |
| direccion | text | — |
| barrio | text | — |
| ciudad | text | — |
| provincia | text | — |
| pais | text | — |
| latitud | float | nullable |
| longitud | float | nullable |
| imagenes | text[] | array de URLs |
| video_url | text | — |
| plano_url | text | — |
| amenities | jsonb | — |
| agente_nombre | text | — |
| agente_telefono | text | — |
| fuente_extraccion | text | tokko_html, custom, wordpress… |
| cms_origen | text | tokko, custom, wordpress |
| fecha_publicacion | date | — |
| estado | text | activa, desconocida, no_detectada_en_ultimo_scraping |
| apto_credito | bool | — |
| created_at | timestamptz | — |
| updated_at | timestamptz | — |

**Distribución por estado:**

| Estado | Filas | % |
|--------|-------|---|
| activa | 94,064 | 99.2% |
| desconocida | 763 | 0.8% |
| no_detectada_en_ultimo_scraping | 7 | <0.1% |
| activo (legacy) | 0 | 0% |
| vendida / alquilada / reservada | 0 | 0% |

**Distribución por operacion:**

| Operación | Filas |
|-----------|-------|
| venta | 87,713 |
| alquiler | 5,054 |
| consultar | 1,987 |
| venta_y_alquiler | 66 |
| temporal / otro | 0 |
| (sin clasificar) | ~14 |

**Distribución por moneda:**

| Moneda | Filas | % |
|--------|-------|---|
| USD | 72,731 | 76.7% |
| ARS | 22,103 | 23.3% |

**Completitud de datos clave:**

| Campo | Con dato | Sin dato | % completitud |
|-------|----------|----------|---------------|
| precio | 82,852 | 11,982 | 87.4% |
| latitud/longitud | 44,934 | 49,900 | 47.4% |
| imagenes | 89,516 | 5,318 | 94.4% |
| ciudad | 94,650 | 184 | 99.8% |
| provincia | 94,342 | 492 | 99.5% |
| inmobiliaria_id | 94,834 | 0 | 100% |
| url | 94,834 | 0 | 100% |

**Top tipo_propiedad (muestra 1000):**
departamento 34%, terreno 29%, casa 25%, local 3.5%, campo 2.6%, cochera 2.1%, ph 1.6%

**Top provincias (muestra 1000):**
Buenos Aires ~46%, Córdoba ~20%, Santa Fe ~18%, Río Negro ~9%, Neuquén ~5%

### v_propiedades_frontend_mapa — DIAGNÓSTICO

⚠️ **Estado actual: 0 filas — ROTA**

**Causa raíz:** El WHERE de la vista incluye:
```sql
COALESCE(p.estado, 'activo'::text) = 'activo'::text
```
Pero desde Sprint A (2026-06-09), **todos los registros tienen `estado = 'activa'`** (con 'a'). No existe ninguna fila con `estado = 'activo'`. El filtro excluye 100% de las filas.

**Fix requerido:**
```sql
-- Cambiar de:
COALESCE(p.estado, 'activo'::text) = 'activo'::text
-- A:
p.estado IN ('activa', 'activo', 'desconocida')
```

**Impacto si se corrige:**
- 44,552 propiedades quedarían visibles en el mapa (latitud IS NOT NULL AND estado IN ('activa','activo'))
- La vista también hace `JOIN v_propiedades_location_ready` que causa timeout en anon → necesita índice o reescritura

**Estado actual del frontend:** El frontend fue reconectado a la tabla `propiedades` directa en Sprint F. La vista rota no impacta al usuario hoy, pero bloquea la funcionalidad si se quiere reimplantar la vista.

---

## 3. Auditoría de RLS/permisos

### Acceso por rol

| Tabla | service_role | anon | Evaluación |
|-------|-------------|------|------------|
| propiedades | 94,834 | 94,834 | ✅ OK — read pública intencional |
| inmobiliarias_main | 7,004 | 7,003 | ✅ OK — RLS excluye la 1 inactiva (`activa=false`) |
| inmobiliarias_scraping | 7,004 | 0 | ✅ OK — operativo, bloqueado |
| inmobiliarias_staging | 11,538 | 0 | ✅ OK — operativo, bloqueado |
| **scraping_runs** | **53** | **53** | ⚠️ **EXPOSICIÓN — datos operativos** |
| **scraping_run_items** | **2,904** | **2,904** | ⚠️ **EXPOSICIÓN — datos operativos** |
| geocoding_results | 670 | 0 | ✅ OK — bloqueado |
| historial_precios | 949 | 949 | ⚠️ Menor — datos de precio accesibles |
| property_events | 924 | 924 | ⚠️ Menor — eventos accesibles |
| tipos_cambio | 4 | 4 | ✅ OK — dato público, intencional |
| city_normalization_rules | 12 | 0 | ✅ OK — bloqueado |
| property_location_corrections | 346 | 0 | ✅ OK — bloqueado |
| zona_metrics | 5 | 5 | ✅ OK — métrica pública |
| Todas las backup_* | var. | 0 | ✅ OK — bloqueadas |
| property_analysis | 0 | 0 | N/A — vacía |
| property_scores | 0 | 0 | N/A — vacía |

### Issues de seguridad detectados

**Nivel ALTO:**
- `scraping_runs` y `scraping_run_items`: tablas operativas internas expuestas al rol anon sin restricción. Cualquier visitante del frontend puede leer el historial completo de scraping (53 corridas, 2904 ítems, nombres de inmobiliarias, URLs, errores). No hay dato personal expuesto, pero sí información competitiva y operativa.

**Nivel BAJO:**
- `historial_precios` y `property_events`: accesibles a anon. Esto puede ser intencional (mostrar historial de precios en frontend), pero no hay política documentada al respecto.

### Vistas expuestas al anon

| Vista | service_role | anon | Nota |
|-------|-------------|------|------|
| v_propiedades_normalizadas | 94,834 | 94,834 | Duplica datos de propiedades |
| v_propiedades_frontend_mapa | 0 | 0 | Rota (bug estado) |
| v_propiedades_location_ready | 94,834 | timeout | Timeout sin índice |
| v_next_scraping_batch | — | — | Operativa, sin `id` |
| resto de vistas analíticas | — | — | Sin `id`, funcionan vía otros campos |

---

## 4. Clasificación de utilidad de datos

### A — Mantener en producción (public schema)

| Objeto | Justificación |
|--------|---------------|
| propiedades | Core del producto |
| inmobiliarias_main | FK de propiedades, datos de contacto |
| historial_precios | Funcionalidad futura precio histórico |
| property_events | Trigger-driven, base para alertas |
| tipos_cambio | Conversión USD↔ARS (datos stale — ver observación) |
| geocoding_results | Cache geocoding Supabase |
| property_location_corrections | Correcciones manuales válidas |
| zona_metrics | Métricas por zona |
| city_normalization_rules | Normalización ciudades |

**Observación tipos_cambio:** Los 4 registros son de Mayo 2026 con fuente `demo_manual`. Dólares: oficial=950, blue=1200, MEP=1150, CCL=1180. Desactualizados. Necesitan actualización antes de usar en producción.

### B — Mantener como operativo (candidatos a `internal_scraping` schema)

| Objeto | Justificación |
|--------|---------------|
| inmobiliarias_scraping | Base de candidatas a scrapear |
| inmobiliarias_staging | Pipeline de enriquecimiento |
| scraping_runs | Historial de corridas |
| scraping_run_items | Ítems por corrida |
| v_next_scraping_batch | Vista del pipeline |
| v_scraping_run_dashboard | Dashboard operativo |
| v_scraping_priority | Priorización |
| (demás vistas v_scraping_*) | Pipeline operativo |

### C — Mantener con reserva (revisar uso)

| Objeto | Justificación |
|--------|---------------|
| property_analysis | 0 filas — ¿se usa? |
| property_scores | 0 filas — ¿se usa? |
| v_propiedades_frontend_mapa | Rota, pero tiene lógica imagen_principal_real valiosa |
| v_data_quality_summary | 0 filas — ¿trigger roto? |
| v_agency_data_quality_summary | 0 filas — ídem |

### D — Candidatos a archivar (`archive` schema)

| Objeto | Filas | Justificación |
|--------|-------|---------------|
| backup_propiedades_inmobiliaria_id_20260518 | 9,016 | Snapshot 2026-05-18 |
| backup_propiedades_run32_ubicacion_20260519 | 330 | Snapshot 2026-05-19 |
| backup_propiedades_sin_provincia_20260520 | 133 | Snapshot 2026-05-20 |
| backup_propiedades_run36_ciudad_20260520 | 130 | Snapshot 2026-05-20 |
| backup_propiedades_duplicadas_url_20260518 | 78 | Snapshot 2026-05-18 |
| backup_propiedades_duplicadas_url_normalizada_20260518 | 34 | Snapshot 2026-05-18 |
| backup_propiedades_run34_encoding_20260520 | 31 | Snapshot 2026-05-20 |
| backup_propiedades_run32_ciudad_detectada_20260519 | 45 | Snapshot 2026-05-19 |
| backup_propiedades_coordenadas_invalidas_20260519 | 2 | Snapshot 2026-05-19 |
| propiedades_backup_pre_quality_fix | 4,492 | Pre-fix snapshot |

**Total datos backup:** ~14,293 filas en 10 tablas. Todos ya están en producción con correcciones aplicadas. No hay razón de mantener en public activo.

### E — Eliminar (previo backup externo)

Ningún objeto se clasifica como E en esta auditoría sin confirmación explícita del usuario. Los de categoría D son los candidatos más próximos si se confirma que los fixes aplicados son correctos.

---

## 5. Auditoría de performance e índices

### Problema detectado: v_propiedades_location_ready

La vista `v_propiedades_location_ready` causa statement timeout cuando la consulta es ejecutada por el rol anon (30s timeout de REST). Con service_role devuelve las 94,834 filas OK.

**Impacto en cadena:** `v_propiedades_frontend_mapa` hace `JOIN v_propiedades_location_ready plr ON plr.id = p.id`. Incluso si se corrige el bug de `estado`, la vista del mapa podría no ser utilizable por anon sin optimización.

### Propuestas de índices (NO ejecutar sin autorización)

```sql
-- 1. propiedades: índice para filtro de mapa (estado + latitud)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_propiedades_estado_latitud
ON public.propiedades (estado, latitud)
WHERE latitud IS NOT NULL;

-- 2. propiedades: índice para búsqueda por ciudad
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_propiedades_ciudad
ON public.propiedades (ciudad);

-- 3. propiedades: índice para búsqueda por provincia
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_propiedades_provincia
ON public.propiedades (provincia);

-- 4. propiedades: índice para filtro operacion + precio
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_propiedades_operacion_precio
ON public.propiedades (operacion, precio);

-- 5. propiedades: índice full-text en titulo+descripcion (si se implementa búsqueda textual)
-- CREATE INDEX CONCURRENTLY idx_propiedades_fts ON public.propiedades
-- USING gin(to_tsvector('spanish', coalesce(titulo,'') || ' ' || coalesce(descripcion,'')));
```

**Nota:** Estos índices requieren acceso directo PostgreSQL (no disponible via REST). Se deben ejecutar desde el Dashboard de Supabase > SQL Editor.

---

## 6. Recomendación de schemas

### Estructura propuesta (post-migración Supabase Pro)

```
public/
  ├── propiedades              (producción — 94,834 rows)
  ├── inmobiliarias_main       (producción)
  ├── historial_precios        (producción)
  ├── property_events          (producción)
  ├── tipos_cambio             (producción — actualizar datos)
  ├── geocoding_results        (operativo compartido)
  ├── property_location_corrections (operativo)
  ├── city_normalization_rules (operativo)
  ├── zona_metrics             (producción)
  └── vistas frontend:
      v_propiedades_frontend_mapa  (corregir bug estado + optimizar)
      v_propiedades_normalizadas   (mantener)

internal_scraping/             (nuevo schema — mover aquí)
  ├── inmobiliarias_scraping
  ├── inmobiliarias_staging
  ├── scraping_runs
  ├── scraping_run_items
  └── vistas operativas:
      v_next_scraping_batch
      v_scraping_run_dashboard
      v_scraping_priority
      v_agency_scraping_priority
      v_pending_scraping_items
      v_scraping_operations_center
      v_next_geocoding_batch
      v_geocoding_priority
      v_geocoding_priority_clean
      v_agency_data_quality_summary
      v_data_quality_summary
      v_inmocapital_radar
      (demás v_ analíticas)

archive/                       (nuevo schema — mover aquí)
  ├── backup_propiedades_inmobiliaria_id_20260518
  ├── backup_propiedades_run32_ubicacion_20260519
  ├── (demás 8 tablas backup)
  └── propiedades_backup_pre_quality_fix

audit/                         (nuevo schema — crear vacío)
  └── (tablas de auditoría futura)
```

### Ventajas de esta separación

- **Seguridad**: RLS granular por schema. `internal_scraping` solo accesible con service_role.
- **Claridad**: Una query en `public` es siempre de producción/frontend.
- **Performance**: PostgREST puede configurar `search_path` solo para schemas activos.
- **Mantenimiento**: Los backups no aparecen en el listado de tablas productivas.

---

## 7. Plan de migración Neon → Supabase Pro

**Objetivo:** Supabase Pro pasa a ser la base central. Neon queda como backup temporal hasta validar integridad.

**Estado actual Neon:**
- Storage: 411 MB / 540 MB (76%)
- Tablas: propiedades_raw (189 MB), propiedades_staging (172 MB), data_quality_issues, geocoding_results, scraping_run_items, scraping_runs (Neon side)
- Margen estimado: ~2 batches de 50 antes de llegar al 95%

**Estado actual Supabase:**
- propiedades: 94,834 publicadas ✓
- scraping_runs + scraping_run_items: sincronizados vía pipeline ✓
- inmobiliarias_main + inmobiliarias_scraping: pobladas ✓

### Pasos propuestos (NO ejecutar hasta autorización)

**Paso 1 — Crear schemas en Supabase Pro:**
```sql
CREATE SCHEMA IF NOT EXISTS internal_scraping;
CREATE SCHEMA IF NOT EXISTS archive;
CREATE SCHEMA IF NOT EXISTS audit;
```

**Paso 2 — Mover tablas operativas:**
```sql
ALTER TABLE public.scraping_runs SET SCHEMA internal_scraping;
ALTER TABLE public.scraping_run_items SET SCHEMA internal_scraping;
ALTER TABLE public.inmobiliarias_scraping SET SCHEMA internal_scraping;
-- inmobiliarias_staging: evaluar si mover o eliminar
```

**Paso 3 — Mover backups a archive:**
```sql
ALTER TABLE public.backup_propiedades_inmobiliaria_id_20260518 SET SCHEMA archive;
-- (idem para los 9 restantes)
```

**Paso 4 — Agregar RLS a tablas operativas expuestas:**
```sql
ALTER TABLE public.scraping_runs ENABLE ROW LEVEL SECURITY;
CREATE POLICY "No anon access" ON public.scraping_runs
  FOR SELECT USING (auth.role() = 'service_role');

ALTER TABLE public.scraping_run_items ENABLE ROW LEVEL SECURITY;
CREATE POLICY "No anon access" ON public.scraping_run_items
  FOR SELECT USING (auth.role() = 'service_role');
```

**Paso 5 — Corregir v_propiedades_frontend_mapa:**
```sql
CREATE OR REPLACE VIEW public.v_propiedades_frontend_mapa AS
SELECT /* mismas columnas que antes */
FROM propiedades p
  JOIN v_propiedades_location_ready plr ON plr.id = p.id
  LEFT JOIN inmobiliarias_main i ON i.id = p.inmobiliaria_id
WHERE p.latitud IS NOT NULL
  AND p.longitud IS NOT NULL
  AND p.estado IN ('activa', 'activo', 'desconocida')  -- corregido
  AND p.url NOT ILIKE '%inmocapital.test%'
  AND p.url NOT ILIKE '%localhost%'
  AND p.url NOT ILIKE '%example.com%';
```

**Paso 6 — Migrar pipeline Neon → Supabase:**
- Crear tablas propiedades_raw, propiedades_staging, publish_queue, data_quality_issues en `internal_scraping` schema de Supabase Pro
- Actualizar `INTERNAL_DB_URL` en .env para apuntar a Supabase Pro
- Validar que todos los scripts del pipeline funcionan con `USE_INTERNAL_DB=true`
- Correr Batch 100 dry-run para verificar conectividad y rendimiento

**Paso 7 — Verificación de integridad:**
- Comparar conteos Neon vs Supabase para propiedades_staging, publish_queue
- Validar que los índices en Neon se recrean en Supabase Pro
- Confirmar que el índice `idx_propiedades_staging_status_score_id` existe

**Paso 8 — Desconectar Neon:**
- Mantener Neon en read-only por 30 días
- Cancelar plan Neon después de validación completa

---

## 8. Resumen de issues detectados

### Críticos (bloquean funcionalidad)

| # | Issue | Tabla/Objeto | Fix requerido |
|---|-------|-------------|---------------|
| C1 | `v_propiedades_frontend_mapa` retorna 0 filas | vista frontend | Cambiar `= 'activo'` por `IN ('activa', 'activo')` en WHERE |
| C2 | `v_propiedades_location_ready` timeout para anon | vista auxiliar | Índice en propiedades(latitud) + optimizar JOIN |

### Importantes (seguridad o datos)

| # | Issue | Tabla | Fix requerido |
|---|-------|-------|---------------|
| I1 | scraping_runs expuesta a anon | scraping_runs | Agregar RLS o mover a internal_scraping |
| I2 | scraping_run_items expuesta a anon | scraping_run_items | Ídem |
| I3 | tipos_cambio stale (datos de mayo 2026) | tipos_cambio | Actualizar valores USD/ARS |
| I4 | property_analysis y property_scores vacías | ambas | Verificar si triggers están activos |
| I5 | v_data_quality_summary vacía | vista analítica | Verificar definición de vista |

### Menores (deuda técnica)

| # | Issue | Objeto | Acción |
|---|-------|--------|--------|
| M1 | 10 tablas backup en public | backup_* | Mover a archive schema o eliminar |
| M2 | inmobiliarias_staging (11,538 vs 7,004 main) | staging | Clasificar/sincronizar surplus |
| M3 | property_events/historial_precios sin restricción anon | ambas | Decidir si es intencional |

---

## 9. Tablas del pipeline de Neon NO en Supabase

Estas tablas existen en Neon pero no en Supabase (confirmado — el REST API devuelve 404):

| Tabla Neon | Filas aprox. | Estado |
|-----------|-------------|--------|
| propiedades_raw | ~77k+ | ~189 MB |
| propiedades_staging | ~78k+ | ~172 MB |
| publish_queue | ~11,687 done + pending | — |
| data_quality_issues | ~72,012 (post-cleanup) | ~22 MB |

Al migrar, estas tablas irán al schema `internal_scraping` de Supabase Pro.

---

## 10. Extensiones activas detectadas

| Extensión | Uso |
|-----------|-----|
| PostGIS | Geoespacial completo (buscar_por_radio, geometrías) |
| pg_trgm | Búsqueda por similitud (buscar_similar) |

---

## 11. Triggeres / funciones de negocio detectadas

Detectadas por evidencia indirecta (property_events con source='trigger_historial_precios'):

| Trigger/función | Tabla | Acción |
|----------------|-------|--------|
| trigger_historial_precios | propiedades | Inserta en historial_precios y property_events al detectar cambio de precio |

No se pudieron auditar DDL completos (requiere acceso directo PostgreSQL).

---

## 12. Diagnóstico de datos duplicados

### inmobiliarias_staging vs inmobiliarias_main

- `inmobiliarias_main`: 7,004 filas (tabla canónica productiva)
- `inmobiliarias_staging`: 11,538 filas (candidatas sin promover)
- Diferencia: 4,534 candidatas sin clasificar/promover

Esta diferencia es esperada — staging es el pool de candidatas del cual se seleccionan las que van a main. Sin embargo, 11,538 es un número alto. Pendiente: revisar si hay duplicados entre staging y main.

### Backup inmobiliarias (inmobiliaria_id_20260518): 9,016 filas

El backup más grande de propiedades es de mayo 2026. Representa ~9.5% del total actual (94,834). Ya incorporadas en producción con correcciones.

---

## 13. Estado de las migraciones documentadas

| Archivo | Estado |
|---------|--------|
| `migrations/supabase_sprint_a_operacion_estado.sql` | Aplicada (Sprint A cerrado) |
| `migrations/supabase_sprint_f_rls_public_read.sql` | Aplicada (RLS anon en propiedades funcionando) |
| `reports/.../etapa7e_fix_v_propiedades_frontend_mapa.sql` | **Estado incierto** — etapa7f dice que el fix se aplicó manualmente, pero la vista hoy devuelve 0 filas. El cambio de `inmobiliarias_scraping` → `inmobiliarias_main` se aplicó, pero el bug `estado='activo'` preexistente nunca se corrigió. |

---

## 14. Próximos pasos recomendados (por prioridad)

**Inmediato (no bloquea Batch 100):**
1. Corregir `v_propiedades_frontend_mapa`: cambiar `= 'activo'` → `IN ('activa', 'activo', 'desconocida')` en el WHERE. Solo requiere SQL Editor de Supabase Dashboard.
2. Actualizar `tipos_cambio` con valores actuales de USD.
3. Agregar RLS a `scraping_runs` y `scraping_run_items` (o mover a internal_scraping).

**Antes de Batch 100:**
4. Decidir sobre Neon storage (411 MB / 540 MB = 76%, ~2 batches de margen).
5. Confirmar que Supabase Pro está activado como DB central.

**Con Supabase Pro activo:**
6. Crear schemas `internal_scraping`, `archive`, `audit`.
7. Mover tablas operativas y backups a sus schemas correspondientes.
8. Crear índices de performance en `propiedades` (estado+latitud, ciudad, provincia, operacion+precio).
9. Migrar pipeline Neon → Supabase Pro (propiedades_raw, propiedades_staging, publish_queue).

**Largo plazo:**
10. Activar `property_analysis` y `property_scores` si tienen lógica de negocio pendiente.
11. Corregir `v_propiedades_location_ready` para eliminar timeout en anon.
12. Revisar y depurar las 35 vistas analíticas — muchas pueden estar desactualizadas.

---

## Apéndice: Método de auditoría

- Herramienta: Python 3 + urllib.request contra REST API de Supabase
- Auth: service_role key (bypass RLS) + anon key (perspectiva del usuario)
- Sin acceso directo PostgreSQL (no hay DB URL en .env)
- Columnas y DDL de views deducidos de muestras y archivos .sql del repo
- Tamaños de tablas NO disponibles via REST (requieren `pg_total_relation_size` o Dashboard)
- Índices existentes NO auditables via REST (requieren `pg_indexes` o Dashboard)
- Políticas RLS inferidas por comparación service_role vs anon count

Ver también: [[Registro 2026-06-11]], [[10 - Decisiones importantes]]
