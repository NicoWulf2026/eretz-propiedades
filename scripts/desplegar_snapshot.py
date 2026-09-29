#!/usr/bin/env python
"""Despliegue controlado de una snapshot candidata YA construida y validada.

Reemplazar `ERETZ_API_CONTRACT/ERETZ_API_SNAPSHOT.sqlite3` es un DEPLOY: solo se
corre con autorizacion del usuario. No reconstruye nada en destino: promueve el
artefacto validado.

ANTES: sha256/tamano/conteos de la servida; respaldo en `_anteriores/<etiqueta>`
(copiado y verificado por hash si no existe); integrity_check de las dos;
ningun proceso con la servida o la candidata abiertas (apertura exclusiva: en
Windows `psutil.open_files` se cuelga); inventario comparado por id -solo se
aceptan ids que faltan si la candidata declara exactamente esa cantidad de
exclusiones por politica (`--exclusiones-declaradas`, clave del SUMMARY)-.

CAMBIO: copia a `.incoming` en el mismo volumen, fsync, verificacion de hash y
`os.replace` atomico.

DESPUES: hash, integrity_check, conteo, QA de API en proceso
(`scripts/benchmark_unified_api.py`) igual a la QA de la candidata (mismo
estado y total por caso), 0 GEO_CONFLICT en el mapa, medianas < 2 s. Cualquier
falla -> ROLLBACK inmediato desde el respaldo, verificado por hash.

Registro: `ERETZ_API_CONTRACT/_despliegues/DEPLOY_<fecha>.json`.
"""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
from ctypes import wintypes
from datetime import datetime
from pathlib import Path
try:  # raiz del estado operativo configurable (ERETZ_DATA_ROOT)
    from scripts.rutas_de_datos import dato  # noqa: E402
except ImportError:  # corrido como `python scripts/x.py`
    from rutas_de_datos import dato  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
SERVIDA_DIR = Path(str(dato('ERETZ_API_CONTRACT')))
NOMBRE = "ERETZ_API_SNAPSHOT.sqlite3"
RESUMEN = "ERETZ_API_SNAPSHOT_SUMMARY.json"
LATENCIA_MAXIMA_MS = 2000


def sha(ruta: Path) -> str:
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for bloque in iter(lambda: f.read(1 << 22), b""):
            h.update(bloque)
    return h.hexdigest()


def medir(ruta: Path) -> dict:
    con = sqlite3.connect(f"file:{ruta}?mode=ro", uri=True)
    try:
        return {"integrity": con.execute("pragma integrity_check").fetchone()[0],
                "propiedades": con.execute("select count(*) from propiedades").fetchone()[0],
                "agencias": con.execute("select count(distinct agency_id) from propiedades").fetchone()[0]}
    finally:
        con.close()


def ids(ruta: Path) -> set[str]:
    con = sqlite3.connect(f"file:{ruta}?mode=ro", uri=True)
    try:
        return {r[0] for r in con.execute("select id from propiedades")}
    finally:
        con.close()


