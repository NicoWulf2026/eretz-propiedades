#!/usr/bin/env python
"""Validación read-only del piloto Pinamar 21 propiedades.

Lee directamente de Supabase (tabla propiedades + view v_propiedades_frontend_mapa)
y de Neon (publish_queue + propiedades_staging). NO escribe nada.

Uso:
  USE_INTERNAL_DB=true python scripts/validate_pinamar_pilot.py
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
PINAMAR_INMO_ID = 4019
PINAMAR_SB_ID_MIN = 6725
PINAMAR_SB_ID_MAX = 6790
PINAMAR_STAGING_IDS = [
    81392, 81396, 81399, 81400, 81401, 81402, 81403,
    81408, 81410, 81411, 81412, 81413, 81414, 81418,
    81420, 81421, 81422, 81423, 81424, 81443, 81445,
]
PINAMAR_BBOX = {"lat_min": -37.20, "lat_max": -37.00, "lon_min": -56.95, "lon_max": -56.75}
EXPECTED_COUNT = 21

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _load_env() -> None:
    for fname in (".env", ".env.local"):
        p = REPO_ROOT / fname
        if not p.exists():
            continue
        for raw in p.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = k.strip()
            v = v.strip().strip('"').strip("'")
            if k and k not in os.environ:
                os.environ[k] = v


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "t", "yes", "y", "on"}


# ---------------------------------------------------------------------------
# Supabase REST queries (read-only GET)
# ---------------------------------------------------------------------------
def _sb_get(session, supabase_url: str, headers: dict, table: str, params: dict) -> List[Dict]:
    import requests
    url = f"{supabase_url}/rest/v1/{table}"
    resp = session.get(url, headers=headers, params=params, timeout=15)
    resp.raise_for_status()
    return resp.json()


def query_supabase(supabase_url: str, supabase_key: str) -> dict:
    import requests

    session = requests.Session()
    headers = {
        "apikey": supabase_key,
        "Authorization": f"Bearer {supabase_key}",
    }

    results: dict = {}

    # --- 1. propiedades: los 21 por inmo_id en el rango de SB IDs esperado
    print("  [Supabase] Consultando tabla propiedades inmo_id=4019 ...")
    props_raw = _sb_get(
        session, supabase_url, headers,
        "propiedades",
        {
            "select": "id,inmobiliaria_id,hash_dedup,titulo,precio,moneda,tipo_propiedad,operacion,"
                      "latitud,longitud,ciudad,provincia,pais,direccion,barrio,estado,url,"
                      "url_normalizada,imagenes,created_at,updated_at",
            "inmobiliaria_id": f"eq.{PINAMAR_INMO_ID}",
            "order": "id.asc",
            "limit": "100",
        },
    )
    results["propiedades_inmo4019"] = props_raw

    # --- 2. Filtrar solo los IDs esperados del piloto
    pinamar_ids_set = set(range(PINAMAR_SB_ID_MIN, PINAMAR_SB_ID_MAX + 1))
    pilot_rows = [r for r in props_raw if int(r.get("id", 0)) in pinamar_ids_set]
    results["pilot_rows"] = pilot_rows

    # --- 3. view v_propiedades_frontend_mapa — buscar inmo_id=4019, estado=activo
    print("  [Supabase] Consultando view v_propiedades_frontend_mapa ...")
    try:
        view_rows = _sb_get(
            session, supabase_url, headers,
            "v_propiedades_frontend_mapa",
            {
                "select": "id,inmobiliaria_id,titulo,precio,moneda,latitud,longitud,"
                          "ciudad_final,provincia_final,estado,imagenes,tiene_imagen_real",
                "inmobiliaria_id": f"eq.{PINAMAR_INMO_ID}",
                "estado": "eq.activo",
                "order": "id.asc",
                "limit": "100",
            },
        )
        results["view_rows"] = view_rows
    except Exception as exc:
        results["view_error"] = str(exc)
        results["view_rows"] = []

    # --- 4. Check hash_dedup uniqueness — does any row share hash with pilot?
    pilot_hashes = [r.get("hash_dedup") for r in pilot_rows if r.get("hash_dedup")]
    results["pilot_hashes"] = pilot_hashes

    return results


# ---------------------------------------------------------------------------
# Neon read-only queries
# ---------------------------------------------------------------------------
def query_neon(db_url: str) -> dict:
    import psycopg
    from psycopg.rows import dict_row

    results: dict = {}

    with psycopg.connect(db_url, row_factory=dict_row) as conn:
        conn.autocommit = True  # read-only mode — no transaction
        with conn.cursor() as cur:

            # --- 1. publish_queue: status de las 21 Pinamar
            cur.execute(
                """
                SELECT id, staging_id, status, priority, attempts, queued_at, last_attempt_at
                FROM public.publish_queue
                WHERE staging_id = ANY(%s)
                ORDER BY staging_id ASC
                """,
                [PINAMAR_STAGING_IDS],
            )
            results["queue_pinamar"] = [dict(r) for r in cur.fetchall()]

            # --- 2. publish_queue: otros pending (no Pinamar)
            cur.execute(
                """
                SELECT status, COUNT(*) as cnt
                FROM public.publish_queue
                WHERE staging_id != ALL(%s)
                GROUP BY status
                ORDER BY status
                """,
                [PINAMAR_STAGING_IDS],
            )
            results["queue_others_by_status"] = [dict(r) for r in cur.fetchall()]

            # --- 3. propiedades_staging: estado de las 21 Pinamar
            cur.execute(
                """
                SELECT id, status, geocoding_status, validation_score,
                       latitud, longitud, ciudad, precio, moneda,
                       direccion_normalizada
                FROM public.propiedades_staging
                WHERE id = ANY(%s)
                ORDER BY id ASC
                """,
                [PINAMAR_STAGING_IDS],
            )
            results["staging_pinamar"] = [dict(r) for r in cur.fetchall()]

            # --- 4. Total publish_queue
            cur.execute("SELECT COUNT(*) as total FROM public.publish_queue")
            results["queue_total"] = dict(cur.fetchone())["total"]

            # --- 5. geocoding_results for Pinamar
            cur.execute(
                """
                SELECT propiedad_id, precision_geocoding, status, proveedor
                FROM public.geocoding_results
                WHERE propiedad_id = ANY(%s)
                ORDER BY propiedad_id ASC
                """,
                [PINAMAR_STAGING_IDS],
            )
            results["geocoding_results"] = [dict(r) for r in cur.fetchall()]

    return results


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------
def analyze(sb_data: dict, neon_data: dict) -> dict:
    report: dict = {
        "checks": {},
        "warnings": [],
        "errors": [],
    }

    pilot_rows = sb_data.get("pilot_rows", [])
    view_rows = sb_data.get("view_rows", [])
    queue_pinamar = neon_data.get("queue_pinamar", [])
    staging_pinamar = neon_data.get("staging_pinamar", [])
    geocoding = neon_data.get("geocoding_results", [])

    # ---- Check 1: exactly 21 in Supabase
    count_sb = len(pilot_rows)
    report["checks"]["sb_count"] = {
        "expected": EXPECTED_COUNT,
        "actual": count_sb,
        "pass": count_sb == EXPECTED_COUNT,
    }

    # ---- Check 2: no duplicate hash_dedup within pilot
    hashes = [r.get("hash_dedup") for r in pilot_rows if r.get("hash_dedup")]
    unique_hashes = len(set(hashes))
    report["checks"]["hash_uniqueness"] = {
        "total_rows": len(pilot_rows),
        "unique_hashes": unique_hashes,
        "pass": unique_hashes == len(hashes),
    }

    # ---- Check 3: all lat/lon within Pinamar bbox
    bbox_fails = []
    for r in pilot_rows:
        lat = r.get("latitud")
        lon = r.get("longitud")
        if lat is None or lon is None:
            bbox_fails.append({"id": r.get("id"), "issue": "null_coordinates"})
        elif not (PINAMAR_BBOX["lat_min"] <= lat <= PINAMAR_BBOX["lat_max"]
                  and PINAMAR_BBOX["lon_min"] <= lon <= PINAMAR_BBOX["lon_max"]):
            bbox_fails.append({
                "id": r.get("id"), "lat": lat, "lon": lon, "issue": "outside_bbox"
            })
    report["checks"]["bbox_pinamar"] = {
        "fail_count": len(bbox_fails),
        "pass": len(bbox_fails) == 0,
        "failures": bbox_fails,
    }

    # ---- Check 4: all estado='activo'
    non_activo = [r for r in pilot_rows if r.get("estado") != "activo"]
    report["checks"]["estado_activo"] = {
        "non_activo": len(non_activo),
        "pass": len(non_activo) == 0,
        "detail": [{"id": r.get("id"), "estado": r.get("estado")} for r in non_activo],
    }

    # ---- Check 5: images present
    no_images = [r for r in pilot_rows if not r.get("imagenes")]
    few_images = [r for r in pilot_rows if r.get("imagenes") and len(r["imagenes"]) < 3]
    report["checks"]["images"] = {
        "no_images_count": len(no_images),
        "few_images_count": len(few_images),
        "pass": len(no_images) == 0,
    }

    # ---- Check 6: all USD
    non_usd = [r for r in pilot_rows if r.get("moneda", "").upper() != "USD"]
    report["checks"]["currency_usd"] = {
        "non_usd": len(non_usd),
        "pass": len(non_usd) == 0,
    }

    # ---- Check 7: ciudad / provincia correct
    wrong_ciudad = [r for r in pilot_rows
                    if (r.get("ciudad") or "").lower() not in {"pinamar", ""}]
    report["checks"]["ciudad_pinamar"] = {
        "wrong_ciudad": len(wrong_ciudad),
        "pass": len(wrong_ciudad) == 0,
        "detail": [{"id": r.get("id"), "ciudad": r.get("ciudad")} for r in wrong_ciudad[:5]],
    }

    # ---- Check 8: view includes them
    view_ids = {int(r.get("id", 0)) for r in view_rows}
    pilot_sb_ids = {int(r.get("id", 0)) for r in pilot_rows}
    missing_from_view = pilot_sb_ids - view_ids
    report["checks"]["view_visibility"] = {
        "total_in_view": len(view_rows),
        "pilot_found_in_view": len(pilot_sb_ids & view_ids),
        "missing_from_view": len(missing_from_view),
        "pass": len(missing_from_view) == 0,
        "missing_ids": sorted(missing_from_view),
    }
    if sb_data.get("view_error"):
        report["checks"]["view_visibility"]["error"] = sb_data["view_error"]

    # ---- Check 9: publish_queue all 'done'
    queue_done = [r for r in queue_pinamar if r.get("status") == "done"]
    queue_non_done = [r for r in queue_pinamar if r.get("status") != "done"]
    report["checks"]["queue_status"] = {
        "done": len(queue_done),
        "non_done": len(queue_non_done),
        "pass": len(queue_non_done) == 0,
        "detail": [{"id": r.get("id"), "staging_id": r.get("staging_id"),
                    "status": r.get("status")} for r in queue_non_done],
    }

    # ---- Check 10: staging all 'published'
    staging_published = [r for r in staging_pinamar if r.get("status") == "published"]
    staging_non_published = [r for r in staging_pinamar if r.get("status") != "published"]
    report["checks"]["staging_status"] = {
        "published": len(staging_published),
        "non_published": len(staging_non_published),
        "pass": len(staging_non_published) == 0,
    }

    # ---- Check 11: no collateral in publish_queue
    others_status = neon_data.get("queue_others_by_status", [])
    queue_total = int(neon_data.get("queue_total", 0))
    report["checks"]["queue_collateral"] = {
        "queue_total": queue_total,
        "pinamar_queue_rows": len(queue_pinamar),
        "others_by_status": others_status,
        "note": "61 pending esperados en otros (no Pinamar)",
    }

    # ---- Warnings
    if len(pilot_rows) != EXPECTED_COUNT:
        report["warnings"].append(
            f"Supabase devolvió {len(pilot_rows)} filas, se esperaban {EXPECTED_COUNT}"
        )
    if missing_from_view:
        report["warnings"].append(
            f"{len(missing_from_view)} propiedades no aparecen en v_propiedades_frontend_mapa: {sorted(missing_from_view)}"
        )
    # superficie null warning
    no_superficie = [r for r in pilot_rows if not r.get("superficie_total") and not r.get("superficie_cubierta")]
    # (superficie está en propiedades table but not in our select — omit)

    return report


# ---------------------------------------------------------------------------
# Print report
# ---------------------------------------------------------------------------
def print_report(sb_data: dict, neon_data: dict, analysis: dict) -> None:
    pilot_rows = sb_data.get("pilot_rows", [])

    print()
    print("=" * 72)
    print("VALIDACIÓN PILOTO PINAMAR — 21 propiedades marcelgestion.com.ar")
    print("=" * 72)

    # --- Supabase table propiedades
    print()
    print("=== FASE 1 — SUPABASE tabla propiedades ===")
    checks = analysis["checks"]

    # sb_count
    c = checks["sb_count"]
    status = "✓ PASS" if c["pass"] else "✗ FAIL"
    print(f"  Conteo exact:      {c['actual']}/{c['expected']}  {status}")

    # hash uniqueness
    c = checks["hash_uniqueness"]
    status = "✓ PASS" if c["pass"] else "✗ FAIL"
    print(f"  Hash únicos:       {c['unique_hashes']}/{c['total_rows']}  {status}")

    # bbox
    c = checks["bbox_pinamar"]
    status = "✓ PASS" if c["pass"] else f"✗ FAIL ({c['fail_count']} fuera de bbox)"
    print(f"  Bbox Pinamar:      {status}")
    if c["failures"]:
        for f in c["failures"]:
            print(f"    → ID {f['id']}: {f}")

    # estado
    c = checks["estado_activo"]
    status = "✓ PASS" if c["pass"] else f"✗ FAIL ({c['non_activo']} no activos)"
    print(f"  Estado=activo:     {status}")

    # imágenes
    c = checks["images"]
    status = "✓ PASS" if c["pass"] else f"✗ FAIL ({c['no_images_count']} sin imágenes)"
    print(f"  Imágenes:          {status}  (few<3: {c['few_images_count']})")

    # moneda
    c = checks["currency_usd"]
    status = "✓ PASS" if c["pass"] else f"✗ FAIL ({c['non_usd']} no USD)"
    print(f"  Moneda USD:        {status}")

    # ciudad
    c = checks["ciudad_pinamar"]
    status = "✓ PASS" if c["pass"] else f"✗ WARN ({c['wrong_ciudad']} ciudad diferente)"
    print(f"  Ciudad=Pinamar:    {status}")
    if c["detail"]:
        for d in c["detail"]:
            print(f"    → ID {d['id']}: ciudad={d['ciudad']!r}")

    # --- Detalle de propiedades
    print()
    print("  Propiedades encontradas:")
    print(f"  {'sb_id':>6}  {'tipo':12}  {'operacion':10}  {'precio':>12}  {'lat':>10}  {'lon':>10}  {'imgs':>4}  {'estado':8}  titulo")
    print("  " + "-" * 100)
    for r in sorted(pilot_rows, key=lambda x: int(x.get("id", 0))):
        imgs_count = len(r.get("imagenes") or [])
        titulo = (r.get("titulo") or "")[:45]
        print(
            f"  {r.get('id'):>6}  "
            f"{(r.get('tipo_propiedad') or ''):12}  "
            f"{(r.get('operacion') or ''):10}  "
            f"USD {r.get('precio') or 0:>10,.0f}  "
            f"{r.get('latitud') or 0:>10.4f}  "
            f"{r.get('longitud') or 0:>10.4f}  "
            f"{imgs_count:>4}  "
            f"{(r.get('estado') or ''):8}  "
            f"{titulo}"
        )

    # --- View
    print()
    print("=== FASE 1b — VIEW v_propiedades_frontend_mapa ===")
    c = checks["view_visibility"]
    if "error" in c:
        print(f"  ✗ ERROR al consultar view: {c['error']}")
    else:
        status = "✓ PASS" if c["pass"] else f"✗ FAIL"
        print(f"  Total inmo_id=4019 activos en view:  {c['total_in_view']}")
        print(f"  Piloto encontrado en view:           {c['pilot_found_in_view']}/21  {status}")
        if c["missing_ids"]:
            print(f"  Faltantes en view: {c['missing_ids']}")

        # mostrar un sample de la view
        view_rows = sb_data.get("view_rows", [])
        if view_rows:
            print()
            print("  Sample de la view (primeras 5):")
            print(f"  {'sb_id':>6}  {'titulo':40}  {'precio':>12}  {'lat':>10}  {'lon':>10}  {'imgs':>4}  img_real")
            for r in view_rows[:5]:
                imgs_count = len(r.get("imagenes") or [])
                titulo = (r.get("titulo") or "")[:40]
                print(
                    f"  {r.get('id'):>6}  "
                    f"{titulo:40}  "
                    f"USD {r.get('precio') or 0:>10,.0f}  "
                    f"{r.get('latitud') or 0:>10.4f}  "
                    f"{r.get('longitud') or 0:>10.4f}  "
                    f"{imgs_count:>4}  "
                    f"{r.get('tiene_imagen_real')}"
                )

    # --- Neon checks
    print()
    print("=== FASE 2 — NEON publish_queue + staging ===")

    c = checks["queue_status"]
    status = "✓ PASS" if c["pass"] else f"✗ FAIL"
    print(f"  Queue Pinamar done:     {c['done']}/21  {status}")
    if c["detail"]:
        for d in c["detail"]:
            print(f"    → queue_id={d['id']} staging_id={d['staging_id']} status={d['status']}")

    c = checks["staging_status"]
    status = "✓ PASS" if c["pass"] else f"✗ FAIL"
    print(f"  Staging published:      {c['published']}/21  {status}")

    c = checks["queue_collateral"]
    print(f"  Queue total:            {c['queue_total']}")
    print(f"  Queue Pinamar rows:     {c['pinamar_queue_rows']}")
    print(f"  Otros por status:       {c['others_by_status']}")

    # --- geocoding
    geocoding = neon_data.get("geocoding_results", [])
    print()
    print(f"  Geocoding results rows: {len(geocoding)}/21")
    prec_counts: dict = {}
    for g in geocoding:
        p = g.get("precision_geocoding", "?")
        prec_counts[p] = prec_counts.get(p, 0) + 1
    for p, cnt in sorted(prec_counts.items()):
        print(f"    {p}: {cnt}")

    # --- Summary
    print()
    print("=== RESUMEN DE CHECKS ===")
    all_pass = True
    for check_name, check_data in analysis["checks"].items():
        if check_name == "queue_collateral":
            continue  # informational only
        passed = check_data.get("pass", True)
        if not passed:
            all_pass = False
        icon = "✓" if passed else "✗"
        print(f"  {icon}  {check_name}")

    print()
    if all_pass:
        print("  RESULTADO GLOBAL: ✓ TODOS LOS CHECKS PASARON")
    else:
        print("  RESULTADO GLOBAL: ✗ HAY CHECKS FALLIDOS — ver detalle arriba")

    if analysis["warnings"]:
        print()
        print("  ADVERTENCIAS:")
        for w in analysis["warnings"]:
            print(f"    ⚠  {w}")

    print()
    print("=" * 72)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    _load_env()

    supabase_url = os.getenv("SUPABASE_URL", "").rstrip("/")
    supabase_key = (
        os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
        or os.getenv("SUPABASE_KEY", "")
    )
    internal_db_url = os.getenv("INTERNAL_DB_URL", "").strip()

    if not supabase_url or not supabase_key:
        raise SystemExit("Faltan SUPABASE_URL y/o SUPABASE_SERVICE_ROLE_KEY en .env")
    if not _env_flag("USE_INTERNAL_DB"):
        raise SystemExit("USE_INTERNAL_DB no está en true; necesario para leer Neon")
    if not internal_db_url:
        raise SystemExit("Falta INTERNAL_DB_URL en .env")

    print()
    print("Iniciando validación read-only del piloto Pinamar...")
    print(f"  Supabase URL: {supabase_url}")
    print(f"  inmo_id: {PINAMAR_INMO_ID} | sb_ids: {PINAMAR_SB_ID_MIN}–{PINAMAR_SB_ID_MAX}")
    print()

    # --- Query Supabase
    print("[1/2] Consultando Supabase...")
    sb_data = query_supabase(supabase_url, supabase_key)
    print(f"  propiedades inmo_id=4019 totales: {len(sb_data.get('propiedades_inmo4019', []))}")
    print(f"  propiedades en rango piloto:       {len(sb_data.get('pilot_rows', []))}")
    print(f"  view rows activos inmo_id=4019:    {len(sb_data.get('view_rows', []))}")
    if sb_data.get("view_error"):
        print(f"  view ERROR: {sb_data['view_error']}")

    # --- Query Neon
    print()
    print("[2/2] Consultando Neon (Supabase interno)...")
    neon_data = query_neon(internal_db_url)
    print(f"  queue pinamar:   {len(neon_data.get('queue_pinamar', []))} filas")
    print(f"  staging pinamar: {len(neon_data.get('staging_pinamar', []))} filas")
    print(f"  queue total:     {neon_data.get('queue_total', '?')}")

    # --- Analyze
    analysis = analyze(sb_data, neon_data)

    # --- Print
    print_report(sb_data, neon_data, analysis)


if __name__ == "__main__":
    main()
