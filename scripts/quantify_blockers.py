#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Que falta exactamente, cuanto afecta, y que accion humana lo desbloquea.

"Quedan algunos casos" no es un estado: no se puede priorizar, no se puede
decidir si vale la pena, y sobre todo no se puede notar cuando empeora. Cada
pendiente tiene que salir con un numero y con la accion concreta que lo mueve.

La distincion que este artefacto existe para sostener:

  BLOQUEO EXTERNO   depende de algo que no esta en nuestras manos -una clave,
                    una credencial, un sitio que no responde-. Se cuenta y se
                    espera.

  TRABAJO PENDIENTE depende de nosotros. Se cuenta y se hace.

Confundirlas es como un pendiente se vuelve permanente: si todo se llama
"bloqueado", nadie vuelve a mirarlo.

Y una que ya costo cara: PENDING nunca es NOT_FOUND. Que falte el proveedor de
busqueda no demuestra que la inmobiliaria no tenga web.

Solo lee artefactos.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import Counter
from pathlib import Path

VERSION = "blocker_quantification_v1"

EXTERNO = "BLOQUEO_EXTERNO"
NUESTRO = "TRABAJO_PENDIENTE"

# Claves de busqueda. Sin ninguna, la cola de descubrimiento no avanza.
CLAVES_BUSQUEDA = ("BRAVE_SEARCH_API_KEY", "SERPAPI_KEY", "GOOGLE_CSE_KEY")

# Credenciales de escritura aceptables. El superusuario NO cuenta: entrar con el
# saltea la restriccion que el rol minimo existe para imponer.
CLAVES_ESCRITURA = ("ERETZ_PREVIEW_RO_POOLER_URL", "ERETZ_PREVIEW_RO_URL",
                    "SUPABASE_PREVIEW_RO_URL")


def leer(ruta: Path):
    if not ruta.exists():
        return
    with ruta.open(encoding="utf-8", errors="replace") as fh:
        for linea in fh:
            linea = linea.strip()
            if not linea:
                continue
            try:
                yield json.loads(linea)
            except ValueError:
                continue


