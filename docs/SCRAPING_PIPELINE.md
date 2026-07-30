# Scraping pipeline

Pipeline A is the only production path. A source is selected from the
versioned manifest, fetched with TLS verification and SSRF controls, parsed,
validated, deduplicated, staged, and only then published by an explicitly
authorized run.

Every run needs a unique run ID, immutable source ledger, per-source terminal
status, resumable checkpoint, error classification, and before/after counts.
Browser concurrency is capped at two. Canaries are read-only by default.

Internal parser/configuration errors block a general run. DNS, remote HTTP,
anti-bot, removed sources, and genuinely missing source fields remain external
categories and must retain evidence.

