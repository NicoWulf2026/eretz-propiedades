"""Deterministic, fail-closed merge policy for Pipeline A properties.

This module is intentionally free of network and database code.  It turns an
incoming scraper payload plus candidate database rows into one of three plans:
insert, update/unchanged, or rejected identity.  Database code must still apply
accepted updates atomically and persist the returned audit decisions.
"""

from __future__ import annotations

import html
import math
import re
import unicodedata
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from models import _compute_hash_dedup, _normalize_url_for_hash

ACCEPTED_INSERT = "ACCEPTED_INSERT"
ACCEPTED_IMPROVEMENT = "ACCEPTED_IMPROVEMENT"
ACCEPTED_SOURCE_CHANGE = "ACCEPTED_SOURCE_CHANGE"
REJECTED_NULL_DEGRADATION = "REJECTED_NULL_DEGRADATION"
REJECTED_PLACEHOLDER = "REJECTED_PLACEHOLDER"
REJECTED_LOWER_CONFIDENCE = "REJECTED_LOWER_CONFIDENCE"
REJECTED_AMBIGUOUS_IDENTITY = "REJECTED_AMBIGUOUS_IDENTITY"
REJECTED_CROSS_PROPERTY_CONTAMINATION = "REJECTED_CROSS_PROPERTY_CONTAMINATION"
UNCHANGED_EQUAL = "UNCHANGED_EQUAL"

DECISIONS = {
    ACCEPTED_INSERT,
    ACCEPTED_IMPROVEMENT,
    ACCEPTED_SOURCE_CHANGE,
    REJECTED_NULL_DEGRADATION,
    REJECTED_PLACEHOLDER,
    REJECTED_LOWER_CONFIDENCE,
    REJECTED_AMBIGUOUS_IDENTITY,
    REJECTED_CROSS_PROPERTY_CONTAMINATION,
    UNCHANGED_EQUAL,
}

MERGE_FIELDS: Tuple[str, ...] = (
    "titulo",
    "descripcion",
    "precio",
    "moneda",
    "tipo_propiedad",
    "operacion",
    "ambientes",
    "dormitorios",
    "banos",
    "superficie_total",
    "direccion",
    "barrio",
    "ciudad",
    "latitud",
    "longitud",
    "imagenes",
)

IMMUTABLE_IDENTITY_FIELDS = {
    "id",
    "inmobiliaria_id",
    "url",
    "url_normalizada",
    "id_externo",
    "hash_dedup",
    "fuente_extraccion",
    "estado",
    "created_at",
    "updated_at",
}

_GENERIC_TEXT = {
    "",
    "-",
    "n/a",
    "na",
    "null",
    "none",
    "sin dato",
    "sin datos",
    "a consultar",
    "consultar",
    "propiedad",
    "propiedades",
    "inmueble",
    "inmuebles",
    "sin titulo",
    "propiedad sin titulo",
    "detalle",
    "descripcion",
    "argentina",
}
_GENERIC_LOCATION = _GENERIC_TEXT | {
    "capital federal",
    "buenos aires",
    "caba",
    "ubicacion",
    "dirección",
    "direccion",
}
_CONTAMINATION_RE = re.compile(
    r"(?:<script|<style|<nav|<footer|cookie|pol[ií]tica de privacidad|"
    r"todos los derechos reservados|copyright|iniciar sesi[oó]n|"
    r"registrate|suscribite|men[uú] principal|javascript:)",
    re.IGNORECASE,
)
_FILE_OR_SHELL_LABEL_RE = re.compile(
    r"(?:^|[/\\])(?:logo|icon|favicon|detalle|detail|index|home)[^/\\]*$|"
    r"\.(?:png|jpe?g|gif|svg|webp|php|html?|aspx?|js|css)\\?$",
    re.IGNORECASE,
)
_IMAGE_REJECT_RE = re.compile(
    r"(?:placeholder|no[-_ ]?image|sin[-_ ]?imagen|logo|favicon|sprite|"
    r"avatar|icon(?:o)?|loading|spinner|map(?:a)?[-_]|google[-_]?maps|"
    r"blank\.(?:gif|png)|transparent\.(?:gif|png))",
    re.IGNORECASE,
)
_VALID_CURRENCIES = {"ARS", "USD"}
_VALID_OPERATIONS = {
    "venta",
    "alquiler",
    "alquiler_temporario",
    "consultar",
    "venta_y_alquiler",
}
_VALID_TYPES = {
    "casa",
    "departamento",
    "terreno",
    "local",
    "oficina",
    "cochera",
    "galpon",
    "otro",
}
_FILL_ONLY_NUMBERS = {
    "ambientes",
    "dormitorios",
    "banos",
    "superficie_total",
}
_LOCATION_FIELDS = {"direccion", "barrio", "ciudad"}


