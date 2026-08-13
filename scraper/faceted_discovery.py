"""faceted_discovery.py — Módulo de descubrimiento de listados faceteados.

Proporciona dos estrategias:
  1. generic_faceted: combinaciones operación×tipo + paginación para sitios HTML estáticos.
  2. xtipo_cms: enumeración de parámetro x_Tipo para el CMS clásico argentino
     (venta-de-propiedades.asp?x_Tipo=N&z_Tipo=%3D%2C%2C).

Este módulo NO escribe en Neon, Supabase ni .env.
Se puede importar desde scraper_propiedades.py o usar standalone.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Set
from urllib.parse import urljoin, urlparse, urlencode, urlunparse, parse_qsl, unquote

# ─── Operación segments (path-based) ─────────────────────────────────────────
OPERACION_SEGMENTS: Dict[str, List[str]] = {
    "venta": ["venta", "ventas", "sale"],
    "alquiler": ["alquiler", "alquileres", "rent"],
    "temporario": ["temporario", "temporada", "vacacional"],
}

# ─── Tipo segments (path-based) ───────────────────────────────────────────────
TIPO_SEGMENTS: Dict[str, List[str]] = {
    "casa": ["casas", "casa"],
    "departamento": ["departamentos", "departamento", "deptos"],
    "terreno": ["terrenos", "terreno", "lotes"],
    "local": ["locales", "local"],
    "oficina": ["oficinas", "oficina"],
    "campo": ["campos", "campo", "chacras", "quintas"],
    "cochera": ["cocheras", "cochera"],
    "galpon": ["galpones", "galpon"],
}

# ─── x_Tipo CMS detection ────────────────────────────────────────────────────
# Classic Argentine CMS: properties loaded via .asp pages with x_Tipo param
_XTIPO_CMS_RE = re.compile(
    r"(?:venta|alquiler(?:-temporario)?)-de-propiedades\.asp",
    re.I,
)
_XTIPO_BASE_PATHS = [
    "venta-de-propiedades.asp",
    "alquiler-de-propiedades.asp",
    "alquiler-temporario-de-propiedades.asp",
]
# Typ values 1-12 cover most property types in this CMS
_XTIPO_VALUES = list(range(1, 13))

# ─── Generic faceted query params ────────────────────────────────────────────
_OPERACION_PARAMS = ["operacion", "operation", "tipo_operacion", "purpose", "op"]
_PAGE_PARAMS = ["p", "pagina", "page", "pag", "offset", "start"]

# Safety limits
MAX_FACETED_CANDIDATES = 30
MAX_XTIPO_CANDIDATES = 40
MAX_PAGES = 6


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _norm(url: str) -> str:
    """Lightweight URL normalization for deduplication."""
    try:
        p = urlparse(url.rstrip("/").lower())
        host = p.netloc.lstrip("www.")
        path = p.path.rstrip("/")
        qs = "&".join(
            f"{k}={v}" for k, v in sorted(parse_qsl(p.query))
            if not k.startswith("utm_") and k not in {"fbclid", "gclid", "_"}
        )
        return f"{host}{path}" + (f"?{qs}" if qs else "")
    except Exception:
        return url.lower().rstrip("/")


def _root(url: str) -> str:
    """Return scheme://host from a URL."""
    try:
        p = urlparse(url)
        return f"{p.scheme}://{p.netloc}".rstrip("/")
    except Exception:
        return ""


# ─── Detection ────────────────────────────────────────────────────────────────

def detect_xtipo_cms(html: str, url: str) -> bool:
    """Return True if the site uses the x_Tipo CMS pattern.

    Detects both from the URL itself and from the HTML content
    (links that contain venta-de-propiedades.asp with x_Tipo).
    """
    combined = (html or "")[:30000] + " " + (url or "")
    return bool(_XTIPO_CMS_RE.search(combined))


# ─── x_Tipo CMS candidates ────────────────────────────────────────────────────

def generate_xtipo_candidates(base_url: str) -> List[str]:
    """Generate x_Tipo CMS URL candidates.

    Produces:
      - base listing for each operation (cmd=reset → all types)
      - per-type listings for each operation × x_Tipo value
    """
    root = _root(base_url)
    if not root:
        return []
    candidates: List[str] = []
    seen: Set[str] = set()

    def _add(u: str) -> None:
        n = _norm(u)
        if n not in seen and len(candidates) < MAX_XTIPO_CANDIDATES:
            seen.add(n)
            candidates.append(u)

    for base_path in _XTIPO_BASE_PATHS:
        # All-types listing
        _add(f"{root}/{base_path}?cmd=reset")
        # Per-type
        for tipo_num in _XTIPO_VALUES:
            _add(f"{root}/{base_path}?x_Tipo={tipo_num}&z_Tipo=%3D%2C%2C")

    return candidates


