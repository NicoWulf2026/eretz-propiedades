"""Empaqueta el estado operativo durable de ERETZ que vive FUERA del repo (checkpoint cloud).

Salida: D:\\INMO CAPITAL\\ERETZ_STATE_CHECKPOINT_2026-09-29\\
  ERETZ_STATE_2026-09-29.tar.gz   el estado, con las rutas relativas a D:\\INMO CAPITAL\\
  MANIFEST.json                    cada archivo: ruta, bytes, sha256; y el sha256 del tar
No incluye secretos: no toca .env ni credenciales; solo artefactos de datos.
"""
import hashlib
import json
import os
import tarfile
import time
from pathlib import Path

RAIZ = Path(r"D:\INMO CAPITAL")
SALIDA = RAIZ / "ERETZ_STATE_CHECKPOINT_2026-09-29"
SALIDA.mkdir(exist_ok=True)
CERT = "ERETZ_AGENCY_CERTIFICATION_20260827"
V2 = "ERETZ_SUPABASE_RECONCILIATION_V2_20260827"

# Estado de la cola y la certificacion (no regenerable).
entradas = [
    f"{CERT}/AGENCY_CERTIFICATION_RESULTS.jsonl",
    f"{CERT}/AGENCY_DEFECTS_DIFERIDOS.jsonl",
    f"{CERT}/AGENCY_DEFECT_QUEUE.jsonl",
    f"{CERT}/ERETZ_FAMILIAS_DETENIDAS.jsonl",
    f"{CERT}/ERETZ_WORKERS.json",
    f"{CERT}/ERETZ_WORKERS_REGIMEN.jsonl",
    f"{CERT}/_regresion",
    f"{CERT}/agencies",
    # Identidad y fuentes (load_catalog).
    f"{V2}/AGENCY_ID_RESOLUTION_FINAL.jsonl",
    f"{V2}/LIVE_AGENCY_IDENTITY_VALIDATION.jsonl",
    "ERETZ_AGENCY_DATA",
    "agency_platform_directory.jsonl",
    # Base canonica congelada y geografia oficial.
    "ERETZ_PREINGESTION_REBUILD_20260903",
    "ERETZ_GEO",
]
EXCLUIR_SUFIJOS = (".lock", ".claim", ".tmp", ".env")


def archivos():
    for e in entradas:
        p = RAIZ / e
        if p.is_file():
            yield p
        elif p.is_dir():
            for r, _, fs in os.walk(p):
                for f in fs:
                    if not f.endswith(EXCLUIR_SUFIJOS) and ".env" not in f:
                        yield Path(r) / f


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 22), b""):
            h.update(b)
    return h.hexdigest()


manifiesto = {"creado": time.strftime("%Y-%m-%dT%H:%M:%S"), "raiz": str(RAIZ), "archivos": []}
tar_ruta = SALIDA / "ERETZ_STATE_2026-09-29.tar.gz"
with tarfile.open(tar_ruta, "w:gz", compresslevel=6) as tar:
    for p in archivos():
        rel = p.relative_to(RAIZ).as_posix()
        manifiesto["archivos"].append({"ruta": rel, "bytes": p.stat().st_size, "sha256": sha(p)})
        tar.add(p, arcname=rel)
manifiesto["tar"] = {"nombre": tar_ruta.name, "bytes": tar_ruta.stat().st_size, "sha256": sha(tar_ruta)}
manifiesto["total_archivos"] = len(manifiesto["archivos"])
manifiesto["total_bytes"] = sum(a["bytes"] for a in manifiesto["archivos"])
(SALIDA / "MANIFEST.json").write_text(json.dumps(manifiesto, ensure_ascii=False, indent=1), encoding="utf-8")
print(json.dumps({k: v for k, v in manifiesto.items() if k != "archivos"}, ensure_ascii=False))
