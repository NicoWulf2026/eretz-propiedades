"""Shared, offline detail URL discovery recovered from the historical parser."""
import re
from typing import Dict, List, Optional, Set, Tuple
from urllib.parse import parse_qsl, parse_qs, urljoin, urlparse
from bs4 import BeautifulSoup

_DETAIL_QUERY_KEYS = {
    "id", "idprop", "id_prop", "prop", "propiedad", "inmueble", "codigo",
    "cod", "code", "ficha", "idficha", "id_ficha", "ref", "referencia",
    "aviso", "ad", "pid",
}

_DETAIL_PATH_SEGMENTS = [
    "/p/",
    "/propiedad/",
    "/propiedades/",
    "/ad/",
    "/inmueble/",
    "/inmuebles/",
    "/property/",
    "/properties/",
    "/listing/",
    "/listings/",
    "/listing-",
    "/detalle/",
    "/detalles/",
    "/aviso/",
    "/emprendimiento/",
    "/portfolio/",
    "/portfolio_page/",
    "/producto/",
    "/prop/",
    "/Ficha/",
    "/ficha/",
    "/ficha-",
    "/fichashtml/",
    "/motor/ficha.php",
]

_DETAIL_CATEGORY_WORDS = {
    "venta", "ventas", "alquiler", "alquileres", "page", "buscar", "busqueda",
    "search", "results", "resultados", "categoria", "category", "tipo",
    "type", "cat", "comprar", "rentas", "emprendimientos", "desarrollos",
    "operation", "operations", "forsale", "forrent", "fortemporaryrent",
}

_DETAIL_BAD_PATH_WORDS = {
    "contact", "contacto", "nosotros", "quienes", "quienes-somos", "about",
    "servicios", "tasacion", "tasaciones", "blog", "noticia", "noticias",
    "news", "staff", "equipo", "login", "wp-admin", "property-category",
    "categoria", "category", "mercado-inmobiliario", "prensa", "operation",
    "operations",
}

_DETAIL_STATIC_EXTENSIONS = (
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".pdf", ".doc",
    ".docx", ".xls", ".xlsx", ".zip", ".rar", ".css", ".js", ".ico",
)

_DETAIL_ONCLICK_RE = re.compile(
    r"(?:location(?:\.href)?|window\.location(?:\.href)?|window\.open|openProperty|goTo|verDetalle|detalle|ficha)"
    r"\s*(?:=\s*|\(\s*)?['\"]([^'\"]+)['\"]",
    re.IGNORECASE,
)


def _netloc(url: str) -> str:
    return (urlparse(url).hostname or '').lower().removeprefix('www.')


def detail_query_identifier(url: str) -> Optional[str]:
    """One explicit source identity; repeated or contradictory IDs are invalid."""
    identifiers = []
    for key, values in parse_qs(urlparse(url).query, keep_blank_values=True).items():
        if key.lower() not in _DETAIL_QUERY_KEYS:
            continue
        if len(values) != 1 or not re.fullmatch(r'[A-Za-z0-9_-]{1,120}', values[0]):
            return None
        identifiers.append(values[0])
    if not identifiers or len(set(identifiers)) != 1:
        return None
    return identifiers[0]


def _same_site_or_subdomain(candidate: str, base_url: str) -> bool:
    cand_host = _netloc(candidate)
    base_host = _netloc(base_url)
    # A tenant does not authorize the provider's root or neighboring tenants.
    return bool(cand_host and base_host and cand_host == base_host)


def _has_strong_card_signal(card) -> bool:
    """True when an element looks like a property card, not plain navigation."""
    text = card.get_text(" ", strip=True)
    cls = " ".join(card.get("class", []))
    blob = f"{text} {cls}".lower()
    score = 0
    if re.search(r"(u\$s|us\$|usd|ars|\$\s*\d|consultar|precio)", blob, re.IGNORECASE):
        score += 2
    if re.search(r"\b(venta|alquiler|comprar|renta|en venta|en alquiler)\b", blob, re.IGNORECASE):
        score += 1
    if re.search(r"\b(casa|departamento|depto|terreno|lote|local|oficina|ph|duplex|galpon|inmueble|propiedad)\b", blob, re.IGNORECASE):
        score += 1
    if re.search(r"(\d+)\s*(m2|m²|mts|amb|ambientes|dorm|habit|baños|banos)", blob, re.IGNORECASE):
        score += 1
    if card.select_one("img[src], img[data-src], img[data-lazy-src], img[data-original]"):
        score += 1
    if re.search(r"(property|propiedad|inmueble|listing|aviso|card|result)", cls, re.IGNORECASE):
        score += 1
    return score >= 2


