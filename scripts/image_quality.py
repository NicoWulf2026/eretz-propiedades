"""Utilities for selecting real property images before publishing."""

from __future__ import annotations

import re
from typing import Any, Iterable, List, Tuple
from urllib.parse import urlparse

BRANDING_IMAGE_PATTERNS = (
    "static.tokkobroker.com/tfw/img/prop-icons",
    "/prop-icons",
    "/imgs/inmobiliaria",
    "inmobiliaria-",
    "mascara-galeria",
    "rounded-cds",
    "footer",
    "logo",
    "isotipo",
    "imagotipo",
    "favicon",
    "placeholder",
    "no-photo",
    "no_image",
    "no-image",
    "sin-imagen",
    "sin_imagen",
)

SURFACE_IMAGE_PATTERNS = (
    "tour",
    "virtual",
    "facebook",
    "instagram",
    "whatsapp",
    "linkedin",
    "youtube",
    "menu",
    "boton",
    "btn",
    "mapa",
    "maps",
    "streetview",
)


def image_url_from_value(value: Any) -> str:
    if isinstance(value, dict):
        raw = value.get("url") or value.get("src") or value.get("href") or value.get("image")
    else:
        raw = value

    return str(raw or "").strip()


def is_branding_or_logo_image(value: Any) -> bool:
    url = image_url_from_value(value)
    if not url:
        return True

    lower = url.lower()
    parsed = urlparse(lower if "://" in lower else f"https://{lower}")
    path = parsed.path or lower

    if lower.startswith(("data:", "blob:")) or path.endswith((".svg", ".ico")):
        return True

    if any(pattern in lower for pattern in BRANDING_IMAGE_PATTERNS):
        return True

    if any(pattern in lower for pattern in SURFACE_IMAGE_PATTERNS):
        return True

    if re.search(r"(?:^|[/_.-])360(?:[/_.-]|$)", lower):
        return True

    return False


def normalize_property_images(values: Any, *, max_images: int = 60) -> Tuple[List[str], List[str]]:
    """Return publishable images first and discarded branding/surface assets second."""

    if not isinstance(values, list):
        return [], []

    seen: set[str] = set()
    real_images: List[str] = []
    discarded: List[str] = []

    for item in values:
        url = image_url_from_value(item)
        if not url or url in seen:
            continue
        seen.add(url)

        if is_branding_or_logo_image(url):
            discarded.append(url)
            continue

        real_images.append(url)
        if len(real_images) >= max_images:
            break

    return real_images, discarded


def has_real_property_image(values: Iterable[Any]) -> bool:
    real_images, _ = normalize_property_images(list(values))
    return bool(real_images)
