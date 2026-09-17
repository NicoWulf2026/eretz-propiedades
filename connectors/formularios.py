"""POST de formularios legacy con las mismas guardas de red del connector.

Se mantiene separado de ``base.py`` porque sólo una familia de sitios propios
lo necesita. Así, agregar o corregir ese contrato no invalida connectors que
jamás ejecutan formularios (Tokko, Wasi, WordPress).
"""
from __future__ import annotations

import random
import re
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from .base import Bloqueado, Descargador, ErrorPermanente, ErrorTransitorio
from scraper.network_security import secure_urlopen, read_bounded_response


def bajar_formulario(descargador: Descargador, url: str,
                     formulario: dict[str, Any],
                     limite_bytes: int = 8_000_000) -> str:
    """Envía un formulario oficial respetando ritmo, backoff y contadores."""
    override = getattr(descargador, "bajar_formulario", None)
    if callable(override):
        return override(url, formulario, limite_bytes)

    safe_url = descargador.url_segura(url)
    host = urllib.parse.urlparse(safe_url).netloc.lower()
    body = urllib.parse.urlencode(formulario, doseq=True).encode("utf-8")
    delay = 2.0
    last_error: Exception | None = None
    for attempt in range(1, descargador.reintentos + 1):
        descargador.limitador.esperar(host)
        try:
            context = ssl.create_default_context()
            request = urllib.request.Request(safe_url, data=body, headers={
                "User-Agent": descargador.UA,
                "Accept-Encoding": "gzip",
                "Accept": "application/json,text/plain,*/*",
                "Content-Type": "application/x-www-form-urlencoded",
            })
            with descargador._lock:
                descargador.pedidos += 1
            with secure_urlopen(
                    request, timeout=descargador.timeout, context=context) as response:
                raw = read_bounded_response(response, limite_bytes)
                charset = "utf-8"
                match = re.search(
                    r"charset=([\w-]+)",
                    response.headers.get("Content-Type") or "", re.I)
                if match:
                    charset = match.group(1)
                with descargador._lock:
                    descargador.bytes_bajados += len(raw)
                    descargador._hosts_leidos.add(host)
                return raw.decode(charset, "ignore")
        except urllib.error.HTTPError as error:
            if error.code in (403, 429):
                raise Bloqueado(f"http {error.code}") from None
            if error.code in (404, 410):
                raise ErrorPermanente(f"http {error.code}") from None
            last_error = ErrorTransitorio(f"http {error.code}")
        except Exception as error:
            last_error = ErrorTransitorio(type(error).__name__)
        if attempt < descargador.reintentos:
            time.sleep(delay + random.uniform(0, 0.5))
            delay *= 2
    raise last_error or ErrorTransitorio("sin respuesta")
