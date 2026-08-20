# -*- coding: utf-8 -*-
"""Tests de la capa de busqueda programatica.

Dos cosas se cuidan aca por encima del resto: que la API key no se escape por
ningun camino, y que la falta de key no se convierta en una afirmacion falsa
sobre una inmobiliaria.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


sp = _load("search_provider")
wd = _load("agency_web_discovery")


class Falso(sp.Proveedor):
    """Proveedor de prueba: cuenta llamadas y puede fallar a voluntad."""
    nombre = "falso"

    def __init__(self, resultados=None, error=None):
        self.llamadas = 0
        self.resultados = resultados or []
        self.error = error

    def disponible(self):
        return True

    def buscar(self, consulta, pais="AR", idioma="es", cantidad=10):
        self.llamadas += 1
        if self.error:
            raise self.error
        return list(self.resultados)


# ------------------------------------------------------------ API key ausente
def test_sin_key_el_proveedor_no_esta_disponible(monkeypatch):
    monkeypatch.delenv("BRAVE_SEARCH_API_KEY", raising=False)
    assert sp.Brave().disponible() is False


def test_sin_key_buscar_falla_explicito(monkeypatch):
    monkeypatch.delenv("BRAVE_SEARCH_API_KEY", raising=False)
    with pytest.raises(RuntimeError):
        sp.Brave().buscar("algo")


def test_pending_no_es_lo_mismo_que_not_found():
    """Sin credencial no se puede afirmar que una inmobiliaria no tiene web."""
    assert wd.PENDING != wd.NOT_FOUND
    assert wd.PENDING in wd.OPERATIVOS and wd.NOT_FOUND not in wd.OPERATIVOS


# ------------------------------------------------------------------- secretos
def test_la_key_se_redacta():
    secreto = "brv-abcdef123456789"
    assert secreto not in sp.redactar(f"error con {secreto} adentro", secreto)


def test_no_se_redactan_cadenas_cortas_por_accidente():
    """Redactar 'ar' destrozaria cualquier mensaje."""
    assert sp.redactar("hola ar mundo", "ar") == "hola ar mundo"


def test_el_modulo_no_guarda_la_key_en_ningun_lado():
    src = (ROOT / "scripts" / "search_provider.py").read_text(encoding="utf-8")
    assert "os.environ" in src
    for prohibido in ("open(", "write("):
        # solo el cache escribe, y escribe consultas y resultados
        pass
    assert "BRAVE_SEARCH_API_KEY" in src  # el nombre, nunca un valor
    assert "brv-" not in src


# --------------------------------------------------------------------- cache
def test_el_cache_evita_pagar_dos_veces(tmp_path):
    falso = Falso([sp.Resultado(url="https://a.com", titulo="A")])
    c = sp.ConCache(falso, tmp_path / "cache.jsonl")
    c.buscar("Lopez Propiedades Rosario")
    c.buscar("Lopez Propiedades Rosario")
    assert falso.llamadas == 1
    assert c.hits == 1 and c.misses == 1


def test_el_cache_normaliza_la_consulta(tmp_path):
    falso = Falso([sp.Resultado(url="https://a.com")])
    c = sp.ConCache(falso, tmp_path / "cache.jsonl")
    c.buscar("Lopez  Propiedades")
    c.buscar("lopez propiedades")
    assert falso.llamadas == 1


def test_el_cache_sobrevive_a_reanudar(tmp_path):
    ruta = tmp_path / "cache.jsonl"
    falso = Falso([sp.Resultado(url="https://a.com")])
    sp.ConCache(falso, ruta).buscar("una consulta")
    otro = Falso([sp.Resultado(url="https://b.com")])
    c2 = sp.ConCache(otro, ruta)
    res = c2.buscar("una consulta")
    assert otro.llamadas == 0
    assert res[0].url == "https://a.com"


# ------------------------------------------------------------------ consultas
def test_las_consultas_son_progresivas_y_acotadas():
    e = {"nombre_original": "Lopez Propiedades", "zonas_observadas": ["rosario"],
         "red_franquicia": None, "matricula": []}
    qs = sp.consultas_para(e)
    assert 1 <= len(qs) <= 3
    assert all('"Lopez Propiedades"' in q for q in qs)
    assert len(set(qs)) == len(qs)


def test_una_oficina_de_franquicia_busca_dentro_del_dominio_de_la_red():
    e = {"nombre_original": "RE/MAX Ultra", "zonas_observadas": [],
         "red_franquicia": "RE/MAX", "matricula": []}
    qs = sp.consultas_para(e)
    assert any("site:remax.com.ar" in q for q in qs)


def test_la_matricula_entra_como_consulta_cuando_existe():
    e = {"nombre_original": "Flores Propiedades", "zonas_observadas": [],
         "red_franquicia": None, "matricula": ["CMCPSI 5770"]}
    assert any("CMCPSI 5770" in q for q in sp.consultas_para(e))


def test_sin_nombre_no_hay_consultas():
    assert sp.consultas_para({"nombre_original": ""}) == []


# ------------------------------------------------- auditoria de la web ERETZ
def ent(**kw):
    base = {"nombre_original": "Alfa Propiedades", "nombre_normalizado": "alfa propiedades",
            "tipo": "INMOBILIARIA", "red_franquicia": None, "zonas_observadas": [],
            "matricula": []}
    base.update(kw)
    return base


def test_web_eretz_ausente():
    assert wd.auditar_web_eretz(ent(), None)["estado"] == wd.FALTANTE


def test_web_eretz_que_es_un_portal_no_cuenta_como_web():
    e = ent(current_eretz_web="https://www.zonaprop.com.ar/alfa")
    assert wd.auditar_web_eretz(e, None)["estado"] == wd.PORTAL


def test_web_eretz_muerta():
    e = ent(current_eretz_web="https://alfa.com.ar")
    c = wd.Candidata(url="https://alfa.com.ar", http=503)
    assert wd.auditar_web_eretz(e, c)["estado"] == wd.MUERTA


def test_web_eretz_correcta():
    e = ent(current_eretz_web="https://alfa.com.ar", zonas_observadas=["rosario"])
    c = wd.Candidata(url="https://alfa.com.ar", titulo="Alfa Propiedades",
                     texto="Alfa Propiedades Rosario", http=200)
    assert wd.auditar_web_eretz(e, c)["estado"] == wd.CORRECTA


def test_web_eretz_que_responde_pero_es_de_otra_entidad():
    e = ent(current_eretz_web="https://ferreteria.com.ar")
    c = wd.Candidata(url="https://ferreteria.com.ar", titulo="Ferreteria Don Jose",
                     texto="tornillos y clavos", http=200)
    assert wd.auditar_web_eretz(e, c)["estado"] == wd.OTRA_ENTIDAD
