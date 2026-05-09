"""
clean_pipeline.py
-----------------
Pipeline de limpieza y enriquecimiento de datos para la tabla inmobiliarias_scraping.

Operaciones:
  1. Carga todos los registros de inmobiliarias_scraping
  2. Normaliza nombres (mayúsculas, sin acentos, sin caracteres raros)
  3. Normaliza webs (elimina trailing slash, convierte a lowercase, agrega https:// si falta)
  4. Normaliza teléfonos (solo dígitos, formato argentino)
  5. Convierte rating a NUMERIC y resenas a INTEGER
  6. Detecta categoría (desarrolladora / constructora / inmobiliaria) si está vacía
  7. Deduplica por web (conserva el registro con más datos)
  8. Agrega campos nombre_normalizado y updated_at
  9. Batch upsert de vuelta a Supabase
"""

import os
import re
import unicodedata
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests
from dotenv import load_dotenv

load_dotenv()

# =============================================================================
# CONFIGURACION
# =============================================================================

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
TABLA = "inmobiliarias_scraping"
BATCH_SIZE = 500

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("clean_pipeline")

# =============================================================================
# SUPABASE HELPERS
# =============================================================================

def _headers() -> Dict[str, str]:
    return {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }


def cargar_todos_los_registros() -> List[Dict[str, Any]]:
    """Carga todos los registros de inmobiliarias_scraping."""
    session = requests.Session()
    url = f"{SUPABASE_URL}/rest/v1/{TABLA}"
    params = {"select": "*", "order": "id.asc"}
    headers = {
        **_headers(),
        "Range-Unit": "items",
        "Range": "0-99999",
    }
    resp = session.get(url, headers=headers, params=params, timeout=60)
    resp.raise_for_status()
    registros = resp.json()
    logger.info(f"Registros cargados: {len(registros)}")
    return registros


def upsert_batch(registros: List[Dict[str, Any]]) -> int:
    """Actualiza campos seguros por id (excluye web para evitar conflictos de constraint)."""
    # Campos que pueden tener constraints únicos — no los tocamos
    CAMPOS_EXCLUIDOS = {"id", "web", "nombre", "web_normalizada"}

    ok = 0
    session = requests.Session()
    for r in registros:
        rid = r.get("id")
        if not rid:
            continue
        payload = {k: v for k, v in r.items() if k not in CAMPOS_EXCLUIDOS}
        if not payload:
            continue
        url = f"{SUPABASE_URL}/rest/v1/{TABLA}?id=eq.{rid}"
        resp = session.patch(url, headers=_headers(), json=payload, timeout=30)
        if resp.status_code in (200, 204):
            ok += 1
        else:
            logger.warning(f"Error actualizando id={rid}: {resp.status_code} — {resp.text[:200]}")
    return ok


# =============================================================================
# NORMALIZACION
# =============================================================================

def quitar_acentos(texto: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", texto)
        if unicodedata.category(c) != "Mn"
    )


def normalizar_nombre(nombre: Optional[str]) -> Optional[str]:
    if not nombre:
        return None
    # Quitar espacios extra
    n = " ".join(nombre.strip().split())
    # Eliminar caracteres que no sean letras, números, espacios o &
    n = re.sub(r"[^\w\s&áéíóúüñÁÉÍÓÚÜÑ]", "", n, flags=re.UNICODE)
    # Quitar acentos para el campo normalizado
    n = quitar_acentos(n)
    # Title Case
    n = n.title()
    return n if n else None


def normalizar_web(web: Optional[str]) -> Optional[str]:
    if not web:
        return None
    w = web.strip().lower()
    # Eliminar espacios internos (a veces hay OCR malformado)
    w = w.replace(" ", "")
    # Agregar https:// si falta protocolo
    if w and not w.startswith("http"):
        w = "https://" + w
    # Eliminar trailing slash
    w = w.rstrip("/")
    # Eliminar www. para normalizar duplicados
    w = re.sub(r"^(https?://)www\.", r"\1", w)
    return w if w else None


_RE_NO_DIGIT = re.compile(r"\D")

def normalizar_telefono(tel: Optional[str]) -> Optional[str]:
    if not tel:
        return None
    digits = _RE_NO_DIGIT.sub("", tel)
    if not digits:
        return None
    # Argentina: los números internos tienen 10 dígitos (sin 0 y sin 15)
    # Si comienza con 549 (whatsapp style) → dejar
    # Si comienza con 54 y tiene 12 dígitos → dejar
    # Si tiene 10 dígitos → agregar +54
    # Si tiene 11 dígitos y empieza con 0 → quitar el 0, agregar +54
    if len(digits) == 10:
        return f"+54{digits}"
    if len(digits) == 11 and digits.startswith("0"):
        return f"+54{digits[1:]}"
    if len(digits) == 12 and digits.startswith("54"):
        return f"+{digits}"
    if len(digits) == 13 and digits.startswith("549"):
        return f"+{digits}"
    # Para números fuera de rango esperado, devolver los dígitos tal cual
    return digits if len(digits) >= 7 else None


def normalizar_rating(rating: Any) -> Optional[float]:
    if rating is None:
        return None
    try:
        v = float(str(rating).replace(",", "."))
        return round(v, 1) if 0 <= v <= 5 else None
    except (ValueError, TypeError):
        return None


