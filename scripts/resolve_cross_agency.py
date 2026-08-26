#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Resolver las urls reclamadas por mas de una inmobiliaria.

El indice unico no detiene esto: `hash_dedup` lleva el id de agencia adentro,
asi que dos agencias con la misma url producen hashes distintos y las dos
entrarian. Serian duplicados que nosotros introducimos, invisibles para la
constraint.

Adjudicar por cantidad de inventario -"gana la que mas tiene"- era comodo y
estaba mal: le da el aviso a la agencia mas grande sin mirar de quien es. Aca se
clasifica cada conflicto por su naturaleza y solo vuelve al write set lo que
tiene dueno demostrable.

  SAME_AGENCY_DUPLICATED_IN_ERETZ   la misma empresa esta dos veces en el padron
  SHARED_FRANCHISE_LISTING          oficinas de una red comparten el aviso
  SHARED_PLATFORM_INVENTORY         varias inmobiliarias sobre el mismo backend
  WHITE_LABEL_SHARED_SOURCE         un proveedor replica inventario entre perfiles
  CLEAR_OWNER                       la ficha dice de quien es
  AMBIGUOUS_CROSS_AGENCY            no alcanza la evidencia

Ningun claim se destruye: los secundarios quedan documentados con su evidencia.
Solo lee artefactos.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

SAME_AGENCY = "SAME_AGENCY_DUPLICATED_IN_ERETZ"
FRANQUICIA = "SHARED_FRANCHISE_LISTING"
PLATAFORMA = "SHARED_PLATFORM_INVENTORY"
WHITE_LABEL = "WHITE_LABEL_SHARED_SOURCE"
CLARO = "CLEAR_OWNER"
AMBIGUO = "AMBIGUOUS_CROSS_AGENCY"

# Solo estas dos categorias vuelven al write set, y la segunda unicamente si la
# canonica quedo resuelta con alta confianza.
LIBERABLES = {CLARO, SAME_AGENCY}

REDES = ("century", "remax", "re/max", "keller williams", "coldwell",
         "engel", "sothebys", "century 21")
RUIDO = {"inmobiliaria", "inmobiliarias", "propiedades", "negocios",
         "inmobiliarios", "inmobiliario", "bienes", "raices", "estate", "real",
         "grupo", "estudio", "sa", "srl", "sas", "ltda", "y", "de", "del",
         "la", "el", "los", "las"}


