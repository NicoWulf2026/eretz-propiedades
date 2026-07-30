# Security

Only the public Supabase anon key may reach the browser. Service-role,
database, proxy, provider, and scraper credentials belong in the deployment
secret manager and local untracked environment files.

All untrusted outbound URLs use `scraper.network_security`: HTTP(S) only,
credential-free URLs, public DNS/IP destinations, manual bounded redirects,
mandatory certificate verification, bounded response size, and sanitized
errors. Do not introduce `verify=False` or urllib3 warning suppression.

Credential exposure response: contain the affected source, rotate/revoke at
the provider, replace the secret in every authorized store, invalidate caches,
scan history/artifacts, run a canary, and record the incident without copying
the secret.

