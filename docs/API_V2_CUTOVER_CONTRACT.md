# ERETZ API v2 backend cutover contract

Property payload version remains `eretz_api_property_v1`. All fields except
`id` may be null or absent when the source did not publish them. A zero numeric
value is serialized as zero, never as null.

## Combined explorer

`GET /v2/buscar` combines `q`, `operacion`, `tipo`, `moneda`,
`precio_min`, `precio_max`, `area`, `nivel`, `provincia`, `departamento`,
`municipio`, `localidad`, `barrio`, `ambientes`, `dormitorios`, `banos` and
`superficie_min`.

`nivel` is one of `PROVINCIA`, `DEPARTAMENTO`, `MUNICIPIO`, `LOCALIDAD` or
`SIN_AREA`. Since discovery does not currently publish IDs for every area,
`nivel + area` is the stable executable fallback. Neighborhood text remains
non-canonical.

`sort` is `relevance`, `price_asc` or `price_desc`. Relevance uses
`eretz_ranking_tecnico_v1` and retains the offset ceiling of 200. Price sorts
require `moneda`, do not expose ranking scores, and support stable deep offset
pagination. There is no `recent` sort because the snapshot has no contractual
publication timestamp. Unsupported enum values return 400/422; they never
fall back silently.

Response fields are `contrato`, nullable `ranking`, `sort`, nullable
`consulta`, `total`, `limit`, `offset`, and `data`. `total` is never truncated
to the ranked window.

## Viewport map

`GET /v2/propiedades/mapa` requires `north`, `south`, `east`, `west`, accepts
the same search/filter fields as Explorer, and returns only valid non-zero
coordinates inside the viewport. The response distinguishes `total_matches`,
`viewport_matches`, `returned_points`, `truncated`, `limit`, and `data`.

Decision: viewport-limited points plus existing frontend Leaflet clustering.
The hard response maximum remains 5,000 and the recommended default is 2,000;
the backend never sends the whole national inventory.

## Detail and identity

`GET /v2/propiedades/{id}` first resolves the canonical API ID (the stable
`hash_dedup`-derived identifier). It then consults the optional
`property_aliases` table for historical/public identifiers. Aliases must come
from a verified export; the API never guesses them from URLs or hashes.

Use `scripts/prepare_api_v2_snapshot.py SOURCE OUTPUT --aliases aliases.csv`
to create an indexed derived snapshot without modifying its source. Until a
verified legacy-ID export is supplied, canonical IDs work and numeric legacy
URLs remain an explicit data blocker.

## Agency and contact display

`GET /v2/agencias/{agency_id}` returns the canonical agency ID, its normalized
public label, nullable logo/website, and a separate contact object. Current
snapshot data has no verified public contact fields, therefore status is
`UNAVAILABLE` and phone/WhatsApp/email are null. There is no contact-action
endpoint: creating a CRM or accepting messages without delivery infrastructure
would be a false contract.

## Batch lookup

`POST /v2/propiedades/batch` accepts `{ "ids": [...] }`, at most 100 entries.
Blank/oversized IDs are rejected. Duplicates are removed using first-occurrence
order. `items` preserves that order, `missing_ids` is explicit, and
`requested_ids` contains the normalized unique request. Canonical IDs and
verified aliases use one set query each; there is no N+1 lookup.

## Errors and schema

FastAPI publishes request constraints and response models in `/openapi.json`.
Validation is 422; semantically invalid combinations are 400; a missing
property/agency is 404; missing or obsolete snapshots are 503. A 503 is never
converted to 404 or an empty success.

## Measured snapshot performance

Windows/SQLite, 58,427-property snapshot, warm median of three calls after
preparing the derived indexes: combined ranked Explorer 464 ms, combined price
sort 779 ms, national viewport map 70 ms for 1,232 points, batch of 100 IDs
13 ms, and detail 0.8 ms. Map improved from roughly 1.4 s without the viewport
indexes. Measurements are local baselines, not production SLOs.