def norm(t: str) -> str:
    x = unicodedata.normalize("NFKD", str(t or "").lower())
    x = "".join(c for c in x if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", x).strip()


def tokens(t: str) -> set[str]:
    return {p for p in norm(t).split() if len(p) >= 3 and p not in RUIDO}


def host(u: str) -> str:
    return re.sub(r"^https?://(www\.)?", "", u or "").split("/")[0].lower()


def dueno_por_misatribucion(agencias: dict, descartados: set) -> tuple[dict | None, str]:
    """Quien queda cuando a los demas ya se les probo que el sitio no era suyo.

    El clasificador deduce "misma empresa duplicada" del apellido compartido en
    el mismo dominio, y ese es justamente el caso en que el apellido engaña: dos
    inmobiliarias homonimas en mercados que no se tocan dan la misma señal que
    una empresa cargada dos veces.

    Cuando una investigacion del padron ya dictamino que ESE sitio no era de un
    reclamante -y lo dejo asentado en el directorio de plataformas- ese
    reclamante deja de disputar. Si queda uno solo, el aviso tiene dueno.
    """
    if not descartados or len(agencias) != 1:
        return None, ""
    unico = next(iter(agencias.values()))
    return unico, ("se probo que el sitio no pertenece a "
                   + ", ".join(sorted(descartados))
                   + "; queda un unico reclamante")


def leer(ruta: Path) -> list[dict]:
    if not ruta.exists():
        return []
    out = []
    for l in ruta.open(encoding="utf-8"):
        l = l.strip()
        if not l:
            continue
        try:
            out.append(json.loads(l))
        except ValueError:
            continue
    return out


def dueno_por_ficha(claims: list[dict], url: str) -> tuple[dict | None, str]:
    """Quien publica el aviso, segun el aviso mismo.

    Es la unica evidencia que no depende de lo que nosotros creamos: si la ficha
    nombra a su oficina, esa es la duena, tenga el inventario que tenga.

    Se miran todos los campos que pueden llevar el nombre, no uno solo. En
    Century 21 el nombre de la oficina viene en `asesor` -"CENTURY 21 Franchi"-
    mientras `oficina_c21` trae el nombre de pila del agente: mirar un solo
    campo dejaba el conflicto sin resolver teniendo la respuesta al lado.
    """
    CAMPOS = ("oficina_c21", "asesor", "afiliadoNombre", "inmobiliaria", "agencia")
    firmas = set()
    for c in claims:
        ex = c.get("extra") or {}
        for campo in CAMPOS:
            v = ex.get(campo)
            if isinstance(v, str) and v.strip():
                firmas |= tokens(v)
    # La url tambien puede nombrar la oficina: .../oficina_133-franchi
    m = re.search(r"/oficina[_-]\d+-([a-z0-9-]+)", url or "", re.I)
    if m:
        firmas |= tokens(m.group(1).replace("-", " "))
    firmas -= {t for t in firmas if t in RUIDO}
    if not firmas:
        return None, ""

    coinciden = [c for c in claims
                 if tokens((c.get("provenance") or {}).get("agency_name", "")) & firmas]
    if len(coinciden) == 1:
        cual = (coinciden[0].get("provenance") or {}).get("agency_name")
        return coinciden[0], (f"la ficha identifica a la oficina publicante y solo "
                              f"{cual!r} coincide con ella")
    return None, ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--eligible", default=r"D:\INMO CAPITAL\DB_WRITE_ELIGIBLE.jsonl")
    ap.add_argument("--cross", default=r"D:\INMO CAPITAL\CROSS_AGENCY_DUPLICATES.jsonl")
    ap.add_argument("--data-dir", default=r"D:\INMO CAPITAL\ERETZ_AGENCY_DATA")
    ap.add_argument("--directorio-plataformas",
                    default=r"D:\INMO CAPITAL\agency_platform_directory.jsonl")
    ap.add_argument("--salida", default=r"D:\INMO CAPITAL")
    a = ap.parse_args()
    out = Path(a.salida)

    elegibles = leer(Path(a.eligible))
    cruzadas = leer(Path(a.cross))
    directorio = {d["canonical_agency_id"]: d
                  for d in leer(Path(a.data_dir) / "agency_web_directory.jsonl")}

    # Sitios que una investigacion del padron probo que NO son de quien los
    # reclamaba. Es evidencia verificada a mano, no una heuristica: por eso
    # puede desempatar lo que el parecido del nombre deja empatado.
    no_dueno = set()
    for d in leer(Path(a.directorio_plataformas)):
        mal = d.get("domain_mal_atribuido")
        if mal and d.get("canonical_agency_id"):
            no_dueno.add((d["canonical_agency_id"], host(mal)))

    por_url = defaultdict(list)
    for p in elegibles + cruzadas:
        por_url[p.get("source_url")].append(p)
    disputadas = {u: g for u, g in por_url.items()
                  if len({x.get("canonical_agency_id") for x in g}) > 1}

    # Cuantas inmobiliarias distintas vive cada host: separa el sitio propio
    # duplicado del backend compartido por muchas.
    agencias_por_host = defaultdict(set)
    for p in elegibles + cruzadas:
        agencias_por_host[host(p.get("source_url"))].add(p.get("canonical_agency_id"))

    print("### CONFLICTOS CROSS-AGENCY ###")
    print(f"  urls disputadas: {len(disputadas):,}")
    print(f"  claims:          {sum(len(g) for g in disputadas.values()):,}\n",
          flush=True)

    resoluciones, dup_agencias = [], {}
    for url, claims in disputadas.items():
        h = host(url)
        agencias = {c.get("canonical_agency_id"): c for c in claims}
        descartados = {cid for cid in agencias if (cid, h) in no_dueno}
        if descartados and len(agencias) - len(descartados) == 1:
            claims = [c for c in claims
                      if c.get("canonical_agency_id") not in descartados]
            agencias = {cid: c for cid, c in agencias.items()
                        if cid not in descartados}
        else:
            descartados = set()
        nombres = {cid: (c.get("provenance") or {}).get("agency_name") or ""
                   for cid, c in agencias.items()}
        n_host = len(agencias_por_host[h])

        # 1. La ficha nombra a su oficina.
        dueno, motivo = dueno_por_misatribucion(agencias, descartados)
        if dueno is None:
            dueno, motivo = dueno_por_ficha(claims, url)
        if dueno is not None:
            categoria, confianza = CLARO, "alta"
        else:
            juegos = [tokens(n) for n in nombres.values()]
            mismo_nombre = bool(juegos) and all(
                j and (j <= juegos[0] or juegos[0] <= j) for j in juegos)
            de_red = any(any(r in norm(n) for r in REDES) for n in nombres.values())

            if mismo_nombre and n_host <= 3:
                # Mismo sitio, mismo nombre distintivo, host no compartido: es
                # la misma empresa cargada dos veces en el padron.
                categoria, confianza = SAME_AGENCY, "alta"
                motivo = ("mismo dominio y mismas palabras distintivas: la misma "
                          "empresa esta duplicada en el padron")
                dup_agencias[tuple(sorted(agencias))] = {
                    "ids": sorted(agencias), "nombres": nombres, "dominio": h}
            elif de_red:
                categoria, confianza = FRANQUICIA, "baja"
                motivo = ("oficinas de una red comparten el aviso y la ficha no "
                          "dice cual lo publica")
            elif n_host > 3:
                categoria, confianza = (PLATAFORMA if n_host > 10 else WHITE_LABEL), "baja"
                motivo = (f"{n_host} inmobiliarias distintas publican en {h}: "
                          f"backend compartido, no se puede adjudicar por la url")
            else:
                categoria, confianza = AMBIGUO, "baja"
                motivo = "no hay evidencia para adjudicar el aviso"
            dueno = None

        resoluciones.append({
            "source_url": url, "host": h, "categoria": categoria,
            "confianza": confianza, "motivo": motivo,
            "canonical_owner": (dueno or {}).get("canonical_agency_id"),
            "eretz_id_owner": (dueno or {}).get("inmobiliaria_id"),
            "reclamantes": [{"canonical_agency_id": cid,
                             "agency_name": nombres[cid],
                             "eretz_id": agencias[cid].get("inmobiliaria_id"),
                             "connector": agencias[cid].get("connector")}
                            for cid in agencias],
            # SAME_AGENCY no se libera sola: saber que son la misma empresa no
            # dice cual de las dos fichas conserva ERETZ, y elegir mal deja el
            # inventario colgando de un id que despues se unifica o se borra.
            "descartados_por_evidencia": sorted(descartados),
            "liberable": categoria == CLARO and confianza == "alta",
            "checked_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        })

    (out / "CROSS_AGENCY_RESOLUTION.jsonl").write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in resoluciones),
        encoding="utf-8")

    # Manifiesto de agencias duplicadas en el padron: es un problema del padron,
    # no de la ingesta, y hay que resolverlo alla.
    manifiesto = []
    for ids, info in dup_agencias.items():
        urls = [r["source_url"] for r in resoluciones
                if r["categoria"] == SAME_AGENCY
                and {c["canonical_agency_id"] for c in r["reclamantes"]} == set(ids)]
        fichas = []
        for cid in info["ids"]:
            d = directorio.get(cid) or {}
            fichas.append({"canonical_agency_id": cid,
                           "eretz_id": d.get("eretz_id"),
                           "nombre": d.get("canonical_name"),
                           "dominio": d.get("selected_domain"),
                           "provincia": d.get("province"),
                           "estado_web": d.get("status")})
        manifiesto.append({
            "ids_implicados": info["ids"], "dominio": info["dominio"],
            "fichas": fichas, "urls_en_conflicto": len(urls),
            "evidencia": ["mismo dominio", "mismas palabras distintivas del nombre"],
            # Sugerencia, no decision. El id mas bajo es la ficha mas antigua
            # del padron, que es una convencion, no evidencia: en uno de los
            # tres casos la ficha mas antigua es justamente la que NO tiene
            # dominio verificado. Por eso viaja al lado la otra senal, y el
            # criterio queda escrito para que nadie lo tome por un veredicto.
            "candidata_por_antiguedad": min(
                (f for f in fichas if str(f.get("eretz_id")).isdigit()),
                key=lambda f: int(f["eretz_id"]), default=None),
            "criterio_de_la_candidata": "eretz_id mas bajo = ficha mas antigua "
                                        "del padron. Es una convencion, no "
                                        "evidencia de cual conserva ERETZ",
            "fichas_con_web_verificada": [
                f for f in fichas
                if f.get("dominio") and "HIGH_CONFIDENCE" in str(f.get("estado_web"))
                or f.get("dominio") and "VERIFIED" in str(f.get("estado_web"))],
            "confidence": "alta para que son la misma empresa; la canonica "
                          "requiere confirmar cual ficha conserva ERETZ",
            "accion_propuesta": ("unificar en el padron antes de ingerir: hasta "
                                 "entonces sus propiedades quedan fuera del "
                                 "write set"),
            "checked_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        })
    (out / "AGENCY_DUPLICATE_RESOLUTION_MANIFEST.jsonl").write_text(
        "\n".join(json.dumps(m, ensure_ascii=False) for m in manifiesto),
        encoding="utf-8")

    print("  clasificacion:")
    for k, v in Counter(r["categoria"] for r in resoluciones).most_common():
        lib = sum(1 for r in resoluciones if r["categoria"] == k and r["liberable"])
        print(f"    {k:34} {v:5,}  liberables: {lib}")
    print(f"\n  agencias duplicadas en el padron: {len(manifiesto)}")
    for m in manifiesto[:5]:
        print(f"    {m['dominio'][:34]:34} ids={m['ids_implicados']} "
              f"urls={m['urls_en_conflicto']}")
    print(f"\n  artefactos -> CROSS_AGENCY_RESOLUTION.jsonl / "
          f"AGENCY_DUPLICATE_RESOLUTION_MANIFEST.jsonl")
    print("  Ningun claim se borro: los secundarios quedan con su evidencia.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
