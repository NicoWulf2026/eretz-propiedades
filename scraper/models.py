import hashlib
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qsl, unquote, urlencode, urlparse

_DEDUP_TRACKING_QUERY_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "fbclid", "gclid", "wbraid", "gbraid", "mc_cid", "mc_eid",
}


def _normalize_url_for_hash(url: Any) -> str:
    """URL canónica para identidad de propiedad (mismo algoritmo que scraper_propiedades.hash_propiedad)."""
    if not url:
        return ""
    raw = unquote(str(url).strip())
    if not raw:
        return ""
    if not re.match(r"^https?://", raw, re.IGNORECASE):
        raw = f"http://{raw.lstrip('/')}"
    try:
        parsed = urlparse(raw)
    except Exception:
        return re.sub(r"\s+", "", raw.lower()).rstrip("/")
    host = (parsed.netloc or parsed.path.split("/")[0]).split("@")[-1]
    host = host.split(":")[0].strip().lower()
    if host.startswith("www."):
        host = host[4:]
    path = parsed.path or ""
    if parsed.netloc:
        path = re.sub(r"/+", "/", unquote(path)).strip().rstrip("/")
    else:
        path = ""
    path = path.lower()
    query_items = []
    for k, v in parse_qsl(parsed.query, keep_blank_values=False):
        kc = k.strip().lower()
        if not kc or kc in _DEDUP_TRACKING_QUERY_PARAMS or kc.startswith("utm_"):
            continue
        query_items.append((kc, v.strip().lower()))
    query = urlencode(sorted(query_items), doseq=True)
    normalized = f"{host}{path}"
    if query:
        normalized = f"{normalized}?{query}"
    return normalized.rstrip("/")


def _compute_hash_dedup(inmobiliaria_id: Any, url: Any) -> str:
    """SHA256[:32] de '{inmobiliaria_id}|url|{url_normalizada}'. Mismo algoritmo que hash_propiedad."""
    url_key = _normalize_url_for_hash(url)
    if url_key:
        key = f"{inmobiliaria_id}|url|{url_key}"
    else:
        key = f"{inmobiliaria_id}|sin_identidad|"
    return hashlib.sha256(key.encode()).hexdigest()[:32]


_INT_MAX = 2_147_483_647
_INT_MIN = -2_147_483_648


def _safe_int(value: Any) -> Optional[int]:
    """Convierte value a int PostgreSQL-safe. Retorna None si es None, no parseable, o fuera de rango."""
    if value is None:
        return None
    try:
        iv = int(value)
    except (TypeError, ValueError):
        return None
    return iv if _INT_MIN <= iv <= _INT_MAX else None


def _is_generic_title(value: Any) -> bool:
    if not value:
        return True
    text = str(value).strip().lower()
    normalized = unicodedata.normalize("NFKD", text)
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized).strip()
    return normalized in {
        "propiedad",
        "propiedades",
        "inmueble",
        "inmuebles",
        "sin titulo",
        "propiedad sin titulo",
        "detalle",
        "descripcion",
    }


ALLOWED_PROPERTY_TYPES = {
    "casa",
    "departamento",
    "terreno",
    "local",
    "oficina",
    "cochera",
    "galpon",
    "otro",
}

ALLOWED_MONEDAS = {"ARS", "USD"}
# Operaciones reconocidas por InmoCapital (FASE 1 — Sprint A).
# - consultar: operacion desconocida o no detectada → no rechazar, publicar con consultar
# - venta_y_alquiler: propiedad publicada simultáneamente como venta y alquiler
ALLOWED_OPERACIONES = {
    "venta",
    "alquiler",
    "alquiler_temporario",
    "consultar",
    "venta_y_alquiler",
    "proyecto",  # legacy — no eliminar
}


@dataclass
class Propiedad:
    url: str
    titulo: str
    precio: Optional[int] = None
    moneda: Optional[str] = None
    direccion: Optional[str] = None
    barrio: Optional[str] = None
    barrio_normalizado: Optional[str] = None
    tipo_propiedad: str = "otro"
    descripcion: str = ""
    dormitorios: Optional[int] = None
    banos: Optional[int] = None
    ambientes: Optional[int] = None
    metros: Optional[int] = None
    imagenes: List[str] = field(default_factory=list)
    ciudad: Optional[str] = None
    operacion: Optional[str] = None
    latitud: Optional[float] = None
    longitud: Optional[float] = None
    fuente: Optional[str] = None
    scraped_at: Optional[str] = None
    inmobiliaria_id: Optional[int] = None

    def __post_init__(self) -> None:
        if self.operacion:
            self.operacion = self.operacion.lower().strip()
        if not self.scraped_at:
            self.scraped_at = datetime.now(timezone.utc).isoformat()

    def calcular_score(self) -> int:
        score = 0
        if self.precio is not None:
            score += 1
        if self.metros is not None:
            score += 1
        if self.direccion:
            score += 1
        if self.imagenes:
            score += 1
        if self.operacion in ALLOWED_OPERACIONES:
            score += 1
        return score

    def to_payload(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "url":               self.url,
            "titulo":            self.titulo,
            "precio":            self.precio,
            "moneda":            self.moneda,
            "direccion":         self.direccion,
            "barrio":            self.barrio,
            "tipo_propiedad":    self.tipo_propiedad,
            "descripcion":       self.descripcion,
            "dormitorios":       _safe_int(self.dormitorios),
            "banos":             _safe_int(self.banos),
            "ambientes":         _safe_int(self.ambientes),
            "superficie_total":  _safe_int(self.metros),        # metros -> superficie_total
            "imagenes":          self.imagenes,
            "ciudad":            self.ciudad,
            "operacion":         self.operacion,
            "latitud":           self.latitud,
            "longitud":          self.longitud,
            "fuente_extraccion": self.fuente,        # fuente -> fuente_extraccion
            # DB DEFAULT is 'activo' but propiedades_estado_chk only accepts 'activa'
            "estado":            "activa",
        }
        if self.inmobiliaria_id is not None:
            payload["inmobiliaria_id"] = self.inmobiliaria_id
        payload["hash_dedup"] = _compute_hash_dedup(self.inmobiliaria_id, self.url)
        return payload

    def is_valid(self) -> bool:
        if not self.url or not self.url.startswith("http"):
            return False
        if not self.titulo or len(self.titulo.strip()) < 3:
            return False
        if _is_generic_title(self.titulo):
            return False
        if not self.direccion and not self.barrio:
            return False
        if self.tipo_propiedad not in ALLOWED_PROPERTY_TYPES:
            return False
        if self.moneda and self.moneda not in ALLOWED_MONEDAS:
            return False
        return True
