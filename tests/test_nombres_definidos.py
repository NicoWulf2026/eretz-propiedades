#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Ninguna función puede leer un nombre que no recibe.

`_procesar_con()` leía `presupuesto` sin recibirlo: el parámetro estaba
declarado en la función de al lado. Un `NameError`, y en el peor lugar posible
—recién al llegar a pedir la primera ficha—, así que fallaba **sólo en las
fuentes que funcionaban**. Las que el connector no reconocía salían antes por
otra rama y nunca tocaban la línea rota.

El resultado era una corrida entera sin un solo error, con cero propiedades, y
un resumen que reconciliaba perfecto: 0 pedidas, 0 obtenidas, 0 perdidas. Quedó
así desde el commit que introdujo el presupuesto hasta que alguien volvió a
correr un rollout.

Mirar el módulo entero no alcanza para verlo: `presupuesto` **existe** en el
módulo, como parámetro de la otra función. Hay que resolver por alcance —lo que
cada función recibe, lo que ella misma asigna, lo que le llega de las funciones
que la contienen, y lo que hay a nivel módulo— que es exactamente lo que hace
Python cuando ejecuta.
"""
from __future__ import annotations

import ast
import builtins
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]

CARPETAS = ("scripts", "connectors", "tests")

SIEMPRE_DEFINIDOS = frozenset(set(dir(builtins)) | {
    "__name__", "__file__", "__doc__", "__spec__", "__package__",
    "__builtins__", "__class__", "annotations",
})


def _ligados_por(nodo: ast.AST) -> set:
    """Los nombres que este nodo introduce en su propio alcance.

    No entra en funciones ni clases anidadas: esas abren un alcance nuevo y se
    resuelven por separado.
    """
    ligados = set()
    if isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
        a = nodo.args
        for arg in (*a.posonlyargs, *a.args, *a.kwonlyargs):
            ligados.add(arg.arg)
        if a.vararg:
            ligados.add(a.vararg.arg)
        if a.kwarg:
            ligados.add(a.kwarg.arg)

    pila = list(ast.iter_child_nodes(nodo))
    while pila:
        n = pila.pop()
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            ligados.add(n.name)          # el nombre sí queda en este alcance
            continue                      # pero el cuerpo no
        if isinstance(n, ast.Lambda):
            # Una lambda tambien abre alcance: sus parametros valen adentro.
            continue
        if isinstance(n, ast.Name) and isinstance(n.ctx, (ast.Store, ast.Del)):
            ligados.add(n.id)
        elif isinstance(n, (ast.Import, ast.ImportFrom)):
            for al in n.names:
                ligados.add(al.asname or al.name.split(".")[0])
        elif isinstance(n, ast.ExceptHandler) and n.name:
            ligados.add(n.name)
        elif isinstance(n, (ast.Global, ast.Nonlocal)):
            ligados.update(n.names)
        pila.extend(ast.iter_child_nodes(n))
    return ligados


def _leidos_en(nodo: ast.AST) -> list:
    """Los nombres que este alcance lee, sin entrar en los anidados."""
    leidos = []
    pila = list(ast.iter_child_nodes(nodo))
    while pila:
        n = pila.pop()
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef,
                          ast.Lambda)):
            continue
        if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load):
            leidos.append(n.id)
        pila.extend(ast.iter_child_nodes(n))
    return leidos


def _anidados(nodo: ast.AST) -> list:
    salida = []
    pila = list(ast.iter_child_nodes(nodo))
    while pila:
        n = pila.pop()
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef,
                          ast.Lambda)):
            salida.append(n)
            continue
        pila.extend(ast.iter_child_nodes(n))
    return salida


def _revisar(nodo: ast.AST, visibles: set, camino: str, fallas: list) -> None:
    propio = visibles | _ligados_por(nodo)
    for nombre in _leidos_en(nodo):
        if nombre not in propio:
            fallas.append("%s lee %r sin recibirlo" % (camino, nombre))
    for hijo in _anidados(nodo):
        nombre_hijo = getattr(hijo, "name", "<lambda>")
        _revisar(hijo, propio, "%s.%s" % (camino, nombre_hijo), fallas)


def leidos_sin_definir(ruta: Path) -> list:
    arbol = ast.parse(ruta.read_text(encoding="utf-8"))
    fallas: list = []
    _revisar(arbol, set(SIEMPRE_DEFINIDOS), ruta.name, fallas)
    return fallas


def modulos() -> list:
    out = []
    for carpeta in CARPETAS:
        out.extend(sorted((RAIZ / carpeta).glob("*.py")))
    return out


def test_hay_modulos_para_auditar():
    """Si el glob deja de encontrar archivos, el test pasaría sin mirar nada."""
    assert len(modulos()) > 50


def test_ninguna_funcion_lee_un_nombre_que_no_recibe():
    fallas = []
    for ruta in modulos():
        try:
            fallas.extend(leidos_sin_definir(ruta))
        except SyntaxError as e:
            fallas.append("%s no parsea: %s" % (ruta.name, e))
    assert not fallas, "\n".join(fallas)


def test_el_detector_reconoce_el_caso_que_lo_origino(tmp_path):
    """El bug real, reducido: el parámetro está en la función de al lado.

    Mirando el módulo entero esto pasa desapercibido, porque `presupuesto`
    existe. Es exactamente por eso que hace falta resolver por alcance.
    """
    roto = tmp_path / "roto.py"
    roto.write_text(
        "def procesar(x, presupuesto=1800):\n"
        "    return _hacer(x)\n"
        "\n"
        "def _hacer(x):\n"
        "    return x + presupuesto\n", encoding="utf-8")
    fallas = leidos_sin_definir(roto)
    assert any("presupuesto" in f and "_hacer" in f for f in fallas), fallas


def test_un_import_olvidado_tambien_se_ve(tmp_path):
    """La misma forma: pasa verde mientras esa rama no se ejecute."""
    roto = tmp_path / "roto.py"
    roto.write_text(
        "def f(ruta):\n"
        "    if not ruta.exists():\n"
        "        pytest.skip('sin artefacto')\n"
        "    return 1\n", encoding="utf-8")
    assert any("pytest" in f for f in leidos_sin_definir(roto))


def test_una_funcion_anidada_ve_lo_de_afuera(tmp_path):
    """Un closure legítimo no puede dar falso positivo."""
    sano = tmp_path / "sano.py"
    sano.write_text(
        "def afuera(x, tope=5):\n"
        "    def adentro(y):\n"
        "        return y + x + tope\n"
        "    return adentro\n", encoding="utf-8")
    assert leidos_sin_definir(sano) == []


def test_lo_normal_no_se_marca(tmp_path):
    sano = tmp_path / "sano.py"
    sano.write_text(
        "import json\n"
        "TOPE = 10\n"
        "\n"
        "class C:\n"
        "    campo = TOPE\n"
        "\n"
        "def f(x, presupuesto=TOPE):\n"
        "    try:\n"
        "        ys = [i * presupuesto for i in range(x)]\n"
        "        with open('a') as fh:\n"
        "            fh.write(json.dumps(ys))\n"
        "        for k, v in enumerate(ys):\n"
        "            del v\n"
        "        return k\n"
        "    except ValueError as e:\n"
        "        return str(e)\n", encoding="utf-8")
    assert leidos_sin_definir(sano) == []
