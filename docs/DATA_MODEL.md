# Data model

`public.propiedades` is the canonical public inventory. Its public lifecycle
state is `activa`; other states are not public. `inmobiliaria_id` links a
property to the canonical agency identity. The source URL and its normalized
form drive deduplication; URL normalization must never merge records solely on
weak text similarity.

`public.inmobiliarias_main` contains canonical agencies.
`internal_scraping.scraping_runs`, run items, staging, queues, and error logs
are operational records. Backup and deprecated tables are not application
contracts and are inaccessible to public API roles.

Quality flags are derived evidence. Missing source data and internally
correctable corruption are different categories and must not be conflated.

