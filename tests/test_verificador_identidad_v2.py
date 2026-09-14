# -*- coding: utf-8 -*-
"""Los once falsos positivos del canario, convertidos en reglas.

Cada test nombra un caso real del canario del 2026-09-14, pero lo que fija es
la REGLA general, no el dominio: el fixture describe un sitio con cierta forma,
y la regla lo rechaza por esa forma. Si mañana otro fabricante de butacas se
llama como una inmobiliaria, tiene que fallar igual.

La asimetría que ordena todo el archivo: un falso negativo cuesta una búsqueda
más; un falso positivo le asigna a una inmobiliaria el catálogo de otra.
"""
import pytest

from scripts.verificador_identidad_v2 import (
    BUSINESS_DIRECTORY, EXTERNAL_PORTAL, EXTERNAL_PORTAL_PROFILE,
    IDENTITY_AMBIGUOUS, NETWORK_DIRECTORY, NETWORK_OFFICE_PAGE, NEWS_MEDIA,
    OFFICIAL_OFFICE_PAGE, OFFICIAL_WEB, PARKED_DOMAIN, PROPERTY_DETAIL_PAGE,
    REAL_ESTATE_OFFICIAL_SITE, REVIEW_REQUIRED, UNRELATED_BUSINESS, ALTA,
    Sitio, clasificar_sitio, tokens_distintivos, verificar)

RUBRO = ("Propiedades en venta y alquiler. Tasaciones sin cargo. "
         "Inmobiliaria con matricula. Departamentos, casas y terrenos. "
         "Contacto: nuestra oficina en Buenos Aires, Argentina.")


def agencia(nombre, zonas=(), matricula=()):
    return {"nombre_original": nombre, "zonas_observadas": list(zonas),
            "matricula": list(matricula)}


def sitio(url, titulo="", texto=RUBRO, http=200):
    return Sitio(url=url, titulo=titulo, texto=texto, http=http)


# --- A: el sitio tiene que ser del rubro (§4) ---------------------------

def test_un_fabricante_de_butacas_no_es_una_inmobiliaria():
    """`Cerullo Propiedades` -> cerullo.com, que fabrica butacas.

    V1 lo aceptaba porque el dominio contiene 'cerullo'. La regla nueva mira
    primero de que habla la pagina.
    """
    s = sitio("https://www.cerullo.com/", "Cerullo Seats",
              "Cerullo Seats. Fabricamos asientos y butacas para cines y "
              "auditorios desde 1960. Nuestra planta produce mas de mil "
              "unidades por mes para toda la region.")
    assert clasificar_sitio(s) == UNRELATED_BUSINESS
    v = verificar(agencia("Cerullo Propiedades"), [s])
    assert v.clase != OFFICIAL_WEB


def test_una_consultora_de_estrategia_tampoco():
    """`BTS Propiedades` -> bts.com, 'Strategy made personal'."""
    s = sitio("https://bts.com", "BTS | Strategy made personal",
              "BTS is a consulting firm. We help leaders align strategy and "
              "culture. Our consulting practice works with global clients on "
              "transformation and leadership development programs.")
    assert clasificar_sitio(s) == UNRELATED_BUSINESS
    assert verificar(agencia("BTS Propiedades"), [s]).clase != OFFICIAL_WEB


def test_un_sitio_del_rubro_si_pasa_el_primer_filtro():
    s = sitio("https://blancopropiedades.com/",
              "Blanco Propiedades | Inmobiliaria en Pilar")
    assert clasificar_sitio(s) == REAL_ESTATE_OFFICIAL_SITE


# --- B: dominios parkeados (§6) -----------------------------------------

def test_un_dominio_con_prefijo_de_parking_no_es_un_sitio():
    """`Genzano` -> ww16.genzano.com/?sub1=... HTTP 200 y no es un sitio."""
    s = sitio("http://ww16.genzano.com/?sub1=20260915-0546", "genzano.com",
              "Related searches. Buy this domain.")
    assert clasificar_sitio(s) == PARKED_DOMAIN
    assert verificar(agencia("Genzano Propiedades"), [s]).clase != OFFICIAL_WEB


def test_una_pagina_sin_texto_no_es_un_sitio():
    """`Mizrahi Real Estate` -> mizrahi.com devolvia su propio dominio."""
    s = sitio("https://mizrahi.com", "mizrahi.com", "mizrahi.com")
    assert clasificar_sitio(s) == PARKED_DOMAIN


