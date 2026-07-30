import logging
import re
import requests
import unicodedata
from html import unescape
from typing import Optional, List, Dict, Any
from urllib.parse import unquote, urljoin, urlparse

from bs4 import BeautifulSoup
from scraper.network_security import secure_get

logger = logging.getLogger(__name__)


class DataCleaner:
    USD_PATTERNS = [r"\bUSD\b", r"\bUS\$\b", r"\bU\$S\b", r"\bDÓLAR\b", r"\bDOLAR\b"]
    ARS_PATTERNS = [r"\bARS\b", r"\bPESO\b", r"\bPESOS\b"]
    ADDRESS_BLACKLIST = ["LOCAL", "GALERIA", "TORRE", "OFICINA", "EDIFICIO"]
    NEIGHBORHOOD_ALIASES = {
        "microcentro": "Centro",
        "centro": "Centro",
        "barrio norte": "Barrio Norte",
        "barrio sur": "Barrio Sur",
        "candioti norte": "Candioti Norte",
        "candioti sur": "Candioti Sur",
        "alto verde": "Alto Verde",
        "constitucion": "Constitución",
    }

    @staticmethod
    def clean_price(texto: Optional[str]) -> tuple[Optional[int], Optional[str]]:
        if not texto or not isinstance(texto, str):
            return None, None
        texto_upper = texto.strip().upper()
        if "CONSULTAR" in texto_upper or "A CONSULTAR" in texto_upper:
            return None, None
        moneda = None
        if any(re.search(patron, texto_upper) for patron in DataCleaner.USD_PATTERNS):
            moneda = "USD"
        elif any(re.search(patron, texto_upper) for patron in DataCleaner.ARS_PATTERNS):
            moneda = "ARS"
        elif "$" in texto_upper:
            moneda = "ARS"
        # Intentar formato con separadores de miles (ej: 1.200.000) primero.
        # Si no tiene separadores, caer a dígitos planos (ej: 280000).
        # El orden importa: \d{1,3}(?:[.,]\d{3})* matchearia "280" de "280000"
        # en lugar de "280000" completo, por eso se requiere al menos UN grupo.
        match = (
            re.search(r"\d{1,3}(?:[.,]\d{3})+(?:[.,]\d+)?", texto)  # 1.200.000
            or re.search(r"\d+", texto)  # 280000 (sin separadores)
        )
        if not match:
            return None, moneda
        raw_value = match.group(0).replace(".", "").replace(",", "")
        try:
            precio = int(raw_value)
        except ValueError:
            return None, moneda
        if precio <= 0 or precio > 100_000_000_000:
            return None, moneda
        return precio, moneda

    @staticmethod
    def clean_visible_text(texto: Optional[str]) -> Optional[str]:
        """Return human-visible text, stripping residual HTML and compacting whitespace."""
        if not texto or not isinstance(texto, str):
            return None
        value = unescape(texto)
        if "<" in value and ">" in value:
            value = BeautifulSoup(value, "html.parser").get_text(" ", strip=True)
        value = re.sub(r"\s+", " ", value).strip()
        return value or None

    @staticmethod
    def is_generic_title(texto: Optional[str]) -> bool:
        value = DataCleaner.clean_visible_text(texto)
        if not value:
            return True
        normalized = unicodedata.normalize("NFKD", value.lower())
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

    @staticmethod
    def title_from_url(url: Optional[str]) -> Optional[str]:
        if not url or not isinstance(url, str):
            return None
        try:
            path = unquote(urlparse(url).path or "")
        except Exception:
            path = str(url)
        slug = path.rstrip("/").rsplit("/", 1)[-1]
        if not slug:
            return None
        if re.fullmatch(r"\d{2,}", slug):
            return f"Propiedad {slug}"[:150]
        slug = re.sub(r"\.(?:html?|php|aspx?)$", "", slug, flags=re.I)
        parts = [p for p in re.split(r"[-_+\s]+", slug) if p and not p.isdigit()]
        title = " ".join(parts).strip()
        if len(title) < 3:
            return None
        return DataCleaner.standardize_capitalization(title)[:150]

    @staticmethod
    def clean_title(texto: Optional[str], url: Optional[str] = None) -> Optional[str]:
        value = DataCleaner.clean_visible_text(texto)
        if value:
            value = re.sub(
                r"\b(?:id|c[oó]digo|codigo)\s+(?:del\s+)?(?:inmueble|propiedad)\s*[:#-]?\s*[a-z0-9-]+",
                " ",
                value,
                flags=re.I,
            )
            value = re.sub(r"\b(?:USD|US\$|U\$S|ARS)\b\s*[\d.,]+", " ", value, flags=re.I)
            value = re.sub(r"\$+\s*[\d.,]+", " ", value)
            value = re.sub(r"\s+", " ", value).strip(" -|")
        if not value or len(value) < 3 or DataCleaner.is_generic_title(value):
            value = DataCleaner.title_from_url(url)
        return value[:200] if value else None

    @staticmethod
    def clean_description(texto: Optional[str], max_length: int = 3000) -> Optional[str]:
        value = DataCleaner.clean_visible_text(texto)
        if not value or len(value) < 20:
            return None
        return value[:max_length]

    @staticmethod
    def clean_address(texto: Optional[str]) -> Optional[str]:
        if not texto or not isinstance(texto, str):
            return None
        direccion = texto.split("-")[0].strip()
        for palabra in DataCleaner.ADDRESS_BLACKLIST:
            direccion = re.sub(rf"\b{palabra}\b", "", direccion, flags=re.IGNORECASE)
        direccion = re.sub(r"[\s,]+", " ", direccion).strip()
        if len(direccion) < 5:
            return None
        return direccion

    @staticmethod
    def normalize_text(texto: Optional[str]) -> Optional[str]:
        if not texto or not isinstance(texto, str):
            return None
        return texto.strip().lower()

    @staticmethod
    def standardize_capitalization(texto: str) -> str:
        return " ".join(word.capitalize() for word in texto.split())

    @staticmethod
    def normalize_neighborhood(texto: Optional[str]) -> Optional[str]:
        normalized = DataCleaner.normalize_text(texto)
        if not normalized:
            return None
        normalized = re.sub(r"\s+", " ", normalized).strip()
        if normalized in DataCleaner.NEIGHBORHOOD_ALIASES:
            return DataCleaner.NEIGHBORHOOD_ALIASES[normalized]
        return DataCleaner.standardize_capitalization(normalized)

    @staticmethod
    def extract_neighborhood(location_text: Optional[str]) -> Optional[str]:
        if not location_text or not isinstance(location_text, str):
            return None
        barrio = (
            location_text.split("-")[-1].strip()
            if "-" in location_text
            else location_text.strip()
        )
        barrio = re.sub(r"\s+", " ", barrio).strip()
        return barrio if barrio else None

    @staticmethod
    def normalize_property_type_token(token: str) -> str:
        token = token.lower().strip()
        if token in {"departamento", "depto", "ph", "departamento interno", "departamentointerno", "monoambiente", "piso", "apt", "flat"}:
            return "departamento"
        if token in {"casa", "chalet", "casa quinta", "quinta", "casas",
                     "duplex", "dúplex", "triplex", "tríplex"}:
            return "casa"
        if token in {"terreno", "lote", "loteo", "parcela", "solar", "terrenos/lotes", "terrenos"}:
            return "terreno"
        if token in {"local", "local comercial", "negocio", "locales"}:
            return "local"
        if token in {"oficina", "oficina comercial", "office", "oficinas"}:
            return "oficina"
        if token in {"cochera", "garage", "garaje", "cocheras"}:
            return "cochera"
        if token in {"galpon", "galpón", "galpones"}:
            return "galpon"
        return "otro"

    @staticmethod
    def extract_property_type_from_html(soup: Optional[BeautifulSoup]) -> Optional[str]:
        if not soup:
            return None
        mapping = {
            "local-comercial": "local",
            "departamento": "departamento",
            "casa": "casa",
            "oficina": "oficina",
            "terreno": "terreno",
            "cochera": "cochera",
        }
        for element in soup.find_all(attrs={"class": True}):
            classes = element.get("class", [])
            for cls in classes:
                if cls.startswith("tipo-"):
                    tipo_raw = cls.replace("tipo-", "").strip()
                    tipo = mapping.get(tipo_raw)
                    if tipo:
                        return tipo
                    tipo_normalizado = DataCleaner.normalize_property_type_token(tipo_raw)
                    if tipo_normalizado != "otro":
                        return tipo_normalizado
                if cls.startswith("property_types-"):
                    tipo_raw = cls.replace("property_types-", "").strip()
                    tipo = mapping.get(tipo_raw)
                    if tipo:
                        return tipo
                    return DataCleaner.normalize_property_type_token(tipo_raw)
        return None

    @staticmethod
    def extract_operation_from_html(soup: Optional[BeautifulSoup]) -> Optional[str]:
        if not soup:
            return None
        for element in soup.find_all(attrs={"class": True}):
            classes = element.get("class", [])
            for cls in classes:
                if cls.startswith("operacion-"):
                    operacion_raw = cls.replace("operacion-", "").strip()
                    if operacion_raw == "venta":
                        return "venta"
                    if operacion_raw == "alquiler":
                        return "alquiler"
        return None

    @staticmethod
    def detect_operation_from_text(texto: Optional[str], descripcion: Optional[str] = None) -> Optional[str]:
        contenido = " ".join(filter(None, [texto, descripcion])).lower()
        if "alquiler" in contenido:
            return "alquiler"
        if "venta" in contenido:
            return "venta"
        return None

    @staticmethod
    def detect_property_type(texto: Optional[str], descripcion: Optional[str] = None) -> str:
        contenido = " ".join(filter(None, [texto, descripcion])).lower()
        contenido = re.sub(r"[^a-z0-9áéíóúüñ\s]", " ", contenido)
        patrones_ordenados = [
            ("departamento", [r"\bmonoambiente\b", r"\bsemipiso\b", r"\bph\b", r"\bdepartamento interno\b", r"\bdepto\b", r"\bdepartamento\b", r"\bapt\b", r"\bflat\b", r"\bpiso\b"]),
            ("casa", [r"\bcasa quinta\b", r"\bquinta\b", r"\bchalet\b", r"\bduplex\b", r"\bdúplex\b", r"\btriplex\b", r"\btríplex\b", r"\bcasa\b"]),
            ("terreno", [r"\bterreno\b", r"\bloteo\b", r"\blote\b", r"\bparcela\b", r"\bsolar\b"]),
            ("local", [r"\blocal comercial\b", r"\bnegocio\b", r"\blocal\b"]),
            ("oficina", [r"\boficina comercial\b", r"\boficina\b", r"\boffice\b"]),
            ("cochera", [r"\bcochera\b", r"\bgarage\b", r"\bgaraje\b"]),
            ("galpon", [r"\bgalp[oó]n\b"]),
        ]
        for tipo, expresiones in patrones_ordenados:
            for expr in expresiones:
                if re.search(expr, contenido):
                    return tipo
        return "otro"

    @staticmethod
    def extract_area_m2(texto: Optional[str]) -> Optional[int]:
        if not texto or not isinstance(texto, str):
            return None
        match = re.search(r"(\d{1,4})\s*(?:m2|m²|mts2|metros cuadrados)\b", texto.lower())
        if not match:
            return None
        try:
            area = int(match.group(1))
            return area if 10 <= area <= 10000 else None
        except ValueError:
            return None


