# Contributing

Use Python 3.11 and Node 22. Install backend dependencies from
`requirements.lock` with hashes, and frontend dependencies with `npm ci`.

Before opening a change, run:

```text
python -m pytest -q
mypy
ruff check scraper/network_security.py tests/test_network_security.py
cd frontend
npm run lint
npm run typecheck
npm test
npm run build
```

Never commit secrets, production exports, `.env` files, property payloads, or
credential-bearing URLs. Database changes require an additive timestamped
migration, a backup plan, a validation block, and an explicit production
approval. Scraper canaries must be read-only unless the run is separately
authorized.