def test_el_parking_se_detecta_tambien_por_el_texto():
    """Sin prefijo raro, pero la pagina se ofrece en venta."""
    s = sitio("https://ejemplo-inmobiliaria.com.ar", "ejemplo",
              "This domain is for sale. Related searches: propiedades, "
              "inmobiliaria, venta, alquiler, tasaciones, departamentos.")
    assert clasificar_sitio(s) == PARKED_DOMAIN


# --- C: directorios y medios (§5) ---------------------------------------

def test_un_buscador_de_cuit_no_es_la_web_de_la_inmobiliaria():
    """`Florencia Brandolin` -> cuitonline.com/detalle/..."""
    s = sitio("https://www.cuitonline.com/detalle/24229233854/brandolin.html",
              "Brandolin Florencia - CUIT", RUBRO)
    assert clasificar_sitio(s) == BUSINESS_DIRECTORY
    assert verificar(agencia("Florencia Brandolin Propiedades"), [s]).clase != OFFICIAL_WEB


def test_una_nota_de_diario_no_es_la_web_de_la_inmobiliaria():
    """`Coldwell Banker Paraguay` -> lanacion.com.py/negocios/..."""
    s = sitio("https://www.lanacion.com.py/negocios/2023/04/01/coldwell-banker",
              "Coldwell Banker desembarca en Paraguay", RUBRO)
    assert clasificar_sitio(s) == NEWS_MEDIA
    assert verificar(agencia("Coldwell Banker Paraguay"), [s]).clase != OFFICIAL_WEB


# --- D: portales y fichas (§5) ------------------------------------------

def test_un_perfil_en_un_portal_no_es_web_propia():
    """`Sol Llabres - DTS` -> puntoclick.com.ar/empresa/..."""
    s = sitio("https://puntoclick.com.ar/empresa/sol-llabres-dts-propiedades",
              "Sol Llabres DTS en Puntoclick", RUBRO)
    assert clasificar_sitio(s) == EXTERNAL_PORTAL
    v = verificar(agencia("Sol Llabres - DTS Propiedades"), [s])
    assert v.clase == EXTERNAL_PORTAL_PROFILE
    assert v.clase != OFFICIAL_WEB


def test_una_ficha_de_propiedad_en_un_portal_tampoco():
    """`RE/MAX GO` -> inmoup.com.ar/113747-re-max-go/inmuebles/2178/ficha/..."""
    s = sitio("https://inmoup.com.ar/113747-re-max-go/inmuebles/2178/ficha/oficina",
              "Oficina en venta", RUBRO)
    assert clasificar_sitio(s) == PROPERTY_DETAIL_PAGE
    assert verificar(agencia("RE/MAX GO"), [s]).clase != OFFICIAL_WEB


def test_un_agregador_desconocido_se_detecta_por_su_forma():
    """No por su host: por listar muchas inmobiliarias distintas."""
    muchas = " ".join(f"{n} Propiedades es una inmobiliaria de la zona."
                      for n in ("Alfa", "Beta", "Gamma", "Delta", "Epsilon", "Zeta"))
    s = sitio("https://portal-desconocido.com.ar/", "Guia", muchas + RUBRO)
    assert clasificar_sitio(s) in (EXTERNAL_PORTAL, PROPERTY_DETAIL_PAGE)


# --- E: redes y oficinas (§7) -------------------------------------------

def test_el_directorio_de_la_red_no_es_la_pagina_de_una_oficina():
    """Cinco oficinas del canario apuntaban a century21.com.ar/directorio."""
    s = sitio("https://century21.com.ar/directorio?orden=desc",
              "Directorio de oficinas Century 21", RUBRO)
    assert clasificar_sitio(s) == NETWORK_DIRECTORY
    v = verificar(agencia("Century 21 MM Real Estate"), [s])
    assert v.clase != OFFICIAL_OFFICE_PAGE


def test_la_pagina_que_nombra_a_la_oficina_si_vale():
    """`Remax Roble` -> remax.com.ar/roble."""
    s = sitio("https://www.remax.com.ar/roble", "RE/MAX Roble", RUBRO)
    assert clasificar_sitio(s) == NETWORK_OFFICE_PAGE
    v = verificar(agencia("Remax Roble"), [s])
    assert v.clase == OFFICIAL_OFFICE_PAGE
    assert v.confianza == ALTA