def _plain(value: Any) -> str:
    text = html.unescape(str(value or "")).strip().lower()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", text)


def _source_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", _plain(value))


def _external_key(value: Any) -> str:
    return re.sub(r"\s+", "", _plain(value))


def _is_blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _is_placeholder_text(value: Any, *, location: bool = False) -> bool:
    raw = str(value or "").strip()
    normalized = _plain(raw)
    generic = _GENERIC_LOCATION if location else _GENERIC_TEXT
    return (
        not normalized
        or normalized in generic
        or bool(_FILE_OR_SHELL_LABEL_RE.search(raw))
    )


def _is_contaminated_text(value: Any) -> bool:
    text = str(value or "")
    return bool(_CONTAMINATION_RE.search(text)) or len(re.findall(r"<[^>]+>", text)) >= 2


def _valid_title(value: Any) -> bool:
    text = str(value or "").strip()
    return (
        len(text) >= 5
        and len(text) <= 500
        and not _is_placeholder_text(text)
        and not _is_contaminated_text(text)
    )


def _valid_description(value: Any) -> bool:
    text = str(value or "").strip()
    return (
        len(text) >= 30
        and len(text) <= 100_000
        and not _is_placeholder_text(text)
        and not _is_contaminated_text(text)
    )


def _number(value: Any) -> Optional[float]:
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _positive_number(value: Any, *, upper: float = 1e15) -> bool:
    number = _number(value)
    return number is not None and 0 < number <= upper


def _valid_coordinate_pair(lat: Any, lon: Any) -> bool:
    latitude = _number(lat)
    longitude = _number(lon)
    if latitude is None or longitude is None:
        return False
    # Argentina plus a small border tolerance; rejects 0/0 and swapped values.
    return -56.5 <= latitude <= -20.0 and -76.5 <= longitude <= -52.0


def clean_images(value: Any) -> List[str]:
    """Return unique, plausible property image URLs without placeholders."""
    raw_values: Iterable[Any]
    if isinstance(value, (list, tuple)):
        raw_values = value
    elif isinstance(value, str):
        raw_values = [value]
    else:
        raw_values = []
    result: List[str] = []
    seen = set()
    for raw in raw_values:
        url = str(raw or "").strip()
        key = url.lower()
        if (
            not key.startswith(("http://", "https://"))
            or key.startswith("data:")
            or _IMAGE_REJECT_RE.search(key)
            or key in seen
        ):
            continue
        seen.add(key)
        result.append(url)
    return result


def _audit(
    field: str,
    old_value: Any,
    new_value: Any,
    decision: str,
    confidence: float,
    reason: str,
) -> Dict[str, Any]:
    if decision not in DECISIONS:
        raise ValueError(f"Unknown merge decision: {decision}")
    return {
        "field": field,
        "old_value": old_value,
        "new_value": new_value,
        "decision": decision,
        "confidence": round(float(confidence), 3),
        "reason": reason,
    }


def _candidate_id(candidate: Mapping[str, Any]) -> str:
    return str(candidate.get("id"))


