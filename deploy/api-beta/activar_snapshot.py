#!/usr/bin/env python
"""Activa, revierte e informa la snapshot que sirve la API beta (P21).

Corre DENTRO del contenedor, sobre el volumen persistente. La API abre
`ERETZ_API_SNAPSHOT` en cada pedido, asi que cambiar a que apunta ese enlace
cambia la snapshot servida sin reiniciar el proceso.

Disposicion del volumen (`/data` por defecto):
    incoming/<cualquier nombre>.sqlite3   lo que se subio y todavia no se verifico
    snapshots/<sha256>.sqlite3             verificadas, inmutables
    ERETZ_API_SNAPSHOT.sqlite3 -> snapshots/<sha256>.sqlite3   (enlace; lo que se sirve)
    HISTORIAL.jsonl                        cada activacion y cada rollback, con su evidencia

Activar exige, antes de tocar el enlace: sha256 igual al esperado (el que midio
LOCAL antes de subir), `integrity_check = ok`, filas > 0, indice de texto, y que
no sea la snapshot SINTETICA de QA. Si algo falla no se cambia nada.
El cambio del enlace es atomico (`os.replace`): no hay instante sin snapshot.

    python activar_snapshot.py activar --archivo /data/incoming/v4l-c.sqlite3 --sha256 <hex>
    python activar_snapshot.py rollback
    python activar_snapshot.py estado
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

VOLUMEN = Path(os.environ.get("ERETZ_BETA_DATA", "/data"))
ENLACE = "ERETZ_API_SNAPSHOT.sqlite3"
CONSERVAR = 3   # snapshots verificadas que quedan en el volumen (la activa incluida)


class Rechazada(Exception):
    """La snapshot no se activa. El mensaje dice por que."""


def _sha256(ruta: Path) -> str:
    h = hashlib.sha256()
    with ruta.open("rb") as fh:
        for bloque in iter(lambda: fh.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


def verificar(ruta: Path, sha_esperado: str, *, permitir_sintetica: bool = False) -> dict:
    if not ruta.is_file():
        raise Rechazada(f"no existe {ruta}")
    sha = _sha256(ruta)
    if sha != sha_esperado.lower():
        raise Rechazada(f"sha256 distinto: esperado {sha_esperado[:12]}, subido {sha[:12]}")
    con = sqlite3.connect(f"file:{ruta.as_posix()}?mode=ro", uri=True)
    try:
        integridad = con.execute("pragma integrity_check").fetchone()[0]
        if integridad != "ok":
            raise Rechazada(f"integrity_check: {integridad}")
        filas = con.execute("select count(*) from propiedades").fetchone()[0]
        busqueda = con.execute("select 1 from sqlite_master where name = 'busqueda'").fetchone()
        try:
            meta = dict(con.execute("select clave, valor from snapshot_meta").fetchall())
        except sqlite3.Error:
            meta = {}
    except sqlite3.Error as exc:
        raise Rechazada(f"no es una snapshot de la API: {exc}") from None
    finally:
        con.close()
    if filas <= 0:
        raise Rechazada("snapshot vacia")
    if not busqueda:
        raise Rechazada("snapshot sin indice de texto")
    if meta.get("sintetica") == "1" and not permitir_sintetica:
        raise Rechazada("es la snapshot SINTETICA de QA")
    return {"sha256": sha, "propiedades": filas, "bytes": ruta.stat().st_size,
            "sintetica": meta.get("sintetica") == "1"}


def _activa(volumen: Path) -> Path | None:
    enlace = volumen / ENLACE
    return enlace.resolve() if enlace.is_symlink() else None


def _apuntar(volumen: Path, destino: Path) -> None:
    enlace = volumen / ENLACE
    if enlace.exists() and not enlace.is_symlink():
        raise Rechazada(f"{enlace} es un archivo, no un enlace: moverlo a mano antes")
    tmp = volumen / (ENLACE + ".nuevo")
    if tmp.is_symlink() or tmp.exists():
        tmp.unlink()
    tmp.symlink_to(destino.relative_to(volumen))
    os.replace(tmp, enlace)


def _registrar(volumen: Path, evento: dict) -> None:
    evento = {"cuando": datetime.now(timezone.utc).isoformat(timespec="seconds"), **evento}
    with (volumen / "HISTORIAL.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(evento, ensure_ascii=False) + "\n")


def _historial(volumen: Path) -> list[dict]:
    ruta = volumen / "HISTORIAL.jsonl"
    if not ruta.exists():
        return []
    return [json.loads(x) for x in ruta.read_text(encoding="utf-8").splitlines() if x.strip()]


def activar(volumen: Path, archivo: Path, sha_esperado: str, *, permitir_sintetica: bool = False) -> dict:
    medida = verificar(archivo, sha_esperado, permitir_sintetica=permitir_sintetica)
    (volumen / "snapshots").mkdir(parents=True, exist_ok=True)
    destino = volumen / "snapshots" / f"{medida['sha256']}.sqlite3"
    anterior = _activa(volumen)
    if anterior == destino.resolve():
        raise Rechazada("esa snapshot ya es la activa")
    if destino.exists():
        if _sha256(destino) != medida["sha256"]:
            raise Rechazada(f"{destino.name} existe con otro contenido")
        archivo.unlink()
    else:
        os.replace(archivo, destino)
    os.chmod(destino, 0o444)
    _apuntar(volumen, destino)
    # Lo que se sirve es lo que se verifico: se relee por el enlace.
    servida = verificar(volumen / ENLACE, medida["sha256"], permitir_sintetica=permitir_sintetica)
    evento = {"accion": "ACTIVAR", **servida,
              "anterior": anterior.name if anterior else None}
    _registrar(volumen, evento)
    _podar(volumen)
    return evento


def rollback(volumen: Path) -> dict:
    """Vuelve a la snapshot activa antes de la ultima activacion."""
    activa = _activa(volumen)
    if activa is None:
        raise Rechazada("no hay snapshot activa")
    for evento in reversed(_historial(volumen)):
        if evento["accion"] == "ACTIVAR" and f"{evento['sha256']}.sqlite3" == activa.name:
            anterior = evento.get("anterior")
            break
    else:
        raise Rechazada("el historial no dice cual era la anterior")
    if not anterior:
        raise Rechazada("la activa fue la primera: no hay a donde volver")
    destino = volumen / "snapshots" / anterior
    medida = verificar(destino, anterior.removesuffix(".sqlite3"), permitir_sintetica=True)
    _apuntar(volumen, destino)
    evento = {"accion": "ROLLBACK", **medida, "desde": activa.name}
    _registrar(volumen, evento)
    return evento


def _podar(volumen: Path) -> None:
    """Deja las CONSERVAR mas recientes; nunca la activa ni la anterior."""
    activa = _activa(volumen)
    protegidas = {activa.name} if activa else set()
    for evento in reversed(_historial(volumen)):
        if evento["accion"] == "ACTIVAR" and evento.get("anterior"):
            protegidas.add(evento["anterior"])
            break
    guardadas = sorted((volumen / "snapshots").glob("*.sqlite3"),
                       key=lambda p: p.stat().st_mtime, reverse=True)
    for vieja in guardadas[CONSERVAR:]:
        if vieja.name not in protegidas:
            vieja.chmod(0o644)
            vieja.unlink()


def estado(volumen: Path) -> dict:
    activa = _activa(volumen)
    return {"volumen": str(volumen), "activa": activa.name if activa else None,
            "guardadas": sorted(p.name for p in (volumen / "snapshots").glob("*.sqlite3"))
            if (volumen / "snapshots").exists() else [],
            "ultimos_eventos": _historial(volumen)[-5:]}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--volumen", type=Path, default=VOLUMEN)
    sub = ap.add_subparsers(dest="orden", required=True)
    a = sub.add_parser("activar")
    a.add_argument("--archivo", type=Path, required=True)
    a.add_argument("--sha256", required=True, help="el que midio LOCAL antes de subir")
    a.add_argument("--permitir-sintetica", action="store_true", help="solo para ensayos")
    sub.add_parser("rollback")
    sub.add_parser("estado")
    args = ap.parse_args(argv)
    try:
        if args.orden == "activar":
            salida = activar(args.volumen, args.archivo, args.sha256,
                             permitir_sintetica=args.permitir_sintetica)
        elif args.orden == "rollback":
            salida = rollback(args.volumen)
        else:
            salida = estado(args.volumen)
    except Rechazada as exc:
        print(json.dumps({"resultado": "RECHAZADA", "motivo": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(salida, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
