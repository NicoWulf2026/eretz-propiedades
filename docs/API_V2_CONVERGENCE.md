# ERETZ API v2 Frontend Convergence

## Source of Truth

Frontend base: `feat/eretz-frontend-phase-a` at `04e63a2895`. API v2 does not exist in that checkout; its verified implementation is `api/v2.py` and `api/ranking.py` in worktree `D:\INMO CAPITAL\Inmo-Capital-main`, commit `79afe12e` (2026-09-06). Backend source and snapshot were read only. No committed OpenAPI/schema DTO was found.

Contract/version: `eretz_api_property_v1`; technical ranking: `eretz_ranking_tecnico_v1`. The current source is nine read-only GET endpoints over the real 58,427-row snapshot.

## API v2 Endpoint Matrix

| Endpoint | Method | Purpose | Request | Response | Nullability | Frontend use | Status |
|---|---|---|---|---|---|---|---|
| `/v2/propiedades` | GET | Filtered list | operation/type/currency/price/typed area/locality/neighborhood/agency/rooms/bedrooms + limit/offset | contract, total, limit, offset, property DTOs | Property fields nullable | Future filtered list | PARTIAL: no explicit sort |
| `/v2/propiedades/mapa` | GET | Coordinate rows | operation/type/limit | total + raw coordinate items | Core values nullable; coordinates selected non-null | Future map input | INCOMPATIBLE with current viewport/cluster API |
| `/v2/propiedades/{id}` | GET | Detail | id | property DTO; 404 missing | Many property fields nullable | Detail | READY for property data; contact absent |
| `/v2/areas` | GET | Typed search areas | q/limit | level/name/count | name is filtered non-null | Area autocomplete/facets | READY |
| `/v2/barrios` | GET | Source neighborhoods | q/limit | `canonizado:false`, name/count | name filtered non-null | Neighborhood suggestions | READY with non-canonical warning |
| `/v2/filtros` | GET | Real facets/coverage | none | values/counts, price ranges, `sin_dato` | Explicit missing counts | Filter catalog | READY |
| `/v2/sugerencias` | GET | Area/neighborhood suggestions | q min length 2, limit | type/level/name/count | level null for neighborhood | Autocomplete | READY; current UI DTO differs |
| `/v2/buscar` | GET | FTS + technical ranking | q/operation/type/limit/offset | ranked page + ranking version | Incomplete properties remain | Default search | PARTIAL: filter set narrower than list |
| `/v2/stats` | GET | Dataset facts | none | totals/geography/write count | N/A | Diagnostics only | READY |

FastAPI standard errors observed from source/tests: 404 for missing property; 422 for invalid query parameters; 503 for missing/old snapshot; other failures are 5xx. Response bodies use FastAPI `detail`, but the frontend error model relies on status rather than undocumented message text.

## DTO vs Domain Boundary

- `frontend/src/lib/api-v2/dto.ts`: wire names and exact v2 shapes.
- `frontend/src/lib/api-v2/schemas.ts`: dependency-free runtime validation at the external boundary.
- `frontend/src/domain/catalog-property.ts`: semantic property/geography/ranking model.
- `frontend/src/domain/catalog-search.ts`: UI-independent sort and page model.
- `frontend/src/lib/api-v2/adapters.ts`: the only DTO-to-domain translation.
- Existing `src/types/property.ts::Property` remains the legacy presentation model; no visual component was migrated in this phase.

Unknown operation/type/currency strings are retained as `raw*` and normalize to `null`; they are never invented as `consultar`/`otro`. API v2 currently requires `agency_id` and `source_url`; agency details/contact remain absent.

## Geography Semantics

Domain geography preserves separate locality, municipality, department, province and neighborhood values. `searchArea` always retains `level`, `name`, `id` and `origin`. `MUNICIPIO` never populates locality. Locality provenance is `CANONICAL_NORMALIZED` or `UNKNOWN`; geography conflict is explicit.

## Null / Zero Semantics

Adapters preserve `null`, `0` and `""` without truthiness conversion. Missing coordinates remain `null,null`; the map predicate requires both values and never substitutes `0,0`. The legacy mapper was narrowly corrected from positive-only to non-negative field parsing so its domain no longer drops real zeros.

## Pagination

The domain exposes page/pageSize. `catalogPaginationToOffset` maps it to v2 `limit/offset`; page responses map back to page/hasPrevious/hasNext. No cursor is required from the backend. Existing explorer cursor cutover remains future work.

## Ranking / Sorting

