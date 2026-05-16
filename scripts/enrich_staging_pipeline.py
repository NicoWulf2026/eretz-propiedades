"""
Pipeline seguro para enriquecer inmobiliarias_staging.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import random
import re
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None


ROOT = Path(__file__).resolve().parents[1]
TABLA = "inmobiliarias_staging"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("enrich_staging")


# =============================================================================
# CONSTANTS & RULES
# =============================================================================

_INVALID_DOMAINS = {
    "zonaprop.com.ar", "argenprop.com", "mercadolibre.com.ar", "mercadolibre.com",
    "facebook.com", "instagram.com", "twitter.com", "x.com", "linkedin.com",
    "youtube.com", "tiktok.com", "google.com", "linktr.ee", "wa.me", "whatsapp.com",
    "gmail.com", "hotmail.com", "outlook.com", "yahoo.com"
}

_CMS_SIGNATURES = {
    "tokko": ["tokkobroker.com", "TokkoWidget", "tokko_key", "api.tokkobroker"],
    "wordpress": ["wp-content/", "wp-includes/"],
    "wix": ["wix.com", "wixsite.com"],
    "realhomes": ["realhomes"],
}

_RE_DIGITS = re.compile(r"\D")
_RE_EMAIL = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
_RE_TEL = re.compile(
    r"(?:\+54|0054|011|0\d{2,4})[\s\-]?(?:15[\s\-]?)?\d{4}[\s\-]?\d{4}"
    r"|\+54\s?9?\s?\d{2,4}[\s\-]?\d{4}[\s\-]?\d{4}"
    r"|\(\d{2,4}\)\s?\d{4}[\s\-]?\d{4}"
)

# =============================================================================
# MODELS
# =============================================================================

@dataclass
class EnrichReport:
    registros_leidos: int = 0
    procesados: int = 0
    enriquecidos: int = 0
    requieren_revision: int = 0
    sin_resultados: int = 0
    errores: int = 0
    ejemplos_enriquecidos: List[Dict[str, Any]] = field(default_factory=list)
    ejemplos_requieren_revision: List[Dict[str, Any]] = field(default_factory=list)
    ejemplos_sin_resultados: List[Dict[str, Any]] = field(default_factory=list)

    def add_example(self, key: str, val: Dict[str, Any], limit: int = 5):
        lst = getattr(self, key)
        if len(lst) < limit:
            lst.append(val)

# =============================================================================
# UTILS
# =============================================================================

def load_env() -> Tuple[str, str]:
    if load_dotenv is not None:
        load_dotenv(ROOT / ".env")
    url = os.getenv("SUPABASE_URL", "").rstrip("/")
    key = (
        os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        or os.getenv("SUPABASE_KEY")
        or os.getenv("SUPABASE_ANON_KEY")
        or ""
    )
    if not url or not key:
        raise RuntimeError("Faltan SUPABASE_URL / SUPABASE_KEY en .env")
    return url, key

def make_session() -> requests.Session:
    s = requests.Session()
    s.trust_env = False
    return s

def headers(key: str, prefer: str = "return=minimal") -> Dict[str, str]:
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": prefer,
    }

def clean_spaces(val: Any) -> str:
    return re.sub(r"\s+", " ", str(val or "")).strip()

def normalizar_nombre_clave(nombre: str) -> str:
    n = unicodedata.normalize("NFKD", nombre.lower())
    n = "".join(c for c in n if not unicodedata.combining(c))
    n = re.sub(r"\b(s\.?a\.?|s\.?r\.?l\.?|inmobiliaria|propiedades|negocios|bienes raices|broker)\b", "", n)
    return re.sub(r"[^\w]", "", n)

def similitud(a: str, b: str) -> float:
    return SequenceMatcher(None, normalizar_nombre_clave(a), normalizar_nombre_clave(b)).ratio()

def is_valid_web(url: str) -> bool:
    if not url: return False
    try:
        p = urlparse(url if url.startswith("http") else f"https://{url}")
        domain = p.netloc.lower().replace("www.", "")
        if domain in _INVALID_DOMAINS:
            return False
        # Also check partials like google.com/maps
        for d in _INVALID_DOMAINS:
            if domain.endswith("." + d) or domain == d:
                return False
        return len(domain) > 3 and "." in domain
    except:
        return False

def extract_phone(text: str) -> Optional[str]:
    phones = _RE_TEL.findall(text)
    if phones:
        return re.sub(r"\D", "", phones[0])
    return None

# =============================================================================
# SUPABASE FETCH
# =============================================================================

def fetch_pending(session: requests.Session, base_url: str, key: str, source: str = None, limit: int = 5) -> List[Dict]:
    params = {
        "select": "*",
        "estado_scraping": "eq.pendiente_enriquecimiento",
        "order": "id.asc",
        "limit": limit
    }
    if source:
        params["fuente"] = f"eq.{source}"
        
    resp = session.get(
        f"{base_url}/rest/v1/{TABLA}",
        headers=headers(key),
        params=params,
        timeout=30
    )
    resp.raise_for_status()
    return resp.json()

# =============================================================================
# ENRICHMENT LOGIC
# =============================================================================

def enrich_web(url: str) -> Dict[str, Any]:
    res = {}
    if not url.startswith("http"):
        url = "https://" + url
    try:
        r = requests.get(
            url, 
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}, 
            timeout=10,
            allow_redirects=True
        )
        if r.status_code == 200:
            html = r.text
            res["html_fetched"] = True
            
            # Detect CMS
            cms = []
            for name, sigs in _CMS_SIGNATURES.items():
                if any(s in html for s in sigs):
                    cms.append(name)
            if cms:
                res["cms_detectado"] = cms[0]
                
            # Phones
            soup = BeautifulSoup(html, "html.parser")
            text = soup.get_text(" ")
            
            p = extract_phone(text)
            if p: res["phone_candidate"] = p
            
            # Emails
            emails = _RE_EMAIL.findall(text)
            emails = [e.lower() for e in emails if not any(x in e.lower() for x in [".png", ".jpg", "example", "wixpress"])]
            if emails:
                res["email_candidate"] = list(set(emails))[0]
    except Exception as e:
        log.debug(f"Error fetching web {url}: {e}")
    return res

def enrich_google_maps(pw_page, nombre: str, ciudad: str, provincia: str) -> Dict[str, Any]:
    query = f"{nombre} {ciudad or ''} {provincia or ''} inmobiliaria".strip()
    url = f"https://www.google.com/maps/search/{requests.utils.quote(query)}"
    
    res = {"google_maps_query": query}
    try:
        pw_page.goto(url, timeout=20000, wait_until="domcontentloaded")
        pw_page.wait_for_timeout(2500)
        
        # Click first result if list
        primer_resultado = pw_page.locator("a[href*='/maps/place/']").first
        if primer_resultado.count() > 0:
            primer_resultado.click()
            pw_page.wait_for_timeout(2000)
            
        # Get Name
        try:
            name_el = pw_page.locator("h1").first
            if name_el.count() > 0:
                res["google_maps_name"] = name_el.inner_text().strip()
        except: pass
        
        # Check similarity
        if res.get("google_maps_name"):
            sim = similitud(nombre, res["google_maps_name"])
            if sim < 0.6:
                res["similarity_warning"] = True
                res["rejection_reasons"] = ["Low name similarity in Google Maps"]
        
        # Extract Web
        for sel in ["a[data-item-id='authority']", "a[aria-label*='Sitio web']"]:
            try:
                el = pw_page.locator(sel).first
                if el.count() > 0:
                    href = el.get_attribute("href")
                    if href and is_valid_web(href):
                        res["website_candidate"] = href
                        break
            except: pass
            
        # Extract Phone
        for sel in ["button[data-item-id^='phone']", "button[aria-label*='Teléfono']"]:
            try:
                el = pw_page.locator(sel).first
                if el.count() > 0:
                    txt = el.get_attribute("aria-label") or el.inner_text()
                    phone = re.sub(r"\D", "", txt)
                    if len(phone) >= 7:
                        res["phone_candidate"] = phone
                        break
            except: pass
            
        # Extract Address
        try:
            el = pw_page.locator("button[data-item-id='address']").first
            if el.count() > 0:
                addr = el.get_attribute("aria-label") or el.inner_text()
                addr = addr.replace("Dirección:", "").strip()
                if addr:
                    res["address_candidate"] = addr
        except: pass

        res["google_maps_url"] = pw_page.url
        
    except Exception as e:
        log.warning(f"Error en Google Maps para {query}: {e}")
        res["error"] = str(e)
        
    return res

def verify_website_candidate(url: str, name: str, phone: Optional[str], address: Optional[str]) -> bool:
    try:
        domain = urlparse(url if url.startswith("http") else "https://" + url).netloc.lower()
        
        # 1. Check domain for name tokens
        # Exclude common noisy words
        ignore_words = {"inmobiliaria", "propiedades", "bienes", "raices", "broker", "estudio", "negocios", "real", "estate", "grupo", "consultora", "inversiones"}
        name_tokens = [w for w in re.sub(r"[^\w\s]", "", name.lower()).split() if len(w) >= 3 and w not in ignore_words]
        
        for t in name_tokens:
            if t in domain:
                return True
                
        # 2. Fetch HTML to find strong signals
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10, allow_redirects=True)
        if r.status_code == 200:
            text = BeautifulSoup(r.text, "html.parser").get_text(" ").lower()
            text_digits = re.sub(r"\D", "", text)
            
            # Check original name
            if name.lower() in text:
                return True
                
            # Check name tokens (require at least 4 chars to be safe)
            for t in name_tokens:
                if len(t) >= 4 and t in text:
                    return True
                    
            # Check phone
            if phone:
                p_digits = re.sub(r"\D", "", str(phone))
                if len(p_digits) >= 6 and p_digits[-6:] in text_digits:
                    return True
                    
            # Check keywords
            keywords = ["inmobiliaria", "propiedades", "real estate", "bienes raíces", "bienes raices"]
            if any(k in text for k in keywords):
                return True
                
        return False
    except Exception as e:
        log.debug(f"Error verificando candidate web {url}: {e}")
        return False

def process_record(record: Dict[str, Any], pw_page, skip_maps: bool) -> Dict[str, Any]:
    nombre = clean_spaces(record.get("nombre"))
    ciudad = clean_spaces(record.get("ciudad"))
    prov = clean_spaces(record.get("provincia"))
    web = clean_spaces(record.get("web"))
    
    enrich_data = {
        "enriched_at": datetime.now(timezone.utc).isoformat(),
        "source_script": "enrich_staging_pipeline.py",
        "accepted_fields": [],
        "rejected_fields": [],
        "rejection_reasons": []
    }
    
    confidence = 0
    updates = {}
    
    # 1. Existing web enrichment
    if web and is_valid_web(web):
        web_info = enrich_web(web)
        confidence += 30
        if "phone_candidate" in web_info and not record.get("telefono"):
            updates["telefono"] = web_info["phone_candidate"]
            enrich_data["accepted_fields"].append("telefono")
            confidence += 20
        if "email_candidate" in web_info:
            enrich_data["email_candidate"] = web_info["email_candidate"]
        if "cms_detectado" in web_info:
            enrich_data["cms_detectado"] = web_info["cms_detectado"]
            
    # 2. Maps enrichment if missing data
    elif not skip_maps:
        if not ciudad and not prov:
            enrich_data["rejection_reasons"].append("Falta ciudad y provincia para búsqueda segura")
        else:
            maps_info = enrich_google_maps(pw_page, nombre, ciudad, prov)
            enrich_data.update(maps_info)
            
            sim_warning = maps_info.get("similarity_warning", False)
            
            if not sim_warning:
                if maps_info.get("website_candidate"):
                    candidate_web = maps_info["website_candidate"]
                    is_web_confirmed = verify_website_candidate(candidate_web, nombre, record.get("telefono"), record.get("direccion"))
                    
                    if is_web_confirmed:
                        updates["web"] = candidate_web
                        enrich_data["accepted_fields"].append("web")
                        confidence += 40
                    else:
                        enrich_data["rejected_fields"].append("web")
                        enrich_data["rejection_reasons"].append("Website domain/content does not confirm official agency")
                        confidence -= 10
                        
                if maps_info.get("phone_candidate") and not record.get("telefono"):
                    updates["telefono"] = maps_info["phone_candidate"]
                    enrich_data["accepted_fields"].append("telefono")
                    confidence += 30
                if maps_info.get("address_candidate") and not record.get("direccion"):
                    updates["direccion"] = maps_info["address_candidate"]
                    enrich_data["accepted_fields"].append("direccion")
                    confidence += 20
            else:
                enrich_data["rejected_fields"] = ["web", "telefono", "direccion"]

    # Basic validations
    if updates.get("web"):
        # Double check validity
        if not is_valid_web(updates["web"]):
            del updates["web"]
            enrich_data["accepted_fields"].remove("web")
            enrich_data["rejected_fields"].append("web")
            enrich_data["rejection_reasons"].append("Web detectada es portal o red social")
            confidence -= 40

    if record.get("telefono") or updates.get("telefono"):
        confidence += 30
    if record.get("direccion") or updates.get("direccion"):
        confidence += 20

    enrich_data["confidence_score"] = min(100, confidence)
    
    # State evaluation
    if updates.get("web") and confidence >= 60:
        updates["estado_scraping"] = "enriquecido"
        updates["needs_manual_review"] = False
    elif (updates.get("telefono") or updates.get("direccion") or updates.get("web")) and confidence < 60:
        updates["estado_scraping"] = "requiere_revision_enriquecimiento"
        updates["needs_manual_review"] = True
    elif not updates:
        updates["estado_scraping"] = "sin_resultados_enriquecimiento"
        updates["needs_manual_review"] = True
    else:
        updates["estado_scraping"] = "requiere_revision_enriquecimiento"
        updates["needs_manual_review"] = True
        
    updates["revision_notas"] = f"Confidence: {confidence}. Motivos rechazo: {', '.join(enrich_data['rejection_reasons'])}"

    # Merge metadata
    meta = record.get("metadata_zonaprop") or {}
    meta["enrichment"] = enrich_data
    updates["metadata_zonaprop"] = meta

    return updates

# =============================================================================
# CLI
# =============================================================================

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", default=True, help="Por defecto TRUE")
    parser.add_argument("--commit", action="store_true", help="Guardar en BD")
    parser.add_argument("--limit", type=int, default=5, help="Límite de registros")
    parser.add_argument("--source", type=str, help="Filtrar por fuente")
    parser.add_argument("--batch-size", type=int, default=50)
    parser.add_argument("--skip-google-maps", action="store_true")
    parser.add_argument("--headful", action="store_true")
    
    args = parser.parse_args()
    if args.commit:
        args.dry_run = False
    return args

def main() -> int:
    args = parse_args()
    base_url, key = load_env()
    session = make_session()
    
    log.info(f"Modo: {'DRY-RUN' if args.dry_run else 'COMMIT'}")
    log.info(f"Target: {TABLA} (limit {args.limit})")
    if args.source: log.info(f"Fuente: {args.source}")
    
    records = fetch_pending(session, base_url, key, args.source, args.limit)
    log.info(f"Recuperados {len(records)} pendientes de enriquecimiento.")
    
    if not records:
        log.info("Nada que procesar.")
        return 0
        
    report = EnrichReport(registros_leidos=len(records))
    
    pw = None
    browser = None
    pw_page = None
    
    if not args.skip_google_maps:
        from playwright.sync_api import sync_playwright
        pw = sync_playwright().start()
        browser = pw.chromium.launch(headless=not args.headful)
        ctx = browser.new_context(locale="es-AR", viewport={"width": 1280, "height": 800})
        pw_page = ctx.new_page()

    try:
        for idx, rec in enumerate(records, 1):
            rid = rec["id"]
            nombre = rec.get("nombre", f"ID {rid}")
            log.info(f"[{idx}/{len(records)}] Procesando: {nombre}")
            
            try:
                updates = process_record(rec, pw_page, args.skip_google_maps)
                report.procesados += 1
                
                estado = updates.get("estado_scraping")
                if estado == "enriquecido":
                    report.enriquecidos += 1
                    report.add_example("ejemplos_enriquecidos", {"id": rid, "nombre": nombre, "updates": updates})
                elif estado == "requiere_revision_enriquecimiento":
                    report.requieren_revision += 1
                    report.add_example("ejemplos_requieren_revision", {"id": rid, "nombre": nombre, "updates": updates})
                else:
                    report.sin_resultados += 1
                    report.add_example("ejemplos_sin_resultados", {"id": rid, "nombre": nombre, "updates": updates})
                    
                if not args.dry_run:
                    resp = session.patch(
                        f"{base_url}/rest/v1/{TABLA}?id=eq.{rid}",
                        headers=headers(key),
                        json=updates,
                        timeout=30
                    )
                    resp.raise_for_status()
                    
            except Exception as e:
                report.errores += 1
                log.error(f"Error procesando {rid}: {e}")
                
            if not args.skip_google_maps:
                time.sleep(random.uniform(1, 3))
                
    finally:
        if browser: browser.close()
        if pw: pw.stop()

    print("\n" + "="*50)
    print("REPORTE FINAL")
    print("="*50)
    
    out = {
        "modo": "dry-run" if args.dry_run else "commit",
        "registros_leidos": report.registros_leidos,
        "procesados": report.procesados,
        "enriquecidos": report.enriquecidos,
        "requieren_revision": report.requieren_revision,
        "sin_resultados": report.sin_resultados,
        "errores": report.errores,
        "ejemplos_enriquecidos": report.ejemplos_enriquecidos,
        "ejemplos_requieren_revision": report.ejemplos_requieren_revision,
        "ejemplos_sin_resultados": report.ejemplos_sin_resultados
    }
    print(json.dumps(out, indent=2, ensure_ascii=False))
    
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
