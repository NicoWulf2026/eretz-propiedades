# Validación Piloto Pinamar — 21 propiedades marcelgestion.com.ar

**Fecha:** 2026-06-08  
**Responsable:** Sprint Autónomo Controlado — validación post-publicación  
**Scope:** 21 propiedades inmo_id=4019 (marcelgestion.com.ar), sb_ids 6725–6790  
**Modo:** Read-only — sin escrituras, sin cambios de schema, sin git push

---

## Resumen ejecutivo

| Dimensión | Resultado |
|-----------|-----------|
| Propiedades en Supabase | **21/21** ✓ |
| Visibles en view frontend | **21/21** ✓ |
| Dentro de bbox Pinamar | **21/21** ✓ |
| Estado = activo | **21/21** ✓ |
| Moneda USD | **21/21** ✓ |
| Imágenes ≥ 3 | **21/21** ✓ (10 cada una) |
| tiene_imagen_real | **20/21** ✓ (1 pre-existente, no regresión) |
| Rank en query frontend | **puesto 1–21 de 300** ✓ |
| Hash duplicados | **0** ✓ |
| Colaterales publish_queue | **0** (61 pending intactos) ✓ |

**Veredicto: PILOTO APROBADO. Datos correctos, sin errores críticos.**

---

## FASE 1 — Supabase tabla `propiedades`

### Checks fundamentales

| Check | Esperado | Encontrado | Status |
|-------|----------|------------|--------|
| Conteo filas | 21 | 21 | ✓ PASS |
| Hash dedup únicos | 21/21 | 21/21 | ✓ PASS |
| Lat/lon presentes | 21/21 | 21/21 | ✓ PASS |
| Lat/lon en bbox Pinamar | 21/21 | 21/21 | ✓ PASS |
| Estado = activo | 21/21 | 21/21 | ✓ PASS |
| Moneda = USD | 21/21 | 21/21 | ✓ PASS |
| Ciudad = Pinamar | 21/21 | 21/21 | ✓ PASS |
| Imágenes (10 por propiedad) | 21 × 10 | 21 × 10 | ✓ PASS |
| updated_at = 2026-06-08 | 21/21 | 21/21 | ✓ PASS |
| Hash colisiones externas | 0 | 0 | ✓ PASS |

### Detalle de las 21 propiedades

| sb_id | tipo | precio USD | lat | lon | imgs | estado | ciudad |
|-------|------|-----------|-----|-----|------|--------|--------|
| 6725 | departamento | 257,885 | -37.1016 | -56.8440 | 10 | activo | Pinamar |
| 6730 | departamento | 230,000 | -37.0995 | -56.8478 | 10 | activo | Pinamar |
| 6733 | casa | 1,850,000 | -37.0850 | -56.8696 | 10 | activo | Pinamar |
| 6734 | casa | 460,000 | -37.0850 | -56.8696 | 10 | activo | Pinamar |
| 6735 | casa | 480,000 | -37.0873 | -56.8598 | 10 | activo | Pinamar |
| 6736 | casa | 395,000 | -37.0803 | -56.8562 | 10 | activo | Pinamar |
| 6737 | casa | 465,000 | -37.0803 | -56.8342 | 10 | activo | Pinamar |
| 6742 | casa | 560,000 | -37.0850 | -56.8696 | 10 | activo | Pinamar |
| 6744 | departamento | 105,000 | -37.1072 | -56.8755 | 10 | activo | Pinamar |
| 6745 | departamento | 223,000 | -37.0964 | -56.8740 | 10 | activo | Pinamar |
| 6746 | departamento | 230,000 | -37.0964 | -56.8740 | 10 | activo | Pinamar |
| 6747 | departamento | 192,000 | -37.0964 | -56.8740 | 10 | activo | Pinamar |
| 6748 | casa | 490,000 | -37.0803 | -56.8562 | 10 | activo | Pinamar |
| 6752 | casa | 280,000 | -37.0794 | -56.8384 | 10 | activo | Pinamar |
| 6754 | casa | 690,000 | -37.0800 | -56.8577 | 10 | activo | Pinamar |
| 6759 | departamento | 162,782 | -37.1124 | -56.8669 | 10 | activo | Pinamar |
| 6760 | departamento | 255,938 | -37.1124 | -56.8669 | 10 | activo | Pinamar |
| 6761 | departamento | 465,000 | -37.1016 | -56.8440 | 10 | activo | Pinamar |
| 6762 | departamento | 161,137 | -37.1124 | -56.8669 | 10 | activo | Pinamar |
| 6788 | departamento | 200,000 | -37.1124 | -56.8669 | 10 | activo | Pinamar |
| 6790 | departamento | 120,000 | -37.1046 | -56.8589 | 10 | activo | Pinamar |

