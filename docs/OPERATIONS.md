# Operational safety

Operational scripts must default to dry-run, require explicit execution flags
for writes, cap concurrency and retries, sanitize errors, and emit a durable
ledger. Every write path must identify the database, schema, table, run ID,
maximum scope, and rollback evidence before execution.

Generated audits belong under `_scratch/` and are not versioned. Production
exports, screenshots with customer data, provider URLs containing keys, and
raw response bodies are never committed.

