import logging
import re
import time
import requests
from typing import List, Dict, Any, Optional, Set
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

from clients import SupabaseClient
from config import SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, SUPABASE_TABLE, SOURCE_CONFIGS
from extractors import DataCleaner
from models import Propiedad
from clients import SessionFactory

# ---------------------------------------------------------------------------
# Constantes de parsing
# ---------------------------------------------------------------------------

# Palabras del slug de URL que NO son ubicaciones geográficas.
# Al extraer barrio/dirección de slugs como /p/12345-Depto-en-Venta-en-Palermo,
# estas palabras se filtran para que el barrio quede solo "Palermo" y no
# "Venta Palermo", "Alquiler Centro", etc.
_SLUG_SKIP_WORDS = frozenset({
    "venta", "alquiler", "en", "de", "la", "los", "las", "del", "al", "por",
    "con", "sin", "una", "uno", "para", "casa", "departamento", "depto", "dep",
    "terreno", "local", "oficina", "cochera", "galpon", "duplex", "monoambiente",
    "ph", "inmueble", "propiedad", "inmobiliaria", "real", "estate", "arg",
    "com", "net", "property", "propiedades", "lote", "chalet", "quinta",
    "piso", "flat", "apt", "quincho", "triplex", "house", "apart",
})

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

FUENTES = [
    # ── Inmobiliarias Santa Fe (Tokko Broker) ─────────────────────────────────
    {"key": "loquet_venta",    "url": "https://www.loquet.com.ar/Venta",                  "operacion": "venta",    "ciudad": "Santa Fe"},
    {"key": "loquet_alquiler", "url": "https://www.loquet.com.ar/Alquiler",               "operacion": "alquiler", "ciudad": "Santa Fe"},
    {"key": "christen_venta",  "url": "https://www.christen.com.ar/Venta",                "operacion": "venta",    "ciudad": "Santa Fe"},
    {"key": "christen_alquiler","url": "https://www.christen.com.ar/Alquiler",            "operacion": "alquiler", "ciudad": "Santa Fe"},
    {"key": "royo_venta",      "url": "https://www.royoinmobiliaria.com.ar/Venta",        "operacion": "venta",    "ciudad": "Santa Fe"},
    {"key": "royo_alquiler",   "url": "https://www.royoinmobiliaria.com.ar/Alquiler",     "operacion": "alquiler", "ciudad": "Santa Fe"},
    {"key": "alicandro_venta", "url": "https://www.alicandro.com.ar/Venta",               "operacion": "venta",    "ciudad": "Santa Fe"},
    {"key": "alicandro_alquiler","url": "https://www.alicandro.com.ar/Alquiler",          "operacion": "alquiler", "ciudad": "Santa Fe"},
    {"key": "demichelis_venta",    "url": "https://www.demichelisbiasoni.com/Venta",      "operacion": "venta",    "ciudad": "Santa Fe"},
    {"key": "demichelis_alquiler", "url": "https://www.demichelisbiasoni.com/Alquiler",  "operacion": "alquiler", "ciudad": "Santa Fe"},
    {"key": "libertador_venta",    "url": "https://www.libertadorargentina.com/Venta",   "operacion": "venta",    "ciudad": "Santa Fe"},
    {"key": "libertador_alquiler", "url": "https://www.libertadorargentina.com/Alquiler","operacion": "alquiler", "ciudad": "Santa Fe"},
]

