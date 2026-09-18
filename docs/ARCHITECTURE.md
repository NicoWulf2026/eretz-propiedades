# Architecture

ERETZ is a read-oriented property portal. In the isolated unification candidate,
connectors enumerate official agency inventories and normalize real properties;
certification records inventory completeness separately from data correctness.
Verified artifacts feed pre-ingestion, geographic validation and a derived,
indexed SQLite catalog served by FastAPI v2. The Next.js F7 frontend consumes
that API through runtime schemas, adapters and domain models.

The production publication path still uses Supabase: raw and staging in
`internal_scraping`, then approved records in `public.propiedades`. The local
API snapshot is derived evidence, not an alternate production source of truth.
No production publication was performed during unification.

Trust boundaries:

- scraper and operational scripts: server-only credentials, never shipped;
- `internal_scraping`: operational data, no anon/authenticated access;
- `public.propiedades`: the sole approved public relation, read-only for API
  roles and filtered by RLS;
- frontend public catalog: Next → API v2; bounded legacy reads remain for numeric
  historical IDs while the populated identity crosswalk is unavailable;
- professional directories, claims/reports and writes: separate existing
  boundaries, not silently replaced by property snapshot data;
- external listing sites: untrusted network input routed through the outbound
  URL/TLS policy.

Neon tooling is legacy and must not be used for production writes.

Compatibility entrypoints remain where actual consumers exist:
`run_daily_pipeline.py` uses raw/staging publication;
`run_manifest.py` uses the historical Playwright runner and audited merge RPCs;
agency queues use `connectors` and certification. Shared URL discovery,
identity models and network policy are centralized. Removing an entrypoint
requires consumer and behavior evidence; the candidate is still under audit.
See `ERETZ_UNIFICATION_EVIDENCE.md` for measured results and unresolved gaps.
