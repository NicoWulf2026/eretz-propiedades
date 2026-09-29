"""Prueba de restore portable: desde un clone limpio, con ERETZ_DATA_ROOT en otra raiz,
reconstruir el estado operativo y detectar CUALQUIER acceso a D:\\INMO CAPITAL (audit hook).

Uso (desde el clone): ERETZ_DATA_ROOT=<raiz restaurada> python prueba_restore.py
"""
import hashlib
import json
import os
import sys
import time
from collections import Counter
from pathlib import Path

ORIGINAL = "d:\\inmo capital"
accesos: Counter = Counter()


def gancho(evento, args):
    if evento in ("open", "os.listdir", "os.scandir", "os.stat") and args:
        ruta = str(args[0]).replace("/", "\\").lower()
        if ruta.startswith(ORIGINAL):
            accesos[f"{evento}: {str(args[0])[:110]}"] += 1


sys.addaudithook(gancho)
sys.path[:0] = [os.getcwd(), os.path.join(os.getcwd(), "scripts")]
raiz = Path(os.environ["ERETZ_DATA_ROOT"])
resultado = {"raiz": str(raiz)}

# 1. integridad del restore contra el MANIFEST
m = json.load(open(raiz / "MANIFEST.json", encoding="utf-8"))
malos = []
for a in m["archivos"]:
    p = raiz / a["ruta"]
    if not p.exists():
        malos.append(("falta", a["ruta"]))
        continue
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 22), b""):
            h.update(b)
    if h.hexdigest() != a["sha256"]:
        malos.append(("hash", a["ruta"]))
resultado["archivos_verificados"] = len(m["archivos"])
resultado["archivos_con_problema"] = len(malos)

# 2. identidad, cola, ledger
from scripts.agency_certifier import load_catalog  # noqa: E402
from scripts.run_agency_certification_queue import ready_queue  # noqa: E402
from scripts.ledger_de_certificacion import vigentes_por_agencia  # noqa: E402
from scripts.rutas_de_datos import dato  # noqa: E402
cat = load_catalog(dato("ERETZ_SUPABASE_RECONCILIATION_V2_20260827"), dato("ERETZ_AGENCY_DATA"),
                   dato("agency_platform_directory.jsonl"))
resultado["catalogo"] = len(cat)
resultado["cola_ready"] = len(ready_queue(cat))
vig, _ = vigentes_por_agencia(dato("ERETZ_AGENCY_CERTIFICATION_20260827", "AGENCY_CERTIFICATION_RESULTS.jsonl"))
resultado["ledger_vigentes"] = dict(Counter(f["status"] for f in vig.values()))
resultado["paquetes"] = sum(1 for _ in dato("ERETZ_AGENCY_CERTIFICATION_20260827", "agencies").glob("*/certification.json"))
resultado["diferidas"] = sum(1 for _ in open(dato("ERETZ_AGENCY_CERTIFICATION_20260827", "AGENCY_DEFECTS_DIFERIDOS.jsonl"), encoding="utf-8"))

# 3. base canonica (via manifiesto) y geografia oficial
from scripts.preingestion_manifest import base_canonica, exigir_base_vigente  # noqa: E402
resultado["base_canonica"] = str(base_canonica())
exigir_base_vigente(base_canonica())
from connectors.geografia import geografia  # noqa: E402
resultado["localidades_georef"] = len(geografia().entidades)

# 4. snapshot: la decision de certificadas (lo que usa api_snapshot) y el Regression Gate
import sqlite3  # noqa: E402
from scripts.snapshot_certificadas import conocidas_de, decidir, paquetes_vigentes  # noqa: E402
t = time.time()
d = decidir(paquetes_vigentes(dato("ERETZ_AGENCY_CERTIFICATION_20260827", "agencies"),
                              dato("ERETZ_AGENCY_CERTIFICATION_20260827", "AGENCY_CERTIFICATION_RESULTS.jsonl")),
            conocidas_de(sqlite3.connect(f"file:{base_canonica().as_posix()}?mode=ro", uri=True)))
resultado["snapshot_nuevas_elegibles"] = len(d.nuevas)
resultado["snapshot_retirables"] = len(d.retirables)
from scripts.comparar_con_linea_base import main as gate  # noqa: E402
salida_gate = raiz / "GATE_PRUEBA.json"
gate(["--linea-base", "_regresion/ANTES_DEL_LOTE_2026-09-24.jsonl", "--desde", "2026-09-24T11:39:00",
      "--salida", str(salida_gate)])
resultado["regression_gate_pendientes"] = json.load(open(salida_gate, encoding="utf-8"))["pendientes_de_revision"]

# 5. el relanzador (dry-run) arma su plan sobre la raiz restaurada
from scripts.relanzar_la_cola import plan, SALIDA  # noqa: E402
resultado["relanzador_salida"] = str(SALIDA)

resultado["accesos_a_la_raiz_original"] = sum(accesos.values())
resultado["detalle_accesos"] = accesos.most_common(15)
print(json.dumps(resultado, ensure_ascii=False, indent=1))