def resolve_identity(
    incoming: Mapping[str, Any],
    candidates: Sequence[Mapping[str, Any]],
    *,
    source_id: Any,
) -> Dict[str, Any]:
    """Resolve an incoming payload to exactly one compatible database row.

    A missing match is a valid insert only when the incoming agency, canonical
    URL and compatible hash are all present.  Any evidence pointing at more
    than one row, or at another agency/source, rejects the write.
    """
    agency = incoming.get("inmobiliaria_id")
    url_key = incoming.get("url_normalizada") or _normalize_url_for_hash(incoming.get("url"))
    external = _external_key(incoming.get("id_externo"))
    incoming_hash = str(incoming.get("hash_dedup") or "")
    expected_hash = _compute_hash_dedup(agency, incoming.get("url"))
    incoming_source = _source_key(incoming.get("fuente_extraccion"))

    if (
        agency is None
        or str(source_id or "").strip() != str(agency)
        or not url_key
        or not incoming_hash
        or incoming_hash != expected_hash
    ):
        return {
            "status": "rejected",
            "reason": "insufficient_or_incompatible_incoming_identity",
            "candidate_ids": [],
            "audit": [
                _audit(
                    "__identity__",
                    None,
                    {
                        "source_id": str(source_id or ""),
                        "inmobiliaria_id": agency,
                        "url_normalizada": url_key,
                    },
                    REJECTED_AMBIGUOUS_IDENTITY,
                    0.0,
                    "Source, agency, canonical URL and compatible hash must agree.",
                )
            ],
        }

    matched: Dict[str, Mapping[str, Any]] = {}
    cross_property: Dict[str, Mapping[str, Any]] = {}
    for row in candidates:
        row_id = _candidate_id(row)
        row_agency = row.get("inmobiliaria_id")
        row_url = row.get("url_normalizada") or _normalize_url_for_hash(row.get("url"))
        row_external = _external_key(row.get("id_externo"))
        row_hash = str(row.get("hash_dedup") or "")
        same_url = bool(row_url and row_url == url_key)
        same_external = bool(external and row_external and external == row_external)
        same_hash = bool(row_hash and row_hash == incoming_hash)
        if not (same_url or same_external or same_hash):
            continue
        if str(row_agency) != str(agency):
            cross_property[row_id] = row
        else:
            matched[row_id] = row

    if cross_property:
        return {
            "status": "rejected",
            "reason": "canonical_identity_belongs_to_another_agency",
            "candidate_ids": sorted(cross_property),
            "audit": [
                _audit(
                    "__identity__",
                    {"candidate_ids": sorted(cross_property)},
                    {"inmobiliaria_id": agency, "url_normalizada": url_key},
                    REJECTED_CROSS_PROPERTY_CONTAMINATION,
                    0.0,
                    "Canonical URL or another strong identifier belongs to another agency.",
                )
            ],
        }

    if len(matched) > 1:
        return {
            "status": "rejected",
            "reason": "multiple_existing_candidates",
            "candidate_ids": sorted(matched),
            "audit": [
                _audit(
                    "__identity__",
                    {"candidate_ids": sorted(matched)},
                    {"inmobiliaria_id": agency, "url_normalizada": url_key},
                    REJECTED_AMBIGUOUS_IDENTITY,
                    0.0,
                    "Strong identity evidence converged on multiple rows.",
                )
            ],
        }

    if not matched:
        return {
            "status": "insert",
            "reason": "no_existing_identity_match",
            "candidate_ids": [],
            "url_normalizada": url_key,
            "expected_hash": expected_hash,
        }

    selected = next(iter(matched.values()))
    row_url_key = selected.get("url_normalizada") or _normalize_url_for_hash(selected.get("url"))
    row_external = _external_key(selected.get("id_externo"))
    row_hash = str(selected.get("hash_dedup") or "")
    row_source = _source_key(selected.get("fuente_extraccion"))
    contradictions: List[str] = []
    if row_url_key != url_key:
        contradictions.append("url_normalizada")
    if external and row_external and external != row_external:
        contradictions.append("id_externo")
    if row_hash and row_hash != incoming_hash:
        contradictions.append("hash_dedup")
    if incoming_source and row_source and incoming_source != row_source:
        contradictions.append("fuente_extraccion")
    if contradictions:
        return {
            "status": "rejected",
            "reason": "contradictory_identity_evidence",
            "candidate_ids": [_candidate_id(selected)],
            "audit": [
                _audit(
                    "__identity__",
                    {"property_id": selected.get("id")},
                    {"contradictions": contradictions},
                    REJECTED_CROSS_PROPERTY_CONTAMINATION,
                    0.0,
                    "Matched evidence contradicts: " + ", ".join(contradictions),
                )
            ],
        }

    return {
        "status": "matched",
        "reason": "single_compatible_candidate",
        "candidate_ids": [_candidate_id(selected)],
        "property": dict(selected),
        "url_normalizada": url_key,
        "expected_hash": expected_hash,
    }


