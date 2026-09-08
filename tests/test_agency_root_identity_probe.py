"""Que la raiz del host decida de quien es el sitio, y no la forma de la url."""
from scripts.agency_root_identity_probe import (candidatas, nombre_nucleo,
                                                presentacion, se_presenta_como)


def test_el_sitio_propio_se_presenta_con_su_nombre():
    """`DBJ Propiedades` publica en `dbj.com.ar`: la marca es una sigla de tres
    letras y ninguna regla sobre el dominio la reconoce. La raíz sí."""
    dicho = presentacion("<title>DBJ Propiedades | Inmobiliaria en Rosario</title>")
    assert se_presenta_como("DBJ Propiedades", dicho) == "dbj propiedades"


def test_el_portal_se_presenta_como_el_portal():
    """`lujanprop.com.ar/inmobiliaria/arte` es el perfil de ARTE en un portal.
    La raíz del portal se titula con el nombre del portal, no con el de ninguna
    de las inmobiliarias que lista."""
    dicho = presentacion(
        "<title>LujanProp - Portal inmobiliario de Luján</title>"
        "<h1>Encontrá tu propiedad</h1>")
    assert se_presenta_como("ARTE PROPIEDADES", dicho) is None


def test_la_pagina_de_perfil_no_sirve_de_evidencia():
    """La página profunda SÍ dice el nombre de la inmobiliaria -para eso es-,
    y por eso no distingue el sitio propio del portal que la lista. Es la razón
    de mirar la raíz: acá el mismo texto daría un falso positivo."""
    perfil = presentacion("<title>Arte Propiedades - LujanProp</title>")
    assert se_presenta_como("ARTE PROPIEDADES", perfil) == "arte propiedades"


def test_una_palabra_corta_del_nombre_no_alcanza():
    """`ARTE PROPIEDADES` sin genéricas queda en "arte", que aparece adentro de
    cualquier cosa. El núcleo solo cuenta cuando es una marca, no una palabra."""
    assert nombre_nucleo("ARTE PROPIEDADES") == "arte"
    assert se_presenta_como("ARTE PROPIEDADES",
                            presentacion("<title>Estilo Arte</title>")) is None
    # Con una marca de verdad, el núcleo solo sí alcanza: el sitio se titula con
    # la marca y omite la palabra genérica.
    assert se_presenta_como("Vanzini Propiedades",
                            presentacion("<title>Vanzini</title>")) == "vanzini"
    assert se_presenta_como("Zaputovich Propiedades",
                            presentacion("<title>Zaputovich</title>")) == "zaputovich"


def test_no_se_pregunta_a_quien_ya_tiene_su_nombre_en_el_dominio():
    """Preguntar de más cuesta una petición y arriesga cerrar mal a quien ya
    está demostrado. Y una url que ya es la raíz no tiene ambigüedad."""
    filas = [
        {"canonical_agency_id": "a", "agency_name": "Vanzini Propiedades",
         "domain": "https://www.vanzini.com.ar/feed", "web_kind": "OFFICIAL_WEB"},
        {"canonical_agency_id": "b", "agency_name": "ARTE PROPIEDADES",
         "domain": "https://lujanprop.com.ar/inmobiliaria/arte",
         "web_kind": "OFFICIAL_WEB"},
        {"canonical_agency_id": "c", "agency_name": "Otra",
         "domain": "https://otra.com.ar/", "web_kind": "OFFICIAL_WEB"},
        {"canonical_agency_id": "d", "agency_name": "Ya clasificada",
         "domain": "https://zonaprop.com.ar/x/y", "web_kind": "EXTERNAL_PORTAL_PROFILE"},
    ]
    assert [f["canonical_agency_id"] for f in candidatas(filas)] == ["b"]


def test_la_presentacion_no_lee_el_cuerpo_entero():
    """Un portal menciona a todas las inmobiliarias que lista en su cuerpo. Si
    la evidencia fuera el HTML entero, cada una de ellas daría positivo."""
    dicho = presentacion(
        "<title>LujanProp</title><body><ul>"
        "<li>Arte Propiedades</li><li>Otra Propiedades</li></ul></body>")
    assert "Arte Propiedades" not in dicho
    assert se_presenta_como("Arte Propiedades", dicho) is None
