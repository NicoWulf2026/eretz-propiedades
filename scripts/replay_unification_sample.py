"""Bounded public-page replay against actual Git parser implementations.

No database/client/pipeline is invoked. Captured HTML is reused by all parsers.
This is a new sample, NOT the missing historical 413-source benchmark.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
import types
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bs4 import BeautifulSoup  # noqa: E402 - direct script bootstrap
from connectors.base import Descargador, Fuente, LimitadorDeRitmo  # noqa: E402
from connectors.generico import GenericoConnector  # noqa: E402

HISTORICAL = '9aa299bde9f7bc410b010be1387566269f551145'
LOCAL = 'd9238e64be53d27f0ca46deae74ad16eb01bb6b5'
URLS = [
    'https://bottegapropiedades.com.ar/site/properties/527501/alquiler-funes-3-dormitorios',
    'https://bottegapropiedades.com.ar/site/properties/517174/casa-en-venta-ibarlucea',
    'https://bottegapropiedades.com.ar/site/properties/527177/vendemos-dto-pb-de-3-dormitorios-en-b-rucci',
    'https://bottegapropiedades.com.ar/site/properties/550521/casa-a-reciclar-en-b-luduena',
    'https://bottegapropiedades.com.ar/site/properties/562437/casa-tres-dormitorios-en-alquiler',
]
FIELDS = ('ambientes', 'dormitorios', 'banos', 'precio', 'moneda', 'operacion')


class NoEnvironment(ast.NodeTransformer):
    """Prevent reading environment values even while importing old source."""
    def visit_Call(self, node):
        node = self.generic_visit(node)
        func = ast.unparse(node.func)
        if func in {'os.getenv', 'os.environ.get'}:
            return node.args[1] if len(node.args) > 1 else ast.Constant(None)
        return node


def load_git_module(ref, filename, module_name):
    source = subprocess.check_output(
        ['git', '-c', f'safe.directory={ROOT.as_posix()}', '-C', str(ROOT),
         'show', f'{ref}:{filename}'], text=True, encoding='utf-8')
    tree = ast.parse(source)
    # Import definitions/constants but not bootstrap calls, CLI, DB or services.
    tree.body = [n for n in tree.body if isinstance(n, (
        ast.Import, ast.ImportFrom, ast.FunctionDef, ast.AsyncFunctionDef,
        ast.ClassDef, ast.Assign, ast.AnnAssign,
    ))]
    tree = ast.fix_missing_locations(NoEnvironment().visit(tree))
    module = types.ModuleType(module_name)
    module.__file__ = str(ROOT / filename)
    module.__package__ = module_name.rpartition('.')[0]
    sys.modules[module_name] = module
    exec(compile(tree, f'{ref}:{filename}', 'exec'), module.__dict__)
    return module


def deny_network(*args, **kwargs):
    raise AssertionError('network is forbidden during parser replay')


def load_git_detail_module(ref):
    """Load only pure URL functions/constants, never historical bootstrap."""
    from scraper import detail_urls
    names = {name for name in vars(detail_urls) if name.startswith('_') or name.startswith('extract_')}
    source = subprocess.check_output(
        ['git', '-c', f'safe.directory={ROOT.as_posix()}', '-C', str(ROOT),
         'show', f'{ref}:scraper/playwright_scraper.py'], text=True, encoding='utf-8')
    tree = ast.parse(source)
    body = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in names:
            body.append(node)
        elif isinstance(node, ast.Assign) and all(
                isinstance(target, ast.Name) and target.id.startswith('_DETAIL_') for target in node.targets):
            body.append(node)
    definitions = ast.fix_missing_locations(ast.Module(body=body, type_ignores=[]))
    module = types.ModuleType('historical_detail_urls')
    module.__dict__.update(re=__import__('re'), BeautifulSoup=BeautifulSoup)
    from urllib.parse import parse_qsl, urljoin, urlparse
    module.__dict__.update(parse_qsl=parse_qsl, urljoin=urljoin, urlparse=urlparse)
    from typing import Dict, List, Optional, Set, Tuple
    module.__dict__.update(Dict=Dict, List=List, Optional=Optional, Set=Set, Tuple=Tuple)
    exec(compile(definitions, f'{ref}:pure-detail-functions', 'exec'), module.__dict__)
    return module


def compare_detail_discovery(baseline):
    historical = load_git_detail_module(HISTORICAL)
    target = 'https://agency.provider.test/propiedad/casa-en-venta-123'
    cases = [(name, f'<a {attr}>Ver</a>', [target]) for name, attr in (
        ('double_href', 'href="/propiedad/casa-en-venta-123"'),
        ('single_href', "href='/propiedad/casa-en-venta-123'"),
        ('data_href', 'data-href="/propiedad/casa-en-venta-123"'),
        ('data_url', 'data-url="/propiedad/casa-en-venta-123"'),
        ('onclick', 'onclick="window.location.href=\'/propiedad/casa-en-venta-123\'"'),
    )]
    cases += [
        ('provider_root_not_tenant', '<a href="https://provider.test/propiedad/casa-en-venta-123">Ver</a>', []),
        ('neighbor_not_tenant', '<a href="https://neighbor.provider.test/propiedad/casa-en-venta-123">Ver</a>', []),
        ('forbidden_portal', '<a href="https://zonaprop.com.ar/propiedad/casa-en-venta-123">Ver</a>', []),
        ('editorial_not_property', '<a href="/nosotros">Ver</a>', []),
    ]
    rows = []
    base = 'https://agency.provider.test'
    for name, content, expected in cases:
        html = '<article class="property-card"><b>Casa en venta USD 120000</b>' + content + '</article>'
        card = BeautifulSoup(html, 'html.parser').article
        results = {
            'historical': historical.extract_candidate_detail_urls_from_card(card, base),
            'local_before': baseline.GenericoConnector._fichas_en(html, base),
            'unified': GenericoConnector._fichas_en(html, base),
        }
        rows.append(dict(case=name, expected=expected, results=results,
                         correct={key: value == expected for key, value in results.items()}))
    return dict(scope='Nine offline structural cases, not the 413-source population benchmark.', rows=rows,
                correct={key: sum(row['correct'][key] for row in rows)
                         for key in ('historical', 'local_before', 'unified')})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--offline', action='store_true', help='reuse captured pages only')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    downloader = Descargador(LimitadorDeRitmo(intervalo=2), reintentos=1)
    captured = []
    for url in URLS:
        path = args.output / (hashlib.sha256(url.encode()).hexdigest()[:16] + '.html')
        start = time.perf_counter()
        try:
            html = path.read_text(encoding='utf-8') if args.offline else downloader.bajar(url)
            if not args.offline:
                path.write_text(html, encoding='utf-8')
            captured.append((url, html, round(time.perf_counter() - start, 3)))
        except Exception as error:
            captured.append((url, None, type(error).__name__))
    with patch('requests.sessions.Session.request', deny_network), patch('urllib.request.urlopen', deny_network), patch('socket.create_connection', deny_network):
        historical = load_git_module(HISTORICAL, 'scraper/scraper_propiedades.py', 'audit_historical')
        baseline = load_git_module(LOCAL, 'connectors/generico.py', 'connectors.audit_baseline')
        rows = []
        for url, html, latency in captured:
            row = dict(url=url, fetch_seconds=latency)
            if html is None:
                row['status'] = 'FETCH_FAILED'
                rows.append(row)
                continue
            row['sha256'] = hashlib.sha256(html.encode()).hexdigest()
            # Ground truth is explicit th/td structure, not regex adjacency.
            soup = BeautifulSoup(html, 'html.parser')
            labels = {'ambientes': 'ambientes', 'dormitorios': 'dormitorios', 'baños': 'banos'}
            expected = {}
            for tr in soup.select('tr'):
                th, td = tr.find('th'), tr.find('td')
                if th and td and th.get_text(strip=True).lower() in labels:
                    value = td.get_text(strip=True)
                    if value.isdigit():
                        expected[labels[th.get_text(strip=True).lower()]] = int(value)
            row['explicit_table'] = expected
            cached = types.SimpleNamespace(bajar=lambda requested: html)
            crudo = dict(source_url=url, source_listing_id=GenericoConnector._id_de(url))
            agency = Fuente('audit:bottega', 'Bottega Propiedades', 'https://bottegapropiedades.com.ar')
            for name, extract in (
                ('historical', lambda: historical._html_extract_detail(soup, url, {'id': 1}, html)),
                ('local_before', lambda: baseline.GenericoConnector(cached).normalize(crudo, agency)),
                ('unified', lambda: GenericoConnector(cached).normalize(crudo, agency)),
            ):
                start = time.perf_counter()
                try:
                    prop = extract()
                    values = prop if isinstance(prop, dict) else (prop.a_dict() if prop else {})
                    row[name] = {field: values.get(field) for field in FIELDS}
                    row[name]['matched_explicit_fields'] = sum(values.get(k) == v for k, v in expected.items())
                    row[name]['parser_ms'] = round(1000 * (time.perf_counter() - start), 2)
                except Exception as error:
                    row[name] = dict(error=type(error).__name__)
            rows.append(row)
    url_comparison = compare_detail_discovery(baseline)
    from scripts.regression_gate import compare
    comparable = [row for row in rows if 'sha256' in row
                  and 'error' not in row.get('local_before', {})
                  and 'error' not in row.get('unified', {})]
    extraction_regression = compare(
        [dict(row['local_before'], source_url=row['url'], canonical_agency_id='audit:bottega')
         for row in comparable],
        [dict(row['unified'], source_url=row['url'], canonical_agency_id='audit:bottega')
         for row in comparable])
    extraction_regression['scope'] = 'Only measured FIELDS on the five matched HTML pages; not all fields or agencies.'
    report = dict(schema='eretz_behavioral_sample_v2', historical_ref=HISTORICAL,
                  local_ref=LOCAL, rows=rows, database_writes=0,
                  detail_discovery=url_comparison, extraction_regression=extraction_regression,
                  limitation='New five-page, one-family sample; not a national or 413-source benchmark.')
    (args.output / 'comparison.json').write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
    print(json.dumps(dict(pages=len(rows), fetched=sum('sha256' in r for r in rows),
                         comparison=str(args.output / 'comparison.json'), database_writes=0)))


if __name__ == '__main__':
    main()