**Bbox Pinamar:** lat ∈ [-37.20, -37.00], lon ∈ [-56.95, -56.75] — todos dentro ✓  
**inmobiliaria_id:** 4019 × 21 ✓  
**operacion:** venta × 21 ✓

### Superficie (hallazgo positivo)

La columna `superficie_total` está presente en los 21 registros:

| Rango | Detalle |
|-------|---------|
| 51 m² – 1,463 m² | Todos los 21 registros tienen superficie_total |
| superficie_cubierta | NULL × 21 (esperado — no la extrae el scraper Tokko) |

**Origen:** los 21 registros ya existían en Supabase de una scrape anterior con `superficie_total` cargada.  
El UPDATE del piloto los enriqueció con lat/lon street-level pero preservó los datos de superficie.  
En la sesión anterior se identificó `superficie_total=NULL` en `propiedades_staging` (staging no tiene ese campo capturado) — pero el UPDATE no sobreescribió el valor ya presente en Supabase. Resultado correcto.

---

## FASE 1b — View `v_propiedades_frontend_mapa`

Esta es la view que usa el frontend para mostrar propiedades.

| Check | Resultado |
|-------|-----------|
| 21 IDs exactos encontrados | **21/21** ✓ |
| Estado = activo | **21/21** ✓ |
| Bbox Pinamar | **21/21** ✓ |
| tiene_imagen_real = True | **20/21** (ver detalle) |
| imagen_principal_real presente | **20/21** |
| Total propiedades activas en view | **41,230** |

### Detalle: sb_id=6742 — tiene_imagen_real=False

- **Casa en Venta en La Herradura, Pinamar** — USD 560,000
- Tiene **10 imágenes tokkobroker CDN**, todas pasan los filtros frontend (`isValidPropertyImage`)
- `tiene_imagen_real=False` es una condición **pre-existente** del registro antes del piloto
- La columna es calculada/almacenada en Supabase — probablemente la función de detección no marcó estas fotos como "reales" en el scrape original
- **Impacto en frontend:** el badge `hasRealImage` será `false`, pero las imágenes sí se mostrarán (el array `imagenes` tiene 10 fotos válidas)
- **No es regresión del piloto** — el piloto actualizó lat/lon y datos de la propiedad, no modificó `tiene_imagen_real`

---

## FASE 2 — Validación query del frontend (simulación exacta)

El frontend ejecuta:
```javascript
supabase
  .from("v_propiedades_frontend_mapa")
  .select("*")
  .eq("estado", "activo")
  .order("updated_at", { ascending: false })
  .limit(300)
```

**Resultado de la simulación:**

| Métrica | Valor |
|---------|-------|
| Filas devueltas | 300/300 |
| Pinamar pilot en los 300 | **21/21** ✓ |
| Posición de las 21 en el ranking | **puesto 1–21 de 300** |

**Las 21 propiedades Pinamar son las PRIMERAS 21 resultados del frontend** — porque fueron actualizadas el 2026-06-08, la fecha más reciente de toda la base de 41,230 activos.

Top 10 del query frontend:
```
rank=1   id=6790  Pinamar  2026-06-08  USD   120,000 ★
rank=2   id=6788  Pinamar  2026-06-08  USD   200,000 ★
rank=3   id=6762  Pinamar  2026-06-08  USD   161,137 ★
rank=4   id=6761  Pinamar  2026-06-08  USD   465,000 ★
rank=5   id=6760  Pinamar  2026-06-08  USD   255,938 ★
rank=6   id=6759  Pinamar  2026-06-08  USD   162,782 ★
rank=7   id=6754  Pinamar  2026-06-08  USD   690,000 ★
rank=8   id=6752  Pinamar  2026-06-08  USD   280,000 ★
rank=9   id=6748  Pinamar  2026-06-08  USD   490,000 ★
rank=10  id=6747  Pinamar  2026-06-08  USD   192,000 ★
```

---

## FASE 2b — Frontend local (dev server)

