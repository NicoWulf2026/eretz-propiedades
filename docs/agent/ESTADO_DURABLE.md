# Estado operativo durable fuera del repo (checkpoint 2026-09-29)

**El repositorio es PÚBLICO.** Estos datos (inventario scrapeado de inmobiliarias, ledger de
certificación, base de preingestión) no se suben al repo ni a un release público: publicarlos no
está autorizado. Están empaquetados y verificados en la máquina original, listos para que el
usuario los suba a almacenamiento PRIVADO. Hasta entonces: `EXTERNAL_STORAGE_REQUIRED`.

## El paquete
- Carpeta: `D:\INMO CAPITAL\ERETZ_STATE_CHECKPOINT_2026-09-29\`
- `ERETZ_STATE_2026-09-29.tar.gz` — 510,244,182 bytes, SHA-256 `a63b35e966c83ed9eb86318244edd08b9a3b3d133d13191c3321bf956f88675c`
- `MANIFEST.json` — SHA-256 de cada uno de los 6,533 archivos (3.34 GB sin comprimir)
- `ERETZ_CLOUD_CHECKPOINT_2026-09-29.bundle` — git bundle de la rama y el tag del checkpoint
  (6.492.768 bytes, SHA-256 `e0bea10032412502ffac45ef7ff7b64499fd5cf93bff2a39975114332bd27b92`,
  `git bundle verify` OK). Es respaldo: la fuente normal es GitHub (tag `cloud-checkpoint-2026-09-29`).
- `ERETZ_DATA_MANIFEST.json` — qué base de preingestión es la vigente (lo lee `scripts/preingestion_manifest.py`)
- Tomado a las 2026-09-29T17:12:35 con la cola corriendo: el ledger es append-only, así que es un corte válido
  en el tiempo; lo certificado después se recupera recertificando.

## Restaurar
```bash
# en la maquina nueva, crear la raiz que los scripts esperan (o pasar rutas por argumento)
mkdir -p "/d/INMO CAPITAL" && cd "/d/INMO CAPITAL"
sha256sum ERETZ_STATE_2026-09-29.tar.gz     # debe dar a63b35e966c83ed9eb86318244edd08b9a3b3d133d13191c3321bf956f88675c
tar -xzf ERETZ_STATE_2026-09-29.tar.gz
cp ERETZ_DATA_MANIFEST.json "/d/INMO CAPITAL/"
python - <<'PY'
import json, hashlib
m = json.load(open("MANIFEST.json", encoding="utf-8"))
malos = [a["ruta"] for a in m["archivos"]
         if hashlib.sha256(open(a["ruta"], "rb").read()).hexdigest() != a["sha256"]]
