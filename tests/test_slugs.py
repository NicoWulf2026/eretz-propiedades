"""URLs públicas que no afirman geografía sin demostrarla."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from api.slugs import (canonica, datos_estructurados, indexable,
                       segmento_geografico, slug_de)


def _prop(**cambios):
    base = {"id": "h1", "titulo": "Casa en Venta con Jardín",
            "descripcion": "Muy linda", "operacion": "venta",
            "tipo_propiedad": "casa", "precio": 100000.0, "moneda": "USD",
            "imagenes": ["a.jpg"], "latitud": -32.95, "longitud": -60.66,
            "geo": {"localidad": {"nombre": "Rosario"},
                    "provincia": {"nombre": "Santa Fe"},
                    "municipio": {"nombre": "Rosario"}}}
    base.update(cambios)
    return base


def test_la_url_no_dice_una_ciudad_que_no_se_demostro():
    """Una URL es una afirmación tan fuerte como el texto, y además queda
    indexada: `/casa/rosario/` le dice a la persona y al buscador que la
    propiedad está en Rosario. Si sólo sabemos el municipio, la inventa —y de
    forma permanente, porque cambiarla rompe los enlaces."""
    sin_localidad = _prop(geo={"localidad": {"nombre": None},
                               "municipio": {"nombre": "La Calera"},
                               "provincia": {"nombre": "Córdoba"}})
    assert segmento_geografico(sin_localidad["geo"]) == "cordoba"
    assert "la-calera" not in slug_de(sin_localidad)


def test_con_localidad_demostrada_si_aparece():
    assert segmento_geografico(_prop()["geo"]) == "rosario"
    assert "rosario" in slug_de(_prop())


def test_sin_nada_demostrado_no_hay_segmento_geografico():
    vacia = _prop(geo={"localidad": {}, "provincia": {}})
    assert segmento_geografico(vacia["geo"]) == ""
    assert "//" not in slug_de(vacia)


def test_el_id_va_siempre_y_al_final():
    """Un slug puede repetirse y puede cambiar si la inmobiliaria corrige el
    título. El id lo hace único y estable."""
    assert slug_de(_prop()).endswith("/h1")
    pelada = {"id": "h9", "geo": {}}
    assert slug_de(pelada) == "h9"


def test_los_acentos_no_llegan_a_la_url():
    assert "jardin" in slug_de(_prop())
    assert "í" not in slug_de(_prop())


def test_la_canonica_es_una_sola():
    a = canonica(_prop(), "https://eretz.com.ar")
    b = canonica(_prop(), "https://eretz.com.ar/")
    assert a == b
    assert a.startswith("https://eretz.com.ar/propiedad/")


def test_una_ficha_sin_nada_no_se_indexa():
    """Publicarla gasta presupuesto de rastreo en páginas que van a rebotar."""
    ok, razon = indexable({"titulo": None, "descripcion": None, "imagenes": []})
    assert ok is False and "nada que indexar" in razon

    ok, razon = indexable({"titulo": "Casa", "descripcion": None, "imagenes": []})
    assert ok is False and "rebotar" in razon

    assert indexable(_prop())[0] is True


def test_un_precio_sin_moneda_no_entra_en_los_datos_estructurados():
    """schema.org exige las dos cosas juntas: publicar una sin la otra es
    publicar un número."""
    d = datos_estructurados(_prop(moneda=None), "https://eretz.com.ar")
    assert "offers" not in d
    assert "offers" in datos_estructurados(_prop(), "https://eretz.com.ar")


def test_los_datos_estructurados_no_inventan_la_localidad():
    """Un dato estructurado inventado es peor que ausente: el buscador lo
    muestra como si fuera nuestro."""
    d = datos_estructurados(
        _prop(geo={"localidad": {"nombre": None},
                   "municipio": {"nombre": "La Calera"},
                   "provincia": {"nombre": "Córdoba"}}),
        "https://eretz.com.ar")
    assert "addressLocality" not in d["address"]
    assert d["address"]["addressRegion"] == "Córdoba"
    assert "La Calera" not in str(d)
