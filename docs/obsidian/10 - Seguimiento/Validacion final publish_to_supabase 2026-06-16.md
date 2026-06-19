# Validación final `publish_to_supabase` end-to-end (2026-06-16)

Prueba real muy chica del último tramo del ciclo:
`internal_scraping.publish_queue → publish_to_supabase.py → public.propiedades`.
**Máximo 10 propiedades.** Primera prueba que sí modifica `public.propiedades`.

Ver también: [[Validacion controlada internal_scraping 2026-06-16]] ·
[[Optimizacion build_publish_queue 2026-06-16]] ·
[[Migracion Neon a Supabase internal_scraping 2026-06-16]]

Variables: `USE_INTERNAL_DB=true`, `INTERNAL_DB_URL=<supabase>`,
`INTERNAL_DB_SCHEMA=internal_scraping`.

---

## 1. Filas encoladas
`build_publish_queue --limit 10` → dry-run y commit ambos `encoladas=10`,
`omitidas=0`, `failed=0`. 10 propiedades de cominmobiliaria.com (Santa Fe).

## 2. Filas publicadas
`publish_to_supabase --limit 10 --max-supabase-writes 10`:
- **Dry-run:** `filas_queue_leidas=10`, `props_validas=10`, `failed=0`,
  `omitidas=0`, rollback. Sin errores de schema/payload.
- **Commit:** `publicadas_ok=10`, `writes_supabase_usados=10`.

## 3. Failed final
**0.**

## 4. Omitidas final
**0.**

## 5. `public.propiedades` antes/después
| | Valor |
|---|---|
| Antes | 94,834 |
| Después | **94,834** |
| Δ | **0** |

Sin cambio de count porque **las 10 ya existían** (10 UPDATE, 0 INSERT).
Pre-chequeo: los 10 `hash_dedup` ya estaban en `public.propiedades`.
Post: las 10 con `updated_at` refrescado (16:55–16:56 UTC), `estado=activa`,
10/10 actualizadas en los últimos 10 min.

## 6. `internal_scraping.publish_queue` antes/después
| Status | Antes | Después |
|---|---:|---:|
| done | 11,687 | **11,697** (+10) |
| pending | 10 (de la prep) | **0** |

Las 10 `pending` pasaron a `done`.

## 7. `internal_scraping.propiedades_staging` antes/después
| Status | Antes | Después |
|---|---:|---:|
| published | 11,687 | **11,697** (+10) |
| queued | 10 (de la prep) | **0** |
| staging | 68,357 | 68,357 |

Las 10 `queued` pasaron a `published`.

## 8. Inserts vs updates
**10 updates, 0 inserts.** Las propiedades ya existían (dedup por
`url_normalizada`). Los logs confirman `Deduplicacion existente:
url_normalizada=1` por cada una → merge/update, no alta nueva.

## 9. Tiempo total
- build_queue dry-run + commit: ~1s cada uno.
- publish dry-run: ~21s.
- publish commit: **97.9s** para 10 props (~10s/prop), dominado por el
  rate-limit intencional (`--sleep`) + latencia + lookups de dedup.
- Hubo **1 WARNING transitorio** (`get_existing_properties_for_dedup` read
  timeout ~40s) del que el script **se recuperó**, completando 10/10 sin fallar.

## 10. ¿Listo para cutover definitivo?

**Sí, el ciclo end-to-end está validado.** Todos los tramos funcionan contra
`internal_scraping`:
`create-run → scraper → validate-raw → geocode → build-queue → publish`.
La escritura final a `public.propiedades` es consistente (updates correctos,
estados de cola/staging propagados).

**Consideraciones para el cutover real:**
- **Performance de publicación:** ~10s/prop por diseño (rate-limit). Publicar
  miles de props llevará horas; dimensionar `--limit`/`--max-supabase-writes`/
  `--sleep` y correr por tandas.
- **Timeouts transitorios:** la latencia Argentina→Supabase puede provocar read
  timeouts en lookups de dedup; el script los tolera, pero conviene monitorear.
- Las 3 herramientas manuales (`import_captured_props_to_neon`,
  `generate_scraping_run_audit_reports`, `validate_pinamar_pilot`) siguen sin
  parametrizar — fuera del ciclo diario.

**Esta prueba dejó 10 propiedades reales actualizadas en producción** (no se
revierten: son datos legítimos del pipeline). Estado de `internal_scraping`
consistente, sin residuos espurios.