def _is_blocked_detail_url(url: str, base_url: str) -> bool:
    parsed = urlparse(url)
    scheme = parsed.scheme.lower()
    if scheme and scheme not in {"http", "https"}:
        return True
    if parsed.username is not None or parsed.password is not None:
        return True
    lowered = url.lower()
    host = _netloc(url)
    prohibited = ('zonaprop.com.ar', 'zonaprop.com', 'argenprop.com', 'properati.com.ar', 'properati.com')
    if any(host == domain or host.endswith('.' + domain) for domain in prohibited):
        return True
    if not _same_site_or_subdomain(url, base_url):
        return True
    path = parsed.path.lower()
    if any(path.endswith(ext) for ext in _DETAIL_STATIC_EXTENSIONS):
        return True
    path_parts = {p for p in path.strip("/").split("/") if p}
    if path in {"", "/"} and not parsed.query:
        return True
    if any(bad in path_parts or bad in path for bad in _DETAIL_BAD_PATH_WORDS):
        return True
    if re.search(r"(/page/|[?&]page=|[?&]pagina=|#)", lowered):
        return True
    return False


def _looks_like_detail_url(url: str, base_url: str) -> bool:
    """Safe detail URL detector used by parse_cards and unit tests."""
    if _is_blocked_detail_url(url, base_url):
        return False

    parsed = urlparse(url)
    path = parsed.path
    path_lower = path.lower()
    query_pairs = [(k.lower(), v) for k, v in [part.split("=", 1) if "=" in part else (part, "") for part in parsed.query.split("&") if part]]
    if any(k in _DETAIL_QUERY_KEYS and len(v.strip()) >= 1 for k, v in query_pairs):
        return True

    for seg in _DETAIL_PATH_SEGMENTS:
        seg_lower = seg.lower()
        if seg_lower not in path_lower:
            continue
        after = path_lower.split(seg_lower, 1)[-1].strip("/")
        if not after:
            return False
        first = after.split("/")[0].split("-")[0].split("_")[0]
        if first in _DETAIL_CATEGORY_WORDS:
            return False
        if len(after) >= 2:
            return True

    if re.search(r"/(?:propiedad|inmueble|aviso)[-_][^/?#]*\d", path_lower):
        return True
    if re.search(r"/d/\d+(?:-|/|$)", path_lower):
        return True
    if re.search(r"-ficha-[a-z0-9_-]*\d", path_lower):
        return True

    # Conservative slug-only fallback: must have at least two path parts and a
    # real-estate token plus a numeric/reference-like component.
    parts = [p for p in path_lower.strip("/").split("/") if p]
    if len(parts) >= 2:
        joined = " ".join(parts)
        if (
            re.search(r"(venta|alquiler|casa|departamento|depto|terreno|lote|local|ph|inmueble|propiedad)", joined)
            and re.search(r"(\d{2,}|ref-|cod)", joined)
            and not all(p in _DETAIL_CATEGORY_WORDS for p in parts)
        ):
            return True
    return False


def _candidate_url_from_value(raw: str, base_url: str) -> Optional[str]:
    raw = (raw or "").strip()
    if not raw or raw.startswith(("#", "mailto:", "tel:", "whatsapp:", "javascript:")):
        return None
    if raw.startswith("//"):
        raw = "https:" + raw
    return urljoin(base_url, raw)


def _onclick_urls(value: str) -> List[str]:
    urls = [m.group(1) for m in _DETAIL_ONCLICK_RE.finditer(value or "")]
    urls.extend(
        re.findall(
            r"['\"]((?:https?://|/)[^'\"]{2,160}(?:propiedad|propiedades|inmueble|detalle|ficha|ad|ref-|codigo|cod|idprop)[^'\"]*)['\"]",
            value or "",
            flags=re.IGNORECASE,
        )
    )
    return urls


