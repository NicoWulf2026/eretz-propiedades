from __future__ import annotations

import socket

import pytest
import requests

from scraper.network_security import (
    OutboundResponseError,
    OutboundSecurityError,
    UnsafeOutboundUrl,
    secure_get,
    validate_outbound_url,
)


def public_resolver(host: str, port: int):
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port))]


def private_resolver(host: str, port: int):
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.1.2.3", port))]


class FakeRequester:
    def __init__(self, responses: list[requests.Response]):
        self.responses = list(responses)
        self.calls: list[tuple[str, dict[str, object]]] = []

    def get(self, url: str, **kwargs):
        self.calls.append((url, kwargs))
        return self.responses.pop(0)


def response(
    status: int = 200,
    *,
    body: bytes = b"ok",
    headers: dict[str, str] | None = None,
) -> requests.Response:
    item = requests.Response()
    item.status_code = status
    item.headers.update(headers or {"content-type": "text/html"})
    item._content = body
    item._content_consumed = True
    return item


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "ftp://example.com/file",
        "gopher://example.com/",
        "data:text/plain,hello",
        "javascript:alert(1)",
        "http://localhost/",
        "http://127.0.0.1/",
        "http://0.0.0.0/",
        "http://169.254.169.254/latest/meta-data/",
        "http://10.0.0.1/",
        "http://172.16.0.1/",
        "http://192.168.1.1/",
        "http://[::1]/",
        "http://224.0.0.1/",
        "https://user:password@example.com/",
    ],
)
def test_validate_outbound_url_rejects_unsafe_targets(url):
    with pytest.raises(UnsafeOutboundUrl):
        validate_outbound_url(url, resolver=public_resolver)


def test_validate_outbound_url_rejects_private_dns_answers():
    with pytest.raises(UnsafeOutboundUrl):
        validate_outbound_url("https://agency.example/property/1", resolver=private_resolver)


def test_validate_outbound_url_allows_public_https():
    assert validate_outbound_url(
        "https://agency.example/property/1",
        resolver=public_resolver,
    ) == "https://agency.example/property/1"


def test_secure_get_enforces_tls_and_bounded_response():
    requester = FakeRequester([response(body=b"property")])

    result = secure_get(
        requester,
        "https://agency.example/property/1",
        resolve_dns=False,
        max_response_bytes=100,
    )

    assert result.content == b"property"
    assert requester.calls[0][1]["verify"] is True
    assert requester.calls[0][1]["allow_redirects"] is False
    with pytest.raises(OutboundSecurityError):
        secure_get(
            requester,
            "https://agency.example/property/1",
            resolve_dns=False,
            verify=False,
        )


def test_secure_get_rejects_redirect_to_private_destination():
    redirect = response(
        status=302,
        headers={"location": "http://127.0.0.1/admin"},
    )
    requester = FakeRequester([redirect])

    with pytest.raises(UnsafeOutboundUrl):
        secure_get(
            requester,
            "https://agency.example/property/1",
            resolve_dns=False,
        )


def test_secure_get_rejects_oversized_response():
    requester = FakeRequester(
        [response(body=b"x" * 11, headers={"content-length": "11"})]
    )

    with pytest.raises(OutboundResponseError):
        secure_get(
            requester,
            "https://agency.example/property/1",
            resolve_dns=False,
            max_response_bytes=10,
        )