print("archivos con hash distinto:", len(malos))
PY
```

## Qué hay adentro
| componente | archivos | tamaño |
|---|---:|---:|
| `ERETZ_AGENCY_CERTIFICATION_20260827` | 6 | 37.9 MB |
| `ERETZ_AGENCY_CERTIFICATION_20260827/_regresion` | 14 | 148.3 MB |
| `ERETZ_AGENCY_CERTIFICATION_20260827/agencies` | 6,348 | 679.9 MB |
| `ERETZ_AGENCY_DATA` | 119 | 157.8 MB |
| `ERETZ_GEO` | 21 | 111.2 MB |
| `ERETZ_PREINGESTION_REBUILD_20260903` | 22 | 2,200.1 MB |
| `ERETZ_SUPABASE_RECONCILIATION_V2_20260827` | 2 | 3.8 MB |
| `agency_platform_directory.jsonl` | 1 | 1.8 MB |

Archivos clave:

| archivo | bytes | SHA-256 |
|---|---:|---|
| `ERETZ_AGENCY_CERTIFICATION_20260827/AGENCY_CERTIFICATION_RESULTS.jsonl` | 35,492,868 | `86715d3ff79439ee82d887aaa8dc4e64595caaad382d23ddf0b953317ab75862` |
| `ERETZ_AGENCY_CERTIFICATION_20260827/AGENCY_DEFECTS_DIFERIDOS.jsonl` | 430,750 | `477a4e21e033a7b71c7521ae9d7faefc5b566ae363cbbbdd266016525806bfe1` |
| `ERETZ_AGENCY_CERTIFICATION_20260827/ERETZ_WORKERS.json` | 717 | `1ab96688c781e2944190f1c918ddf48cdc52e65fee5c6d51a339b002b54132f9` |
| `ERETZ_AGENCY_CERTIFICATION_20260827/_regresion/ANTES_DEL_LOTE_2026-09-24.jsonl` | 129,059,449 | `3f798a8adcf956baa9309f56f9282afe226889ce515acfd15198cc054bc88d1b` |
| `ERETZ_AGENCY_CERTIFICATION_20260827/_regresion/REVISADAS.jsonl` | 1,056,112 | `78e4cc6a723a0f2f0cc9f407f364fd0ddba370a589daa6fa90408b452eca12b9` |
| `ERETZ_AGENCY_DATA/AGENCY_OFFICIAL_WEB_VERIFIED.jsonl` | 1,259,157 | `dc17dfcae1c4dfed2c2dbb3d007c7e3ed4f721df56fb437594c8ac42d34338dc` |
| `ERETZ_PREINGESTION_REBUILD_20260903/PREINGESTION_REBUILD.sqlite3` | 1,149,599,744 | `6abe497c8fe08bde626ada5a8dee6e246c7d40e8885007b94fc0c3e0b0652470` |
| `ERETZ_SUPABASE_RECONCILIATION_V2_20260827/AGENCY_ID_RESOLUTION_FINAL.jsonl` | 3,430,106 | `eb02d4325669b92e9fcfb8e12fdb6d2b2c0ebfc6444253410f8937de3efce9c0` |
| `agency_platform_directory.jsonl` | 1,752,658 | `85236d4d5d19a0d6add959b3f6552dd1a14f3ff9a040c72c2555dde01e688915` |

## Qué es cada cosa y si se regenera
| componente | para qué | ¿regenerable? |
|---|---|---|
| `AGENCY_CERTIFICATION_RESULTS.jsonl` (ledger) | resultado vigente por agencia (NEXT-001) | **no** (recertificar todo: ~230 h) |
| `agencies/` (paquetes) | inventario certificado, fuente de la snapshot | solo recertificando (y el sitio cambia) |
| `AGENCY_DEFECTS_DIFERIDOS.jsonl`, `AGENCY_DEFECT_QUEUE.jsonl`, `ERETZ_FAMILIAS_DETENIDAS.jsonl` | paros y diferidas firmadas | **no** |
| `ERETZ_WORKERS*.json(l)` | régimen de workers y su historia (P5) | trivial (por defecto 2) |
| `_regresion/` | línea base y revisiones del Regression Gate | **no** (la línea base es del 24-09) |
| `ERETZ_AGENCY_DATA/` | webs verificadas (P6), tecnología, directorio | parcial (verificar_webs_* re-abre webs) |
| `agency_platform_directory.jsonl` | directorio de plataformas | parcial |
| `ERETZ_SUPABASE_RECONCILIATION_V2_*` (2 archivos) | resolución de identidad (FK de main) | desde Supabase con credencial (P17) |
| `ERETZ_PREINGESTION_REBUILD_20260903/` | base canónica congelada del 03-09 | desde los insumos legacy (`scripts/preingestion_rebuild.py`), no incluidos |
| `ERETZ_GEO/` | GeoRef/IGN, cobertura geo | sí (`scripts/geo_snapshot.py`, `geo_coverage_audit.py`) |

No incluidos, porque se regeneran desde lo anterior + el repo:
- snapshots de la API (`api_snapshot.py`); la servida v4l-c tiene SHA-256 `482de3ac0081…`;
- `_scratch/`, logs, cerrojos y PID.

Nunca incluidos: `.env` ni credenciales.
