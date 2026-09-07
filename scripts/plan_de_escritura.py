#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""El plan exacto de escritura productiva, listo para el dia que vuelva la base.

Postgres responde `PGRST002` desde hace dias. Cuando vuelva, lo peor que se
puede hacer es escribir enseguida: la base pudo cambiar mientras no
respondia, y todos los dry-runs se calcularon contra un estado que quiza ya no
existe.

Este script arma el plan y NO escribe. Produce, por paso:

  cuantas filas       el numero exacto, no "unas cuantas"
  la clave            por que campo se hace upsert. Sin clave declarada, un
                      reintento duplica en vez de actualizar
  precondicion        que tiene que ser cierto ANTES de correr el paso
  invariante          que tiene que seguir siendo cierto DESPUES
  rollback            como se deshace, y si no se puede, se dice

**El orden no es una preferencia.** Cada paso depende de que el anterior haya
creado las filas a las que apunta: promover una inmobiliaria antes de
vincularla deja propiedades apuntando a un id que todavia no existe.

**Todo idempotente.** Correr el plan dos veces tiene que dar el mismo estado
que correrlo una. Sin eso, una interrupcion a la mitad no se puede reanudar y
hay que decidir a mano que quedo escrito, que es como se pierde la trazabilidad.

`database_writes: 0`. Este script prepara; la ejecucion requiere autorizacion
humana explicita.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

PLAN_VERSION = "plan_de_escritura_v1"


def _contar_jsonl(ruta: Path, filtro=None) -> int:
    if not ruta.exists():
        return 0
    total = 0
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        if not linea.strip():
            continue
        try:
            fila = json.loads(linea)
        except ValueError:
            continue
        if filtro is None or filtro(fila):
            total += 1
    return total


def _ultimos_por_clave(ruta: Path, clave: str) -> dict[str, dict[str, Any]]:
    fuera: dict[str, dict[str, Any]] = {}
    if not ruta.exists():
        return fuera
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        if linea.strip():
            try:
                fila = json.loads(linea)
            except ValueError:
                continue
            if fila.get(clave):
                fuera[fila[clave]] = fila
    return fuera


