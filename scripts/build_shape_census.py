#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Censo de fuentes habilitadas por su FORMA DE FICHA verificada.

El descubrimiento agrupo las urls internas de cada sitio por forma y la
verificacion bajo tres fichas de la forma dominante para comprobar que ahi hay
propiedades y no notas. Este script convierte ese veredicto en el censo que
consume el rollout: una fila por fuente, con la forma que el connector generico
puede usar PARA ESA FUENTE.

Es deliberadamente el camino largo. La alternativa era aflojar el patron global
de fichas hasta que entraran estos sitios, y ese patron gobierna 2.258 fuentes:
un solo caracter de mas ahi mete listados, paginas institucionales y notas del
blog en el inventario de todas.

Solo lee archivos. No baja nada ni escribe en la base.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.parse
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from connectors.generico import patron_de_forma  # noqa: E402


# Una forma cuyo camino dice lo que hace: filtrar, buscar, contar clicks. La
# verificacion no las distingue de una ficha porque una pagina filtrada por
# ciudad tambien trae precios, operacion y fotos -de varias propiedades a la
# vez-. El nombre de la ruta es la evidencia de que no identifica UNA.
NO_ES_FICHA_POR_LA_RUTA = re.compile(
    r"(filtro|filtrar|aplicarfiltro|buscar|busqueda|search|listado|listar|"
    r"banners?|track|resultados?|pagina|categoria)", re.I)


def leer(ruta: Path) -> list[dict]:
    if not ruta.exists():
        return []
    return [json.loads(l) for l in ruta.open(encoding="utf-8") if l.strip()]


def raiz_de(url: str) -> str | None:
    """El origen, sin la busqueda con la que se descubrio el sitio.

    `domain` a veces trae la url del listado con filtros
    -/inmuebles?en=venta&tipo=local-. El connector arranca del origen.
    """
    p = urllib.parse.urlparse(url or "")
    if not p.netloc:
        return None
    return f"{p.scheme or 'https'}://{p.netloc}"


def host_de(url: str) -> str:
    return urllib.parse.urlparse(url or "").netloc.lower().replace("www.", "")


def hosts_compartidos(padron: dict) -> dict[str, int]:
    """Hosts que el padron le atribuye a mas de una inmobiliaria.

    Un host que aparece como web oficial de 13 agencias distintas no es la web
    propia de ninguna: o es un portal -inmoup.com.ar figura en 48 fichas del
    padron- o es una url mal atribuida. Ingerirlo publicaria el inventario de
    un sitio a nombre de doce inmobiliarias que no son sus duenas.

    Un SaaS marca blanca NO cae aca: le da a cada inmobiliaria su propio host
    -aguilarbugeau87.kitepropcrm.com-, que es exactamente la diferencia entre
    una web propia alojada en una plataforma y un perfil dentro de un portal.
    """
    cuenta: Counter = Counter()
    for cid, d in padron.items():
        h = host_de(d.get("selected_domain") or d.get("official_url") or "")
        if h:
            cuenta[h] += 1
    return {h: n for h, n in cuenta.items() if n > 1}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--verificado", nargs="+",
                    default=[r"D:\INMO CAPITAL\ROOT_SHAPES_VERIFIED.jsonl"])
    ap.add_argument("--salida", default=r"D:\INMO CAPITAL\CENSO_FORMAS.jsonl")
    ap.add_argument("--directorio",
                    default=r"D:\INMO CAPITAL\ERETZ_AGENCY_DATA\agency_web_directory.jsonl")
    a = ap.parse_args()

    padron = {x["canonical_agency_id"]: x for x in leer(Path(a.directorio))}
    compartidos = hosts_compartidos(padron)

    filas, motivos, excluidas = {}, Counter(), []
    for ruta in a.verificado:
        for r in leer(Path(ruta)):
            cid = r.get("canonical_agency_id")
            if r.get("veredicto") != "FORMA_DE_FICHA":
                motivos[r.get("veredicto") or "SIN_VEREDICTO"] += 1
                continue
            forma = r.get("forma") or ""
            if NO_ES_FICHA_POR_LA_RUTA.search(forma):
                motivos["LA_RUTA_DICE_QUE_NO_ES_FICHA"] += 1
                continue
            if patron_de_forma(forma) is None:
                # La forma existe pero no se puede traducir a un patron
                # acotado. Se deja afuera antes que habilitar algo que no se
                # sabe que va a alcanzar.
                motivos["FORMA_NO_TRADUCIBLE"] += 1
                continue
            base = raiz_de(r.get("domain") or "")
            if not base or not cid:
                motivos["SIN_DOMINIO"] += 1
                continue
            if cid in filas:
                motivos["DUPLICADA"] += 1
                continue
            n = compartidos.get(host_de(base), 0)
            if n > 1:
                motivos["WEB_COMPARTIDA_NO_PROPIA"] += 1
                excluidas.append({"canonical_agency_id": cid,
                                  "agency_name": r.get("agency_name"),
                                  "host": host_de(base), "agencias_en_el_host": n,
                                  "forma": forma,
                                  "motivo": "el padron le atribuye este host a "
                                            f"{n} inmobiliarias: no es web propia"})
                continue
            d = padron.get(cid) or {}
            eid = d.get("eretz_id")
            filas[cid] = {
                "canonical_agency_id": cid,
                "agency_name": r.get("agency_name") or d.get("agency_name"),
                "official_url": base,
                "connector_candidato": r.get("connector_candidato") or "generico",
                "clasificacion_nueva": "FORMA_VERIFICADA",
                "patron_ficha": forma,
                "eretz_id": int(eid) if str(eid).isdigit() else None,
                "urls_en_la_forma": r.get("urls_vistas"),
                "evidencia": r.get("motivo"),
                "verifier_version": r.get("verifier_version"),
            }
            motivos["HABILITADA"] += 1

    salida = Path(a.salida)
    with salida.open("w", encoding="utf-8") as fh:
        for f in sorted(filas.values(), key=lambda x: x["canonical_agency_id"]):
            fh.write(json.dumps(f, ensure_ascii=False) + "\n")

    if excluidas:
        ruta_ex = salida.with_name(salida.stem + "_EXCLUIDAS.jsonl")
        with ruta_ex.open("w", encoding="utf-8") as fh:
            for e in excluidas:
                fh.write(json.dumps(e, ensure_ascii=False) + "\n")

    print("### CENSO POR FORMA VERIFICADA ###")
    for k, v in motivos.most_common():
        print(f"  {k:26} {v:5}")
    con_id = sum(1 for f in filas.values() if f["eretz_id"])
    urls = sum(f.get("urls_en_la_forma") or 0 for f in filas.values())
    print(f"\n  fuentes habilitadas : {len(filas)}")
    print(f"  con eretz_id real   : {con_id}")
    print(f"  urls en esas formas : {urls:,}")
    print("  formas:")
    for k, v in Counter(f["patron_ficha"] for f in filas.values()).most_common(12):
        print(f"    {k:34} {v:4}")
    print(f"\n  artefacto -> {salida}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
