"""Pure integrity checks shared by geographic download and comparison tooling."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any


def entity_ids(rows: Any) -> list[str]:
    if not isinstance(rows, list):
        raise ValueError('GeoRef entities must be a list')
    identities = []
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get('id'), str) or not row['id'].strip():
            raise ValueError('GeoRef entity requires a nonempty text ID')
        identities.append(row['id'])
    if len(set(identities)) != len(identities):
        raise ValueError('GeoRef resource contains duplicate entity IDs')
    return identities


def verified_rows(directory: Path, resource: str) -> list[dict[str, Any]]:
    path = directory / f'{resource}.json'
    raw = path.read_bytes()  # Missing is an error, not an empty reference.
    try:
        rows = json.loads(raw.decode('utf-8'))
        manifest = json.loads((directory / 'MANIFEST.json').read_text(encoding='utf-8'))
    except (ValueError, UnicodeError):
        raise ValueError('Invalid GeoRef reference or manifest JSON') from None
    entity_ids(rows)
    if not isinstance(manifest, dict) or not isinstance(manifest.get('recursos'), dict):
        raise ValueError('GeoRef reference requires resource manifest metadata')
    record = manifest['recursos'].get(resource.replace('_', '-'))
    if not isinstance(record, dict) or record.get('archivo') != path.name:
        raise ValueError('GeoRef resource is missing from its manifest')
    total = record.get('total_declarado')
    count = record.get('filas_traidas')
    if (type(total) is not int or total <= 0 or type(count) is not int
            or total != len(rows) or count != len(rows) or record.get('completo') is not True):
        raise ValueError('GeoRef reference count or completeness is not verified')
    expected = record.get('sha256')
    if not isinstance(expected, str) or not re.fullmatch('[0-9a-f]{64}', expected):
        raise ValueError('GeoRef reference requires a valid SHA256')
    scope = manifest.get('sha256_scope')
    if scope == 'file_bytes_utf8_lf':
        if type(manifest.get('schema_version')) is not int or manifest['schema_version'] != 2:
            raise ValueError('Unknown GeoRef manifest version')
        payload = raw
    elif scope is None and 'schema_version' not in manifest:
        # Explicit compatibility for the demonstrated historical Windows writer.
        payload = raw.decode('utf-8').replace('\r\n', '\n').replace('\r', '\n').encode('utf-8')
    else:
        raise ValueError('Unknown GeoRef manifest hash scope')
    if hashlib.sha256(payload).hexdigest() != expected:
        raise ValueError('GeoRef reference hash does not match its manifest')
    return rows
