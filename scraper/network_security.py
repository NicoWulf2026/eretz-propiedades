"""Central outbound HTTP safety policy for ERETZ.

HTTP and HTTPS are the only accepted schemes. Every destination, including
redirect targets, is checked against private, loopback, link-local, multicast,
reserved and otherwise non-global addresses. TLS verification is mandatory.
"""

from __future__ import annotations

import ipaddress
import socket
from collections.abc import Iterable
from collections.abc import Mapping
from typing import Any, Protocol
from urllib.parse import urljoin, urlsplit

import requests


DEFAULT_CONNECT_TIMEOUT_SECONDS = 8.0
DEFAULT_READ_TIMEOUT_SECONDS = 30.0
DEFAULT_MAX_REDIRECTS = 5
DEFAULT_MAX_RESPONSE_BYTES = 20 * 1024 * 1024
ALLOWED_SCHEMES = frozenset({"http", "https"})
BLOCKED_HOSTNAMES = frozenset(
    {
        "localhost",
        "localhost.localdomain",
        "metadata",
        "metadata.google.internal",
        "instance-data",
    }
)


class OutboundSecurityError(ValueError):
    """Base class for fail-closed outbound request policy violations."""


class UnsafeOutboundUrl(OutboundSecurityError):
    """Raised when an outbound URL can reach a forbidden destination."""


class OutboundResolutionError(OutboundSecurityError):
    """Raised when a hostname cannot be safely and deterministically resolved."""


class OutboundResponseError(OutboundSecurityError):
    """Raised when redirects, response size or content violate policy."""


class Requester(Protocol):
    def get(self, url: str, **kwargs: Any) -> requests.Response: ...


