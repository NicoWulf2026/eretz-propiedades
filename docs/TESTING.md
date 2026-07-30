# Testing

Backend:

```text
python -m compileall -q scraper scripts api tests
python -m pytest -q
mypy
ruff check scraper/network_security.py tests/test_network_security.py
python -m pip_audit -r requirements.lock --progress-spinner off
```

Frontend:

```text
cd frontend
npm run lint
npm run typecheck
npm test
npm run build
npm audit --audit-level=high
```

The narrow Ruff gate protects newly hardened security code; the legacy codebase
still has a separately tracked lint backlog. A clean database reconstruction
test requires local Supabase/PostgreSQL tooling.