def test_una_oficina_de_la_red_en_otro_dominio_de_la_red_tambien():
    """`RE/MAX Premium` -> global.remax.com/en/offices/argentina/.../remax-premium/42."""
    s = sitio("https://global.remax.com/en/offices/argentina/palermo/remax-premium/42",
              "RE/MAX Premium - Palermo Nuevo", RUBRO)
    v = verificar(agencia("RE/MAX Premium", zonas=["palermo"]), [s])
    assert v.clase == OFFICIAL_OFFICE_PAGE


def test_la_pagina_de_OTRA_oficina_de_la_misma_red_no_vale():
    """`RE/MAX Estudio` -> remax-urbana.com.ar, que es otra oficina.

    El token distintivo separa una oficina de otra: 'estudio' no esta en
    'urbana'. Sin esto, cualquier pagina de la red satisface a cualquier
    oficina de la red.
    """
    s = sitio("https://www.remax-urbana.com.ar/", "RE/MAX Urbana", RUBRO)
    v = verificar(agencia("RE/MAX Estudio"), [s])
    assert v.clase != OFFICIAL_WEB
    assert v.clase != OFFICIAL_OFFICE_PAGE


# --- F: pais (§8) -------------------------------------------------------

def test_una_oficina_uruguaya_no_satisface_a_una_agencia_argentina():
    """`RE/MAX Focus` -> remax.com.uy/agent/martin-diaz-pintos."""
    s = sitio("https://www.remax.com.uy/agent/martin-diaz-pintos",
              "Martin Diaz Pintos - RE/MAX Uruguay",
              "Propiedades en venta y alquiler en Montevideo y Punta del Este, "
              "Uruguay. Tasaciones. Inmobiliaria. Telefono +598 99 123 456.")
    v = verificar(agencia("RE/MAX Focus", zonas=["capital federal"]), [s])
    assert v.clase not in (OFFICIAL_WEB, OFFICIAL_OFFICE_PAGE)


def test_el_listado_general_de_la_red_en_otro_pais_tampoco():
    """`RE/MAX REAL` -> remax.com.uy/listings/buy?page=0."""
    s = sitio("https://www.remax.com.uy/listings/buy?page=0",
              "Propiedades en venta - RE/MAX Uruguay",
              "Inmobiliaria en Montevideo, Uruguay. Propiedades en venta y "
              "alquiler en Punta del Este, Maldonado y Canelones. Tasaciones "
              "sin cargo. Departamentos, casas y terrenos. Telefono +598 2 "
              "600 0000. Nuestras oficinas en todo el pais.")
    assert clasificar_sitio(s) == NETWORK_DIRECTORY
    assert verificar(agencia("RE/MAX REAL"), [s]).clase != OFFICIAL_WEB


# --- G: identidad cruzada (§9) ------------------------------------------

def test_el_sitio_de_otra_inmobiliaria_no_vale_aunque_te_nombre():
    """`REMAX RAICES` -> aspenbienesraices.com.ar/inmobiliaria/remax-raices/.

    Es el error mas caro: le asigna a una inmobiliaria el catalogo de otra.
    """
    s = sitio("https://aspenbienesraices.com.ar/inmobiliaria/remax-raices/",
              "Aspen Bienes Raices",
              "Aspen Propiedades es una inmobiliaria de Mendoza. "
              "Tambien listamos a Remax Raices Inmobiliaria. " + RUBRO)
    v = verificar(agencia("REMAX RAICES"), [s])
    assert v.clase != OFFICIAL_WEB


# --- H: evidencia minima segun el nombre (§10) --------------------------

def test_un_nombre_generico_exige_dos_evidencias():
    """Un solo token comun no distingue: hace falta zona o matricula."""
    s = sitio("https://centro.com.ar/", "Centro", RUBRO)
    v = verificar(agencia("Inmobiliaria Centro"), [s])
    assert v.clase != OFFICIAL_WEB


def test_un_nombre_generico_con_zona_coincidente_si_cierra():
    s = sitio("https://centroquilmes.com.ar/", "Inmobiliaria Centro Quilmes",
              RUBRO + " Estamos en Quilmes hace treinta anios.")
    v = verificar(agencia("Inmobiliaria Centro", zonas=["quilmes"]), [s])
    assert v.clase == OFFICIAL_WEB


def test_un_nombre_distintivo_cierra_con_una_evidencia():
    s = sitio("https://blancopropiedades.com/",
              "Blanco Propiedades | Inmobiliaria en Pilar", RUBRO)
    v = verificar(agencia("Blanco Propiedades", zonas=["pilar"]), [s])
    assert v.clase == OFFICIAL_WEB
    assert v.confianza == ALTA