`technical_relevance` maps only to `/v2/buscar` and preserves `eretz_ranking_tecnico_v1` plus score parts. User-selected `recent`, `price_asc`, `price_desc` are distinct domain values. They currently fail as unsupported before the network because v2 exposes no explicit sort parameter. The frontend does not create a parallel ranking or use price as relevance.

## Error Model

`ApiV2Result<T>` distinguishes `SUCCESS`, `SUCCESS_EMPTY`, `PARTIAL_DATA` and `FAILURE`. Failures distinguish `NOT_FOUND`, `BAD_REQUEST`, `NETWORK_ERROR`, `TIMEOUT`, `SERVER_ERROR`, `INVALID_RESPONSE`, and `UNCONFIGURED`. Invalid rows in an otherwise valid page are reported as partial data with paths; malformed detail is invalid response, never 404 or an empty object.

## Legacy PostgreSQL Migration Matrix

| Legacy data path | Used by | API v2 replacement | Ready to migrate | Blocker |
|---|---|---|---|---|
| `searchProperties` | `/api/properties/search`, counts, home | `/v2/buscar` + `/v2/propiedades` | NO | Split filter/search contracts; sort; cursor cutover |
| `searchMap` | `/api/properties/map` | `/v2/propiedades/mapa` | NO | No viewport, clusters, confidence or compatible counts |
| `searchSuggestions` | suggestions route | `/v2/sugerencias`, `/v2/areas`, `/v2/barrios` | YES: CUT OVER | None for autocomplete; legacy function remains isolated and unused |
| `getPropertyById` | property detail | `/v2/propiedades/{id}` | PARTIAL | Contact/agency details and presentation mapping absent |
| `getPropertiesByIds` | favorites/compare/collections | Repeated detail or future batch endpoint | NO | No v2 batch endpoint |
| Agency directory/profile/inventory | professional routes, claims | None complete | NO | Agency/contact/profile contract missing |
| Related/duplicates/history | detail | None | NO | No v2 endpoints |
| `db-writer` claims/reports | mutations | Out of read-only v2 | NO | Separate backend mutation contract required |

## Backend Contract Gaps

### Verified contract mismatches

FRONTEND_EXPECTS: one explorer request combining text, geography, price, rooms, bedrooms, bathrooms, surface and explicit sort.<br>
BACKEND_PROVIDES: ranked `/v2/buscar` with q/operation/type, plus separately filtered `/v2/propiedades` without explicit sort.<br>
MISMATCH: neither endpoint represents the complete explorer query.<br>
CAN_FRONTEND_ADAPT_SAFELY: NO; the adapter can only reject unsupported combinations.<br>
PROPOSED_CONTRACT: document a combined filter set and explicit user sorts on ranked search.

FRONTEND_EXPECTS: viewport-aware map rows with stable visible/scanned/truncated semantics.<br>
BACKEND_PROVIDES: up to 5,000 raw coordinate rows filtered only by operation/type.<br>
MISMATCH: current map pagination and clustering semantics cannot be preserved.<br>
CAN_FRONTEND_ADAPT_SAFELY: NO.<br>
PROPOSED_CONTRACT: add bounds and documented total/truncation semantics, then decide clustering ownership.

FRONTEND_EXPECTS: property detail with agency/contact data and saved-id batch reads.<br>
BACKEND_PROVIDES: `agency_id`, `source_url` and single-property detail only.<br>
MISMATCH: contact, agency profile and bounded batch lookup data do not exist.<br>
CAN_FRONTEND_ADAPT_SAFELY: NO.<br>
PROPOSED_CONTRACT: public agency/contact lookup plus a batch-id endpoint with per-id missing/error results.

### Contact and agency

BACKEND_DEPENDENCY: public agency/contact lookup tied to `agency_id`.<br>
WHY_FRONTEND_NEEDS_IT: detail and professional profiles expose direct contact.<br>
CURRENT_API_V2: property has `agency_id` and `source_url` only.<br>
MINIMUM_REQUIRED_CONTRACT: authoritative agency id/name plus optional phone, email, website and verification/provenance.<br>
CAN_FRONTEND_PROCEED_WITHOUT_IT: YES for property/search foundation; NO for detail/contact cutover.<br>
TEMPORARY_FRONTEND_BEHAVIOR: leave optional domain extension absent; keep legacy screens unchanged.

### Map

BACKEND_DEPENDENCY: viewport-aware map contract or explicit approval for server-side clustering adapter.<br>
WHY_FRONTEND_NEEDS_IT: existing map requests bounds/zoom and distinguishes visible/scanned/truncated points.<br>
CURRENT_API_V2: operation/type plus capped raw coordinates.<br>
MINIMUM_REQUIRED_CONTRACT: bounds, stable total semantics, coordinate validity/conflict and documented truncation; clustering ownership must be explicit.<br>
CAN_FRONTEND_PROCEED_WITHOUT_IT: YES for list/detail foundation; NO for map cutover.<br>
TEMPORARY_FRONTEND_BEHAVIOR: keep Leaflet and legacy map route untouched.