def _text_decision(field: str, old: Any, new: Any) -> Dict[str, Any]:
    validator = _valid_title if field == "titulo" else _valid_description
    if _is_blank(new):
        return _audit(field, old, new, REJECTED_NULL_DEGRADATION, 0.0, "Incoming value is null or empty.")
    if _is_contaminated_text(new):
        return _audit(
            field,
            old,
            new,
            REJECTED_CROSS_PROPERTY_CONTAMINATION,
            0.0,
            "Incoming text contains navigation, institutional or HTML contamination.",
        )
    if not validator(new):
        return _audit(field, old, new, REJECTED_PLACEHOLDER, 0.1, "Incoming text is generic or invalid.")
    if validator(old) and _plain(old) == _plain(new):
        return _audit(field, old, new, UNCHANGED_EQUAL, 1.0, "Normalized values are equal.")
    if not validator(old):
        return _audit(field, old, new, ACCEPTED_IMPROVEMENT, 0.95, "Valid text fills an absent or invalid value.")

    old_text = _plain(old)
    new_text = _plain(new)
    if field == "descripcion" and old_text in new_text and len(new_text) >= len(old_text) + 30:
        return _audit(field, old, new, ACCEPTED_IMPROVEMENT, 0.9, "Description is a strict, clean superset.")
    if field == "titulo" and old_text in new_text and len(new_text) > len(old_text):
        return _audit(field, old, new, ACCEPTED_IMPROVEMENT, 0.85, "Title adds specific information without removing the old title.")
    return _audit(
        field,
        old,
        new,
        REJECTED_LOWER_CONFIDENCE,
        0.4,
        "Existing valid text is preserved because the incoming replacement is not demonstrably better.",
    )


