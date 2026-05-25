"""Mide el estado actual de propiedades y las ultimas runs de scraping."""
import os, sys, requests
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, ".")
from dotenv import load_dotenv
load_dotenv(".env")
from collections import Counter

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = (
    os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    or os.environ.get("SUPABASE_KEY", "")
)
hdrs = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
}
hdrs_count = {**hdrs, "Prefer": "count=exact", "Range": "0-0"}


def count(url):
    r = requests.get(url, headers=hdrs_count)
    return r.headers.get("Content-Range", "?/0").split("/")[-1]


def fetch_all(url):
    all_data = []
    offset = 0
    hdrs2 = {k: v for k, v in hdrs.items() if k not in ("Prefer", "Range")}
    while True:
        sep = "&" if "?" in url else "?"
        r = requests.get(f"{url}{sep}limit=1000&offset={offset}", headers=hdrs2)
        batch = r.json()
        if not isinstance(batch, list):
            print("ERROR:", batch)
            break
        all_data.extend(batch)
        if len(batch) < 1000:
            break
        offset += 1000
    return all_data


print("=== ESTADO GLOBAL PROPIEDADES ===")
print(f"Total propiedades:    {count(SUPABASE_URL+'/rest/v1/propiedades?select=id')}")
print(f"Con imagenes:         {count(SUPABASE_URL+'/rest/v1/propiedades?imagenes=not.is.null&select=id')}")
print(f"Con precio > 0:       {count(SUPABASE_URL+'/rest/v1/propiedades?precio=not.is.null&precio=gt.0&select=id')}")
print(f"Con coordenadas:      {count(SUPABASE_URL+'/rest/v1/propiedades?latitud=not.is.null&longitud=not.is.null&select=id')}")
print(f"Sin coordenadas:      {count(SUPABASE_URL+'/rest/v1/propiedades?latitud=is.null&select=id')}")

print()
print("=== QUEUE STATUS ===")
print(f"Pending/running items: {count(SUPABASE_URL+'/rest/v1/scraping_run_items?status=in.(pending,running)&select=id')}")
print(f"v_next_batch (lista):  {count(SUPABASE_URL+'/rest/v1/v_next_scraping_batch?lista_para_batch=eq.true&select=inmobiliaria_id')}")
print(f"v_next_batch (total):  {count(SUPABASE_URL+'/rest/v1/v_next_scraping_batch?select=inmobiliaria_id')}")

print()
print("=== ULTIMAS 5 RUNS ===")
runs_raw = requests.get(
    f"{SUPABASE_URL}/rest/v1/scraping_runs?select=id,status,started_at,total_inmobiliarias_planificadas&order=id.desc&limit=5",
    headers=hdrs,
).json()

for run in runs_raw:
    run_id = run["id"]
    data = fetch_all(
        f"{SUPABASE_URL}/rest/v1/scraping_run_items?scraping_run_id=eq.{run_id}"
        f"&select=status,error_type,propiedades_nuevas,propiedades_actualizadas,metadata"
    )
    if not data:
        print(f"Run {run_id} ({run.get('status')}): sin items")
        continue
    cnt = Counter(x["status"] for x in data)
    err = Counter(
        x.get("error_type", "") for x in data if x["status"] == "error"
    )
    nuevas = sum(x.get("propiedades_nuevas") or 0 for x in data)
    actualizadas = sum(x.get("propiedades_actualizadas") or 0 for x in data)

    # Geocoding desde metadata de los items
    geo_done = 0
    geo_pending = 0
    geo_failed = 0
    for x in data:
        meta = x.get("metadata") or {}
        if isinstance(meta, dict):
            geo_done += int(meta.get("geocoding_done") or meta.get("geocodificadas") or 0)
            geo_pending += int(meta.get("geocoding_pending") or meta.get("geocoding_omitido_por_timeout") or 0)
            geo_failed += int(meta.get("geocoding_failed") or 0)

    started = (run.get("started_at") or "-")[:19]
    print(
        f"Run {run_id} | {run.get('status')} | planif={run.get('total_inmobiliarias_planificadas')} "
        f"| started={started}"
    )
    print(f"  Items: {dict(cnt)} | nuevas={nuevas} | actualizadas={actualizadas}")
    print(f"  Geocoding: done={geo_done} pending={geo_pending} failed={geo_failed}")
    if err:
        top_errors = sorted(err.items(), key=lambda x: -x[1])[:5]
        print(f"  Errores: {dict(top_errors)}")
    print()
