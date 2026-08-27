#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Que propiedades pueden escribirse hoy en propiedades_raw, y cuales no.

La regla no admite matices: una propiedad solo entra a la base si su
inmobiliaria tiene `eretz_id` real. Un id sintetico, derivado o temporal
produciria filas que no pertenecen a ninguna inmobiliaria existente, y ese error
no se nota al insertar: aparece meses despues, cuando alguien une las tablas y
faltan agencias.

Las que no lo tienen quedan AGENCY_ID_PENDING. Se descubren, se normalizan, se
validan y viven en los artefactos; simplemente no se escriben todavia.

Solo lee artefactos. No toca la base ni la red.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.parse
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from connectors.base import calcular_hash_dedup  # noqa: E402
from scripts.input_universe import (OBLIGATORIAS, UNIVERSE_VERSION,  # noqa: E402
                                    rutas)

ELEGIBLE = "DB_WRITE_ELIGIBLE"
PENDIENTE = "AGENCY_ID_PENDING"
NO_ES_FICHA = "NO_ES_UNA_FICHA"
CROSS_AGENCIA = "CROSS_AGENCY_DUPLICATE"
WEB_AJENA = "WEB_NO_PROPIA"
DUPLICADA = "DUPLICADO_EN_ENTRADA"
SITIO_AJENO = "SITIO_PROBADO_AJENO"

# Un perfil en un portal no es la web de la inmobiliaria, y su catalogo no es su
# inventario: choza.ai figura como web oficial de 36 agencias distintas. Escribir
# lo que se lee ahi le atribuye a una el inventario de las otras 35.
#
# La pagina de la oficina DENTRO de su propia red -century21.com.ar/oficina/X-
# si es suya, y no cae aca.
NO_SON_WEB_PROPIA = {"EXTERNAL_PORTAL_PROFILE", "AMBIGUOUS_WEB_ATTRIBUTION",
                     # Una guia de rubros o un diario de la zona. Se
                     # comprobo mirando que publica el sitio.
                     "NOT_A_REAL_ESTATE_WEB"}

# Defensa en profundidad: aunque el connector ya filtre, lo que llega a la base
# se revisa otra vez. Las paginas que se cuelan son siempre las mismas y entran
# porque comparten la ruta con las fichas: el listado se llama "propiedades" y
# la busqueda "buscar-propiedades".
RECHAZOS = [
    ("query_string", re.compile(r"[?#]")),
    ("busqueda", re.compile(r"/(buscar|busqueda|search|filtrar|filtro|"
                            r"resultados?|results?)(/|$|-)", re.I)),
    ("paginacion", re.compile(r"/(page|pagina|pag)[/_-]?\d+/?$", re.I)),
    ("categoria_o_tag", re.compile(r"/(category|categoria|categorias|tag|tags|"
                                   r"etiqueta|etiquetas|rubro)(/|$)", re.I)),
    ("archivo_por_fecha", re.compile(r"/\d{4}/\d{2}(/\d{2})?/?$")),
    ("institucional", re.compile(r"/(nosotros|about|quienes[-_]somos|contacto|"
                                 r"contact|servicios|tasacion|blog|noticias|"
                                 r"novedades|privacidad|terminos|login|admin|"
                                 r"sucursales|equipo|staff|faq)(/|$)", re.I)),
    ("feed_o_recurso", re.compile(r"(/feed/?$|\.(xml|json|rss|pdf|jpe?g|png)$)", re.I)),
    ("solo_la_seccion", re.compile(r"/(propiedades|inmuebles|propert(y|ies)|"
                                   r"listings?|emprendimientos)/?$", re.I)),
    # Segunda capa para Wasi. El connector filtra por forma de ficha y no emite
    # ninguna de estas, pero con WordPress la primera capa tambien alcanzaba
    # "en teoria" y entraron 56 paginas de busqueda igual: donde hay una sola
    # barrera, tarde o temprano se pasa algo.
    ("listado_wasi", re.compile(r"://[^/]+/s/[a-z0-9-]+(/[a-z0-9-]+)?/?$", re.I)),
    ("institucional_wasi", re.compile(r"/main-[a-z0-9-]+\.html?$", re.I)),
]

# Un id que es en realidad una query string o un texto largo no identifica nada.
LARGO_MAXIMO_ID = 120

# Una ficha termina identificando UNA propiedad: el ultimo tramo de la ruta
# lleva un numero largo. Sirve para no confundir la pagina de resultados con la
# ficha que cuelga de ella.
RE_TERMINA_EN_ID = re.compile(r"/[^/]*\d{4,}[^/]*/?$")


def _host(u):
    return re.sub(r"^https?://(www[.])?", "", u or "").split("/")[0].lower()


