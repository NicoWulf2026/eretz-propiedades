# -*- coding: utf-8 -*-
"""Tests del padron de publicadores.

Lo central: Roomix es un medio para descubrir anunciantes, no una fuente de
propiedades. Estos tests fijan esa frontera en el codigo, no solo en la
documentacion.
"""
from __future__ import annotations

import importlib.util
import inspect
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


ad = _load("build_agency_directory")


def _solo_codigo(mod) -> str:
    """Sin docstrings ni comentarios: la prosa nombra justamente los campos que
    el codigo promete no tocar, y eso daria un falso positivo."""
    import ast, io, tokenize
    src = inspect.getsource(mod)
    sin_com = tokenize.untokenize(
        t for t in tokenize.generate_tokens(io.StringIO(src).readline)
        if t.type != tokenize.COMMENT)
    arbol = ast.parse(sin_com)
    for nodo in ast.walk(arbol):
        if isinstance(nodo, (ast.Module, ast.FunctionDef, ast.ClassDef)) and ast.get_docstring(nodo):
            nodo.body = nodo.body[1:] or [ast.Pass()]
    return ast.unparse(arbol)


def test_no_se_toca_ningun_dato_de_la_propiedad():
    """La frontera del encargo: de la ficha solo sale el anunciante."""
    src = _solo_codigo(ad)
    for campo in ("precio", "price", "descripcion", "description", "fotos",
                  "images", "amenities", "ambientes\"", "superficie", "m2",
                  "dormitorios\"", "banos\""):
        assert campo not in src, f"el padron no debe tocar {campo}"


def test_la_zona_sale_del_slug_y_descarta_lo_que_describe_la_propiedad():
    z = ad.zona_de_url("https://roomix.ai/propiedad/departamento-5-ambientes-barrio-norte-91a39c57")
    assert "departamento" not in z and "ambientes" not in z
    assert "barrio" in z and "norte" in z


def test_la_zona_quita_el_hash_final():
    assert "91a39c57" not in ad.zona_de_url(
        "https://roomix.ai/propiedad/casa-villa-allende-91a39c57")


def test_una_url_sin_zona_util_no_inventa_zona():
    assert ad.zona_de_url("https://roomix.ai/propiedad/departamento-3-ambientes-abc123def") == ""


def test_el_logo_se_deriva_del_agent_id():
    """No hace falta leer la pagina: el patron es determinista."""
    assert ad.LOGO.format(agent_id="abc") == "https://cdn.roomix.ai/agents/abc"