def construir(certificacion: Path, geo: Path, preingestion: Path) -> dict[str, Any]:
    promocion = _ultimos_por_clave(certificacion / "AGENCY_PROMOTION_GATE.jsonl",
                                   "canonical_agency_id")
    seguras = [f for f in promocion.values()
               if f.get("promotion_state") == "SAFE_TO_PROMOTE"]
    # La verificacion de web se hizo abriendo la pagina: manda sobre el puntaje.
    recheck = _ultimos_por_clave(
        certificacion / "AGENCY_PROMOTION_WEB_RECHECK.jsonl",
        "canonical_agency_id")
    seguras_confirmadas = [f for f in seguras
                           if (recheck.get(f["canonical_agency_id"], {})
                               .get("veredicto") or "SIN_RECHEQUEO") != "RECHAZADA"]

    vinculos = _contar_jsonl(certificacion / "AGENCY_MAIN_LINK_DRYRUN.jsonl")
    ciudades = _contar_jsonl(geo / "CIUDAD_DRYRUN_AUDIT.jsonl",
                             lambda f: f.get("apta_para_escritura"))
    publicables = _contar_jsonl(preingestion / "PROPERTY_QUALITY_GATE.jsonl",
                                lambda f: f.get("publicable"))

    pasos = [
        {
            "orden": 1,
            "paso": "vincular inmobiliarias homonimas ya existentes en main",
            "filas": vinculos,
            "clave_de_upsert": "canonical_agency_id -> eretz_id",
            "precondicion": "el eretz_id existe en main y no tiene otra "
                            "canonical_agency_id asociada",
            "invariante": "ninguna inmobiliaria de main queda con dos "
                          "canonical_agency_id",
            "rollback": "borrar la asociacion; no crea filas nuevas en main",
            "por_que_primero": "no crea entidades: solo ata las que ya estan. "
                               "Si algo sale mal, es el paso mas barato de "
                               "deshacer.",
        },
        {
            "orden": 2,
            "paso": "promover inmobiliarias nuevas a main",
            "filas": len(seguras_confirmadas),
            "clave_de_upsert": "canonical_agency_id",
            "precondicion": "identity_status READY y web oficial verificada "
                            "argentina; el recheque de web no la rechazo",
            "invariante": "no se crea una inmobiliaria cuya web no se pudo "
                          "abrir y confirmar",
            "rollback": "borrar por canonical_agency_id las creadas en esta "
                        "corrida; quedan marcadas con el lote",
            "por_que_primero": "las propiedades apuntan a estos ids: "
                               "escribirlas antes las dejaria colgadas.",
        },
        {
            "orden": 3,
            "paso": "escribir geografia canonica sobre lo ya guardado",
            "filas": ciudades,
            "clave_de_upsert": "hash_dedup",
            "precondicion": "la propuesta esta marcada apta_para_escritura; "
                            "las 6.890 retenidas NO entran",
            "invariante": "ninguna propiedad queda con localidad que no se "
                          "pueda demostrar; el municipio no se escribe en el "
                          "campo de localidad",
            "rollback": "se conserva el valor anterior por fila en el "
                        "artefacto, asi que se puede revertir campo a campo",
            "por_que_primero": "es una correccion sobre filas existentes y no "
                               "depende de la ingesta nueva.",
        },
        {
            "orden": 4,
            "paso": "ingestar propiedades publicables",
            "filas": publicables,
            "clave_de_upsert": "hash_dedup",
            "precondicion": "su inmobiliaria existe en main (pasos 1 y 2) y la "
                            "propiedad tiene identidad completa",
            "invariante": "una propiedad real incompleta se escribe igual: lo "
                          "que falta le quita alcance, no existencia",
            "rollback": "borrar por hash_dedup las de este lote",
            "por_que_primero": "depende de los pasos 1 y 2; sin ellos las "
                               "propiedades no se pueden asociar.",
        },
        {
            "orden": 5,
            "paso": "recalcular alcances y publicar",
            "filas": publicables,
            "clave_de_upsert": "hash_dedup",
            "precondicion": "los pasos anteriores terminaron sin filas "
                            "rechazadas",
            "invariante": "la cantidad de propiedades publicables no baja "
                          "respecto del quality gate local",
            "rollback": "los alcances se recalculan enteros desde los datos: "
                        "revertir es volver a correr el paso",
            "por_que_primero": "es el ultimo porque lee todo lo anterior.",
        },
    ]

    return {
        "plan_version": PLAN_VERSION,
        "estado": "WAITING_USER_AUTHORIZATION",
        "bloqueado_por": [
            "Postgres de produccion responde PGRST002",
            "la escritura productiva requiere autorizacion humana explicita",
        ],
        "antes_de_ejecutar": [
            "auditoria live de solo lectura: la base pudo cambiar mientras no "
            "respondia y todos los dry-runs se calcularon contra otro estado",
            "confirmar el esquema y comparar los conteos actuales contra los "
            "de estos artefactos",
            "recalcular los dry-runs sobre el estado real",
            "backup verificado, no solo lanzado",
            "probar el rollback de cada paso en una copia",
        ],
        "pasos": pasos,
        "filas_totales_a_escribir": sum(p["filas"] for p in pasos[:4]),
        "database_writes": 0,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--certificacion",
                    default=r"D:\INMO CAPITAL\ERETZ_AGENCY_CERTIFICATION_20260827")
    ap.add_argument("--geo", default=r"D:\INMO CAPITAL\ERETZ_GEO")
    ap.add_argument("--preingestion",
                    default=r"D:\INMO CAPITAL\ERETZ_PREINGESTION_REBUILD_20260903")
    ap.add_argument("--salida", default=r"D:\INMO CAPITAL\ERETZ_OPERACION")
    args = ap.parse_args()

    plan = construir(Path(args.certificacion), Path(args.geo),
                     Path(args.preingestion))
    salida = Path(args.salida)
    salida.mkdir(parents=True, exist_ok=True)
    (salida / "ERETZ_PLAN_DE_ESCRITURA.json").write_text(
        json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(plan, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
