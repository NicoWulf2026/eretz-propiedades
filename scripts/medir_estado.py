"""Mide el estado actual de propiedades y run 43."""
import os, sys, requests
sys.path.insert(0, '.')
from dotenv import load_dotenv
load_dotenv('.env')
from collections import Counter

SUPABASE_URL = os.environ.get('SUPABASE_URL', '').rstrip('/')
SUPABASE_KEY = os.environ.get('SUPABASE_SERVICE_ROLE_KEY', '') or os.environ.get('SUPABASE_KEY', '')
hdrs = {
    'apikey': SUPABASE_KEY, 'Authorization': f'Bearer {SUPABASE_KEY}',
    'Content-Type': 'application/json', 'Prefer': 'count=exact', 'Range': '0-0'
}

def count(url):
    r = requests.get(url, headers=hdrs)
    return r.headers.get('Content-Range', '?/0').split('/')[-1]

print('=== ESTADO GLOBAL PROPIEDADES ===')
print(f'Total propiedades: {count(SUPABASE_URL+"/rest/v1/propiedades?select=id")}')
print(f'Con imagenes:      {count(SUPABASE_URL+"/rest/v1/propiedades?imagenes=not.is.null&select=id")}')
print(f'Con precio > 0:    {count(SUPABASE_URL+"/rest/v1/propiedades?precio=not.is.null&precio=gt.0&select=id")}')

print()
print('=== RUNS STATUS ===')
def fetch_all(url):
    all_data = []
    offset = 0
    hdrs2 = {k: v for k, v in hdrs.items() if k != 'Prefer' and k != 'Range'}
    while True:
        sep = '&' if '?' in url else '?'
        r = requests.get(f'{url}{sep}limit=1000&offset={offset}', headers=hdrs2)
        batch = r.json()
        if not isinstance(batch, list):
            print('ERROR:', batch); break
        all_data.extend(batch)
        if len(batch) < 1000: break
        offset += 1000
    return all_data

for run_id in [43, 44]:
    data = fetch_all(
        f'{SUPABASE_URL}/rest/v1/scraping_run_items?scraping_run_id=eq.{run_id}'
        '&select=status,error_type,propiedades_nuevas,propiedades_actualizadas'
    )
    if not data:
        print(f'Run {run_id}: sin datos')
        continue
    cnt = Counter(x['status'] for x in data)
    err = Counter(x.get('error_type', '') for x in data if x['status'] == 'error')
    nuevas = sum(x.get('propiedades_nuevas') or 0 for x in data)
    actualizadas = sum(x.get('propiedades_actualizadas') or 0 for x in data)
    print(f'Run {run_id}: {dict(cnt)} | nuevas={nuevas} | actualizadas={actualizadas}')
    if err:
        print(f'  Errores: {dict(err)}')
