#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Que gana la recertificacion, medido contra la snapshot que va a reemplazar.

La cola vuelve a certificar 764 inmobiliarias y eso son decenas de horas de
maquina. La pregunta que lo justifica -o no- es simple y no estaba respondida:
**las propiedades que salen ahora traen mas campos que las que ya tenemos?**

Se compara por `hash_dedup`, que es la misma propiedad en los dos lados, y solo
sobre las agencias efectivamente recertificadas: mezclar las que todavia no
pasaron diluiria el resultado hasta volverlo ilegible.

Tres cuentas por campo:

  gana      estaba vacio en la snapshot y ahora tiene valor
  pierde    tenia valor y ahora esta vacio
  igual     los dos lados dicen lo mismo, o los dos estan vacios

**Perder no siempre es empeorar**, y esa es la lectura mas dificil del informe.
Un campo que se vacia porque la validacion lo rechazo -una superficie de
cincuenta kilometros cuadrados, una ciudad que el catalogo desmiente- es una
mejora que aparece en la columna equivocada. Esas se cuentan aparte, con su
motivo.

Pero hay una segunda clase que el informe NO puede separar solo: el lector que
se niega a afirmar un valor ambiguo. En la primera corrida, `banos` figuraba
perdiendo 182 sin motivo, y las 182 eran correcciones:

  alaspropiedades.com   el valor viejo, `banos=5`, salia del desplegable del
                        buscador -"Habitaciones Min. Cualquiera 1 2 3 4 5
                        Banos Min..."-, leyendo el numero ANTES del rotulo
  agostiniinmobiliaria  salia del bloque de propiedades relacionadas al pie:
                        era la cantidad de banos del vecino

O sea que una columna de perdidas sin motivo hay que ABRIRLA contra la fuente
antes de leerla como regresion. El informe dice donde mirar, no que paso.

No escribe en ninguna base.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import Counter
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.preingestion_manifest import (base_canonica,  # noqa: E402
                                           exigir_base_vigente)

GANANCIA_VERSION = "recertification_gain_v1"

# Los campos que decidan si una propiedad se puede publicar y encontrar. No se
# miran `titulo` ni `descripcion`: cambian de redaccion sin cambiar de valor y
# ensucian la cuenta.
CAMPOS = ("precio", "moneda", "operacion", "tipo_propiedad", "ciudad",
          "provincia", "barrio", "direccion", "latitud", "longitud",
          "ambientes", "dormitorios", "banos", "superficie_total",
          "superficie_cubierta")


def _vacio(valor: Any) -> bool:
    return valor in (None, "", [], {}, 0)


def _frescas(paquetes: Path) -> tuple[dict[str, dict], set[str]]:
    """Lo ultimo certificado, por propiedad, y de que agencias salio."""
    fuera: dict[str, dict] = {}
    agencias: set[str] = set()
    for paquete in paquetes.iterdir():
        certificacion = paquete / "certification.json"
        propiedades = paquete / "properties_run1.jsonl"
        if not (certificacion.exists() and propiedades.exists()):
            continue
        try:
            cabecera = json.loads(certificacion.read_text(encoding="utf-8"))
        except ValueError:
            continue
        agencias.add(str(cabecera.get("canonical_agency_id")))
        for linea in propiedades.read_text(encoding="utf-8").splitlines():
            if linea.strip():
                fila = json.loads(linea)
                if fila.get("hash_dedup"):
                    fuera[fila["hash_dedup"]] = fila
    return fuera, agencias


def comparar(vieja: dict, fresca: dict) -> dict[str, str]:
    """Campo por campo: gana, pierde, o queda igual."""
    salida = {}
    descartados = str((fresca.get("extra") or {}).get(
        "atributos_descartados") or "")
    for campo in CAMPOS:
        antes, ahora = _vacio(vieja.get(campo)), _vacio(fresca.get(campo))
        if antes and not ahora:
            salida[campo] = "gana"
        elif ahora and not antes:
            # Vaciar por validacion es una decision, no una perdida.
            salida[campo] = ("pierde_con_motivo" if campo in descartados
                             else "pierde")
        else:
            salida[campo] = "igual"
    return salida


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(base_canonica()))
    ap.add_argument("--paquetes",
                    default=r"D:\INMO CAPITAL\ERETZ_AGENCY_CERTIFICATION_20260827\agencies")
    ap.add_argument("--salida", default=r"D:\INMO CAPITAL\ERETZ_OPERACION")
    args = ap.parse_args()
    exigir_base_vigente(args.db)

    frescas, agencias = _frescas(Path(args.paquetes))
    conexion = sqlite3.connect(f"file:{Path(args.db).as_posix()}?mode=ro",
                               uri=True)

    por_campo: dict[str, Counter] = {c: Counter() for c in CAMPOS}
    comparadas = 0
    nuevas = len(frescas)
    for crudo, hash_dedup, canonical in conexion.execute(
            "select row_json, hash_dedup, canonical_id from rows "
            "where status = 'CANDIDATE'"):
        if canonical not in agencias:
            continue
        fresca = frescas.get(hash_dedup)
        if fresca is None:
            continue
        nuevas -= 1
        comparadas += 1
        for campo, veredicto in comparar(json.loads(crudo), fresca).items():
            por_campo[campo][veredicto] += 1

    resumen = {
        "ganancia_version": GANANCIA_VERSION,
        "agencias_recertificadas": len(agencias),
        "propiedades_comparadas": comparadas,
        "propiedades_que_no_estaban_en_la_snapshot": max(0, nuevas),
        "por_campo": {c: dict(v.most_common()) for c, v in por_campo.items()
                      if v},
        "campos_que_mas_ganan": sorted(
            ((c, v.get("gana", 0)) for c, v in por_campo.items()),
            key=lambda x: -x[1])[:6],
        "database_writes": 0,
    }
    salida = Path(args.salida)
    salida.mkdir(parents=True, exist_ok=True)
    (salida / "ERETZ_RECERTIFICATION_GAIN.json").write_text(
        json.dumps(resumen, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(resumen, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
