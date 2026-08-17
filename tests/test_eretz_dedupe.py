# -*- coding: utf-8 -*-
"""Tests del motor de dedupe.

Cubren sobre todo las formas en que el cruce anterior se equivocaba: decidir
identidad por una sola columna, tratar un dato ausente como desacuerdo, y
fusionar oficinas distintas de una misma red.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


d = _load("eretz_dedupe")
cw = _load("agency_crosswalk")


def E(ident, nombre, **kw):
    return d.Entidad(ident=ident, nombre=nombre, **kw)


# --------------------------------------------------------- normalizacion
def test_el_normalizador_es_el_mismo_que_el_del_cruce():
    """Si difieren, las dos etapas llaman distinto a la misma entidad."""
    for n in ("Estela D&#x27;onofrio Propiedades", "López Baena Propiedades",
              "Benuzzi Inmobiliaria SA", "Marcel Gestion (Pinamar)",
              "RE/MAX Uno - San Isidro", "Perez & Asociados"):
        assert d.norm_name(n) == cw.norm_name(n), n


def test_la_clave_se_calcula_y_no_depende_de_la_columna():
    """El problema real: 1.983 filas de main tienen nombre_normalizado NULL."""
    con = E("1", "FIOS Consultoría Inmobiliaria", normalizado_guardado="fios consultora inmobiliaria")
    sin = E("2", "FIOS Consultoría Inmobiliaria", normalizado_guardado=None)
    assert sin.norm_calculado == con.norm_calculado
    assert d.comparar(con, sin).estado in (d.EXACT, d.HIGH_CONFIDENCE)


def test_acentos_y_mayusculas_no_separan():
    a = E("1", "Fios Consultoría Inmobiliaria")
    b = E("2", "FIOS CONSULTORIA INMOBILIARIA")
    assert d.comparar(a, b).estado == d.HIGH_CONFIDENCE


# --------------------------------------------------------- dominios
def test_dominio_propio_compartido_es_identidad():
    a = E("1", "Alfa Propiedades", web="https://www.alfaprop.com.ar/inicio")
    b = E("2", "Alfa Negocios Inmobiliarios", web="http://alfaprop.com.ar")
    v = d.comparar(a, b)
    assert v.estado == d.HIGH_CONFIDENCE
    assert any("dominio" in s for s in v.senales)


def test_portal_no_cuenta_como_dominio_propio():
    """Dos inmobiliarias con ficha en Zonaprop no son la misma."""
    a = E("1", "Alfa Propiedades", web="https://www.zonaprop.com.ar/inmobiliaria-alfa")
    b = E("2", "Beta Propiedades", web="https://www.zonaprop.com.ar/inmobiliaria-beta")
    assert d.dominio(a.web) == "" and d.dominio(b.web) == ""
    assert d.comparar(a, b).estado == d.DISTINCT


def test_dominios_propios_distintos_contradicen():
    a = E("1", "Alfa Propiedades", web="https://alfa.com.ar")
    b = E("2", "Alfa Propiedades", web="https://alfa-inmobiliaria.com")
    v = d.comparar(a, b)
    assert v.estado == d.AMBIGUOUS
    assert any("dominios distintos" in c for c in v.contras)


# --------------------------------------------------------- telefonos
def test_el_mismo_telefono_en_formatos_distintos_coincide():
    assert d.telefono("+54 9 11 4555-1234") == d.telefono("011 4555-1234") != ""


def test_telefono_demasiado_corto_se_descarta():
    assert d.telefono("1234") == ""


# --------------------------------------------------------- datos ausentes
def test_localidad_ausente_no_es_desacuerdo():
    """Las filas historicas de main suelen no tener ciudad; tratar el NULL como
    contradiccion descartaba coincidencias buenas."""
    a = E("1", "Vanzini Propiedades", ciudad=None, provincia=None)
    b = E("2", "VANZINI PROPIEDADES", ciudad="Rosario", provincia="Santa Fe")
    v = d.comparar(a, b)
    assert not v.contras
    assert v.estado == d.HIGH_CONFIDENCE


def test_localidades_distintas_si_ambas_existen_vuelven_ambiguo():
    a = E("1", "Sur Propiedades", ciudad="Rosario", provincia="Santa Fe")
    b = E("2", "Sur Propiedades", ciudad="Salta", provincia="Salta")
    v = d.comparar(a, b)
    assert v.estado == d.AMBIGUOUS
    assert any("localidades distintas" in c for c in v.contras)


# --------------------------------------------------------- franquicias
def test_oficinas_distintas_de_la_misma_red_no_se_fusionan():
    a = E("1", "RE/MAX Uno San Isidro", ciudad="San Isidro", provincia="Buenos Aires")
    b = E("2", "RE/MAX Vita Colegiales", ciudad="CABA", provincia="CABA")
    assert d.comparar(a, b).estado in (d.DISTINCT, d.AMBIGUOUS)


def test_la_marca_sola_no_absorbe_una_oficina():
    marca = E("1", "RE/MAX")
    ofi = E("2", "RE/MAX Data Work")
    assert d.comparar(marca, ofi).estado != d.EXACT


# --------------------------------------------------------- matriculas
def test_matricula_compartida_es_senal_fuerte():
    a = E("1", "Flores Propiedades CMCPSI 5770")
    b = E("2", "Gabriel Flores Negocios CMCPSI 5770")
    v = d.comparar(a, b)
    assert v.estado == d.HIGH_CONFIDENCE
    assert any("matricula" in s for s in v.senales)


# --------------------------------------------------------- estados
def test_nombre_parecido_sin_respaldo_no_alcanza():
    a = E("1", "Mauro Sola Negocios Inmobiliarios")
    b = E("2", "Mauro Musso Negocios Inmobiliarios")
    assert d.comparar(a, b).estado in (d.AMBIGUOUS, d.DISTINCT)


def test_nombre_muy_corto_es_insuficiente():
    assert d.comparar(E("1", "AB"), E("2", "AB")).estado == d.INSUFFICIENT


def test_sin_nada_en_comun_es_distinct():
    a = E("1", "Alberto Dacal Propiedades")
    b = E("2", "Zzyzx Bienes Raices Patagonia")
    assert d.comparar(a, b).estado == d.DISTINCT


def test_todo_veredicto_explica_su_decision():
    v = d.comparar(E("1", "Alfa Propiedades", web="https://alfa.com.ar"),
                   E("2", "Alfa Propiedades", web="https://alfa.com.ar"))
    assert v.explicacion and v.matcher_version == d.MATCHER_VERSION


# --------------------------------------------------------- cardinalidad
def test_uno_a_uno_es_resoluble_y_muchos_a_uno_no():
    izq = [E("s1", "Alfa Propiedades"), E("s2", "Alfa Propiedades")]
    der = [E("m1", "Alfa Propiedades")]
    pares = d.cruzar(izq, der)
    card = d.cardinalidad(pares)
    assert pares and all(c == "muchos_a_uno" for c in card.values())
    assert not any(d.resoluble(p, card[f"{p.izquierda.ident}->{p.derecha.ident}"]) for p in pares)


def test_un_par_limpio_uno_a_uno_si_es_resoluble():
    pares = d.cruzar([E("s1", "Vanzini Propiedades")], [E("m1", "VANZINI PROPIEDADES")])
    card = d.cardinalidad(pares)
    assert len(pares) == 1
    p = pares[0]
    assert d.resoluble(p, card[f"{p.izquierda.ident}->{p.derecha.ident}"])


def test_el_cruce_no_compara_todo_contra_todo():
    """Sin bloqueo, staging x main serian ~82 millones de comparaciones."""
    izq = [E(f"s{i}", f"Inmobiliaria Numero {i}") for i in range(200)]
    der = [E(f"m{i}", f"Inmobiliaria Numero {i}") for i in range(200)]
    pares = d.cruzar(izq, der)
    # Cada una encuentra la suya, no las 200.
    assert len(pares) <= 400