# ── Inmobiliarias nuevas (Tokko Broker — varias ciudades) ─────────────────────
FUENTES_NUEVAS = [
    # Buenos Aires / GBA
    {"key": "pilares_venta",          "url": "https://www.pilarespropiedades.com.ar/Venta",               "operacion": "venta",    "ciudad": "Banfield"},
    {"key": "pilares_alquiler",       "url": "https://www.pilarespropiedades.com.ar/Alquiler",            "operacion": "alquiler", "ciudad": "Banfield"},
    {"key": "ageo_venta",             "url": "https://www.ageopropiedades.com.ar/Venta",                  "operacion": "venta",    "ciudad": "Buenos Aires"},
    {"key": "ageo_alquiler",          "url": "https://www.ageopropiedades.com.ar/Alquiler",               "operacion": "alquiler", "ciudad": "Buenos Aires"},
    {"key": "ombu_venta",             "url": "https://www.ombupropiedades.com.ar/Venta",                  "operacion": "venta",    "ciudad": "Buenos Aires"},
    {"key": "ombu_alquiler",          "url": "https://www.ombupropiedades.com.ar/Alquiler",               "operacion": "alquiler", "ciudad": "Buenos Aires"},
    {"key": "torqui_venta",           "url": "https://www.torquipropiedades.com/Venta",                   "operacion": "venta",    "ciudad": "Buenos Aires"},
    {"key": "torqui_alquiler",        "url": "https://www.torquipropiedades.com/Alquiler",                "operacion": "alquiler", "ciudad": "Buenos Aires"},
    {"key": "coelho_venta",           "url": "https://www.coelhopropiedades.com.ar/Venta",                "operacion": "venta",    "ciudad": "Buenos Aires"},
    {"key": "coelho_alquiler",        "url": "https://www.coelhopropiedades.com.ar/Alquiler",             "operacion": "alquiler", "ciudad": "Buenos Aires"},
    # liottainmobiliaria.com usa /venta/ y /alquiler/ (minúscula con slash final)
    {"key": "liotta_venta",           "url": "https://www.liottainmobiliaria.com/venta/",                 "operacion": "venta",    "ciudad": "Buenos Aires"},
    {"key": "liotta_alquiler",        "url": "https://www.liottainmobiliaria.com/alquiler/",              "operacion": "alquiler", "ciudad": "Buenos Aires"},
    # ragno_pizarro: solo publica en portales, sin sitio propio con listado — eliminado
    # attili_bisso: CMS propio PHP — manejado por scrape_zanola pattern en no_tokko
    {"key": "attili_bisso_venta",     "url": "https://www.attili-bisso.com.ar/index.php",                 "operacion": "venta",    "ciudad": "Pilar",         "url_segment": "ficha.php"},
    {"key": "attili_bisso_alquiler",  "url": "https://www.attili-bisso.com.ar/index.php",                 "operacion": "alquiler", "ciudad": "Pilar",         "url_segment": "ficha.php"},
    # baccello usa /propiedades/
    {"key": "baccello_venta",         "url": "https://www.baccello.com/propiedades/venta/",               "operacion": "venta",    "ciudad": "Buenos Aires"},
    {"key": "baccello_alquiler",      "url": "https://www.baccello.com/propiedades/alquiler/",            "operacion": "alquiler", "ciudad": "Buenos Aires"},
    # foieri navarro: URL alternativa
    {"key": "foieri_navarro_venta",   "url": "https://www.foierinavarro.com.ar/propiedades/venta",        "operacion": "venta",    "ciudad": "Pilar"},
    {"key": "foieri_navarro_alquiler","url": "https://www.foierinavarro.com.ar/propiedades/alquiler",     "operacion": "alquiler", "ciudad": "Pilar"},
    # espacio_palermo: certificado SSL expirado — eliminado hasta que lo renueven
    # repetto: URL alternativa
    {"key": "repetto_venta",          "url": "https://www.repettopropiedades.com/propiedades/venta",      "operacion": "venta",    "ciudad": "Banfield"},
    {"key": "repetto_alquiler",       "url": "https://www.repettopropiedades.com/propiedades/alquiler",   "operacion": "alquiler", "ciudad": "Banfield"},
    # doopla: URL alternativa
    {"key": "doopla_venta",           "url": "https://www.doopla.com.ar/propiedades?operacion=venta",     "operacion": "venta",    "ciudad": "Buenos Aires"},
    {"key": "doopla_alquiler",        "url": "https://www.doopla.com.ar/propiedades?operacion=alquiler",  "operacion": "alquiler", "ciudad": "Buenos Aires"},
    # rucci: URL alternativa
    {"key": "rucci_venta",            "url": "https://www.ruccipropiedades.com/venta/",                   "operacion": "venta",    "ciudad": "Buenos Aires"},
    {"key": "rucci_alquiler",         "url": "https://www.ruccipropiedades.com/alquiler/",                "operacion": "alquiler", "ciudad": "Buenos Aires"},
    # loiacono: URL alternativa
    {"key": "loiacono_venta",         "url": "https://loiaconopropiedades.com.ar/propiedades/venta",      "operacion": "venta",    "ciudad": "Buenos Aires"},
    {"key": "loiacono_alquiler",      "url": "https://loiaconopropiedades.com.ar/propiedades/alquiler",   "operacion": "alquiler", "ciudad": "Buenos Aires"},
    {"key": "amadeo_venta",           "url": "https://amadeopropiedades.com/Venta",                       "operacion": "venta",    "ciudad": "Lomas de Zamora"},
    {"key": "amadeo_alquiler",        "url": "https://amadeopropiedades.com/Alquiler",                    "operacion": "alquiler", "ciudad": "Lomas de Zamora"},
    {"key": "invernizzi_venta",       "url": "https://invernizzi.com.ar/Venta",                           "operacion": "venta",    "ciudad": "Buenos Aires"},
    {"key": "invernizzi_alquiler",    "url": "https://invernizzi.com.ar/Alquiler",                        "operacion": "alquiler", "ciudad": "Buenos Aires"},
    {"key": "gibelli_venta",          "url": "https://gibelli.com.ar/Venta",                              "operacion": "venta",    "ciudad": "Buenos Aires"},
    {"key": "gibelli_alquiler",       "url": "https://gibelli.com.ar/Alquiler",                           "operacion": "alquiler", "ciudad": "Buenos Aires"},
    {"key": "vaccaro_venta",          "url": "https://vaccaroinmobiliaria.com.ar/Venta",                  "operacion": "venta",    "ciudad": "Banfield"},
    {"key": "vaccaro_alquiler",       "url": "https://vaccaroinmobiliaria.com.ar/Alquiler",               "operacion": "alquiler", "ciudad": "Banfield"},
    {"key": "arnaus_venta",           "url": "https://arnaus.com/Venta",                                  "operacion": "venta",    "ciudad": "San Isidro"},
    {"key": "arnaus_alquiler",        "url": "https://arnaus.com/Alquiler",                               "operacion": "alquiler", "ciudad": "San Isidro"},
    {"key": "castro_reisse_venta",    "url": "https://castroreisse.com/Venta",                            "operacion": "venta",    "ciudad": "Buenos Aires"},
    {"key": "castro_reisse_alquiler", "url": "https://castroreisse.com/Alquiler",                         "operacion": "alquiler", "ciudad": "Buenos Aires"},
    {"key": "iprop_venta",            "url": "https://www.ipropinmobiliaria.com.ar/Venta",                "operacion": "venta",    "ciudad": "Buenos Aires"},
    {"key": "iprop_alquiler",         "url": "https://www.ipropinmobiliaria.com.ar/Alquiler",             "operacion": "alquiler", "ciudad": "Buenos Aires"},
    {"key": "palau_venta",            "url": "https://www.palau.com.ar/Venta",                            "operacion": "venta",    "ciudad": "Buenos Aires"},
    {"key": "palau_alquiler",         "url": "https://www.palau.com.ar/Alquiler",                         "operacion": "alquiler", "ciudad": "Buenos Aires"},
    {"key": "levy_amon_venta",        "url": "https://www.levyamonpropiedades.com.ar/Venta",              "operacion": "venta",    "ciudad": "Buenos Aires"},
    {"key": "levy_amon_alquiler",     "url": "https://www.levyamonpropiedades.com.ar/Alquiler",           "operacion": "alquiler", "ciudad": "Buenos Aires"},
    {"key": "liotto_venta",           "url": "https://liottopropiedades.com.ar/venta/",                  "operacion": "venta",    "ciudad": "Buenos Aires"},
    {"key": "liotto_alquiler",        "url": "https://liottopropiedades.com.ar/alquiler/",               "operacion": "alquiler", "ciudad": "Buenos Aires"},
    {"key": "adrian_ghio_venta",      "url": "https://www.adrianghiopropiedades.com/Venta",               "operacion": "venta",    "ciudad": "La Plata"},
    {"key": "adrian_ghio_alquiler",   "url": "https://www.adrianghiopropiedades.com/Alquiler",            "operacion": "alquiler", "ciudad": "La Plata"},
    {"key": "oilher_venta",           "url": "https://www.oilherpropiedades.com/Venta",                   "operacion": "venta",    "ciudad": "Villa Gesell"},
    {"key": "oilher_alquiler",        "url": "https://www.oilherpropiedades.com/Alquiler",                "operacion": "alquiler", "ciudad": "Villa Gesell"},
    {"key": "ressia_venta",           "url": "https://ressiabienesraices.com.ar/Venta",                   "operacion": "venta",    "ciudad": "Villa Gesell"},
    {"key": "ressia_alquiler",        "url": "https://ressiabienesraices.com.ar/Alquiler",                "operacion": "alquiler", "ciudad": "Villa Gesell"},
    {"key": "arenas_venta",           "url": "https://arenaspropiedades.com/Venta",                       "operacion": "venta",    "ciudad": "Villa Carlos Paz"},
    {"key": "arenas_alquiler",        "url": "https://arenaspropiedades.com/Alquiler",                    "operacion": "alquiler", "ciudad": "Villa Carlos Paz"},
    {"key": "di_palermo_venta",       "url": "https://www.dipalermopropiedades.com/Venta",                "operacion": "venta",    "ciudad": "Mendoza"},
    {"key": "di_palermo_alquiler",    "url": "https://www.dipalermopropiedades.com/Alquiler",             "operacion": "alquiler", "ciudad": "Mendoza"},
    {"key": "damonte_venta",          "url": "https://www.inmobiliaria-damonteyasociados.com.ar/Venta",   "operacion": "venta",    "ciudad": "Córdoba"},
    {"key": "damonte_alquiler",       "url": "https://www.inmobiliaria-damonteyasociados.com.ar/Alquiler","operacion": "alquiler", "ciudad": "Córdoba"},
    {"key": "compreprop_venta",       "url": "https://www.compreprop.com.ar/Venta",                       "operacion": "venta",    "ciudad": "Córdoba"},
    {"key": "compreprop_alquiler",    "url": "https://www.compreprop.com.ar/Alquiler",                    "operacion": "alquiler", "ciudad": "Córdoba"},
    {"key": "giobellina_venta",       "url": "https://giobellinapropiedades.com.ar/Venta",                "operacion": "venta",    "ciudad": "Córdoba"},
    {"key": "giobellina_alquiler",    "url": "https://giobellinapropiedades.com.ar/Alquiler",             "operacion": "alquiler", "ciudad": "Córdoba"},
    # Santa Fe / Rosario
    {"key": "massera_venta",          "url": "https://masserapropiedades.com/Venta",                      "operacion": "venta",    "ciudad": "Rosario"},
    {"key": "massera_alquiler",       "url": "https://masserapropiedades.com/Alquiler",                   "operacion": "alquiler", "ciudad": "Rosario"},

    # ── NUEVAS — Buenos Aires Ciudad / GBA — Tokko Broker ────────────────────
    {"key": "calderon_venta",         "url": "https://www.calderonpropiedades.com.ar/Venta",              "operacion": "venta",    "ciudad": "Buenos Aires"},
    {"key": "calderon_alquiler",      "url": "https://www.calderonpropiedades.com.ar/Alquiler",           "operacion": "alquiler", "ciudad": "Buenos Aires"},
    {"key": "mgdeluca_venta",         "url": "https://www.mgdeluca.com.ar/Venta",                         "operacion": "venta",    "ciudad": "Ramos Mejía"},
    {"key": "mgdeluca_alquiler",      "url": "https://www.mgdeluca.com.ar/Alquiler",                      "operacion": "alquiler", "ciudad": "Ramos Mejía"},
    {"key": "nico_venta",             "url": "https://www.nicopropiedades.com.ar/Venta",                  "operacion": "venta",    "ciudad": "Buenos Aires"},
    {"key": "nico_alquiler",          "url": "https://www.nicopropiedades.com.ar/Alquiler",               "operacion": "alquiler", "ciudad": "Buenos Aires"},
    {"key": "arocha_venta",           "url": "https://www.arochapropiedades.com.ar/Venta",                "operacion": "venta",    "ciudad": "Buenos Aires"},
    {"key": "arocha_alquiler",        "url": "https://www.arochapropiedades.com.ar/Alquiler",             "operacion": "alquiler", "ciudad": "Buenos Aires"},
    {"key": "mas_venta",              "url": "https://maspropiedades.ar/Venta",                           "operacion": "venta",    "ciudad": "Buenos Aires"},
    {"key": "mas_alquiler",           "url": "https://maspropiedades.ar/Alquiler",                        "operacion": "alquiler", "ciudad": "Buenos Aires"},

    # ── NUEVAS — CMS Propio / Estructura diferente ───────────────────────────
    # Radeglia — GBA Sur (Burzaco, Adrogué, Lomas de Zamora) — param ?ope=V/A
    {"key": "radeglia_venta",         "url": "https://www.radegliaprop.com.ar/propiedades?ope=V",         "operacion": "venta",    "ciudad": "Burzaco"},
    {"key": "radeglia_alquiler",      "url": "https://www.radegliaprop.com.ar/propiedades?ope=A",         "operacion": "alquiler", "ciudad": "Burzaco"},
    # Repetto — GBA Sur — CMS Template4 con /propiedad/ID (no /p/)
    {"key": "repetto_venta",          "url": "https://www.repettopropiedades.com/propiedades/venta",      "operacion": "venta",    "ciudad": "Banfield"},
    {"key": "repetto_alquiler",       "url": "https://www.repettopropiedades.com/propiedades/alquiler",   "operacion": "alquiler", "ciudad": "Banfield"},
    # Vaccaro — GBA Sur — CMS propio /propiedad/ID
    {"key": "vaccaro_venta",          "url": "https://vaccaroinmobiliaria.com.ar/propiedades/venta",      "operacion": "venta",    "ciudad": "Banfield"},
    {"key": "vaccaro_alquiler",       "url": "https://vaccaroinmobiliaria.com.ar/propiedades/alquiler",   "operacion": "alquiler", "ciudad": "Banfield"},

    # ── Feli Mackinlay — Tokko Broker — Buenos Aires
    {"key": "feli_mackinlay_venta",   "url": "https://www.felicitasmackinlay.com.ar/Venta",              "operacion": "venta",    "ciudad": "Buenos Aires"},
    {"key": "feli_mackinlay_alquiler","url": "https://www.felicitasmackinlay.com.ar/Alquiler",           "operacion": "alquiler", "ciudad": "Buenos Aires"},

    # ── Caudana Propiedades — San Justo / Ramos Mejía — CMS propio
    {"key": "caudana_venta",          "url": "https://www.caudanapropiedades.com.ar/Venta",              "operacion": "venta",    "ciudad": "San Justo"},
    {"key": "caudana_alquiler",       "url": "https://www.caudanapropiedades.com.ar/Alquiler",           "operacion": "alquiler", "ciudad": "San Justo"},

    # ── Nizzi Propiedades — Mar del Plata — CMS propio ?operacion=1(venta)/2(alquiler)
    {"key": "nizzi_venta",            "url": "https://www.nizzipropiedades.com/propiedades?operacion=1", "operacion": "venta",    "ciudad": "Mar del Plata"},
    {"key": "nizzi_alquiler",         "url": "https://www.nizzipropiedades.com/propiedades?operacion=2", "operacion": "alquiler", "ciudad": "Mar del Plata"},

    # ── Galera Propiedades — Escobar / Pilar — Tokko Broker
    {"key": "galera_venta",           "url": "https://galerapropiedades.com.ar/Venta",                   "operacion": "venta",    "ciudad": "Escobar"},
    {"key": "galera_alquiler",        "url": "https://galerapropiedades.com.ar/Alquiler",                "operacion": "alquiler", "ciudad": "Escobar"},

    # ── Paulet Propiedades — Buenos Aires — Tokko Broker
    {"key": "paulet_venta",           "url": "https://www.pauletpropiedades.com/Venta",                  "operacion": "venta",    "ciudad": "Buenos Aires"},
    {"key": "paulet_alquiler",        "url": "https://www.pauletpropiedades.com/Alquiler",               "operacion": "alquiler", "ciudad": "Buenos Aires"},

    # ── Galea Propiedades — Pilar / Escobar — CMS propio
    {"key": "galea_venta",            "url": "https://galeapropiedades.com/Venta",                       "operacion": "venta",    "ciudad": "Pilar"},
    {"key": "galea_alquiler",         "url": "https://galeapropiedades.com/Alquiler",                    "operacion": "alquiler", "ciudad": "Pilar"},

    # ── Barón Inmobiliaria — Buenos Aires — Tokko Broker
    {"key": "baron_venta",            "url": "https://www.baroninmobiliaria.com.ar/Venta",               "operacion": "venta",    "ciudad": "Buenos Aires"},
    {"key": "baron_alquiler",         "url": "https://www.baroninmobiliaria.com.ar/Alquiler",            "operacion": "alquiler", "ciudad": "Buenos Aires"},

    # ── Garcia Propiedades — Mar del Plata — CMS propio
    {"key": "garcia_mdp_venta",       "url": "https://www.garciapropiedades.com.ar/Venta",               "operacion": "venta",    "ciudad": "Mar del Plata"},
    {"key": "garcia_mdp_alquiler",    "url": "https://www.garciapropiedades.com.ar/Alquiler",            "operacion": "alquiler", "ciudad": "Mar del Plata"},

    # ── Dalle Nogare — Buenos Aires — Tokko Broker
    {"key": "dalle_nogare_venta",     "url": "https://www.dallenogare.com.ar/Venta",                     "operacion": "venta",    "ciudad": "Buenos Aires"},
    {"key": "dalle_nogare_alquiler",  "url": "https://www.dallenogare.com.ar/Alquiler",                  "operacion": "alquiler", "ciudad": "Buenos Aires"},

    # ── Mudafy — Buenos Aires — CMS propio /venta/propiedades
    {"key": "mudafy_venta",           "url": "https://mudafy.com.ar/venta/propiedades",                  "operacion": "venta",    "ciudad": "Buenos Aires"},

    # ── 5411 Estate — Buenos Aires — CMS propio
    {"key": "5411estate_venta",       "url": "https://5411estate.com/Venta",                             "operacion": "venta",    "ciudad": "Buenos Aires"},
    {"key": "5411estate_alquiler",    "url": "https://5411estate.com/Alquiler",                          "operacion": "alquiler", "ciudad": "Buenos Aires"},

    # ── Mariana Stange — Buenos Aires — Tokko Broker
    {"key": "mariana_stange_venta",   "url": "https://www.maristange.com.ar/Venta",                      "operacion": "venta",    "ciudad": "Buenos Aires"},
    {"key": "mariana_stange_alquiler","url": "https://www.maristange.com.ar/Alquiler",                   "operacion": "alquiler", "ciudad": "Buenos Aires"},

    # ── Fransa Propiedades — Buenos Aires — Tokko Broker
    {"key": "fransa_venta",           "url": "https://www.fransapropiedades.com.ar/Venta",               "operacion": "venta",    "ciudad": "Buenos Aires"},
    {"key": "fransa_alquiler",        "url": "https://www.fransapropiedades.com.ar/Alquiler",            "operacion": "alquiler", "ciudad": "Buenos Aires"},

    # ── Nueva Vista — Buenos Aires — Tokko Broker
    {"key": "nueva_vista_venta",      "url": "https://www.nuevavistapropiedades.com.ar/Venta",           "operacion": "venta",    "ciudad": "Buenos Aires"},
    {"key": "nueva_vista_alquiler",   "url": "https://www.nuevavistapropiedades.com.ar/Alquiler",        "operacion": "alquiler", "ciudad": "Buenos Aires"},

    # ── Gold Group — Buenos Aires — Tokko Broker
    {"key": "gold_group_venta",       "url": "https://www.goldgrouppropiedades.com/Venta",               "operacion": "venta",    "ciudad": "Buenos Aires"},
    {"key": "gold_group_alquiler",    "url": "https://www.goldgrouppropiedades.com/Alquiler",            "operacion": "alquiler", "ciudad": "Buenos Aires"},

    # ── Tizado — Buenos Aires / GBA / Nordelta — CMS propio
    # Manejado por scrape_tizado() en scrape_nuevas_no_tokko()
    # No va en FUENTES_NUEVAS (requiere scraper especial)

    # ════════════════════════════════════════════════════════════════
    # SELECTIA + ROI — Las 20 inmobiliarias premium de CABA
    # ════════════════════════════════════════════════════════════════

    # ── ASEMPRO — Tokko Broker — CABA
    {"key": "asempro_venta",          "url": "https://www.asempro.com.ar/Venta",                          "operacion": "venta",    "ciudad": "Buenos Aires"},
    {"key": "asempro_alquiler",       "url": "https://www.asempro.com.ar/Alquiler",                       "operacion": "alquiler", "ciudad": "Buenos Aires"},

    # ── Braulio Inmuebles — Tokko Broker — CABA / Nordelta
    {"key": "braulio_venta",          "url": "https://www.braulioinmuebles.com/Venta",                    "operacion": "venta",    "ciudad": "Buenos Aires"},
    {"key": "braulio_alquiler",       "url": "https://www.braulioinmuebles.com/Alquiler",                 "operacion": "alquiler", "ciudad": "Buenos Aires"},

    # ── Click Aparts — Tokko Broker — CABA
    {"key": "clickaparts_venta",      "url": "https://www.clickaparts.com/Venta",                         "operacion": "venta",    "ciudad": "Buenos Aires"},
    {"key": "clickaparts_alquiler",   "url": "https://www.clickaparts.com/Alquiler",                      "operacion": "alquiler", "ciudad": "Buenos Aires"},

    # ── GPS Real Estate — Tokko Broker — CABA
    {"key": "gps_venta",              "url": "https://www.gpsrealestate.com.ar/Venta",                    "operacion": "venta",    "ciudad": "Buenos Aires"},
    {"key": "gps_alquiler",           "url": "https://www.gpsrealestate.com.ar/Alquiler",                 "operacion": "alquiler", "ciudad": "Buenos Aires"},

    # ── Iribarren Propiedades — Tokko Broker — CABA
    {"key": "iribarren_venta",        "url": "https://www.iribarrenpropiedades.com.ar/Venta",             "operacion": "venta",    "ciudad": "Buenos Aires"},
    {"key": "iribarren_alquiler",     "url": "https://www.iribarrenpropiedades.com.ar/Alquiler",          "operacion": "alquiler", "ciudad": "Buenos Aires"},

    # ── Altgelt Negocios Inmobiliarios — CMS propio — Recoleta/CABA
    {"key": "altgelt_venta",          "url": "https://www.e-altgelt.com/Venta",                           "operacion": "venta",    "ciudad": "Buenos Aires"},
    {"key": "altgelt_alquiler",       "url": "https://www.e-altgelt.com/Alquiler",                        "operacion": "alquiler", "ciudad": "Buenos Aires"},

    # ── Izrastzoff — CMS propio — Recoleta / Nordelta
    {"key": "izrastzoff_venta",       "url": "https://www.izr.com.ar/buscar-propiedades-en-venta",        "operacion": "venta",    "ciudad": "Buenos Aires"},
    {"key": "izrastzoff_alquiler",    "url": "https://www.izr.com.ar/buscar-propiedades-en-alquiler",     "operacion": "alquiler", "ciudad": "Buenos Aires"},

    # ── Covello Propiedades — CMS propio — Palermo / Zona Norte
    {"key": "covello_venta",          "url": "https://www.covello.com.ar/Venta",                          "operacion": "venta",    "ciudad": "Buenos Aires"},
    {"key": "covello_alquiler",       "url": "https://www.covello.com.ar/Alquiler",                       "operacion": "alquiler", "ciudad": "Buenos Aires"},

    # ── Maure Inmobiliaria — CMS propio — Palermo/Belgrano
    {"key": "maure_venta",            "url": "https://maureinmobiliaria.com/propiedades/venta",           "operacion": "venta",    "ciudad": "Buenos Aires"},
    {"key": "maure_alquiler",         "url": "https://maureinmobiliaria.com/propiedades/alquiler",        "operacion": "alquiler", "ciudad": "Buenos Aires"},

    # ── Evoluer — CMS propio — CABA premium
    {"key": "evoluer_venta",          "url": "https://evoluer.com.ar/propiedades",                        "operacion": "venta",    "ciudad": "Buenos Aires"},

    # ── Predial — CMS propio — Villa Urquiza / Caballito / Belgrano
    {"key": "predial_venta",          "url": "https://www.predial.com.ar/propiedades-venta",              "operacion": "venta",    "ciudad": "Buenos Aires"},
    {"key": "predial_alquiler",       "url": "https://www.predial.com.ar/propiedades-alquiler",           "operacion": "alquiler", "ciudad": "Buenos Aires"},

    # ── Krell Brokers — CMS propio — Villa Crespo / CABA
    {"key": "krell_venta",            "url": "https://krellbrokers.com/propiedades/todas/venta",          "operacion": "venta",    "ciudad": "Buenos Aires"},
    {"key": "krell_alquiler",         "url": "https://krellbrokers.com/propiedades/todas/alquiler",       "operacion": "alquiler", "ciudad": "Buenos Aires"},

    # ── Interwin — CMS propio — CABA / GBA Norte
    {"key": "interwin_venta",         "url": "https://www.interwin.com.ar/Venta",                         "operacion": "venta",    "ciudad": "Buenos Aires"},
    {"key": "interwin_alquiler",      "url": "https://www.interwin.com.ar/Alquiler",                      "operacion": "alquiler", "ciudad": "Buenos Aires"},

    # ── Bresson Brokers — CMS propio — Recoleta/Palermo
    {"key": "bresson_venta",          "url": "https://bressonbrokers.com/Venta",                          "operacion": "venta",    "ciudad": "Buenos Aires"},
    {"key": "bresson_alquiler",       "url": "https://bressonbrokers.com/Alquiler",                       "operacion": "alquiler", "ciudad": "Buenos Aires"},

    # ── Soldati — CMS propio — CABA / Palermo / GBA Norte
    {"key": "soldati_venta",          "url": "https://soldati.com/propiedades/todas/ventas",              "operacion": "venta",    "ciudad": "Buenos Aires"},
    {"key": "soldati_alquiler",       "url": "https://soldati.com/propiedades/todas/alquileres",          "operacion": "alquiler", "ciudad": "Buenos Aires"},

    # ── Ocampo Propiedades — CMS propio — Belgrano / CABA
    {"key": "ocampo_venta",           "url": "https://ocampopropiedades.com/propiedades?operation_types=1","operacion": "venta",   "ciudad": "Buenos Aires"},
    {"key": "ocampo_alquiler",        "url": "https://ocampopropiedades.com/propiedades?operation_types=2","operacion": "alquiler","ciudad": "Buenos Aires"},

    # ── Lepore Propiedades — CMS propio — Caballito / Palermo / CABA
    {"key": "lepore_venta",           "url": "https://www.lepore.com.ar/Venta",                           "operacion": "venta",    "ciudad": "Buenos Aires"},
    {"key": "lepore_alquiler",        "url": "https://www.lepore.com.ar/Alquiler",                        "operacion": "alquiler", "ciudad": "Buenos Aires"},

    # ── D'Antonio Propiedades — CMS propio — Caballito/Palermo
    {"key": "dantonio_venta",         "url": "https://www.dantoniopropiedades.com.ar/Venta",              "operacion": "venta",    "ciudad": "Buenos Aires"},
    {"key": "dantonio_alquiler",      "url": "https://www.dantoniopropiedades.com.ar/Alquiler",           "operacion": "alquiler", "ciudad": "Buenos Aires"},

    # ── Achával Cornejo — CMS propio — Vicente López / GBA Norte
    {"key": "achavalcornejo_venta",   "url": "https://achavalcornejo.com/propiedades/operacion/venta/",   "operacion": "venta",    "ciudad": "Vicente López"},
    {"key": "achavalcornejo_alquiler","url": "https://achavalcornejo.com/propiedades/operacion/alquiler/","operacion": "alquiler", "ciudad": "Vicente López"},

    # ── Fabián Achával Propiedades — CMS propio — Palermo/Belgrano
    {"key": "fabian_achaval_venta",   "url": "https://www.fabianachaval.com.ar/Venta",                    "operacion": "venta",    "ciudad": "Buenos Aires"},
    {"key": "fabian_achaval_alquiler","url": "https://www.fabianachaval.com.ar/Alquiler",                 "operacion": "alquiler", "ciudad": "Buenos Aires"},

    # ── L.M. Elizalde — CMS propio — CABA
    {"key": "elizalde_venta",         "url": "https://www.lmelizalde.com.ar/Venta",                       "operacion": "venta",    "ciudad": "Buenos Aires"},
    {"key": "elizalde_alquiler",      "url": "https://www.lmelizalde.com.ar/Alquiler",                    "operacion": "alquiler", "ciudad": "Buenos Aires"},

    # ── Mel Inmobiliario — Tokko Broker — CABA
    {"key": "mel_venta",              "url": "https://www.melinmobiliario.com.ar/Venta",                  "operacion": "venta",    "ciudad": "Buenos Aires"},
    {"key": "mel_alquiler",           "url": "https://www.melinmobiliario.com.ar/Alquiler",               "operacion": "alquiler", "ciudad": "Buenos Aires"},

    # ── Addario Inmobiliaria — CMS propio — CABA
    {"key": "addario_venta",          "url": "https://www.addario.com.ar/Venta",                          "operacion": "venta",    "ciudad": "Buenos Aires"},
    {"key": "addario_alquiler",       "url": "https://www.addario.com.ar/Alquiler",                       "operacion": "alquiler", "ciudad": "Buenos Aires"},

    # ── Alemany Propiedades — Tokko Broker — CABA
    {"key": "alemany_venta",          "url": "https://www.alemanypropiedades.com.ar/Venta",               "operacion": "venta",    "ciudad": "Buenos Aires"},
    {"key": "alemany_alquiler",       "url": "https://www.alemanypropiedades.com.ar/Alquiler",            "operacion": "alquiler", "ciudad": "Buenos Aires"},

    # ── Dodorico Propiedades — Tokko Broker — CABA
    {"key": "dodorico_venta",         "url": "https://www.dodorico.com.ar/Venta",                         "operacion": "venta",    "ciudad": "Buenos Aires"},
    {"key": "dodorico_alquiler",      "url": "https://www.dodorico.com.ar/Alquiler",                      "operacion": "alquiler", "ciudad": "Buenos Aires"},

    # ── Shenk Propiedades — Tokko Broker — CABA
    {"key": "shenk_venta",            "url": "https://www.shenk.com.ar/Venta",                            "operacion": "venta",    "ciudad": "Buenos Aires"},
    {"key": "shenk_alquiler",         "url": "https://www.shenk.com.ar/Alquiler",                         "operacion": "alquiler", "ciudad": "Buenos Aires"},

    # ── Toribio Achával — CMS propio — Barrios cerrados / CABA premium
    {"key": "toribio_venta",          "url": "https://www.toribioachaval.com/propiedades/venta",          "operacion": "venta",    "ciudad": "Buenos Aires"},
    {"key": "toribio_alquiler",       "url": "https://www.toribioachaval.com/propiedades/alquiler",       "operacion": "alquiler", "ciudad": "Buenos Aires"},

    # ── L.J. Ramos Brokers — CMS propio — CABA corporativo
    {"key": "ljramos_venta",          "url": "https://www.ljramos.com.ar/propiedades/venta",              "operacion": "venta",    "ciudad": "Buenos Aires"},
    {"key": "ljramos_alquiler",       "url": "https://www.ljramos.com.ar/propiedades/alquiler",           "operacion": "alquiler", "ciudad": "Buenos Aires"},

    # ── Miranda Bosch — Tokko Broker — CABA / Zona Norte
    {"key": "mirandabosch_venta",     "url": "https://www.mirandabosch.com.ar/Venta",                     "operacion": "venta",    "ciudad": "Buenos Aires"},
    {"key": "mirandabosch_alquiler",  "url": "https://www.mirandabosch.com.ar/Alquiler",                  "operacion": "alquiler", "ciudad": "Buenos Aires"},

    # ── Agüero Vera Propiedades — Tokko Broker — CABA
    {"key": "aguero_vera_venta",      "url": "https://www.agueroyverapropiedades.com.ar/Venta",           "operacion": "venta",    "ciudad": "Buenos Aires"},
    {"key": "aguero_vera_alquiler",   "url": "https://www.agueroyverapropiedades.com.ar/Alquiler",        "operacion": "alquiler", "ciudad": "Buenos Aires"},

    # ── Fabián Noseda Propiedades — Tokko Broker — CABA
    {"key": "noseda_venta",           "url": "https://www.fabiannoseda.com.ar/Venta",                     "operacion": "venta",    "ciudad": "Buenos Aires"},
    {"key": "noseda_alquiler",        "url": "https://www.fabiannoseda.com.ar/Alquiler",                  "operacion": "alquiler", "ciudad": "Buenos Aires"},

    # ── Brick Propiedades — Tokko Broker — CABA
    {"key": "brick_venta",            "url": "https://www.brickpropiedades.com.ar/Venta",                 "operacion": "venta",    "ciudad": "Buenos Aires"},
    {"key": "brick_alquiler",         "url": "https://www.brickpropiedades.com.ar/Alquiler",              "operacion": "alquiler", "ciudad": "Buenos Aires"},

    # ── Lincoln Negocios Inmobiliarios — Tokko Broker — CABA
    {"key": "lincoln_venta",          "url": "https://www.lincolninmobiliaria.com.ar/Venta",              "operacion": "venta",    "ciudad": "Buenos Aires"},
    {"key": "lincoln_alquiler",       "url": "https://www.lincolninmobiliaria.com.ar/Alquiler",           "operacion": "alquiler", "ciudad": "Buenos Aires"},

    # ── Salaya Romera Propiedades — Tokko Broker — CABA
    {"key": "salaya_venta",           "url": "https://www.salayaromera.com.ar/Venta",                     "operacion": "venta",    "ciudad": "Buenos Aires"},
    {"key": "salaya_alquiler",        "url": "https://www.salayaromera.com.ar/Alquiler",                  "operacion": "alquiler", "ciudad": "Buenos Aires"},

    # ── Vinelli Propiedades — Tokko Broker — CABA
    {"key": "vinelli_venta",          "url": "https://www.vinellipropiedades.com.ar/Venta",               "operacion": "venta",    "ciudad": "Buenos Aires"},
    {"key": "vinelli_alquiler",       "url": "https://www.vinellipropiedades.com.ar/Alquiler",            "operacion": "alquiler", "ciudad": "Buenos Aires"},

    # ── Cifre Propiedades — Tokko Broker — CABA
    {"key": "cifre_venta",            "url": "https://www.cifrepropiedades.com.ar/Venta",                 "operacion": "venta",    "ciudad": "Buenos Aires"},
    {"key": "cifre_alquiler",         "url": "https://www.cifrepropiedades.com.ar/Alquiler",              "operacion": "alquiler", "ciudad": "Buenos Aires"},

    # ── Di Mitrio Inmobiliaria — Tokko Broker — Barracas / CABA Sur
    {"key": "dimitrio_venta",         "url": "https://www.dimitrioinmobiliaria.com.ar/Venta",             "operacion": "venta",    "ciudad": "Buenos Aires"},
    {"key": "dimitrio_alquiler",      "url": "https://www.dimitrioinmobiliaria.com.ar/Alquiler",          "operacion": "alquiler", "ciudad": "Buenos Aires"},

    # ── Adriana Massa — Tokko Broker — CABA
    {"key": "adrianamassa_venta",     "url": "https://www.adrianamassa.com.ar/Venta",                     "operacion": "venta",    "ciudad": "Buenos Aires"},
    {"key": "adrianamassa_alquiler",  "url": "https://www.adrianamassa.com.ar/Alquiler",                  "operacion": "alquiler", "ciudad": "Buenos Aires"},

    # ── Capilla García Fernández — Tokko Broker — CABA
    {"key": "capilla_venta",          "url": "https://www.capillainmobiliaria.com.ar/Venta",              "operacion": "venta",    "ciudad": "Buenos Aires"},
    {"key": "capilla_alquiler",       "url": "https://www.capillainmobiliaria.com.ar/Alquiler",           "operacion": "alquiler", "ciudad": "Buenos Aires"},

    # ── RGM Propiedades — Tokko Broker — CABA
    {"key": "rgm_venta",              "url": "https://www.rgmpropiedades.com.ar/Venta",                   "operacion": "venta",    "ciudad": "Buenos Aires"},
    {"key": "rgm_alquiler",           "url": "https://www.rgmpropiedades.com.ar/Alquiler",                "operacion": "alquiler", "ciudad": "Buenos Aires"},
]


def _goto_safe(page, url: str, timeout: int = 40000) -> bool:
    """Navega a una URL con manejo de errores. Retorna True si exitoso."""
    try:
        page.goto(url, timeout=timeout, wait_until="domcontentloaded")
        return True
    except Exception as exc:
        err = str(exc)
        if "Timeout" in err:
            logger.warning(f"Timeout navegando a {url}")
        elif "ERR_CERT" in err or "SSL" in err:
            logger.warning(f"Error SSL en {url}")
        elif "ERR_NAME_NOT_RESOLVED" in err or "ERR_CONNECTION" in err:
            logger.warning(f"Sitio no disponible: {url}")
        else:
            logger.warning(f"Error navegando a {url}: {type(exc).__name__}")
        return False