def extract_candidate_detail_urls_from_document(soup, base_url: str) -> List[Tuple[str, str]]:
    """Fast, conservative document-level pre-pass before card parsing."""
    found: List[Tuple[str, str]] = []
    found_index: Dict[str, int] = {}
    found_strength: Dict[str, int] = {}

    def add(raw: str, context, label: str = "", force: bool = False) -> None:
        candidate = _candidate_url_from_value(raw, base_url)
        if not candidate or _is_blocked_detail_url(candidate, base_url):
            return
        accepted = force or _looks_like_detail_url(candidate, base_url)
        if not accepted and context is not None and _has_strong_card_signal(context):
            path = urlparse(candidate).path.lower()
            accepted = bool(
                re.search(r"/(?:venta|alquiler|producto|prop|portfolio_page)/[^/]{5,}/?$", path)
                or re.search(r"/(?:venta|alquiler)-[^/]{5,}/?$", path)
                or (
                    len(path.strip("/")) >= 12
                    and re.search(
                        r"(venta|alquiler|casa|departamento|depto|terreno|lote|"
                        r"local|oficina|ph|duplex|galpon|deposito|cochera)",
                        path,
                    )
                    and path.strip("/") not in _DETAIL_CATEGORY_WORDS
                )
            )
        if not accepted:
            return

        text = ""
        strength = 0
        if context is not None:
            title_node = context.select_one(
                "h1, h2, h3, [class*='title'], [class*='titulo'], "
                "[class*='address'], [class*='direccion']"
            )
            if title_node is not None:
                text = title_node.get_text(" ", strip=True)[:150]
                strength = 4
            if not text:
                image = context.select_one("img[alt]")
                image_alt = image.get("alt", "").strip() if image is not None else ""
                if len(image_alt) > 8:
                    text = image_alt[:150]
                    strength = 3
        clean_label = re.sub(r"\s+", " ", label or "").strip()
        if (
            len(clean_label) > 8
            and clean_label.lower() not in {"ver propiedad", "más detalles", "mas detalles"}
            and strength < 2
        ):
            text = clean_label[:150]
            strength = 2
        if context is not None and _has_strong_card_signal(context):
            strength += 1

        previous_strength = found_strength.get(candidate, -1)
        if previous_strength >= strength:
            return
        found_strength[candidate] = strength
        if candidate in found_index:
            found[found_index[candidate]] = (candidate, text)
        else:
            found_index[candidate] = len(found)
            found.append((candidate, text))

    anchors = list(soup.select("a[href]"))
    repeated_patterns: Dict[str, int] = {}
    for anchor in anchors:
        candidate = _candidate_url_from_value(anchor.get("href", ""), base_url)
        if not candidate or _is_blocked_detail_url(candidate, base_url):
            continue
        path_pattern = re.sub(r"\d+", "{id}", urlparse(candidate).path.lower()).rstrip("/")
        repeated_patterns[path_pattern] = repeated_patterns.get(path_pattern, 0) + 1

    generic_categories = {
        "casa", "casas", "departamento", "departamentos", "terreno", "terrenos",
        "lote", "lotes", "local", "locales", "oficina", "oficinas", "ph",
        "duplex", "galpon", "galpones", "campo", "campos",
    }
    for anchor in anchors:
        raw_href = anchor.get("href", "")
        direct_candidate = _candidate_url_from_value(raw_href, base_url)
        context = anchor
        for _ in range(4):
            if getattr(context, "name", "") in {"nav", "header", "footer", "body", "html"}:
                context = None
                break
            if context is None or _has_strong_card_signal(context):
                break
            context = getattr(context, "parent", None)
        if direct_candidate and _looks_like_detail_url(direct_candidate, base_url):
            add(raw_href, context, anchor.get_text(" ", strip=True)[:150])
            continue
        force = False
        if direct_candidate and not _is_blocked_detail_url(direct_candidate, base_url):
            path = urlparse(direct_candidate).path.lower().rstrip("/")
            pattern = re.sub(r"\d+", "{id}", path)
            final = path.rsplit("/", 1)[-1]
            repeated = repeated_patterns.get(pattern, 0) >= 2
            operation_slug = bool(
                repeated
                and re.search(r"/(?:venta|alquiler)/[^/]{5,}$", path)
                and final not in generic_categories
            )
            numeric_realestate_slug = bool(
                repeated
                and re.search(r"\d", path)
                and re.search(r"(venta|alquiler|casa|depto|departamento|terreno|lote|local|inmueble)", path)
            )
            short_id_route = bool(
                repeated
                and re.fullmatch(r"/(?:d/)?\d+(?:-[^/]{4,})?", path)
                and context is not None
                and _has_strong_card_signal(context)
            )
            branded_reference_slug = bool(
                repeated
                and re.fullmatch(r"/[a-z][a-z0-9_-]{2,}-\d{2,}", path)
                and context is not None
                and _has_strong_card_signal(context)
            )
            force = (
                operation_slug
                or numeric_realestate_slug
                or short_id_route
                or branded_reference_slug
            )
        add(raw_href, context, anchor.get_text(" ", strip=True)[:150], force=force)

    data_selector = ",".join(
        f"[{key}]" for key in ("data-href", "data-url", "data-link", "data-slug", "data-path")
    )
    for element in soup.select(data_selector):
        context = element
        for _ in range(4):
            if getattr(context, "name", "") in {"nav", "header", "footer", "body", "html"}:
                context = None
                break
            if context is None or _has_strong_card_signal(context):
                break
            context = getattr(context, "parent", None)
        for key in ("data-href", "data-url", "data-link", "data-slug", "data-path"):
            if element.get(key):
                add(str(element.get(key)), context)
        if element.get("onclick"):
            for raw in _onclick_urls(str(element.get("onclick"))):
                add(raw, context)

    for script in soup.find_all("script"):
        text = script.get_text(" ", strip=True)
        if not text or len(text) > 2_000_000:
            continue
        for raw in re.findall(r"[\"']((?:https?://|/)[^\"']{2,240})[\"']", text):
            add(raw.replace("\\/", "/"), None)
    return found


