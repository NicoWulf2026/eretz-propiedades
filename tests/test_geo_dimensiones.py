"""El modelo geográfico multidimensional: ningún nivel rellena a otro."""
from __future__ import annotations

from connectors.base import (AREA_DEPARTAMENTO, AREA_LOCALIDAD, AREA_MUNICIPIO,
                             AREA_PROVINCIA, AREA_SIN, GEO_CANONICAL,
                             GEO_SOURCE_TEXT, GEO_UNKNOWN, Connector,
                             PropiedadNormalizada, dimension_geo)


def _propiedad(**cambios):
    base = dict(canonical_agency_id="roomix:alfa", source_listing_id="1",
                source_url="https://alfa.com.ar/p/1", connector="generico")
    base.update(cambios)
    return PropiedadNormalizada(**base)


# ------------------------------------------------------------ dimensiones

def test_una_localidad_demostrada_llena_su_dimension_y_el_departamento():
    """Los ids de GeoRef son jerárquicos —`06` provincia, `06280`
    departamento, `06280040` localidad—, así que el departamento no se deduce:
    viene adentro del id de la localidad."""
    p = _propiedad(ciudad="Miramar", provincia="Buenos Aires")
    Connector._resolver_geografia(p)

    assert p.geo["localidad"]["nombre"] == "Miramar"
    assert p.geo["localidad"]["id"] == "06280040"
    assert p.geo["localidad"]["procedencia"] == GEO_CANONICAL
    assert p.geo["departamento"]["id"] == "06280"
    assert p.geo["provincia"]["nombre"] == "Buenos Aires"


def test_cada_dimension_dice_por_que_no_se_pudo_demostrar():
    """`rechazo` es la mitad que suele faltar. Sin ella, "no se pudo demostrar"
    y "nunca se intentó" se ven iguales, y confundir esas dos ausencias es como
    se escribe geografía inventada."""
    p = _propiedad(ciudad="Nombre Que No Existe En Ningun Catalogo")
    Connector._resolver_geografia(p)

    assert p.geo["localidad"]["nombre"] is None
    assert p.geo["localidad"]["procedencia"] == GEO_UNKNOWN
    assert p.geo["localidad"]["rechazo"]
    assert "no se pudo demostrar" in p.geo["localidad"]["rechazo"]


def test_el_municipio_no_se_cuenta_como_localidad():
    """La decisión: un municipio puede servir para descubrir una propiedad,
    pero no puede fingir ser una localidad."""
    geo = {"localidad": dimension_geo(None),
           "municipio": dimension_geo("La Calera", id="140119",
                                      procedencia=GEO_CANONICAL),
           "departamento": dimension_geo(None),
           "provincia": dimension_geo("Córdoba", procedencia=GEO_SOURCE_TEXT)}
    area = Connector._area_de_busqueda(geo)

    assert area["nivel"] == AREA_MUNICIPIO
    assert area["nombre"] == "La Calera"
    # Y la localidad sigue vacía: bajar de nivel no rellena hacia arriba.
    assert geo["localidad"]["nombre"] is None


def test_el_barrio_se_conserva_aunque_no_se_pueda_canonizar():
    """GeoRef no cataloga barrios. Una persona que busca en Villa del Parque
    reconoce el nombre, y esconderlo pierde información real sin ganar nada."""
    p = _propiedad(barrio="Villa Crespo", ciudad="Miramar",
                   provincia="Buenos Aires")
    Connector._resolver_geografia(p)

    assert p.geo["barrio"]["nombre"] == "Villa Crespo"
    assert p.geo["barrio"]["procedencia"] == GEO_SOURCE_TEXT
    assert "no cataloga" in (p.geo["barrio"]["rechazo"] or "")


# --------------------------------------------------------- area de busqueda

def test_el_area_baja_de_nivel_hasta_encontrar_evidencia():
    def area(**dims):
        base = {d: dimension_geo(None) for d in
                ("localidad", "municipio", "departamento", "provincia")}
        base.update(dims)
        return Connector._area_de_busqueda(base)["nivel"]

    assert area(localidad=dimension_geo("Miramar", procedencia=GEO_CANONICAL)) == AREA_LOCALIDAD
    assert area(municipio=dimension_geo("La Calera", procedencia=GEO_CANONICAL)) == AREA_MUNICIPIO
    assert area(departamento=dimension_geo("Colón", procedencia=GEO_CANONICAL)) == AREA_DEPARTAMENTO
    assert area(provincia=dimension_geo("Córdoba", procedencia=GEO_SOURCE_TEXT)) == AREA_PROVINCIA
    assert area() == AREA_SIN


def test_una_dimension_sin_procedencia_no_sirve_de_area():
    """Un nombre sin evidencia no es evidencia. Si la procedencia es UNKNOWN,
    el nivel no se usa aunque haya quedado un nombre suelto."""
    geo = {"localidad": dimension_geo(None),
           "municipio": dimension_geo("Sospechoso", procedencia=GEO_UNKNOWN),
           "departamento": dimension_geo(None),
           "provincia": dimension_geo(None)}
    assert Connector._area_de_busqueda(geo)["nivel"] == AREA_SIN


def test_el_area_declara_siempre_su_nivel():
    """Sin nivel, un municipio en la caja de búsqueda se lee como una ciudad.
    El nivel es el diseño entero."""
    p = _propiedad(ciudad="Miramar", provincia="Buenos Aires")
    Connector._resolver_geografia(p)
    area = p.geo["area_busqueda"]

    assert set(area) == {"nivel", "nombre", "id", "origen"}
    assert area["nivel"] == AREA_LOCALIDAD
    assert area["origen"] == "localidad"


# ------------------------------------------------------------- la huella

def test_la_geografia_derivada_no_entra_en_la_huella_de_contenido():
    """Sus insumos —ciudad, barrio, provincia, lat, lon— ya están hasheados,
    así que agregarla no aporta información sobre si la FUENTE cambió. Si
    entrara, cualquier mejora del resolver devolvería el inventario entero
    como MODIFICADA."""
    a = _propiedad(ciudad="Miramar", provincia="Buenos Aires")
    b = _propiedad(ciudad="Miramar", provincia="Buenos Aires")
    sin_resolver = a.fingerprint

    Connector._resolver_geografia(b)
    assert b.geo, "el resolver tiene que haber escrito las dimensiones"
    assert b.fingerprint == sin_resolver


def test_la_propiedad_nunca_desaparece_por_geografia():
    """La regla que no se negocia."""
    p = _propiedad(ciudad="Nombre Inexistente", titulo="Casa en Venta")
    Connector._resolver_geografia(p)
    assert p.source_url and p.titulo
