#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Aritmetica de inmuebles: lo que no puede ser cierto no se publica.

Un dato ausente se ve; un dato incorrecto se publica. Por eso, cuando dos
valores se contradicen, se van los dos: no hay forma de saber cual salio de la
ficha y cual de las "propiedades relacionadas" al pie de la misma pagina.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from connectors.coherencia import revisar  # noqa: E402


def test_un_dormitorio_es_un_ambiente():
    p = {"dormitorios": 5, "ambientes": 1}
    assert "dormitorios>ambientes" in revisar(p)
    assert p["dormitorios"] is None and p["ambientes"] is None


def test_lo_cubierto_es_parte_de_lo_total():
    p = {"superficie_cubierta": 400.0, "superficie_total": 120.0}
    assert "cubierta>total" in revisar(p)
    assert p["superficie_cubierta"] is None and p["superficie_total"] is None


def test_una_superficie_de_cero_metros_no_es_una_superficie():
    p = {"superficie_total": 0, "superficie_cubierta": -5}
    fuera = revisar(p)
    assert "superficie_total_no_positiva" in fuera
    assert "superficie_cubierta_no_positiva" in fuera
    assert p["superficie_total"] is None and p["superficie_cubierta"] is None


def test_un_lote_no_tiene_banos():
    p = {"tipo_propiedad": "terreno", "dormitorios": 3, "banos": 2,
         "ambientes": 4, "superficie_cubierta": 90.0, "superficie_total": 800.0}
    fuera = revisar(p)
    assert "banos_en_un_terreno" in fuera
    assert p["banos"] is None and p["dormitorios"] is None
    assert p["superficie_total"] == 800.0     # esa si es de un lote


def test_media_coordenada_no_ubica_nada():
    """Argentina esta entera en el hemisferio sur y oeste. Poner la propiedad
    donde no esta es peor que no ponerla en el mapa."""
    p = {"latitud": 40.7128, "longitud": -74.0060}      # Nueva York
    assert "coordenada_fuera_de_argentina" in revisar(p)
    assert p["latitud"] is None and p["longitud"] is None

    buena = {"latitud": -34.6037, "longitud": -58.3816}  # Buenos Aires
    assert revisar(buena) == []


def test_cero_no_es_un_precio():
    p = {"precio": 0, "moneda": "USD"}
    assert "precio_no_positivo" in revisar(p)
    assert p["precio"] is None and p["moneda"] is None


def test_una_propiedad_sana_no_se_toca():
    sana = {"dormitorios": 3, "ambientes": 4, "banos": 2, "tipo_propiedad": "casa",
            "superficie_cubierta": 120.0, "superficie_total": 300.0,
            "latitud": -31.42, "longitud": -64.18, "precio": 150000.0,
            "moneda": "USD"}
    copia = dict(sana)
    assert revisar(copia) == []
    assert copia == sana


def test_un_campo_que_no_esta_no_inventa_un_problema():
    assert revisar({}) == []
    assert revisar({"dormitorios": None, "ambientes": None}) == []
    # Un texto donde deberia haber un numero no rompe la revision.
    assert revisar({"superficie_total": "a consultar"}) == []


def test_el_cartel_de_sin_imagen_no_es_una_foto():
    """Y la miniatura de YouTube es el poster del video del tour, no una foto
    de la propiedad."""
    p = {"imagenes": ["https://a.com/f/1.jpg",
                      "https://a.com/images/no-imagen.png",
                      "https://img.youtube.com/vi/x/hqdefault.jpg",
                      "https://a.com/img/logo.png"]}
    assert "imagenes_que_no_son_fotos" in revisar(p)
    assert p["imagenes"] == ["https://a.com/f/1.jpg"]


def test_una_galeria_limpia_no_se_toca():
    p = {"imagenes": ["https://a.com/f/1.jpg", "https://a.com/f/2.webp"]}
    assert revisar(p) == []
    assert len(p["imagenes"]) == 2


def test_el_precio_de_relleno_no_es_un_precio():
    """Un dos ambientes a 1.111 millones de dolares. El sitio escribe un digito
    repetido cuando no quiere publicar el valor."""
    p = {"precio": 1111111111, "moneda": "USD"}
    assert "precio_de_relleno" in revisar(p)
    assert p["precio"] is None and p["moneda"] is None


def test_un_precio_de_marketing_no_es_relleno():
    """"USD 99.999" es un precio de venta perfectamente normal, y 1.111.111
    tambien puede serlo. Solo se descarta el que ademas es absurdo."""
    for precio in (99999, 999999, 1111111, 11111):
        p = {"precio": precio, "moneda": "USD"}
        assert revisar(p) == [], precio
        assert p["precio"] == precio


def test_en_pesos_el_umbral_es_otro():
    """Mil millones de pesos si puede ser un precio; mil millones de dolares no."""
    p = {"precio": 111111111, "moneda": "ARS"}
    assert revisar(p) == [] and p["precio"] == 111111111
