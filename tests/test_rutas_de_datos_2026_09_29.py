"""El estado operativo vive bajo una raiz configurable (checkpoint cloud, 29-09)."""
from __future__ import annotations

import ast
import io
import re
import tokenize
from pathlib import Path

from scripts.rutas_de_datos import RAIZ_POR_DEFECTO, dato, raiz_de_datos

RAIZ_REPO = Path(__file__).resolve().parents[1]
NUCLEO = [
    "api/v2.py", "connectors/geografia.py", "scripts/preingestion_manifest.py",
    "scripts/agency_certifier.py", "scripts/run_agency_certification_queue.py",
    "scripts/run_rollout.py", "scripts/relanzar_la_cola.py", "scripts/vigilante_de_paros.py",
    "scripts/interruptor_eretz.py", "scripts/regimen_de_workers.py", "scripts/api_snapshot.py",
    "scripts/verificar_retiros.py", "scripts/desplegar_snapshot.py",
    "scripts/comparar_con_linea_base.py", "scripts/geo_coverage_audit.py",
    "scripts/verificar_webs_del_directorio.py", "scripts/plan_de_escritura.py",
    "scripts/property_freshest.py", "scripts/diferir_por_precedente.py",
]


def test_sin_variable_es_la_raiz_de_la_maquina_original(monkeypatch):
    monkeypatch.delenv("ERETZ_DATA_ROOT", raising=False)
    assert raiz_de_datos() == Path(RAIZ_POR_DEFECTO)


def test_la_variable_mueve_todo_el_estado(monkeypatch, tmp_path):
    monkeypatch.setenv("ERETZ_DATA_ROOT", str(tmp_path))
    assert dato("ERETZ_GEO") == tmp_path / "ERETZ_GEO"
    assert dato("ERETZ_AGENCY_CERTIFICATION_20260827", "agencies") == \
        tmp_path / "ERETZ_AGENCY_CERTIFICATION_20260827" / "agencies"


def test_MUERDE_el_nucleo_no_vuelve_a_escribir_la_ruta_de_la_maquina():
    r"""Una ruta completa a D:\INMO CAPITAL en un literal del nucleo no se restaura en otra maquina."""
    prefijo = re.compile(r"^[Dd]:[\/]+INMO CAPITAL")
    culpables = []
    for rel in NUCLEO:
        texto = (RAIZ_REPO / rel).read_text(encoding="utf-8")
        for tok in tokenize.generate_tokens(io.StringIO(texto).readline):
            if tok.type == tokenize.STRING:
                try:
                    valor = ast.literal_eval(tok.string)
                except Exception:
                    continue
                if isinstance(valor, str) and prefijo.match(valor):
                    culpables.append(f"{rel}:{tok.start[0]}")
    assert culpables == []


def test_MUERDE_las_rutas_absolutas_del_manifiesto_se_reubican_en_la_raiz_nueva(monkeypatch, tmp_path):
    r"""ERETZ_DATA_MANIFEST.json guarda rutas bajo D:\INMO CAPITAL: restaurado en otra raiz, se reubican."""
    from scripts.preingestion_manifest import _rebasar
    monkeypatch.setenv("ERETZ_DATA_ROOT", str(tmp_path))
    ruta = r"D:\INMO CAPITAL\ERETZ_PREINGESTION_REBUILD_20260903\PREINGESTION_REBUILD.sqlite3"
    assert _rebasar(ruta) == tmp_path / "ERETZ_PREINGESTION_REBUILD_20260903" / "PREINGESTION_REBUILD.sqlite3"
    assert _rebasar("C:/otro/lugar.sqlite3") == Path("C:/otro/lugar.sqlite3")