def scroll_to_bottom(page, max_scrolls=12):
    """
    Hace scroll hasta el fondo para disparar la carga lazy de propiedades.
    max_scrolls reducido a 12 (antes 20) y timeout a 1500ms (antes 2000ms)
    para acortar el tiempo en sitios que no necesitan muchos scrolls.
    """
    PROP_SELECTOR = (
        'a[href*="/p/"], a[href*="/propiedad/"], a[href*="/inmueble/"], '
        'a[href*="/inmuebles/"], a[href*="/property/"], a[href*="/Ficha/"], a[href*="/ficha/"]'
    )
    prev = 0
    for _ in range(max_scrolls):
        try:
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(1500)
            count = len(page.query_selector_all(PROP_SELECTOR))
        except Exception:
            # El contexto de la página fue destruido (redirección durante el scroll)
            break

        if count == prev:
            # Espera corta extra por si el contenido llega con retraso
            try:
                page.wait_for_timeout(600)
                count = len(page.query_selector_all(PROP_SELECTOR))
            except Exception:
                break
            if count == prev:
                # Intentar botón "Ver más" antes de rendirse
                clicked = False
                for sel in ['button:has-text("Ver más")', 'a:has-text("Ver más")',
                            'button:has-text("Cargar más")', '[class*="load-more"]']:
                    try:
                        btn = page.query_selector(sel)
                        if btn and btn.is_visible():
                            btn.click()
                            page.wait_for_timeout(2000)
                            clicked = True
                            break
                    except Exception:
                        pass
                if not clicked:
                    break
        prev = count
    return prev


def parse_cards(html: str, operacion: str, fuente_key: str, base_url: str,
                ciudad: str = "Santa Fe") -> List[Propiedad]:
    """
    Parser genérico para sitios Tokko Broker y similares.
    Acepta 'ciudad' para cubrir inmobiliarias fuera de Santa Fe.
    Si no encuentra card containers o el card mode devuelve vacío,
    hace fallback directo por links (resuelve repetto, vaccaro, oilher, etc).
    """
    soup = BeautifulSoup(html, "html.parser")

    # ── Segmentos de URL que identifican páginas de propiedades individuales ──
    # CAUSA 1 de 0-resultados: segmentos faltantes hacen que el fallback ignore
    # sitios que usan CMS diferentes a Tokko Broker.
    PROP_SEGMENTS = [
        # ── Tokko Broker / iMeSH / custom PHP ──────────────────────────────
        "/p/",              # Tokko Broker  e.g. /p/7654321-Casa-en-Venta-...
        "/propiedad/",      # repetto, vaccaro, varios CMS propios
        "/propiedades/",    # WP Real Estate, Houzez, Inmogestor
        "/inmueble/",       # iMeSH / Sitioinmuebles
        "/inmuebles/",      # civeira, WordPress custom
        # ── English CMS (usados en Argentina con nombres en inglés) ────────
        "/property/",       # WP themes: Houzez, Estate Engine
        "/properties/",     # plural de la mayoría de themes en inglés
        "/listing/",        # EasyBroker, ListingPro
        "/listings/",       # plural
        # ── PHP genérico / sistemas nacionales ─────────────────────────────
        "/detalle/",        # PHP custom: /detalle/123-titulo
        "/detalles/",       # variante plural
        "/aviso/",          # algunas plataformas de avisos
        "/emprendimiento/", # desarrolladoras: /emprendimiento/slug
        # ── WP / Keysoft / Tizado ──────────────────────────────────────────
        "/Ficha/",          # Tizado.com, Keysoft
        "/ficha/",
        "/ficha-",          # variante sin barra (ficha-123)
    ]

    # Segmentos que sirven como categorías/paginación (no son fichas individuales)
    # Usados para filtrar falsos positivos cuando un segmento como /propiedades/
    # aparece seguido de una categoría.
    _CATEGORY_SUFFIXES = {
        "venta", "alquiler", "page", "buscar", "search", "results",
        "resultados", "categoria", "category", "tipo", "type",
    }

    def _is_detail_url(path: str) -> bool:
        """True si el path parece una ficha individual (no una categoría o paginación)."""
        for seg in PROP_SEGMENTS:
            if seg in path:
                after = path.split(seg, 1)[-1].strip("/")
                if not after:
                    return False
                # Rechazar si lo que sigue es una categoría conocida
                first_part = after.split("/")[0].split("-")[0].lower()
                if first_part in _CATEGORY_SUFFIXES:
                    return False
                # Debe tener al menos 3 caracteres útiles
                return len(after) >= 3
        return False

    # ── Detectar tipo de card container — orden de prioridad ─────────────────
    # CAUSA 2 de 0-resultados: selectores de card demasiado específicos.
    # Sólo cubrían Bootstrap 3 y 2-3 clases más. Ahora cubre la mayoría de
    # los CMS inmobiliarios argentinos y themes de WordPress.
    cards = (
        # ── Clases semánticas de propiedad (más confiables) ────────────────
        soup.select("[class*='property-card'], [class*='property-item']")
        or soup.select("[class*='prop-card'], [class*='prop-item']")
        or soup.select("[class*='listing-item'], [class*='listing-card']")
        or soup.select("[class*='inmueble-item'], [class*='item-inmueble']")
        or soup.select("[class*='aviso-'], [class*='-aviso']")
        or soup.select("[class*='real-estate-item'], [class*='estate-item']")
        or soup.select("[class*='card-inmueble'], [class*='inmueble-card']")
        or soup.select("[class*='result-item'], [class*='search-result']")
        # ── Elementos article con contexto de listado ──────────────────────
        or soup.select("article.property-row")
        or soup.select("article[class*='prop'], article[class*='listing']")
        or soup.select("article[class*='inmueble'], article[class*='aviso']")
        # ── Temas WP específicos (Real Homes, EstateEngine) ────────────────
        or soup.select(".rh_list_card, .rh-ultra-property-card-two, .rh_prop_card")
        or soup.select(".figure-block, .hotels-layout")
        # ── Bootstrap 3 grid (herencia) ────────────────────────────────────
        or soup.select("div.col-md-6.col-lg-6")
        or soup.select("div.col-sm-6.col-xs-12")
        or soup.select("div.col-md-4.col-sm-6")
        # ── Listas ordenadas de propiedades ───────────────────────────────
        or soup.select("ul.resultados-list li")
        or soup.select("li.prop-card, li[class*='prop-item'], li[class*='listing-item']")
        # NOTA: li[data-id] fue removido — matcheaba filtros del sidebar
    )

    propiedades = []
    seen = set()

    def _make_prop_from_url(href: str, card_text: str = "") -> Optional[Propiedad]:
        """
        Crea un Propiedad mínimo desde un href de Tokko Broker o CMS propio.
        Extrae título/barrio desde texto del card o slug de la URL.
        """
        url = href if href.startswith("http") else urljoin(base_url, href)
        if url in seen:
            return None
        seen.add(url)

        # Obtener slug de la URL (parte descriptiva del path)
        path = url.split("?")[0]  # quitar query string
        slug = path.rstrip("/").split("/")[-1]  # último segmento

        # Título desde texto del card o desde el slug
        if card_text and len(card_text) > 8:
            # Limpiar texto del card: remover precios y textos técnicos
            titulo = card_text[:150]
        else:
            slug_sin_id = "-".join(p for p in slug.split("-") if not p.isdigit())
            titulo = (
                slug_sin_id.replace("-", " ").title()[:100]
                if slug_sin_id
                else slug.replace("-", " ").title()[:100]
            )

        # Extraer dirección/barrio del slug
        slug_parts = slug.split("-")

        # Saltar el ID numérico inicial (Tokko usa ID-palabra-palabra-barrio)
        first_non_id = 0
        for i, p in enumerate(slug_parts):
            if not p.isdigit():
                first_non_id = i
                break

        meaningful_parts = slug_parts[first_non_id:]
        # Filtrar palabras que no son ubicaciones (operacion, tipo de propiedad, preposiciones)
        palabras = [p for p in meaningful_parts
                    if not p.isdigit() and len(p) > 2 and p.lower() not in _SLUG_SKIP_WORDS]
        nums = [p for p in meaningful_parts if p.isdigit() and 2 <= len(p) <= 5]

        direccion = None
        barrio = None

        if palabras:
            barrio = " ".join(palabras[-2:]).title() if len(palabras) >= 2 else palabras[-1].title()
            if nums:
                calle = " ".join(palabras[:3]).title()
                direccion = f"{calle} {nums[0]}"
            else:
                direccion = " ".join(palabras[:4]).title()

        # Fallback: usar ciudad como barrio si no se pudo extraer nada
        if not barrio and not direccion:
            barrio = ciudad or "Argentina"

        # Tipo: la URL de Tokko incluye el tipo en el slug (/p/1234-Casa-en-Venta-...)
        tipo = DataCleaner.detect_property_type(slug.replace("-", " ") + " " + (titulo or ""))

        # Operación: detectar desde el slug/path antes de usar el parámetro global.
        # Se chequean variantes con guion ("en-venta", "-venta-", slug termina en "-venta")
        # y también el path completo ("/Venta", "/Alquiler") para cubrir todos los CMS.
        slug_lower = slug.lower()
        path_lower = path.lower()
        if ("en-venta" in slug_lower or slug_lower.endswith("-venta")
                or "-venta-" in slug_lower or "/venta" in path_lower):
            detected_operacion = "venta"
        elif ("en-alquiler" in slug_lower or slug_lower.endswith("-alquiler")
              or "-alquiler-" in slug_lower or "/alquiler" in path_lower):
            detected_operacion = "alquiler"
        else:
            detected_operacion = operacion  # fallback (puede ser None)

        return Propiedad(
            url=url,
            titulo=titulo or slug.replace("-", " ").title() or "Sin título",
            precio=None,
            moneda=None,
            barrio=barrio,
            barrio_normalizado=DataCleaner.normalize_neighborhood(barrio) if barrio else None,
            tipo_propiedad=tipo,
            ciudad=ciudad,
            operacion=detected_operacion,
            fuente=fuente_key,
            direccion=direccion,
        )

    # ── Modo card: parsear containers ─────────────────────────────────────────
    _IMG_SKIP = {"logo", "icon", "placeholder", "blank", "spinner", "loading", "avatar"}

    if cards:
        for card in cards:
            # CAUSA 3: el selector de link sólo cubría 7 segmentos originales.
            # Ahora cubre todos los PROP_SEGMENTS + un último recurso genérico.
            link = card.select_one(
                'a[href*="/p/"],'
                'a[href*="/propiedad/"],'
                'a[href*="/propiedades/"],'
                'a[href*="/inmueble/"],'
                'a[href*="/inmuebles/"],'
                'a[href*="/property/"],'
                'a[href*="/properties/"],'
                'a[href*="/listing/"],'
                'a[href*="/listings/"],'
                'a[href*="/detalle/"],'
                'a[href*="/detalles/"],'
                'a[href*="/aviso/"],'
                'a[href*="/emprendimiento/"],'
                'a[href*="/Ficha/"],'
                'a[href*="/ficha/"],'
                'a[href*="ficha-"]'
            )
            # CAUSA 4: si ningún segmento conocido matchea, usar el primer link
            # del card que apunte a la misma base_url (evita quedar con 0 si el
            # CMS usa URLs sin segmento reconocible como /123-slug o /slug).
            if not link:
                for candidate in card.select("a[href]"):
                    ch = candidate.get("href", "")
                    if not ch or ch.startswith(("#", "javascript:", "mailto:", "tel:")):
                        continue
                    # Aceptar si el path tiene al menos 2 segmentos y no es nav/paginación
                    try:
                        _cp = urlparse(ch).path if ch.startswith("http") else ch.split("?")[0]
                    except Exception:
                        _cp = ch.split("?")[0]
                    _parts = [x for x in _cp.strip("/").split("/") if x]
                    if len(_parts) >= 2 and not any(
                        bad in ch for bad in ["/page/", "?page=", "#", "javascript:",
                                              "/buscar", "/search", "/contact", "/about",
                                              "/nosotros", "/quienes", "/servicios"]
                    ):
                        link = candidate
                        break
            if not link:
                continue
            href = link.get("href", "")

            # ── Rechazar links que apuntan a dominios externos (portales, redes, etc.) ──
            # Ocurre cuando un card tiene un botón "Ver en Argenprop/ZonaProp" etc.
            # que coincide con el selector (ej: /inmuebles/ en argenprop.com).
            if href.startswith("http"):
                try:
                    _href_netloc = urlparse(href).netloc.lower().lstrip("www.")
                    _base_netloc = urlparse(base_url).netloc.lower().lstrip("www.")
                    if (_href_netloc and _base_netloc
                            and _href_netloc != _base_netloc
                            and not _href_netloc.endswith("." + _base_netloc)
                            and not _base_netloc.endswith("." + _href_netloc)):
                        continue
                except Exception:
                    pass

            textos = [el.get_text(strip=True) for el in card.find_all(True)
                      if el.get_text(strip=True) and not el.find(True)]

            # ── PRECIO: buscar en selectores específicos primero, luego texto libre ──
            precio_raw = None
            for price_sel in ["[class*='price']", "[class*='precio']", ".aviso-precio",
                               ".property-price", "[class*='Price']", "strong", "b"]:
                el = card.select_one(price_sel)
                if el:
                    txt = el.get_text(strip=True)
                    if ("$" in txt or "USD" in txt or "U$S" in txt or
                            "US$" in txt or "usd" in txt.lower()):
                        precio_raw = txt
                        break
            if not precio_raw:
                precio_raw = next((t for t in textos if
                                   "$" in t or "USD" in t or "U$S" in t or "US$" in t), None)
            precio, moneda = DataCleaner.clean_price(precio_raw)

            # ── TÍTULO ─────────────────────────────────────────────────────────────
            titulo = None
            for title_sel in ["h2", "h3", "h1", "[class*='title']", "[class*='titulo']",
                               ".aviso-title", ".property-title"]:
                el = card.select_one(title_sel)
                if el:
                    txt = el.get_text(strip=True)
                    if len(txt) > 8 and "$" not in txt and "USD" not in txt:
                        titulo = txt[:150]
                        break
            if not titulo:
                titulo = next((t for t in textos if len(t) > 10 and "$" not in t
                               and "USD" not in t and "m²" not in t
                               and "Dormitorio" not in t and "Área" not in t
                               and "U$S" not in t), None)

            # ── TIPO: URL del href > texto del card > título ───────────────────────
            # Tokko Broker codifica el tipo en la URL: /p/1234567-Casa-en-Venta-...
            href_texto = href.replace("-", " ").replace("/", " ")
            tipo = DataCleaner.detect_property_type(href_texto)
            if tipo == "otro":
                tipo_raw = next((t for t in textos if t.lower() in
                                 ["casa", "departamento", "terreno", "local", "oficina",
                                  "cochera", "galpon", "galpón", "duplex", "dúplex", "ph"]), None)
                tipo = DataCleaner.normalize_property_type_token(tipo_raw or "")
            if tipo == "otro" and titulo:
                tipo = DataCleaner.detect_property_type(titulo)

            # ── OPERACIÓN: detectar por card (href > texto > parámetro global) ────
            # Tokko Broker codifica "en-venta"/"en-alquiler" en el slug de cada URL.
            # También se chequea "-venta-" y terminación "-venta" para variantes de CMS.
            href_lower = href.lower()
            card_texto_lower = " ".join(textos).lower()
            if ("en-venta" in href_lower or "/venta" in href_lower
                    or "-venta-" in href_lower or href_lower.endswith("-venta")):
                card_operacion = "venta"
            elif ("en-alquiler" in href_lower or "/alquiler" in href_lower
                  or "-alquiler-" in href_lower or href_lower.endswith("-alquiler")):
                card_operacion = "alquiler"
            elif "venta" in card_texto_lower and "alquiler" not in card_texto_lower:
                card_operacion = "venta"
            elif "alquiler" in card_texto_lower:
                card_operacion = "alquiler"
            else:
                card_operacion = operacion  # fallback al parámetro global (puede ser None)

            # ── DIRECCIÓN: extraer del slug del href filtrando palabras no-ubicación ──
            # Antes: "partes" incluía "Venta", "Alquiler", "Casa", etc. como parte del barrio.
            # Fix: se filtran por _SLUG_SKIP_WORDS para obtener solo palabras geográficas.
            href_path = href.split("?")[0]  # quitar query string
            partes = re.split(r"[-/]", href_path)
            nums = [p for p in partes if p.isdigit()]
            palabras = [p for p in partes
                        if not p.isdigit() and len(p) > 2 and p.lower() not in _SLUG_SKIP_WORDS]
            direccion = None
            if palabras and nums:
                calle = " ".join(palabras[-3:]) if len(palabras) >= 3 else " ".join(palabras[-2:])
                direccion = f"{calle} {nums[-1]}".title()
            # Fallback: usar ciudad como barrio para pasar is_valid()
            barrio = (ciudad or "Argentina") if not direccion else None

            # ── MÉTRICAS: metros, ambientes, dormitorios, baños ────────────────────
            # Muchos cards Tokko muestran "3 ambientes", "2 dorm.", "85 m²" en el texto.
            metros = None
            ambientes = None
            dormitorios = None
            banos = None
            texto_completo = " ".join(textos)
            m = re.search(r"(\d+)\s*(?:m²|m2|mts?\.?\s*(?:cuad)?)", texto_completo, re.IGNORECASE)
            if m:
                try:
                    v = int(m.group(1))
                    metros = v if 10 <= v <= 10000 else None
                except Exception:
                    pass
            texto_completo_lower = " ".join(textos).lower()
            def _card_num(text: str, kw: str) -> Optional[int]:
                m = (re.search(rf"(\d+)\s*(?:{kw})", text, re.IGNORECASE)
                     or re.search(rf"(?:{kw})[^0-9]{{0,15}}(\d+)", text, re.IGNORECASE))
                if m:
                    try:
                        return int(m.group(1))
                    except Exception:
                        pass
                return None
            if ambientes is None:
                ambientes = _card_num(texto_completo_lower, r"amb")
            if dormitorios is None:
                dormitorios = _card_num(texto_completo_lower, r"dorm|habit")
            if banos is None:
                banos = _card_num(texto_completo_lower, r"ba[ñn]")

            # ── IMAGEN: primer thumbnail del card que no sea logo/icon ────────────
            imagenes = []
            for img in card.select("img"):
                src = (img.get("src") or img.get("data-src") or
                       img.get("data-lazy-src") or img.get("data-original") or "").strip()
                if not src or src.startswith("data:"):
                    continue
                if not src.startswith("http"):
                    src = urljoin(base_url, src)
                lower = src.lower()
                if any(skip in lower for skip in _IMG_SKIP) or lower.endswith(".svg"):
                    continue
                imagenes = [src]
                break

            url = href if href.startswith("http") else urljoin(base_url, href)
            if url in seen:
                continue
            seen.add(url)

            prop = Propiedad(
                url=url,
                titulo=titulo or direccion or "Sin título",
                precio=precio,
                moneda=moneda,
                barrio=barrio,
                barrio_normalizado=DataCleaner.normalize_neighborhood(barrio) if barrio else None,
                tipo_propiedad=tipo,
                ciudad=ciudad,
                operacion=card_operacion,
                fuente=fuente_key,
                direccion=direccion,
                imagenes=imagenes,
                metros=metros,
                ambientes=ambientes,
                dormitorios=dormitorios,
                banos=banos,
            )
            if prop.is_valid():
                propiedades.append(prop)

        # ── Si el card mode encontró propiedades, devolver ─────────────────
        if propiedades:
            return propiedades
        # Si no encontró nada (ej: filtros del sidebar matchearon como cards),
        # caer al fallback de links directos ↓

    # ── Fallback: cosechar links directamente desde el HTML ───────────────────
    # Resuelve: repetto (Template4 CMS), vaccaro, tizado, y otros sitios donde
    # el card mode no funciona o los cards no tienen selectores reconocibles.
    for a in soup.find_all("a", href=True):
        href = a.get("href", "")
        if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
            continue

        # CAUSA 5: Evaluar PROP_SEGMENTS solo en el PATH de la URL.
        # Previene: WhatsApp share links donde /propiedad/ aparece en ?text=
        try:
            _href_path = urlparse(href).path if href.startswith("http") else href.split("?")[0]
        except Exception:
            _href_path = href.split("?")[0]

        # Usar _is_detail_url que valida el segmento Y filtra categorías
        if not _is_detail_url(_href_path):
            continue

        # Evitar paginación, anchors, búsquedas generales
        if any(bad in href for bad in ["/page/", "?page=", "/busqueda/",
                                        "/buscar/", "/search/"]):
            continue

        card_text = a.get_text(strip=True)
        if not card_text:
            parent = a.parent
            if parent:
                card_text = parent.get_text(strip=True)[:150]

        prop = _make_prop_from_url(href, card_text)
        if prop and prop.is_valid():
            propiedades.append(prop)

    return propiedades


