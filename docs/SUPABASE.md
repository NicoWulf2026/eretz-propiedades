# Supabase

Production uses Supabase only. Application schemas are `public` and
`internal_scraping`; temporary and extension schemas are platform-owned.
The frontend is limited to `SELECT` on `public.propiedades`, with RLS exposing
only `estado = 'activa'`.

Schema changes live in `supabase/migrations/`. The historical scripts under
`migrations/` are an audited legacy sequence, not a safe replay mechanism.
Never reset production. Before applying a migration, capture schema and data
backups, test on a disposable environment, review the diff, and execute the
migration validation block.

