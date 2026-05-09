"""
scraper_google_inmobiliarias.py
--------------------------------
Scraper de Google Maps para inmobiliarias de toda Argentina.

Cobertura: 23 provincias + CABA, barrio por barrio en ciudades principales.

Extrae por negocio:
    nombre, direccion, barrio, ciudad, provincia, pais,
    telefono, email, web, rating, resenas, fuente, fecha_scrapeo

Guarda en CSV local + Supabase (con fallback a CSV si Supabase falla).
Deduplicacion global por nombre y por web.

Dependencias:
    pip install playwright requests python-dotenv playwright-stealth
    playwright install chromium
"""

import os
import sys
import csv
import re
import json
import time
import random
import traceback
from datetime import datetime
from urllib.parse import urlparse, unquote_plus, parse_qs

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

try:
    from playwright_stealth import stealth_sync
    STEALTH_AVAILABLE = True
except ImportError:
    STEALTH_AVAILABLE = False

# =============================================================================
# CONFIGURACION
# =============================================================================

script_dir = os.path.dirname(os.path.abspath(__file__))

try:
    from dotenv import load_dotenv
    _dotenv_path = os.path.join(script_dir, "..", ".env")
    if not os.path.exists(_dotenv_path):
        _dotenv_path = os.path.join(script_dir, ".env")
    load_dotenv(dotenv_path=_dotenv_path)
except ImportError:
    pass

SUPABASE_URL      = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY      = (
    os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    or os.getenv("SUPABASE_KEY")
    or os.getenv("SUPABASE_ANON_KEY", "")
)
SUPABASE_TABLE    = "inmobiliarias_scraping"
SUPABASE_ENDPOINT        = f"{SUPABASE_URL}/rest/v1/{SUPABASE_TABLE}?on_conflict=nombre"
SUPABASE_ENDPOINT_IGNORE = f"{SUPABASE_URL}/rest/v1/{SUPABASE_TABLE}?on_conflict=nombre"
SUPABASE_HEADERS  = {
    "apikey":        SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type":  "application/json",
    "Prefer":        "resolution=merge-duplicates,return=minimal",
}
SUPABASE_HEADERS_IGNORE = {
    "apikey":        SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type":  "application/json",
    "Prefer":        "resolution=ignore-duplicates,return=minimal",
}

