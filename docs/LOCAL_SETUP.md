# Local setup

Use Python 3.11 and Node 22.

```text
python -m venv .venv
.venv/Scripts/python -m pip install --require-hashes -r requirements.lock
cd frontend
npm ci
```

Copy example environment files locally and provide only development
credentials. Never commit `.env` files. Playwright browsers are installed only
when a browser-backed test is required.