class DetailExtractor:
    DESCRIPTION_SELECTORS = [
        ".entry-content",
        ".rh_page__property_description",
        ".description",
        "[class*='description']",
        ".entry",
        ".content",
    ]

    IMAGE_SELECTORS = [
        "#gallery img",
        ".gallery img",
        ".rh_slider img",
        ".slider img",
        ".carousel img",
        "article img",
    ]

    def __init__(self, session: requests.Session) -> None:
        self.session = session

    def fetch_detail(self, url: str) -> Dict[str, Any]:
        try:
            response = secure_get(self.session, url, timeout=(8, 15))
            response.raise_for_status()
        except requests.RequestException as exc:
            logger.warning(f"Error HTTP obteniendo detalle {url}: {exc}")
            return {}
        try:
            soup = BeautifulSoup(response.text, "html.parser")
            if "sauce.com.ar" in url:
                return self._extract_sauce(soup, url)
            elif "guastavinoeimbert.com.ar" in url:
                return self._extract_guastavino(soup, url)
            elif "inmobiliariatomas.com.ar" in url:
                return self._extract_tomas(soup, url)
            elif "samarpropiedades.com.ar" in url:
                return self._extract_samar(soup, url)
            elif "orcuinmobiliaria.com.ar" in url:
                return self._extract_orcu(soup, url)
            elif "grossopropiedades.com" in url:
                return self._extract_grosso(soup, url)
            else:
                return self._extract_uretacortes(soup, url)
        except Exception as exc:
            logger.warning(f"Error parseando detalle {url}: {exc}")
            return {}

    def _extract_uretacortes(self, soup: BeautifulSoup, url: str) -> Dict[str, Any]:
        direccion = None
        barrio_detalle = None
        direccion_el = soup.select_one("h2.h2")
        if direccion_el:
            for content in direccion_el.contents:
                text = str(content).strip()
                if text and not text.startswith("<"):
                    cleaned = text.strip('"').strip()
                    if cleaned:
                        direccion = cleaned
                        break
            em = direccion_el.select_one("em")
            if em:
                barrio_detalle = em.get_text(strip=True).lstrip("—").strip()
        descripcion = self._parse_description(soup)
        tipo_propiedad = DataCleaner.extract_property_type_from_html(soup)
        if not tipo_propiedad:
            tipo_propiedad = DataCleaner.detect_property_type(descripcion)
        operacion = DataCleaner.extract_operation_from_html(soup)
        if not operacion:
            operacion = DataCleaner.detect_operation_from_text(descripcion)
        return {
            "descripcion": descripcion,
            "direccion": direccion,
            "barrio_detalle": barrio_detalle,
            "dormitorios": self._parse_meta(soup, ["dorm", "habit"]),
            "banos": self._parse_meta(soup, ["baño", "bano"]),
            "ambientes": self._parse_meta(soup, ["ambi"]),
            "imagenes": self._parse_images(soup, url),
            "tipo_propiedad": tipo_propiedad,
            "operacion": operacion,
        }

    def _extract_sauce(self, soup: BeautifulSoup, url: str) -> Dict[str, Any]:
        direccion = None
        h1 = soup.select_one("h1")
        if h1:
            direccion = h1.get_text(strip=True)
        barrio_detalle = None
        operacion = None
        tipo_propiedad = None
        article = soup.select_one("article, [class*='property']")
        if article:
            classes = " ".join(article.get("class", []))
            loc_match = re.search(r"locations-([a-z0-9-]+)", classes)
            if loc_match:
                barrio_raw = loc_match.group(1).replace("-", " ").title()
                barrio_detalle = barrio_raw
            tipo_match = re.search(r"property_types-([a-z0-9-]+)", classes)
            if tipo_match:
                tipo_raw = tipo_match.group(1).replace("-", " ")
                tipo_propiedad = DataCleaner.normalize_property_type_token(tipo_raw)
        for row in soup.select("tr"):
            cells = row.select("td, th")
            if len(cells) >= 2:
                label = cells[0].get_text(strip=True).lower()
                value = cells[1].get_text(strip=True).lower()
                if "operaci" in label:
                    if "alquiler" in value:
                        operacion = "alquiler"
                    elif "venta" in value:
                        operacion = "venta"
        if not operacion:
            operacion = DataCleaner.detect_operation_from_text(soup.get_text().lower())
        descripcion = self._parse_description(soup)
        if not tipo_propiedad:
            tipo_propiedad = DataCleaner.detect_property_type(descripcion)
        return {
            "descripcion": descripcion,
            "direccion": direccion,
            "barrio_detalle": barrio_detalle,
            "dormitorios": self._parse_meta_sauce(soup, ["dormitor", "dorm", "habit"]),
            "banos": self._parse_meta_sauce(soup, ["baño", "bano"]),
            "ambientes": self._parse_meta_sauce(soup, ["ambi"]),
            "imagenes": self._parse_images(soup, url),
            "tipo_propiedad": tipo_propiedad,
            "operacion": operacion,
        }

    def _extract_guastavino(self, soup: BeautifulSoup, url: str) -> Dict[str, Any]:
        direccion = None
        h1 = soup.select_one("h1.rh_banner__title, h1")
        if h1:
            direccion = h1.get_text(strip=True)
        barrio_detalle = None
        location_el = soup.select_one(".rh_page__location, [class*='page__location']")
        if location_el:
            full_location = location_el.get_text(strip=True)
            parts = full_location.split(",")
            if len(parts) >= 3:
                barrio_detalle = parts[2].strip()
        operacion = None
        price_el = soup.select_one(".rh_page__property_price")
        if price_el:
            price_text = price_el.get_text(strip=True).lower()
            if "alquiler" in price_text:
                operacion = "alquiler"
            elif "venta" in price_text:
                operacion = "venta"
        if not operacion:
            operacion = DataCleaner.detect_operation_from_text(soup.get_text())
        descripcion = self._parse_description(soup)
        tipo_propiedad = DataCleaner.detect_property_type(descripcion, direccion)
        return {
            "descripcion": descripcion,
            "direccion": direccion,
            "barrio_detalle": barrio_detalle,
            "dormitorios": self._parse_meta_guastavino(soup, ["dormitor", "habit", "cama"]),
            "banos": self._parse_meta_guastavino(soup, ["baño", "bano"]),
            "ambientes": self._parse_meta_guastavino(soup, ["ambi"]),
            "imagenes": self._parse_images(soup, url),
            "tipo_propiedad": tipo_propiedad,
            "operacion": operacion,
        }

    def _extract_tomas(self, soup: BeautifulSoup, url: str) -> Dict[str, Any]:
        direccion = None
        operacion = None
        tipo_propiedad = None
        title_tag = soup.find("title")
        if title_tag:
            title_text = title_tag.get_text(strip=True)
            main_part = title_text.split("|")[0].strip()
            parts = main_part.split(" - ")
            if len(parts) >= 1:
                direccion = parts[0].strip()
            if len(parts) >= 2:
                tipo_op = parts[1].strip().lower()
                if "venta" in tipo_op:
                    operacion = "venta"
                elif "alquiler" in tipo_op:
                    operacion = "alquiler"
                tipo_propiedad = DataCleaner.normalize_property_type_token(
                    tipo_op.replace("en venta", "").replace("en alquiler", "").strip()
                )
        dormitorios = None
        banos = None
        ambientes = None
        for row in soup.select("tr"):
            cells = row.select("td, th")
            if len(cells) >= 2:
                label = cells[0].get_text(strip=True).lower()
                value = cells[1].get_text(strip=True)
                if "baño" in label:
                    match = re.search(r"\d+", value)
                    if match:
                        banos = int(match.group(0))
                elif "ambient" in label:
                    match = re.search(r"\d+", value)
                    if match:
                        ambientes = int(match.group(0))
                elif "dorm" in label or "habit" in label:
                    match = re.search(r"\d+", value)
                    if match:
                        dormitorios = int(match.group(0))
        descripcion = self._parse_description(soup)
        if not tipo_propiedad or tipo_propiedad == "otro":
            tipo_propiedad = DataCleaner.detect_property_type(descripcion, direccion)
        return {
            "descripcion": descripcion,
            "direccion": direccion,
            "barrio_detalle": None,
            "dormitorios": dormitorios,
            "banos": banos,
            "ambientes": ambientes,
            "imagenes": self._parse_images(soup, url),
            "tipo_propiedad": tipo_propiedad,
            "operacion": operacion,
        }

    def _extract_samar(self, soup: BeautifulSoup, url: str) -> Dict[str, Any]:
        direccion = None
        operacion = None
        tipo_propiedad = None
        barrio_detalle = None
        meta_items = soup.select(".nav.property-meta li")
        if meta_items:
            direccion = meta_items[0].get_text(strip=True)
        full_text = soup.get_text(" ", strip=True).lower()
        if "alquiler" in full_text:
            operacion = "alquiler"
        elif "venta" in full_text:
            operacion = "venta"
        if not operacion:
            if "alquiler" in url:
                operacion = "alquiler"
            elif "venta" in url:
                operacion = "venta"
        for item in meta_items[1:]:
            text = item.get_text(strip=True)
            if text and text != "SANTA FE" and "," not in text and len(text) > 3:
                barrio_detalle = text
                break
        descripcion = self._parse_description(soup)
        tipo_propiedad = DataCleaner.detect_property_type(descripcion, direccion)
        dormitorios = None
        banos = None
        for item in meta_items:
            text = item.get_text(strip=True).lower()
            if "dorm" in text or "habit" in text:
                match = re.search(r"\d+", text)
                if match:
                    dormitorios = int(match.group(0))
            elif "baño" in text or "bano" in text:
                match = re.search(r"\d+", text)
                if match:
                    banos = int(match.group(0))
        return {
            "descripcion": descripcion,
            "direccion": direccion,
            "barrio_detalle": barrio_detalle,
            "dormitorios": dormitorios,
            "banos": banos,
            "ambientes": None,
            "imagenes": self._parse_images(soup, url),
            "tipo_propiedad": tipo_propiedad,
            "operacion": operacion,
        }

    def _extract_orcu(self, soup: BeautifulSoup, url: str) -> Dict[str, Any]:
        direccion = None
        operacion = None
        tipo_propiedad = None
        title_tag = soup.find("title")
        if title_tag:
            title_text = title_tag.get_text(strip=True)
            parts = title_text.split(" - ")
            if len(parts) >= 2:
                tipo_raw = parts[0].strip().lower()
                tipo_propiedad = DataCleaner.normalize_property_type_token(tipo_raw)
                direccion = " - ".join(parts[1:-1]).strip()
        full_text = soup.get_text(" ", strip=True).lower()
        if "alquiler" in full_text:
            operacion = "alquiler"
        elif "venta" in full_text:
            operacion = "venta"
        descripcion = self._parse_description(soup)
        if not tipo_propiedad or tipo_propiedad == "otro":
            tipo_propiedad = DataCleaner.detect_property_type(descripcion, direccion)
        return {
            "descripcion": descripcion,
            "direccion": direccion,
            "barrio_detalle": None,
            "dormitorios": None,
            "banos": None,
            "ambientes": None,
            "imagenes": self._parse_images(soup, url),
            "tipo_propiedad": tipo_propiedad,
            "operacion": operacion,
        }

    def _extract_grosso(self, soup: BeautifulSoup, url: str) -> Dict[str, Any]:
        """Extractor específico para grossopropiedades.com"""
        direccion = None
        operacion = None
        tipo_propiedad = None
        title_tag = soup.find("title")
        if title_tag:
            title_text = title_tag.get_text(strip=True)
            # Formato: "SANTIAGO DEL ESTERO 2800 > Cochera en VENTA en Santa Fe > Grosso"
            parts = title_text.split(" > ")
            if len(parts) >= 1:
                direccion = parts[0].strip()
            if len(parts) >= 2:
                tipo_op = parts[1].strip().lower()
                if "venta" in tipo_op:
                    operacion = "venta"
                elif "alquiler" in tipo_op:
                    operacion = "alquiler"
                tipo_raw = tipo_op.split(" en ")[0].strip()
                tipo_propiedad = DataCleaner.normalize_property_type_token(tipo_raw)
        descripcion = self._parse_description(soup)
        if not tipo_propiedad or tipo_propiedad == "otro":
            tipo_propiedad = DataCleaner.detect_property_type(descripcion, direccion)
        return {
            "descripcion": descripcion,
            "direccion": direccion,
            "barrio_detalle": None,
            "dormitorios": None,
            "banos": None,
            "ambientes": None,
            "imagenes": self._parse_images(soup, url),
            "tipo_propiedad": tipo_propiedad,
            "operacion": operacion,
        }

    def _parse_description(self, soup: BeautifulSoup) -> str:
        for selector in self.DESCRIPTION_SELECTORS:
            element = soup.select_one(selector)
            if element:
                return element.get_text(" ", strip=True)
        return ""

    @staticmethod
    def _parse_meta(soup: BeautifulSoup, keywords: List[str]) -> Optional[int]:
        dts = soup.select(".service-list.dl-horizontal dt")
        dds = soup.select(".service-list.dl-horizontal dd")
        for dt, dd in zip(dts, dds):
            label = dt.get_text(strip=True).lower()
            if any(keyword in label for keyword in keywords):
                match = re.search(r"\d+", dd.get_text(strip=True))
                return int(match.group(0)) if match else None
        return None

    @staticmethod
    def _parse_meta_sauce(soup: BeautifulSoup, keywords: List[str]) -> Optional[int]:
        for row in soup.select("tr"):
            cells = row.select("td, th")
            if len(cells) >= 2:
                label = cells[0].get_text(strip=True).lower()
                if any(kw in label for kw in keywords):
                    match = re.search(r"\d+", cells[1].get_text(strip=True))
                    return int(match.group(0)) if match else None
        return None

    @staticmethod
    def _parse_meta_guastavino(soup: BeautifulSoup, keywords: List[str]) -> Optional[int]:
        for item in soup.select(".rh_page__overview_item, [class*='overview_item']"):
            text = item.get_text(strip=True).lower()
            if any(kw in text for kw in keywords):
                match = re.search(r"\d+", text)
                return int(match.group(0)) if match else None
        return None

    def _parse_images(self, soup: BeautifulSoup, base_url: str) -> List[str]:
        seen: set = set()
        urls: List[str] = []

        def collect(imgs):
            for img in imgs:
                src = (
                    img.get("src")
                    or img.get("data-src")
                    or img.get("data-original")
                    or img.get("data-lazy-src")
                )
                if not src:
                    continue
                full = urljoin(base_url, src.strip())
                if full.startswith("http") and full not in seen:
                    lower = full.lower()
                    if any(skip in lower for skip in [
                        "logo", "icon", "sprite", "placeholder", "blank",
                        ".svg", "data:image", "facebook.com/tr",
                        "data-fiscal", "loungemedia",
                    ]):
                        continue
                    seen.add(full)
                    urls.append(full)

        found_specific = False
        for selector in self.IMAGE_SELECTORS:
            imgs = soup.select(selector)
            if imgs:
                collect(imgs)
                found_specific = True
                break

        if not found_specific:
            collect(soup.find_all("img"))

        return urls
