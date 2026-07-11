"""Seguridad: la Tokko API key nunca debe aparecer en logs/errores.

Verifica _redact_secrets() en scraper/scraper_propiedades.py con una key FICTICIA.
NUNCA usar la key real.
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scraper"))

import scraper_propiedades as sp  # noqa: E402

FAKE_KEY = "FAKEKEY_1234567890abcdefABCDEF"


def test_redact_url_query_key():
    url = f"https://api.tokkobroker.com/api/v1/property/?key={FAKE_KEY}&limit=20&format=json"
    out = sp._redact_secrets(url)
    assert FAKE_KEY not in out
    assert "key=<redacted>" in out
    # el resto de la URL se conserva para debugging
    assert "limit=20" in out


def test_redact_detail_url():
    url = f"https://api.tokkobroker.com/api/v1/property/12345/?key={FAKE_KEY}&format=json&lang=es"
    out = sp._redact_secrets(url)
    assert FAKE_KEY not in out
    assert "key=<redacted>" in out


def test_redact_requests_httperror_message():
    # Simula el str() de una requests.HTTPError que incluye la URL con la key
    msg = (
        "403 Client Error: Forbidden for url: "
        f"https://api.tokkobroker.com/api/v1/property/?key={FAKE_KEY}&limit=20"
    )
    out = sp._redact_secrets(msg)
    assert FAKE_KEY not in out
    assert "<redacted>" in out


def test_redact_none_and_empty():
    assert sp._redact_secrets(None) == ""
    assert sp._redact_secrets("") == ""


def test_redact_variants_apikey_token():
    for k in ("apikey", "api_key", "token", "access_token", "secret", "password"):
        url = f"https://x/y?{k}={FAKE_KEY}&z=1"
        out = sp._redact_secrets(url)
        assert FAKE_KEY not in out, f"no redacto {k}"