### Search filters and sorting

BACKEND_DEPENDENCY: one documented composition for ranked text search plus supported filters and explicit user sorts.<br>
WHY_FRONTEND_NEEDS_IT: the explorer combines these in one URL/result set.<br>
CURRENT_API_V2: `/buscar` ranks but accepts only q/operation/type; `/propiedades` filters more but has no sort parameter.<br>
MINIMUM_REQUIRED_CONTRACT: declare supported combinations and explicit sort values; preserve technical ranking as default.<br>
CAN_FRONTEND_PROCEED_WITHOUT_IT: YES for limited default search; NO for explorer cutover.<br>
TEMPORARY_FRONTEND_BEHAVIOR: reject unsupported combinations in the new adapter; never pretend they were applied.

### Saved ids, related data and history

BACKEND_DEPENDENCY: batch property lookup and decisions for duplicates/related/history.<br>
WHY_FRONTEND_NEEDS_IT: favorites/compare/collections/detail use them.<br>
CURRENT_API_V2: single detail only.<br>
MINIMUM_REQUIRED_CONTRACT: batch ids with per-id missing/error semantics; separate optional related/history endpoints if retained for beta.<br>
CAN_FRONTEND_PROCEED_WITHOUT_IT: YES for search foundation; NO for full legacy cutover.<br>
TEMPORARY_FRONTEND_BEHAVIOR: retain legacy reads; do not fan out unbounded detail calls.

## Implemented in This Phase

- Typed DTOs for the verified endpoint shapes.
- Runtime validation for core property/detail/search pages.
- Catalog property/search domain with typed geography and ranking.
- Null/zero-safe property adapters and legacy mapper correction.
- Page-to-offset pagination adapter.
- Server-only, environment-configured fetch client with abort/timeout/error semantics.
- API DTO fixture matrix and contract/client tests.
- `ERETZ_API_V2_BASE_URL` documented in `.env.local.example`.

## Remaining Cutover Work

1. Obtain backend decisions for combined search/filter/sort, contact/agency, map and batch ids.
2. Add runtime validators/client methods for non-core area/facet/suggestion/map DTOs as each UI cutover starts.
3. Adapt the existing presentation `Property` without discarding v2 geography or null/zero meaning.
4. Migrate internal Next routes one at a time, keeping their browser contracts stable where useful.
5. Replace false-zero/404 fallbacks in UI services with `ApiV2Result` states.
6. Repeat real-data and desktop browser acceptance against the configured preview before promotion.

## First Production Cutover

### Flows migrated

| Flow | Legacy | API v2 | Cutover status |
|---|---|---|---|
| Autocomplete / suggestions | `property-db-service.searchSuggestions` | `/v2/sugerencias` through the server-only discovery facade | API_V2 |
| Areas | Direct PostgreSQL-derived location text | `/v2/areas` validated and adapted | API_V2_INFRASTRUCTURE |
| Neighborhoods | Direct source rows | `/v2/barrios` with `canonizado:false` preserved | API_V2_INFRASTRUCTURE |
| Filter metadata | Static/legacy catalog assumptions | `/v2/filtros` validated, adapted and exposed through the existing controls | API_V2 |
| Explorer results | PostgreSQL | Not cut over | LEGACY |
| Map | PostgreSQL | Not cut over | LEGACY |
| Detail/contact | PostgreSQL | Not cut over | LEGACY / BLOCKED |

There is no PostgreSQL fallback in the migrated autocomplete route. API failures remain typed failures and the UI distinguishes them from a successful empty response.

The legacy property-detail loader now also preserves absence versus infrastructure failure. A malformed, hidden or genuinely absent numeric id remains `NOT_FOUND`; missing database configuration, a disabled/unavailable quality gate or a failed query returns `UNAVAILABLE`. The property route renders an explicit, no-index temporary-service state for the latter instead of emitting a false 404. This corrects the lifecycle/error contract without changing the legacy detail data source while API v2 identifiers and fields remain blocked.

The legacy bounded batch read used by favorites, collections and comparison follows the same rule: an empty valid id set or ids that are no longer visible can produce a successful empty collection, while missing database/gate infrastructure and query failures return HTTP 503 with `no-store`. Existing clients already render that response as a recoverable error, so an outage no longer claims that every saved listing disappeared.

