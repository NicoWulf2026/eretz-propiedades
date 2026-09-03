#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Reverificar la web de las inmobiliarias que el gate declaro promovibles.

Promover inserta en `inmobiliarias_main`. El propio gate de promocion lo dice:
el riesgo no es perder una fila, es CREAR UNA DUPLICADA que despues parte el
inventario de un negocio entre dos fichas.

Su invariante 4 exige "web propia con identidad de confianza alta o
verificada", y las 939 promovibles la cumplen con `free_web_audit_v1`: la
auditoria que puntuo URLs **sin abrirlas**. 933 de las 939 se apoyan en
`OFFICIAL_WEB_HIGH_CONFIDENCE`, que se midio y no discrimina nada -597 de 598
dominios descubiertos lo traen, incluidos `waze.com` y la lista de socios de un
colegio inmobiliario-. Ninguna de las 939 fue evaluada por el resolver que si
abre la pagina.

Este script no cambia la clasificacion ni promueve nada. Aplica a esas 939 las
mismas reglas que ya se usan para el resto -normalizar al origen, host
compartido, nombre en el dominio, y abrir el sitio exigiendo evidencia
argentina- y dice cuantas sostienen su evidencia cuando se la lee.

No escribe en ninguna base.
"""
from __future__ import annotations

import argparse
import json
import sys
import threading
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.agency_official_web_gate import evaluar as evaluar_compuerta  # noqa: E402
from scripts.agency_official_web_verify import evaluar as verificar  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gate", default=r"D:\INMO CAPITAL\ERETZ_AGENCY_CERTIFICATION_20260827\AGENCY_PROMOTION_GATE.jsonl")
    ap.add_argument("--data-dir", default=r"D:\INMO CAPITAL\ERETZ_AGENCY_DATA")
    ap.add_argument("--salida", default=r"D:\INMO CAPITAL\ERETZ_AGENCY_CERTIFICATION_20260827")
    ap.add_argument("--concurrencia", type=int, default=6)
    ap.add_argument("--limite", type=int, default=0)
    args = ap.parse_args()

    promovibles = [json.loads(l) for l in Path(args.gate).read_text(encoding="utf-8").splitlines()
                   if l.strip()]
    promovibles = [g for g in promovibles if g.get("promotion_state") == "SAFE_TO_PROMOTE"]
    if args.limite:
        promovibles = promovibles[:args.limite]

    # La compuerta necesita ver el CONJUNTO para poder decidir que un host
    # compartido no identifica a nadie. Se le pasan todas juntas.
    # El gate guarda el host pelado (`acampos.com.ar`); la compuerta razona
    # sobre origenes, asi que se le antepone el esquema.
    def como_origen(dominio: str | None) -> str:
        dominio = (dominio or "").strip()
        if not dominio:
            return ""
        return dominio if dominio.startswith("http") else f"https://{dominio}"

    crudas = [{"canonical_agency_id": g["canonical_agency_id"],
               "nombre": g.get("agency_name"),
               "discovered_domain": como_origen(g.get("domain"))}
              for g in promovibles]
    decididas = evaluar_compuerta(crudas)
    por_estado = Counter(d["estado"] for d in decididas)

    # Se abren TODAS, tambien las que la compuerta rechazo por no llevar el
    # nombre en el dominio. Esa regla no distingue un acronimo legitimo de un
    # dominio ajeno, y la pagina si: `ayfb.com.ar` nombra a la inmobiliaria y
    # el sitio de los Bomberos de San Lorenzo no.
    afirmables = [d for d in decididas if d["origen_descubierto"]]
    cerrojo = threading.Lock()
    verificadas: list[dict[str, Any]] = []

    def trabajar(fila: dict[str, Any]) -> None:
        # La compuerta deja `official_url` en None cuando no afirma; para leer
        # la pagina hay que ir igual al origen que descubrio.
        resultado = verificar(dict(fila, official_url=fila["origen_descubierto"]))
        with cerrojo:
            verificadas.append(resultado)
            if len(verificadas) % 100 == 0:
                print(f"    {len(verificadas)}/{len(afirmables)}", flush=True)

    print(f"  promovibles: {len(promovibles)} | pasan la compuerta: "
          f"{len(afirmables)} | se abren ahora", flush=True)
    with ThreadPoolExecutor(max_workers=args.concurrencia) as pool:
        list(pool.map(trabajar, afirmables))

    por_verificacion = Counter(v["verificacion"] for v in verificadas)

    def veredicto(decidida: dict[str, Any], leida: dict[str, Any]) -> str:
        estado = leida.get("verificacion")
        if estado in (None, "NO_LLEGO_A_ABRIRSE"):
            return "NO_LLEGO_A_ABRIRSE"
        if estado in ("RECHAZADA_SIN_EL_NOMBRE",):
            return "DOMINIO_AJENO_DEMOSTRADO"
        if estado in ("RECHAZADA_OTRO_PAIS", "RECHAZADA_TLD_EXTRANJERO"):
            return "DOMINIO_DE_OTRO_PAIS"
        if estado == "NO_RESPONDE":
            return "NO_RESPONDE"
        if decidida["estado"] != "AFIRMABLE":
            # La pagina nombra a la inmobiliaria pero el dominio no lo prueba.
            return "PLAUSIBLE_SIN_PRUEBA_EN_EL_DOMINIO"
        if estado == "VERIFICADA_ARGENTINA":
            return "SOSTIENE_SU_EVIDENCIA"
        return "SIN_EVIDENCIA_DE_PAIS"

    indice = {v["canonical_agency_id"]: v for v in verificadas}
    veredictos = {d["canonical_agency_id"]: veredicto(d, indice.get(d["canonical_agency_id"], {}))
                  for d in decididas}
    sostienen = {k for k, v in veredictos.items() if v == "SOSTIENE_SU_EVIDENCIA"}

    destino = Path(args.salida) / "AGENCY_PROMOTION_WEB_RECHECK.jsonl"
    with destino.open("w", encoding="utf-8") as archivo:
        for d in decididas:
            v = indice.get(d["canonical_agency_id"], {})
            archivo.write(json.dumps({
                **d,
                "verificacion": v.get("verificacion", "NO_LLEGO_A_ABRIRSE"),
                "verificacion_razon": v.get("verificacion_razon",
                                            d.get("razon")),
                "titulo": v.get("titulo"),
                "veredicto": veredictos[d["canonical_agency_id"]],
                "sostiene_su_evidencia": d["canonical_agency_id"] in sostienen,
                "database_writes": 0,
            }, ensure_ascii=False) + "\n")

    resumen = {
        "promovibles_evaluadas": len(promovibles),
        "por_estado_de_compuerta": dict(por_estado),
        "abiertas": len(verificadas),
        "por_verificacion": dict(por_verificacion),
        "por_veredicto": dict(Counter(veredictos.values())),
        "sostienen_su_evidencia": len(sostienen),
        "no_la_sostienen": len(promovibles) - len(sostienen),
        "promociones_ejecutadas": 0,
        "database_writes": 0,
        "artefacto": destino.name,
    }
    (Path(args.salida) / "AGENCY_PROMOTION_WEB_RECHECK_SUMMARY.json").write_text(
        json.dumps(resumen, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(resumen, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