def enrich_detail(
    propiedades: List[Propiedad],
    context,
    fuente_key: str,
    max_enriched: int = 8,
) -> int:
    """
    Visita las páginas de ficha individual para propiedades sin precio/métricas.
    Extrae precio, moneda, metros, dormitorios, banos, ambientes e imagenes.
    Retorna la cantidad de propiedades efectivamente enriquecidas.

    Se llama ANTES de guardar en DB, en el mismo BrowserContext que ya existe
    para la fuente (sin abrir un browser extra). max_enriched limita el total
    de requests extra por fuente para no ser excesivamente lento.
    """
    # Solo enriquecer propiedades sin precio (son las que más lo necesitan)
    candidatos = [p for p in propiedades if p.precio is None][:max_enriched]
    if not candidatos:
        return 0

    _PRICE_SELS = [
        "[class*='price']", "[class*='precio']", ".aviso-precio",
        ".property-price", ".prop-precio", "[class*='Price']", "strong", "b",
    ]
    _IMG_SKIP_SET = {"logo", "icon", "placeholder", "blank", "spinner", "loading", "avatar"}
    enriched_count = 0
    consecutive_timeouts = 0  # salir temprano si el sitio es inaccesible

    for p in candidatos:
        # Si 2 fichas seguidas fallaron, el sitio probablemente está caído o
        # bloqueando — no tiene sentido seguir gastando tiempo en él.
        if consecutive_timeouts >= 2:
            logger.debug(
                f"[{fuente_key}] enrich_detail: 2 timeouts consecutivos, abortando"
            )
            break

        try:
            detail_page = context.new_page()
        except Exception as _ctx_err:
            # BrowserContext cerrado (ej: Ctrl+C durante enrich) — salir limpiamente
            if "closed" in str(_ctx_err).lower():
                logger.debug(f"[{fuente_key}] enrich_detail: contexto cerrado, abortando")
                break
            continue

        try:
            ok = _goto_safe(detail_page, p.url, 12000)
            if not ok:
                consecutive_timeouts += 1
                continue
            consecutive_timeouts = 0  # reset al tener éxito
            # Esperar precio visible
            try:
                detail_page.wait_for_selector(
                    "[class*='price'],[class*='precio'],.aviso-precio,.property-price",
                    state="visible",
                    timeout=3000,
                )
            except Exception:
                pass

            html = detail_page.content()
            soup = BeautifulSoup(html, "html.parser")

            # ── PRECIO ─────────────────────────────────────────────────────────
            if p.precio is None:
                for sel in _PRICE_SELS:
                    el = soup.select_one(sel)
                    if el:
                        txt = el.get_text(strip=True)
                        if any(c in txt for c in ["$", "USD", "U$S", "US$"]):
                            precio, moneda = DataCleaner.clean_price(txt)
                            if precio:
                                p.precio = precio
                                p.moneda = moneda
                                enriched_count += 1
                                break

            # ── METROS ─────────────────────────────────────────────────────────
            if p.metros is None:
                for sel in ["[class*='surface']", "[class*='metros']",
                             "[class*='area']", "[class*='m2']"]:
                    el = soup.select_one(sel)
                    if el:
                        v = DataCleaner.extract_area_m2(el.get_text())
                        if v:
                            p.metros = v
                            break
                if p.metros is None:
                    p.metros = DataCleaner.extract_area_m2(soup.get_text())

            # ── DORMITORIOS / BAÑOS / AMBIENTES ────────────────────────────────
            # Soporta "3 dormitorios" (número antes) Y "Dormitorios: 3" (número después)
            full_text = soup.get_text(" ", strip=True)

            def _extract_num(text: str, keywords: str) -> Optional[int]:
                m = (re.search(rf"(\d+)\s*(?:{keywords})", text, re.IGNORECASE)
                     or re.search(rf"(?:{keywords})[^0-9]{{0,15}}(\d+)", text, re.IGNORECASE))
                if m:
                    try:
                        return int(m.group(1))
                    except Exception:
                        pass
                return None

            if p.dormitorios is None:
                p.dormitorios = _extract_num(full_text, r"dorm|habit")
            if p.banos is None:
                p.banos = _extract_num(full_text, r"ba[ñn]")
            if p.ambientes is None:
                p.ambientes = _extract_num(full_text, r"amb")

            # ── IMÁGENES (si la ficha tiene más que el thumbnail del listado) ──
            if len(p.imagenes) < 2:
                imgs = []
                for img in soup.select(
                    "#gallery img, .gallery img, .slider img, .carousel img, "
                    "[class*='slider'] img, [class*='gallery'] img, article img"
                ):
                    src = (img.get("src") or img.get("data-src") or
                           img.get("data-lazy-src") or "").strip()
                    if not src or src.startswith("data:") or not src.startswith("http"):
                        continue
                    sl = src.lower()
                    if any(s in sl for s in _IMG_SKIP_SET) or sl.endswith(".svg"):
                        continue
                    if src not in imgs:
                        imgs.append(src)
                    if len(imgs) >= 5:
                        break
                if imgs:
                    p.imagenes = imgs

        except Exception as exc:
            logger.debug(f"[{fuente_key}] enrich_detail error en {p.url}: {exc}")
        finally:
            try:
                detail_page.close()
            except Exception:
                pass

    if enriched_count:
        logger.info(
            f"[{fuente_key}] enrich_detail: {enriched_count}/{len(candidatos)} precios obtenidos"
        )
    return enriched_count


# =============================================================================
# SCRAPER DE FICHA INDIVIDUAL — extrae TODOS los campos desde la página de detalle
# =============================================================================

def _apply_feature(prop: "Propiedad", label: str, value: str) -> None:
    """Aplica un par label/value a los campos del Propiedad."""
    lbl = label.lower().strip()
    val = value.strip()
    m = re.search(r"\d+", val)
    num = int(m.group(0)) if m else None
    if any(k in lbl for k in ("dorm", "habit")):
        if prop.dormitorios is None and num:
            prop.dormitorios = num
    elif "baño" in lbl or "bano" in lbl:
        if prop.banos is None and num:
            prop.banos = num
    elif "ambi" in lbl:
        if prop.ambientes is None and num:
            prop.ambientes = num
    elif any(k in lbl for k in ("sup", "m²", "metro", "area", "superficie")):
        if prop.metros is None and num and 10 <= num <= 10000:
            prop.metros = num
    elif any(k in lbl for k in ("tipo", "inmueble", "propiedad", "tipolog")):
        if prop.tipo_propiedad in (None, "otro"):
            t = DataCleaner.normalize_property_type_token(val.lower())
            if t != "otro":
                prop.tipo_propiedad = t


def _apply_feature_text(prop: "Propiedad", text: str) -> None:
    """Aplica un texto libre de un <li> al Propiedad (cuando no hay spans separados)."""
    tl = text.lower()
    m = re.search(r"\d+", text)
    num = int(m.group(0)) if m else None
    if not num:
        return
    if any(k in tl for k in ("dorm", "habit")) and prop.dormitorios is None:
        prop.dormitorios = num
    elif ("baño" in tl or "bano" in tl) and prop.banos is None:
        prop.banos = num
    elif "ambi" in tl and prop.ambientes is None:
        prop.ambientes = num
    elif any(k in tl for k in ("sup", "m²", "metro")) and prop.metros is None:
        if 10 <= num <= 10000:
            prop.metros = num


def scrape_detail_page(page, prop: "Propiedad", fuente_key: str,
                       timeout: int = 20000) -> bool:
    """
    Visita la ficha individual de una propiedad y completa TODOS sus campos.
    Modifica `prop` in-place. Retorna True si la página cargó correctamente.

    Cubre:
      - Tokko Broker (todos los themes — dl.horizontal, feature lists, spans)
      - CMS propios comunes (tablas key-value, listas, texto libre)
    """
    try:
        ok = _goto_safe(page, prop.url, timeout)
        if not ok:
            return False

        try:
            page.wait_for_selector(
                "h1, h2, [class*='price'], [class*='precio'], [class*='property']",
                state="attached", timeout=6000,
            )
        except Exception:
            pass

        html = page.content()
        soup = BeautifulSoup(html, "html.parser")
        full_text = soup.get_text(" ", strip=True)

        # ── PRECIO ──────────────────────────────────────────────────────────
        if prop.precio is None:
            for sel in [
                "[class*='price']", "[class*='precio']", ".aviso-precio",
                ".property-price", ".prop-precio", "[class*='Price']",
                "[itemprop='price']", "strong", "b",
            ]:
                el = soup.select_one(sel)
                if el:
                    txt = el.get_text(strip=True)
                    if any(c in txt for c in ("$", "USD", "U$S", "US$")):
                        p, m = DataCleaner.clean_price(txt)
                        if p:
                            prop.precio, prop.moneda = p, m
                            break

        # ── TÍTULO ──────────────────────────────────────────────────────────
        # El h1 de la ficha es más confiable que el texto del card
        for sel in [
            "h1.property-title", "[class*='property-title'] h1",
            "[class*='titulo'] h1", "h1[class*='title']",
            "[class*='property-title']", "h1",
        ]:
            el = soup.select_one(sel)
            if el:
                txt = el.get_text(strip=True)
                if txt and len(txt) > 4 and "$" not in txt and "USD" not in txt:
                    prop.titulo = txt[:200]
                    break

        # ── DIRECCIÓN ───────────────────────────────────────────────────────
        if not prop.direccion:
            for sel in [
                "[class*='address']", "[class*='direccion']", "address",
                "[itemprop='streetAddress']", ".property-address",
                "[class*='location'] h2", "[class*='location'] h3",
                "h2[class*='address']", "h2[class*='ubicac']",
            ]:
                el = soup.select_one(sel)
                if el:
                    txt = el.get_text(strip=True)
                    if txt and 4 < len(txt) < 150:
                        cleaned = DataCleaner.clean_address(txt)
                        if cleaned:
                            prop.direccion = cleaned
                            break

        # ── BARRIO ──────────────────────────────────────────────────────────
        if not prop.barrio or prop.barrio == prop.ciudad:
            for sel in [
                "[class*='neighborhood']", "[class*='barrio']",
                "[itemprop='addressLocality']", ".property-location",
                "[class*='location']",
            ]:
                el = soup.select_one(sel)
                if el:
                    txt = el.get_text(strip=True)
                    if txt and 2 < len(txt) < 80 and txt != prop.ciudad:
                        prop.barrio = txt
                        prop.barrio_normalizado = DataCleaner.normalize_neighborhood(txt)
                        break

        # ── CARACTERÍSTICAS ─────────────────────────────────────────────────
        # Estrategia 1: dl.horizontal — Tokko Broker clásico / Bootstrap 3
        dts = soup.select(
            "dl.dl-horizontal dt, .service-list dt, "
            "[class*='detail-list'] dt, [class*='features-list'] dt, "
            "[class*='property-features'] dt"
        )
        dds = soup.select(
            "dl.dl-horizontal dd, .service-list dd, "
            "[class*='detail-list'] dd, [class*='features-list'] dd, "
            "[class*='property-features'] dd"
        )
        for dt, dd in zip(dts, dds):
            _apply_feature(prop, dt.get_text(strip=True), dd.get_text(strip=True))

        # Estrategia 2: li items con spans label + value — Tokko Broker moderno
        for item in soup.select(
            "[class*='feature'] li, [class*='amenity'] li, "
            "[class*='characteristic'] li, [class*='stats'] li, "
            "[class*='spec'] li, [class*='property-detail'] li, "
            "ul[class*='prop'] li, ul[class*='info'] li, "
            "[class*='overview'] li"
        ):
            spans = item.select("span, b, strong")
            if len(spans) >= 2:
                _apply_feature(prop, spans[0].get_text(strip=True), spans[-1].get_text(strip=True))
            else:
                _apply_feature_text(prop, item.get_text(" ", strip=True))

        # Estrategia 3: tabla key-value (CMS propios con <table>)
        for row in soup.select("table tr"):
            cells = row.select("td, th")
            if len(cells) >= 2:
                _apply_feature(prop, cells[0].get_text(strip=True), cells[1].get_text(strip=True))

        # Estrategia 4: elementos con class semántica de rooms/superficie
        for el in soup.select(
            "[class*='dorm'], [class*='bedroom'], [class*='room-count'], "
            "[class*='bano'], [class*='bath'], "
            "[class*='surface'], [class*='metros'], [class*='m2-']"
        ):
            classes = " ".join(el.get("class", []))
            txt = el.get_text(strip=True).lower()
            m_num = re.search(r"\d+", txt)
            num = int(m_num.group(0)) if m_num else None
            if not num:
                continue
            if any(k in classes for k in ("dorm", "bedroom", "room")) and prop.dormitorios is None:
                prop.dormitorios = num
            elif any(k in classes for k in ("bano", "bath")) and prop.banos is None:
                prop.banos = num
            elif any(k in classes for k in ("surface", "metros", "m2")) and prop.metros is None:
                if 10 <= num <= 10000:
                    prop.metros = num

        # Estrategia 5: regex bidireccional sobre el texto completo (fallback final)
        def _bidir(kw: str) -> Optional[int]:
            m = (re.search(rf"(\d+)\s*(?:{kw})", full_text, re.IGNORECASE)
                 or re.search(rf"(?:{kw})[^0-9]{{0,20}}(\d+)", full_text, re.IGNORECASE))
            return int(m.group(1)) if m else None

        if prop.dormitorios is None:
            prop.dormitorios = _bidir(r"dorm(?:itorios?)?|habit(?:aciones?)?")
        if prop.banos is None:
            prop.banos = _bidir(r"ba[ñn](?:os?)?")
        if prop.ambientes is None:
            prop.ambientes = _bidir(r"amb(?:ientes?)?")
        if prop.metros is None:
            prop.metros = DataCleaner.extract_area_m2(full_text)

        # ── TIPO DE PROPIEDAD ────────────────────────────────────────────────
        if prop.tipo_propiedad in (None, "otro"):
            prop.tipo_propiedad = DataCleaner.detect_property_type(
                f"{prop.titulo or ''} {full_text[:500]}"
            )

        # ── DESCRIPCIÓN ─────────────────────────────────────────────────────
        if not prop.descripcion:
            for sel in [
                "[class*='description']", ".property-description",
                ".tokko-description", ".entry-content",
                "[class*='content'] p", "article p", "main p",
            ]:
                el = soup.select_one(sel)
                if el:
                    txt = el.get_text(" ", strip=True)
                    if len(txt) > 50:
                        prop.descripcion = txt[:3000]
                        break

        # ── IMÁGENES ────────────────────────────────────────────────────────
        if len(prop.imagenes) < 3:
            imgs: List[str] = []
            _SKIP = {"logo", "icon", "placeholder", "blank", "spinner", "avatar", "loading"}
            for img in soup.select(
                "#gallery img, .gallery img, [class*='gallery'] img, "
                "[class*='slider'] img, [class*='photo'] img, "
                "[class*='imagen'] img, .carousel img, article img, main img"
            ):
                src = (
                    img.get("src") or img.get("data-src") or
                    img.get("data-lazy-src") or img.get("data-original") or ""
                ).strip()
                if not src or src.startswith("data:"):
                    continue
                if not src.startswith("http"):
                    src = urljoin(prop.url, src)
                sl = src.lower()
                if any(s in sl for s in _SKIP) or sl.endswith(".svg"):
                    continue
                if src not in imgs:
                    imgs.append(src)
                if len(imgs) >= 10:
                    break
            if imgs:
                prop.imagenes = imgs

        # ── OPERACIÓN ───────────────────────────────────────────────────────
        if not prop.operacion:
            url_lower = prop.url.lower()
            if "venta" in url_lower:
                prop.operacion = "venta"
            elif "alquiler" in url_lower:
                prop.operacion = "alquiler"
            else:
                prop.operacion = DataCleaner.detect_operation_from_text(
                    prop.titulo, prop.descripcion
                )

        # Garantizar barrio mínimo para pasar is_valid()
        if not prop.barrio:
            prop.barrio = prop.ciudad or "Argentina"

        return True

    except Exception as exc:
        logger.debug(f"[{fuente_key}] Error scrapeando ficha {prop.url}: {exc}")
        return False


def _get_next_page_url(html: str, current_url: str) -> Optional[str]:
    """
    Detecta si hay una página siguiente en la paginación numerada.
    Retorna la URL absoluta de la siguiente página, o None si no hay.
    No aplica para Tokko Broker (usa infinite scroll, ya cubierto por scroll_to_bottom).
    """
    soup = BeautifulSoup(html, "html.parser")

    # 1. rel="next" — el estándar más confiable
    el = soup.select_one('a[rel="next"]')
    if el:
        href = el.get("href", "").strip()
        if href and href not in ("#", "javascript:void(0)", current_url):
            return href if href.startswith("http") else urljoin(current_url, href)

    # 2. Link con texto de "siguiente"
    for a in soup.find_all("a", href=True):
        txt = a.get_text(strip=True).lower()
        href = a.get("href", "").strip()
        if not href or href in ("#", "javascript:void(0)", current_url):
            continue
        if txt in ("siguiente", "next", ">", "›", "»", "→"):
            return href if href.startswith("http") else urljoin(current_url, href)

    # 3. Elemento con class *next* que tenga href
    for sel in ('[class*="next"] a[href]', 'a[class*="next"][href]',
                '.pagination .active + li a[href]', 'li.next a[href]'):
        el = soup.select_one(sel)
        if el:
            href = el.get("href", "").strip()
            if href and href not in ("#", "javascript:void(0)", current_url):
                return href if href.startswith("http") else urljoin(current_url, href)

    return None


def parse_apl_cards(html: str) -> List[Propiedad]:
    """Parser específico para APL Inmobiliaria (mercado-unico CMS)."""
    soup = BeautifulSoup(html, "html.parser")
    cards = soup.select(".card.card-property")
    propiedades = []
    seen = set()

    for card in cards:
        # URL
        link = card.select_one("a[href*='/propiedades/']")
        if not link:
            continue
        url = link.get("href", "")
        if not url.startswith("http"):
            url = "https://aplinmobiliaria.com" + url
        if url in seen:
            continue
        seen.add(url)

        # Título / dirección
        titulo_el = card.select_one("h5.card-title")
        titulo = titulo_el.get_text(strip=True) if titulo_el else None

        # Barrio
        barrio_el = card.select_one("span.badge.text-bg-gray")
        barrio = barrio_el.get_text(strip=True) if barrio_el else None

        # Operación: "Venta" o "Alquiler" en el badge de color
        operacion = None
        badge = card.select_one("span.badge.bg-success, span.badge.bg-warning, span.badge.bg-info")
        if badge:
            texto_badge = badge.get_text(strip=True).lower()
            if "venta" in texto_badge:
                operacion = "venta"
            elif "alquiler" in texto_badge:
                operacion = "alquiler"
        # Fallback: detectar desde la URL
        if not operacion:
            url_lower = url.lower()
            if "compraventa" in url_lower or "venta" in url_lower:
                operacion = "venta"
            elif "alquiler" in url_lower or "arriendo" in url_lower:
                operacion = "alquiler"

        # Tipo de propiedad: desde el alt de la imagen o el texto del card
        tipo = "otro"
        img = card.select_one("img")
        if img:
            alt = img.get("alt", "").lower()
            tipo = DataCleaner.detect_property_type(alt)
        if tipo == "otro" and titulo:
            tipo = DataCleaner.detect_property_type(titulo)

        # Precio: no está en el card, se deja None (lo busca el detail extractor)
        precio = None
        moneda = None

        # Metros: buscar en los spans de detalles
        metros = None
        for det in card.select("span.property-detail"):
            texto = det.get_text(strip=True)
            if "m2" in texto.lower() or "m²" in texto.lower():
                metros = DataCleaner.extract_area_m2(texto)
                break

        # Ciudad: filtrar solo Santa Fe capital
        ciudad = "Santa Fe"
        # Si el barrio o URL menciona Santo Tomé, Sauce Viejo, etc. igual lo guardamos
        # (el usuario puede filtrar por ciudad en Supabase)

        if not titulo:
            titulo = barrio or "Sin título"

        # Fallback de barrio: si el card no tenía badge de barrio, usar la ciudad
        barrio = barrio or ciudad

        prop = Propiedad(
            url=url,
            titulo=titulo,
            precio=precio,
            moneda=moneda,
            barrio=barrio,
            barrio_normalizado=DataCleaner.normalize_neighborhood(barrio),
            tipo_propiedad=tipo,
            ciudad=ciudad,
            operacion=operacion,
            fuente="apl",
            metros=metros,
        )

        if prop.is_valid():
            propiedades.append(prop)

    return propiedades