The legacy Explorer search and count routes likewise preserve their existing browser payloads but now return HTTP 503 with `no-store` when the service reports an error or the public gate is unavailable. Their existing consumers already convert non-success responses into recoverable result/count error states; failures are no longer cached as successful empty inventory or unknown counts.

Filter metadata is now loaded once by the Explorer through the internal server route. Existing operation, property-type and currency controls remain structurally unchanged; when API v2 reports a matching facet, its real catalog count is appended without changing the submitted legacy value. Unsupported legacy controls remain visible as required. Metadata failure, partial data and valid empty data are distinct UI states and never disable search execution.

### Filter compatibility

| Classification | Current controls/data |
|---|---|
| SUPPORTED_NOW | Operation, property type, currency, price range, typed area/locality/neighborhood, agency id, rooms and bedrooms |
| DISPLAY_ONLY_LEGACY | Existing filter controls remain backed by the legacy result flow until Explorer is migrated |
| BLOCKED_BY_BACKEND | Bathrooms, surfaces, garages, mortgage state, media, recency, publisher text and user-selected sort |
| UNUSED | `/v2/filtros.sin_dato` is retained as coverage metadata but does not remove or add controls in this phase |

### Validation and partial-data policy

The response envelope and contract version are response-level invariants: if either is malformed, the response is `INVALID_RESPONSE`. Collection items are validated independently for areas, neighborhoods, suggestions and property pages. Invalid items are omitted, their exact paths are reported, and valid siblings return as `PARTIAL_DATA`. `PARTIAL_DATA` with zero usable autocomplete items is rendered as a recoverable error, never as an empty result.

`agency_id` remains required for an individual property. Evidence: the current snapshot table declares `agency_id text not null`; all 58,427 rows have a non-null, non-empty column value; all 58,427 stored property documents contain a non-empty string; and backend tests construct the same non-null schema. This is a strong current implementation invariant, but it is not formally guaranteed by a committed OpenAPI/response model because API v2 returns raw dictionaries. A single missing `agency_id` invalidates that item, not its page: nine valid siblings plus one invalid item produce nine properties and `PARTIAL_DATA`.

### URL geography preservation

Selections add `area_nivel` and `area_nombre` (plus `area_id` when a future backend supplies one). Municipality, department and locality selections use the existing generic `ubicaciones` parameter for legacy result compatibility and never populate `ciudad`. Province keeps the existing `provincia` parameter. Neighborhoods retain `barrio_canonico=0`. These typed parameters round-trip through the existing filter serializer but do not claim that legacy Explorer execution understands the new hierarchy.

### Base URL strategy

- Local development: start the read-only API locally and set `ERETZ_API_V2_BASE_URL=http://127.0.0.1:<port>` only in the Next.js server process.
- Tests: inject `baseUrl` and `fetchImpl`; real smoke uses `ERETZ_API_V2_SMOKE_URL`.
- Preview: configure `ERETZ_API_V2_BASE_URL` as a server environment variable. It is not secret, but it must never use `NEXT_PUBLIC_` because browser calls go through the internal route.

### Real smoke and browser QA

After an unrelated snapshot regeneration released its SQLite lock, the real frontend client passed against the 58,427-row snapshot: `/v2/areas` HTTP 200/SUCCESS with 10 adapted items in about 144 ms; `/v2/barrios` 200/SUCCESS with 20 items in about 542 ms; `/v2/sugerencias` 200/SUCCESS with 8 items in about 473 ms; `/v2/filtros` 200/SUCCESS with one adapted metadata object in about 608 ms. Times are single local observations, not benchmarks.

Focused Playwright QA passed 7/7 against the real local API at 1440, 1366 and 1280 px. It covered accented and partial queries, province/locality/municipality labels, real internal network requests, no Supabase browser requests, empty versus failure feedback, keyboard and mouse selection, Escape/reopen, re-query after selection, non-canonical neighborhoods, typed URL persistence, filter-count enrichment, metadata failure fallback and console errors. The home does not currently use this autocomplete, so its discovery flow was not changed.

### Remaining blockers

Explorer still needs a combined ranked search/filter/sort contract. Map still needs viewport, stable total/truncation semantics and a clustering decision. Detail still needs agency/contact data. Filter metadata enriches existing choices with catalog counts but intentionally does not add, remove or disable controls until result execution can honor the same contract.

The detail cutover also needs an identifier bridge: current public routes use numeric PostgreSQL ids, while the local API snapshot exposes `hash_dedup` identifiers. The API detail payload lacks address, expenses, lifecycle timestamps/status, amenities and contact/publisher data used by the existing page. Cutting over before those contracts converge would silently degrade the current product.
