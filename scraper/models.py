import hashlib
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
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
    if value is None or isinstance(value, bool):
        return None
    try:
        number = Decimal(str(value))
        if (not number.is_finite() or number != number.to_integral_value()
                or not _INT_MIN <= number <= _INT_MAX):
            return None
        iv = int(number)
    except (TypeError, ValueError, InvalidOperation):
        return None
    return iv


def _safe_surface(value: Any) -> Optional[float]:
    """Surfaces are measurements, not integer room counts."""
    if value is None or isinstance(value, bool):
        return None
    try:
        number = Decimal(str(value))
    except (ValueError, InvalidOperation):
        return None
    return float(number) if number.is_finite() and 0 <= number <= _INT_MAX else None


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
# Operaciones reconocidas por ERETZ Propiedades (FASE 1 — Sprint A).
# - consultar: la fuente dice explicitamente "consultar" → se publica como tal
# - desconocida: no se pudo determinar la operacion (FASE 4). No es lo mismo que
#   "consultar": antes ambos casos colapsaban y un aviso que decia "Consultar"
#   quedaba indistinguible de uno sin operacion detectable. Aca solo puntua la
#   completitud del registro; en almacenamiento público se representa con NULL.
# - venta_y_alquiler: propiedad publicada simultáneamente como venta y alquiler
ALLOWED_OPERACIONES = {
    "venta",
    "alquiler",
    "alquiler_temporario",
    "consultar",
    "venta_y_alquiler",
    "desconocida",
    "proyecto",  # legacy — no eliminar
}

# Public CHECK observed read-only on 2026-09-18. Domain-only states are not
# storage enum values: retain the original in memory/raw evidence, not as venta.
PUBLIC_STORAGE_OPERACIONES = frozenset({
    "venta", "alquiler", "alquiler_temporario", "consultar", "venta_y_alquiler",
})


def operation_for_storage(value: Any) -> Optional[str]:
    if not isinstance(value, str):
        return None
    normalized = value.strip().lower().replace(" ", "_")
    return normalized if normalized in PUBLIC_STORAGE_OPERACIONES else None


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
    metros: Optional[float] = None
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
            "superficie_total":  _safe_surface(self.metros),    # metros -> superficie_total
            "imagenes":          self.imagenes,
            "ciudad":            self.ciudad,
            "operacion":         operation_for_storage(self.operacion),
            "latitud":           self.latitud,
            "longitud":          self.longitud,
            "fuente_extraccion": self.fuente,        # fuente -> fuente_extraccion
            # DB DEFAULT is 'activo' but propiedades_estado_chk only accepts 'activa'
            "estado":            "activa",
        }
        if self.inmobiliaria_id is not None:
            payload["inmobiliaria_id"] = self.inmobiliaria_id
        payload["hash_dedup"] = _compute_hash_dedup(self.inmobiliaria_id, self.url)
        # `url_normalizada` no se producia y el RPC la EXIGE: sin ella,
        # `insert_property_safe` levanta "safe insert requires complete
        # identity and audit envelope". O sea que migrar del REST al RPC no
        # era cambiar la llamada, faltaba el dato. Y produccion ya trata su
        # ausencia como defecto: la bandera `missing_normalized_url` de
        # `property_active_state_and_quality_flags.sql` es exactamente "url
        # exists and url_normalizada is blank".
        #
        # Se calcula con `_normalize_url_for_hash`, la MISMA funcion sobre la
        # que ya esta definido `hash_dedup`, y no con la forma que usa el
        # volcado de produccion -`netloc + path`, sin query-. Medido sobre las
        # 22.097 propiedades certificadas: aquella forma colapsa 492 en otra
        # fila, porque los sitios que identifican la propiedad por query
        # quedan todos con la misma clave. `agostinelli` funde 397 propiedades
        # en `agostinelli.com.ar/ficha.php` y `abonapace` 92 en
        # `abonapace.com.ar/propiedad.php`. Esta funcion conserva las 21.901
        # urls distintas como 21.901 claves distintas.
        normalizada = _normalize_url_for_hash(self.url)
        if normalizada:
            payload["url_normalizada"] = normalizada
        return payload

    def is_valid(self) -> bool:
        try:
            parsed = urlparse(self.url or "")
        except ValueError:
            return False
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
            return False
        if not self.titulo or len(self.titulo.strip()) < 3:
            return False
        if _is_generic_title(self.titulo):
            return False
        # Missing location restricts geographic scopes, not existence. Source
        # ownership and detail verification belong to the discovery boundary.
        if self.tipo_propiedad not in ALLOWED_PROPERTY_TYPES:
            return False
        if self.moneda and self.moneda not in ALLOWED_MONEDAS:
            return False
        return True
