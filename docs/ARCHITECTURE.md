# Architecture

ERETZ is a read-oriented property portal backed by Supabase. Pipeline A
discovers and parses listings, stages run state in `internal_scraping`, and
publishes approved records to `public.propiedades`. The public Next.js
application reads only active (`activa`) properties through the anon role.

Trust boundaries:

- scraper and operational scripts: service-role access, never shipped;
- `internal_scraping`: operational data, no anon/authenticated access;
- `public.propiedades`: the sole approved public relation, read-only for API
  roles and filtered by RLS;
- frontend: untrusted public client using only the anon key;
- external listing sites: untrusted network input routed through the outbound
  URL/TLS policy.

Neon tooling is legacy and must not be used for production writes.

