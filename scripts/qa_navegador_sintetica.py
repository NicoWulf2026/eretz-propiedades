#!/usr/bin/env python
"""QA de navegador de punta a punta sobre la snapshot SINTETICA (sin estado LOCAL).

Arma la snapshot (`snapshot_sintetica.py`), levanta la API v2 sobre ella, levanta
el frontend (`next dev`) apuntando a esa API, corre la e2e de Playwright y deja un
informe JSON con el SHA del codigo, el de la snapshot y el resultado por test.
Al terminar baja los dos procesos, pase lo que pase.

Sirve en CLOUD, en CI y en la PC LOCAL (Windows): no lee nada de ERETZ_DATA_ROOT.
No reemplaza la QA sobre la snapshot servida (P16 #8 pide el SHA exacto contra el
backend real); la complementa: prueba el codigo sin depender de los datos.

    python scripts/qa_navegador_sintetica.py --salida _scratch/qa_sintetica
    python scripts/qa_navegador_sintetica.py --salida ... --e2e e2e/test_api_v2_discovery.py
    # Chromium ya instalado en otra ruta (no se descarga nada):
    ERETZ_E2E_CHROMIUM=/opt/pw-browsers/chromium python scripts/qa_navegador_sintetica.py ...
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
FRONTEND = RAIZ / "frontend"
sys.path.insert(0, str(RAIZ))

from scripts.snapshot_sintetica import CASOS, construir  # noqa: E402

# Lo que la e2e necesita saber de la snapshot con la que corre.
CONSULTA_SIN_COORDENADAS = "Casa amplia en alquiler sin mapa"


def _esperar(url: str, *, codigo: int = 200, segundos: float = 300) -> None:
    limite = time.monotonic() + segundos
    ultimo = None
    while time.monotonic() < limite:
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                if r.status == codigo:
                    return
                ultimo = r.status
        except urllib.error.HTTPError as e:
            ultimo = e.code
        except (urllib.error.URLError, OSError) as e:
            ultimo = type(e).__name__
        time.sleep(2)
    raise TimeoutError(f"{url} no respondio {codigo} en {segundos:.0f} s (ultimo: {ultimo})")


def _lanzar(cmd: list[str], *, cwd: Path, env: dict[str, str], log: Path) -> subprocess.Popen:
    fh = log.open("w", encoding="utf-8")
    extra: dict = ({"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt"
                   else {"start_new_session": True})
    return subprocess.Popen(cmd, cwd=cwd, env=env, stdout=fh, stderr=subprocess.STDOUT, **extra)


def _bajar(proceso: subprocess.Popen | None) -> None:
    if proceso is None or proceso.poll() is not None:
        return
    if os.name == "nt":
        # `next dev` deja hijos: se baja el arbol entero.
        subprocess.run(["taskkill", "/PID", str(proceso.pid), "/T", "/F"],
                       capture_output=True, check=False)
    else:
        try:
            os.killpg(proceso.pid, signal.SIGTERM)
        except ProcessLookupError:
            return
    try:
        proceso.wait(timeout=20)
    except subprocess.TimeoutExpired:
        if os.name != "nt":
            os.killpg(proceso.pid, signal.SIGKILL)
        proceso.wait(timeout=10)


def _sha(ruta: Path) -> str:
    return hashlib.sha256(ruta.read_bytes()).hexdigest()


def _commit() -> dict:
    """El SHA y si el arbol tenia cambios: con cambios, el SHA solo no es lo probado."""
    r = subprocess.run(["git", "rev-parse", "HEAD"], cwd=RAIZ, capture_output=True, text=True)
    s = subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"], cwd=RAIZ,
                       capture_output=True, text=True)
    return {"sha": r.stdout.strip() or None, "arbol_con_cambios": bool(s.stdout.strip())}


def _resultados(junit: Path) -> dict:
    if not junit.exists():
        return {"total": 0, "fallidos": [], "salteados": 0}
    raiz = ET.parse(junit).getroot()
    casos = raiz.iter("testcase")
    fallidos, salteados, total = [], 0, 0
    for caso in casos:
        total += 1
        nombre = f"{caso.get('classname')}::{caso.get('name')}"
        if caso.find("failure") is not None or caso.find("error") is not None:
            fallidos.append(nombre)
        elif caso.find("skipped") is not None:
            salteados += 1
    return {"total": total, "pasados": total - len(fallidos) - salteados,
            "fallidos": fallidos, "salteados": salteados}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--salida", type=Path, required=True, help="carpeta para snapshot, logs e informe")
    ap.add_argument("--puerto-api", type=int, default=8765)
    ap.add_argument("--puerto-web", type=int, default=3100)
    ap.add_argument("--e2e", nargs="*", default=["e2e"],
                    help="rutas de pytest relativas a frontend/ (por defecto toda la e2e)")
    args = ap.parse_args()

    salida = args.salida.resolve()
    salida.mkdir(parents=True, exist_ok=True)
    snapshot = salida / "ERETZ_API_SNAPSHOT.sqlite3"
    resumen = construir(snapshot)

    base_api = f"http://127.0.0.1:{args.puerto_api}"
    base_web = f"http://127.0.0.1:{args.puerto_web}"
    env = {**os.environ, "PYTHON_DOTENV_DISABLED": "1", "NEXT_TELEMETRY_DISABLED": "1"}
    env_api = {**env, "ERETZ_API_SNAPSHOT": str(snapshot), "ERETZ_ALLOW_SYNTHETIC_SNAPSHOT": "1"}
    env_web = {**env, "ERETZ_API_V2_BASE_URL": base_api}
    npx = shutil.which("npx") or "npx"

    api = web = None
    informe: dict = {
        "inicio": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "commit": _commit(),
        "snapshot": {**resumen, "sha256": _sha(snapshot)},
        "api": base_api, "web": base_web, "e2e": args.e2e,
        "alcance": "QA de navegador sobre la snapshot SINTETICA: prueba el codigo, no los datos.",
    }
    codigo = 1
    try:
        api = _lanzar([sys.executable, "-m", "uvicorn", "api.main:app", "--host", "127.0.0.1",
                       "--port", str(args.puerto_api)], cwd=RAIZ, env=env_api, log=salida / "api.log")
        _esperar(f"{base_api}/readyz", segundos=60)
        web = _lanzar([npx, "next", "dev", "-p", str(args.puerto_web), "-H", "127.0.0.1"],
                      cwd=FRONTEND, env=env_web, log=salida / "web.log")
        _esperar(f"{base_web}/propiedades", segundos=600)
        junit = salida / "e2e_junit.xml"
        env_e2e = {**env, "ERETZ_E2E_BASE_URL": base_web,
                   "ERETZ_E2E_SIN_COORDENADAS_ID": CASOS["sin_coordenadas"],
                   "ERETZ_E2E_SIN_COORDENADAS_Q": CONSULTA_SIN_COORDENADAS,
                   "ERETZ_E2E_SINTETICA_CASOS": json.dumps(CASOS)}
        corrida = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
             f"--junitxml={junit}", *args.e2e],
            cwd=FRONTEND, env=env_e2e, capture_output=True, text=True)
        (salida / "e2e.log").write_text(corrida.stdout + corrida.stderr, encoding="utf-8")
        informe["resultado"] = _resultados(junit)
        informe["pytest_exit"] = corrida.returncode
        codigo = 0 if corrida.returncode == 0 else 1
    except Exception as exc:  # el informe tiene que decir por que no corrio
        informe["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        _bajar(web)
        _bajar(api)
        informe["fin"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        (salida / "QA_NAVEGADOR_SINTETICA.json").write_text(
            json.dumps(informe, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: informe.get(k) for k in ("commit", "resultado", "error")}, ensure_ascii=False))
    return codigo


if __name__ == "__main__":
    raise SystemExit(main())