def motivo_rechazo(p: dict) -> str | None:
    url = p.get("source_url") or ""
    if not url.startswith("http"):
        return "url_invalida"
    lid = str(p.get("source_listing_id") or "")
    if not lid:
        return "sin_source_listing_id"
    if len(lid) > LARGO_MAXIMO_ID or "=" in lid or "&" in lid:
        return "id_derivado_de_query"
    ruta = urllib.parse.urlparse(url).path
    for nombre, patron in RECHAZOS:
        if not patron.search(url):
            continue
        # "busqueda" no es lo mismo cuando la ficha CUELGA del buscador.
        # laroccapropiedades.com publica cada propiedad en
        # /busqueda/ver/8693745-2/: la regla le rechazaba 88 fichas reales
        # -verificado: esa url sirve "Mario Bravo al 600", una direccion-.
        # Se sigue rechazando /buscar-propiedades/ y /busqueda/casas/, que no
        # identifican ninguna propiedad.
        if nombre == "busqueda" and RE_TERMINA_EN_ID.search(ruta):
            continue
        return nombre
    return None


def escribir_jsonl(ruta: Path, filas) -> None:
    """Una linea por vez, y a un temporal.

    Armar el artefacto entero como un solo string murio con MemoryError:
    143.000 propiedades son 740 MB y el join los construye completos en
    memoria antes de escribir el primer byte. Peor todavia, el fallo dejo el
    artefacto anterior en CERO, porque write_text ya lo habia truncado. Por
    eso ademas se escribe al lado y recien al final se reemplaza: un fallo a
    la mitad no puede destruir lo que ya estaba.
    """
    tmp = ruta.with_suffix(ruta.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        for f in filas:
            fh.write(json.dumps(f, ensure_ascii=False) + "\n")
    tmp.replace(ruta)


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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--entradas", nargs="*", default=None,
                    help="por defecto, el universo canonico de "
                         "scripts/input_universe.py")
    ap.add_argument("--data-dir", default=r"D:\INMO CAPITAL\ERETZ_AGENCY_DATA")
    ap.add_argument("--salida", default=r"D:\INMO CAPITAL\DB_WRITE_ELIGIBLE.jsonl")
    ap.add_argument("--directorio-plataformas",
                    default=r"D:\INMO CAPITAL\agency_platform_directory.jsonl")
    ap.add_argument("--resolucion", default="",
                    help="CROSS_AGENCY_RESOLUTION.jsonl; sin el, ningun "
                         "conflicto cross-agency se libera")
    a = ap.parse_args()

    padron = {}
    for d in leer(Path(a.data_dir) / "agency_web_directory.jsonl"):
        eid = d.get("eretz_id")
        if str(eid).isdigit():
            padron[d["canonical_agency_id"]] = int(eid)

    # Clasificacion de la web de cada agencia. La produce
    # reclassify_portal_profiles.py contando cuantas inmobiliarias cuelgan del
    # mismo host, sin depender de conocer el nombre de cada portal.
    tipo_de_web = {}

    # Sitios que una investigacion del padron probo que NO son de quien los
    # reclamaba. La correccion vivia solo en el directorio de plataformas y la
    # entidad seguia scrapeando la url ajena: 5 propiedades de otra
    # inmobiliaria entraron al write set bajo su id.
    no_dueno = set()
    for d in leer(Path(a.directorio_plataformas)):
        mal = d.get("domain_mal_atribuido")
        if mal and d.get("canonical_agency_id"):
            no_dueno.add((d["canonical_agency_id"], _host(mal)))
    for d in leer(Path(a.directorio_plataformas)):
        tipo_de_web[d["canonical_agency_id"]] = d.get("web_kind")

    props: list[dict] = []
    # El universo no se arma a mano en la linea de comandos. Se armaba asi, y
    # una lista a la que le faltaban dos rollouts produjo un write set 791
    # propiedades mas chico sin una sola linea de error: write_eligibility no
    # tiene como saber que le falta un archivo que nadie le paso.
    if not a.entradas:
        a.entradas = [str(x) for x in rutas()]
        print(f"universo canonico: {len(a.entradas)} entradas "
              f"({UNIVERSE_VERSION})")
    else:
        dados = {Path(e).parent.name for e in a.entradas}
        faltan = OBLIGATORIAS - dados
        if faltan:
            print("ERROR: faltan entradas obligatorias del universo: "
                  + ", ".join(sorted(faltan)))
            print("Omitirlas no da error mas adelante, da menos propiedades.")
            return 2

    for e in a.entradas:
        props.extend(leer(Path(e)))
    if not props:
        print("sin propiedades")
        return 1

    elegibles, pendientes, descartadas, ajenas = [], [], [], []
    duplicadas = []
    vistos_hash = set()
    for p in props:
        kind = tipo_de_web.get(p.get("canonical_agency_id"))
        if kind in NO_SON_WEB_PROPIA:
            ajenas.append({**p, "db_write_status": WEB_AJENA, "web_kind": kind})
            continue
        if (p.get("canonical_agency_id"), _host(p.get("source_url"))) in no_dueno:
            ajenas.append({**p, "db_write_status": SITIO_AJENO,
                           "web_kind": SITIO_AJENO})
            continue
        motivo = motivo_rechazo(p)
        if motivo:
            descartadas.append({**p, "motivo_rechazo": motivo})
            continue
        real = padron.get(p.get("canonical_agency_id"))
        if real is None:
            pendientes.append(p)
            continue
        q = dict(p)
        q["inmobiliaria_id"] = real
        # El hash depende del id, asi que se recalcula con el real: el del
        # artefacto se produjo con el sustituto del canary y no coincidiria con
        # lo que produce produccion.
        q["hash_dedup"] = calcular_hash_dedup(real, p.get("source_url"))
        if q["hash_dedup"] in vistos_hash:
            # Dos urls que normalizan igual son la misma propiedad. Escribir las
            # dos no crearia un duplicado -el indice unico lo impide- pero haria
            # que la reconciliacion no cierre.
            #
            # Descartarlas con un `continue` pelado tampoco cerraba: 428
            # propiedades desaparecian del recuento sin quedar en ninguna
            # categoria, que es la perdida silenciosa que este artefacto existe
            # para no tener. Se van a un balde propio, contadas y guardadas.
            duplicadas.append({**q, "db_write_status": DUPLICADA})
            continue
        vistos_hash.add(q["hash_dedup"])
        q["db_write_status"] = ELEGIBLE
        elegibles.append(q)

    # --- misma url reclamada por dos inmobiliarias ---------------------------
    # El hash lleva el id de agencia, asi que dos agencias con la MISMA url dan
    # hashes distintos y las dos entrarian a la base: dos copias del mismo
    # inmueble bajo duenos distintos, duplicados introducidos por nosotros
    # aunque el indice unico no los vea.
    #
    # No se fusiona nada. Se conserva la copia de la agencia que mas inventario
    # aporta en ese dominio -la que mejor evidencia tiene de ser la duena- y las
    # otras quedan documentadas para que alguien decida.
    por_url = defaultdict(list)
    for q in elegibles:
        por_url[q.get("source_url")].append(q)

    # La adjudicacion NO se decide aca por tamano de inventario: eso le daba el
    # aviso a la agencia mas grande sin mirar de quien era. La decide
    # resolve_cross_agency.py con la evidencia de cada ficha, y aca solo se
    # aplica. Sin ese archivo, ningun conflicto se libera.
    resolucion = {}
    ruta_res = Path(a.resolucion) if a.resolucion else         Path(a.salida).with_name("CROSS_AGENCY_RESOLUTION.jsonl")
    for r in leer(ruta_res):
        resolucion[r.get("source_url")] = r

    cruzadas, conservadas = [], []
    for url, grupo in por_url.items():
        if len({q.get("canonical_agency_id") for q in grupo}) <= 1:
            conservadas.extend(grupo)
            continue
        r = resolucion.get(url) or {}
        dueno = r.get("canonical_owner") if r.get("liberable") else None
        for q in grupo:
            if dueno and q.get("canonical_agency_id") == dueno:
                q["cross_agency"] = {"categoria": r.get("categoria"),
                                     "motivo": r.get("motivo"),
                                     "reclamantes": [c.get("canonical_agency_id")
                                                     for c in r.get("reclamantes") or []]}
                conservadas.append(q)
            else:
                cruzadas.append({**q,
                                 "db_write_status": CROSS_AGENCIA,
                                 "categoria_conflicto": r.get("categoria") or "SIN_RESOLVER",
                                 "motivo_conflicto": r.get("motivo") or
                                 "conflicto todavia sin clasificar",
                                 "adjudicada_a": dueno,
                                 "url_en_disputa": url})
    elegibles = conservadas
    if cruzadas:
        ruta_cross = Path(a.salida).with_name("CROSS_AGENCY_DUPLICATES.jsonl")
        escribir_jsonl(ruta_cross, cruzadas)
        print(f"  {CROSS_AGENCIA:26}  {len(cruzadas):,}  (misma url, dos inmobiliarias)")
        for k, v in Counter(q["categoria_conflicto"] for q in cruzadas).most_common():
            print(f"      {k:34} {v:6,}")
        print(f"      -> {ruta_cross}")

    escribir_jsonl(Path(a.salida), elegibles)

    n = len(props)
    print("### ELEGIBILIDAD PARA ESCRITURA EN propiedades_raw ###")
    print(f"  propiedades analizadas:     {n:,}")
    print(f"  {ELEGIBLE:24}    {len(elegibles):,}  ({len(elegibles)/n*100:.1f}%)")
    print(f"  {PENDIENTE:24}    {len(pendientes):,}  ({len(pendientes)/n*100:.1f}%)")
    print(f"  {NO_ES_FICHA:24}    {len(descartadas):,}  ({len(descartadas)/n*100:.1f}%)")
    print(f"  {WEB_AJENA:24}    {len(ajenas):,}  ({len(ajenas)/n*100:.1f}%)")
    print(f"  {DUPLICADA:24}    {len(duplicadas):,}  "
          f"({len(duplicadas)/n*100:.1f}%)")
    if duplicadas:
        ruta_dup = Path(a.salida).with_name("DUPLICADO_EN_ENTRADA.jsonl")
        escribir_jsonl(ruta_dup, duplicadas)
        print(f"      -> {ruta_dup}")
    if ajenas:
        ruta_ajenas = Path(a.salida).with_name("WEB_NO_PROPIA.jsonl")
        escribir_jsonl(ruta_ajenas, ajenas)
        for k, v in Counter(q["web_kind"] for q in ajenas).most_common():
            print(f"      {k:26} {v:6,}")
        print(f"      -> {ruta_ajenas}")
    if descartadas:
        ruta_desc = Path(a.salida).with_name("NO_ES_UNA_FICHA.jsonl")
        escribir_jsonl(ruta_desc, [{**x, "db_write_status": NO_ES_FICHA}
                                   for x in descartadas])
        print(f"      -> {ruta_desc}")
        for k, v in Counter(x["motivo_rechazo"] for x in descartadas).most_common():
            print(f"      {k:26} {v:6,}")
    # --- reconciliacion ------------------------------------------------------
    # Cada propiedad analizada tiene que estar en exactamente una categoria.
    # No es una formalidad: las 428 que se perdian por el descarte de hashes
    # repetidos no daban ningun error, solo un write set mas chico.
    baldes = {ELEGIBLE: len(elegibles), CROSS_AGENCIA: len(cruzadas),
              PENDIENTE: len(pendientes), NO_ES_FICHA: len(descartadas),
              WEB_AJENA: len(ajenas), DUPLICADA: len(duplicadas)}
    suma = sum(baldes.values())
    print(f"\n  RECONCILIACION  analizadas={n:,}  suma={suma:,}")
    if suma != n:
        print(f"  *** NO CIERRA: {n - suma:+,} sin categoria ***")
        for k, v in baldes.items():
            print(f"      {k:28} {v:7,}")
        return 2
    print("  cierra: ninguna propiedad quedo sin explicacion")

    print(f"\n  agencias elegibles:         "
          f"{len({q['canonical_agency_id'] for q in elegibles}):,}")
    print(f"  agencias sin eretz_id:      "
          f"{len({p.get('canonical_agency_id') for p in pendientes}):,}")
    print(f"  hash unicos entre elegibles:"
          f"{len({q['hash_dedup'] for q in elegibles}):,}")
    print(f"\n  por connector (elegibles):  "
          f"{dict(Counter(q.get('connector') for q in elegibles))}")
    print(f"  por connector (pendientes): "
          f"{dict(Counter(p.get('connector') for p in pendientes))}")

    # --- manifiesto de agencias sin id real ---------------------------------
    # No se inventa ningun id. Se documenta que falta y por que, para que quien
    # pueda resolverlo tenga todo a mano.
    por_agencia = defaultdict(list)
    for x in pendientes:
        por_agencia[x.get("canonical_agency_id")].append(x)
    manifiesto = []
    for cid, g in sorted(por_agencia.items(), key=lambda t: -len(t[1])):
        prov = g[0].get("provenance") or {}
        manifiesto.append({
            "canonical_agency_id": cid,
            "agency_name": prov.get("agency_name"),
            "official_domain": prov.get("official_domain"),
            "connector": g[0].get("connector"),
            "propiedades_descubiertas": len(g),
            "estado": PENDIENTE,
            "motivo": ("la entidad no tiene eretz_id en el crosswalk canonico: "
                       "esta en el padron de Roomix pero no se pudo enlazar con "
                       "una inmobiliaria de ERETZ"),
            "evidencia_disponible": {
                "urls_de_ejemplo": [x.get("source_url") for x in g[:3]],
                "plataforma": prov.get("source_platform"),
            },
        })
    ruta_man = Path(a.salida).with_name("AGENCY_ID_PENDING_MANIFEST.jsonl")
    escribir_jsonl(ruta_man, manifiesto)

    print()
    print(f"  agencias en {PENDIENTE}: {len(manifiesto)}")
    for m in manifiesto[:10]:
        print(f"    {(m['agency_name'] or '?')[:36]:36} "
              f"{m['propiedades_descubiertas']:5,} props  {m['connector']}")
    print(f"  manifiesto -> {ruta_man}")
    print(f"\n  artefacto -> {a.salida}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
