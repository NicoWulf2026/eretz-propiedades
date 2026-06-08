# publish_to_supabase.py — Commit Pinamar 21 IDs

**Fecha:** 2026-06-08  
**Modo:** commit (2 pasadas: max_writes=10 + max_writes=15)  
**ids-file:** `publish_queue_ids_pinamar_21_done.csv`  
**Resultado:** 21/21 procesadas, 0 fallos

---

## Resultado del commit

| Pasada | filas_leidas | publicadas_ok | failed | writes |
|--------|-------------|---------------|--------|--------|
| 1 | 10 | 10 | 0 | 10 |
| 2 | 11 | 11 | 0 | 11 |
| **Total** | **21** | **21** | **0** | **21** |

---

## Hallazgo: UPDATEs, no INSERTs

El log mostró `Deduplicacion existente: url_normalizada=1` para cada una de las 21 propiedades.

**Diagnóstico:** estas propiedades ya existían en Supabase de una scrape run previa.  
El script las encontró por `url_normalizada` y las **actualizó** con datos frescos, en particular:
- lat/lon (geocoding street-level nuevo) ✓
- precio, moneda, imágenes, descripción actualizados ✓
- `Proteccion update: 1 campos conservados` → preservó el hash_dedup original

La query pre-commit por `hash_dedup` devolvió 0 resultados porque los registros existentes tenían un hash diferente (de la scrape anterior). Esto no fue un error de seguridad — el resultado es correcto.

---

## Estado post-commit

### publish_queue (21 Pinamar)

| Resultado | Count |
|-----------|-------|
| status=done | **21** |
| status=failed | 0 |
| status=pending | 0 |

### Otros pending (no Pinamar): **61** — sin cambio (era 61, delta=0 ✓)

### propiedades_staging (21 Pinamar): status=**published** ✓

---

## Supabase — 21 registros verificados por url_normalizada

| sb_id | staging_id | precio USD | lat | lon | imgs | inmo |
|-------|-----------|-----------|-----|-----|------|------|
| 6736 | 81402 | 395,000 | -37.0803 | -56.8562 | 10 | 4019 |
| 6742 | 81408 | 560,000 | -37.0850 | -56.8696 | 10 | 4019 |
| 6744 | 81410 | 105,000 | -37.1072 | -56.8755 | 10 | 4019 |
| 6733 | 81399 | 1,850,000 | -37.0850 | -56.8696 | 10 | 4019 |
| 6745 | 81411 | 223,000 | -37.0964 | -56.8740 | 10 | 4019 |
| 6734 | 81400 | 460,000 | -37.0850 | -56.8696 | 10 | 4019 |
| 6725 | 81392 | 257,885 | -37.1016 | -56.8440 | 10 | 4019 |
| 6735 | 81401 | 480,000 | -37.0873 | -56.8598 | 10 | 4019 |
| 6737 | 81403 | 465,000 | -37.0803 | -56.8342 | 10 | 4019 |
| 6730 | 81396 | 230,000 | -37.0995 | -56.8478 | 10 | 4019 |
| 6761 | 81423 | 465,000 | -37.1016 | -56.8440 | 10 | 4019 |
| 6754 | 81420 | 690,000 | -37.0800 | -56.8577 | 10 | 4019 |
| 6790 | 81445 | 120,000 | -37.1046 | -56.8590 | 10 | 4019 |
| 6788 | 81443 | 200,000 | -37.1124 | -56.8669 | 10 | 4019 |
| 6746 | 81412 | 230,000 | -37.0964 | -56.8740 | 10 | 4019 |
| 6747 | 81413 | 192,000 | -37.0964 | -56.8740 | 10 | 4019 |
| 6748 | 81414 | 490,000 | -37.0803 | -56.8562 | 10 | 4019 |
| 6752 | 81418 | 280,000 | -37.0793 | -56.8384 | 10 | 4019 |
| 6762 | 81424 | 161,137 | -37.1124 | -56.8669 | 10 | 4019 |
| 6760 | 81422 | 255,938 | -37.1124 | -56.8669 | 10 | 4019 |
| 6759 | 81421 | 162,782 | -37.1124 | -56.8669 | 10 | 4019 |

**Todas con:** lat/lon ✓ | precio USD ✓ | 10 imágenes ✓ | inmobiliaria_id=4019 ✓  
**Bbox Pinamar:** lat ∈ [-37.12, -37.07], lon ∈ [-56.88, -56.83] — todos dentro ✓

---

## Verificaciones de seguridad

| Check | Resultado |
|-------|-----------|
| Otros pending publish_queue | 61 → 61, delta=0 ✓ |
| staging_id fuera del ids-file encolados | ninguno ✓ |
| Supabase IDs fuera del lote | 0 ✓ |
| frontend | NO tocada ✓ |
| .env | sin cambio (modificado hace ~11 días) ✓ |
| git push | NO ejecutado ✓ |
| schema changes | NO ✓ |
| geocoding nuevo | NO ✓ |

---

## Campos faltantes

| Campo | Estado |
|-------|--------|
| `superficie_total` | NULL × 21 — registrado, no bloquea |
| `superficie_cubierta` | NULL × 21 — ídem |

---

## Próximo paso recomendado

El piloto Pinamar está completo. Los 21 registros de `marcelgestion.com.ar` (inmo_id=4019)
están en Supabase con coordenadas street-level, precio USD y 10 imágenes c/u.

Para escalar a los otros 61 pending de publish_queue (batch mayo/junio-7),
se requiere nueva autorización. Esos lotes tienen:
- 10 priority=1 de mayo (staging_ids 21–40)
- 12 priority=1 de junio-7 (staging_ids 81276–81327)
- 39 priority=2 de mayo

**FRENADO. No se escala sin nueva autorización.**
