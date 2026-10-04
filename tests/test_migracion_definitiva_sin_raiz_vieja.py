"""Migracion definitiva (04-10): el codigo ACTIVO no depende de la raiz vieja ni de nombres viejos.

ACTIVO = la clausura de imports desde lo que de verdad corre: tareas programadas (relanzador,
vigilante), cola y certificador, huellas, constructor de snapshot, compuertas, Regression Gate,
QA y API. Ninguna cadena de esa clausura puede empezar con una raiz vieja (`D:/INMO CAPITAL`,
`E:/INMO CAPITAL`) ni presentar el proyecto con un nombre anterior (InmoLink, InmoCapital,
URLink). `rutas_de_datos.RAICES_HISTORICAS` es la unica excepcion: reubica rutas guardadas.
"""
from __future__ import annotations

import ast
import io
import re
import tokenize
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
ENTRADAS = ["scripts/relanzar_la_cola.py", "scripts/vigilante_de_paros.py",
            "scripts/run_agency_certification_queue.py", "scripts/eretz_automatizacion.py",
            "scripts/api_snapshot.py", "scripts/compuertas_de_despliegue.py",
            "scripts/gate_de_snapshots.py", "scripts/qa_navegador_sintetica.py",
            "scripts/desplegar_snapshot.py", "scripts/agency_certifier.py",
            "scripts/agency_fingerprints.py", "api/v2.py", "api/main.py"]
EXCEPCIONES = {"scripts/rutas_de_datos.py"}
RAIZ_VIEJA = re.compile("^[A-Za-z]:[/" + chr(92) * 2 + "]+INMO CAPITAL", re.I)
NOMBRE_VIEJO = re.compile(r"inmo ?link|inmocapital|ur ?l ?ink", re.I)
# Contratos persistidos que se conservan como alias de compatibilidad (ver
# docs/agent/MIGRACION_DEFINITIVA_2026-10-04.md): claves ya guardadas en datos.
ALIAS = {"inmocapital", "_inmocapital", "inmocapital_source"}


def _ruta(modulo: str) -> str | None:
    for cand in (modulo.replace(".", "/") + ".py", modulo.replace(".", "/") + "/__init__.py"):
        if (RAIZ / cand).exists():
            return cand
    return None


def clausura() -> set[str]:
    visto: set[str] = set()
    pend = [e for e in ENTRADAS if (RAIZ / e).exists()]
    while pend:
        f = pend.pop()
        if f in visto:
            continue
        visto.add(f)
        arbol = ast.parse((RAIZ / f).read_text(encoding="utf-8"))
        base = str(Path(f).parent).replace("/", ".").replace(chr(92), ".")
        for n in ast.walk(arbol):
            mods: list[str] = []
            if isinstance(n, ast.Import):
                mods = [a.name for a in n.names]
            elif isinstance(n, ast.ImportFrom) and n.module:
                pre = base + "." if n.level else ""
                mods = [pre + n.module] + [pre + n.module + "." + a.name for a in n.names]
            for m in mods:
                otro = m.split(".", 1)[-1] if m.startswith("scripts.") else "scripts." + m
                for cand in (m, otro):
                    r = _ruta(cand)
                    if r and r not in visto:
                        pend.append(r)
    return visto


def test_la_clausura_activa_es_la_esperada():
    activos = clausura()
    assert {"scripts/relanzar_la_cola.py", "scripts/api_snapshot.py", "connectors/generico.py",
            "scripts/rutas_de_datos.py"} <= activos


def test_MUERDE_ninguna_cadena_activa_apunta_a_la_raiz_vieja_ni_usa_un_nombre_viejo():
    culpables = []
    for rel in sorted(clausura() - EXCEPCIONES):
        texto = (RAIZ / rel).read_text(encoding="utf-8")
        for tok in tokenize.generate_tokens(io.StringIO(texto).readline):
            if tok.type != tokenize.STRING:
                continue
            try:
                valor = ast.literal_eval(tok.string)
            except Exception:
                continue
            if not isinstance(valor, str) or valor in ALIAS:
                continue
            if RAIZ_VIEJA.match(valor) or (NOMBRE_VIEJO.search(valor) and "\n" not in valor):
                culpables.append(f"{rel}:{tok.start[0]}")
    assert culpables == []
