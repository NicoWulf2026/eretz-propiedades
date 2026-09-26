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