def scrape_apl(supabase: SupabaseClient, existing_urls: set, context) -> None:
    """Scraper dedicado para APL Inmobiliaria."""
    url = "https://aplinmobiliaria.com/propiedades"
    logger.info(f"[apl] Scrapeando {url}")

    page = context.new_page()
    try:
        # _goto_safe usa domcontentloaded + 40s — más robusto que networkidle 90s
        ok = _goto_safe(page, url, 40000)
        if not ok:
            logger.warning("[apl] No se pudo cargar la página")
            return
        page.wait_for_timeout(3000)

        # Scroll para cargar todo el contenido
        prev = 0
        for _ in range(8):
            try:
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                page.wait_for_timeout(1500)
                count = len(page.query_selector_all(".card.card-property"))
            except Exception:
                break
            if count == prev and count > 0:
                break
            prev = count

        logger.info(f"[apl] {prev} cards encontradas")

        propiedades = parse_apl_cards(page.content())
        # is_valid() se verifica en parse_apl_cards — propiedades ya filtradas
        nuevas = [p for p in propiedades if p.url not in existing_urls]
        logger.info(f"[apl] {len(nuevas)} nuevas de {len(propiedades)}")

        if nuevas:
            saved = supabase.batch_save_only_new([p.to_payload() for p in nuevas])
            logger.info(f"[apl] Guardadas: {saved}")
            existing_urls.update(p.url for p in nuevas)

    except Exception as exc:
        logger.error(f"[apl] Error: {exc}")
    finally:
        page.close()


def scrape_raffin(supabase: SupabaseClient, existing_urls: set, context) -> None:
    """Scraper para Raffin Inmobiliaria (Pixel Inmobiliario CMS)."""
    FUENTES = [
        ("https://www.raffininmobiliaria.com.ar/listing?user_id=1137&purpose=sale",   "venta"),
        ("https://www.raffininmobiliaria.com.ar/listing?user_id=1137&purpose=rent",   "alquiler"),
    ]
    BASE = "https://www.raffininmobiliaria.com.ar"

    for url, operacion in FUENTES:
        logger.info(f"[raffin_{operacion}] Scrapeando {url}")
        page = context.new_page()
        try:
            ok = _goto_safe(page, url, 40000)
            if not ok:
                logger.warning(f"[raffin_{operacion}] No se pudo cargar")
                continue
            page.wait_for_timeout(2500)

            soup = BeautifulSoup(page.content(), "html.parser")
            cards = soup.select(".thumbnail_one")
            logger.info(f"[raffin_{operacion}] {len(cards)} cards encontradas")

            nuevas = []
            for card in cards:
                link = card.select_one("a[href*='/ad/']")
                if not link:
                    continue
                prop_url = link.get("href", "")
                if not prop_url.startswith("http"):
                    prop_url = BASE + prop_url
                if prop_url in existing_urls:
                    continue

                # Título: alt de la imagen suele ser "Tipo en Venta - Dirección"
                img = card.select_one("img")
                titulo = img.get("alt", "").strip() if img else None

                # Precio
                precio_el = card.select_one(".area_price p, .sale")
                precio_raw = precio_el.get_text(strip=True) if precio_el else None
                precio, moneda = DataCleaner.clean_price(precio_raw)

                # Tipo
                tipo = DataCleaner.detect_property_type(titulo or "")

                # Metros
                metros = None
                metros_el = card.select_one(".area_price span")
                if metros_el:
                    metros = DataCleaner.extract_area_m2(metros_el.get_text(strip=True))

                if not titulo:
                    titulo = prop_url.split("/ad/")[-1].replace("-", " ").title()

                # Dirección: intentar extraer del título
                direccion = DataCleaner.clean_address(titulo) if titulo else None

                prop = Propiedad(
                    url=prop_url,
                    titulo=titulo,
                    precio=precio,
                    moneda=moneda,
                    tipo_propiedad=tipo,
                    ciudad="Santa Fe",
                    operacion=operacion,
                    fuente="raffin",
                    metros=metros,
                    direccion=direccion,
                    barrio="Santa Fe",  # fallback para pasar is_valid()
                )
                if prop.is_valid():
                    nuevas.append(prop)

            logger.info(f"[raffin_{operacion}] {len(nuevas)} nuevas")
            if nuevas:
                saved = supabase.batch_save_only_new([p.to_payload() for p in nuevas])
                logger.info(f"[raffin_{operacion}] Guardadas: {saved}")
                existing_urls.update(p.url for p in nuevas)

        except Exception as exc:
            logger.error(f"[raffin_{operacion}] Error: {exc}")
        finally:
            page.close()


def scrape_9010(supabase: SupabaseClient, existing_urls: set, session: requests.Session) -> None:
    """Scraper dedicado para 9010 Inmobiliaria (PHP estático, sin Playwright)."""
    BASE = "https://www.9010inmobiliaria.com.ar/"
    FUENTES_9010 = [
        (BASE + "propiedades-en-venta.php",    "venta"),
        (BASE + "propiedades-en-alquiler.php", "alquiler"),
    ]
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0",
        "Accept-Language": "es-AR,es;q=0.9",
    }

    def parse_detalle(url: str, operacion_fallback: str) -> Optional[dict]:
        try:
            r = session.get(url, headers=HEADERS, timeout=15)
            if r.status_code != 200:
                return None
            soup = BeautifulSoup(r.text, "html.parser")
            texto = soup.get_text(" ", strip=True)

            # Título
            titulo_el = soup.find("h1") or soup.find("h2") or soup.find("title")
            titulo = titulo_el.get_text(strip=True).split("|")[0].strip() if titulo_el else None
            if titulo and "9010" in titulo:
                titulo = titulo.split("9010")[0].strip(" |-")

            # Operación
            operacion = operacion_fallback
            m = re.search(r'Operaci[oó]n[:\s]+(\w+)', texto)
            if m:
                op = m.group(1).lower()
                if "venta" in op:
                    operacion = "venta"
                elif "alquiler" in op:
                    operacion = "alquiler"

            # Tipo de propiedad
            tipo = "otro"
            m = re.search(r'Inmueble[:\s]+([^\n\r]+?)(?:\s+Operaci)', texto)
            if m:
                tipo = DataCleaner.detect_property_type(m.group(1))

            # Dormitorios
            dormitorios = None
            m = re.search(r'Dormitorios[:\s]+(\d+)', texto)
            if m:
                dormitorios = int(m.group(1))

            # Baños
            banos = None
            m = re.search(r'Ba[ñn]os[:\s]+(\d+)', texto)
            if m:
                banos = int(m.group(1))

            # Metros
            metros = None
            m = re.search(r'Sup\.\s*\(m2\)[:\s]+([\d.,]+)', texto)
            if m:
                try:
                    metros = int(float(m.group(1).replace(",", ".")))
                except ValueError:
                    pass

            # Precio
            precio = None
            moneda = None
            m_precio = re.search(r'(USD|U\$S|U\$D|\$)\s*([\d.,]+)', texto)
            if m_precio:
                precio, moneda = DataCleaner.clean_price(m_precio.group(0))

            return {
                "titulo": titulo,
                "operacion": operacion,
                "tipo": tipo,
                "dormitorios": dormitorios,
                "banos": banos,
                "metros": metros,
                "precio": precio,
                "moneda": moneda,
            }
        except Exception as exc:
            logger.debug(f"[9010] Error detalle {url}: {exc}")
            return None

    total_nuevas = 0
    for listing_url, operacion_forzada in FUENTES_9010:
        logger.info(f"[9010] Scrapeando {listing_url}")
        try:
            r = session.get(listing_url, headers=HEADERS, timeout=15)
            if r.status_code != 200:
                logger.warning(f"[9010] HTTP {r.status_code} en {listing_url}")
                continue
            soup = BeautifulSoup(r.text, "html.parser")

            urls_prop = list(dict.fromkeys([
                BASE + a["href"]
                for a in soup.find_all("a", href=True)
                if a["href"].startswith("p-")
            ]))
            logger.info(f"[9010] {len(urls_prop)} propiedades encontradas")

            nuevas = [u for u in urls_prop if u not in existing_urls]
            logger.info(f"[9010] {len(nuevas)} nuevas")

            payloads = []
            for url in nuevas:
                det = parse_detalle(url, operacion_forzada)
                if not det or not det.get("titulo"):
                    continue
                prop = Propiedad(
                    url=url,
                    titulo=det["titulo"],
                    precio=det["precio"],
                    moneda=det["moneda"],
                    tipo_propiedad=det["tipo"] or "otro",
                    ciudad="Santa Fe",
                    operacion=det["operacion"],
                    fuente="novenodiez",
                    dormitorios=det["dormitorios"],
                    banos=det["banos"],
                    metros=det["metros"],
                )
                if prop.titulo and len(prop.titulo) >= 3:
                    payloads.append(prop.to_payload())
                time.sleep(0.5)

            if payloads:
                saved = supabase.batch_save_only_new(payloads)
                logger.info(f"[9010] Guardadas: {saved}")
                existing_urls.update(nuevas)
                total_nuevas += saved

        except Exception as exc:
            logger.error(f"[9010] Error en {listing_url}: {exc}")

    logger.info(f"[9010] Total guardadas: {total_nuevas}")


def scrape_lenarduzzi(supabase: SupabaseClient, existing_urls: set, session: requests.Session) -> None:
    """Scraper para Lenarduzzi usando cookie del navegador."""
    import os
    COOKIE = os.environ.get("LENARDUZZI_COOKIE", "")
    if not COOKIE:
        logger.warning("[lenarduzzi] LENARDUZZI_COOKIE no configurada, saltando.")
        return

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "es-AR,es-419;q=0.9,es;q=0.8",
        "Cookie": COOKIE,
        "Referer": "https://www.google.com/",
    }

    FUENTES = [
        ("https://lenarduzzi.com.ar/estado/venta/page/{}/",    "venta"),
        ("https://lenarduzzi.com.ar/estado/alquiler/page/{}/", "alquiler"),
    ]

    for base_url, operacion in FUENTES:
        logger.info(f"[lenarduzzi_{operacion}] Iniciando")
        page_num = 1
        empty_pages = 0
        total_nuevas = 0

        while empty_pages < 2:
            url = base_url.format(page_num)
            try:
                resp = session.get(url, headers=headers, timeout=20)
                if resp.status_code == 403:
                    logger.warning(f"[lenarduzzi] Cookie expirada — renovar LENARDUZZI_COOKIE en .env")
                    return
                if resp.status_code != 200:
                    empty_pages += 1
                    page_num += 1
                    continue

                soup = BeautifulSoup(resp.text, "html.parser")
                cards = soup.select(".property-item")

                if not cards:
                    empty_pages += 1
                    page_num += 1
                    continue

                empty_pages = 0
                nuevas = []

                for card in cards:
                    link = card.select_one("a[href*='/propiedades/']")
                    if not link:
                        continue
                    prop_url = link.get("href", "")
                    if prop_url in existing_urls:
                        continue

                    titulo_el = card.select_one(".item-title, h2, h3")
                    titulo = titulo_el.get_text(strip=True) if titulo_el else None

                    precio_el = card.select_one(".item-price")
                    precio, moneda = DataCleaner.clean_price(precio_el.get_text(strip=True) if precio_el else None)

                    op = operacion
                    label = card.select_one(".label-status a")
                    if label:
                        texto_label = label.get_text(strip=True).lower()
                        if "venta" in texto_label:
                            op = "venta"
                        elif "alquiler" in texto_label:
                            op = "alquiler"

                    direccion_el = card.select_one(".item-address, [class*='address']")
                    direccion = direccion_el.get_text(strip=True) if direccion_el else None

                    if not titulo and direccion:
                        titulo = direccion

                    tipo = DataCleaner.detect_property_type(titulo or "")

                    prop = Propiedad(
                        url=prop_url,
                        titulo=titulo or "Sin título",
                        precio=precio,
                        moneda=moneda,
                        tipo_propiedad=tipo,
                        ciudad="Santa Fe",
                        operacion=op,
                        fuente="lenarduzzi",
                        direccion=direccion,
                    )
                    if prop.titulo and len(prop.titulo) >= 3:
                        nuevas.append(prop)

                logger.info(f"[lenarduzzi_{operacion}] Página {page_num}: {len(cards)} cards | {len(nuevas)} nuevas")

                if nuevas:
                    saved = supabase.batch_save_only_new([p.to_payload() for p in nuevas])
                    logger.info(f"[lenarduzzi_{operacion}] Guardadas: {saved}")
                    existing_urls.update(p.url for p in nuevas)
                    total_nuevas += saved

            except Exception as exc:
                logger.error(f"[lenarduzzi_{operacion}] Error página {page_num}: {exc}")
                empty_pages += 1

            page_num += 1
            time.sleep(1.5)

        logger.info(f"[lenarduzzi_{operacion}] Total guardadas: {total_nuevas}")


def scrape_pilay(supabase: SupabaseClient, existing_urls: set, context) -> None:
    """Scraper para Pilay Inmobiliaria con paginación."""
    BASE = "https://www.pilayinmobiliaria.com"
    FUENTES = [
        (f"{BASE}/search-results/?status%5B0%5D=venta",    "venta"),
        (f"{BASE}/search-results/?status%5B0%5D=alquiler", "alquiler"),
        (f"{BASE}/search-results/?status%5B0%5D=proyectos","proyecto"),
    ]

    for base_url, operacion in FUENTES:
        logger.info(f"[pilay_{operacion}] Iniciando")
        total_nuevas = 0
        page_num = 1
        empty_pages = 0

        while empty_pages < 2:
            if page_num == 1:
                url = base_url
            else:
                url = base_url.replace("/search-results/", f"/search-results/page/{page_num}/")

            page = context.new_page()
            try:
                ok = _goto_safe(page, url, 40000)
                if not ok:
                    empty_pages += 1
                    page.close()
                    page_num += 1
                    continue
                page.wait_for_timeout(3000)

                soup = BeautifulSoup(page.content(), "html.parser")
                cards = soup.select(".item-listing-wrap")

                if not cards:
                    empty_pages += 1
                    page.close()
                    page_num += 1
                    continue

                empty_pages = 0
                nuevas = []
                seen = set()

                for card in cards:
                    link = card.select_one("a[href*='/property/']")
                    if not link:
                        continue
                    prop_url = link.get("href", "")
                    if not prop_url.startswith("http"):
                        prop_url = BASE + prop_url
                    if prop_url in existing_urls or prop_url in seen:
                        continue
                    seen.add(prop_url)

                    titulo_el = card.select_one(".item-title, h2, h3, .listing-title")
                    titulo = titulo_el.get_text(strip=True) if titulo_el else None

                    precio_el = card.select_one(".item-price")
                    precio, moneda = DataCleaner.clean_price(
                        precio_el.get_text(strip=True) if precio_el else None
                    )

                    tipo = DataCleaner.detect_property_type(titulo or prop_url)

                    dir_el = card.select_one(".item-address, [class*='address']")
                    direccion = dir_el.get_text(strip=True) if dir_el else None

                    if not titulo:
                        titulo = prop_url.split("/property/")[-1].replace("-", " ").strip("/").title()

                    prop = Propiedad(
                        url=prop_url,
                        titulo=titulo,
                        precio=precio,
                        moneda=moneda,
                        tipo_propiedad=tipo,
                        ciudad="Santa Fe",
                        operacion=operacion,
                        fuente="pilay",
                        direccion=direccion,
                        barrio=direccion or "Santa Fe",  # fallback para is_valid()
                    )
                    if prop.is_valid():
                        nuevas.append(prop)

                logger.info(f"[pilay_{operacion}] Página {page_num}: {len(cards)} cards | {len(nuevas)} nuevas")

                if nuevas:
                    saved = supabase.batch_save_only_new([p.to_payload() for p in nuevas])
                    logger.info(f"[pilay_{operacion}] Guardadas: {saved}")
                    existing_urls.update(p.url for p in nuevas)
                    total_nuevas += saved

            except Exception as exc:
                logger.error(f"[pilay_{operacion}] Error página {page_num}: {exc}")
                empty_pages += 1
            finally:
                page.close()

            page_num += 1
            time.sleep(1.5)

        logger.info(f"[pilay_{operacion}] Total guardadas: {total_nuevas}")


def scrape_cisfe(supabase: SupabaseClient, existing_urls: set, session: requests.Session) -> None:
    """Scraper para CISFE - Cámara Inmobiliaria de Santa Fe (20 inmobiliarias)."""
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0",
        "Accept-Language": "es-AR,es;q=0.9",
    }
    BASE = "https://cisfe.ar"
    # Santa Fe capital = 12712
    BASE_URL = f"{BASE}/results-page/?search_location=12712&offset={{}}"
    total_nuevas = 0
    offset = 0
    empty_pages = 0

    while empty_pages < 2:
        url = f"{BASE}/results-page/?search_location=12712&offset={offset}"
        try:
            resp = session.get(url, headers=HEADERS, timeout=20)
            if resp.status_code != 200:
                empty_pages += 1
                offset += 20
                continue

            soup = BeautifulSoup(resp.text, "html.parser")
            cards = soup.select("div.card")

            if not cards:
                empty_pages += 1
                offset += 20
                continue

            empty_pages = 0
            nuevas = []
            seen = set()

            for card in cards:
                # URL — primer link a /inmueble/
                link = card.select_one("a[href*='/inmueble/']")
                if not link:
                    continue
                prop_url = link.get("href", "")
                if not prop_url.startswith("http"):
                    prop_url = BASE + prop_url
                if prop_url in existing_urls or prop_url in seen:
                    continue
                seen.add(prop_url)

                # Título
                titulo_el = card.select_one("h3, h4, h5, .card-title, [class*='title']")
                titulo = titulo_el.get_text(strip=True) if titulo_el else None

                # Precio
                precio_el = card.select_one("[class*='price'], .price, [class*='valor']")
                precio, moneda = DataCleaner.clean_price(precio_el.get_text(strip=True) if precio_el else None)

                # Operación
                operacion = None
                for el in card.find_all(True):
                    texto = el.get_text(strip=True).lower()
                    if texto in ("venta", "alquiler"):
                        operacion = texto
                        break

                # Tipo
                tipo = DataCleaner.detect_property_type(titulo or "")

                if not titulo:
                    titulo = prop_url.split("/inmueble/")[-1].replace("-", " ").strip("/").title()

                prop = Propiedad(
                    url=prop_url,
                    titulo=titulo,
                    precio=precio,
                    moneda=moneda,
                    tipo_propiedad=tipo,
                    ciudad="Santa Fe",
                    operacion=operacion,
                    fuente="cisfe",
                )
                if prop.titulo and len(prop.titulo) >= 3:
                    nuevas.append(prop)

            logger.info(f"[cisfe] Offset {offset}: {len(cards)} cards | {len(nuevas)} nuevas")

            if nuevas:
                saved = supabase.batch_save_only_new([p.to_payload() for p in nuevas])
                logger.info(f"[cisfe] Guardadas: {saved}")
                existing_urls.update(p.url for p in nuevas)
                total_nuevas += saved

        except Exception as exc:
            logger.error(f"[cisfe] Error offset {offset}: {exc}")
            empty_pages += 1

        offset += 20
        time.sleep(1.5)

    logger.info(f"[cisfe] Total guardadas: {total_nuevas}")