def abiertos(*rutas: Path) -> list:
    """Rutas que otro proceso tiene abiertas (CreateFileW sin compartir falla)."""
    if os.name != "nt":
        return []
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateFileW.restype = wintypes.HANDLE
    k32.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
                                wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    hallados = []
    for ruta in rutas:
        h = k32.CreateFileW(str(ruta), 0x80000000, 0, None, 3, 0x80, None)
        if h in (None, wintypes.HANDLE(-1).value):
            hallados.append((str(ruta), ctypes.get_last_error()))
        else:
            k32.CloseHandle(h)
    return hallados


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--candidata", type=Path, required=True, help="carpeta con la snapshot y su QA")
    ap.add_argument("--etiqueta-respaldo", required=True, help="nombre de la carpeta en _anteriores")
    ap.add_argument("--exclusiones-declaradas", default=None,
                    help="clave del SUMMARY de la candidata con las filas excluidas por politica")
    ap.add_argument("--faltantes-esperados", type=int, default=None,
                    help="ids de la servida que la candidata ya no trae, medidos y auditados "
                         "de antemano (reemplaza a --exclusiones-declaradas cuando la servida "
                         "ya excluia una parte: v4j -> v4k faltan 121 de 152 declaradas)")
    ap.add_argument("--nuevos-esperados", type=int, default=0,
                    help="ids que la candidata agrega, medidos y auditados de antemano; por "
                         "defecto 0: una candidata que agrega sin declararlo aborta "
                         "(v4l: +9.330 de inventarios certificados vigentes)")
    ap.add_argument("--servida-dir", type=Path, default=SERVIDA_DIR)
    ap.add_argument("--automatico", action="store_true",
                    help="politica P2: las altas/bajas esperadas salen de CAMBIOS_DE_INVENTARIO.jsonl "
                         "y deben pasar TODAS las compuertas de compuertas_de_despliegue.py")
    ap.add_argument("--cert", type=Path,
                    default=Path(str(dato('ERETZ_AGENCY_CERTIFICATION_20260827'))))
    args = ap.parse_args()

    servida_dir = args.servida_dir
    servida, resumen = servida_dir / NOMBRE, servida_dir / RESUMEN
    cand, cand_resumen = args.candidata / NOMBRE, args.candidata / RESUMEN
    respaldo_dir = servida_dir / "_anteriores" / args.etiqueta_respaldo
    registro_dir = servida_dir / "_despliegues"
    sello = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
    reg: dict = {"inicio": sello, "candidata": str(args.candidata), "pasos": []}

    def paso(msg: str, **kw) -> None:
        print(msg, kw or "", flush=True)
        reg["pasos"].append({"t": datetime.now().isoformat(timespec="seconds"), "msg": msg, **kw})

    def guardar() -> None:
        registro_dir.mkdir(parents=True, exist_ok=True)
        (registro_dir / f"DEPLOY_{sello}.json").write_text(
            json.dumps(reg, ensure_ascii=False, indent=2), encoding="utf-8")

    def abortar(motivo: str) -> int:
        paso(f"ABORTADO: {motivo}")
        reg["resultado"] = "ABORTADO"
        guardar()
        return 1

    def rollback(motivo: str) -> int:
        paso("ROLLBACK", motivo=motivo)
        tmp = servida.with_name(NOMBRE + ".rollback")
        shutil.copyfile(respaldo_dir / NOMBRE, tmp)
        os.replace(tmp, servida)
        shutil.copyfile(respaldo_dir / RESUMEN, resumen)
        ok = sha(servida) == reg["antes"]["sha256"]
        paso("rollback verificado" if ok else "ROLLBACK SIN VERIFICAR", sha_igual=ok)
        reg["resultado"] = "ROLLBACK"
        guardar()
        return 2

    # ---------- ANTES ----------
    sha_servida, sha_cand = sha(servida), sha(cand)
    m_serv, m_cand = medir(servida), medir(cand)
    datos_cand = json.loads(cand_resumen.read_text(encoding="utf-8"))
    reg["antes"] = {"sha256": sha_servida, "bytes": servida.stat().st_size, **m_serv,
                    "resumen": json.loads(resumen.read_text(encoding="utf-8"))}
    reg["candidata_medida"] = {"sha256": sha_cand, "bytes": cand.stat().st_size, **m_cand,
                               "resumen": datos_cand}
    if sha_servida == sha_cand:
        return abortar("la candidata ya es la servida")
    if m_serv["integrity"] != "ok" or m_cand["integrity"] != "ok":
        return abortar("integrity_check")
    if not respaldo_dir.exists():
        respaldo_dir.mkdir(parents=True)
        shutil.copyfile(servida, respaldo_dir / NOMBRE)
        shutil.copyfile(resumen, respaldo_dir / RESUMEN)
    if sha(respaldo_dir / NOMBRE) != sha_servida:
        return abortar(f"el respaldo {respaldo_dir} no coincide con la servida")
    reg["respaldo"] = str(respaldo_dir)
    paso("antes registrado", servida=sha_servida[:12], candidata=sha_cand[:12], respaldo=str(respaldo_dir))
    en_uso = abiertos(servida, cand)
    if en_uso:
        return abortar(f"archivos abiertos: {en_uso}")

    ids_s, ids_c = ids(servida), ids(cand)
    faltan, sobran = ids_s - ids_c, ids_c - ids_s
    if args.automatico:
        sys.path.insert(0, str(REPO / "scripts"))
        from compuertas_de_despliegue import evaluar as compuertas
        fallas = compuertas(servida, args.candidata, args.cert, faltan, sobran)
        reg["compuertas_p2"] = fallas
        if fallas:
            return abortar("compuertas P2: " + "; ".join(fallas))
        paso("compuertas P2 superadas", faltan=len(faltan), sobran=len(sobran))
        args.faltantes_esperados, args.nuevos_esperados = len(faltan), len(sobran)
    declaradas = datos_cand.get(args.exclusiones_declaradas, 0) if args.exclusiones_declaradas else 0
    if args.faltantes_esperados is not None:
        declaradas = args.faltantes_esperados
    reg["inventario"] = {"ids_solo_en_servida": len(faltan), "ids_solo_en_candidata": len(sobran),
                         "exclusiones_declaradas": declaradas,
                         "nuevos_esperados": args.nuevos_esperados,
                         "muestra_solo_en_servida": sorted(faltan)[:50]}
    paso("inventario", solo_servida=len(faltan), solo_candidata=len(sobran), declaradas=declaradas)
    if len(sobran) != args.nuevos_esperados:
        return abortar(f"{len(sobran)} ids nuevos y se esperaban {args.nuevos_esperados}")
    if len(faltan) != declaradas:
        return abortar(f"faltan {len(faltan)} ids y la candidata declara {declaradas} exclusiones")

    # ---------- CAMBIO ----------
    entrante = servida.with_name(NOMBRE + ".incoming")
    shutil.copyfile(cand, entrante)
    with open(entrante, "rb+") as f:
        os.fsync(f.fileno())
    if sha(entrante) != sha_cand:
        entrante.unlink()
        return abortar("la copia entrante no coincide")
    os.replace(entrante, servida)
    shutil.copyfile(cand_resumen, resumen)
    paso("promovida por os.replace atomico")

    # ---------- DESPUES ----------
    if sha(servida) != sha_cand:
        return rollback("sha servida != candidata")
    m_new = medir(servida)
    reg["despues"] = {"sha256": sha_cand, **m_new}
    if m_new["integrity"] != "ok" or m_new["propiedades"] != m_cand["propiedades"]:
        return rollback(f"integrity/conteo: {m_new}")
    bench = registro_dir / f"API_BENCHMARK_{sello}.json"
    registro_dir.mkdir(parents=True, exist_ok=True)
    r = subprocess.run([sys.executable, "scripts/benchmark_unified_api.py", str(servida),
                        "--output", str(bench)], cwd=REPO, capture_output=True, text=True)
    if r.returncode != 0 or not bench.exists():
        return rollback(f"benchmark rc={r.returncode}: {r.stderr[-500:]}")
    b = json.loads(bench.read_text(encoding="utf-8"))
    ref_ruta = args.candidata / "API_BENCHMARK.json"
    qa = {"casos": len(b["cases"]), "total": b["total"], "geo_conflict": b["conflicts"],
          "geo_conflict_en_mapa": b["conflicting_map_points"],
          "medianas_ms": {c["case"]: c["median_ms"] for c in b["cases"]}, "salida": str(bench)}
    if ref_ruta.exists():
        ref = json.loads(ref_ruta.read_text(encoding="utf-8"))
        esperado = {c["case"]: (c["status"], c.get("total")) for c in ref["cases"]}
        obtenido = {c["case"]: (c["status"], c.get("total")) for c in b["cases"]}
        qa["igual_a_la_qa_de_la_candidata"] = esperado == obtenido
        if esperado != obtenido:
            reg["qa"] = qa
            return rollback("QA distinta de la de la candidata")
    reg["qa"] = qa
    paso("QA API", **{k: v for k, v in qa.items() if k != "medianas_ms"})
    if b["conflicting_map_points"] != 0:
        return rollback("GEO_CONFLICT en el mapa")
    if b["total"] != m_cand["propiedades"]:
        return rollback("total de la API distinto")
    lentos = {k: v for k, v in qa["medianas_ms"].items() if v > LATENCIA_MAXIMA_MS}
    if lentos:
        return rollback(f"latencias fuera de rango: {lentos}")

    reg["resultado"] = "DESPLEGADA"
    reg["rollback_manual"] = (f"copiar {respaldo_dir / NOMBRE} y {respaldo_dir / RESUMEN} sobre "
                              f"{servida_dir}; sha esperado {sha_servida}")
    guardar()
    paso("DESPLEGADA", registro=str(registro_dir / f"DEPLOY_{sello}.json"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