| Check | Resultado |
|-------|-----------|
| Dev server arranca | ✓ (Next.js v16.2.6, puerto 3000) |
| HTTP 200 en localhost:3000 | ✓ |
| HTML renderiza sin crash | ✓ (84 KB, InmoCapital branding presente) |
| Env vars frontend | ✓ NEXT_PUBLIC_SUPABASE_URL y ANON_KEY configurados |
| `supabase-client.ts` usa anon key | ✓ (lectura pública, sin service role) |
| View `v_propiedades_frontend_mapa` accesible | ✓ (verificado vía service role) |

---

## FASE 3 — Neon (publish_queue + staging)

| Check | Resultado |
|-------|-----------|
| Queue Pinamar (21 filas): status=done | **21/21** ✓ |
| Queue Pinamar: failed | 0 ✓ |
| Staging Pinamar: status=published | **21/21** ✓ |
| Queue total | 92 (71 previas + 21 Pinamar) |
| Queue otros: pending intactos | 61 → 61, delta=0 ✓ |
| Queue otros: done (pre-existentes) | 10 → 10, delta=0 ✓ |
| Geocoding results (street) | 21/21 ✓ |

---

## Advertencias (no bloquean)

| # | Advertencia | Impacto | Acción |
|---|-------------|---------|--------|
| 1 | sb_id=6742: `tiene_imagen_real=False` | Badge `hasRealImage=false`, pero imágenes sí se muestran | Ninguna — pre-existente |
| 2 | `superficie_cubierta=NULL` × 21 | Frontend muestra 0 m² cubiertos | Ninguna — scraper Tokko no extrae ese campo |
| 3 | Títulos con doble espacio (`"en Venta   en"`) | Cosmético | Ninguna — pre-existente del scraper |
| 4 | Imágenes en CDN tokkobroker | URLs externas; podrían expirar | A monitorear |
| 5 | 4 staging_ids sin geocoding (81389/81391/81393/81407) | No publicados — requieren fix manual | Requiere autorización |

---

## Estado global del pipeline

### propiedades_staging (Neon)
- 21 Pinamar: **status=published** ✓
- 61 pending: sin cambio ✓
- 4 sin geocoding (Pinamar): **pendientes** (bloque/letra)

### publish_queue (Neon)
- 21 Pinamar: **done** ✓
- 61 otros: **pending** (sin cambio, esperan autorización)

### Supabase propiedades
- 21 Pinamar: **activo**, lat/lon street-level, 10 imgs, USD ✓
- Total activos view: 41,230

---

## ¿Conviene publicar otro lote?

El piloto Pinamar (21 props) es un éxito técnico completo. No hay regresiones ni efectos colaterales.

### Los 61 pending restantes en publish_queue:

| Lote | Count | staging_ids | priority | queued_at |
|------|-------|-------------|----------|-----------|
| Batch mayo priority=1 | 10 | ~21–40 | 1 | 2026-05-29 |
| Batch junio-7 priority=1 | 12 | ~81276–81327 | 1 | 2026-06-07 |
| Batch mayo priority=2 | 39 | varios | 2 | 2026-05-29 |

**Prerequisitos antes de publicar esos lotes:**
1. Verificar que tienen geocoding_status=done (o skipped con coords válidas)
2. Verificar que no hay direcciones con ruido de marketing (como fix pre-Pinamar)
3. Si se usan staging_ids del batch mayo, confirmar que los datos son recientes y no stale
4. Autorización explícita con ids-file, como el piloto Pinamar

**Recomendación:** publicar lote junio-7 (12 props, staging_ids ~81276–81327) como segundo lote controlado. Son recientes, misma metodología. Requiere:
- Revisar si tienen geocoding_status=done
- Preflight
- Dry-run con `--staging-ids-file`
- Autorización

---

## Verificaciones de seguridad final

| Check | Resultado |
|-------|-----------|
| Otros pending publish_queue | 61 → 61, delta=0 ✓ |
| Supabase IDs fuera del piloto modificados | 0 ✓ |
| .env / .env.local | NO modificados ✓ |
| frontend/ | NO modificada ✓ |
| schema Neon / Supabase | NO modificado ✓ |
| git push | NO ejecutado ✓ |
| geocoding nuevo | NO ejecutado ✓ |

---

## FRENADO

No se escala publicación. No se publica más lotes. No se toca frontend.  
**Esperando nueva autorización.**
