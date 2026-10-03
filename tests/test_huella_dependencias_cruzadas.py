"""Lo que un codigo EJECUTA de otro modulo tambien es su huella.

Ventana semantica final (03-10). `wordpress.py` le pasa fichas a
`GenericoConnector.normalize` y lee el precio con `cuerpo_principal`; `wasi.py`
usa `generico.fuera_de_servicio`; el certificador audita WordPress y Century21
con `source_signals`, hecha de funciones de `generico.py`; el runner decide los
descartes sospechosos con `defect_triage`. Nada de eso entraba en la huella de
quien lo ejecuta: el P0 de KiteProp (d1f9fdf) cambio `cuerpo_principal` y dejo
vigentes certificaciones de WordPress que ya no se reproducian.

Y dentro de generico: `normalize`, que es comun, llamaba sin condicion a
`_fichas_en`, repartida en seis estrategias y ausente de las demas.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from scripts import agency_fingerprints as af  # noqa: E402

GENERICO = RAIZ / "connectors" / "generico.py"


def _de_estrategia() -> tuple[set[str], set[str]]:
    metodos = set().union(*af.GENERIC_STRATEGY_METHODS.values())
    funciones = set().union(*af.GENERIC_STRATEGY_FUNCTIONS.values())
    return metodos, funciones


def _clave_que_condiciona(cadena: list[ast.AST]) -> set[str]:
    """Las constantes de texto en la condicion de cada `if` que encierra el nodo
    por su rama verdadera. `cadena` va del nodo hacia arriba."""
    claves: set[str] = set()
    for hijo, padre in zip(cadena, cadena[1:]):
        if isinstance(padre, ast.If) and hijo in padre.body:
            prueba = padre.test
        elif isinstance(padre, ast.IfExp) and hijo is padre.body:
            prueba = padre.test
        else:
            continue
        claves |= {c.value for c in ast.walk(prueba)
                   if isinstance(c, ast.Constant) and isinstance(c.value, str)}
    return claves


def _referencias(nodo: ast.AST):
    """(nombre, es_metodo, cadena de ancestros) de cada referencia en `nodo`."""
    def bajar(n, cadena):
        if isinstance(n, ast.Name):
            yield n.id, False, cadena
        elif (isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name)
              and n.value.id in ("self", "cls", "GenericoConnector")):
            yield n.attr, True, cadena
        for h in ast.iter_child_nodes(n):
            yield from bajar(h, [h] + cadena)
    yield from bajar(nodo, [nodo])


def test_MUERDE_normalize_solo_ejecuta_de_una_estrategia_lo_que_su_clave_condiciona():
    arbol = ast.parse(GENERICO.read_text(encoding="utf-8"))
    funcs = {n.name: n for n in arbol.body if isinstance(n, ast.FunctionDef)}
    clase = next(n for n in arbol.body
                 if isinstance(n, ast.ClassDef) and n.name == "GenericoConnector")
    metodos = {n.name: n for n in clase.body if isinstance(n, ast.FunctionDef)}
    de_estrategia_m, de_estrategia_f = _de_estrategia()

    sin_condicion = []
    pila, vistos = [("normalize", True)], set()
    while pila:
        nombre, es_metodo = pila.pop()
        if (nombre, es_metodo) in vistos:
            continue
        vistos.add((nombre, es_metodo))
        nodo = metodos.get(nombre) if es_metodo else funcs.get(nombre)
        if nodo is None:
            continue
        for ref, ref_es_metodo, cadena in _referencias(nodo):
            propio = (ref in de_estrategia_m) if ref_es_metodo else (ref in de_estrategia_f)
            if not propio:
                pila.append((ref, ref_es_metodo))
                continue
            clave = af.LLAMADAS_CONDICIONADAS.get(ref)
            if clave is None or clave not in _clave_que_condiciona(cadena):
                sin_condicion.append((nombre, ref))
    assert sin_condicion == [], (
        "codigo de estrategia que el `normalize` comun ejecuta sin la clave que "
        "lo condiciona: es comun, sacalo de GENERIC_STRATEGY_*", sin_condicion)


def test_las_claves_de_estrategia_no_salen_de_wordpress():
    """WordPress le pasa su crudo a `normalize`: si pusiera una de estas claves,
    ejecutaria codigo de una estrategia que su huella no lleva."""
    arbol = ast.parse((RAIZ / "connectors" / "wordpress.py").read_text(encoding="utf-8"))
    textos = {c.value for c in ast.walk(arbol)
              if isinstance(c, ast.Constant) and isinstance(c.value, str)}
    assert set(af.LLAMADAS_CONDICIONADAS.values()) & textos == set()


def test_wordpress_lleva_el_codigo_comun_de_generico():
    wp = af.fingerprint_components("wordpress", "wordpress")
    gen = af.fingerprint_components("generico", "generic/sitemap")
    assert wp["generic/common"] == gen["generic/common"]


def test_wasi_lleva_solo_fuera_de_servicio_y_lo_que_lee():
    dump = af.fingerprint_components("wasi", "wasi")["generic/importado"].decode()
    for nombre in ("fuera_de_servicio", "RE_FUERA_DE_SERVICIO",
                   "TOPE_DE_PAGINA_DE_BAJA", "RE_PIDE_JAVASCRIPT"):
        assert nombre in dump, nombre
    assert "generic/common" not in af.fingerprint_components("wasi", "wasi")
    assert "name='normalize'" not in dump


def test_las_senales_genericas_del_certificador_van_donde_se_usan():
    for conector in ("wordpress", "century21"):
        dump = af.fingerprint_components(conector, conector)[
            "certifier/generic_signals"].decode()
        for nombre in ("cuerpo_principal", "_es_tabla_estructurada",
                       "_cuenta_de_ficha", "ETIQUETAS_DE_CONTEO"):
            assert nombre in dump, (conector, nombre)
    for conector in ("tokko", "wasi"):
        assert "certifier/generic_signals" not in af.fingerprint_components(
            conector, conector)


def test_los_conectores_con_senales_propias_son_los_del_certificador():
    arbol = ast.parse((RAIZ / "scripts" / "agency_certifier.py").read_text(encoding="utf-8"))
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Dict) and any(
                isinstance(v, ast.Constant) and v.value == "source_signals_tokko"
                for v in nodo.values):
            claves = {k.value for k in nodo.keys}
            break
    else:
        raise AssertionError("no encontre el mapa de senales de field_audit")
    assert claves == set(af.CONECTORES_CON_SENALES_PROPIAS)


def test_todo_lo_que_un_conector_importa_de_generico_esta_en_su_huella():
    for conector in ("tokko", "wasi", "wordpress", "century21"):
        importado = af._importado_de_generico(RAIZ / "connectors" / f"{conector}.py")
        componentes = af.fingerprint_components(conector, conector)
        if importado:
            assert ("generic/common" in componentes
                    or "generic/importado" in componentes), conector


def test_el_descarte_sospechoso_del_runner_esta_en_toda_huella():
    assert (RAIZ / "scripts" / "defect_triage.py").resolve() in {
        p.resolve() for p in af.archivos_de_la_huella()}
    for conector, estrategia in (("generico", "generic/html_catalog"),
                                 ("tokko", "tokko"), ("wasi", "wasi")):
        dump = af.fingerprint_components(conector, estrategia)[
            "shared/descarte_con_senal"].decode()
        assert "descarte_parecia_una_propiedad" in dump


def test_el_alcance_sigue_llamadas_y_constantes(tmp_path):
    modulo = tmp_path / "m.py"
    modulo.write_text(chr(10).join([
        "import re",
        "RE_A = re.compile('a')",
        "RE_B = re.compile('b')",
        "TABLA = {'x': RE_A}",
        "def ayuda(t):",
        "    return TABLA['x'].search(t)",
        "def raiz(t):",
        "    return ayuda(t)",
        "def otra(t):",
        "    return RE_B.search(t)",
        ""]), encoding="utf-8")
    m, f, c = af._alcance(modulo, "", (), {"raiz"})
    assert f == {"raiz", "ayuda"}
    assert c == {"TABLA", "RE_A"}
    dump = af._selected_nodes(modulo, "", m, f, constants=c).decode()
    assert "RE_B" not in dump and "otra" not in dump