def _field_decision(
    field: str,
    old: Any,
    new: Any,
    incoming: Mapping[str, Any],
) -> Dict[str, Any]:
    if field in {"titulo", "descripcion"}:
        return _text_decision(field, old, new)

    if field == "imagenes":
        old_clean = clean_images(old)
        new_clean = clean_images(new)
        if not new_clean:
            decision = REJECTED_NULL_DEGRADATION if _is_blank(new) else REJECTED_PLACEHOLDER
            return _audit(field, old, new, decision, 0.0, "No plausible property image remains after sanitization.")
        combined = old_clean + [url for url in new_clean if url.lower() not in {x.lower() for x in old_clean}]
        if combined == old_clean:
            return _audit(field, old, old_clean, UNCHANGED_EQUAL, 1.0, "No new real image was found.")
        return _audit(field, old, combined, ACCEPTED_IMPROVEMENT, 0.95, "Real images are added without removing existing images.")

    if field in {"latitud", "longitud"}:
        old_pair_valid = _valid_coordinate_pair(incoming.get("_old_latitud"), incoming.get("_old_longitud"))
        new_pair_valid = _valid_coordinate_pair(incoming.get("latitud"), incoming.get("longitud"))
        if not new_pair_valid:
            return _audit(field, old, new, REJECTED_PLACEHOLDER, 0.0, "Coordinates are incomplete or outside Argentina.")
        if old_pair_valid:
            if _number(old) == _number(new):
                return _audit(field, old, new, UNCHANGED_EQUAL, 1.0, "Coordinate is equal.")
            return _audit(field, old, new, REJECTED_LOWER_CONFIDENCE, 0.5, "Existing valid coordinate pair is preserved.")
        return _audit(field, old, new, ACCEPTED_IMPROVEMENT, 0.9, "Valid coordinate pair fills an invalid or missing pair.")

    if _is_blank(new):
        return _audit(field, old, new, REJECTED_NULL_DEGRADATION, 0.0, "Incoming value is null or empty.")

    if field == "precio":
        if not _positive_number(new):
            return _audit(field, old, new, REJECTED_PLACEHOLDER, 0.0, "Incoming price is non-positive, non-finite or out of range.")
        incoming_currency = incoming.get("moneda")
        if incoming_currency and str(incoming_currency).upper() not in _VALID_CURRENCIES:
            return _audit(field, old, new, REJECTED_PLACEHOLDER, 0.0, "Incoming price has an unknown currency.")
        if not _positive_number(old):
            return _audit(field, old, new, ACCEPTED_IMPROVEMENT, 0.95, "Valid price fills an absent or invalid price.")
        if _number(old) == _number(new):
            return _audit(field, old, new, UNCHANGED_EQUAL, 1.0, "Numeric prices are equal.")
        return _audit(field, old, new, ACCEPTED_SOURCE_CHANGE, 0.9, "A valid current detail-page price changed.")

    if field == "moneda":
        normalized_new = str(new).upper()
        if normalized_new not in _VALID_CURRENCIES:
            return _audit(field, old, new, REJECTED_PLACEHOLDER, 0.0, "Incoming currency is unknown.")
        normalized_old = str(old or "").upper()
        if normalized_old == normalized_new:
            return _audit(field, old, normalized_new, UNCHANGED_EQUAL, 1.0, "Currencies are equal.")
        if normalized_old not in _VALID_CURRENCIES:
            return _audit(field, old, normalized_new, ACCEPTED_IMPROVEMENT, 0.95, "Valid currency fills an absent or invalid currency.")
        if _positive_number(incoming.get("precio")):
            return _audit(field, old, normalized_new, ACCEPTED_SOURCE_CHANGE, 0.85, "Currency changed together with a valid current price.")
        return _audit(field, old, normalized_new, REJECTED_LOWER_CONFIDENCE, 0.3, "Existing valid currency is preserved.")

    if field in _FILL_ONLY_NUMBERS:
        if not _positive_number(new, upper=10_000_000):
            return _audit(field, old, new, REJECTED_PLACEHOLDER, 0.0, "Incoming numeric value is invalid.")
        if _positive_number(old, upper=10_000_000):
            if _number(old) == _number(new):
                return _audit(field, old, new, UNCHANGED_EQUAL, 1.0, "Numeric values are equal.")
            return _audit(field, old, new, REJECTED_LOWER_CONFIDENCE, 0.5, "Existing valid numeric value is preserved.")
        return _audit(field, old, new, ACCEPTED_IMPROVEMENT, 0.9, "Valid numeric value fills an absent or invalid value.")

    if field in _LOCATION_FIELDS:
        if _is_placeholder_text(new, location=True):
            return _audit(field, old, new, REJECTED_PLACEHOLDER, 0.0, "Incoming location is generic.")
        if _plain(old) == _plain(new):
            return _audit(field, old, new, UNCHANGED_EQUAL, 1.0, "Normalized locations are equal.")
        if _is_placeholder_text(old, location=True):
            return _audit(field, old, new, ACCEPTED_IMPROVEMENT, 0.9, "Specific location fills an absent or generic value.")
        return _audit(field, old, new, REJECTED_LOWER_CONFIDENCE, 0.5, "Existing specific location is preserved.")

    if field == "operacion":
        normalized_new = _plain(new).replace(" ", "_")
        normalized_old = _plain(old).replace(" ", "_")
        if normalized_new not in _VALID_OPERATIONS:
            return _audit(field, old, new, REJECTED_PLACEHOLDER, 0.0, "Incoming operation is outside the approved enum.")
        if normalized_old == normalized_new:
            return _audit(field, old, normalized_new, UNCHANGED_EQUAL, 1.0, "Operations are equal.")
        if normalized_old not in _VALID_OPERATIONS or normalized_old == "consultar":
            return _audit(field, old, normalized_new, ACCEPTED_IMPROVEMENT, 0.9, "Specific valid operation replaces an absent or generic operation.")
        return _audit(field, old, normalized_new, REJECTED_LOWER_CONFIDENCE, 0.5, "Existing specific operation is preserved.")

    if field == "tipo_propiedad":
        normalized_new = _plain(new).replace(" ", "_")
        normalized_old = _plain(old).replace(" ", "_")
        if normalized_new not in _VALID_TYPES:
            return _audit(field, old, new, REJECTED_PLACEHOLDER, 0.0, "Incoming property type is outside the approved enum.")
        if normalized_old == normalized_new:
            return _audit(field, old, normalized_new, UNCHANGED_EQUAL, 1.0, "Property types are equal.")
        if normalized_old not in _VALID_TYPES or normalized_old == "otro":
            return _audit(field, old, normalized_new, ACCEPTED_IMPROVEMENT, 0.9, "Specific valid type replaces an absent or generic type.")
        return _audit(field, old, normalized_new, REJECTED_LOWER_CONFIDENCE, 0.5, "Existing specific type is preserved.")

    return _audit(field, old, new, REJECTED_LOWER_CONFIDENCE, 0.0, "Field has no approved merge rule.")


