#!/usr/bin/env python
"""Clasifica que inmobiliarias descubiertas pueden promoverse a `main`.

Promover significa insertar la inmobiliaria en `inmobiliarias_main` y darle un
`eretz_id` real. Es lo que habilita atribuirle propiedades: hoy 127.595 filas de
la pre-ingesta quedan en `AGENCY_ID_UNRESOLVED` porque su inmobiliaria vive solo
en `inmobiliarias_staging`.

El riesgo de una promocion falsa no es perder una fila: es CREAR UNA DUPLICADA
de una inmobiliaria que ya existe en `main`. Eso parte su inventario entre dos
fichas y despues no se distingue de dos negocios distintos -ya pasa hoy con
`inmobiliaria salerno` (eretz_id 3535) y `salerno inmobiliaria` (6334), el mismo
negocio con dos filas-. Por eso el nombre nunca alcanza como evidencia.

Las invariantes que exige la promocion automatica, todas demostradas y no
supuestas:

  1. el cruce con staging no es ambiguo;
  2. no hay homonima en `main`, o la estariamos duplicando;
  3. no es parte de un grupo duplicado dentro del propio universo canonico;
  4. tiene web propia con identidad de confianza alta o verificada;
  5. esa web no es el perfil de un portal ajeno ni un sitio que no es
     inmobiliario;
  6. el dominio no lo comparte con otra inmobiliaria del universo.

La sexta importa mas de lo que parece: hay dominios de plataforma compartidos
por inmobiliarias sin relacion, y `re max urbana` / `re max time` son sucursales
distintas del mismo dominio. Un dominio no identifica a una inmobiliaria.

Este script NO escribe en ninguna base. Produce la clasificacion y el rollup
para decidir; la insercion en `main` es una escritura productiva y queda del
otro lado de la barrera de autorizacion.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.agency_certifier import load_catalog, read_jsonl, write_json

SAFE = "SAFE_TO_PROMOTE"
REVIEW = "REQUIRES_REVIEW"
BLOCKED = "BLOCKED"
SIN_EVIDENCIA = "INSUFFICIENT_EVIDENCE"

# Un estado de descubrimiento que si demuestra web propia.
WEB_DEMOSTRADA = {"OFFICIAL_WEB_VERIFIED", "OFFICIAL_WEB_HIGH_CONFIDENCE"}
# Uno que demuestra lo contrario, o que no hay nada que demostrar todavia.
WEB_AUSENTE = {"NO_EXISTING_WEB_DATA", "SEARCH_SECOND_PASS_REQUIRED",
               "NO_INDEPENDENT_WEBSITE"}
WEB_NO_PROPIA = {"EXTERNAL_PORTAL_PROFILE", "NOT_A_REAL_ESTATE_WEB",
                 "PORTAL_NOT_OFFICIAL"}


def palabras(valor: Any) -> set[str]:
    plano = unicodedata.normalize("NFKD", str(valor or "").lower())
    plano = "".join(c for c in plano if not unicodedata.combining(c))
    return set(re.sub(r"[^a-z0-9]+", " ", plano).split())


def clave_nombre(valor: Any) -> str:
    return " ".join(sorted(palabras(valor)))


def dominio_de(registro: dict[str, dict[str, Any]]) -> str:
    crudo = (registro["directory"].get("selected_domain")
             or registro["platform"].get("domain")
             or registro["resolution"].get("official_domain") or "")
    crudo = str(crudo).strip().lower()
    crudo = re.sub(r"^https?://", "", crudo).split("/")[0]
    return crudo[4:] if crudo.startswith("www.") else crudo


def clasificar(registro: dict[str, dict[str, Any]], *,
               homonimas_en_main: int,
               miembros_del_grupo: int,
               inmobiliarias_en_el_dominio: int) -> tuple[str, list[str]]:
    """Decide si una inmobiliaria puede promoverse, y por que.

    Devuelve siempre las razones: una clasificacion sin motivo no se puede
    auditar despues, y el punto de esto es no promover a ciegas.
    """
    directorio, plataforma, resolucion = (registro["directory"],
                                          registro["platform"],
                                          registro["resolution"])
    estado_web = str(directorio.get("status") or "")
    tipo_web = str(plataforma.get("web_kind") or "")
    cruce = str((resolucion.get("evidence") or {}).get("crosswalk_state") or "")

    bloqueos: list[str] = []
    if homonimas_en_main:
        # Existe una inmobiliaria con ese nombre en main. Insertarla de nuevo
        # crea la duplicada que este gate viene a evitar.
        bloqueos.append("HOMONIMA_EN_MAIN")
    if miembros_del_grupo > 1:
        bloqueos.append("DUPLICADA_EN_EL_UNIVERSO")
    if tipo_web in WEB_NO_PROPIA or estado_web in WEB_NO_PROPIA:
        bloqueos.append("LA_WEB_NO_ES_PROPIA")
    if bloqueos:
        return BLOCKED, bloqueos

    revisiones: list[str] = []
    if cruce and cruce != "HIGH_CONFIDENCE_EXISTING":
        revisiones.append(f"CRUCE_{cruce}")
    if tipo_web == "AMBIGUOUS_WEB_ATTRIBUTION":
        revisiones.append("ATRIBUCION_DE_WEB_AMBIGUA")
    if estado_web == "OFFICIAL_WEB_AMBIGUOUS":
        revisiones.append("IDENTIDAD_DE_WEB_AMBIGUA")
    if inmobiliarias_en_el_dominio > 1:
        # Dominio de plataforma o franquicia: no identifica a una sola.
        revisiones.append("DOMINIO_COMPARTIDO")
    if revisiones:
        return REVIEW, revisiones

    if estado_web in WEB_AUSENTE or not dominio_de(registro):
        # Sin web no queda mas evidencia que el nombre, y el nombre solo es
        # exactamente lo que produce duplicadas.
        return SIN_EVIDENCIA, ["SIN_WEB_QUE_CORROBORE_LA_IDENTIDAD"]
    if estado_web not in WEB_DEMOSTRADA:
        return SIN_EVIDENCIA, [f"ESTADO_DE_WEB_NO_CONCLUYENTE_{estado_web}"]

    return SAFE, [f"WEB_{estado_web}", "SIN_HOMONIMA", "SIN_DUPLICADA",
                  "DOMINIO_PROPIO"]


def nombres_de_main(backup: Path) -> dict[str, list[str]]:
    indice: dict[str, list[str]] = defaultdict(list)
    if not backup.exists():
        return indice
    with backup.open(encoding="utf-8-sig", errors="replace", newline="") as f:
        for fila in csv.DictReader(f):
            if fila.get("nombre"):
                indice[clave_nombre(fila["nombre"])].append(str(fila.get("id")))
    return indice


def evaluar(catalogo: dict[str, dict[str, Any]],
            main: dict[str, list[str]]) -> list[dict[str, Any]]:
    candidatas = [k for k, r in catalogo.items()
                  if r["resolution"].get("resolution_method")
                  == "STAGING_NAMESPACE_NOT_A_MAIN_FK"]
    # Los grupos se calculan sobre el universo ENTERO, no sobre las candidatas:
    # una duplicada puede tener a su gemela ya resuelta en main.
    por_nombre: dict[str, list[str]] = defaultdict(list)
    por_dominio: dict[str, list[str]] = defaultdict(list)
    for clave, registro in catalogo.items():
        por_nombre[clave_nombre(clave.split(":", 1)[-1])].append(clave)
        dominio = dominio_de(registro)
        if dominio:
            por_dominio[dominio].append(clave)

    salida = []
    for clave in sorted(candidatas):
        registro = catalogo[clave]
        nombre = clave.split(":", 1)[-1]
        dominio = dominio_de(registro)
        estado, motivos = clasificar(
            registro,
            homonimas_en_main=len(main.get(clave_nombre(nombre), [])),
            miembros_del_grupo=len(por_nombre[clave_nombre(nombre)]),
            inmobiliarias_en_el_dominio=len(por_dominio.get(dominio, [])))
        salida.append({
            "canonical_agency_id": clave,
            "agency_name": registro["resolution"].get("agency_name") or nombre,
            "promotion_state": estado,
            "reasons": motivos,
            "domain": dominio or None,
            "discovery_status": registro["directory"].get("status"),
            "web_kind": registro["platform"].get("web_kind"),
        })
    return salida


def vinculaciones(catalogo: dict[str, dict[str, Any]],
                  main: dict[str, list[str]],
                  filas: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Las que ya existen en `main` y solo hay que enlazar, no crear.

    Salieron bloqueadas por homonima, pero eso no las convierte en un problema:
    las convierte en la accion MAS segura de todas. "bechara inmobiliaria" es
    "Inmobiliaria Bechara" con las palabras al reves; enlazarla al id que ya
    existe no crea ninguna fila y le devuelve la inmobiliaria a sus propiedades.

    Coincidir el conjunto de palabras es evidencia fuerte pero no prueba: dos
    negocios distintos podrian compartirlo. Por eso una sola candidata en main
    es enlazable y varias van a revision, nunca se elige la primera.
    """
    salida = []
    for fila in filas:
        if "HOMONIMA_EN_MAIN" not in fila["reasons"]:
            continue
        nombre = fila["canonical_agency_id"].split(":", 1)[-1]
        candidatas = main.get(clave_nombre(nombre), [])
        salida.append({
            "canonical_agency_id": fila["canonical_agency_id"],
            "agency_name": fila["agency_name"],
            "action": "LINK_TO_EXISTING" if len(candidatas) == 1
                      else "REQUIRES_REVIEW",
            "main_candidates": candidatas,
            "evidence": "identical normalized word set",
            "writes_a_new_row": False,
        })
    return salida


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--v2-dir", default=r"D:\INMO CAPITAL\ERETZ_SUPABASE_RECONCILIATION_V2_20260827")
    parser.add_argument("--data-dir", default=r"D:\INMO CAPITAL\ERETZ_AGENCY_DATA")
    parser.add_argument("--platform-directory", default=r"D:\INMO CAPITAL\agency_platform_directory.jsonl")
    parser.add_argument("--main-backup", default=r"D:\INMO CAPITAL\Inmo-Capital-main\backups supabase\2026-05-27_inmobiliarias_main.csv")
    parser.add_argument("--output", default=r"D:\INMO CAPITAL\ERETZ_AGENCY_CERTIFICATION_20260827")
    args = parser.parse_args()

    catalogo = load_catalog(Path(args.v2_dir), Path(args.data_dir),
                            Path(args.platform_directory))
    filas = evaluar(catalogo, nombres_de_main(Path(args.main_backup)))

    salida = Path(args.output)
    salida.mkdir(parents=True, exist_ok=True)
    destino = salida / "AGENCY_PROMOTION_GATE.jsonl"
    destino.write_text(
        "".join(json.dumps(f, ensure_ascii=False) + "\n" for f in filas),
        encoding="utf-8")

    conteo = Counter(f["promotion_state"] for f in filas)
    motivos: dict[str, Counter] = defaultdict(Counter)
    for fila in filas:
        for motivo in fila["reasons"]:
            motivos[fila["promotion_state"]][motivo] += 1
    resumen = {
        "total": len(filas),
        "by_state": dict(conteo),
        "reasons_by_state": {k: dict(v) for k, v in motivos.items()},
        "database_writes": 0,
    }
    enlaces = vinculaciones(catalogo, nombres_de_main(Path(args.main_backup)),
                            filas)
    (salida / "AGENCY_MAIN_LINK_DRYRUN.jsonl").write_text(
        "".join(json.dumps(e, ensure_ascii=False) + chr(10)
                for e in enlaces),
        encoding="utf-8")
    resumen["links_dry_run"] = dict(Counter(e["action"] for e in enlaces))
    write_json(salida / "AGENCY_PROMOTION_GATE_SUMMARY.json", resumen)

    print(json.dumps(resumen, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