# --- I: los tokens distinguen oficinas de la misma red ------------------

@pytest.mark.parametrize("nombre,esperado", [
    ("RE/MAX Focus", {"focus"}),
    ("Century 21 MM Real Estate", {"mm"}),
    ("Remax Roble", {"roble"}),
    ("Blanco Propiedades", {"blanco"}),
    ("Inmobiliaria Centro", {"centro"}),
])
def test_los_tokens_sacan_la_red_y_el_rubro(nombre, esperado):
    assert tokens_distintivos(nombre) == esperado


# --- J: sin candidata legible no se inventa nada ------------------------

def test_una_candidata_que_no_responde_no_resuelve_nada():
    v = verificar(agencia("Cualquiera Propiedades"),
                  [Sitio(url="https://no-responde.com.ar", http=None)])
    assert v.clase not in (OFFICIAL_WEB, OFFICIAL_OFFICE_PAGE)


def test_sin_candidatas_no_hay_veredicto_positivo():
    v = verificar(agencia("Cualquiera Propiedades"), [])
    assert v.clase not in (OFFICIAL_WEB, OFFICIAL_OFFICE_PAGE)


# --- K: la ruta que enumera terceros (canario V2) -----------------------

@pytest.mark.parametrize("url,caso", [
    ("https://www.gopunta.uy/inmobiliarias/beba-paez-vilaro-20/pagina",
     "portal uruguayo con seccion de inmobiliarias"),
    ("https://www.infocasas.com.uy/inmobiliarias/perfil/1712",
     "perfil dentro de un portal"),
    ("https://www.bullano.com.ar/anunciantes/tienda/SITUAR-REALTY",
     "tienda de un anunciante en un marketplace"),
    ("https://puntoclick.com.ar/empresa/sol-llabres-dts-propiedades",
     "empresa dentro de un portal"),
])
def test_un_host_con_seccion_de_terceros_no_es_una_inmobiliaria(url, caso):
    """Los cuatro salieron del canario V2 y no comparten host.

    Lo que comparten es la forma: la ruta enumera terceros. Un sitio que tiene
    una seccion de 'inmobiliarias' o de 'anunciantes' no es una inmobiliaria,
    es donde varias se publican. La regla reemplaza media lista negra.
    """
    s = sitio(url, "x")
    assert clasificar_sitio(s) in (EXTERNAL_PORTAL, PROPERTY_DETAIL_PAGE), caso


def test_una_nota_se_reconoce_por_la_ruta_aunque_el_medio_no_este_en_la_lista():
    """`Remax Roble` -> 0221.com.ar/nota/2022-1-11-..., un diario de La Plata
    que no figura en ninguna lista de medios."""
    s = sitio("https://www.0221.com.ar/nota/2022-1-11-10-45-0-re-max-roble", "x")
    assert clasificar_sitio(s) == NEWS_MEDIA


def test_la_regla_no_se_come_un_sitio_propio_con_ruta_parecida():
    """`/propiedades/` en el sitio propio NO es una seccion de terceros."""
    s = sitio("https://blancopropiedades.com/propiedades/casas", "Blanco")
    assert clasificar_sitio(s) == REAL_ESTATE_OFFICIAL_SITE


def test_un_2xx_con_cuerpo_vacio_es_un_desafio_no_un_dominio_parkeado():
    """`global.remax.com` y `remax.com.ar` devuelven 202 con cero bytes.

    La pagina existe y probablemente es correcta; lo que falta es un navegador
    que ejecute el desafio. Llamarlas parkeadas descartaba 100 oficinas con
    20.919 avisos, el grupo de mayor inventario del universo.
    """
    s = Sitio(url="https://www.remax.com.ar/titanium", titulo="", texto="",
              http=202, html_bytes=0)
    assert clasificar_sitio(s) != PARKED_DOMAIN
    v = verificar(agencia("RE/MAX TITANIUM"), [s])
    assert v.clase not in (OFFICIAL_WEB, OFFICIAL_OFFICE_PAGE)


def test_pero_un_2xx_con_poco_html_y_poco_texto_si_es_parkeado():
    """La distincion es el tamanyo del HTML, no la ausencia de texto."""
    s = Sitio(url="https://mizrahi.com", titulo="mizrahi.com",
              texto="mizrahi.com", http=200, html_bytes=2048)
    assert clasificar_sitio(s) == PARKED_DOMAIN
