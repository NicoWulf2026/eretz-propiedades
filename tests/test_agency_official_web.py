"""La compuerta que decide cual web descubierta se puede afirmar."""
from __future__ import annotations

from scripts.agency_official_web_gate import evaluar, nombre_en_el_dominio, origen
from scripts.agency_official_web_verify import (TLD_EXTRANJEROS,
                                                evidencia_de_argentina,
                                                evidencia_de_otro_pais,
                                                solo_alfanumerico)
from scripts.agency_official_web_verify import evaluar as verificar


def _fila(nombre: str, dominio: str, agencia: str | None = None) -> dict:
    return {"canonical_agency_id": agencia or f"roomix:{nombre.lower()}",
            "nombre": nombre, "discovered_domain": dominio}


def test_un_host_que_reclaman_varias_no_identifica_a_ninguna():
    """`buscainmueble.com` figuraba como web oficial de 65 inmobiliarias.

    Es la misma familia que poner `remax.com.ar` como web de las 191 oficinas
    de la red. La regla se demuestra con nuestros propios datos y no necesita
    una lista de portales mantenida a mano.
    """
    salida = evaluar([
        _fila("Alfa Propiedades", "https://buscainmueble.com/inmobiliarias/alfa"),
        _fila("Beta Propiedades", "https://buscainmueble.com/inmobiliarias/beta"),
    ])
    assert {f["estado"] for f in salida} == {"AMBIGUO_HOST_COMPARTIDO"}
    assert all(f["official_url"] is None for f in salida)
    assert all(f["entidades_que_reclaman_el_host"] == 2 for f in salida)


def test_la_web_oficial_es_un_origen_no_una_pagina():
    """La mitad de los dominios descubiertos apuntaba a la ficha de una
    propiedad. Esa ruta dice donde lo encontramos, no cual es el sitio."""
    salida = evaluar([_fila(
        "ACIN Propiedades",
        "https://www.acinpropiedades.com.ar/p/8093032-Departamento-en-Alquiler")])
    assert salida[0]["estado"] == "AFIRMABLE"
    assert salida[0]["official_url"] == "https://www.acinpropiedades.com.ar"
    assert salida[0]["era_ruta_profunda"] is True


def test_sin_el_nombre_en_el_dominio_no_se_afirma():
    """`waze.com` y `signalhire.com` traen `nombre_exacto` igual que un sitio
    propio: un directorio que lista a una inmobiliaria menciona su nombre
    exacto. Esa senal no distingue el sitio propio del que lo lista, asi que
    aca solo decide el dominio."""
    salida = evaluar([_fila("BECHARA INMOBILIARIA", "https://www.waze.com")])
    assert salida[0]["estado"] == "SIN_RASTRO_DEL_NOMBRE_EN_EL_DOMINIO"
    assert salida[0]["official_url"] is None


def test_una_palabra_generica_no_prueba_nada():
    """Casi toda inmobiliaria tiene `propiedades` en el nombre."""
    assert nombre_en_el_dominio(
        "Alfa Propiedades", "https://propiedadesdelsur.com.ar") is None
    assert nombre_en_el_dominio(
        "Alfa Propiedades", "https://alfapropiedades.com.ar") == "alfa"
    # Tres letras adentro de una marca larga es casualidad, no evidencia.
    assert nombre_en_el_dominio(
        "Sol Propiedades", "https://solucionesglobales.com") is None


def test_origen_descarta_lo_que_no_es_una_url():
    assert origen("no-es-una-url") == ""
    assert origen("https://Alfa.COM.AR/x?y=1") == "https://alfa.com.ar"


def test_el_cctld_de_otro_pais_se_rechaza_sin_abrir_la_pagina():
    """Una inmobiliaria argentina no publica su sitio oficial bajo `.es`."""
    fila = {"official_url": "https://sandoval.es", "palabra_que_coincide": "sandoval"}
    resultado = verificar(fila)  # corta antes de tocar la red
    assert resultado["verificacion"] == "RECHAZADA_TLD_EXTRANJERO"
    assert resultado["official_url"] is None
    assert "es" in TLD_EXTRANJEROS


def test_un_nombre_de_lugar_no_es_evidencia_de_pais():
    """La primera version busco localidades del catalogo GeoRef en el texto y
    dejo pasar a la inmobiliaria Sandoval de IBIZA: su pagina dice "esquina",
    palabra corriente en cualquier aviso y ademas localidad de Corrientes.

    Tampoco alcanza con subir el listado a provincias: Cordoba, La Rioja y
    Santa Fe son tambien provincias espanolas.
    """
    assert evidencia_de_argentina(" propiedad en esquina, muy luminosa ",
                                  "sandovalinmobiliaria.com") == []
    assert evidencia_de_argentina(" oficina en Cordoba ", "x.com") == []
    assert evidencia_de_argentina(" llamanos al +54 341 5551234 ", "x.com")
    assert evidencia_de_argentina(" ", "quinipropiedades.com.ar") == ["dominio .ar"]
    assert evidencia_de_otro_pais(" nuestras oficinas en Ibiza ") == ["ibiza"]


def test_el_nombre_se_busca_con_el_mismo_alfabeto():
    """`RE/MAX` y `remax` son el mismo nombre; buscarlo tal cual dejaba afuera
    a `Remax Cuore`, cuyo sitio escribe la marca con barra."""
    assert solo_alfanumerico("RE/MAX Cuore") == "remaxcuore"
    assert solo_alfanumerico("remax") in solo_alfanumerico("RE/MAX CUORE")


def test_cuando_el_dominio_no_lleva_el_nombre_lo_decide_la_pagina():
    """La regla del dominio no distingue un acrónimo de un dominio ajeno.

    `ayfb.com.ar` es de `Archeri + Fernandez Bazan` y su página lo nombra; el
    sitio de los Bomberos de San Lorenzo, que el gate de promoción daba como
    web de `Casiana Severio`, no. Sin palabra hallada en el dominio se busca la
    más larga del nombre, que es lo que permite separarlos.
    """
    from scripts.agency_official_web_verify import palabra_a_buscar

    assert palabra_a_buscar({"palabra_que_coincide": "alfa"}) == "alfa"
    assert palabra_a_buscar(
        {"palabra_que_coincide": None,
         "nombre": "Casiana Severio Administracion"}) == "administracion"
    # Un nombre sin ninguna palabra larga no alcanza para preguntar nada.
    assert palabra_a_buscar({"palabra_que_coincide": None, "nombre": "A B C"}) == ""


def test_sin_url_no_se_intenta_abrir_nada():
    """El gate de promoción guarda el host pelado y deja `official_url` en None
    cuando no afirma. Pedirle a urllib que abra eso daba un TypeError sobre
    bytes que no explicaba nada."""
    resultado = verificar({"official_url": None, "nombre": "Alfa"})
    assert resultado["verificacion"] == "NO_LLEGO_A_ABRIRSE"
    assert resultado["official_url"] is None