def discover_listing_page_urls(
    html: str,
    current_url: str,
    *,
    limit: int = 4,
) -> List[str]:
    """Return conservative same-site listing alternatives from site navigation."""
    soup = BeautifulSoup(html, "html.parser")
    try:
        current = current_url.rstrip("/")
        candidates: List[str] = []
        seen: Set[str] = set()
        exact_labels = {
            "propiedades",
            "inmuebles",
            "ventas",
            "venta",
            "alquileres",
            "alquiler",
            "comprar",
            "alquilar",
        }
        route_re = re.compile(
            r"^/(?:propiedades(?:\.html)?|inmuebles(?:-\d+)?|ventas?|alquileres?)/?$",
            re.IGNORECASE,
        )
        for anchor in soup.select("a[href]"):
            raw = str(anchor.get("href") or "").strip()
            candidate = _candidate_url_from_value(raw, current_url)
            if not candidate or not _same_site_or_subdomain(candidate, current_url):
                continue
            parsed = urlparse(candidate)
            label = re.sub(r"\s+", " ", anchor.get_text(" ", strip=True)).casefold()
            query = {
                key.casefold(): value.casefold()
                for key, value in parse_qsl(parsed.query)
            }
            listing_query = any(
                key in {"operacion", "operation", "purpose"}
                and value in {"venta", "alquiler", "sale", "rent", "1", "2"}
                for key, value in query.items()
            )
            route_match = bool(route_re.fullmatch(parsed.path))
            if label not in exact_labels and not route_match and not listing_query:
                continue
            normalized = candidate.rstrip("/")
            if normalized == current or normalized in seen:
                continue
            seen.add(normalized)
            candidates.append(candidate)
            if len(candidates) >= max(1, limit):
                break
        return candidates
    finally:
        soup.decompose()


def extract_candidate_detail_urls_from_card(card, base_url: str) -> List[str]:
    """
    Extract safe property-detail candidates from a listing card.

    It accepts anchors, relative URLs, safe detail query params, data-* attrs and
    onclick URLs only when the card itself has strong real-estate signals.
    """
    if not _has_strong_card_signal(card):
        return []

    raw_values: List[str] = []
    for a in card.select("a[href]"):
        raw_values.append(a.get("href", ""))

    data_keys = {"data-href", "data-url", "data-link", "data-slug", "data-target", "data-path"}
    for el in [card, *card.find_all(True)]:
        for key, value in el.attrs.items():
            if key in data_keys or (key.startswith("data-") and any(tok in key for tok in ("href", "url", "link", "slug", "path"))):
                if isinstance(value, list):
                    raw_values.extend(str(v) for v in value)
                else:
                    raw_values.append(str(value))
        onclick = el.get("onclick")
        if onclick:
            raw_values.extend(_onclick_urls(onclick))

    out: List[str] = []
    seen: Set[str] = set()
    for raw in raw_values:
        candidate = _candidate_url_from_value(raw, base_url)
        if not candidate or candidate in seen:
            continue
        if _looks_like_detail_url(candidate, base_url):
            seen.add(candidate)
            out.append(candidate)
    return out
