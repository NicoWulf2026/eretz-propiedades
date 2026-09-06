"""Ningún módulo semántico queda fuera de la huella."""
from __future__ import annotations

import ast
from pathlib import Path

from scripts.agency_fingerprints import (_semantic_file,
                                         fingerprint_components)

RAIZ = Path(__file__).resolve().parents[1]

# Módulos que el pipeline importa pero que NO deciden qué se extrae.
# Cada exención tiene que poder justificarse; la lista se mira, no se amplía
# por comodidad.
OPERACIONALES = {"__init__"}


def _importados(modulo: Path) -> set[str]:
    """Los módulos de `connectors/` que este archivo importa."""
    arbol = ast.parse(modulo.read_text(encoding="utf-8"))
    fuera: set[str] = set()
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.ImportFrom) and nodo.level == 1 and nodo.module:
            fuera.add(nodo.module.split(".")[0])
        elif isinstance(nodo, ast.ImportFrom) and (nodo.module or "").startswith(
                "connectors."):
            fuera.add(nodo.module.split(".", 1)[1].split(".")[0])
    return fuera


def _cubiertos_por_contenido() -> set[str]:
    """Los módulos de `connectors/` cuyo contenido entra en alguna huella.

    Se comparan PAYLOADS, no nombres: `formularios.py` viaja como
    `strategy/php_form_transport`, y buscarlo por nombre lo daría por huérfano
    cuando en realidad está correctamente acotado a la única estrategia que lo
    usa.
    """
    payloads: set[bytes] = set()
    for connector, estrategia in (("generico", "generic/html_catalog"),
                                  ("generico", "generic/php_ajax_search"),
                                  ("tokko", "tokko"), ("wordpress", "wordpress"),
                                  ("wasi", "wasi"), ("century21", "century21")):
        payloads |= set(fingerprint_components(connector, estrategia).values())

    cubiertos = set()
    for archivo in (RAIZ / "connectors").glob("*.py"):
        if _semantic_file(archivo) in payloads:
            cubiertos.add(archivo.stem)
    # `generico.py` entra troceado por metodos, no como archivo entero.
    return cubiertos | {"generico"}


def test_ningun_modulo_semantico_importado_queda_fuera_de_la_huella():
    """Ya aprendimos este error dos veces y en las dos direcciones: código
    operacional adentro produjo resets falsos, y código semántico afuera
    produjo certificaciones falsamente vigentes.

    `connectors/coherencia.py` fue el tercer caso: `generico.py` lo importa
    para decidir qué atributos se descartan, y no era componente de ninguna
    huella. Cambiar esa regla habría cambiado lo que se extrae sin invalidar
    una sola certificación.

    Un módulo nuevo que nadie registra es el mismo agujero que tuvo
    `discover()`.
    """
    cubiertos = _cubiertos_por_contenido()
    huerfanos = []
    for modulo in ("base.py", "generico.py", "tokko.py", "wordpress.py",
                   "wasi.py", "century21.py"):
        for importado in _importados(RAIZ / "connectors" / modulo):
            if importado in OPERACIONALES or importado in cubiertos:
                continue
            huerfanos.append(f"{modulo} importa {importado}")

    assert not huerfanos, (
        "modulos semanticos fuera de toda huella: " + "; ".join(sorted(huerfanos)))


def test_los_componentes_compartidos_estan_en_todas_las_estrategias():
    """`shared/*` tiene que valer para todos: si una familia no lo incluye,
    cambiar el código compartido no invalidaría sus certificaciones."""
    compartidos = {"shared/base", "shared/geografia", "shared/texto",
                   "shared/runner", "shared/certifier", "shared/coherencia"}
    for connector, estrategia in (("generico", "generic/html_catalog"),
                                  ("tokko", "tokko"), ("wordpress", "wordpress"),
                                  ("wasi", "wasi"), ("century21", "century21")):
        faltan = compartidos - set(fingerprint_components(connector, estrategia))
        assert not faltan, f"{connector}/{estrategia} no incluye {sorted(faltan)}"
