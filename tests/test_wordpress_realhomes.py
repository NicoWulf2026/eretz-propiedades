"""RealHomes y REST sin datos de propiedad (`alas`, `echesortu`, `fiorio`)."""
from __future__ import annotations

from connectors.wordpress import meta_con_claves_houzez, meta_de_propiedad


def test_realhomes_se_traduce_a_claves_houzez():
    meta = {"REAL_HOMES_property_address": "Mayu Sumaj, Córdoba, Argentina",
            "REAL_HOMES_property_bathrooms": "2", "REAL_HOMES_property_lot_size": "1.500",
            "REAL_HOMES_property_location": {"latitude": "-31.46", "longitude": "-64.54"}}
    m = meta_con_claves_houzez(meta)
    assert m["fave_property_address"].startswith("Mayu Sumaj")
    assert m["fave_property_bathrooms"] == "2" and m["fave_property_land"] == "1.500"
    assert m["fave_property_location"] == "-31.46,-64.54"


def test_no_pisa_una_clave_houzez_existente():
    m = meta_con_claves_houzez({"fave_property_address": "A", "REAL_HOMES_property_address": "B"})
    assert m["fave_property_address"] == "A"


def test_meta_del_tema_no_es_meta_de_propiedad():
    assert not meta_de_propiedad({"_acf_changed": True, "site-sidebar-layout": "default"})
    assert not meta_de_propiedad({"inline_featured_image": False, "footnotes": ""})
    assert meta_de_propiedad({"fave_property_price": "100000"})
    assert meta_de_propiedad({"REAL_HOMES_property_price": "430000"})


def test_icono_de_atributo_por_nombre():
    from scripts.image_quality import is_attribute_icon
    base = "https://f.test/wp-content/uploads/2025/09/"
    for nombre in ("ubicacion.avif", "metros-cuadrados.avif", "metros-cubiertos.avif",
                   "ambientes.avif", "dormitorios2.avif", "bano.avif"):
        assert is_attribute_icon(base + nombre), nombre
    assert not is_attribute_icon(base + "PERON-DEPTO.webp")
    assert not is_attribute_icon(base + "bano-principal-reformado.jpg")


def test_iconos_repetidos_se_descartan_y_fotos_propias_no():
    from types import SimpleNamespace
    from scripts.run_rollout import descartar_imagenes_compartidas
    icono = "https://f.test/wp-content/uploads/2025/09/bano.avif"
    objs = [SimpleNamespace(imagenes=[icono, f"https://f.test/wp-content/uploads/p{i}.webp"], extra={})
            for i in range(10)]
    assert descartar_imagenes_compartidas(objs) == 10
    assert all(o.imagenes == [f"https://f.test/wp-content/uploads/p{i}.webp"]
               for i, o in enumerate(objs))


def test_fallo_de_red_del_html_no_cae_al_rest_pobre():
    from connectors.base import ErrorTransitorio, Fuente
    from connectors.wordpress import WordPressConnector

    class Caido:
        def bajar(self, url):
            raise ErrorTransitorio("timeout")

    c = WordPressConnector(Caido())
    f = Fuente(canonical_agency_id="roomix:x", agency_name="X",
               official_url="https://f.test", inmobiliaria_id=1)
    crudo = {"source_url": "https://f.test/propiedad/casa-en-venta-centro/",
             "source_listing_id": "1",
             "rest": {"title": {"rendered": "Casa"}, "content": {"rendered": ""}, "meta": {}}}
    assert c.normalize(crudo, f) is None
    assert c.errores[-1]["etapa"] == "detalle"


def test_rest_con_catalogo_multiplo_de_la_pagina_no_queda_interrumpido():
    import json as _json
    from connectors.base import ErrorTransitorio
    from connectors.wordpress import POR_PAGINA, WordPressConnector

    class D:
        def bajar(self, url):
            if "page=1&" in url:
                return _json.dumps([{"id": i, "link": f"https://w.test/property/p{i}/"}
                                    for i in range(1, POR_PAGINA + 1)])
            raise ErrorTransitorio("http 400")

    c = WordPressConnector(D())
    items = list(c._rest({"base": "https://w.test", "rest_base": "properties"}))
    assert len(items) == POR_PAGINA
    assert not getattr(c, "paginacion_interrumpida", False)


def test_rest_con_red_caida_en_la_primera_pagina_si_queda_interrumpido():
    from connectors.base import ErrorTransitorio
    from connectors.wordpress import WordPressConnector

    class D:
        def bajar(self, url):
            raise ErrorTransitorio("http 400")

    c = WordPressConnector(D())
    assert list(c._rest({"base": "https://w.test", "rest_base": "properties"})) == []
    assert c.paginacion_interrumpida
