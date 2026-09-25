"""Lo que un conector importa del repo también es su huella.

`connectors/wasi.py` lee cada ficha con `scripts.wasi_fingerprint.campos_de_ficha`,
y ese archivo no entraba en la huella de `wasi`: cambiar un rótulo cambiaba lo
que se extrae sin invalidar una sola certificación. El 25-09 lo mostró
«Habitaciones:», que la plataforma usa en lugar de «Dormitorios:» y que dejó
sin dormitorios 86 de 91 fichas de `varesse`.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from scripts import agency_fingerprints as af  # noqa: E402
from scripts.agency_fingerprints import archivos_de_la_huella, fingerprint_components  # noqa: E402

CONECTORES = {"generico": "generic/sitemap", "tokko": "tokko", "wasi": "wasi",
              "wordpress": "wordpress", "century21": "century21"}


def _importados_del_repo(archivo: Path) -> set[Path]:
    arbol = ast.parse(archivo.read_text(encoding="utf-8"))
    salida = set()
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.ImportFrom) and nodo.module and nodo.module.split(".")[0] in (
                "scripts", "connectors", "scraper"):
            ruta = RAIZ / (nodo.module.replace(".", "/") + ".py")
            if ruta.exists():
                salida.add(ruta.resolve())
    return salida


def test_MUERDE_todo_modulo_propio_que_importa_un_conector_esta_en_su_huella(monkeypatch):
    faltan = {}
    original = Path.read_text
    for conector, estrategia in CONECTORES.items():
        leidos: set[str] = set()

        def registrar(self, *a, **k):
            leidos.add(str(self.resolve()))
            return original(self, *a, **k)

        monkeypatch.setattr(Path, "read_text", registrar)
        af._semantic_file_cacheado.cache_clear()
        af._archivo_sin_operativas.cache_clear()
        fingerprint_components(conector, estrategia)
        monkeypatch.setattr(Path, "read_text", original)
        importados = _importados_del_repo(RAIZ / "connectors" / f"{conector}.py")
        sin_huella = {p.name for p in importados if str(p) not in leidos}
        if sin_huella:
            faltan[conector] = sorted(sin_huella)
    assert faltan == {}


def test_la_guarda_de_los_workers_ve_el_parser_de_wasi():
    assert (RAIZ / "scripts" / "wasi_fingerprint.py").resolve() in {
        p.resolve() for p in archivos_de_la_huella()}
