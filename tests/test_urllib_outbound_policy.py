import gzip
import io
import ssl
from types import SimpleNamespace
import urllib.request

import pytest

from scraper.network_security import (OutboundResponseError, OutboundSecurityError,
                                      SafeRedirectHandler, UnsafeOutboundUrl,
                                      read_bounded_response, secure_urlopen)


@pytest.mark.parametrize('url', ['http://127.0.0.1/p', 'http://169.254.169.254/latest/',
                               'file:///secret', 'https://user:pass@public.test/p'])
def test_urllib_blocks_unsafe_initial_destination_without_opening(monkeypatch, url):
    opened = []
    monkeypatch.setattr('urllib.request.build_opener', lambda *args: opened.append(args))
    with pytest.raises(UnsafeOutboundUrl):
        secure_urlopen(url, timeout=1)
    assert opened == []


def test_redirect_to_private_destination_is_rejected():
    req = urllib.request.Request('https://official.test/p')
    with pytest.raises(UnsafeOutboundUrl):
        SafeRedirectHandler().redirect_request(req, None, 302, 'Found', {},
                                              'http://127.0.0.1/admin')


def test_cannot_disable_tls_even_via_context(monkeypatch):
    monkeypatch.setattr('scraper.network_security.validate_outbound_url', lambda url: url)
    context = ssl._create_unverified_context()
    with pytest.raises(OutboundSecurityError):
        secure_urlopen('https://official.test', timeout=1, context=context)


def response(body, encoding=''):
    return SimpleNamespace(read=io.BytesIO(body).read, headers={'Content-Encoding': encoding})


def test_size_cap_is_an_error_not_a_partial_success():
    with pytest.raises(OutboundResponseError):
        read_bounded_response(response(b'123456'), 5)
    assert read_bounded_response(response(b'12345'), 5) == b'12345'


def test_gzip_expansion_and_truncation_are_bounded():
    with pytest.raises(OutboundResponseError):
        read_bounded_response(response(gzip.compress(b'x' * 10000), 'gzip'), 100)
    with pytest.raises(OutboundResponseError):
        read_bounded_response(response(gzip.compress(b'valid')[:-2], 'gzip'), 100)
    assert read_bounded_response(response(gzip.compress(b'valid'), 'gzip'), 100) == b'valid'
