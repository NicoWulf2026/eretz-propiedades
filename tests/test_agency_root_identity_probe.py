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


def test_el_host_que_indexa_inmobiliarias_enlaza_a_las_hermanas():
    """`lujanprop.com.ar/inmobiliaria/arte` convive en el host con
    `/inmobiliaria/46`, `/27` y `/33`: está organizado por inmobiliaria y la
    url cargada es una entrada de esa lista, no un sitio."""
    from scripts.agency_root_identity_probe import hermanos_de_perfil

    html = ('<a href="/inmobiliaria/46">A</a><a href="/inmobiliaria/27">B</a>'
            '<a href="/inmobiliaria/33">C</a><a href="/inmobiliaria/arte">yo</a>')
    assert hermanos_de_perfil(html, "/inmobiliaria/arte") == ["27", "33", "46"]


def test_las_secciones_del_sitio_propio_no_son_hermanas():
    """`cuno.com.ar/Venta` tiene `/Alquiler` y `/Contacto` al lado, que son
    secciones de su propio sitio. Se exige profundidad dos: el último tramo
    tiene que ser un item ADENTRO de una colección nombrada."""
    from scripts.agency_root_identity_probe import hermanos_de_perfil

    propio = ('<a href="/Alquiler">x</a><a href="/Contacto">y</a>'
              '<a href="/Nosotros">z</a>')
    assert hermanos_de_perfil(propio, "/Venta") == []


def test_una_coleccion_de_otra_profundidad_no_cuenta():
    """Las fichas de propiedades de un sitio propio cuelgan de un prefijo
    distinto: `/propiedad/123` no es hermana de `/inmobiliaria/arte`."""
    from scripts.agency_root_identity_probe import hermanos_de_perfil

    html = ('<a href="/propiedad/123">a</a><a href="/propiedad/124">b</a>'
            '<a href="/propiedad/125">c</a>')
    assert hermanos_de_perfil(html, "/inmobiliaria/arte") == []


def test_solo_cuentan_las_hermanas_cuando_el_sitio_dice_que_son_inmobiliarias():
    """Contar hermanas sin mirar la palabra confunde tres cosas: hermanas que
    son agencias -la evidencia-, hermanas que son propiedades -que tiene
    cualquier sitio propio- y hermanas que son secciones del sitio."""
    from scripts.agency_root_identity_probe import indexa_inmobiliarias

    assert indexa_inmobiliarias("/inmobiliaria/arte", ["46", "27", "33"])
    assert indexa_inmobiliarias("/cordoba/inmobiliarias/kunze",
                                ["boiago", "contigiani", "hosteria"])
    # Las fichas de propiedades de un sitio propio no prueban nada.
    assert not indexa_inmobiliarias(
        "/propiedades/516284-x", ["516285-y", "516286-z", "516287-w"])
    # Ni las secciones del sitio.
    assert not indexa_inmobiliarias(
        "/portal/agency_profile", ["home", "search", "favorites"])


def test_la_paginacion_de_un_perfil_no_son_hermanas():
    """`infocasas` numera las páginas del MISMO perfil: `.../pagina44`. Contadas
    como hermanas, el perfil se delataría a sí mismo."""
    from scripts.agency_root_identity_probe import indexa_inmobiliarias

    assert not indexa_inmobiliarias("/inmobiliarias/caetano",
                                    ["pagina44", "pagina45", "pagina46"])