def scrape_raes(supabase: SupabaseClient, existing_urls: set, context) -> None:
    """
    Scraper para Raes Inversiones (raesinversiones.com).
    Red de inmobiliarias que incluye Raes Black, Raes Equilibrio, Raes Potencia, etc.

    El sitio es una SPA de React. Estrategia:
      1. Interceptar llamadas JSON de la API mientras Playwright carga la página.
      2. Si se capturan datos, parsearlos directo (más limpio y completo).
      3. Si no, fallback: parsear el HTML renderizado.
    """
    BASE = "https://www.raesinversiones.com"
    FUENTES_RAES = [
        (f"{BASE}/venta",    "venta",    "raes_venta"),
        (f"{BASE}/alquiler", "alquiler", "raes_alquiler"),
    ]

    def _is_property_list(body: Any) -> bool:
        if not isinstance(body, list) or not body or not isinstance(body[0], dict):
            return False
        claves = {"price", "precio", "address", "direccion", "bedrooms",
                  "dormitorios", "title", "titulo", "property_type", "surface", "area"}
        return bool(claves & set(body[0].keys()))

    def _extract_list_from_dict(body: dict) -> Optional[List]:
        for key in ("results", "data", "propiedades", "properties",
                    "items", "content", "listings", "inmuebles"):
            v = body.get(key)
            if isinstance(v, list) and v and isinstance(v[0], dict):
                return v
        return None

    def _parse_api_item(item: dict, operacion: str, fuente_key: str) -> Optional[Propiedad]:
        url = (item.get("url") or item.get("link") or item.get("permalink")
               or item.get("property_url") or item.get("propertyUrl"))
        if not url:
            slug = str(item.get("slug") or item.get("id_property") or item.get("id") or "")
            url = f"{BASE}/propiedad/{slug}" if slug else None
        if not url:
            return None
        if not url.startswith("http"):
            url = BASE + url

        titulo = (item.get("title") or item.get("titulo") or item.get("name")
                  or item.get("address") or item.get("direccion") or "Sin título")

        precio_raw = (item.get("price") or item.get("precio")
                      or item.get("sale_price") or item.get("rent_price"))
        if isinstance(precio_raw, (int, float)):
            precio = int(precio_raw)
            moneda = "USD" if str(item.get("currency", "")).upper() in ("USD", "U$S") else "ARS"
        else:
            precio, moneda = DataCleaner.clean_price(str(precio_raw) if precio_raw else None)

        op_raw = str(item.get("operacion") or item.get("operation")
                     or item.get("purpose") or operacion).lower()
        if "sale" in op_raw or "venta" in op_raw:
            op = "venta"
        elif "rent" in op_raw or "alquiler" in op_raw:
            op = "alquiler"
        else:
            op = operacion

        tipo_raw = str(item.get("property_type") or item.get("tipo") or item.get("type") or "")
        tipo = DataCleaner.detect_property_type(tipo_raw)
        if tipo == "otro":
            tipo = DataCleaner.detect_property_type(str(titulo))

        direccion = item.get("address") or item.get("direccion") or item.get("street")
        barrio = item.get("neighborhood") or item.get("barrio") or item.get("sector")

        metros = None
        for k in ("area", "metros", "built_area", "surface", "superficie"):
            v = item.get(k)
            if v:
                try:
                    metros = int(float(str(v).replace(",", ".")))
                    break
                except (ValueError, TypeError):
                    pass

        dormitorios = None
        for k in ("bedrooms", "dormitorios", "rooms"):
            v = item.get(k)
            if v:
                try:
                    dormitorios = int(v); break
                except (ValueError, TypeError):
                    pass

        banos = None
        for k in ("bathrooms", "banos", "baños"):
            v = item.get(k)
            if v:
                try:
                    banos = int(v); break
                except (ValueError, TypeError):
                    pass

        imagenes = []
        for k in ("images", "photos", "gallery", "fotos"):
            imgs = item.get(k)
            if isinstance(imgs, list):
                for img in imgs[:10]:
                    if isinstance(img, str) and img.startswith("http"):
                        imagenes.append(img)
                    elif isinstance(img, dict):
                        img_url = img.get("url") or img.get("src")
                        if img_url and str(img_url).startswith("http"):
                            imagenes.append(str(img_url))
                if imagenes:
                    break

        prop = Propiedad(
            url=url, titulo=str(titulo), precio=precio, moneda=moneda,
            direccion=direccion, barrio=barrio,
            barrio_normalizado=DataCleaner.normalize_neighborhood(barrio),
            tipo_propiedad=tipo, ciudad="Santa Fe", operacion=op,
            fuente=fuente_key, metros=metros, dormitorios=dormitorios,
            banos=banos, imagenes=imagenes,
        )
        return prop if prop.titulo and len(prop.titulo) >= 3 else None

    for page_url, operacion, fuente_key in FUENTES_RAES:
        logger.info(f"[{fuente_key}] Iniciando → {page_url}")
        page = context.new_page()
        captured: List[Dict[str, Any]] = []

        def handle_response(response):
            if response.status != 200:
                return
            if "application/json" not in response.headers.get("content-type", ""):
                return
            try:
                body = response.json()
            except Exception:
                return
            if _is_property_list(body):
                logger.debug(f"[{fuente_key}] API list @ {response.url}: {len(body)} items")
                captured.extend(body)
            elif isinstance(body, dict):
                items = _extract_list_from_dict(body)
                if items:
                    logger.debug(f"[{fuente_key}] API dict @ {response.url}: {len(items)} items")
                    captured.extend(items)

        page.on("response", handle_response)

        try:
            ok = _goto_safe(page, page_url, 40_000)
            if not ok:
                logger.warning(f"[{fuente_key}] No se pudo cargar {page_url}")
                continue
            page.wait_for_timeout(3_000)

            prev = 0
            for _ in range(15):
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                page.wait_for_timeout(1_500)
                if len(captured) == prev and _ > 5:
                    break
                prev = len(captured)

            if captured:
                logger.info(f"[{fuente_key}] API: {len(captured)} items capturados")
                nuevas = []
                seen_urls: set = set()
                for item in captured:
                    prop = _parse_api_item(item, operacion, fuente_key)
                    if prop and prop.url not in existing_urls and prop.url not in seen_urls:
                        nuevas.append(prop)
                        seen_urls.add(prop.url)
                logger.info(f"[{fuente_key}] {len(nuevas)} nuevas")
                if nuevas:
                    saved = supabase.batch_save_only_new([p.to_payload() for p in nuevas])
                    logger.info(f"[{fuente_key}] Guardadas: {saved}")
                    existing_urls.update(p.url for p in nuevas)
            else:
                # Fallback HTML
                logger.warning(f"[{fuente_key}] No se detectó API, parseando HTML")
                soup = BeautifulSoup(page.content(), "html.parser")
                cards = (soup.select("[class*='property-card']") or
                         soup.select("[class*='card-property']") or
                         soup.select("[class*='listing-item']") or
                         soup.select("article") or [])
                logger.info(f"[{fuente_key}] HTML fallback: {len(cards)} cards encontradas")
                nuevas = []
                seen_urls: set = set()
                for card in cards:
                    link = card.select_one("a[href]")
                    if not link:
                        continue
                    href = link.get("href", "")
                    url = href if href.startswith("http") else BASE + href
                    if not any(s in url for s in ("/propiedad", "/property", "/inmueble", "/p/")):
                        continue
                    if url in existing_urls or url in seen_urls:
                        continue
                    seen_urls.add(url)
                    textos = [el.get_text(strip=True) for el in card.find_all(True)
                              if el.get_text(strip=True) and not el.find(True)]
                    titulo = next((t for t in textos if len(t) > 8
                                   and "$" not in t and "USD" not in t), None)
                    precio_raw = next((t for t in textos if "$" in t or "USD" in t), None)
                    precio, moneda = DataCleaner.clean_price(precio_raw)
                    tipo = DataCleaner.detect_property_type(titulo or "")
                    if not titulo:
                        titulo = url.split("/")[-1].replace("-", " ").strip("/").title()
                    prop = Propiedad(url=url, titulo=titulo or "Sin título",
                                    precio=precio, moneda=moneda, tipo_propiedad=tipo,
                                    ciudad="Santa Fe", operacion=operacion, fuente=fuente_key)
                    if prop.titulo and len(prop.titulo) >= 3:
                        nuevas.append(prop)
                logger.info(f"[{fuente_key}] HTML: {len(nuevas)} nuevas")
                if nuevas:
                    saved = supabase.batch_save_only_new([p.to_payload() for p in nuevas])
                    logger.info(f"[{fuente_key}] Guardadas: {saved}")
                    existing_urls.update(p.url for p in nuevas)

        except Exception as exc:
            logger.error(f"[{fuente_key}] Error: {exc}", exc_info=True)
        finally:
            page.close()

        time.sleep(2)


def scrape_cam(supabase: SupabaseClient, existing_urls: set, session: requests.Session) -> None:
    """
    Scraper para CAM Construcciones (camconstrucciones.com.ar).
    Desarrolladora con +125 edificios en Santa Fe. Scrapeamos solo los
    edificios en construcción (en pozo / fideicomiso) → operacion='proyecto'.
    No hay precios publicados (se consulta por WhatsApp/mail).
    """
    BASE = "https://www.camconstrucciones.com.ar"
    LISTING_URL = f"{BASE}/edificios-ejecucion/"
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0",
        "Accept-Language": "es-AR,es;q=0.9",
    }

    logger.info("[cam] Iniciando")

    try:
        resp = session.get(LISTING_URL, headers=HEADERS, timeout=20)
        if resp.status_code != 200:
            logger.error(f"[cam] Error cargando listing: {resp.status_code}")
            return
        soup = BeautifulSoup(resp.text, "html.parser")
    except Exception as exc:
        logger.error(f"[cam] Error: {exc}")
        return

    # Links a páginas de portfolio (edificios individuales)
    links = []
    seen = set()
    for a in soup.select("a[href*='/portfolio/']"):
        href = a.get("href", "")
        if not href.startswith("http"):
            href = BASE + href
        if href not in seen and "/portfolio/" in href:
            # Excluir links de nav u otros que no sean edificios reales
            text = a.get_text(strip=True)
            seen.add(href)
            links.append((href, text))

    logger.info(f"[cam] {len(links)} edificios encontrados")

    nuevas = []
    for prop_url, nombre_link in links:
        if prop_url in existing_urls:
            continue

        try:
            r = session.get(prop_url, headers=HEADERS, timeout=15)
            if r.status_code != 200:
                continue
            det = BeautifulSoup(r.text, "html.parser")

            # Título: H2 o <title> de la página
            titulo_el = det.select_one("h2.et_pb_module_header, .portfolio-title, h1, h2")
            titulo = titulo_el.get_text(strip=True) if titulo_el else None
            if not titulo:
                titulo_tag = det.find("title")
                if titulo_tag:
                    titulo = titulo_tag.get_text(strip=True).split("–")[0].strip()
            if not titulo:
                titulo = nombre_link or prop_url.split("/portfolio/")[-1].replace("-", " ").strip("/").title()

            # Descripción: texto del body del portfolio
            desc_el = det.select_one(".et_pb_post_content, .entry-content, .portfolio-description, article")
            descripcion = desc_el.get_text(" ", strip=True)[:1500] if desc_el else ""

            # Dirección: buscar en el texto patrones de calle + número
            dir_match = re.search(
                r'(Bv\.?|Av\.?|Blvd\.?|Calle|Entre\s+R[ií]os|Rivadavia|San\s+Martín|Francia|Urquiza|Pellegrini|Freyre|Alem|Laprida|[A-Z][a-záéíóú]+)\s+\d{3,5}',
                descripcion
            )
            direccion = dir_match.group(0).strip() if dir_match else None

            # Imágenes: todas las img src que sean uploads de WP y no íconos
            imagenes = []
            for img in det.select("img[src*='/wp-content/uploads/']"):
                src = img.get("src", "")
                if src and src.startswith("http") and "-367x367" not in src and "logo" not in src.lower():
                    imagenes.append(src)
            imagenes = list(dict.fromkeys(imagenes))[:8]  # dedup, max 8

            prop = Propiedad(
                url=prop_url,
                titulo=titulo,
                precio=None,
                moneda=None,
                direccion=direccion,
                barrio=None,
                tipo_propiedad="departamento",
                descripcion=descripcion,
                ciudad="Santa Fe",
                operacion="proyecto",
                fuente="cam",
                imagenes=imagenes,
            )
            if prop.titulo and len(prop.titulo) >= 3:
                nuevas.append(prop)

        except Exception as exc:
            logger.debug(f"[cam] Error detalle {prop_url}: {exc}")

        time.sleep(0.8)

    logger.info(f"[cam] {len(nuevas)} nuevas propiedades")
    if nuevas:
        saved = supabase.batch_save_only_new([p.to_payload() for p in nuevas])
        logger.info(f"[cam] Guardadas: {saved}")
        existing_urls.update(p.url for p in nuevas)


def scrape_sofia(supabase: SupabaseClient, existing_urls: set, session: requests.Session) -> None:
    """
    Scraper para Sofía Desarrollos (sofiadesarrollos.com.ar).
    Desarrolladora con 10 proyectos en Santa Fe (Sofia I al X).
    Scrapeamos todos los que tienen página propia → operacion='proyecto'.
    """
    BASE = "https://sofiadesarrollos.com.ar"
    PROYECTOS_URL = f"{BASE}/proyectos/"
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0",
        "Accept-Language": "es-AR,es;q=0.9",
    }

    logger.info("[sofia] Iniciando")

    try:
        resp = session.get(PROYECTOS_URL, headers=HEADERS, timeout=20)
        if resp.status_code != 200:
            logger.error(f"[sofia] Error cargando listing: {resp.status_code}")
            return
        soup = BeautifulSoup(resp.text, "html.parser")
    except Exception as exc:
        logger.error(f"[sofia] Error: {exc}")
        return

    # Recolectar links a proyectos individuales
    links = []
    seen = set()
    for a in soup.select("a[href]"):
        href = a.get("href", "")
        # Links de proyectos: /sofia-i/, /sofia-ii/, etc. o dominios propios
        if not href.startswith("http"):
            href = BASE + href
        if href in seen:
            continue
        if any(pat in href for pat in [
            "/sofia-i/", "/sofia-ii/", "/sofia-iii/", "/sofia-iv/", "/sofia-v/",
            "/sofia-vi/", "/sofia-vii/", "/sofia-viii/", "/sofia-ix/", "/sofia-x/",
            "sofia-ii.com.ar", "sofia-x.com.ar",
        ]):
            # Excluir la propia página de proyectos u otros falsos positivos
            if href not in (PROYECTOS_URL, BASE + "/", BASE):
                seen.add(href)
                links.append(href)

    logger.info(f"[sofia] {len(links)} proyectos encontrados: {[l for l in links]}")

    nuevas = []
    for prop_url in links:
        if prop_url in existing_urls:
            continue

        try:
            r = session.get(prop_url, headers=HEADERS, timeout=15)
            if r.status_code != 200:
                continue
            det = BeautifulSoup(r.text, "html.parser")

            # Título
            titulo_el = det.select_one("h1, h2")
            titulo = titulo_el.get_text(strip=True) if titulo_el else None
            if not titulo:
                titulo_tag = det.find("title")
                if titulo_tag:
                    titulo = titulo_tag.get_text(strip=True).split("-")[0].strip()
            if not titulo:
                titulo = prop_url.rstrip("/").split("/")[-1].replace("-", " ").upper()

            # Descripción
            desc_el = det.select_one(".elementor-widget-container, .entry-content, article, main")
            descripcion = desc_el.get_text(" ", strip=True)[:1500] if desc_el else ""

            # Dirección: buscar en el título o descripción
            dir_match = re.search(
                r'(Bv\.?|Av\.?|Blvd\.?|Rivadavia|Suipacha|Hipólito|Freyre|Gálvez|San\s+Martín|Urquiza|Entre\s+Ríos|[A-Z][a-záéíóú]+)\s+\d{3,5}',
                titulo + " " + descripcion[:500]
            )
            direccion = dir_match.group(0).strip() if dir_match else None

            # Imágenes
            imagenes = []
            for img in det.select("img[src*='/wp-content/uploads/'], img[src*='sofia']"):
                src = img.get("src", "")
                if (src and src.startswith("http")
                        and "logo" not in src.lower()
                        and "icono" not in src.lower()
                        and "stricker" not in src.lower()
                        and "thumb" not in src.lower()):
                    imagenes.append(src)
            imagenes = list(dict.fromkeys(imagenes))[:8]

            prop = Propiedad(
                url=prop_url,
                titulo=titulo,
                precio=None,
                moneda=None,
                direccion=direccion,
                barrio=None,
                tipo_propiedad="departamento",
                descripcion=descripcion,
                ciudad="Santa Fe",
                operacion="proyecto",
                fuente="sofia",
                imagenes=imagenes,
            )
            if prop.titulo and len(prop.titulo) >= 3:
                nuevas.append(prop)

        except Exception as exc:
            logger.debug(f"[sofia] Error detalle {prop_url}: {exc}")

        time.sleep(0.8)

    logger.info(f"[sofia] {len(nuevas)} nuevas propiedades")
    if nuevas:
        saved = supabase.batch_save_only_new([p.to_payload() for p in nuevas])
        logger.info(f"[sofia] Guardadas: {saved}")
        existing_urls.update(p.url for p in nuevas)


def scrape_casablanca(supabase: SupabaseClient, existing_urls: set, session: requests.Session) -> None:
    """
    Scraper para Casablanca SRL (casablancasrl.com.ar).
    HTML estático, una página por categoría, sin paginación.
    """
    BASE = "https://www.casablancasrl.com.ar"
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0",
        "Accept-Language": "es-AR,es;q=0.9",
    }

    CATEGORIAS = [
        ("/inmuebles/casas-para-venta",           "venta",    "casa"),
        ("/inmuebles/departamentos-para-venta",    "venta",    "departamento"),
        ("/inmuebles/casasquintas-para-venta",     "venta",    "casa"),
        ("/inmuebles/oficinas-para-venta",         "venta",    "oficina"),
        ("/inmuebles/salones-para-venta",          "venta",    "local"),
        ("/inmuebles/galpones-para-venta",         "venta",    "otro"),
        ("/inmuebles/terrenos-para-venta",         "venta",    "terreno"),
        ("/inmuebles/casas-para-alquiler",         "alquiler", "casa"),
        ("/inmuebles/departamentos-para-alquiler", "alquiler", "departamento"),
        ("/inmuebles/casasquintas-para-alquiler",  "alquiler", "casa"),
        ("/inmuebles/oficinas-para-alquiler",      "alquiler", "oficina"),
        ("/inmuebles/salones-para-alquiler",       "alquiler", "local"),
        ("/inmuebles/galpones-para-alquiler",      "alquiler", "otro"),
        ("/inmuebles/terrenos-para-alquiler",      "alquiler", "terreno"),
    ]

    logger.info("[casablanca] Iniciando")
    total_nuevas = 0

    for path, operacion, tipo_default in CATEGORIAS:
        url = BASE + path
        try:
            resp = session.get(url, headers=HEADERS, timeout=15)
            if resp.status_code != 200:
                continue
            soup = BeautifulSoup(resp.text, "html.parser")

            # Cada propiedad es un <a href="/inmuebles/venta/ref-XXXXX"> o alquiler
            cards = soup.select("a[href*='/ref-']")
            nuevas = []

            for card in cards:
                href = card.get("href", "")
                prop_url = href if href.startswith("http") else BASE + href
                if prop_url in existing_urls:
                    continue

                # Título: h4 dentro del card
                titulo_el = card.select_one("h4")
                titulo = titulo_el.get_text(strip=True) if titulo_el else None

                # Precio: texto completo del link, buscar patrón "Venta | $XX" o "U$SXX"
                texto_completo = card.get_text(" ", strip=True)
                precio, moneda = DataCleaner.clean_price(texto_completo)

                # Descripción corta
                desc_el = card.select_one("p")
                descripcion = desc_el.get_text(strip=True) if desc_el else ""

                # Tipo de propiedad
                tipo = DataCleaner.detect_property_type(titulo or descripcion) if titulo else tipo_default
                if tipo == "otro":
                    tipo = tipo_default

                if not titulo:
                    titulo = prop_url.split("/ref-")[-1].strip("/")

                prop = Propiedad(
                    url=prop_url,
                    titulo=titulo,
                    precio=precio,
                    moneda=moneda,
                    tipo_propiedad=tipo,
                    descripcion=descripcion,
                    ciudad="Santa Fe",
                    operacion=operacion,
                    fuente="casablanca",
                    direccion=titulo,  # el título es la dirección en Casablanca
                )
                if prop.titulo and len(prop.titulo) >= 3:
                    nuevas.append(prop)

            logger.info(f"[casablanca] {path}: {len(nuevas)} nuevas")
            if nuevas:
                saved = supabase.batch_save_only_new([p.to_payload() for p in nuevas])
                total_nuevas += saved
                existing_urls.update(p.url for p in nuevas)

        except Exception as exc:
            logger.error(f"[casablanca] Error en {path}: {exc}")

        time.sleep(0.8)

    logger.info(f"[casablanca] Total guardadas: {total_nuevas}")


