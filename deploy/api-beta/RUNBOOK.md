# API v2 beta remota (P21) — runbook

Estado: **PREPARADO, NO DESPLEGADO**. `EXTERNAL_ACCOUNT_REQUIRED`: la cuenta y el medio de
pago del hosting los crea el usuario. Nada de este runbook se ejecuta automáticamente
(deploy público = acción productiva, `CLAUDE.md` § Barreras).

Objetivo de P21: la arquitectura actual (FastAPI + snapshot SQLite en volumen persistente)
alojada por ≤ USD 10/mes, accesible para la beta cerrada (P16 #6).

## Qué hay

| archivo | qué es |
|---|---|
| `Dockerfile` | imagen `python:3.14-slim`, usuario sin privilegios, solo `api/` + `scripts/rutas_de_datos.py`; sin datos |
| `requirements.runtime.lock` | dependencias de runtime con hashes, mismas versiones que `requirements.lock` |
| `activar_snapshot.py` | activa / revierte / informa la snapshot del volumen (atómico, verificado) |
| `fly.toml` | configuración para Fly.io (1 máquina `shared-cpu-1x` 256 MB, volumen en `/data`, chequeo `/readyz`) |
| `/.dockerignore` (raíz) | el contexto de build solo incluye lo que la imagen copia |

La imagen es la misma para cualquier proveedor que corra un contenedor con volumen
(Railway, Render, una VM): `fly.toml` es la única pieza específica de Fly.

## Verificado en CLOUD (29-09, sin cuenta)

- `docker build -f deploy/api-beta/Dockerfile .` → imagen de 206 MB.
- Contenedor con volumen vacío: `/healthz` 200, `/readyz` 503 «snapshot ausente».
- `activar_snapshot.py`: sha256 incorrecto → RECHAZADA sin tocar nada; activación →
  `/readyz` 200 y `/v2/buscar` responde; segunda activación + `rollback` → vuelve a la
  anterior, verificada por el enlace. Ensayo hecho con la snapshot SINTÉTICA
  (`--permitir-sintetica` + `ERETZ_ALLOW_SYNTHETIC_SNAPSHOT=1`, solo para ensayar).
- Tests: `tests/test_activar_snapshot_beta.py`, `tests/test_snapshot_sintetica.py`.

## Costos: a verificar al crear la cuenta (no verificados desde CLOUD)

No hay acceso a la tarifa vigente desde este entorno. Antes de crear nada, confirmar en la
página de precios del proveedor el costo mensual de: 1 máquina `shared-cpu-1x` 256 MB (con
auto-stop, se cobra el tiempo encendida), el volumen del tamaño medido abajo, y la
transferencia saliente esperada de la beta. Si la suma supera USD 10/mes → no crear;
volver a esta decisión (P21).

## Tamaño del volumen — REQUIRES_LOCAL_OPERATIONAL_STATE

La snapshot servida está en la PC LOCAL. Medir allí:

    python -c "import os;p=r'D:\INMO CAPITAL\ERETZ_API_CONTRACT\ERETZ_API_SNAPSHOT.sqlite3';print(os.path.getsize(p))"

Volumen = 3 × ese tamaño (activa + anterior + la que se sube) redondeado hacia arriba al GB.

## Primer despliegue (lo hace el usuario, o una sesión con autorización explícita)

1. Crear cuenta y medio de pago; instalar `flyctl`; `fly auth login`.
2. Confirmar región: `fly platform regions`; ajustar `primary_region` en `fly.toml`.
3. Completar `ERETZ_CORS_ORIGINS` en `fly.toml` con el dominio del Preview (P22/P23).
4. Crear app y volumen (desde la raíz del repo):

       fly apps create eretz-api-beta
       fly volumes create eretz_snapshot --app eretz-api-beta --region <region> --size <GB>
       fly deploy --config deploy/api-beta/fly.toml --dockerfile deploy/api-beta/Dockerfile --app eretz-api-beta

   El Dockerfile va explícito por `--dockerfile` (el contexto de build es la raíz del repo).
   Sin snapshot la máquina queda viva pero no lista (`/readyz` 503): es lo esperado.
5. Subir y activar la snapshot (siguiente sección).
6. Verificar: `curl https://<app>.fly.dev/readyz` → 200 con `"sintetica": false` y el número
   de propiedades de la servida; `python scripts/benchmark_unified_api.py` se puede
   apuntar a una copia local de la misma snapshot para la línea base de latencia.
7. Conectar el Preview (P16 #7): `ERETZ_API_V2_BASE_URL=https://<app>.fly.dev` en las
   variables de Preview de Vercel (P22), y la QA de navegador sobre el SHA exacto (P16 #8).

## Publicar una snapshot nueva (desde LOCAL)

Solo snapshots que ya pasaron las compuertas P2 en LOCAL (`desplegar_snapshot.py`).

    # 1. medir en LOCAL
    python -c "import hashlib;print(hashlib.sha256(open(r'<snapshot>','rb').read()).hexdigest())"
    # 2. subir al volumen
    fly ssh sftp shell --app eretz-api-beta
    >> put <snapshot> /data/incoming/<etiqueta>.sqlite3
    # 3. activar (verifica sha256, integrity_check, filas, índice, no sintética; cambio atómico)
    fly ssh console --app eretz-api-beta -C "python /app/deploy/activar_snapshot.py activar --archivo /data/incoming/<etiqueta>.sqlite3 --sha256 <sha>"
    # 4. comprobar
    curl https://<app>.fly.dev/readyz

La API abre la snapshot en cada pedido: el cambio no requiere reiniciar. El volumen
conserva las 3 más recientes (nunca borra la activa ni la anterior).

## Rollback

- **Snapshot**: `fly ssh console --app eretz-api-beta -C "python /app/deploy/activar_snapshot.py rollback"`
  (vuelve a la anterior, verificada; queda en `/data/HISTORIAL.jsonl`).
- **Código**: `fly releases --app eretz-api-beta` y `fly deploy --image <imagen de la release anterior>`.
- **Todo**: `fly scale count 0 --app eretz-api-beta` apaga la API; el Preview muestra el
  estado «no disponible» del frontend (no inventa datos).

## Observabilidad

Una línea JSON por pedido en stdout (`fly logs`), mismo formato `http_request` que el frontend:
`requestId`, `route` (la plantilla, no el id), `status`, `outcome`, `durationMs` y solo las CLAVES de
los parámetros (nunca lo buscado). Cada respuesta lleva `x-request-id` para cruzar un error del
navegador con su línea. Latencia por ruta: filtrar `event=http_request` y agrupar por `route`.
Una excepción no atrapada responde 500 con el `requestId` y sin detalle interno.

## Seguridad y límites

- Solo lectura: la API abre SQLite con `mode=ro`; `database_writes: 0` en `/readyz`.
- Sin secretos en la imagen ni en `fly.toml`. La v1 (`/propiedades`, Supabase) queda sin
  `SUPABASE_*` en la beta: esos endpoints responden error (500) sin datos; la beta usa solo `/v2`.
- `/readyz` rechaza la snapshot SINTÉTICA salvo `ERETZ_ALLOW_SYNTHETIC_SNAPSHOT=1`: nunca
  definir esa variable en la app beta.
- CORS restringido al origen del Preview (`ERETZ_CORS_ORIGINS`).
- Encabezados en toda respuesta: `x-robots-tag: noindex, nofollow`, `nosniff`, `no-referrer`.
- Beta cerrada y `noindex` las pone el frontend (P14, P23); la API no se anuncia.