def normalizar_resenas(resenas: Any) -> Optional[int]:
    if resenas is None:
        return None
    try:
        digits = _RE_NO_DIGIT.sub("", str(resenas))
        return int(digits) if digits else None
    except (ValueError, TypeError):
        return None


# =============================================================================
# DETECCION DE CATEGORIA
# =============================================================================

_PALABRAS_DESARROLLADORA = [
    "desarrolladora", "desarrollos", "developer", "emprendimiento",
    "emprendimientos", "fideicomiso", "inmobiliaria desarrolladora",
]
_PALABRAS_CONSTRUCTORA = [
    "constructora", "construccion", "construcciones", "empresa constructora",
    "contractor", "obra", "obras", "ingenieria", "arquitectura",
]
_PALABRAS_INMOBILIARIA = [
    "inmobiliaria", "real estate", "broker", "agencia inmobiliaria",
    "agencia", "propiedades",
]


def detectar_categoria(
    nombre: Optional[str],
    categoria_actual: Optional[str],
    fuente: Optional[str],
) -> str:
    """Infiere categoría desde nombre si la actual está vacía o genérica."""
    if categoria_actual and categoria_actual.lower() not in ("", "inmobiliaria", "none"):
        return categoria_actual

    texto = (nombre or "").lower()
    texto_sin_acentos = quitar_acentos(texto)

    for p in _PALABRAS_DESARROLLADORA:
        if p in texto_sin_acentos:
            return "desarrolladora"
    for p in _PALABRAS_CONSTRUCTORA:
        if p in texto_sin_acentos:
            return "constructora"
    for p in _PALABRAS_INMOBILIARIA:
        if p in texto_sin_acentos:
            return "inmobiliaria"

    # Fallback por fuente
    if fuente == "zonaprop":
        return "inmobiliaria"
    if fuente == "google_lugares":
        return "inmobiliaria"
    return "inmobiliaria"


# =============================================================================
# DEDUPLICACION POR WEB
# =============================================================================

def _completitud(registro: Dict[str, Any]) -> int:
    """Cuenta campos no vacíos — más alto = más completo."""
    campos = ["nombre", "web", "telefono", "email", "direccion", "ciudad",
              "provincia", "rating", "resenas", "categoria", "logo"]
    return sum(1 for c in campos if registro.get(c))


def deduplicar_por_web(registros: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Cuando dos registros tienen la misma web normalizada, conserva el más completo."""
    por_web: Dict[str, Dict[str, Any]] = {}
    sin_web: List[Dict[str, Any]] = []

    for r in registros:
        web = r.get("web_normalizada") or r.get("web")
        if not web:
            sin_web.append(r)
            continue
        if web not in por_web:
            por_web[web] = r
        else:
            existente = por_web[web]
            if _completitud(r) > _completitud(existente):
                # Conservar el id del existente para hacer update en lugar de insert
                r["id"] = existente.get("id", r.get("id"))
                por_web[web] = r
            else:
                # Conservar el existente pero marcar para eliminar duplicado
                pass

    resultado = list(por_web.values()) + sin_web
    return resultado


# =============================================================================
# PIPELINE PRINCIPAL
# =============================================================================

def limpiar_registro(r: Dict[str, Any]) -> Dict[str, Any]:
    nombre_norm = normalizar_nombre(r.get("nombre"))
    web_norm = normalizar_web(r.get("web"))
    telefono_norm = normalizar_telefono(r.get("telefono"))
    rating_norm = normalizar_rating(r.get("rating"))
    resenas_norm = normalizar_resenas(r.get("resenas"))
    categoria_norm = detectar_categoria(
        r.get("nombre"),
        r.get("categoria"),
        r.get("fuente"),
    )

    return {
        **r,
        "nombre_normalizado": nombre_norm,
        # web NO se modifica para evitar conflictos con constraint uq_scraping_web
        # web_normalizada se usa solo internamente para deduplicación
        "web_normalizada": web_norm or r.get("web"),
        "telefono": telefono_norm or r.get("telefono"),
        "rating": rating_norm,
        "resenas": resenas_norm,
        "categoria": categoria_norm,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def run():
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        logger.error("Faltan variables de entorno SUPABASE_URL o SUPABASE_SERVICE_ROLE_KEY")
        return

    logger.info("=== Iniciando clean_pipeline ===")

    # 1. Cargar
    registros = cargar_todos_los_registros()
    if not registros:
        logger.warning("No hay registros para limpiar.")
        return

    # 2. Limpiar cada registro
    logger.info("Limpiando y normalizando registros...")
    limpios = [limpiar_registro(r) for r in registros]

    # 3. Deduplicar por web
    antes = len(limpios)
    limpios = deduplicar_por_web(limpios)
    despues = len(limpios)
    logger.info(f"Deduplicación por web: {antes} → {despues} registros ({antes - despues} duplicados eliminados)")

    # 4. Preparar payload para upsert (excluir campo auxiliar web_normalizada si no existe en la tabla)
    for r in limpios:
        r.pop("web_normalizada", None)

    # 5. Batch upsert
    total = 0
    for i in range(0, len(limpios), BATCH_SIZE):
        lote = limpios[i : i + BATCH_SIZE]
        n = upsert_batch(lote)
        total += n
        logger.info(f"  Lote {i // BATCH_SIZE + 1}: {n}/{len(lote)} registros procesados")

    logger.info(f"=== Pipeline completado: {total} registros actualizados ===")


if __name__ == "__main__":
    run()