def contar(ruta: Path) -> int:
    return sum(1 for _ in leer(ruta))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--raiz", default=r"D:\INMO CAPITAL")
    ap.add_argument("--data-dir", default=r"D:\INMO CAPITAL\ERETZ_AGENCY_DATA")
    ap.add_argument("--salida", default=r"D:\INMO CAPITAL\BACKLOG_RESIDUAL.json")
    a = ap.parse_args()
    raiz, dd = Path(a.raiz), Path(a.data_dir)

    manifiesto = list(leer(raiz / "SCRAPING_SOURCE_MANIFEST.jsonl"))
    pendientes_id = list(leer(raiz / "AGENCY_ID_PENDING_MANIFEST.jsonl"))
    cross = list(leer(raiz / "CROSS_AGENCY_RESOLUTION.jsonl"))
    dup = list(leer(raiz / "AGENCY_DUPLICATE_RESOLUTION_MANIFEST.jsonl"))
    candidatos = list(leer(raiz / "AGENCY_DUPLICATE_CANDIDATES.jsonl"))

    con_dominio = [x for x in manifiesto if x.get("official_domain")]
    scrape = Counter(x.get("scrapeability_status") for x in con_dominio)

    hay_busqueda = any(os.environ.get(v) for v in CLAVES_BUSQUEDA)
    hay_escritura = any(os.environ.get(v) for v in CLAVES_ESCRITURA)

    write_set = contar(raiz / "DB_WRITE_ELIGIBLE.jsonl")

    items = [
        {"blocker": "SEARCH_API_PENDING", "tipo": EXTERNO,
         "afecta": sum(1 for x in manifiesto if x.get("needs_external_search")),
         "unidad": "entidades del padron",
         "listo": "la cola de candidatas ya se agoto sin proveedor externo",
         "accion_humana": "configurar %s" % CLAVES_BUSQUEDA[0],
         "nota": "PENDING no es NOT_FOUND: que falte proveedor no demuestra "
                 "que la inmobiliaria no tenga web"},

        {"blocker": "DB_CREDENTIAL_PENDING", "tipo": EXTERNO,
         "afecta": write_set, "unidad": "propiedades listas para escribir",
         "listo": "write set validado, invariantes verificadas, canary listo",
         "accion_humana": "configurar %s con el usuario eretz_preview_ro"
                          % CLAVES_ESCRITURA[1],
         "nota": "no se usa postgres para saltear el privilegio minimo"},

        {"blocker": "NETWORK_ACCESS_BLOCKED", "tipo": EXTERNO,
         "afecta": scrape.get("SCRAPE_SOURCE_BLOCKED", 0), "unidad": "fuentes",
         "listo": "identificadas y con su dominio demostrado",
         "accion_humana": "ninguna: el sitio bloquea el acceso automatizado",
         "nota": "no se evaden protecciones"},

        {"blocker": "REQUIRES_JS", "tipo": NUESTRO,
         "afecta": scrape.get("SCRAPE_SOURCE_REQUIRES_JS", 0), "unidad": "fuentes",
         "listo": "detectadas",
         "accion_humana": "decidir si vale un camino con navegador",
         "nota": "dos fuentes no justifican una infraestructura nueva"},

        {"blocker": "NO_INVENTORY", "tipo": NUESTRO,
         "afecta": scrape.get("SCRAPE_SOURCE_NO_LISTINGS", 0), "unidad": "fuentes",
         "listo": "el sitio responde y no publica propiedades",
         "accion_humana": "ninguna mientras el sitio siga sin inventario",
         "nota": "no es un error: hay inmobiliarias sin catalogo publicado"},

        {"blocker": "PROFILE_ON_EXTERNAL_PORTAL", "tipo": NUESTRO,
         "afecta": sum(1 for x in manifiesto if x.get("perfil_en_portal_ajeno")),
         "unidad": "entidades",
         "listo": "identificadas y sacadas de la cola de scraping",
         "accion_humana": "buscar su web propia cuando haya proveedor",
         "nota": "su catalogo en el portal es de todos, no de ella"},

        {"blocker": "AGENCY_ID_PENDING", "tipo": NUESTRO,
         "afecta": sum(x.get("propiedades_descubiertas", 0)
                       for x in pendientes_id),
         "unidad": "propiedades de %d agencias" % len(pendientes_id),
         "listo": "descubiertas, normalizadas y validadas",
         "accion_humana": "resolver el eretz_id de esas agencias en el padron",
         "nota": "ninguna propiedad se escribe con un id inventado"},

        {"blocker": "CROSS_AGENCY_PENDING", "tipo": NUESTRO,
         "afecta": sum(1 for x in cross if not x.get("liberable")),
         "unidad": "urls disputadas",
         "listo": "clasificadas por naturaleza del conflicto",
         "accion_humana": "ninguna automatica: sin dueno demostrable se retiene",
         "nota": "adjudicar por tamano de inventario le da el aviso a la mas "
                 "grande sin mirar de quien es"},

        {"blocker": "AGENCY_DUPLICATE_PENDING", "tipo": NUESTRO,
         "afecta": len(dup), "unidad": "duplicados del padron sin resolver",
         "listo": "los resueltos ya liberaron sus propiedades",
         "accion_humana": "revisar los candidatos de la auditoria (%d)"
                          % len(candidatos),
         "nota": "ninguna fusion automatica"},
    ]

    informe = {
        "checked_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "version": VERSION,
        "claves_de_busqueda_presentes": hay_busqueda,
        "credencial_de_escritura_presente": hay_escritura,
        "write_set": write_set,
        "items": items,
    }
    Path(a.salida).write_text(json.dumps(informe, ensure_ascii=False, indent=2),
                              encoding="utf-8")

    print("### BACKLOG RESIDUAL ###")
    for tipo in (EXTERNO, NUESTRO):
        print()
        print("  %s" % tipo)
        for it in [x for x in items if x["tipo"] == tipo]:
            print("    %-28s %8d  %s"
                  % (it["blocker"], it["afecta"], it["unidad"]))
            print("        listo:  %s" % it["listo"])
            print("        accion: %s" % it["accion_humana"])
    print()
    print("  claves de busqueda:      %s"
          % ("PRESENTES" if hay_busqueda else "ABSENT"))
    print("  credencial de escritura: %s"
          % ("PRESENTE" if hay_escritura else "ABSENT"))
    print("  artefacto -> %s" % a.salida)
    return 0


if __name__ == "__main__":
    sys.exit(main())
