#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""El registro de que se vio y cuando. Sin esto el ciclo de vida no existe.

El ciclo de vida estaba especificado y sin activar, y la razon anotada era
"faltan pasadas repetidas en el tiempo". Pero el problema no era el tiempo: era
que las observaciones NO SE GUARDABAN EN NINGUN LADO. El checkpoint tiene lo
que se vio en la ultima corrida y se sobrescribe; el paquete de certificacion
tambien. Cada pasada borraba la evidencia de la anterior.

Asi el ciclo de vida no se iba a poder activar nunca, por muchas pasadas que se
hicieran.

Este registro es append-only y guarda, por inmobiliaria y por corrida, el
conjunto de propiedades vistas. Con dos observaciones ya se puede decir que
desaparecio; con tres, si volvio. Nada mas se necesita.

**Solo se registran las enumeraciones CONFIABLES.** Si la corrida no termino
OK, lo que no se vio no estuvo ausente: no se lo busco. Contar eso como
ausencia es fabricar bajas a partir de nuestros propios fallos, que es
exactamente como se borra inventario vivo.

No escribe en ninguna base.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any, Iterable

OBSERVACION_VERSION = "property_observations_v1"

ARCHIVO = "PROPERTY_OBSERVATIONS.jsonl"

# Estados de corrida en los que lo que no se vio SI estuvo ausente.
CORRIDAS_CONFIABLES = ("OK",)


def _hashes(ruta: Path) -> set[str]:
    fuera: set[str] = set()
    if not ruta.exists():
        return fuera
    for linea in ruta.read_text(encoding="utf-8", errors="replace").splitlines():
        if not linea.strip():
            continue
        try:
            fila = json.loads(linea)
        except ValueError:
            continue
        if fila.get("hash_dedup"):
            fuera.add(fila["hash_dedup"])
    return fuera


def observacion(paquete: Path, resultado: dict[str, Any]) -> dict[str, Any] | None:
    """Lo visto en esta certificacion, o None si no se puede confiar.

    Se usa la UNION de las dos corridas: una propiedad que aparecio en una y no
    en la otra estuvo, y exigir las dos convertiria una lectura intermitente en
    una baja.
    """
    corridas = [resultado.get("run1") or {}, resultado.get("run2") or {}]
    if not all(c.get("estado") in CORRIDAS_CONFIABLES for c in corridas):
        return None
    vistos = _hashes(paquete / "properties_run1.jsonl") | _hashes(
        paquete / "properties_run2.jsonl")
    if not vistos:
        return None
    return {
        "canonical_agency_id": resultado.get("canonical_agency_id"),
        "observacion_version": OBSERVACION_VERSION,
        "observado_en": resultado.get("checked_at")
                        or time.strftime("%Y-%m-%dT%H:%M:%S"),
        "vistas": len(vistos),
        "hashes": sorted(vistos),
    }


def registrar(paquete: Path, resultado: dict[str, Any], salida: Path) -> bool:
    """Agrega una observacion al registro. Devuelve si registro algo."""
    fila = observacion(paquete, resultado)
    if fila is None:
        return False
    ruta = salida / ARCHIVO
    ruta.parent.mkdir(parents=True, exist_ok=True)
    import os
    renglon = (json.dumps(fila, ensure_ascii=False) + "\n").encode("utf-8")
    descriptor = os.open(ruta, os.O_WRONLY | os.O_CREAT | os.O_APPEND)
    try:
        os.write(descriptor, renglon)
    finally:
        os.close(descriptor)
    return True


def leer(ruta: Path) -> dict[str, list[dict[str, Any]]]:
    """Las observaciones de cada inmobiliaria, en orden."""
    por_agencia: dict[str, list[dict[str, Any]]] = {}
    if not ruta.exists():
        return por_agencia
    for linea in ruta.read_text(encoding="utf-8", errors="replace").splitlines():
        if not linea.strip():
            continue
        try:
            fila = json.loads(linea)
        except ValueError:
            continue
        por_agencia.setdefault(fila.get("canonical_agency_id"), []).append(fila)
    for filas in por_agencia.values():
        filas.sort(key=lambda f: f.get("observado_en") or "")
    return por_agencia


def transiciones(observaciones: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Que aparecio, que desaparecio, y que volvio.

    Volver importa mas que desaparecer: si las propiedades que desaparecen
    reaparecen seguido, el umbral para dar una por inactiva tiene que ser mas
    alto, y ese numero no se puede elegir sin medirlo.
    """
    filas = list(observaciones)
    if len(filas) < 2:
        return {"observaciones": len(filas), "suficiente_para_medir": False}

    conjuntos = [set(f.get("hashes") or []) for f in filas]
    ausencias: dict[str, int] = {}
    reapariciones = 0
    desapariciones = 0
    ausentes_al_final = 0

    for anterior, actual in zip(conjuntos, conjuntos[1:]):
        for h in anterior - actual:
            ausencias[h] = ausencias.get(h, 0) + 1
            desapariciones += 1
        for h in actual & set(ausencias):
            if ausencias.get(h):
                reapariciones += 1
                ausencias[h] = 0
    ausentes_al_final = sum(1 for v in ausencias.values() if v)

    return {
        "observaciones": len(filas),
        "suficiente_para_medir": True,
        "desapariciones": desapariciones,
        "reapariciones": reapariciones,
        "ausentes_al_final": ausentes_al_final,
        "tasa_de_reaparicion": (round(reapariciones / desapariciones, 3)
                                if desapariciones else None),
        "ausencia_consecutiva_maxima": max(ausencias.values(), default=0),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--registro",
                    default=str(Path(r"D:\INMO CAPITAL\ERETZ_AGENCY_CERTIFICATION_20260827")
                                / ARCHIVO))
    args = ap.parse_args()

    por_agencia = leer(Path(args.registro))
    medibles = {a: transiciones(f) for a, f in por_agencia.items()}
    con_datos = {a: m for a, m in medibles.items() if m["suficiente_para_medir"]}

    total_des = sum(m["desapariciones"] for m in con_datos.values())
    total_re = sum(m["reapariciones"] for m in con_datos.values())
    resumen = {
        "observacion_version": OBSERVACION_VERSION,
        "inmobiliarias_con_registro": len(por_agencia),
        "inmobiliarias_medibles": len(con_datos),
        "desapariciones": total_des,
        "reapariciones": total_re,
        "tasa_de_reaparicion": (round(total_re / total_des, 3)
                                if total_des else None),
        "ausencia_consecutiva_maxima": max(
            (m["ausencia_consecutiva_maxima"] for m in con_datos.values()),
            default=0),
        "listo_para_activar_el_ciclo_de_vida": len(con_datos) > 0 and total_des > 0,
        "database_writes": 0,
    }
    print(json.dumps(resumen, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
