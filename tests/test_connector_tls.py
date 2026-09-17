import ssl
from types import SimpleNamespace

import pytest

from connectors.base import Descargador, ErrorTransitorio
from connectors.formularios import bajar_formulario


@pytest.mark.parametrize('method', ['get', 'form'])
def test_connectors_verify_tls_and_do_not_fallback_on_certificate_error(monkeypatch, method):
    contexts = []
    def fail(request, *, timeout, context):
        contexts.append(context)
        raise ssl.SSLCertVerificationError('invalid certificate')
    monkeypatch.setattr('urllib.request.urlopen', fail)
    downloader = Descargador(limitador=SimpleNamespace(esperar=lambda host: None), reintentos=1)
    with pytest.raises(ErrorTransitorio):
        if method == 'get':
            downloader.bajar('https://official.test/p/123')
        else:
            bajar_formulario(downloader, 'https://official.test/catalog', {'pagina': 1})
    assert len(contexts) == 1
    assert contexts[0].verify_mode == ssl.CERT_REQUIRED
    assert contexts[0].check_hostname is True