# ─── Generic faceted candidates ───────────────────────────────────────────────

def generate_faceted_candidates(
    base_url: str,
    existing_urls: Optional[List[str]] = None,
    max_candidates: int = MAX_FACETED_CANDIDATES,
) -> List[str]:
    """Generate operation×tipo path combinations and query-param variants.

    Args:
        base_url: The domain root or main listing URL.
        existing_urls: Already-known candidate URLs (to avoid duplicates).
        max_candidates: Cap on new candidates returned.

    Returns a list of new candidate listing URLs to try.
    """
    root = _root(base_url)
    if not root:
        return []

    existing_set: Set[str] = {_norm(u) for u in (existing_urls or [])}
    candidates: List[str] = []
    seen: Set[str] = set()

    def _add(u: str) -> None:
        n = _norm(u)
        if n not in existing_set and n not in seen and len(candidates) < max_candidates:
            seen.add(n)
            candidates.append(u)

    # 1. /propiedades/<operacion> paths
    for op_key, op_segs in OPERACION_SEGMENTS.items():
        op = op_segs[0]
        _add(f"{root}/propiedades/{op}")
        _add(f"{root}/inmuebles/{op}")

    # 2. Operation × tipo combinations (most impactful)
    for op_key, op_segs in OPERACION_SEGMENTS.items():
        op = op_segs[0]
        for tipo_key, tipo_segs in TIPO_SEGMENTS.items():
            tipo = tipo_segs[0]
            _add(f"{root}/{op}/{tipo}")
            _add(f"{root}/propiedades/{op}/{tipo}")

    # 3. Query param combinations
    for op_key, op_segs in OPERACION_SEGMENTS.items():
        op_val = op_segs[0]
        for param in _OPERACION_PARAMS[:2]:
            _add(f"{root}/propiedades?{param}={op_val}")
            _add(f"{root}/buscar?{param}={op_val}")

    # 4. Additional common paths not in existing
    for path in ["/propiedades/venta", "/propiedades/alquiler",
                 "/inmuebles/venta", "/inmuebles/alquiler"]:
        _add(root + path)

    return candidates


# ─── Pagination URL generation ─────────────────────────────────────────────────

def generate_pagination_urls(
    listing_url: str,
    html: str,
    max_pages: int = MAX_PAGES,
) -> List[str]:
    """Generate paginated URLs for a listing page.

    Detects query-param style (?p=N, ?pagina=N, ?page=N) and path-segment
    style (/pagina-N) pagination from the page HTML.

    Returns a list of pagination URLs (pages 2 through max_pages).
    """
    soup = None
    try:
        from bs4 import BeautifulSoup  # type: ignore
        soup = BeautifulSoup(html or "", "html.parser")
    except Exception:
        return []

    parsed = urlparse(listing_url)
    results: List[str] = []

    # Find existing page links to detect the pattern
    page_links: List[str] = []
    pager = (
        soup.find(class_=re.compile(r"\bpaginat|pager|paginator\b", re.I))
        or soup.find("nav", {"aria-label": re.compile(r"pag", re.I)})
        or soup  # fallback: search whole document
    )
    if pager:
        for a in pager.find_all("a", href=True):
            full = urljoin(listing_url, a["href"])
            page_links.append(full)

    # Detect query-param pagination
    detected_param: Optional[str] = None
    for link in page_links:
        for pp in _PAGE_PARAMS:
            m = re.search(rf"[?&]{pp}=(\d+)", link)
            if m:
                detected_param = pp
                break
        if detected_param:
            break

    if detected_param:
        for page_num in range(2, max_pages + 1):
            params = dict(parse_qsl(parsed.query))
            params[detected_param] = str(page_num)
            url = urlunparse(parsed._replace(query=urlencode(params)))
            results.append(url)
        return results

    # Detect path-segment pagination
    for link in page_links:
        if re.search(r"/(?:page|pagina|p)/(\d+)", link):
            for page_num in range(2, max_pages + 1):
                url = f"{listing_url.rstrip('/')}/pagina-{page_num}"
                results.append(url)
            return results

    return results


# ─── Summary reporting ────────────────────────────────────────────────────────

def build_faceted_metadata(
    strategy_name: str,
    combinations_tried: int,
    pages_visited: int,
    links_per_combo: Dict[str, int],
    total_links_found: int,
    limits_reached: List[str],
    elapsed_seconds: float,
) -> Dict[str, Any]:
    """Build a metadata dict for logging faceted discovery results."""
    return {
        "strategy_current": strategy_name,
        "faceted_combinations_tried": combinations_tried,
        "faceted_pages_visited": pages_visited,
        "faceted_links_per_combination": links_per_combo,
        "faceted_total_links_found": total_links_found,
        "faceted_limits_reached": limits_reached,
        "faceted_elapsed_seconds": round(elapsed_seconds, 2),
    }