def _validate_ip(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> None:
    if (
        not address.is_global
        or address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
    ):
        raise UnsafeOutboundUrl("destination resolves to a non-global address")


def validate_outbound_url(
    url: str,
    *,
    resolve_dns: bool = True,
    resolver: Any = socket.getaddrinfo,
) -> str:
    """Validate and return a normalized HTTP(S) URL.

    DNS resolution is fail-closed. All returned addresses must be globally
    routable; one unsafe answer rejects the hostname.
    """

    if not isinstance(url, str) or not url.strip():
        raise UnsafeOutboundUrl("outbound URL is empty")
    value = url.strip()
    parsed = urlsplit(value)
    if parsed.scheme.casefold() not in ALLOWED_SCHEMES:
        raise UnsafeOutboundUrl("outbound URL scheme is not HTTP(S)")
    if not parsed.hostname:
        raise UnsafeOutboundUrl("outbound URL has no hostname")
    if parsed.username is not None or parsed.password is not None:
        raise UnsafeOutboundUrl("credentials in outbound URLs are forbidden")
    try:
        port = parsed.port
    except ValueError as exc:
        raise UnsafeOutboundUrl("outbound URL has an invalid port") from exc
    if port is not None and not 1 <= port <= 65535:
        raise UnsafeOutboundUrl("outbound URL port is outside the valid range")

    hostname = parsed.hostname.rstrip(".").casefold()
    if (
        hostname in BLOCKED_HOSTNAMES
        or hostname.endswith(".localhost")
        or hostname.endswith(".local")
        or hostname.endswith(".internal")
    ):
        raise UnsafeOutboundUrl("outbound hostname is reserved for local use")

    try:
        literal = ipaddress.ip_address(hostname)
    except ValueError:
        literal = None
    if literal is not None:
        _validate_ip(literal)
    elif resolve_dns:
        try:
            answers = resolver(hostname, port or (443 if parsed.scheme == "https" else 80))
        except OSError as exc:
            raise OutboundResolutionError("outbound hostname resolution failed") from exc
        addresses = {
            ipaddress.ip_address(answer[4][0].split("%", 1)[0])
            for answer in answers
            if answer and len(answer) >= 5 and answer[4]
        }
        if not addresses:
            raise OutboundResolutionError("outbound hostname returned no addresses")
        for address in addresses:
            _validate_ip(address)
    return value


def _content_type_allowed(content_type: str, accepted: Iterable[str]) -> bool:
    media_type = content_type.split(";", 1)[0].strip().casefold()
    return not media_type or any(
        media_type == item.casefold() or media_type.startswith(item.casefold())
        for item in accepted
    )


def secure_get(
    requester: Requester,
    url: str,
    *,
    timeout: tuple[float, float] | float = (
        DEFAULT_CONNECT_TIMEOUT_SECONDS,
        DEFAULT_READ_TIMEOUT_SECONDS,
    ),
    max_redirects: int = DEFAULT_MAX_REDIRECTS,
    max_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES,
    accepted_content_types: Iterable[str] | None = None,
    resolve_dns: bool = True,
    **kwargs: Any,
) -> requests.Response:
    """Perform a bounded, TLS-verified GET with redirect-by-redirect validation."""

    if kwargs.pop("verify", True) is not True:
        raise OutboundSecurityError("TLS verification cannot be disabled")
    if kwargs.pop("allow_redirects", False):
        raise OutboundSecurityError("automatic redirects bypass outbound validation")
    if max_redirects < 0 or max_redirects > 10:
        raise OutboundSecurityError("redirect limit is outside the safe range")
    if max_response_bytes <= 0:
        raise OutboundSecurityError("response size limit must be positive")

    current = validate_outbound_url(url, resolve_dns=resolve_dns)
    request_kwargs = dict(kwargs)
    request_kwargs["allow_redirects"] = False
    request_kwargs["verify"] = True
    request_kwargs["timeout"] = timeout
    request_kwargs["stream"] = True

    for redirect_count in range(max_redirects + 1):
        try:
            response = requester.get(current, **request_kwargs)
        except requests.RequestException as exc:
            # Do not include query parameters or provider credentials in errors.
            target = urlsplit(current)
            safe_target = f"{target.scheme}://{target.netloc}{target.path}"
            raise OutboundResponseError(
                f"{type(exc).__name__}: outbound request failed for {safe_target}"
            ) from exc
        status_code = int(response.status_code)
        headers = response.headers if isinstance(response.headers, Mapping) else {}
        if status_code in {301, 302, 303, 307, 308}:
            location = headers.get("location", "")
            response.close()
            if not location:
                raise OutboundResponseError("redirect response has no Location header")
            if redirect_count >= max_redirects:
                raise OutboundResponseError("outbound redirect limit exceeded")
            current = validate_outbound_url(
                urljoin(current, location),
                resolve_dns=resolve_dns,
            )
            request_kwargs.pop("params", None)
            continue

        content_length = headers.get("content-length")
        if content_length:
            try:
                if int(content_length) > max_response_bytes:
                    response.close()
                    raise OutboundResponseError("outbound response exceeds size limit")
            except ValueError:
                response.close()
                raise OutboundResponseError("outbound response has invalid Content-Length")
        if accepted_content_types is not None and not _content_type_allowed(
            headers.get("content-type", ""),
            accepted_content_types,
        ):
            response.close()
            raise OutboundResponseError("outbound response content type is not accepted")

        body = bytearray()
        chunks: Iterable[bytes]
        if isinstance(response, requests.Response):
            chunks = response.iter_content(chunk_size=64 * 1024)
        else:
            raw_content = getattr(response, "content", None)
            if isinstance(raw_content, bytes):
                chunks = (raw_content,)
            else:
                raw_text = getattr(response, "text", "")
                chunks = (
                    raw_text.encode("utf-8") if isinstance(raw_text, str) else b"",
                )
        for chunk in chunks:
            if not chunk:
                continue
            body.extend(chunk)
            if len(body) > max_response_bytes:
                response.close()
                raise OutboundResponseError("outbound response exceeds size limit")
        response._content = bytes(body)
        setattr(response, "_content_consumed", True)
        return response

    raise OutboundResponseError("outbound redirect handling failed closed")
