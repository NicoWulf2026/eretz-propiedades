---
paths:
  - "supabase/**"
  - "migrations/**"
  - "**/*.sql"
  - "scripts/*supabase*"
  - "scripts/*writer*"
---
# Base de datos

- Nada muta producción de forma automática: ni INSERT/UPDATE/DELETE, ni migraciones, ni RLS/grants,
  ni restore. Se prepara, se verifica local y se anota en `docs/agent/READY_FOR_PRODUCTION_ACTION.md`.
- El acceso MCP a Supabase es de solo lectura por decisión; no usar `execute_sql` ni
  `apply_migration` para escribir.
- Migraciones: aditivas, con su `_rollback.sql`, verificadas en PostgreSQL/WASM desechable
  (`scripts/verify_writer_equivalence.mjs`, `scripts/verify_local_postgres.mjs`). Orden en
  `supabase/MIGRATION_ORDER.md`.
- Único camino de escritura aceptado: el RPC `apply_property_safe_merge` (lista blanca de campos,
  identidad verificada, auditoría en la misma transacción). El REST directo está bloqueado.
- Sin `pg_dump` con restore probado, ningún write productivo es reversible
  (`BLOCKED_EXTERNAL_CREDENTIAL` mientras falte la credencial directa).
