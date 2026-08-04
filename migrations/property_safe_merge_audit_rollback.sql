-- Non-destructive rollback for Pipeline A safe merge.
-- It disables API access but intentionally leaves audit evidence and routines
-- in place.  The application flag must also remain disabled.

BEGIN;

REVOKE EXECUTE ON FUNCTION public.record_property_merge_audit(bigint, text, text, jsonb)
    FROM PUBLIC, anon, authenticated, service_role;
REVOKE EXECUTE ON FUNCTION public.insert_property_safe(jsonb, text, text, jsonb)
    FROM PUBLIC, anon, authenticated, service_role;
REVOKE EXECUTE ON FUNCTION public.apply_property_safe_merge(
    bigint, bigint, text, text, text, jsonb, text, text, jsonb
) FROM PUBLIC, anon, authenticated, service_role;
REVOKE ALL ON public.property_merge_audit
    FROM PUBLIC, anon, authenticated, service_role;
REVOKE ALL ON SEQUENCE public.property_merge_audit_id_seq
    FROM PUBLIC, anon, authenticated, service_role;

COMMENT ON TABLE public.property_merge_audit IS
    'DISABLED by property_safe_merge_audit_rollback.sql; retained as immutable operational evidence.';

COMMIT;
