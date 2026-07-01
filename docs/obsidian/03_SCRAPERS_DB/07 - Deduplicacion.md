# Deduplicacion de propiedades

Ultima actualizacion: 2026-06-09

---

## Politica oficial

Si una misma propiedad aparece publicada en varias inmobiliarias, se conservan como publicaciones separadas.

No se fusionan automaticamente en una unica publicacion.

---

## Clasificacion de duplicados

| Tipo | Descripcion | Accion |
|------|-------------|--------|
| Duplicado exacto | Misma URL, mismo hash, misma publicacion repetida por el mismo origen | Bloquear import. No duplicar en raw ni staging. |
| Misma propiedad por varias inmobiliarias | La misma propiedad aparece publicada en 2 o mas inmobiliarias distintas | Conservar ambas publicaciones. No bloquear. Marcar como posible duplicado cross-agency. |
| Posible duplicado dudoso | Misma direccion aproximada, mismo precio, distinto origen | Conservar. Marcar para revision futura. |

---

## Comportamiento en el pipeline

- El import bloquea duplicados exactos (misma URL + misma inmobiliaria).
- No bloquea publicaciones de la misma propiedad por distintas inmobiliarias.
- Se registra el flag `possible_cross_agency_duplicate` como informacion, no como rechazo.

---

## Comportamiento futuro en frontend

A futuro puede mostrarse en el detalle de una propiedad:
"Tambien publicada por: [otras inmobiliarias]"

Esto requiere:
- Algoritmo de matching por coordenadas + tipo + operacion + superficie.
- Umbral de similitud configurable.
- No fusion automatica, solo indicacion.

Por ahora: no implementar. Conservar publicaciones separadas.

---

---

## Dedup en el pipeline run_manifest (2026-06-28)

### Mecanismo actual

1. Al inicio de run_execute, `supabase.get_all_existing_urls()` carga un Set[str] de URLs existentes.
2. En _scrape_batch, antes de visitar fichas: `nuevas_urls = [u for u in all_prop_urls if u not in existing_urls]`.
3. Antes de guardar: doble-check bajo lock para consistencia entre workers.
4. Después de guardar: `existing_urls.update(p.url for p in nuevas_final)`.

### Limitación actual — PostgREST 1.000 rows

`get_all_existing_urls()` pasa `limit=100_000`, pero PostgREST en Supabase retorna máximo **1.000 filas** por request (límite de servidor, no del código).

Con 115.559 propiedades (2026-06-28), solo 0.9% de las URLs están en el set de dedup.

**Consecuencia:** si se re-corre una fuente ya procesada, las propiedades existentes de esa fuente no se detectan como duplicados y se vuelven a insertar.

**No afectó 09d** porque:
- Las 50 fuentes no habían sido corridas antes por este pipeline.
- No hubo re-ejecuciones de las mismas fuentes.

**Afecta 09e** porque el manifest de 891 incluye las 50 fuentes de 09d (1.039 propiedades ya en DB). Sin fix, al re-correrlas se insertarían ~1.039 duplicados.

### Fix propuesto — per-source dedup (sin schema change)

En `run_execute()` de `scripts/run_manifest.py`, después del FK preflight y antes de lanzar workers:

```python
# Cargar existing_urls por inmobiliaria_id — no el total global
def _load_existing_urls_by_inmobiliaria(supabase_url, key, inmobiliaria_ids):
    existing = set()
    H = {"apikey": key, "Authorization": f"Bearer {key}"}
    for inmo_id in inmobiliaria_ids:
        r = requests.get(
            f"{supabase_url}/rest/v1/propiedades",
            headers=H,
            params={"select": "url", "inmobiliaria_id": f"eq.{inmo_id}", "limit": "10000"},
            timeout=30,
        )
        if r.status_code == 200:
            existing.update(item["url"] for item in r.json() if "url" in item)
    return existing

# Reemplaza get_all_existing_urls() en run_execute:
inmobiliaria_ids = [f["inmobiliaria_id"] for f in fuentes_con_fk]
existing_urls = _load_existing_urls_by_inmobiliaria(cfg.SUPABASE_URL, cfg.SUPABASE_SERVICE_ROLE_KEY, inmobiliaria_ids)
```

**Por qué funciona:**
- Cada fuente tiene como máximo unos pocos cientos de propiedades → bien dentro del límite PostgREST.
- Para un lote de 891 fuentes con ~640 FK, son ~640 queries → ~64 segundos a 100ms c/u.
- Sin ALTER TABLE. Sin unique constraint. Sin schema change.
- Detecta correctamente las 1.039 propiedades de 09d como duplicados.

### Fix implementado (2026-06-28, PR-BE-PROD-09e-DEDUP-FIX)

```python
# scripts/run_manifest.py — reemplaza get_all_existing_urls() en run_execute()
inmobiliaria_ids_fk = [f["inmobiliaria_id"] for f in fuentes_con_fk]
existing_urls = _load_existing_urls_by_inmobiliaria(
    cfg.SUPABASE_URL, cfg.SUPABASE_SERVICE_ROLE_KEY, inmobiliaria_ids_fk
)
```

`_load_existing_urls_by_inmobiliaria()` hace un GET por cada `inmobiliaria_id` del batch (con `limit=10000`). Para ~640 fuentes con FK → ~640 queries → ~64 segundos de overhead. Sin schema change.

MAX_EXECUTE_LIMIT subido a **892**. 9 tests nuevos. 64/64 tests verdes.

### Estado

RESUELTO. Funcionó correctamente en PR-BE-PROD-09e (ejecutado 2026-06-28 a 2026-07-01).

### Comportamiento verificado en 09e

- 4 intentos acumulados. El dedup por inmobiliaria_id protegió correctamente los re-runs.
- En rerun_01: no duplicó los +3.082 del intento 1.
- En rerun_02: no duplicó los +3.923 acumulados (intento 1 + rerun_01).
- En rerun_03: no duplicó los +15.533 acumulados previos.
- Total duplicados evitados: ~decenas de miles de inserciones redundantes.
- 3 errores 409 hash_dedup (secondary safety net): cittadini_inmobiliaria, stiefel_propiedades, santa_fe_propiedades — urls que existían bajo otro inmobiliaria_id. Manejados correctamente, run continuó.
- Dedup FIABLE para próximas corridas con el mismo manifest.

---

## Notas relacionadas

- [[00 - Decisiones oficiales]]
- [[08 - Estados de propiedades]]
