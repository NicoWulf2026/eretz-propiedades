"""Utilities for selecting real property images before publishing."""

from __future__ import annotations

import re
from typing import Any, Iterable, List, Tuple
from urllib.parse import urlparse, unquote

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

    # A WhatsApp-exported property photo is not a social widget. Match the
    # widget filename, not any mention of the channel in a media URL.
    filename = unquote(path).rsplit('/', 1)[-1]
    if re.fullmatch(r'(?:icon[-_])?whatsapp(?:[-_]icon)?\.(?:png|jpe?g|gif|webp)', filename):
        return True

    if re.search(r"(?:^|[/_.-])360(?:[/_.-]|$)", lower):
        return True

    return False


def is_known_page_asset(value: Any) -> bool:
    """Known UI/branding assets; repetition alone is not ownership evidence."""
    if is_branding_or_logo_image(value):
        return True
    if is_high_confidence_non_property_image(image_url_from_value(value)):
        return True
    parsed = urlparse(image_url_from_value(value).lower())
    filename = unquote(parsed.path).rsplit('/', 1)[-1]
    return bool(re.fullmatch(
        r'(?:user-\d+|avatar(?:[-_]\d+)?|ico[-_]tel|icon[-_]phone)\.(?:png|jpe?g|gif|webp)',
        filename,
    ) or ((parsed.hostname == 'pinterest.com' or
           (parsed.hostname or '').endswith('.pinterest.com')) and '/pin/create/button' in parsed.path))


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


IMAGE_CLASS_HIGH = "HIGH_CONFIDENCE_NON_PROPERTY_IMAGE"
IMAGE_CLASS_POSSIBLE = "POSSIBLE_NON_PROPERTY_IMAGE"
IMAGE_CLASS_VALID = "LIKELY_VALID_IMAGE"

IMAGE_DETECTOR_VERSION = "2026-08-12.1"

# Hosts que sirven UI de mapas: jamas son la foto de un aviso.
_UI_MAP_HOSTS = (
    "tile.osm.org", "tile.openstreetmap.org", "a.tile.", "b.tile.", "c.tile.",
    "maps.gstatic.com", "ssl.gstatic.com", "maps.googleapis.com",
    "unpkg.com/leaflet", "cdnjs.cloudflare.com/ajax/libs/leaflet",
)

# Marcadores semanticos: el propio nombre declara que no es una foto del aviso.
_NON_PROPERTY_STEMS = (
    "sinfoto", "sin-foto", "sin_foto", "nofoto", "no-foto",
    "no-image", "noimage", "sin-imagen", "sinimagen",
    "placeholder", "default", "sample", "dummy", "spacer", "blank",
    "transparent", "transparente", "pixel", "1x1",
    "avatar", "matricula", "matricula_", "logo", "isotipo", "imagotipo",
    "isologo", "favicon", "watermark", "marca-agua",
    "og-home", "og_home", "og-image", "og_image", "opengraph",
    "impression-header", "spotlight-poi",
)

# Rutas propias de plantilla/CMS, no del contenido cargado por el publicador.
_TEMPLATE_PATHS = (
    "/wp-content/themes/", "/wp-content/plugins/",
    "/static/src/img/", "/assets/og/", "/assets/img/theme",
    "/stthemeeditor/", "/themeeditor/", "/mapfiles/",
    "/includes/images/", "/admin/uploads/", "/slider/",
)


def _norm_token(value):
    """Normaliza para comparar nombres: minusculas, sin acentos ni separadores."""
    import unicodedata
    text = unicodedata.normalize("NFD", str(value or "").lower())
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", "", text)


# These markers are constants. Normalize them once, not twice per marker for
# every photo in a national inventory build.
_NORMALIZED_NON_PROPERTY_STEMS = tuple((marker, _norm_token(marker))
                                      for marker in _NON_PROPERTY_STEMS)


