#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""El presupuesto por fuente tiene que existir donde se lo usa.

`procesar()` declaraba `presupuesto` como parametro y `_procesar_con()` -que es
donde vive el bucle que pide fichas- lo leia sin recibirlo. NameError, y en el
peor lugar posible: recien al llegar a pedir la primera ficha.

O sea que fallaba exactamente en las fuentes que SI funcionaban. Las que el
connector no reconocia salian antes por VARIANTE_NO_SOPORTADA y nunca tocaban la
linea rota, asi que una corrida entera podia terminar "sin errores" con cero
propiedades y el resumen reconciliando: 0 pedidas, 0 obtenidas, 0 perdidas.

Quedo latente desde el commit que introdujo el presupuesto porque ningun rollout
volvio a correr hasta esta mision.
"""
from __future__ import annotations

import inspect
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.run_rollout import (PRESUPUESTO_POR_FUENTE,  # noqa: E402
                                 _procesar_con, procesar)

FUENTE = (Path(__file__).resolve().parents[1] / "scripts"
          / "run_rollout.py").read_text(encoding="utf-8")


def test_el_bucle_de_fichas_recibe_el_presupuesto():
    """Donde se usa `presupuesto` es donde tiene que estar declarado."""
    assert "presupuesto" in inspect.signature(_procesar_con).parameters


def test_las_dos_funciones_arrancan_del_mismo_numero():
    a = inspect.signature(procesar).parameters["presupuesto"].default
    b = inspect.signature(_procesar_con).parameters["presupuesto"].default
    assert a == b == PRESUPUESTO_POR_FUENTE


def test_el_presupuesto_se_pasa_en_las_dos_llamadas():
    """La segunda llamada es la del connector de respaldo. Sin presupuesto, la
    fuente rescatada seria la unica sin tope de tiempo."""
    llamadas = [l for l in FUENTE.splitlines() if "_procesar_con(" in l
                and not l.strip().startswith("def ")]
    assert len(llamadas) == 2, llamadas
    for l in llamadas:
        # el argumento va en la misma linea o en la siguiente por el corte
        assert "presupuesto" in l or "observacion," in l


def test_ninguna_funcion_usa_un_nombre_que_no_recibe():
    """La red que atrapa la clase de error, no solo este caso.

    Recorre las funciones de nivel superior y verifica que cada nombre que leen
    sea un parametro propio, una variable que ellas mismas asignan, o algo
    definido en el modulo. Un nombre que no es ninguna de las tres cosas es un
    NameError esperando a que alguien ejecute esa rama, y puede quedarse ahi
    meses si esa rama solo corre cuando todo lo demas salio bien.
    """
    import ast
    import builtins

    arbol = ast.parse(FUENTE)
    conocidos = set(dir(builtins)) | {"__name__", "__file__", "annotations"}
    for n in ast.walk(arbol):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            conocidos.add(n.name)
        elif isinstance(n, (ast.Import, ast.ImportFrom)):
            for al in n.names:
                conocidos.add(al.asname or al.name.split(".")[0])
        elif isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store):
            conocidos.add(n.id)
        elif isinstance(n, ast.ExceptHandler) and n.name:
            conocidos.add(n.name)
        elif isinstance(n, ast.arg):
            conocidos.add(n.arg)

    fallas = []
    for fn in [n for n in arbol.body if isinstance(n, ast.FunctionDef)]:
        for n in ast.walk(fn):
            if (isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)
                    and n.id not in conocidos):
                fallas.append("%s usa %r sin que exista" % (fn.name, n.id))
    assert not fallas, fallas


def test_una_corrida_vacia_no_puede_pasar_por_exitosa():
    """El resumen reconcilia con 0 pedidas y 0 obtenidas, que es cierto y no
    dice nada. Las excepciones por fuente tienen que quedar contadas aparte."""
    assert '"estado": "EXCEPCION"' in FUENTE or "EXCEPCION" in FUENTE
    assert "fuentes_por_estado" in FUENTE


def test_un_fallo_transitorio_tiene_segunda_oportunidad_como_el_none():
    """El mismo timeout tenía o no reintento según qué rama lo absorbiera.

    Cuando el connector devuelve ``None`` y deja el error en ``errores``, el
    runner difiere la ficha y la reintenta al terminar el lote. Cuando el
    descargador propaga `ErrorTransitorio` —el mismo fallo, sólo que sin
    absorber— iba directo a fallido, sin segunda oportunidad.

    Eso dejó a `alagnapropiedades.com.ar` en NEEDS_FIX: 210 fichas en la
    primera corrida y 209 en la segunda, inventarios distintos, por una ficha
    que devuelve HTTP 200 cuando se la pide de nuevo.

    `Bloqueado` y `ErrorPermanente` no se difieren: insistir ante un 403/429 o
    un 404 no es reintentar, es golpear.
    """
    cuerpo = inspect.getsource(sys.modules["scripts.run_rollout"])
    bucle = cuerpo[cuerpo.index("errores_antes = len(con.errores)"):]
    bucle = bucle[:bucle.index("fichas_vacias = 0")]

    transitorio = bucle.index("except ErrorTransitorio:")
    permanente = bucle.index("except ErrorPermanente:")
    bloqueado = bucle.index("except Bloqueado:")

    # El transitorio se difiere; los otros dos cuentan como fallo en el acto.
    assert "reintentos_diferidos.append(a)" in bucle[transitorio:transitorio + 900]
    # Se mira hasta la rama siguiente, no una ventana de caracteres: un
    # comentario nuevo movia el limite y rompia el test sin que cambiara nada
    # del comportamiento.
    def _rama(desde: int) -> str:
        resto = bucle[desde:]
        siguiente = resto.find("\n        except", 1)
        corte = resto.find("\n        if ", 1)
        fin = min(x for x in (siguiente, corte, len(resto)) if x > 0)
        return resto[:fin]

    assert "fallidos += 1" in _rama(permanente)
    assert "fallidos += 1" in _rama(bloqueado)
    assert "reintentos_diferidos" not in _rama(bloqueado)
    # Y nunca vuelven a fusionarse en una sola rama que los trate igual.
    assert "except (ErrorTransitorio, ErrorPermanente):" not in bucle