def _scrape_desarrolladora(
    supabase: SupabaseClient,
    existing_urls: set,
    session: requests.Session,
    fuente_key: str,
    proyecto_urls: list,
    base_url: str,
) -> None:
    """
    Helper genérico para desarrolladoras WordPress con páginas de proyecto individuales.
    Mismo patrón que CAM y Sofía.
    """
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0",
        "Accept-Language": "es-AR,es;q=0.9",
    }
    logger.info(f"[{fuente_key}] Iniciando — {len(proyecto_urls)} proyectos")

    # Consultar la DB directamente por fuente para evitar falsos positivos
    urls_en_db = set(supabase.get_active_urls_by_fuente(fuente_key))
    urls_a_omitir = existing_urls | urls_en_db

    nuevas = []
    for prop_url in proyecto_urls:
        if prop_url in urls_a_omitir:
            logger.debug(f"[{fuente_key}] Ya existe: {prop_url}")
            continue
        try:
            r = session.get(prop_url, headers=HEADERS, timeout=15)
            if r.status_code != 200:
                logger.warning(f"[{fuente_key}] {r.status_code} → {prop_url}")
                continue

            soup = BeautifulSoup(r.text, "html.parser")

            # Título
            titulo_el = soup.select_one("h1, h2.et_pb_module_header, h2")
            titulo = titulo_el.get_text(strip=True) if titulo_el else None
            if not titulo:
                titulo_tag = soup.find("title")
                titulo = titulo_tag.get_text(strip=True).split("–")[0].split("|")[0].strip() if titulo_tag else None
            if not titulo:
                titulo = prop_url.rstrip("/").split("/")[-1].replace("-", " ").title()

            # Descripción
            desc_el = soup.select_one(".et_pb_post_content, .entry-content, .elementor-widget-container, article, main")
            descripcion = desc_el.get_text(" ", strip=True)[:1500] if desc_el else ""

            # Dirección
            dir_match = re.search(
                r'(Bv\.?|Av\.?|Blvd\.?|Irigoyen|Freyre|Rivadavia|San\s+Martín|Suipacha|Urquiza|Entre\s+Ríos|Zaspe|Laprida|Gálvez|Pellegrini|Sarmiento|[A-ZÁÉÍÓÚ][a-záéíóúñ]+(?:\s+[A-ZÁÉÍÓÚ][a-záéíóúñ]+)?)\s+\d{3,5}',
                titulo + " " + descripcion[:600]
            )
            direccion = dir_match.group(0).strip() if dir_match else None

            # Imágenes
            imagenes = []
            for img in soup.select("img[src*='/wp-content/uploads/'], img[src*='.webp'], img[src*='.jpg']"):
                src = img.get("src", "")
                if (src and src.startswith("http")
                        and not any(x in src.lower() for x in ["logo", "icon", "favicon", "avatar", "thumb", "flag"])):
                    imagenes.append(src)
            imagenes = list(dict.fromkeys(imagenes))[:8]

            prop = Propiedad(
                url=prop_url,
                titulo=titulo,
                precio=None,
                moneda=None,
                direccion=direccion,
                tipo_propiedad="departamento",
                descripcion=descripcion,
                ciudad="Santa Fe",
                operacion="proyecto",
                fuente=fuente_key,
                imagenes=imagenes,
            )
            if prop.titulo and len(prop.titulo) >= 3:
                nuevas.append(prop)

        except Exception as exc:
            logger.debug(f"[{fuente_key}] Error en {prop_url}: {exc}")

        time.sleep(0.8)

    logger.info(f"[{fuente_key}] {len(nuevas)} nuevas")
    if nuevas:
        saved = supabase.batch_save_only_new([p.to_payload() for p in nuevas])
        logger.info(f"[{fuente_key}] Guardadas: {saved}")
        existing_urls.update(p.url for p in nuevas)


def scrape_proa(supabase: SupabaseClient, existing_urls: set, session: requests.Session) -> None:
    """PROA Desarrollos (proadesarrollos.com.ar) — 3 proyectos activos en Santa Fe."""
    _scrape_desarrolladora(supabase, existing_urls, session, "proa", [
        "https://proadesarrollos.com.ar/amura-desarrollos/",
        "https://proadesarrollos.com.ar/proa-2-desarrollos/",
        "https://proadesarrollos.com.ar/proa-3-desarrollos/",
    ], "https://proadesarrollos.com.ar")


def scrape_sur(supabase: SupabaseClient, existing_urls: set, session: requests.Session) -> None:
    """Sur S.A. (sur-sa.com.ar) — proyectos nuevos y en ejecución en Santa Fe."""
    BASE = "https://sur-sa.com.ar"
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0",
        "Accept-Language": "es-AR,es;q=0.9",
    }
    logger.info("[sur] Buscando proyectos activos")

    urls_proyectos = []
    for listing in ["/estado-proyecto/nuevo/", "/estado-proyecto/en-ejecucion/"]:
        try:
            r = session.get(BASE + listing, headers=HEADERS, timeout=15)
            if r.status_code != 200:
                continue
            soup = BeautifulSoup(r.text, "html.parser")
            for a in soup.select("a[href*='/portfolio/'], a[href*='/proyecto/'], a[href*='/emprendimiento/']"):
                href = a.get("href", "")
                if not href.startswith("http"):
                    href = BASE + href
                if href not in urls_proyectos and "sur-sa.com.ar" in href:
                    urls_proyectos.append(href)
        except Exception as exc:
            logger.debug(f"[sur] Error en listing {listing}: {exc}")
        time.sleep(1)

    if not urls_proyectos:
        # Fallback: proyectos conocidos
        urls_proyectos = [
            "https://sur-sa.com.ar/portfolio-proyectos/",
        ]
    logger.info(f"[sur] {len(urls_proyectos)} proyectos encontrados")
    _scrape_desarrolladora(supabase, existing_urls, session, "sur", urls_proyectos, BASE)


def scrape_neo(supabase: SupabaseClient, existing_urls: set, session: requests.Session) -> None:
    """NEO Inversiones (neo-inversiones.com) — proyectos en pozo en Santa Fe.
    Sitio HTML estático con URLs fijas por proyecto.
    """
    _scrape_desarrolladora(supabase, existing_urls, session, "neo", [
        "http://neo-inversiones.com/neo_20.html",
        "http://neo-inversiones.com/neo_19.html",
        "http://neo-inversiones.com/neo_18.html",
        "http://neo-inversiones.com/neo_17.html",
        "http://neo-inversiones.com/neo_16.html",
    ], "http://neo-inversiones.com")


def scrape_bygger(supabase: SupabaseClient, existing_urls: set, session: requests.Session) -> None:
    """Bygger (bygger.com.ar) — 4 proyectos activos en Santa Fe."""
    _scrape_desarrolladora(supabase, existing_urls, session, "bygger", [
        "https://bygger.com.ar/bygger-blues/",
        "https://bygger.com.ar/bygger-pop/",
        "https://bygger.com.ar/bygger-soul/",
        "https://bygger.com.ar/bygger-progreso/",
    ], "https://bygger.com.ar")


def scrape_gen(supabase: SupabaseClient, existing_urls: set, session: requests.Session) -> None:
    """GEN Desarrollos (gendesarrollos.com) — proyectos con propiedades en venta directa."""
    BASE = "https://gendesarrollos.com"
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0",
        "Accept-Language": "es-AR,es;q=0.9",
    }
    logger.info("[gen] Buscando proyectos")

    urls_proyectos = []
    for listing in ["/", "/propiedades-en-venta/"]:
        try:
            r = session.get(BASE + listing, headers=HEADERS, timeout=15)
            if r.status_code != 200:
                continue
            soup = BeautifulSoup(r.text, "html.parser")
            for a in soup.select("a[href*='/obra/'], a[href*='/propiedad/'], a[href*='/proyecto/']"):
                href = a.get("href", "")
                if not href.startswith("http"):
                    href = BASE + href
                if href not in urls_proyectos and "gendesarrollos.com" in href:
                    urls_proyectos.append(href)
        except Exception as exc:
            logger.debug(f"[gen] Error en listing {listing}: {exc}")
        time.sleep(0.8)

    logger.info(f"[gen] {len(urls_proyectos)} proyectos encontrados")
    _scrape_desarrolladora(supabase, existing_urls, session, "gen", urls_proyectos, BASE)


def scrape_nuevas(supabase: SupabaseClient, existing_urls: set, context) -> None:
    """
    Scrapea todas las inmobiliarias de FUENTES_NUEVAS con Playwright.
    Usa scroll + parse_cards para Tokko Broker (con fallback de links directos).
    Para sitios con url_segment custom, usa _guardar_urls_desde_pagina.
    """
    # Sitios que sabemos que fallan consistentemente — evitar perder tiempo
    # Para agregar un sitio de vuelta: verificar URL correcta y removerlo de aquí
    SKIP_KEYS = {
        "liotto_venta", "liotto_alquiler",          # timeout: sitio caído/bloqueado
        "palau_venta", "palau_alquiler",            # extremadamente lento, 0 resultados
        "amadeo_venta", "amadeo_alquiler",          # 0 resultados en todas las variantes
        "invernizzi_venta", "invernizzi_alquiler",  # 0 resultados en todas las variantes
        "gibelli_venta", "gibelli_alquiler",        # 0 resultados en todas las variantes
        "arnaus_venta", "arnaus_alquiler",          # 0 resultados en todas las variantes
        "castro_reisse_venta", "castro_reisse_alquiler",  # 0 resultados
        "levy_amon_venta", "levy_amon_alquiler",    # 0 resultados
        "ressia_venta", "ressia_alquiler",          # 0 resultados
        "arenas_venta", "arenas_alquiler",          # 0 resultados
        "damonte_venta", "damonte_alquiler",        # 0 resultados
        "compreprop_venta", "compreprop_alquiler",  # 0 resultados
        "giobellina_venta", "giobellina_alquiler",  # 0 resultados
        "massera_venta", "massera_alquiler",        # 0 resultados
        "loiacono_venta", "loiacono_alquiler",      # 0 resultados
        "rucci_venta", "rucci_alquiler",            # lento y bloqueado
        "doopla_venta", "doopla_alquiler",          # CMS diferente
        "foieri_navarro_venta", "foieri_navarro_alquiler",  # 0 resultados
        "baccello_venta", "baccello_alquiler",      # 0 resultados
        "liotta_venta", "liotta_alquiler",          # 0 resultados (Tokko pero sin propiedades activas)
        "iprop_alquiler",                           # solo tiene venta
        "loquet_alquiler",                          # solo tiene venta
        "libertador_alquiler",                      # solo tiene venta
        # Repetto/Vaccaro: RESUELTO — parse_cards ahora hace fallback correcto
        # cuando li[data-id] del sidebar era confundido como card container

    }

    logger.info(f"[nuevas] Iniciando — {len(FUENTES_NUEVAS)} fuentes")
    total_guardadas = 0

    for fuente in FUENTES_NUEVAS:
        key = fuente["key"]
        if key in SKIP_KEYS:
            logger.debug(f"[{key}] Saltando (sitio problemático conocido)")
            continue

        url = fuente["url"]
        operacion = fuente["operacion"]
        ciudad = fuente.get("ciudad", "Argentina")
        url_segment = fuente.get("url_segment")
        base_url = "/".join(url.split("/")[:3])

        page = context.new_page()
        try:
            logger.info(f"[{key}] {url}")

            try:
                page.goto(url, timeout=45000, wait_until="domcontentloaded")
            except Exception as exc:
                if any(e in str(exc) for e in ["ERR_CERT", "SSL", "Timeout", "ERR_NAME"]):
                    logger.warning(f"[{key}] Error de conexión — saltando: {type(exc).__name__}")
                    page.close()
                    continue
                raise

            page.wait_for_timeout(3000)

            # Sitios con URL de propiedad no-Tokko (PHP clásico)
            if url_segment:
                saved = _guardar_urls_desde_pagina(
                    page, supabase, existing_urls, key, ciudad,
                    segmentos_prop=[url_segment],
                    operacion_default=operacion,
                )
                total_guardadas += saved
                page.close()
                continue

            # Flujo normal Tokko Broker
            total = scroll_to_bottom(page)
            logger.info(f"[{key}] {total} propiedades en página")

            # Esperar renderizado de precios JS (hasta 3s extra)
            try:
                page.wait_for_selector(
                    "[class*='price'], [class*='precio'], .aviso-precio, .property-price",
                    timeout=3000, state="attached"
                )
            except Exception:
                pass  # Sin precios JS — continuar igual

            if total == 0:
                # Probar variantes de URL comunes en Tokko
                url_variants = []
                if "/Venta" in url:
                    url_variants = [
                        url.replace("/Venta", "/venta/"),
                        url.replace("/Venta", "/propiedades/venta"),
                        url.replace("/Venta", "/propiedades"),
                    ]
                elif "/Alquiler" in url:
                    url_variants = [
                        url.replace("/Alquiler", "/alquiler/"),
                        url.replace("/Alquiler", "/propiedades/alquiler"),
                        url.replace("/Alquiler", "/propiedades"),
                    ]

                for url_alt in url_variants:
                    try:
                        page.goto(url_alt, timeout=25000, wait_until="domcontentloaded")
                        page.wait_for_timeout(2000)
                        total = scroll_to_bottom(page)
                        if total > 0:
                            logger.info(f"[{key}] URL alternativa ({url_alt}): {total} propiedades")
                            break
                    except Exception:
                        continue

            if total == 0:
                logger.warning(f"[{key}] Sin propiedades. Verificar URL o CMS.")
                page.close()
                continue

            propiedades = parse_cards(page.content(), operacion, key, base_url, ciudad)

            if not propiedades and total > 0:
                logger.warning(f"[{key}] {total} links encontrados pero 0 propiedades válidas después del parse. "
                               f"El fallback interno de parse_cards también falló. Sitio requiere selector específico.")
                page.close()
                continue

            nuevas = [p for p in propiedades if p.url not in existing_urls]
            logger.info(f"[{key}] {len(nuevas)} nuevas de {len(propiedades)}")

            if nuevas:
                saved = supabase.batch_save_only_new([p.to_payload() for p in nuevas])
                logger.info(f"[{key}] Guardadas: {saved}")
                existing_urls.update(p.url for p in nuevas)
                total_guardadas += saved

        except Exception as exc:
            logger.error(f"[{key}] Error inesperado: {exc}")
        finally:
            try:
                page.close()
            except Exception:
                pass

    logger.info(f"[nuevas] Total guardadas: {total_guardadas}")


# ─── Scrapers para inmobiliarias NO-Tokko ─────────────────────────────────────

def _guardar_urls_desde_pagina(
    page,
    supabase: SupabaseClient,
    existing_urls: set,
    key: str,
    ciudad: str,
    segmentos_prop: list = None,
    operacion_default: str = None,
) -> int:
    """
    Helper: extrae todos los links de propiedades de la página actual.
    Usa parse_cards primero (rápido, batch). Si falla, visita propiedad por propiedad.
    operacion_default: si se pasa, override la detección automática.
    """
    if segmentos_prop is None:
        segmentos_prop = ["/p/", "/propiedad/", "/inmueble/", "/inmuebles/",
                          "/property/", "/Ficha/", "/ficha/", "/ficha-",
                          "ref-"]

    dominio = page.url.split("/")[2] if "/" in page.url else ""
    base_url = "/".join(page.url.split("/")[:3])

    # ── Estrategia 1: usar parse_cards sobre el HTML actual (rápido) ──────────
    html = page.content()
    # Inferir operacion: primero del operacion_default (más confiable), luego del key, luego URL
    if operacion_default:
        operacion = operacion_default
    elif "_alquiler" in key.lower() or "alquiler" in key.lower():
        operacion = "alquiler"
    elif "_venta" in key.lower() or "venta" in key.lower() or "ventas" in key.lower():
        operacion = "venta"
    elif "alquiler" in page.url.lower():
        operacion = "alquiler"
    elif "venta" in page.url.lower() or "ventas" in page.url.lower():
        operacion = "venta"
    else:
        operacion = "venta"  # default

    propiedades = parse_cards(html, operacion, key, base_url, ciudad)
    nuevas = [p for p in propiedades if p.url not in existing_urls]

    if nuevas:
        logger.info(f"[{key}] {len(nuevas)} propiedades válidas (batch)")
        saved = supabase.batch_save_only_new([p.to_payload() for p in nuevas])
        logger.info(f"[{key}] Guardadas: {saved}")
        existing_urls.update(p.url for p in nuevas)
        return saved

    # ── Estrategia 2: fallback por visita individual (lento, solo si batch falla) ──
    try:
        hrefs = page.eval_on_selector_all("a[href]", "els => els.map(el => el.href)")
    except Exception:
        return 0

    urls_prop = set()
    for href in hrefs:
        if dominio and dominio not in href:
            continue
        if any(seg in href for seg in segmentos_prop):
            urls_prop.add(href.split("?")[0])

    urls_nuevas = [u for u in urls_prop if u not in existing_urls]
    if not urls_nuevas:
        return 0

    logger.info(f"[{key}] Fallback individual: {len(urls_nuevas)} URLs a visitar")
    nuevas_props = []

    for prop_url in urls_nuevas[:50]:  # limitar a 50 para no tardar infinito
        try:
            page.goto(prop_url, timeout=15000, wait_until="domcontentloaded")
            page.wait_for_timeout(500)
            soup = BeautifulSoup(page.content(), "html.parser")

            titulo = ""
            for sel in ["h1", "h2", ".property-title", ".aviso-title"]:
                el = soup.select_one(sel)
                if el and el.get_text(strip=True):
                    titulo = el.get_text(strip=True)[:150]
                    break

            precio_raw = ""
            for sel in ["[class*='price']", "[class*='precio']", ".aviso-price"]:
                el = soup.select_one(sel)
                if el:
                    precio_raw = el.get_text(strip=True)
                    break
            precio, moneda = DataCleaner.clean_price(precio_raw)

            direccion = ""
            for sel in ["[class*='address']", "[class*='direccion']", "address"]:
                el = soup.select_one(sel)
                if el:
                    direccion = el.get_text(strip=True)[:100]
                    break

            operacion_prop = "venta" if "venta" in prop_url.lower() else (
                "alquiler" if "alquiler" in prop_url.lower() else operacion  # fallback al operacion del config
            )
            tipo = DataCleaner.detect_property_type(titulo)
            barrio = DataCleaner.extract_neighborhood(direccion or titulo) or ciudad

            prop = Propiedad(
                url=prop_url,
                titulo=titulo or prop_url.rstrip("/").split("/")[-1].replace("-", " ").title() or "Sin título",
                precio=precio,
                moneda=moneda,
                barrio=barrio,
                barrio_normalizado=DataCleaner.normalize_neighborhood(barrio),
                tipo_propiedad=tipo,
                direccion=direccion or None,
                ciudad=ciudad,
                operacion=operacion_prop,
                fuente=key,
            )
            if prop.url and prop.url.startswith("http") and prop.titulo and len(prop.titulo.strip()) >= 3:
                nuevas_props.append(prop)
        except Exception as exc:
            logger.debug(f"[{key}] Error en {prop_url}: {exc}")
        time.sleep(0.3)

    logger.info(f"[{key}] {len(nuevas_props)} propiedades válidas")
    if nuevas_props:
        saved = supabase.batch_save_only_new([p.to_payload() for p in nuevas_props])
        logger.info(f"[{key}] Guardadas: {saved}")
        existing_urls.update(p.url for p in nuevas_props)
        return saved
    return 0


def _scrape_no_tokko(supabase: SupabaseClient, existing_urls: set, context,
                     key: str, urls_listado: list, ciudad: str,
                     segmentos_prop: list = None) -> None:
    """
    Scraper genérico para sitios con CMS propio (no Tokko).
    Scrape cada operación (venta/alquiler) usando la primera URL que funcione.
    Las URLs sin operación identificable se prueban todas.
    """
    def _get_op(url: str):
        u = url.lower()
        if "alquiler" in u:
            return "alquiler"
        if "venta" in u or "ventas" in u:
            return "venta"
        return None

    # Agrupar URLs por operación para intentar cada una exactamente una vez
    ops_done: Set[str] = set()
    any_found = False

    page = context.new_page()
    try:
        for url in urls_listado:
            op = _get_op(url)
            # Si esta operación ya fue scrapeada exitosamente, saltar URL de fallback
            if op and op in ops_done:
                continue
            try:
                page.goto(url, timeout=25000, wait_until="domcontentloaded")
                page.wait_for_timeout(3000)
                scroll_to_bottom(page)
                saved = _guardar_urls_desde_pagina(
                    page, supabase, existing_urls, key, ciudad,
                    segmentos_prop, operacion_default=op
                )
                if saved > 0 or len(page.query_selector_all("a[href]")) > 10:
                    any_found = True
                    if op:
                        ops_done.add(op)  # marcar esta operación como lista; no reintentar fallbacks
            except Exception as exc:
                logger.debug(f"[{key}] Error en {url}: {exc}")

        if not any_found:
            logger.warning(f"[{key}] Sin propiedades en ninguna URL probada.")
    finally:
        page.close()


def scrape_tizado(supabase: SupabaseClient, existing_urls: set, context) -> None:
    """
    tizado.com — Inmobiliaria grande Buenos Aires / GBA / Nordelta.
    CMS propio: listado en /busqueda/-/venta/ y fichas en /Ficha/SLUG-ID.
    """
    URLS_LISTADO = [
        "https://www.tizado.com/busqueda/-/venta/",
        "https://www.tizado.com/busqueda/-/alquiler/",
    ]
    operacion_map = {"venta": "venta", "alquiler": "alquiler"}

    page = context.new_page()
    total_guardadas = 0
    try:
        for url in URLS_LISTADO:
            operacion = "venta" if "venta" in url else "alquiler"
            base_url = "https://www.tizado.com"

            if not _goto_safe(page, url, timeout=40000):
                continue
            page.wait_for_timeout(4000)
            scroll_to_bottom(page)

            html = page.content()
            propiedades = parse_cards(html, operacion, "tizado", base_url, "Buenos Aires")
            nuevas = [p for p in propiedades if p.url not in existing_urls]
            logger.info(f"[tizado_{operacion}] {len(nuevas)} nuevas de {len(propiedades)}")
            if nuevas:
                saved = supabase.batch_save_only_new([p.to_payload() for p in nuevas])
                logger.info(f"[tizado_{operacion}] Guardadas: {saved}")
                existing_urls.update(p.url for p in nuevas)
                total_guardadas += saved
    except Exception as exc:
        logger.error(f"[tizado] Error: {exc}")
    finally:
        page.close()
    logger.info(f"[tizado] Total: {total_guardadas}")


