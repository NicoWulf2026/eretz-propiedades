#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Replay: re-extraer las fichas de una agencia desde el almacen de paginas, SIN red, con el codigo actual.

Mision 08-10 (plan, punto 6). Cambiar un extractor obligaba a recertificar bajando catalogos enteros otra vez
(~2/3 de la capacidad de la cola). Con las paginas guardadas (`almacen_de_paginas.py`), esto contesta antes
de aplicar un arreglo: con el extractor de HOY, ¿que campos de cada ficha certificada cambian, se recuperan o
se pierden? Es el replay de P4 (regresion antes de tocar la huella) sin costo de red.

- Lee el paquete vigente de la agencia (`properties_run2.jsonl`) y el indice del almacen.
- Para cada ficha con pagina guardada, corre `normalize` del MISMO conector del paquete con un descargador
  que solo sirve desde el almacen (una URL no guardada es ErrorPermanente: nunca sale a la red).
- Compara campo por campo y resume: igual / recuperado / perdido / cambiado, con ejemplos.

No escribe nada fuera de su salida. `database_writes: 0`.

    python scripts/replay_desde_almacen.py "roomix:alguna agencia" [--json salida.json]
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

sys.path[:0] = [str(Path(__file__).resolve().parents[1]), str(Path(__file__).resolve().parent)]
from connectors.base import ErrorPermanente, Fuente  # noqa: E402
from scripts.almacen_de_paginas import AlmacenDePaginas  # noqa: E402
from scripts.rutas_de_datos import dato  # noqa: E402

CAMPOS = ("titulo", "descripcion", "precio", "moneda", "operacion", "tipo_propiedad", "direccion", "barrio",
          "ciudad", "provincia", "latitud", "longitud", "dormitorios", "banos", "ambientes", "superficie_total",
          "superficie_cubierta")


def indice_de(almacen: Path, agencia: str | None = None) -> dict[str, str]:
    """url -> sha256 de la ultima descarga guardada (de esa agencia si se indica)."""
    ultimo: dict[str, tuple[str, str]] = {}
    for archivo in sorted((almacen / "indice").glob("*.jsonl")):
        for linea in archivo.read_text(encoding="utf-8", errors="replace").splitlines():
            if not linea.strip():
                continue
            try:
                f = json.loads(linea)
            except ValueError:
                continue
            if agencia and f.get("canonical_agency_id") not in (None, agencia):
                continue
            previo = ultimo.get(f["url"])
            if previo is None or f.get("bajada_en", "") >= previo[0]:
                ultimo[f["url"]] = (f.get("bajada_en", ""), f["sha256"])
    return {u: sha for u, (_t, sha) in ultimo.items()}


class DescargadorDelAlmacen:
    """Sirve paginas guardadas; lo que no esta guardado NO se baja: ErrorPermanente."""

    def __init__(self, almacen: AlmacenDePaginas, indice: dict[str, str]) -> None:
        self.almacen, self.indice = almacen, indice
        self.servidas = 0
        self.faltantes: list[str] = []
        self.pedidos = 0
        self.bytes_bajados = 0

    def bajar(self, url: str) -> str:
        sha = self.indice.get(url)
        cuerpo = self.almacen.leer(sha) if sha else None
        if cuerpo is None:
            self.faltantes.append(url)
            raise ErrorPermanente("NO_ALMACENADA")
        self.servidas += 1
        return cuerpo

    def __getattr__(self, nombre: str) -> Any:
        # El conector puede consultar robots, hosts leidos, etc.: sin red, todo es neutro.
        if nombre in ("permite_robots", "hubo_contacto"):
            return lambda *a, **k: True
        raise AttributeError(nombre)


def _igual(a: Any, b: Any) -> bool:
    if isinstance(a, float) or isinstance(b, float):
        try:
            return abs(float(a) - float(b)) < 1e-6
        except (TypeError, ValueError):
            return a == b
    return a == b


def comparar(viejas: list[dict[str, Any]], nuevas: dict[str, dict[str, Any]]) -> dict[str, Any]:
    resumen = {c: collections.Counter() for c in CAMPOS}
    ejemplos: dict[str, list] = collections.defaultdict(list)
    for v in viejas:
        n = nuevas.get(v.get("source_url"))
        if n is None:
            continue
        for c in CAMPOS:
            a, b = v.get(c), n.get(c)
            if _igual(a, b):
                clase = "igual"
            elif a in (None, "", []) and b not in (None, "", []):
                clase = "recuperado"
            elif a not in (None, "", []) and b in (None, "", []):
                clase = "perdido"
            else:
                clase = "cambiado"
            resumen[c][clase] += 1
            if clase != "igual" and len(ejemplos[f"{c}:{clase}"]) < 3:
                ejemplos[f"{c}:{clase}"].append({"url": v.get("source_url"), "antes": a, "ahora": b})
    return {"por_campo": {c: dict(r) for c, r in resumen.items() if r}, "ejemplos": dict(ejemplos)}


def replay(agencia: str, almacen_dir: Path | None = None, cert_dir: Path | None = None) -> dict[str, Any]:
    from scripts.agency_certifier import CONNECTORS
    almacen_dir = almacen_dir or dato("ERETZ_ALMACEN_PAGINAS")
    cert_dir = cert_dir or dato("ERETZ_AGENCY_CERTIFICATION_20260827")
    carpeta = cert_dir / "agencies" / hashlib.sha256(agencia.encode()).hexdigest()[:16]
    cert = json.loads((carpeta / "certification.json").read_text(encoding="utf-8"))
    viejas = [json.loads(l) for l in (carpeta / "properties_run2.jsonl").read_text(encoding="utf-8").splitlines()
              if l.strip()]
    descargador = DescargadorDelAlmacen(AlmacenDePaginas(almacen_dir), indice_de(almacen_dir, agencia))
    conector_nombre = (viejas[0].get("connector") if viejas else None) or cert.get("connector") or "generico"
    conector = CONNECTORS[conector_nombre](descargador=descargador)
    fuente = Fuente(canonical_agency_id=agencia, agency_name=str(cert.get("agency_name") or agencia),
                    official_url=str(cert.get("official_url") or ""), inmobiliaria_id=None)
    nuevas: dict[str, dict[str, Any]] = {}
    sin_pagina = 0
    for v in viejas:
        if v.get("source_url") not in descargador.indice:
            sin_pagina += 1
            continue
        try:
            p = conector.normalize({"source_url": v["source_url"],
                                    "source_listing_id": v.get("source_listing_id") or ""}, fuente)
        except Exception as error:  # noqa: BLE001 - un replay no se cae por una ficha
            nuevas[v["source_url"]] = {"_error": type(error).__name__}
            continue
        if p is not None:
            nuevas[v["source_url"]] = {c: getattr(p, c, None) for c in CAMPOS}
    return {"agencia": agencia, "conector": conector_nombre, "fichas_del_paquete": len(viejas),
            "con_pagina_guardada": len(viejas) - sin_pagina, "re_extraidas": len(nuevas),
            "certificado_en": cert.get("checked_at"), **comparar(viejas, nuevas),
            "pedidos_a_la_red": 0, "database_writes": 0}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("agencia")
    ap.add_argument("--json", type=Path)
    args = ap.parse_args()
    salida = replay(args.agencia)
    texto = json.dumps(salida, ensure_ascii=False, indent=1, default=str)
    if args.json:
        args.json.write_text(texto, encoding="utf-8")
    print(texto)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
