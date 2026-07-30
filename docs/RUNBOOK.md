# Operations runbook

1. Confirm the workspace, branch, clean scope, environment, and expected
   Supabase project.
2. Review the previous run ledger and recover interrupted work.
3. Run tests and read-only preflights.
4. Start a uniquely identified canary with at most two browser workers.
5. Stop on internal errors, unexpected writes, credential exposure, or
   property-count drift.
6. For an authorized run, persist checkpoints and classify every source.
7. Reconcile before/after counts, duplicate groups, RLS/grants, and run items.
8. Archive sanitized evidence and document rollback.

Never deactivate properties, reset a database, run Pipeline B, write to Neon,
push, deploy, or publish without explicit authorization.