def scrape_civeira(supabase: SupabaseClient, existing_urls: set, context) -> None:
    """civeirabienesraices.com.ar — Lanús."""
    _scrape_no_tokko(supabase, existing_urls, context, "civeira",
                     ["https://www.civeirabienesraices.com.ar/inmuebles/venta",
                      "https://www.civeirabienesraices.com.ar/propiedades/venta",
                      "https://www.civeirabienesraices.com.ar/Venta",
                      "https://www.civeirabienesraices.com.ar/inmuebles/alquiler",
                      "https://www.civeirabienesraices.com.ar/propiedades/alquiler",
                      "https://www.civeirabienesraices.com.ar/Alquiler",
                      "https://www.civeirabienesraices.com.ar/inmuebles/",
                      "https://www.civeirabienesraices.com.ar/"],
                     "Lanús",
                     segmentos_prop=["/inmuebles/", "/propiedades/", "/propiedad/", "/p/"])


def scrape_zanola(supabase: SupabaseClient, existing_urls: set, context) -> None:
    """zanola.com.ar — Morón, Buenos Aires."""
    _scrape_no_tokko(supabase, existing_urls, context, "zanola",
                     ["https://www.zanola.com.ar/venta-moron",
                      "https://www.zanola.com.ar/alquiler-moron",
                      "https://www.zanola.com.ar/Venta",
                      "https://www.zanola.com.ar/Alquiler"],
                     "Morón")


def scrape_krak(supabase: SupabaseClient, existing_urls: set, context) -> None:
    """krak.com.ar — Buenos Aires."""
    _scrape_no_tokko(supabase, existing_urls, context, "krak",
                     ["https://www.krak.com.ar/Venta",
                      "https://www.krak.com.ar/Alquiler",
                      "https://www.krak.com.ar/propiedades",
                      "https://www.krak.com.ar/ventas"],
                     "Buenos Aires")


def scrape_barbini(supabase: SupabaseClient, existing_urls: set, context) -> None:
    """barbinipropiedades.com.ar — Tandil."""
    _scrape_no_tokko(supabase, existing_urls, context, "barbini",
                     ["https://www.barbinipropiedades.com.ar/propiedades.php",
                      "https://www.barbinipropiedades.com.ar/Venta",
                      "https://www.barbinipropiedades.com.ar/Alquiler"],
                     "Tandil")


def scrape_palma_mdp(supabase: SupabaseClient, existing_urls: set, context) -> None:
    """palmapropiedades.com.ar — Mar del Plata."""
    _scrape_no_tokko(supabase, existing_urls, context, "palma_mdp",
                     ["https://www.palmapropiedades.com.ar/Venta",
                      "https://www.palmapropiedades.com.ar/Alquiler",
                      "https://www.palmapropiedades.com.ar/propiedades"],
                     "Mar del Plata")


def scrape_fracchia(supabase: SupabaseClient, existing_urls: set, context) -> None:
    """fracchiapropiedades.com.ar — Monte Grande."""
    _scrape_no_tokko(supabase, existing_urls, context, "fracchia",
                     ["https://www.fracchiapropiedades.com.ar/Venta",
                      "https://www.fracchiapropiedades.com.ar/Alquiler",
                      "https://www.fracchiapropiedades.com.ar/propiedades",
                      "https://www.fracchiapropiedades.com.ar/"],
                     "Monte Grande")




def scrape_caruso(supabase: SupabaseClient, existing_urls: set, context) -> None:
    """caruso-prop.com — Quilmes."""
    _scrape_no_tokko(supabase, existing_urls, context, "caruso",
                     ["https://www.caruso-prop.com/Venta",
                      "https://www.caruso-prop.com/Alquiler",
                      "https://www.caruso-prop.com/propiedades"],
                     "Quilmes")


def scrape_labrousse(supabase: SupabaseClient, existing_urls: set, context) -> None:
    """labrousseprop.com.ar — Ciudad Evita."""
    _scrape_no_tokko(supabase, existing_urls, context, "labrousse",
                     ["http://www.labrousseprop.com.ar/Venta",
                      "http://www.labrousseprop.com.ar/Alquiler",
                      "http://www.labrousseprop.com.ar/propiedades"],
                     "Ciudad Evita")


def scrape_romanazzi(supabase: SupabaseClient, existing_urls: set, context) -> None:
    """inmoromanazzi.com.ar"""
    _scrape_no_tokko(supabase, existing_urls, context, "romanazzi",
                     ["https://www.inmoromanazzi.com.ar/Venta",
                      "https://www.inmoromanazzi.com.ar/Alquiler",
                      "https://www.inmoromanazzi.com.ar/propiedades",
                      "https://www.inmoromanazzi.com.ar/"],
                     "Buenos Aires")


def scrape_cudrano(supabase: SupabaseClient, existing_urls: set, context) -> None:
    """cudranopropiedades.com.ar — Miramar."""
    _scrape_no_tokko(supabase, existing_urls, context, "cudrano",
                     ["https://www.cudranopropiedades.com.ar/Venta",
                      "https://www.cudranopropiedades.com.ar/Alquiler",
                      "https://www.cudranopropiedades.com.ar/propiedades"],
                     "Miramar")


def scrape_siciliano(supabase: SupabaseClient, existing_urls: set, context) -> None:
    """sicilianopropiedades.com.ar — Buenos Aires."""
    _scrape_no_tokko(supabase, existing_urls, context, "siciliano",
                     ["https://www.sicilianopropiedades.com.ar/propiedades/venta",
                      "https://www.sicilianopropiedades.com.ar/propiedades/alquiler",
                      "https://www.sicilianopropiedades.com.ar/Venta",
                      "https://www.sicilianopropiedades.com.ar/Alquiler"],
                     "Buenos Aires")


def scrape_rlb(supabase: SupabaseClient, existing_urls: set, context) -> None:
    """rlbinmoarq.com — Valentín Alsina."""
    _scrape_no_tokko(supabase, existing_urls, context, "rlb",
                     ["https://rlbinmoarq.com/propiedades/",
                      "https://rlbinmoarq.com/Venta",
                      "https://rlbinmoarq.com/Alquiler",
                      "https://rlbinmoarq.com/"],
                     "Buenos Aires")


def scrape_caruso_propiedades(supabase: SupabaseClient, existing_urls: set, context) -> None:
    """carusopropiedades.com — Paso del Rey."""
    _scrape_no_tokko(supabase, existing_urls, context, "caruso_propiedades",
                     ["https://www.carusopropiedades.com/Venta",
                      "https://www.carusopropiedades.com/Alquiler",
                      "https://www.carusopropiedades.com/propiedades"],
                     "Paso del Rey")


def scrape_battini(supabase: SupabaseClient, existing_urls: set, context) -> None:
    """inmobiliariabattini.com.ar — Morón."""
    _scrape_no_tokko(supabase, existing_urls, context, "battini",
                     ["https://www.inmobiliariabattini.com.ar/Venta",
                      "https://www.inmobiliariabattini.com.ar/Alquiler",
                      "https://www.inmobiliariabattini.com.ar/propiedades"],
                     "Morón")


def scrape_caudana(supabase: SupabaseClient, existing_urls: set, context) -> None:
    """caudanapropiedades.com.ar — San Justo / Ramos Mejía. CMS propio."""
    _scrape_no_tokko(supabase, existing_urls, context, "caudana",
                     ["https://www.caudanapropiedades.com.ar/Venta",
                      "https://www.caudanapropiedades.com.ar/Alquiler",
                      "https://www.caudanapropiedades.com.ar/propiedades",
                      "https://www.caudanapropiedades.com.ar/"],
                     "San Justo")


def scrape_nizzi(supabase: SupabaseClient, existing_urls: set, context) -> None:
    """nizzipropiedades.com — Mar del Plata. CMS propio con ?operacion=."""
    _scrape_no_tokko(supabase, existing_urls, context, "nizzi",
                     ["https://www.nizzipropiedades.com/propiedades?operacion=1",
                      "https://www.nizzipropiedades.com/propiedades?operacion=2",
                      "https://www.nizzipropiedades.com/propiedades"],
                     "Mar del Plata",
                     segmentos_prop=["/propiedades/"])


def scrape_mudafy(supabase: SupabaseClient, existing_urls: set, context) -> None:
    """mudafy.com.ar — Buenos Aires. Plataforma propia. Solo venta."""
    _scrape_no_tokko(supabase, existing_urls, context, "mudafy",
                     ["https://mudafy.com.ar/venta/propiedades",
                      "https://mudafy.com.ar/propiedades"],
                     "Buenos Aires",
                     segmentos_prop=["/propiedad/", "/p/", "/venta/"])


def scrape_nuevas_no_tokko(supabase: SupabaseClient, existing_urls: set, context) -> None:
    """Llama a todos los scrapers de inmobiliarias con CMS propio."""
    for fn in [
        scrape_zanola,
        scrape_krak,
        scrape_barbini,
        scrape_palma_mdp,
        scrape_fracchia,
        scrape_civeira,
        scrape_caruso,
        scrape_labrousse,
        scrape_romanazzi,
        scrape_cudrano,
        scrape_siciliano,
        scrape_rlb,
        scrape_caruso_propiedades,
        scrape_battini,
        scrape_tizado,
        scrape_caudana,
        scrape_nizzi,
        scrape_mudafy,
    ]:
        try:
            fn(supabase, existing_urls, context)
        except Exception as exc:
            logger.error(f"Error en {fn.__name__}: {exc}")


def scrape_config_sources(supabase: SupabaseClient, existing_urls: set, context) -> None:
    """
    Scrapea todas las fuentes definidas en SOURCE_CONFIGS (config.py) usando Playwright.
    Reemplaza el scraper.py basado en requests para estas inmobiliarias.
    Usa los mismos selectores CSS definidos en cada SourceConfig.

    Fuentes incluidas: uretacortes, sauce, guastavino, tomas_venta/alquiler,
    samar_venta/alquiler, orcu_venta/alquiler, grosso_venta/alquiler,
    migone_venta/alquiler, salas_venta/alquiler, benuzzi.
    (lenarduzzi se maneja por separado con cookie)
    """
    # Estas fuentes tienen manejo especial, las saltamos acá
    SKIP_KEYS = {"lenarduzzi_venta", "lenarduzzi_alquiler"}

    logger.info(f"[config_sources] Iniciando — {len(SOURCE_CONFIGS)} fuentes en config.py")
    total_guardadas = 0

    for key, cfg in SOURCE_CONFIGS.items():
        if key in SKIP_KEYS:
            logger.info(f"[{key}] Saltando (manejo especial)")
            continue

        page = context.new_page()
        try:
            # Construir URLs de paginación
            # Si max_pages=1 o no hay {} en la URL, solo una página
            max_p = cfg.max_pages if cfg.max_pages is not None else 30
            page_start = getattr(cfg, "page_start", 1)
            empty_pages = 0
            consecutive_zero_nuevas = 0  # corte anticipado si el sitio repite contenido
            MAX_ZERO_NUEVAS = 3
            total_fuente = 0

            for page_num in range(page_start, page_start + max_p):
                # Construir URL de la página
                if "{}" in cfg.base_url:
                    url = cfg.base_url.format(page_num)
                else:
                    url = cfg.base_url
                base_domain = "/".join(url.split("/")[:3])

                logger.info(f"[{key}] Página {page_num} → {url}")

                try:
                    ok = _goto_safe(page, url, timeout=40000)
                    if not ok:
                        empty_pages += 1
                        if empty_pages >= 2:
                            break
                        continue
                    page.wait_for_timeout(2500)
                    if cfg.post_data:
                        # orcu usa POST — vamos directo a la URL de resultados
                        # que Playwright puede manejar navegando con JS
                        page.evaluate(f"""
                            fetch('{url}', {{
                                method: 'POST',
                                headers: {{'Content-Type': 'application/x-www-form-urlencoded'}},
                                body: '{_dict_to_form(cfg.post_data)}'
                            }}).then(r => r.text()).then(html => {{
                                document.open(); document.write(html); document.close();
                            }})
                        """)
                        page.wait_for_timeout(3000)
                except Exception as exc:
                    logger.warning(f"[{key}] Error procesando página {page_num}: {exc}")
                    empty_pages += 1
                    if empty_pages >= 2:
                        break
                    continue

                html = page.content()
                soup = BeautifulSoup(html, "html.parser")
                cards = soup.select(cfg.selector_propiedad)

                if not cards:
                    empty_pages += 1
                    logger.info(f"[{key}] Página {page_num}: sin cards ({empty_pages} vacías)")
                    if empty_pages >= 2:
                        break
                    if max_p == 1 or "{}" not in cfg.base_url:
                        break
                    continue

                empty_pages = 0
                nuevas = []
                seen = set()

                for card in cards:
                    # Extraer URL de la propiedad
                    prop_url = None
                    for a in card.find_all("a", href=True):
                        href = a["href"].strip()
                        if cfg.url_required_segment in href:
                            if cfg.forbidden_segment and cfg.forbidden_segment in href:
                                continue
                            prop_url = href if href.startswith("http") else urljoin(base_domain + "/", href.lstrip("/"))
                            break

                    if not prop_url or prop_url in existing_urls or prop_url in seen:
                        continue
                    seen.add(prop_url)

                    # Extraer datos del card
                    titulo_el = card.select_one(cfg.selector_titulo)
                    titulo = titulo_el.get_text(strip=True) if titulo_el else None

                    ubicacion_el = card.select_one(cfg.selector_ubicacion)
                    ubicacion = ubicacion_el.get_text(strip=True) if ubicacion_el else ""

                    precio_el = card.select_one(cfg.selector_precio)
                    precio_raw = precio_el.get_text(strip=True) if precio_el else ""
                    precio, moneda = DataCleaner.clean_price(precio_raw)

                    barrio = DataCleaner.extract_neighborhood(ubicacion) or DataCleaner.extract_neighborhood(titulo or "")
                    tipo = DataCleaner.detect_property_type(titulo or "", ubicacion)

                    # ── OPERACIÓN: forzada > card text/URL > URL path > key suffix ─
                    if cfg.operacion_forzada:
                        operacion = cfg.operacion_forzada
                    else:
                        card_text_lower = (titulo or "").lower() + " " + ubicacion.lower()
                        prop_lower = prop_url.lower()
                        if "alquiler" in prop_lower or "alquiler" in card_text_lower:
                            operacion = "alquiler"
                        elif "venta" in prop_lower or "venta" in card_text_lower:
                            operacion = "venta"
                        elif "alquiler" in url.lower() or "alquileres" in url.lower() or key.endswith("_alquiler"):
                            operacion = "alquiler"
                        elif "venta" in url.lower() or "ventas" in url.lower() or key.endswith("_venta"):
                            operacion = "venta"
                        else:
                            operacion = "venta"  # default

                    if not titulo:
                        titulo = ubicacion or prop_url.split("/")[-1].replace("-", " ").title()

                    # ── IMAGEN: thumbnail del card ────────────────────────────────
                    _CFG_IMG_SKIP = {"logo", "icon", "placeholder", "blank",
                                     "spinner", "loading", "avatar"}
                    imagenes: List[str] = []
                    for img in card.select("img"):
                        src = (img.get("src") or img.get("data-src") or
                               img.get("data-lazy-src") or img.get("data-original") or "").strip()
                        if not src or src.startswith("data:"):
                            continue
                        if not src.startswith("http"):
                            src = urljoin(base_domain + "/", src.lstrip("/"))
                        sl = src.lower()
                        if any(s in sl for s in _CFG_IMG_SKIP) or sl.endswith(".svg"):
                            continue
                        imagenes = [src]
                        break

                    prop = Propiedad(
                        url=prop_url,
                        titulo=titulo,
                        precio=precio,
                        moneda=moneda,
                        barrio=barrio,
                        barrio_normalizado=DataCleaner.normalize_neighborhood(barrio),
                        tipo_propiedad=tipo,
                        ciudad=cfg.ciudad,
                        operacion=operacion,
                        fuente=key,
                        direccion=ubicacion or None,
                        imagenes=imagenes,
                    )

                    if prop.is_valid():
                        nuevas.append(prop)

                logger.info(f"[{key}] Página {page_num}: {len(cards)} cards | {len(nuevas)} nuevas")

                if nuevas:
                    saved = supabase.batch_save_only_new([p.to_payload() for p in nuevas])
                    logger.info(f"[{key}] Guardadas: {saved}")
                    existing_urls.update(p.url for p in nuevas)
                    total_fuente += saved
                    total_guardadas += saved
                    consecutive_zero_nuevas = 0
                else:
                    consecutive_zero_nuevas += 1
                    if consecutive_zero_nuevas >= MAX_ZERO_NUEVAS and max_p > 1:
                        logger.info(f"[{key}] {MAX_ZERO_NUEVAS} páginas sin nuevas — deteniendo paginación.")
                        break

                # Si solo hay una página o URL sin paginación, salir
                if max_p == 1 or "{}" not in cfg.base_url:
                    break

                time.sleep(1.2)

            logger.info(f"[{key}] Total guardadas: {total_fuente}")

        except Exception as exc:
            logger.error(f"[{key}] Error general: {exc}")
        finally:
            page.close()

    logger.info(f"[config_sources] Total general guardadas: {total_guardadas}")


def _dict_to_form(d: dict) -> str:
    """Convierte un dict a formato application/x-www-form-urlencoded."""
    from urllib.parse import urlencode
    return urlencode(d)


def scrape_all():
    session = SessionFactory.create()
    supabase = SupabaseClient(session, SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, SUPABASE_TABLE)
    existing_urls = supabase.get_all_existing_urls()
    logger.info(f"URLs existentes: {len(existing_urls)}")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ))

        for fuente in FUENTES:
            key = fuente["key"]
            url = fuente["url"]
            operacion = fuente["operacion"]
            ciudad = fuente.get("ciudad", "Santa Fe")
            base_url = "/".join(url.split("/")[:3])

            logger.info(f"[{key}] Scrapeando {url}")
            page = context.new_page()
            try:
                page.goto(url, timeout=90000, wait_until="domcontentloaded")
                page.wait_for_timeout(5000)
                total = scroll_to_bottom(page)
                logger.info(f"[{key}] {total} propiedades encontradas")

                if total == 0:
                    logger.info(f"[{key}] Sin propiedades, saltando.")
                    page.close()
                    continue

                propiedades = parse_cards(page.content(), operacion, key, base_url, ciudad)
                nuevas = [prop for prop in propiedades if prop.url not in existing_urls]
                logger.info(f"[{key}] {len(nuevas)} nuevas de {len(propiedades)}")

                if nuevas:
                    saved = supabase.batch_save_only_new([prop.to_payload() for prop in nuevas])
                    logger.info(f"[{key}] Guardadas: {saved}")
                    existing_urls.update(prop.url for prop in nuevas)

            except Exception as exc:
                logger.error(f"[{key}] Error: {exc}")
            finally:
                page.close()

        # ── Inmobiliarias nuevas (Tokko Broker y similares) ───────────────────
        scrape_nuevas(supabase, existing_urls, context)

        # ── Fuentes de config.py migradas a Playwright ────────────────────────
        scrape_config_sources(supabase, existing_urls, context)

        browser.close()

    # APL, Raffin, Pilay, Raes, no-Tokko y otros con lógica especial
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ))
        scrape_apl(supabase, existing_urls, context)
        scrape_raffin(supabase, existing_urls, context)
        scrape_pilay(supabase, existing_urls, context)
        scrape_raes(supabase, existing_urls, context)
        scrape_nuevas_no_tokko(supabase, existing_urls, context)
        browser.close()

    # Scrapers con lógica especial que siguen usando requests
    scrape_9010(supabase, existing_urls, session)
    scrape_lenarduzzi(supabase, existing_urls, session)  # necesita cookie
    scrape_cisfe(supabase, existing_urls, session)
    scrape_cam(supabase, existing_urls, session)
    scrape_sofia(supabase, existing_urls, session)
    scrape_casablanca(supabase, existing_urls, session)
    scrape_proa(supabase, existing_urls, session)
    scrape_sur(supabase, existing_urls, session)
    scrape_neo(supabase, existing_urls, session)
    scrape_bygger(supabase, existing_urls, session)
    scrape_gen(supabase, existing_urls, session)

    logger.info("Scraping finalizado.")


if __name__ == "__main__":
    scrape_all()