# Sesión HTTP persistente con retry automático para errores de red
def _crear_sesion_supabase() -> requests.Session:
    sesion = requests.Session()
    retry = Retry(
        total=4,
        backoff_factor=1.5,          # esperas: 0s, 1.5s, 3s, 6s
        status_forcelist=[500, 502, 503, 504],
        allowed_methods=["POST", "GET"],
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    sesion.mount("https://", adapter)
    sesion.mount("http://",  adapter)
    return sesion

_SUPA_SESSION: requests.Session = _crear_sesion_supabase()

CSV_FILE        = os.path.join(script_dir, "..", "google_inmobiliarias.csv")
CHECKPOINT_FILE = os.path.join(script_dir, "checkpoint_inmobiliarias.txt")
CSV_FIELDS = [
    "nombre", "direccion", "barrio", "ciudad", "provincia", "pais",
    "telefono", "email", "web", "rating", "resenas", "categoria", "fuente", "fecha_scrapeo",
]

GOOGLE_LUGARES_URL = "https://www.google.com/maps/search/{query}/"

# =============================================================================
# QUERIES — 23 PROVINCIAS + CABA (cobertura completa)
# =============================================================================

QUERIES = [
     # =========================================================================
    # CIUDAD AUTÓNOMA DE BUENOS AIRES (CABA) — 48 barrios
    # =========================================================================
    "inmobiliarias caba buenos aires",
    "inmobiliarias barrio palermo buenos aires",
    "inmobiliarias barrio recoleta buenos aires",
    "inmobiliarias barrio belgrano buenos aires",
    "inmobiliarias barrio caballito buenos aires",
    "inmobiliarias barrio almagro buenos aires",
    "inmobiliarias barrio balvanera buenos aires",
    "inmobiliarias barrio villa crespo buenos aires",
    "inmobiliarias barrio villa urquiza buenos aires",
    "inmobiliarias barrio villa devoto buenos aires",
    "inmobiliarias barrio villa del parque buenos aires",
    "inmobiliarias barrio villa pueyrredon buenos aires",
    "inmobiliarias barrio villa ortuzar buenos aires",
    "inmobiliarias barrio colegiales buenos aires",
    "inmobiliarias barrio chacarita buenos aires",
    "inmobiliarias barrio paternal buenos aires",
    "inmobiliarias barrio saavedra buenos aires",
    "inmobiliarias barrio nunez buenos aires",
    "inmobiliarias barrio coghlan buenos aires",
    "inmobiliarias barrio retiro buenos aires",
    "inmobiliarias barrio san nicolas buenos aires",
    "inmobiliarias barrio monserrat buenos aires",
    "inmobiliarias barrio san telmo buenos aires",
    "inmobiliarias barrio constitucion buenos aires",
    "inmobiliarias barrio barracas buenos aires",
    "inmobiliarias barrio la boca buenos aires",
    "inmobiliarias barrio san cristobal buenos aires",
    "inmobiliarias barrio boedo buenos aires",
    "inmobiliarias barrio parque patricios buenos aires",
    "inmobiliarias barrio nueva pompeya buenos aires",
    "inmobiliarias barrio parque chacabuco buenos aires",
    "inmobiliarias barrio flores buenos aires",
    "inmobiliarias barrio floresta buenos aires",
    "inmobiliarias barrio velez sarfield buenos aires",
    "inmobiliarias barrio liniers buenos aires",
    "inmobiliarias barrio mataderos buenos aires",
    "inmobiliarias barrio parque avellaneda buenos aires",
    "inmobiliarias barrio villa lugano buenos aires",
    "inmobiliarias barrio villa soldati buenos aires",
    "inmobiliarias barrio villa riachuelo buenos aires",
    "inmobiliarias barrio villa luro buenos aires",
    "inmobiliarias barrio monte castro buenos aires",
    "inmobiliarias barrio versalles buenos aires",
    "inmobiliarias barrio villa real buenos aires",
    "inmobiliarias barrio villa santa rita buenos aires",
    "inmobiliarias barrio villa general mitre buenos aires",
    "inmobiliarias barrio parque chas buenos aires",
    "inmobiliarias barrio agronoma buenos aires",
    "inmobiliarias barrio puerto madero buenos aires",
    "propiedades venta caba buenos aires",
    "propiedades alquiler caba buenos aires",
    "martilleros caba buenos aires",
    "agencia inmobiliaria capital federal",
    "inmobiliarias zona norte caba",
    "inmobiliarias zona sur caba",

    # =========================================================================
    # BUENOS AIRES PROVINCIA — GBA ZONA NORTE
    # =========================================================================
    "inmobiliarias san isidro buenos aires",
    "inmobiliarias barrio centro san isidro",
    "inmobiliarias barrio beccar san isidro",
    "inmobiliarias barrio martinez san isidro",
    "inmobiliarias barrio acassuso san isidro",
    "inmobiliarias barrio boulogne san isidro",
    "inmobiliarias vicente lopez buenos aires",
    "inmobiliarias barrio florida vicente lopez",
    "inmobiliarias barrio olivos vicente lopez",
    "inmobiliarias barrio la lucila vicente lopez",
    "inmobiliarias barrio munro vicente lopez",
    "inmobiliarias san fernando buenos aires",
    "inmobiliarias tigre buenos aires",
    "inmobiliarias barrio nordelta tigre",
    "inmobiliarias barrio el talar tigre",
    "inmobiliarias barrio rincon de milberg tigre",
    "inmobiliarias escobar buenos aires",
    "inmobiliarias barrio belen de escobar",
    "inmobiliarias pilar buenos aires",
    "inmobiliarias barrio centro pilar",
    "inmobiliarias barrio del viso pilar",
    "inmobiliarias barrio manzanares pilar",
    "inmobiliarias barrio villa rosa pilar",
    "inmobiliarias zarate buenos aires",
    "inmobiliarias campana buenos aires",
    "inmobiliarias san pedro buenos aires",
    "inmobiliarias baradero buenos aires",
    "inmobiliarias pergamino buenos aires",
    "inmobiliarias san antonio de areco buenos aires",

    # =========================================================================
    # BUENOS AIRES PROVINCIA — GBA ZONA OESTE
    # =========================================================================
    "inmobiliarias moron buenos aires",
    "inmobiliarias barrio centro moron",
    "inmobiliarias barrio haedo moron",
    "inmobiliarias hurlingham buenos aires",
    "inmobiliarias ituzaingo buenos aires",
    "inmobiliarias merlo buenos aires",
    "inmobiliarias barrio centro merlo",
    "inmobiliarias barrio libertad merlo",
    "inmobiliarias moreno buenos aires",
    "inmobiliarias barrio centro moreno",
    "inmobiliarias barrio paso del rey moreno",
    "inmobiliarias general rodriguez buenos aires",
    "inmobiliarias lujan buenos aires",
    "inmobiliarias mercedes buenos aires",
    "inmobiliarias chivilcoy buenos aires",
    "inmobiliarias tres de febrero buenos aires",
    "inmobiliarias barrio caseros tres de febrero",
    "inmobiliarias barrio ciudadela tres de febrero",
    "inmobiliarias barrio el palomar tres de febrero",
    "inmobiliarias san miguel buenos aires",
    "inmobiliarias jose c paz buenos aires",
    "inmobiliarias malvinas argentinas buenos aires",

    # =========================================================================
    # BUENOS AIRES PROVINCIA — GBA ZONA SUR
    # =========================================================================
    "inmobiliarias lomas de zamora buenos aires",
    "inmobiliarias barrio centro lomas de zamora",
    "inmobiliarias barrio llavallol lomas de zamora",
    "inmobiliarias lanus buenos aires",
    "inmobiliarias barrio centro lanus",
    "inmobiliarias barrio lanus este",
    "inmobiliarias avellaneda buenos aires",
    "inmobiliarias barrio centro avellaneda",
    "inmobiliarias barrio sarandí avellaneda",
    "inmobiliarias quilmes buenos aires",
    "inmobiliarias barrio centro quilmes",
    "inmobiliarias barrio bernal quilmes",
    "inmobiliarias barrio ezpeleta quilmes",
    "inmobiliarias berazategui buenos aires",
    "inmobiliarias florencio varela buenos aires",
    "inmobiliarias almirante brown buenos aires",
    "inmobiliarias barrio adrogué almirante brown",
    "inmobiliarias barrio burzaco almirante brown",
    "inmobiliarias barrio longchamps almirante brown",
    "inmobiliarias esteban echeverria buenos aires",
    "inmobiliarias barrio monte grande esteban echeverria",
    "inmobiliarias la matanza buenos aires",
    "inmobiliarias barrio ramos mejia la matanza",
    "inmobiliarias barrio san justo la matanza",
    "inmobiliarias barrio tapalque la matanza",
    "inmobiliarias ezeiza buenos aires",
    "inmobiliarias presidente peron buenos aires",
    "inmobiliarias canuelas buenos aires",

    # =========================================================================
    # BUENOS AIRES PROVINCIA — INTERIOR
    # =========================================================================
    # La Plata
    "inmobiliarias la plata buenos aires",
    "inmobiliarias barrio centro la plata",
    "inmobiliarias barrio norte la plata",
    "inmobiliarias barrio sur la plata",
    "inmobiliarias barrio este la plata",
    "inmobiliarias barrio city bell la plata",
    "inmobiliarias barrio villa elisa la plata",
    "inmobiliarias barrio tolosa la plata",
    "inmobiliarias barrio gonnet la plata",
    "inmobiliarias barrio los hornos la plata",
    "inmobiliarias berisso buenos aires",
    "inmobiliarias ensenada buenos aires",
    # Mar del Plata
    "inmobiliarias mar del plata",
    "inmobiliarias barrio centro mar del plata",
    "inmobiliarias barrio norte mar del plata",
    "inmobiliarias barrio sur mar del plata",
    "inmobiliarias barrio camet mar del plata",
    "inmobiliarias barrio punta mogotes mar del plata",
    "inmobiliarias barrio puerto mar del plata",
    "inmobiliarias barrio los pinos mar del plata",
    "inmobiliarias barrio playa grande mar del plata",
    # Bahía Blanca
    "inmobiliarias bahia blanca",
    "inmobiliarias barrio centro bahia blanca",
    "inmobiliarias barrio villa mitre bahia blanca",
    "inmobiliarias barrio villa rosas bahia blanca",
    "inmobiliarias barrio napostá bahia blanca",
    "inmobiliarias punta alta buenos aires",
    # Interior bonaerense
    "inmobiliarias tandil buenos aires",
    "inmobiliarias olavarria buenos aires",
    "inmobiliarias junin buenos aires",
    "inmobiliarias san nicolas buenos aires",
    "inmobiliarias azul buenos aires",
    "inmobiliarias necochea buenos aires",
    "inmobiliarias miramar buenos aires",
    "inmobiliarias pinamar buenos aires",
    "inmobiliarias villa gesell buenos aires",
    "inmobiliarias mar de ajo buenos aires",
    "inmobiliarias dolores buenos aires",
    "inmobiliarias chascomus buenos aires",
    "inmobiliarias nine de julio buenos aires",
    "inmobiliarias lincoln buenos aires",
    "inmobiliarias bragado buenos aires",
    "inmobiliarias trenque lauquen buenos aires",
    "inmobiliarias pehuajo buenos aires",
    "inmobiliarias colonel suarez buenos aires",
    "inmobiliarias tres arroyos buenos aires",
    "inmobiliarias coronel pringles buenos aires",
    "inmobiliarias daireaux buenos aires",
    "inmobiliarias bolivar buenos aires",
    "inmobiliarias rauch buenos aires",
    "inmobiliarias general pueyrredon mar del plata",
    "propiedades venta buenos aires provincia",
    "martilleros buenos aires provincia",

    # =========================================================================
    # CÓRDOBA CAPITAL — todos los barrios
    # =========================================================================
    "inmobiliarias cordoba capital",
    "inmobiliarias barrio centro cordoba capital",
    "inmobiliarias barrio nueva cordoba",
    "inmobiliarias barrio alta cordoba",
    "inmobiliarias barrio cofico cordoba",
    "inmobiliarias barrio general paz cordoba",
    "inmobiliarias barrio cerro de las rosas cordoba",
    "inmobiliarias barrio villa belgrano cordoba",
    "inmobiliarias barrio arguello cordoba",
    "inmobiliarias barrio urca cordoba",
    "inmobiliarias barrio alberdi cordoba",
    "inmobiliarias barrio guemes cordoba",
    "inmobiliarias barrio jardin cordoba",
    "inmobiliarias barrio maipu cordoba capital",
    "inmobiliarias barrio san martin cordoba capital",
    "inmobiliarias barrio san vicente cordoba",
    "inmobiliarias barrio villa el libertador cordoba",
    "inmobiliarias barrio villa paez cordoba",
    "inmobiliarias barrio villa urquiza cordoba",
    "inmobiliarias barrio observatorio cordoba",
    "inmobiliarias barrio providencia cordoba",
    "inmobiliarias barrio chateau carreras cordoba",
    "inmobiliarias barrio parque velez sarfield cordoba",
    "inmobiliarias barrio general bustos cordoba",
    "inmobiliarias barrio marques de sobremonte cordoba",
    "inmobiliarias barrio los naranjos cordoba",
    "inmobiliarias barrio el brillante cordoba",
    "inmobiliarias barrio villa cabrera cordoba",
    "inmobiliarias barrio villa warcalde cordoba",
    "inmobiliarias barrio manantiales cordoba",
    "inmobiliarias barrio ituzaingo cordoba",
    "inmobiliarias barrio pueyrredon cordoba",
    "inmobiliarias barrio remedios de escalada cordoba",
    "inmobiliarias barrio santa isabel cordoba",
    "inmobiliarias barrio los boulevares cordoba",
    "inmobiliarias barrio villa san isidro cordoba",
    "inmobiliarias barrio yapeyu cordoba",
    "inmobiliarias barrio yofre norte cordoba",
    "inmobiliarias barrio yofre sur cordoba",
    "inmobiliarias barrio las violetas cordoba",
    "inmobiliarias barrio colinas de velez sarfield cordoba",
    "inmobiliarias barrio muller cordoba",
    "inmobiliarias barrio ferreyra cordoba",
    "inmobiliarias barrio malvinas argentinas cordoba",
    "inmobiliarias barrio villa adela cordoba",
    "inmobiliarias barrio villa boedo cordoba",
    "inmobiliarias barrio villa buenos aires cordoba",
    "inmobiliarias barrio villa corina cordoba",
    "inmobiliarias barrio villa dora cordoba",
    "inmobiliarias barrio villa eucaristica cordoba",
    "inmobiliarias barrio villa fortunata cordoba",
    "inmobiliarias barrio villa hipodromo cordoba",
    "inmobiliarias barrio villa la merced cordoba",
    "inmobiliarias barrio villa lourdes cordoba",
    "inmobiliarias barrio villa los llanos cordoba",
    "inmobiliarias barrio villa moreno cordoba",
    "inmobiliarias barrio villa revol cordoba",
    "inmobiliarias barrio villa rios cordoba",
    "inmobiliarias barrio villa robles cordoba",
    "inmobiliarias barrio villa santos dumont cordoba",
    "inmobiliarias barrio villa siburu cordoba",
    "inmobiliarias barrio juniors cordoba",
    "inmobiliarias barrio inaudi cordoba",
    "inmobiliarias barrio parque atletico cordoba",
    "inmobiliarias barrio parque capital cordoba",
    "inmobiliarias barrio las palmas cordoba",
    "inmobiliarias barrio las delicias cordoba capital",
    "inmobiliarias barrio los paraísos cordoba",
    "inmobiliarias barrio country club cordoba",
    "inmobiliarias barrio quintas de santa ana cordoba",
    "inmobiliarias barrio suarez cordoba",
    "inmobiliarias barrio san pablo cordoba capital",
    "inmobiliarias barrio la tablada cordoba",
    "inmobiliarias barrio empalme cordoba",
    "inmobiliarias zona norte cordoba capital",
    "inmobiliarias zona sur cordoba capital",
    "inmobiliarias zona este cordoba capital",
    "inmobiliarias zona oeste cordoba capital",
    "propiedades venta cordoba capital",
    "propiedades alquiler cordoba capital",
    "martilleros cordoba capital",
    # Gran Córdoba
    "inmobiliarias villa allende cordoba",
    "inmobiliarias mendiolaza cordoba",
    "inmobiliarias unquillo cordoba",
    "inmobiliarias rio ceballos cordoba",
    "inmobiliarias la calera cordoba",
    "inmobiliarias saldan cordoba",
    "inmobiliarias malagueño cordoba",
    "inmobiliarias pilar cordoba",
    "inmobiliarias jesus maria cordoba",
    "inmobiliarias colonia caroya cordoba",
    # Zona serrana
    "inmobiliarias villa carlos paz cordoba",
    "inmobiliarias cosquin cordoba",
    "inmobiliarias la falda cordoba",
    "inmobiliarias la cumbre cordoba",
    "inmobiliarias villa giardino cordoba",
    "inmobiliarias capilla del monte cordoba",
    "inmobiliarias alta gracia cordoba",
    "inmobiliarias villa general belgrano cordoba",
    "inmobiliarias mina clavero cordoba",
    "inmobiliarias villa cura brochero cordoba",
    "inmobiliarias tanti cordoba",
    "inmobiliarias bialet masse cordoba",
    "inmobiliarias santa rosa de calamuchita cordoba",
    "inmobiliarias embalse cordoba",
    "inmobiliarias cruz del eje cordoba",
    # Zona sur/norte/este
    "inmobiliarias rio cuarto cordoba",
    "inmobiliarias villa maria cordoba",
    "inmobiliarias rio tercero cordoba",
    "inmobiliarias bell ville cordoba",
    "inmobiliarias marcos juarez cordoba",
    "inmobiliarias san francisco cordoba",
    "inmobiliarias laboulaye cordoba",
    "inmobiliarias dean funes cordoba",
    "inmobiliarias oncativo cordoba",
    "inmobiliarias arroyito cordoba",

    # =========================================================================
    # SANTA FE — capital, rosario y provincia
    # =========================================================================
    "inmobiliarias santa fe capital",
    "inmobiliarias barrio centro santa fe",
    "inmobiliarias barrio candioti santa fe",
    "inmobiliarias barrio el pozo santa fe",
    "inmobiliarias barrio la florida santa fe",
    "inmobiliarias barrio guadalupe santa fe",
    "inmobiliarias barrio norte santa fe capital",
    "inmobiliarias barrio sur santa fe capital",
    "inmobiliarias santo tome santa fe",
    "inmobiliarias sauce viejo santa fe",
    "inmobiliarias recreo santa fe",
    "inmobiliarias rosario santa fe",
    "inmobiliarias barrio centro rosario",
    "inmobiliarias barrio pichincha rosario",
    "inmobiliarias barrio martin rosario",
    "inmobiliarias barrio alberdi rosario",
    "inmobiliarias barrio echesortu rosario",
    "inmobiliarias barrio fisherton rosario",
    "inmobiliarias barrio puerto norte rosario",
    "inmobiliarias barrio belgrano rosario",
    "inmobiliarias barrio arroyito rosario",
    "inmobiliarias barrio ludueña rosario",
    "inmobiliarias barrio republica de la sexta rosario",
    "inmobiliarias barrio saladillo rosario",
    "inmobiliarias barrio zona norte rosario",
    "inmobiliarias barrio zona sur rosario",
    "inmobiliarias funes santa fe",
    "inmobiliarias roldan santa fe",
    "inmobiliarias granadero baigorria",
    "inmobiliarias villa gobernador galvez",
    "inmobiliarias san lorenzo santa fe",
    "inmobiliarias rafaela santa fe",
    "inmobiliarias esperanza santa fe",
    "inmobiliarias venado tuerto santa fe",
    "inmobiliarias reconquista santa fe",
    "inmobiliarias casilda santa fe",
    "inmobiliarias villa constitucion santa fe",
    "inmobiliarias cañada de gomez santa fe",
    
    # =========================================================================
    # MENDOZA — capital, gran mendoza y provincia
    # =========================================================================
    "inmobiliarias mendoza capital",
    "inmobiliarias barrio primera seccion mendoza",
    "inmobiliarias barrio segunda seccion mendoza",
    "inmobiliarias barrio tercera seccion mendoza",
    "inmobiliarias barrio cuarta seccion mendoza",
    "inmobiliarias barrio quinta seccion mendoza",
    "inmobiliarias barrio sexta seccion mendoza",
    "inmobiliarias barrio dorrego mendoza",
    "inmobiliarias barrio bombal mendoza",
    "inmobiliarias barrio norte mendoza capital",
    "inmobiliarias barrio sur mendoza capital",
    "inmobiliarias godoy cruz mendoza",
    "inmobiliarias barrio chacras de coria mendoza",
    "inmobiliarias barrio benegas godoy cruz",
    "inmobiliarias guaymallen mendoza",
    "inmobiliarias barrio buena nueva guaymallen",
    "inmobiliarias barrio rodeo del medio guaymallen",
    "inmobiliarias las heras mendoza",
    "inmobiliarias barrio el challao las heras",
    "inmobiliarias lujan de cuyo mendoza",
    "inmobiliarias barrio vistalba mendoza",
    "inmobiliarias barrio chacras de coria lujan",
    "inmobiliarias barrio mayor drummond mendoza",
    "inmobiliarias barrio perdriel lujan de cuyo",
    "inmobiliarias maipu mendoza",
    "inmobiliarias barrio coquimbito maipu",
    "inmobiliarias barrio luzuriaga maipu",
    "inmobiliarias san martin mendoza",
    "inmobiliarias junin mendoza",
    "inmobiliarias rivadavia mendoza",
    "inmobiliarias san rafael mendoza",
    "inmobiliarias barrio centro san rafael",
    "inmobiliarias malargue mendoza",
    "inmobiliarias general alvear mendoza",
    "inmobiliarias lavalle mendoza",
    "inmobiliarias tunuyan mendoza",
    "inmobiliarias tupungato mendoza",
    "inmobiliarias valle de uco mendoza",
    "propiedades venta mendoza capital",
    "propiedades alquiler mendoza capital",
    "martilleros mendoza",

    # =========================================================================
    # TUCUMÁN
    # =========================================================================
    "inmobiliarias san miguel de tucuman",
    "inmobiliarias barrio centro tucuman",
    "inmobiliarias barrio norte tucuman",
    "inmobiliarias barrio sur tucuman",
    "inmobiliarias barrio este tucuman",
    "inmobiliarias barrio oeste tucuman",
    "inmobiliarias barrio yerba buena tucuman",
    "inmobiliarias barrio san javier tucuman",
    "inmobiliarias barrio alberdi tucuman",
    "inmobiliarias barrio los nogales tucuman",
    "inmobiliarias barrio villa carmela tucuman",
    "inmobiliarias barrio villa 9 de julio tucuman",
    "inmobiliarias barrio villa urquiza tucuman",
    "inmobiliarias barrio marcos paz tucuman",
    "inmobiliarias barrio el dorado tucuman",
    "inmobiliarias barrio san cayetano tucuman",
    "inmobiliarias barrio la loma tucuman",
    "inmobiliarias tafi viejo tucuman",
    "inmobiliarias barrio tafi del valle tucuman",
    "inmobiliarias concepcion tucuman",
    "inmobiliarias monteros tucuman",
    "inmobiliarias aguilares tucuman",
    "inmobiliarias famaillá tucuman",
    "inmobiliarias banda del rio sali tucuman",
    "inmobiliarias alderetes tucuman",
    "inmobiliarias las talitas tucuman",
    "inmobiliarias lules tucuman",
    "propiedades venta tucuman",
    "propiedades alquiler tucuman",
    "martilleros tucuman",

    # =========================================================================
    # SALTA
    # =========================================================================
    "inmobiliarias salta capital",
    "inmobiliarias barrio centro salta",
    "inmobiliarias barrio norte salta",
    "inmobiliarias barrio sur salta",
    "inmobiliarias barrio este salta capital",
    "inmobiliarias barrio oeste salta capital",
    "inmobiliarias barrio tres cerritos salta",
    "inmobiliarias barrio el tribuno salta",
    "inmobiliarias barrio san bernardo salta",
    "inmobiliarias barrio la loma salta",
    "inmobiliarias barrio nueva salta",
    "inmobiliarias barrio del milagro salta",
    "inmobiliarias barrio miguel ortiz salta",
    "inmobiliarias barrio castañares salta",
    "inmobiliarias barrio limache salta",
    "inmobiliarias san lorenzo salta",
    "inmobiliarias oran salta",
    "inmobiliarias tartagal salta",
    "inmobiliarias general guemes salta",
    "inmobiliarias cafayate salta",
    "inmobiliarias rosario de la frontera salta",
    "inmobiliarias embarcacion salta",
    "propiedades venta salta",
    "propiedades alquiler salta",
    "martilleros salta",

    # =========================================================================
    # ENTRE RÍOS
    # =========================================================================
    "inmobiliarias parana entre rios",
    "inmobiliarias barrio centro parana",
    "inmobiliarias barrio norte parana",
    "inmobiliarias barrio sur parana",
    "inmobiliarias barrio este parana",
    "inmobiliarias barrio oeste parana",
    "inmobiliarias barrio chapuis parana",
    "inmobiliarias barrio paraná norte",
    "inmobiliarias concordia entre rios",
    "inmobiliarias barrio centro concordia",
    "inmobiliarias gualeguaychu entre rios",
    "inmobiliarias barrio centro gualeguaychu",
    "inmobiliarias colon entre rios",
    "inmobiliarias concepcion del uruguay entre rios",
    "inmobiliarias gualeguay entre rios",
    "inmobiliarias victoria entre rios",
    "inmobiliarias nogoya entre rios",
    "inmobiliarias villaguay entre rios",
    "inmobiliarias san jose entre rios",
    "inmobiliarias federacion entre rios",
    "propiedades venta entre rios",
    "martilleros entre rios",

    # =========================================================================
    # CORRIENTES
    # =========================================================================
    "inmobiliarias corrientes capital",
    "inmobiliarias barrio centro corrientes",
    "inmobiliarias barrio norte corrientes",
    "inmobiliarias barrio sur corrientes",
    "inmobiliarias barrio este corrientes capital",
    "inmobiliarias barrio oeste corrientes capital",
    "inmobiliarias barrio querencia corrientes",
    "inmobiliarias barrio san gerardo corrientes",
    "inmobiliarias barrio laguna seca corrientes",
    "inmobiliarias goya corrientes",
    "inmobiliarias paso de los libres corrientes",
    "inmobiliarias curuzú cuatiá corrientes",
    "inmobiliarias santo tome corrientes",
    "inmobiliarias monte caseros corrientes",
    "inmobiliarias mercedes corrientes",
    "inmobiliarias bella vista corrientes",
    "inmobiliarias esquina corrientes",
    "propiedades venta corrientes",
    "martilleros corrientes",

    # =========================================================================
    # CHACO
    # =========================================================================
    "inmobiliarias resistencia chaco",
    "inmobiliarias barrio centro resistencia",
    "inmobiliarias barrio norte resistencia",
    "inmobiliarias barrio sur resistencia",
    "inmobiliarias barrio este resistencia",
    "inmobiliarias barrio oeste resistencia",
    "inmobiliarias barranqueras chaco",
    "inmobiliarias fontana chaco",
    "inmobiliarias villa del rosario chaco",
    "inmobiliarias presidencia roque saenz peña chaco",
    "inmobiliarias barrio centro saenz peña chaco",
    "inmobiliarias villa angela chaco",
    "inmobiliarias charata chaco",
    "inmobiliarias general pinedo chaco",
    "inmobiliarias juan jose castelli chaco",
    "propiedades venta chaco",
    "martilleros chaco",

    # =========================================================================
    # MISIONES
    # =========================================================================
    "inmobiliarias posadas misiones",
    "inmobiliarias barrio centro posadas",
    "inmobiliarias barrio norte posadas",
    "inmobiliarias barrio sur posadas",
    "inmobiliarias barrio este posadas",
    "inmobiliarias barrio villa lanus posadas",
    "inmobiliarias barrio villa cabello posadas",
    "inmobiliarias obera misiones",
    "inmobiliarias eldorado misiones",
    "inmobiliarias apostoles misiones",
    "inmobiliarias san ignacio misiones",
    "inmobiliarias puerto iguazu misiones",
    "inmobiliarias barrio centro puerto iguazu",
    "inmobiliarias montecarlo misiones",
    "inmobiliarias garuhape misiones",
    "inmobiliarias leandro n alem misiones",
    "propiedades venta misiones",
    "martilleros misiones",

    # =========================================================================
    # NEUQUÉN
    # =========================================================================
    "inmobiliarias neuquen capital",
    "inmobiliarias barrio centro neuquen",
    "inmobiliarias barrio norte neuquen",
    "inmobiliarias barrio sur neuquen",
    "inmobiliarias barrio este neuquen capital",
    "inmobiliarias barrio oeste neuquen capital",
    "inmobiliarias barrio alta barda neuquen",
    "inmobiliarias barrio san lorenzo neuquen",
    "inmobiliarias barrio belgrano neuquen",
    "inmobiliarias barrio villa del prado neuquen",
    "inmobiliarias barrio el progreso neuquen",
    "inmobiliarias cipolletti neuquen",
    "inmobiliarias barrio centro cipolletti",
    "inmobiliarias allen neuquen",
    "inmobiliarias general roca neuquen",
    "inmobiliarias san martin de los andes",
    "inmobiliarias villa la angostura neuquen",
    "inmobiliarias zapala neuquen",
    "inmobiliarias cutral co neuquen",
    "inmobiliarias plaza huincul neuquen",
    "inmobiliarias junin de los andes neuquen",
    "inmobiliarias centenario neuquen",
    "propiedades venta neuquen",
    "martilleros neuquen",

    # =========================================================================
    # RÍO NEGRO
    # =========================================================================
    "inmobiliarias bariloche rio negro",
    "inmobiliarias barrio centro bariloche",
    "inmobiliarias barrio norte bariloche",
    "inmobiliarias barrio sur bariloche",
    "inmobiliarias barrio este bariloche",
    "inmobiliarias barrio melipal bariloche",
    "inmobiliarias barrio las victorias bariloche",
    "inmobiliarias barrio villa los coihues bariloche",
    "inmobiliarias general roca rio negro",
    "inmobiliarias barrio centro general roca",
    "inmobiliarias viedma rio negro",
    "inmobiliarias barrio centro viedma",
    "inmobiliarias cipolletti rio negro",
    "inmobiliarias allen rio negro",
    "inmobiliarias villa regina rio negro",
    "inmobiliarias san antonio oeste rio negro",
    "inmobiliarias el bolson rio negro",
    "inmobiliarias barrio centro el bolson",
    "inmobiliarias lago puelo rio negro",
    "propiedades venta rio negro",
    "martilleros rio negro",

    # =========================================================================
    # SAN JUAN
    # =========================================================================
    "inmobiliarias san juan capital",
    "inmobiliarias barrio centro san juan",
    "inmobiliarias barrio norte san juan",
    "inmobiliarias barrio sur san juan capital",
    "inmobiliarias barrio este san juan capital",
    "inmobiliarias barrio chimbas san juan",
    "inmobiliarias barrio rivadavia san juan",
    "inmobiliarias barrio rawson san juan",
    "inmobiliarias barrio pocito san juan",
    "inmobiliarias barrio caucete san juan",
    "inmobiliarias barrio santa lucia san juan",
    "inmobiliarias barrio las flores san juan",
    "inmobiliarias barrio capital federal san juan",
    "inmobiliarias chimbas san juan",
    "inmobiliarias rawson san juan",
    "inmobiliarias pocito san juan",
    "inmobiliarias caucete san juan",
    "inmobiliarias media agua san juan",
    "inmobiliarias villa krause san juan",
    "propiedades venta san juan",
    "martilleros san juan",

    # =========================================================================
    # SAN LUIS
    # =========================================================================
    "inmobiliarias san luis capital",
    "inmobiliarias barrio centro san luis",
    "inmobiliarias barrio norte san luis",
    "inmobiliarias barrio sur san luis capital",
    "inmobiliarias barrio este san luis capital",
    "inmobiliarias barrio oeste san luis capital",
    "inmobiliarias barrio juan martin pueyrredon san luis",
    "inmobiliarias villa mercedes san luis",
    "inmobiliarias barrio centro villa mercedes",
    "inmobiliarias merlo san luis",
    "inmobiliarias barrio centro merlo san luis",
    "inmobiliarias barrio villa del carmen merlo san luis",
    "inmobiliarias potrero de los funes san luis",
    "inmobiliarias la punta san luis",
    "inmobiliarias juana koslay san luis",
    "propiedades venta san luis",
    "martilleros san luis",

    # =========================================================================
    # LA PAMPA
    # =========================================================================
    "inmobiliarias santa rosa la pampa",
    "inmobiliarias barrio centro santa rosa la pampa",
    "inmobiliarias barrio norte santa rosa la pampa",
    "inmobiliarias barrio sur santa rosa la pampa",
    "inmobiliarias general pico la pampa",
    "inmobiliarias barrio centro general pico la pampa",
    "inmobiliarias toay la pampa",
    "inmobiliarias realico la pampa",
    "inmobiliarias general acha la pampa",
    "inmobiliarias eduardo castex la pampa",
    "inmobiliarias victorica la pampa",
    "inmobiliarias macachín la pampa",
    "propiedades venta la pampa",
    "martilleros la pampa",

    # =========================================================================
    # JUJUY
    # =========================================================================
    "inmobiliarias san salvador de jujuy",
    "inmobiliarias barrio centro jujuy",
    "inmobiliarias barrio norte jujuy",
    "inmobiliarias barrio sur jujuy capital",
    "inmobiliarias barrio este jujuy capital",
    "inmobiliarias barrio alto comedero jujuy",
    "inmobiliarias barrio gorriti jujuy",
    "inmobiliarias barrio mariano moreno jujuy",
    "inmobiliarias barrio ciudad de nieva jujuy",
    "inmobiliarias palpalá jujuy",
    "inmobiliarias san pedro de jujuy",
    "inmobiliarias libertador general san martin jujuy",
    "inmobiliarias perico jujuy",
    "inmobiliarias humahuaca jujuy",
    "inmobiliarias tilcara jujuy",
    "inmobiliarias purmamarca jujuy",
    "propiedades venta jujuy",
    "martilleros jujuy",

    # =========================================================================
    # LA RIOJA
    # =========================================================================
    "inmobiliarias la rioja capital",
    "inmobiliarias barrio centro la rioja",
    "inmobiliarias barrio norte la rioja",
    "inmobiliarias barrio sur la rioja capital",
    "inmobiliarias barrio este la rioja capital",
    "inmobiliarias barrio oeste la rioja capital",
    "inmobiliarias barrio villa del parque la rioja",
    "inmobiliarias chilecito la rioja",
    "inmobiliarias barrio centro chilecito",
    "inmobiliarias aimogasta la rioja",
    "inmobiliarias chamical la rioja",
    "inmobiliarias villa union la rioja",
    "propiedades venta la rioja",
    "martilleros la rioja",

    # =========================================================================
    # CATAMARCA
    # =========================================================================
    "inmobiliarias san fernando del valle catamarca",
    "inmobiliarias barrio centro catamarca",
    "inmobiliarias barrio norte catamarca capital",
    "inmobiliarias barrio sur catamarca capital",
    "inmobiliarias barrio este catamarca capital",
    "inmobiliarias barrio oeste catamarca capital",
    "inmobiliarias barrio villa del carmen catamarca",
    "inmobiliarias andalgala catamarca",
    "inmobiliarias tinogasta catamarca",
    "inmobiliarias santa maria catamarca",
    "inmobiliarias belen catamarca",
    "inmobiliarias recreo catamarca",
    "propiedades venta catamarca",
    "martilleros catamarca",

    # =========================================================================
    # SANTIAGO DEL ESTERO
    # =========================================================================
    "inmobiliarias santiago del estero capital",
    "inmobiliarias barrio centro santiago del estero",
    "inmobiliarias barrio norte santiago del estero",
    "inmobiliarias barrio sur santiago del estero capital",
    "inmobiliarias barrio este santiago del estero capital",
    "inmobiliarias barrio villa del carmen santiago del estero",
    "inmobiliarias la banda santiago del estero",
    "inmobiliarias barrio centro la banda sgo del estero",
    "inmobiliarias termas de rio hondo santiago del estero",
    "inmobiliarias frías santiago del estero",
    "inmobiliarias añatuya santiago del estero",
    "inmobiliarias loreto santiago del estero",
    "inmobiliarias quimili santiago del estero",
    "propiedades venta santiago del estero",
    "martilleros santiago del estero",

    # =========================================================================
    # FORMOSA
    # =========================================================================
    "inmobiliarias formosa capital",
    "inmobiliarias barrio centro formosa",
    "inmobiliarias barrio norte formosa capital",
    "inmobiliarias barrio sur formosa capital",
    "inmobiliarias barrio este formosa capital",
    "inmobiliarias barrio nam qom formosa",
    "inmobiliarias clorinda formosa",
    "inmobiliarias pirané formosa",
    "inmobiliarias general lucio victorio mansilla formosa",
    "propiedades venta formosa",
    "martilleros formosa",

    # =========================================================================
    # CHUBUT
    # =========================================================================
    "inmobiliarias rawson chubut",
    "inmobiliarias trelew chubut",
    "inmobiliarias barrio centro trelew",
    "inmobiliarias barrio norte trelew",
    "inmobiliarias barrio sur trelew",
    "inmobiliarias comodoro rivadavia chubut",
    "inmobiliarias barrio centro comodoro rivadavia",
    "inmobiliarias barrio norte comodoro rivadavia",
    "inmobiliarias barrio sur comodoro rivadavia",
    "inmobiliarias barrio astra comodoro rivadavia",
    "inmobiliarias puerto madryn chubut",
    "inmobiliarias barrio centro puerto madryn",
    "inmobiliarias esquel chubut",
    "inmobiliarias barrio centro esquel",
    "inmobiliarias gaiman chubut",
    "inmobiliarias rada tilly chubut",
    "inmobiliarias sarmiento chubut",
    "propiedades venta chubut",
    "martilleros chubut",

    # =========================================================================
    # SANTA CRUZ
    # =========================================================================
    "inmobiliarias rio gallegos santa cruz",
    "inmobiliarias barrio centro rio gallegos",
    "inmobiliarias barrio norte rio gallegos",
    "inmobiliarias barrio sur rio gallegos",
    "inmobiliarias caleta olivia santa cruz",
    "inmobiliarias barrio centro caleta olivia",
    "inmobiliarias pico truncado santa cruz",
    "inmobiliarias puerto deseado santa cruz",
    "inmobiliarias las heras santa cruz",
    "inmobiliarias el calafate santa cruz",
    "inmobiliarias barrio centro el calafate",
    "inmobiliarias el chalten santa cruz",
    "propiedades venta santa cruz",
    "martilleros santa cruz",

    # =========================================================================
    # TIERRA DEL FUEGO
    # =========================================================================
    "inmobiliarias ushuaia tierra del fuego",
    "inmobiliarias barrio centro ushuaia",
    "inmobiliarias barrio norte ushuaia",
    "inmobiliarias barrio sur ushuaia",
    "inmobiliarias barrio bahia encerrada ushuaia",
    "inmobiliarias rio grande tierra del fuego",
    "inmobiliarias barrio centro rio grande",
    "inmobiliarias barrio norte rio grande tierra del fuego",
    "inmobiliarias tolhuin tierra del fuego",
    "propiedades venta tierra del fuego",
    "martilleros tierra del fuego",
]

# =============================================================================
# MAPA PROVINCIA — para inferir desde la query
# =============================================================================

_PROVINCIA_MAP = [
    ("tierra del fuego",           "Tierra del Fuego"),
    ("santiago del estero",        "Santiago del Estero"),
    ("entre rios",                 "Entre Ríos"),
    ("rio negro",                  "Río Negro"),
    ("la pampa",                   "La Pampa"),
    ("la rioja",                   "La Rioja"),
    ("san juan",                   "San Juan"),
    ("san luis",                   "San Luis"),
    ("santa cruz",                 "Santa Cruz"),
    ("santa fe",                   "Santa Fe"),
    ("caba",                       "Ciudad Autónoma de Buenos Aires"),
    ("capital federal",            "Ciudad Autónoma de Buenos Aires"),
    ("buenos aires",               "Buenos Aires"),
    ("cordoba",                    "Córdoba"),
    ("mendoza",                    "Mendoza"),
    ("tucuman",                    "Tucumán"),
    ("salta",                      "Salta"),
    ("corrientes",                 "Corrientes"),
    ("chaco",                      "Chaco"),
    ("misiones",                   "Misiones"),
    ("neuquen",                    "Neuquén"),
    ("jujuy",                      "Jujuy"),
    ("catamarca",                  "Catamarca"),
    ("formosa",                    "Formosa"),
    ("chubut",                     "Chubut"),
    ("rosario",                    "Santa Fe"),
    ("parana",                     "Entre Ríos"),
    ("resistencia",                "Chaco"),
    ("posadas",                    "Misiones"),
    ("bariloche",                  "Río Negro"),
    ("ushuaia",                    "Tierra del Fuego"),
    ("rio gallegos",               "Santa Cruz"),
    ("comodoro rivadavia",         "Chubut"),
    ("trelew",                     "Chubut"),
    ("rawson",                     "Chubut"),
    ("neuquen capital",            "Neuquén"),
]


def inferir_ubicacion(query: str) -> dict:
    """Infiere provincia, ciudad y barrio desde el texto de la query."""
    q = query.lower()
    provincia = ""
    barrio    = ""
    ciudad    = ""

    for clave, nombre in _PROVINCIA_MAP:
        if clave in q:
            provincia = nombre
            break

    if "barrio" in q:
        idx = q.find("barrio") + 6
        resto = q[idx:].strip()
        # Limpiar provincia y palabras comunes del resto
        for clave, _ in _PROVINCIA_MAP:
            resto = resto.replace(clave, "")
        for palabra in ["inmobiliarias", "propiedades", "venta", "alquiler",
                        "martilleros", "agencia", "capital"]:
            resto = resto.replace(palabra, "")
        barrio = " ".join(resto.split()).title()

    return {"provincia": provincia, "barrio": barrio, "ciudad": ciudad}


# =============================================================================
# CHECKPOINT
# =============================================================================

def cargar_checkpoint() -> int:
    try:
        with open(CHECKPOINT_FILE, "r") as f:
            return int(f.read().strip())
    except Exception:
        return 0


def guardar_checkpoint(idx: int):
    try:
        with open(CHECKPOINT_FILE, "w") as f:
            f.write(str(idx))
    except Exception as e:
        log(f"[WARN] No se pudo guardar checkpoint: {e}")


# =============================================================================
# UTILIDADES
# =============================================================================

def log(msg: str):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def random_delay(min_secs: float = 1.5, max_secs: float = 4.0):
    time.sleep(random.uniform(min_secs, max_secs))


def limpiar_texto(txt: str) -> str:
    if not txt:
        return ""
    return re.sub(r"\s+", " ", txt).strip()


def extraer_telefono(texto: str) -> str:
    """Extrae el primer teléfono argentino o internacional encontrado."""
    # Primero intenta formato argentino
    patron_ar = re.compile(
        r"(?:(?:\+|00)?54[\s\-]?)?(?:9[\s\-]?)?(?:\(0?\d{2,4}\)[\s\-]?|\d{2,4}[\s\-])"
        r"\d{3,4}[\s\-]?\d{3,4}"
    )
    match = patron_ar.search(texto)
    if match:
        return re.sub(r"[^\d+]", "", match.group())
    # Fallback: cualquier número de al menos 7 dígitos
    patron_gen = re.compile(r"[\+]?[\d\s\-\(\)]{7,15}")
    match = patron_gen.search(texto)
    if match:
        resultado = re.sub(r"[^\d+]", "", match.group())
        if len(resultado) >= 7:
            return resultado
    return ""


def limpiar_url(href: str) -> str:
    if not href:
        return ""
    href = href.strip()
    if "/url?q=" in href:
        try:
            parsed = urlparse(href)
            qs = parse_qs(parsed.query)
            real = qs.get("q", [None])[0]
            if real:
                href = unquote_plus(real)
        except Exception:
            return ""
    if href.startswith("//"):
        href = "https:" + href
    if not href.startswith("http"):
        return ""
    try:
        parsed = urlparse(href)
        return f"{parsed.scheme}://{parsed.netloc}{parsed.path}".rstrip("/")
    except Exception:
        return ""


# =============================================================================
# ALMACENAMIENTO
# =============================================================================

def guardar_csv(datos: dict):
    file_exists = os.path.isfile(CSV_FILE)
    try:
        with open(CSV_FILE, mode="a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
            if not file_exists:
                writer.writeheader()
                log(f"[CSV] Archivo creado: {os.path.abspath(CSV_FILE)}")
            writer.writerow({k: datos.get(k, "") for k in CSV_FIELDS})
    except Exception as e:
        log(f"   [ERROR-CSV] {e}")


def guardar_supabase(datos: dict):
    if not SUPABASE_URL or not SUPABASE_KEY:
        guardar_csv(datos)
        return

    body = {
        "nombre":             datos.get("nombre", "")     or None,
        "web":                datos.get("web", "")        or None,
        "telefono_principal": datos.get("telefono", "")   or None,
        "email_principal":    datos.get("email", "")      or None,
        "barrio":             datos.get("barrio", "")     or None,
        "ciudad":             datos.get("ciudad", "")     or None,
        "provincia":          datos.get("provincia", "")  or None,
        "pais":               datos.get("pais", "Argentina") or "Argentina",
        "categoria":          datos.get("categoria", "")  or None,
        "estado_scraping":    "ok",
        "ultimo_scrapeo":     datos.get("fecha_scrapeo", ""),
    }
    global _SUPA_SESSION
    payload = json.dumps(body)

    for intento in range(1, 4):
        try:
            r = _SUPA_SESSION.post(
                SUPABASE_ENDPOINT,
                headers=SUPABASE_HEADERS,
                data=payload,
                timeout=15,
            )
            if r.status_code in (200, 201, 204):
                log(f"   [SUPA-OK] {datos.get('nombre')}")
                return
            elif r.status_code == 409:
                # Conflicto de web: actualizar el registro existente por nombre
                nombre_enc = requests.utils.quote(body.get("nombre", ""), safe="")
                patch_url = f"{SUPABASE_URL}/rest/v1/{SUPABASE_TABLE}?nombre=eq.{nombre_enc}"
                patch_body = {k: v for k, v in body.items() if k != "nombre" and v is not None}
                r2 = _SUPA_SESSION.patch(
                    patch_url,
                    headers=SUPABASE_HEADERS,
                    data=json.dumps(patch_body),
                    timeout=15,
                )
                if r2.status_code in (200, 204):
                    log(f"   [SUPA-UPDATE] {datos.get('nombre')} (actualizado)")
                else:
                    log(f"   [SUPA-ERR] HTTP {r2.status_code}: {r2.text[:120]}")
                    guardar_csv(datos)
                return
            else:
                log(f"   [SUPA-ERR] HTTP {r.status_code}: {r.text[:120]}")
                guardar_csv(datos)
                return

        except Exception as e:
            espera = 2 ** intento
            log(f"   [SUPA-REINTENTO {intento}/3] {type(e).__name__}. Reintentando en {espera}s...")
            time.sleep(espera)
            # Recrear sesión en caso de conexión rota
            _SUPA_SESSION = _crear_sesion_supabase()

    log(f"   [SUPA-ERR] Falló tras 3 intentos. Usando CSV.")
    guardar_csv(datos)


def guardar(datos: dict):
    guardar_csv(datos)
    guardar_supabase(datos)


# =============================================================================
# SCROLL DEL PANEL
# =============================================================================

def scroll_panel_izquierdo(page, max_intentos: int = 30) -> int:
    log("[SCROLL] Cargando todos los resultados del panel...")
    items_anteriores = -1
    sin_cambio = 0

    for _ in range(max_intentos):
        items_actuales = contar_items(page)
        if items_actuales == items_anteriores:
            sin_cambio += 1
            if sin_cambio >= 3:
                log(f"[SCROLL] Sin cambios. Total: {items_actuales}")
                break
        else:
            sin_cambio = 0
            items_anteriores = items_actuales

        try:
            page.evaluate("""
                () => {
                    const sels = [
                        'div[role="main"] > div',
                        '#search > div > div',
                        'div[data-async-context]',
                        '#rcnt',
                    ];
                    for (const s of sels) {
                        const el = document.querySelector(s);
                        if (el && el.scrollHeight > el.clientHeight) {
                            el.scrollTop += 800; return;
                        }
                    }
                    window.scrollBy(0, 800);
                }
            """)
        except Exception:
            try:
                page.keyboard.press("End")
            except Exception:
                pass

        random_delay(0.8, 1.5)

        try:
            fin = page.locator(
                ":text('Has llegado al final'), :text('No hay mas resultados'), "
                ":text(\"You've reached the end\")"
            ).first
            if fin.is_visible(timeout=500):
                log("[SCROLL] Fin de resultados detectado.")
                break
        except Exception:
            pass

    return contar_items(page)


def contar_items(page) -> int:
    SELS = [
        "a.vwVdIc", "a.vwVdIc.wzN8Ac",
        "div.dbg0pd[role='heading']",
        "div[data-cid]", "div[role='article']",
        "a[href*='ludocid']",
    ]
    for sel in SELS:
        try:
            c = page.locator(sel).count()
            if c > 0:
                return c
        except Exception:
            continue
    return 0


# =============================================================================
# EXTRACCIÓN DE DATOS DEL PANEL DE DETALLE
# =============================================================================

_NOMBRES_INVALIDOS = {
    "resultados", "sin nombre", "sin título", "sin titulo",
    "google maps", "maps", "cerca", "negocios", "lugares",
}


def extraer_nombre(page) -> str:
    SELS = [
        "h1.DUwDvf",
        "h1.fontHeadlineLarge",
        "div[role='main'] h1",
        "h2.qrShPb span",
        "h1[data-attrid='title']",
        "h2[data-attrid='title'] span",
        "[role='heading'][aria-level='1']",
        "[role='heading'][aria-level='2'] span",
        "h1",
        "[jsaction*='pane.hero'] h1",
        "div[class*='fontHeadline'] h1",
        "div[class*='tAiQdd'] h1",
    ]
    for sel in SELS:
        try:
            loc = page.locator(sel).first
            if loc.is_visible(timeout=1500):
                txt = limpiar_texto(loc.inner_text())
                if txt and len(txt) > 1 and txt.lower() not in _NOMBRES_INVALIDOS:
                    return txt
        except Exception:
            continue

    # Fallback 1: extraer desde la URL de Google Maps
    try:
        url = page.url
        m = re.search(r"/maps/place/([^/@]+)", url)
        if m:
            nombre_url = unquote_plus(m.group(1)).replace("+", " ").strip()
            nombre_url = limpiar_texto(nombre_url)
            if nombre_url and len(nombre_url) > 1 and nombre_url.lower() not in _NOMBRES_INVALIDOS:
                return nombre_url
    except Exception:
        pass

    # Fallback 2: título de la pestaña
    try:
        titulo = page.title()
        if " - Google Maps" in titulo:
            nombre_titulo = titulo.replace(" - Google Maps", "").strip()
            nombre_titulo = limpiar_texto(nombre_titulo)
            if nombre_titulo and len(nombre_titulo) > 1 and nombre_titulo.lower() not in _NOMBRES_INVALIDOS:
                return nombre_titulo
    except Exception:
        pass

    return ""


def extraer_direccion(page) -> str:
    SELS = [
        "[data-item-id='address']",
        "button[data-item-id='address']",
        "[aria-label*='direcci']",
        "[aria-label*='irec']",
        "[data-tooltip*='irec']",
        "div[data-attrid='kc:/location/location:address'] span",
        "span[jsan*='address']",
    ]
    for sel in SELS:
        try:
            loc = page.locator(sel).first
            if loc.is_visible(timeout=1500):
                txt = limpiar_texto(
                    loc.inner_text() or loc.get_attribute("aria-label") or ""
                )
                if txt:
                    return txt
        except Exception:
            continue
    try:
        bloque = page.locator("div[data-item-id='address'], div[jsaction*='address']").first
        return limpiar_texto(bloque.inner_text())
    except Exception:
        return ""


def extraer_telefono_panel(page) -> str:
    SELS = [
        "[data-item-id*='phone']",
        "[aria-label*='eléfono']",
        "[aria-label*='elefono']",
        "[aria-label*='hone']",
        "button[data-item-id*='oh']",
    ]
    for sel in SELS:
        try:
            loc = page.locator(sel).first
            if loc.is_visible(timeout=1500):
                txt = loc.get_attribute("aria-label") or loc.inner_text() or ""
                tel = extraer_telefono(txt)
                if tel:
                    return tel
        except Exception:
            continue
    try:
        texto = page.locator("div[role='main']").first.inner_text()
        return extraer_telefono(texto)
    except Exception:
        return ""


def extraer_email(page) -> str:
    """Extrae el email del panel de detalles."""
    # Intentar link mailto: directo
    try:
        links = page.locator("a[href^='mailto:']").all()
        for link in links:
            href = link.get_attribute("href") or ""
            if href.startswith("mailto:"):
                email = href[7:].split("?")[0].strip()
                if "@" in email:
                    return email
    except Exception:
        pass

    # Intentar ítem de email en el panel
    SELS = [
        "[data-item-id*='email']",
        "[aria-label*='mail']",
        "[aria-label*='correo']",
    ]
    for sel in SELS:
        try:
            loc = page.locator(sel).first
            if loc.is_visible(timeout=1000):
                txt = loc.get_attribute("aria-label") or loc.inner_text() or ""
                if "@" in txt:
                    return txt.strip()
        except Exception:
            continue

    # Fallback: regex en todo el texto del panel
    try:
        texto = page.locator("div[role='main']").first.inner_text()
        match = re.search(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", texto)
        if match:
            return match.group()
    except Exception:
        pass
    return ""


def extraer_web(page) -> str:
    SELS = [
        "a[data-item-id='authority']",
        "a[aria-label*='itio web']",
        "a[aria-label*='ebsite']",
        "a.yYlJEf:has-text('Sitio web')",
        "a.yYlJEf.Q7PwXb:has-text('Sitio web')",
        "a[href*='http'][jsname]:not([href*='google'])",
    ]
    for sel in SELS:
        try:
            loc = page.locator(sel).first
            if loc.is_visible(timeout=2000):
                url = limpiar_url(loc.get_attribute("href") or "")
                if url and "google.com" not in url:
                    return url
        except Exception:
            continue
    try:
        links = page.locator("div[role='main'] a[href^='http']").all()
        for link in links:
            href = link.get_attribute("href") or ""
            if "google.com" not in href:
                url = limpiar_url(href)
                if url:
                    return url
    except Exception:
        pass
    return ""


def extraer_rating_resenas(page) -> tuple:
    rating, resenas = "", ""
    try:
        loc = page.locator(
            "span[aria-label*='stella'], span[aria-label*='star'], "
            "div[aria-label*='star'], div[aria-label*='stella']"
        ).first
        if loc.is_visible(timeout=1500):
            lbl = loc.get_attribute("aria-label") or ""
            m = re.search(r"[\d,\.]+", lbl)
            if m:
                rating = m.group().replace(",", ".")
    except Exception:
        pass
    try:
        loc = page.locator(
            "span[aria-label*='eseña'], span[aria-label*='eview'], "
            "button[aria-label*='eseña']"
        ).first
        if loc.is_visible(timeout=1000):
            lbl = loc.get_attribute("aria-label") or loc.inner_text() or ""
            m = re.search(r"[\d\.]+", lbl.replace(",", ""))
            if m:
                resenas = m.group()
    except Exception:
        pass
    return rating, resenas


def detectar_captcha(page) -> bool:
    """Detecta si Google está mostrando una página de verificación o CAPTCHA."""
    titulo = page.title().lower()
    if any(w in titulo for w in ["unusual traffic", "captcha", "verifica", "robot",
                                  "before you continue", "our systems"]):
        return True
    try:
        if page.locator(
            "form#captcha-form, div#captcha, iframe[src*='recaptcha'], "
            "div[id*='challenge'], #recaptcha"
        ).count() > 0:
            return True
    except Exception:
        pass
    return False


def extraer_categoria(page) -> str:
    SELS = [
        "button.DkEaL",
        "span.mgr77e",
        "div.fontBodyMedium.dmRWX",
        "button[jsaction*='category']",
        "[data-attrid*='category'] span",
    ]
    for sel in SELS:
        try:
            loc = page.locator(sel).first
            if loc.is_visible(timeout=1000):
                txt = limpiar_texto(loc.inner_text())
                if txt and len(txt) > 1:
                    return txt
        except Exception:
            continue
    return ""


def extraer_ciudad_de_direccion(direccion: str) -> str:
    """Intenta extraer la ciudad del string de dirección de Google Maps."""
    if not direccion:
        return ""
    # Google Maps suele formatear: "Calle 123, Ciudad, Provincia"
    partes = [p.strip() for p in direccion.split(",")]
    if len(partes) >= 2:
        # La ciudad suele estar en la penúltima o anteúltima parte
        for parte in reversed(partes[1:]):
            # Descartar códigos postales (solo números)
            parte_limpia = re.sub(r"\d", "", parte).strip()
            if len(parte_limpia) > 2:
                return parte.strip()
    return ""


# =============================================================================
# PROCESAMIENTO DE UN RESULTADO
# =============================================================================

def _volver_al_listado(page):
    """Vuelve al listado usando el botón interno de Google Maps."""
    if "/maps/place/" not in page.url:
        return
    SELS_BACK = [
        "button[aria-label='Volver']",
        "button[aria-label='Back']",
        "button[jsaction*='back']",
        "div[role='button'][aria-label*='olver']",
        "button.hjuVxf",
        "button.VfPpkd-icon-button",
        "[data-tooltip='Volver']",
        "[data-tooltip='Back']",
    ]
    for sel in SELS_BACK:
        try:
            btn = page.locator(sel).first
            if btn.is_visible(timeout=1500):
                btn.click(timeout=3000)
                try:
                    page.wait_for_selector("a.vwVdIc, div[data-cid]", timeout=5000)
                except Exception:
                    pass
                random_delay(0.8, 1.5)
                return
        except Exception:
            continue
    # Fallback: go_back del navegador
    try:
        page.go_back(wait_until="domcontentloaded", timeout=10000)
        try:
            page.wait_for_selector("a.vwVdIc, div[data-cid]", timeout=5000)
        except Exception:
            pass
        random_delay(1.0, 2.0)
    except Exception as e:
        log(f"   [WARN] go_back fallido: {e}")


def _nombre_desde_panel(item) -> str:
    """Extrae el nombre del item desde el panel sin clickear."""
    SELS_PANEL = [
        ".qBF1Pd",
        ".fontHeadlineSmall",
        "span[class*='fontHeadline']",
        "div[class*='fontHeadline']",
        ".NrDZNb",
        "span[jsan*='t_el']",
        "div[aria-label]",
    ]
    for sel in SELS_PANEL:
        try:
            loc = item.locator(sel).first
            txt = limpiar_texto(loc.inner_text())
            if txt and len(txt) > 1 and txt.lower() not in _NOMBRES_INVALIDOS:
                return txt
        except Exception:
            continue
    try:
        label = item.get_attribute("aria-label") or ""
        txt = limpiar_texto(label.split("\n")[0])
        if txt and len(txt) > 1 and txt.lower() not in _NOMBRES_INVALIDOS:
            return txt
    except Exception:
        pass
    return ""


def procesar_resultado(page, idx: int, total: int, vistos: set,
                       ubicacion_query: dict) -> dict | None:
    ITEM_SELS = [
        "a.vwVdIc", "a.vwVdIc.wzN8Ac",
        "div[data-cid]", "div[role='article']",
    ]
    item = None
    for sel in ITEM_SELS:
        try:
            items = page.locator(sel).all()
            if idx < len(items):
                item = items[idx]
                break
        except Exception:
            continue

    if not item:
        log(f"   [WARN] Item #{idx+1} no encontrado.")
        return None

    # Chequeo rápido de duplicado desde el panel (sin clickear)
    nombre_panel = _nombre_desde_panel(item)
    if nombre_panel:
        clave_panel = nombre_panel.lower().strip()
        if clave_panel in vistos:
            log(f"   [DUP-FAST] '{nombre_panel}' (salteado sin clickear)")
            return None

    url_antes = page.url

    for intento in range(3):
        try:
            item.scroll_into_view_if_needed(timeout=3000)
            random_delay(0.5, 1.0)
            item.click(timeout=5000)
            break
        except Exception as e:
            if intento == 2:
                log(f"   [WARN] Click fallido en #{idx+1}: {e}")
                return None
            random_delay(1, 2)

    # Esperar apertura del panel de detalle
    try:
        page.wait_for_url("**/maps/place/**", timeout=8000)
    except PlaywrightTimeoutError:
        for sel_det in ["h1.DUwDvf", "h1.fontHeadlineLarge", "div[role='main'] h1"]:
            try:
                page.wait_for_selector(sel_det, timeout=4000)
                break
            except Exception:
                continue

    # Si la URL no cambió, el click no navegó
    if page.url == url_antes:
        log(f"   [SKIP] #{idx+1}: click no navegó.")
        return None

    random_delay(1.5, 3.0)

    nombre = extraer_nombre(page)
    if not nombre:
        page.wait_for_timeout(2000)
        nombre = extraer_nombre(page)
    if not nombre:
        log(f"   [SKIP] #{idx+1}: nombre vacío.")
        _volver_al_listado(page)
        return None

    clave = nombre.lower().strip()
    if clave in vistos:
        log(f"   [DUP] '{nombre}'")
        _volver_al_listado(page)
        return None
    vistos.add(clave)

    direccion = extraer_direccion(page)
    telefono  = extraer_telefono_panel(page)
    email     = extraer_email(page)
    web       = extraer_web(page)
    rating, resenas = extraer_rating_resenas(page)
    categoria = extraer_categoria(page)

    if web:
        clave_web = web.lower().rstrip("/")
        if clave_web in vistos:
            log(f"   [DUP-WEB] '{web}'")
            _volver_al_listado(page)
            return "DUP"
        vistos.add(clave_web)

    # Ciudad: primero desde dirección, luego desde query
    ciudad = extraer_ciudad_de_direccion(direccion) or ubicacion_query.get("ciudad", "")
    # Barrio: desde query (si la query era por barrio específico)
    barrio = ubicacion_query.get("barrio", "")

    datos = {
        "nombre":        nombre,
        "direccion":     direccion,
        "barrio":        barrio,
        "ciudad":        ciudad,
        "provincia":     ubicacion_query.get("provincia", ""),
        "pais":          "Argentina",
        "telefono":      telefono,
        "email":         email,
        "web":           web,
        "rating":        rating,
        "resenas":       resenas,
        "categoria":     categoria,
        "fuente":        "google_lugares",
        "fecha_scrapeo": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

    log(
        f"   [{idx+1}/{total}] {nombre} | "
        f"tel={telefono or '-'} | email={email or '-'} | "
        f"web={web or '-'} | cat={categoria or '-'} | {ubicacion_query.get('provincia','')}"
    )

    _volver_al_listado(page)
    return datos


# =============================================================================
# SCRAPER PRINCIPAL DE UNA QUERY
# =============================================================================

def scrapear_query(page, query: str, vistos: set) -> int:
    url = GOOGLE_LUGARES_URL.format(query=query.replace(" ", "+"))
    log(f"\n[QUERY] '{query}'")
    log(f"[URL]   {url}")

    ubicacion_query = inferir_ubicacion(query)

    try:
        page.goto(url, wait_until="domcontentloaded", timeout=25000)
        try:
            page.wait_for_load_state("networkidle", timeout=10000)
        except Exception:
            pass
        random_delay(2, 4)
    except PlaywrightTimeoutError:
        log(f"[ERROR] Timeout: {url}")
        return 0
    except Exception as e:
        log(f"[ERROR] {e}")
        return 0

    # Aceptar cookies
    try:
        btn = page.locator(
            "button:has-text('Aceptar todo'), button:has-text('Accept all'), "
            "button:has-text('Aceptar'), button[aria-label*='Accept']"
        ).first
        if btn.is_visible(timeout=4000):
            btn.click()
            log("[INFO] Cookies aceptadas.")
            random_delay(1.5, 2.5)
    except Exception:
        pass

    log(f"[INFO] Título: {page.title()[:65]}")

    if detectar_captcha(page):
        log("[CAPTCHA] Google está pidiendo verificación. Pausando 90 segundos...")
        log("[CAPTCHA] Resolvé el CAPTCHA manualmente en el navegador y esperá.")
        try:
            path = os.path.join(script_dir, "..", "debug_captcha.png")
            page.screenshot(path=path)
            log(f"[CAPTCHA] Screenshot: {os.path.abspath(path)}")
        except Exception:
            pass
        time.sleep(90)
        if detectar_captcha(page):
            log("[CAPTCHA] Sigue bloqueado. Saltando query.")
            return 0

    total_items = scroll_panel_izquierdo(page)
    log(f"[INFO] Items detectados: {total_items}")

    if total_items == 0:
        log("[WARN] Sin items. Guardando screenshot de diagnóstico.")
        try:
            path = os.path.join(script_dir, "..", "debug_screenshot.png")
            page.screenshot(path=path)
        except Exception:
            pass
        return 0

    guardados = 0
    dups_consecutivos = 0
    for idx in range(total_items):
        try:
            datos = procesar_resultado(page, idx, total_items, vistos, ubicacion_query)
            if datos == "DUP":
                dups_consecutivos += 1
                if dups_consecutivos >= 2:
                    log(f"   [CORTE] 2 duplicados consecutivos — pasando a la siguiente query.")
                    break
                random_delay(2, 4)
                continue
            dups_consecutivos = 0
            if datos:
                guardar(datos)
                guardados += 1
            random_delay(2, 4)
        except Exception as e:
            log(f"   [ERROR] Item #{idx+1}: {e}")
            continue

    return guardados


# =============================================================================
# MAIN
# =============================================================================

def main():
    log("=" * 65)
    log("SCRAPER GOOGLE LUGARES — Argentina completa")
    log(f"Supabase : {SUPABASE_ENDPOINT}")
    log(f"CSV      : {os.path.abspath(CSV_FILE)}")
    log(f"Stealth  : {'ACTIVADO' if STEALTH_AVAILABLE else 'NO disponible'}")
    log(f"Queries  : {len(QUERIES)}")
    log("=" * 65)

    inicio = cargar_checkpoint()
    if inicio > 0:
        log(f"[CHECKPOINT] Retomando desde query #{inicio + 1} de {len(QUERIES)}")
    else:
        log("[CHECKPOINT] Empezando desde el inicio.")

    vistos: set = set()

    with sync_playwright() as p:
        browser = None
        try:
            browser = p.chromium.launch(
                headless=False,
                args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
            )
            context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1400, "height": 900},
                locale="es-AR",
                device_scale_factor=1,
                is_mobile=False,
            )
            page = context.new_page()

            if STEALTH_AVAILABLE:
                stealth_sync(page)
                log("[INFO] Stealth aplicado.")

            page.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                window.chrome = { runtime: {} };
            """)

            total_global = 0
            for i, query in enumerate(QUERIES, start=1):
                if i - 1 < inicio:
                    continue
                log(f"\n[{i}/{len(QUERIES)}] '{query}'")
                try:
                    guardados = scrapear_query(page, query, vistos)
                    total_global += guardados
                    log(f"[FIN-QUERY] {guardados} nuevos | acumulado: {total_global}")
                except Exception as e:
                    log(f"[ERROR-QUERY] {e}")
                    log(traceback.format_exc())
                guardar_checkpoint(i)
                if i < len(QUERIES):
                    random_delay(4, 8)

            log(f"\n{'='*65}")
            log(f"[COMPLETADO] Total guardados: {total_global}")
            log(f"CSV: {os.path.abspath(CSV_FILE)}")
            log("=" * 65)

        except Exception as e:
            log(f"[ERROR FATAL] {e}")
            log(traceback.format_exc())
        finally:
            if browser:
                try:
                    browser.close()
                    log("[INFO] Navegador cerrado.")
                except Exception:
                    pass


if __name__ == "__main__":
    main()
