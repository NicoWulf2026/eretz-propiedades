# publish_to_supabase.py — Dry-run análisis Pinamar 21 IDs

**Fecha:** 2026-06-08  
**Modo:** simulación manual (el script no fue ejecutado — ver BLOQUEO)  
**Supabase:** NO tocada  

---

## BLOQUEO: script no soporta --ids-file

`publish_to_supabase.py` no tiene flag `--staging-ids-file` ni `--queue-ids-file`.
Su query ordena `WHERE status='pending' ORDER BY priority ASC, queued_at ASC LIMIT N`.

Estado real de la queue al momento del análisis:

| Grupo | Filas pending priority=1 | queued_at |
|-------|--------------------------|-----------|
| Batch mayo 2026 (staging_ids 21-40) | 10 | 2026-05-29 |
| Batch junio-7 (staging_ids 81276-81327) | 12 | 2026-06-07 |
| **Pinamar (staging_ids 81392-81445)** | **21** | **2026-06-08** |
| Priority=2 pending | 39 | 2026-05-29 |

Con `--limit 21` el script procesaría las 10+12=22 filas anteriores, **no las nuestras**.  
Con `--limit 43` las procesaría todas las priority=1, mezclando Pinamar con las otras 22.

**Conclusión: NO se ejecutó el script. Se requiere agregar `--staging-ids-file`.**

---

## Simulación del dry-run (contra DB, sin ejecutar script)

### Resultado: 21/21 pasarían validación — 0 skips

Validaciones aplicadas (replicando `validation_skip_reason` del script):

| Check | Resultado |
|-------|-----------|
| staging.status == 'queued' | OK × 21 |
| hash_dedup presente | OK × 21 |
| inmobiliaria_id válido (4019) | OK × 21 |
| url presente | OK × 21 |
| titulo presente | OK × 21 |
| operacion in {venta, alquiler, alquiler_temporario} | OK × 21 (venta × 21) |
| geocoding_status in {done, skipped} | OK × 21 (done × 21) |
| validation_score >= 60 | OK × 21 (score=100 × 21) |
| latitud/longitud not null | OK × 21 |
| n_imagenes > 0 | OK × 21 (10 imgs × 21) |
| precio not null | OK × 21 |
| Riesgo duplicados (hash en staging published) | 0 colisiones |

### Queue IDs y staging IDs

| queue_id | staging_id | tipo | precio USD | lat | lon |
|---------|-----------|------|-----------|-----|-----|
| 276 | 81392 | departamento | 257,885 | -37.101627 | -56.843988 |
| 277 | 81396 | departamento | 230,000 | -37.099468 | -56.847798 |
| 278 | 81399 | casa | 1,850,000 | -37.085014 | -56.869588 |
| 279 | 81400 | casa | 460,000 | -37.085014 | -56.869588 |
| 280 | 81401 | casa | 480,000 | -37.087312 | -56.859764 |
| 281 | 81402 | casa | 395,000 | -37.080347 | -56.856169 |
| 282 | 81403 | casa | 465,000 | -37.080266 | -56.834225 |
| 283 | 81408 | casa | 560,000 | -37.085014 | -56.869588 |
| 284 | 81410 | departamento | 105,000 | -37.107164 | -56.875492 |
| 285 | 81411 | departamento | 223,000 | -37.096368 | -56.874023 |
| 286 | 81412 | departamento | 230,000 | -37.096368 | -56.874023 |
| 287 | 81413 | departamento | 192,000 | -37.096368 | -56.874023 |
| 288 | 81414 | casa | 490,000 | -37.080347 | -56.856169 |
| 289 | 81418 | casa | 280,000 | -37.079393 | -56.838352 |
| 290 | 81420 | casa | 690,000 | -37.080042 | -56.857663 |
| 291 | 81421 | departamento | 162,782 | -37.112379 | -56.866943 |
| 292 | 81422 | departamento | 255,938 | -37.112379 | -56.866943 |
| 293 | 81423 | departamento | 465,000 | -37.101627 | -56.843988 |
| 294 | 81424 | departamento | 161,137 | -37.112379 | -56.866943 |
| 295 | 81443 | departamento | 200,000 | -37.112379 | -56.866943 |
| 296 | 81445 | departamento | 120,000 | -37.104608 | -56.858935 |

