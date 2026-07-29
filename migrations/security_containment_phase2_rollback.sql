-- Explicit rollback for security_containment_phase2.sql.
-- Execute only after a human confirms the wider historical exposure is desired.

BEGIN;

GRANT ALL PRIVILEGES ON public.propiedades TO anon, authenticated;

ALTER POLICY propiedades_public_read ON public.propiedades
TO anon
USING (true);

-- Exact historical grants are preserved in:
-- _scratch/backend_final_closure/SUPABASE_AUDIT/grants.csv
-- Restore a relation only from that closed evidence set; this rollback does
-- not broadly re-expose every public relation automatically.

RESET search_path;

COMMIT;