def build_merge_plan(
    incoming: Mapping[str, Any],
    candidates: Sequence[Mapping[str, Any]],
    *,
    source_id: Any,
) -> Dict[str, Any]:
    """Return a deterministic insert/update/reject plan and per-field audit."""
    normalized_incoming = dict(incoming)
    normalized_incoming["url_normalizada"] = (
        incoming.get("url_normalizada") or _normalize_url_for_hash(incoming.get("url"))
    )
    identity = resolve_identity(normalized_incoming, candidates, source_id=source_id)
    if identity["status"] == "rejected":
        return {**identity, "patch": {}}

    if identity["status"] == "insert":
        payload = prepare_insert_payload(normalized_incoming)
        audit = [
            _audit(
                field,
                None,
                value,
                ACCEPTED_INSERT,
                1.0,
                "New property with unambiguous agency, canonical URL and compatible hash.",
            )
            for field, value in payload.items()
            if field not in {"created_at", "updated_at"} and not _is_blank(value)
        ]
        return {**identity, "payload": payload, "patch": {}, "audit": audit}

    existing = identity["property"]
    decision_input = {
        **normalized_incoming,
        "_old_latitud": existing.get("latitud"),
        "_old_longitud": existing.get("longitud"),
    }
    patch: Dict[str, Any] = {}
    audit: List[Dict[str, Any]] = []
    for field in MERGE_FIELDS:
        if field not in normalized_incoming:
            continue
        entry = _field_decision(field, existing.get(field), normalized_incoming.get(field), decision_input)
        audit.append(entry)
        if entry["decision"] in {ACCEPTED_IMPROVEMENT, ACCEPTED_SOURCE_CHANGE}:
            patch[field] = entry["new_value"]
    return {**identity, "patch": patch, "audit": audit}


def prepare_insert_payload(incoming: Mapping[str, Any]) -> Dict[str, Any]:
    """Sanitize the mutable fields of a new row without inventing data."""
    payload = dict(incoming)
    payload["url_normalizada"] = incoming.get("url_normalizada") or _normalize_url_for_hash(incoming.get("url"))
    payload["hash_dedup"] = _compute_hash_dedup(incoming.get("inmobiliaria_id"), incoming.get("url"))
    if "imagenes" in payload:
        payload["imagenes"] = clean_images(payload.get("imagenes"))
    for text_field, validator in (("titulo", _valid_title), ("descripcion", _valid_description)):
        if text_field in payload and not validator(payload.get(text_field)):
            payload[text_field] = None
    if payload.get("moneda") and str(payload["moneda"]).upper() not in _VALID_CURRENCIES:
        payload["moneda"] = None
    elif payload.get("moneda"):
        payload["moneda"] = str(payload["moneda"]).upper()
    if payload.get("precio") is not None and not _positive_number(payload.get("precio")):
        payload["precio"] = None
    operation = _plain(payload.get("operacion")).replace(" ", "_")
    payload["operacion"] = operation if operation in _VALID_OPERATIONS else None
    property_type = _plain(payload.get("tipo_propiedad")).replace(" ", "_")
    payload["tipo_propiedad"] = property_type if property_type in _VALID_TYPES else "otro"
    if not _valid_coordinate_pair(payload.get("latitud"), payload.get("longitud")):
        payload["latitud"] = None
        payload["longitud"] = None
    return payload
