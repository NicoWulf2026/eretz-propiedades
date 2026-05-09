import os
from dataclasses import dataclass
from typing import Dict, Optional

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv(*args, **kwargs):
        pass

load_dotenv()


@dataclass
class SourceConfig:
    key: str
    base_url: str
    ciudad: str
    selector_propiedad: str
    selector_titulo: str
    selector_ubicacion: str
    selector_precio: str
    url_required_segment: str = "/propiedad/"
    forbidden_segment: Optional[str] = "/operacion/"
    max_pages: Optional[int] = None
    post_data: Optional[Dict] = None
    page_param: Optional[str] = None
    operacion_forzada: Optional[str] = None
    page_start: int = 1


SOURCE_CONFIGS: Dict[str, SourceConfig] = {
    "uretacortes": SourceConfig(
        key="uretacortes",
        base_url="https://uretacortes.com.ar/propiedad/page/{}/",
        ciudad="Santa Fe",
        selector_propiedad=".box.propiedad",
        selector_titulo=".h3",
        selector_ubicacion=".h4.em",
        selector_precio=".price-block",
    ),
    "sauce": SourceConfig(
        key="sauce",
        base_url="https://www.sauce.com.ar/properties/page/{}/",
        ciudad="Santa Fe",
        selector_propiedad="article.property-row",
        selector_titulo=".property-row-title",
        selector_ubicacion=".property-row-location",
        selector_precio=".property-price2",
        url_required_segment="/properties/",
        forbidden_segment=None,
    ),
"guastavino": SourceConfig(
        key="guastavino",
        base_url="https://guastavinoeimbert.com.ar/lista-inmuebles/page/{}/",
        ciudad="Santa Fe",
        selector_propiedad=".rh_list_card",
        selector_titulo="h2, h3",
        selector_ubicacion="[class*='location'], [class*='address']",
        selector_precio="[class*='price']",
        url_required_segment="/property/",
        forbidden_segment=None,
    ),
    "tomas_venta": SourceConfig(
        key="tomas_venta",
        base_url="https://inmobiliariatomas.com.ar/ventas.php",
        ciudad="Santa Fe",
        selector_propiedad=".card.flex-column.border-0",
        selector_titulo=".fs-22",
        selector_ubicacion=".mb-0.fs-14",
        selector_precio=".table",
        url_required_segment="propiedad.php",
        forbidden_segment=None,
        max_pages=1,
    ),
    "tomas_alquiler": SourceConfig(
        key="tomas_alquiler",
        base_url="https://inmobiliariatomas.com.ar/alquileres.php",
        ciudad="Santa Fe",
        selector_propiedad=".card.flex-column.border-0",
        selector_titulo=".fs-22",
        selector_ubicacion=".mb-0.fs-14",
        selector_precio=".table",
        url_required_segment="propiedad.php",
        forbidden_segment=None,
        max_pages=1,
    ),
    "samar_alquiler": SourceConfig(
        key="samar_alquiler",
        base_url="https://samarpropiedades.com.ar/alquileres/page/{}/",
        ciudad="Santa Fe",
        selector_propiedad=".property-wrap.property-grid",
        selector_titulo="h2, h3, [class*='title']",
        selector_ubicacion=".property-meta",
        selector_precio=".property-price",
        url_required_segment="/inmueble/",
        forbidden_segment=None,
    ),
    "samar_venta": SourceConfig(
        key="samar_venta",
        base_url="https://samarpropiedades.com.ar/ventas/page/{}/",
        ciudad="Santa Fe",
        selector_propiedad=".property-wrap.property-grid",
        selector_titulo="h2, h3, [class*='title']",
        selector_ubicacion=".property-meta",
        selector_precio=".property-price",
        url_required_segment="/inmueble/",
        forbidden_segment=None,
    ),
    "orcu_venta": SourceConfig(
        key="orcu_venta",
        base_url="https://www.orcuinmobiliaria.com.ar/resultados",
        ciudad="Santa Fe",
        selector_propiedad=".card-deck .card",
        selector_titulo="h5.card-title",
        selector_ubicacion="h5.card-title",
        selector_precio=".card-footer",
        url_required_segment="/detalles/",
        forbidden_segment=None,
        max_pages=1,
        post_data={"inmueble_si": "on", "operacion": "V", "cochera": ""},
    ),
    "orcu_alquiler": SourceConfig(
        key="orcu_alquiler",
        base_url="https://www.orcuinmobiliaria.com.ar/resultados",
        ciudad="Santa Fe",
        selector_propiedad=".card-deck .card",
        selector_titulo="h5.card-title",
        selector_ubicacion="h5.card-title",
        selector_precio=".card-footer",
        url_required_segment="/detalles/",
        forbidden_segment=None,
        max_pages=1,
        post_data={"inmueble_si": "on", "operacion": "A", "cochera": ""},
    ),
    "grosso_venta": SourceConfig(
        key="grosso_venta",
        base_url="https://www.grossopropiedades.com/ventas.php",
        ciudad="Santa Fe",
        selector_propiedad=".propiedad_1, .propiedad_2",
        selector_titulo=".propiedad_imagen_direccion",
        selector_ubicacion=".propiedad_imagen_direccion",
        selector_precio=".propiedad_precio",
        url_required_segment="propiedad/",
        forbidden_segment=None,
        max_pages=1,
    ),
    "grosso_alquiler": SourceConfig(
        key="grosso_alquiler",
        base_url="https://www.grossopropiedades.com/alquileres.php",
        ciudad="Santa Fe",
        selector_propiedad=".propiedad_1, .propiedad_2",
        selector_titulo=".propiedad_imagen_direccion",
        selector_ubicacion=".propiedad_imagen_direccion",
        selector_precio=".propiedad_precio",
        url_required_segment="propiedad/",
        forbidden_segment=None,
        max_pages=1,
    ),
    "lenarduzzi_venta": SourceConfig(
        key="lenarduzzi_venta",
        base_url="https://lenarduzzi.com.ar/estado/venta/page/{}/",
        ciudad="Santa Fe",
        selector_propiedad=".figure-block",
        selector_titulo=".item-title, h2, h3",
        selector_ubicacion=".item-address, [class*='address']",
        selector_precio=".item-price, [class*='price']",
        url_required_segment="/propiedades/",
        forbidden_segment=None,
    ),
    "lenarduzzi_alquiler": SourceConfig(
        key="lenarduzzi_alquiler",
        base_url="https://lenarduzzi.com.ar/estado/alquiler/page/{}/",
        ciudad="Santa Fe",
        selector_propiedad=".figure-block",
        selector_titulo=".item-title, h2, h3",
        selector_ubicacion=".item-address, [class*='address']",
        selector_precio=".item-price, [class*='price']",
        url_required_segment="/propiedades/",
        forbidden_segment=None,
    ),
    "migone_venta": SourceConfig(
        key="migone_venta",
        base_url="https://migoneinmobiliaria.com.ar/propiedades?p={}&b=All&ope=V&tipo=All&a1=All&cod=",
        ciudad="Santa Fe",
        selector_propiedad=".hotels-layout",
        selector_titulo="a.title",
        selector_ubicacion="span.number",
        selector_precio=".price",
        url_required_segment="ficha-mig",
        forbidden_segment=None,
        operacion_forzada="venta",
        page_start=0,
    ),
    "migone_alquiler": SourceConfig(
        key="migone_alquiler",
        base_url="https://migoneinmobiliaria.com.ar/propiedades?p={}&b=All&ope=A&tipo=All&a1=All&cod=",
        ciudad="Santa Fe",
        selector_propiedad=".hotels-layout",
        selector_titulo="a.title",
        selector_ubicacion="span.number",
        selector_precio=".price",
        url_required_segment="ficha-mig",
        forbidden_segment=None,
        operacion_forzada="alquiler",
        page_start=0,
    ),
    "salas_venta": SourceConfig(
        key="salas_venta",
        base_url="https://www.salasinmobiliaria.com.ar/listado.php?id_operacion=2&pag={}",
        ciudad="Santa Fe",
        selector_propiedad=".real-estate-item",
        selector_titulo="h3",
        selector_ubicacion="h3",
        selector_precio="span",
        url_required_segment="/propiedad/",
        forbidden_segment=None,
        operacion_forzada="venta",
    ),
    "salas_alquiler": SourceConfig(
        key="salas_alquiler",
        base_url="https://www.salasinmobiliaria.com.ar/listado.php?id_operacion=3&pag={}",
        ciudad="Santa Fe",
        selector_propiedad=".real-estate-item",
        selector_titulo="h3",
        selector_ubicacion="h3",
        selector_precio="span",
        url_required_segment="/propiedad/",
        forbidden_segment=None,
        operacion_forzada="alquiler",
    ),
    "benuzzi": SourceConfig(
        key="benuzzi",
        base_url="https://benuzzi.com/property/page/{}/",
        ciudad="Santa Fe",
        selector_propiedad=".rh-ultra-property-card-two",
        selector_titulo="h3",
        selector_ubicacion=".rh-ultra-property-card-two-address",
        selector_precio=".rh-ultra-property-card-two-price",
        url_required_segment="/property/",
        forbidden_segment="/property/page/",
        max_pages=4,
    ),
}

SUPABASE_URL: str = os.environ.get("SUPABASE_URL", "")
SUPABASE_SERVICE_ROLE_KEY: str = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
SUPABASE_ANON_KEY: str = os.environ.get("SUPABASE_ANON_KEY", "")
SUPABASE_TABLE: str = os.environ.get("SUPABASE_TABLE", "propiedades")

SUPABASE_KEY = SUPABASE_SERVICE_ROLE_KEY

_required = {
    "SUPABASE_URL": SUPABASE_URL,
    "SUPABASE_SERVICE_ROLE_KEY": SUPABASE_SERVICE_ROLE_KEY,
}
_missing = [k for k, v in _required.items() if not v]
if _missing:
    raise RuntimeError(
        f"Variables de entorno requeridas no configuradas: {', '.join(_missing)}\n"
        f"Copiá .env.example a .env y completá los valores."
    )

REQUEST_TIMEOUT: int = 15
PAGE_DELAY: float = 1.2
ITEM_DELAY: float = 0.4
MAX_EMPTY_PAGES: int = 2

REQUEST_HEADERS: Dict[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "es-AR,es;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}