def non_property_image_signals(image_url, publisher_name=None):
    """Devuelve la lista de senales estructurales detectadas en la URL."""
    url = str(image_url or "").strip()
    low = unquote(url.lower())
    signals = []
    if not low.strip():
        return ["empty_url"]

    # URL sin resolver: plantilla de tiles. No es una imagen concreta.
    if re.search(r"\{[szxy]\}", low):
        signals.append("unresolved_url_template")
    if any(h in low for h in _UI_MAP_HOSTS):
        signals.append("map_ui_asset")

    parsed = urlparse(low)
    path = parsed.path or low
    filename = path.rsplit("/", 1)[-1]
    stem = _norm_token(filename.rsplit(".", 1)[0])

    for marker, normalized in _NORMALIZED_NON_PROPERTY_STEMS:
        if normalized and normalized in stem:
            signals.append("semantic_marker:%s" % marker)
            break
    for tpath in _TEMPLATE_PATHS:
        if tpath in low:
            signals.append("template_asset")
            break
    if path.endswith((".svg", ".ico", ".gif")):
        signals.append("non_photo_format")

    # Branding del propio publicador: el archivo lleva su nombre.
    if publisher_name:
        pub = _norm_token(publisher_name)
        # Se usa el token mas largo del nombre para evitar coincidencias debiles.
        # Se descartan las palabras genericas del rubro: "Inmobiliaria Bessa"
        # sin este filtro haria match con cualquier archivo que diga inmobiliaria.
        generic = {"inmobiliaria", "inmobiliarias", "propiedades", "negocios",
                   "servicios", "bienes", "raices", "inmuebles", "desarrollos",
                   "asociados", "grupo", "estudio", "consultora", "gestion"}
        parts = [p for p in re.split(r"[^A-Za-zÁÉÍÓÚÑáéíóúñ]+", str(publisher_name))
                 if len(p) >= 5 and _norm_token(p) not in generic]
        for part in parts:
            if _norm_token(part) and _norm_token(part) in stem:
                signals.append("publisher_name_in_filename")
                break
        del pub
    # Fondo transparente declarado: firma tipica de un logo exportado.
    if "fondotransp" in stem or "transp" in stem:
        signals.append("declared_transparent_background")
    # Variante cromatica: los logos se exportan como "-blanco" / "-negro".
    if re.search(r"(?:^|[a-z0-9])(blanc[oa]|negr[oa]|white|black)$", stem):
        signals.append("color_variant_marker")
    return signals


def classify_property_image(image_url, publisher_name=None, repetition_scoped=0):
    """Clasifica una URL. Devuelve (clase, reasons, confidence).

    `repetition_scoped` es cuantas publicaciones del MISMO publicador usan esta
    misma URL. Sola no alcanza para HIGH: eleva a POSSIBLE, o confirma HIGH
    cuando ya hay una senal estructural.
    """
    signals = non_property_image_signals(image_url, publisher_name)

    if "empty_url" in signals:
        return IMAGE_CLASS_HIGH, ["empty_url"], 1.0

    strong = {"unresolved_url_template", "map_ui_asset", "template_asset", "non_photo_format"}
    has_strong = any(s in strong for s in signals)
    has_semantic = any(s.startswith("semantic_marker:") for s in signals)
    # Nombre del publicador + firma de exportacion de logo (fondo transparente o
    # variante cromatica) es evidencia suficiente por si sola.
    branding = ("publisher_name_in_filename" in signals
                and ("declared_transparent_background" in signals
                     or "color_variant_marker" in signals))

    # Inequivocas por si mismas, sin necesidad de repeticion.
    if has_strong or has_semantic or branding:
        return IMAGE_CLASS_HIGH, signals, 0.95

    # Senal debil aislada + repeticion alta dentro del mismo publicador.
    weak = [s for s in signals if s in ("publisher_name_in_filename",
                                       "declared_transparent_background",
                                       "color_variant_marker")]
    if weak and repetition_scoped >= 10:
        return IMAGE_CLASS_HIGH, signals + ["scoped_repetition>=10"], 0.9
    if weak:
        return IMAGE_CLASS_POSSIBLE, signals, 0.5

    # Repeticion sin ninguna otra senal: sospecha, nunca certeza. La auditoria
    # encontro fotos reales repetidas legitimamente entre unidades de un loteo.
    if repetition_scoped >= 10:
        return IMAGE_CLASS_POSSIBLE, ["scoped_repetition>=%d" % repetition_scoped], 0.4

    return IMAGE_CLASS_VALID, signals, 0.0


def is_high_confidence_non_property_image(image_url, publisher_name=None, repetition_scoped=0):
    cls, _, _ = classify_property_image(image_url, publisher_name, repetition_scoped)
    return cls == IMAGE_CLASS_HIGH