### Payload esperado (campos que llegarían a Supabase)

Campos mapeados por `staging_to_prop()`:

```
inmobiliaria_id   = 4019
hash_dedup        = <md5 único por propiedad>
titulo            = "Departamento en Venta   en Norte Playa, Pinamar..."
descripcion       = <texto del scraper>
precio            = <float>
moneda            = "USD"
tipo_propiedad    = "departamento" | "casa"
operacion         = "venta"
superficie_total  = None  ← CAMPO VACÍO (ver flags)
superficie_cubierta = None  ← CAMPO VACÍO (ver flags)
direccion         = "De la Cincha 401" | "Martín Pescador 1485 PB 103" | etc.
barrio            = "La Herradura" | "Norte Playa" | "Golf Nuevo" | etc.
ciudad            = "Pinamar"
provincia         = "Buenos Aires"
pais              = "Argentina"
latitud           = <float, precision street>
longitud          = <float, precision street>
imagenes          = [<10 URLs tokkobroker CDN>]
url               = "https://www.marcelgestion.com.ar/p/..."
url_normalizada   = "https://www.marcelgestion.com.ar/p/..."
```

---

## Flags / advertencias

### superficie_total y superficie_cubierta: None × 21
El scraper no capturó superficie para ninguna de las 21 propiedades.
No bloquea la publicación (el script no valida este campo), pero los registros
quedarían en Supabase sin superficie.

### titulo con espacios extra
`"Departamento en Venta   en Norte Playa, Pinamar..."` — doble/triple espacio.
Cosmético. No bloquea.

### Imágenes: CDN tokkobroker
URLs del tipo `https://static.tokkobroker.com/pictures/...`.
Son URLs externas. Si tokkobroker expira las URLs, las fotos desaparecerían.
No bloquea pero vale la pena tenerlo en cuenta.

### Riesgo duplicados en Supabase: DESCONOCIDO
La simulación comprobó que no hay `hash_dedup` colisionando con **staging rows published**.
No hay forma de verificar colisiones contra Supabase directamente sin conectarse.
`save_propiedades` hace upsert por `hash_dedup` (si aplica) — verificar comportamiento
exacto del método antes del commit real.

---

## Propuesta de cambio mínimo: agregar --staging-ids-file

Para habilitar dry-run y commit controlado sobre IDs exactos, agregar a
`scripts/publish_to_supabase.py`:

```python
# En argparse (línea ~318):
parser.add_argument(
    "--staging-ids-file", type=str, default=None,
    help="CSV con columna 'staging_id' — evalua SOLO esos IDs de la queue."
)

# En main(), tras args = parser.parse_args(), cargar los IDs:
staging_ids_filter: Optional[List[int]] = None
if args.staging_ids_file:
    import csv as _csv
    with open(args.staging_ids_file, newline="", encoding="utf-8") as f:
        staging_ids_filter = [int(row["staging_id"]) for row in _csv.DictReader(f)]

# Modificar QUEUE_SELECT_DRY_RUN_SQL y QUEUE_CLAIM_SQL para aceptar filtro:
# Reemplazar fetch_queue_rows() para inyectar AND staging_id = ANY(%s)
# cuando staging_ids_filter no es None.
```

El cambio es ~15 líneas. No altera el comportamiento existente (sin flag = comportamiento actual).

**Requiere autorización para aplicar el cambio.**

---

## Veredicto: ¿es seguro hacer publicación real?

**Sí, con la siguiente condición:**

Una vez aplicado `--staging-ids-file`, la publicación real de los 21 IDs es segura:
- 21/21 pasan todas las validaciones del script
- 0 duplicados conocidos en staging
- Coordenadas street-level dentro de Pinamar
- Precio USD, 10 imágenes, score=100
- Única duda: comportamiento de `save_propiedades` ante upsert (confirmar antes)

**Frenado. No se publicó Supabase. Esperando confirmación para aplicar el cambio.**
