"""Read-only, in-process API acceptance/latency measurement on a real snapshot."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sqlite3
import statistics
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fastapi import FastAPI  # noqa: E402 - direct script bootstrap
from fastapi.testclient import TestClient  # noqa: E402
from api import v2  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('snapshot', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    v2.SNAPSHOT = args.snapshot.resolve()
    with sqlite3.connect(f'file:{v2.SNAPSHOT.as_posix()}?mode=ro', uri=True) as conn:
        total = conn.execute('select count(*) from propiedades').fetchone()[0]
        ids = [r[0] for r in conn.execute('select id from propiedades order by id limit 100')]
        conflicts = conn.execute("select count(*) from propiedades where geo_estado='GEO_CONFLICT'").fetchone()[0]
        conflict_points = conn.execute("select count(*) from propiedades where geo_estado='GEO_CONFLICT' and latitud is not null").fetchone()[0]
        plan = [r[3] for r in conn.execute('explain query plan select id from propiedades where latitud between -35 and -34 and longitud between -59 and -58 limit 2000')]
    app = FastAPI()
    app.include_router(v2.router)
    client = TestClient(app)
    cases = [
        ('explorer', 'GET', '/v2/buscar', dict(q='casa', limit=24), None, 200),
        ('combined', 'GET', '/v2/buscar', dict(q='casa', operacion='venta', tipo='casa', moneda='USD', precio_min=0, dormitorios=1, limit=24), None, 200),
        ('price_asc', 'GET', '/v2/buscar', dict(sort='price_asc', moneda='USD', limit=24), None, 200),
        ('price_desc', 'GET', '/v2/buscar', dict(sort='price_desc', moneda='ARS', limit=24), None, 200),
        ('window_end', 'GET', '/v2/buscar', dict(limit=24, offset=200), None, 200),
        ('window_rejected', 'GET', '/v2/buscar', dict(offset=201), None, 400),
        ('invalid_sort', 'GET', '/v2/buscar', dict(sort='unknown'), None, 422),
        ('empty', 'GET', '/v2/buscar', dict(q='zzznothingmatchesxxx'), None, 200),
        ('map_small', 'GET', '/v2/propiedades/mapa', dict(north=-34.4, south=-34.8, east=-58.2, west=-58.7), None, 200),
        ('map_large_combined', 'GET', '/v2/propiedades/mapa', dict(north=-21, south=-56, east=-53, west=-74, q='casa', operacion='venta', limit=2000), None, 200),
        ('detail', 'GET', f'/v2/propiedades/{ids[0]}', {}, None, 200),
        ('agency', 'GET', '/v2/agencias/' + client.get(f'/v2/propiedades/{ids[0]}').json()['agency_id'], {}, None, 200),
        ('batch_100', 'POST', '/v2/propiedades/batch', {}, dict(ids=ids), 200),
        ('batch_missing', 'POST', '/v2/propiedades/batch', {}, dict(ids=[ids[0], 'definitely-absent-id', ids[0]]), 200),
    ]
    results = []
    for name, method, url, params, body, expected in cases:
        samples = []
        for _ in range(5):
            start = time.perf_counter()
            response = client.request(method, url, params=params, **({'json': body} if body else {}))
            samples.append(1000 * (time.perf_counter() - start))
            assert response.status_code == expected, (name, response.status_code)
        payload = response.json()
        if name == 'empty':
            assert payload['total'] == 0 and payload['data'] == []
        if name.startswith('map'):
            assert payload['returned_points'] <= 2000
            assert payload['truncated'] == (payload['viewport_matches'] > payload['returned_points'])
        if name == 'batch_missing':
            assert len(payload['items']) == 1 and payload['missing_ids'] == ['definitely-absent-id']
        results.append(dict(case=name, status=response.status_code,
                            median_ms=round(statistics.median(samples), 2), max_ms=round(max(samples), 2),
                            response_bytes=len(response.content),
                            total=payload.get('total', payload.get('total_matches')),
                            returned=payload.get('returned_points', len(payload.get('data', payload.get('items', []))))
                            if isinstance(payload.get('data', []), list) else None))
    report = dict(snapshot=str(v2.SNAPSHOT), total=total, conflicts=conflicts,
                  conflicting_map_points=conflict_points, map_query_plan=plan, cases=results,
                  database_writes=0, scope='In-process local latency, not remote TTFB or production load test.')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    main()
