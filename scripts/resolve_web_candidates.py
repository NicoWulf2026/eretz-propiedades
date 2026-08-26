#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Bajar los candidatos que ya tenemos y decidir con evidencia leida.

El motor de identidad estaba construido y probado, y la libreria de discovery
tambien. Faltaba lo que las une: alguien que BAJE la pagina candidata y le pase
el contenido. Sin eso, `A.L.A.N. PROPIEDADES` tenia guardado
`alanpropiedades.com.ar` como candidato, puntaje 0 y evidencia vacia -ni a favor
ni en contra-, porque nunca se leyo la pagina. La auditoria anterior
-`free_web_audit_v1`- puntuo urls sin abrirlas.

4.306 entidades quedaron sin resolver y 1.634 de ellas ya tienen candidatos
guardados. Resolverlas no necesita ninguna API de busqueda paga: la busqueda ya
se hizo y se pago. Lo que falta es leer.

Este script no inventa candidatos ni sale a buscar afuera. Solo abre los que ya
estan, y para cada entidad produce:

  identidad      VERIFIED / HIGH_CONFIDENCE / AMBIGUOUS / rechazos, con la
                 evidencia que lo justifica y el puntaje que la explica
  url historica  VALID / DEAD / REDIRECTED / REPLACED / ... cuando hay una
  scrapeabilidad diagnostico tecnico superficial, sin scrapear inventario

Lo que no se puede demostrar no se afirma: una entidad sin candidatos utiles
queda SEARCH_API_PENDING, nunca NOT_FOUND. Que falte proveedor de busqueda no es
evidencia de que la inmobiliaria no tenga web.

Reanudable: cada entidad terminada se escribe y no se repite.
No escribe en ninguna base.
"""
from __future__ import annotations

import argparse
import json
import sys
import threading
import time
import urllib.parse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from html import unescape
from pathlib import Path

import re

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from connectors.base import (Bloqueado, Descargador, ErrorPermanente,  # noqa: E402
                             ErrorTransitorio, LimitadorDeRitmo)
from scripts.agency_web_discovery import Candidata, fila_de_salida, verificar  # noqa: E402
from scripts.identity_scoring import (SCORING_VERSION, UMBRAL_ALTA,  # noqa: E402
                                      UMBRAL_VERIFIED, clasificar,
                                      diagnosticar_scrapeabilidad,
                                      diagnosticar_url_historica, puntuar)

RUNNER_VERSION = "resolve_web_candidates_v1"

# Estados que significan "todavia no lo sabemos", no "no existe".
SIN_RESOLVER = {"NO_EXISTING_WEB_DATA", "SEARCH_SECOND_PASS_REQUIRED",
                "OFFICIAL_WEB_AMBIGUOUS"}

# Cuantos candidatos se abren por entidad. Los buscadores devuelven ruido
# despues de los primeros: abrir diez para encontrar el mismo dominio del primer
# resultado es gastar cortesia ajena.
MAX_CANDIDATOS = 4

# Presupuesto por entidad. Un host que acepta la conexion y no contesta cuesta
# 75 segundos por pedido; sin este techo, una sola entidad retiene un worker
# durante toda la corrida. Ya paso con una fuente en el rollout anterior.
PRESUPUESTO_POR_ENTIDAD = 180

RE_TITULO = re.compile(r"<title[^>]*>(.{1,300}?)</title>", re.S | re.I)
RE_TAG = re.compile(r"<(script|style|noscript)[^>]*>.*?</\1>", re.S | re.I)


def texto_visible(html: str) -> str:
    t = RE_TAG.sub(" ", html or "")
    t = re.sub(r"<[^>]+>", " ", t)
    return re.sub(r"\s+", " ", unescape(t)).strip()


def leer_jsonl(ruta: Path) -> list[dict]:
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


class Escritor:
    """Append seguro desde varios hilos, abriendo y cerrando en cada tanda."""

    def __init__(self, ruta: Path):
        self.ruta = Path(ruta)
        self.ruta.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def escribir(self, fila: dict) -> None:
        linea = json.dumps(fila, ensure_ascii=False) + "\n"
        with self._lock:
            with self.ruta.open("a", encoding="utf-8") as fh:
                fh.write(linea)
                fh.flush()


def abrir(d: Descargador, url: str, origen: str) -> Candidata:
    """Una candidata con lo que la pagina realmente dijo."""
    c = Candidata(url=url, origen=origen)
    try:
        html = d.bajar(url)
    except Bloqueado as e:
        c.http = 403
        c.texto = f"[bloqueado] {str(e)[:80]}"
        return c
    except ErrorPermanente as e:
        c.http = 404
        c.texto = f"[no existe] {str(e)[:80]}"
        return c
    except ErrorTransitorio as e:
        c.http = None
        c.texto = f"[sin respuesta] {str(e)[:80]}"
        return c
    c.http = 200
    m = RE_TITULO.search(html or "")
    c.titulo = unescape(m.group(1)).strip()[:300] if m else ""
    c.texto = texto_visible(html)[:20000]
    return c


def aplicar_veto(salida: dict, mejor_p) -> dict:
    """Reconcilia el veredicto por nombre con lo que dice la pagina.

    Funcion pura: recibe la fila y el puntaje, devuelve la fila. Se
    separo para poder fijarla con tests sin abrir una sola conexion.
    """
    # --- el que leyo la pagina tiene veto -------------------------------
    #
    # `verificar()` decide por nombre y dominio: no abre la pagina. El scoring
    # si la lee. Cuando discrepan, mandan los ojos.
    #
    # Lo vimos en el canario, y son los dos errores que mas caro salen:
    #   A.MAGGIO PROPIEDADES  -> VERIFIED con puntaje -100, que es el rechazo
    #                            por rubro: el sitio vende otra cosa.
    #   A. ZACCARDI Propiedades -> VERIFIED apuntando a una pagina de creditos
    #                            hipotecarios, con 31 puntos sobre 70.
    #
    # Un dominio parecido al nombre no demuestra identidad. Es la misma regla
    # por la que "Lopez Propiedades" en una tienda de ropa no es una
    # inmobiliaria.
    estado = salida.get("official_web_status")
    if salida.get("discovered_domain") and mejor_p is not None:
        veto = None
        if mejor_p.rechazado_por_rubro:
            # El rechazo cubre dos casos distintos y conviene nombrarlos: el
            # sitio vende otra cosa, o la url es una nota SOBRE la inmobiliaria
            # y no su sitio.
            veto = (f"el sitio es de {mejor_p.rubro_detectado}, no una inmobiliaria"
                    if mejor_p.rubro_detectado
                    else "la url es una nota sobre la inmobiliaria, no su sitio")
        elif mejor_p.total <= 0:
            veto = "la pagina no aporta ninguna evidencia a favor"
        elif estado == "OFFICIAL_WEB_VERIFIED" and mejor_p.total < UMBRAL_VERIFIED:
            veto = (f"{mejor_p.total} puntos: alcanza para sospechar, "
                    f"no para afirmar (VERIFIED pide {UMBRAL_VERIFIED})")
        if veto:
            salida["veto_del_scoring"] = veto
            salida["discovered_domain_rechazado"] = salida["discovered_domain"]
            if mejor_p.rechazado_por_rubro or mejor_p.total <= 0:
                salida["discovered_domain"] = None
                salida["official_web_status"] = ("CANDIDATE_REJECTED_OTHER_ENTITY"
                                                 if mejor_p.rechazado_por_rubro
                                                 else "OFFICIAL_WEB_AMBIGUOUS")
            elif mejor_p.total >= UMBRAL_ALTA:
                salida["official_web_status"] = "OFFICIAL_WEB_HIGH_CONFIDENCE"
            else:
                # Por debajo de HIGH_CONFIDENCE el dominio no se publica. Se
                # conserva como candidato para que la evidencia no se pierda,
                # pero no ocupa el lugar de una web oficial: una url dudosa en
                # ese campo se lee despues como si fuera un hecho.
                salida["official_web_status"] = "OFFICIAL_WEB_AMBIGUOUS"
                salida["candidato_no_confirmado"] = salida["discovered_domain"]
                salida["discovered_domain"] = None
            salida["reason"] = f"{salida.get('reason','')} | veto: {veto}"

    return salida


def resolver(ent: dict, fila: dict, lim: LimitadorDeRitmo) -> dict:
    """Abre los candidatos de una entidad y decide con lo leido."""
    t0 = time.time()
    d = Descargador(lim, limite_bytes=600_000)
    urls, vistos = [], set()
    for u in (fila.get("candidate_urls") or []):
        dom = urllib.parse.urlparse(u).netloc.lower().replace("www.", "")
        if not u.startswith("http") or dom in vistos:
            continue
        vistos.add(dom)
        urls.append(u)
        if len(urls) >= MAX_CANDIDATOS:
            break

    candidatas: list[Candidata] = []
    agotado = False
    for u in urls:
        if time.time() - t0 > PRESUPUESTO_POR_ENTIDAD:
            agotado = True
            break
        candidatas.append(abrir(d, u, "candidato_guardado"))

    salida = fila_de_salida(ent, verificar(ent, candidatas), candidatas)

    # Puntaje explicable sobre la candidata que el discovery eligio; si no
    # eligio ninguna, sobre la que mejor puntue. El puntaje no reemplaza al
    # veredicto: lo explica y lo puede degradar.
    elegida = salida.get("discovered_domain")
    mejor, mejor_p = None, None
    for c in candidatas:
        if c.http != 200:
            continue
        p = puntuar(ent, {"url": c.url, "titulo": c.titulo, "texto": c.texto})
        if mejor_p is None or p.total > mejor_p.total:
            mejor, mejor_p = c, p
        if elegida and c.url == elegida:
            mejor, mejor_p = c, p
            break

    if mejor_p is not None:
        salida["identity_score"] = mejor_p.total
        salida["identity_status_scoring"] = clasificar(mejor_p)
        salida["positive_evidence"] = [s.clave for s in mejor_p.positivas]
        salida["negative_evidence"] = [s.clave for s in mejor_p.negativas]
        salida["scoring_reason"] = mejor_p.explicacion
        salida["scoring_version"] = SCORING_VERSION
        salida["candidata_puntuada"] = mejor.url
    else:
        salida["identity_score"] = None
        salida["identity_status_scoring"] = None
        salida["positive_evidence"] = []
        salida["negative_evidence"] = []
        salida["scoring_reason"] = ("ninguna candidata respondio"
                                    if candidatas else "sin candidatas guardadas")

    salida = aplicar_veto(salida, mejor_p)

    # --- url historica ---
    previa = fila.get("previous_url")
    if previa:
        cand = None
        if mejor is not None:
            cand = {"url": mejor.url, "http": mejor.http,
                    "redirects": mejor.redirects, "texto": mejor.texto}
        h = diagnosticar_url_historica(previa, cand)
        salida["previous_url"] = previa
        salida["previous_url_status"] = h.get("estado")
        salida["previous_url_detalle"] = h.get("detalle")

    # --- scrapeabilidad, solo si hay una web aceptada ---
    if mejor is not None and salida.get("discovered_domain"):
        salida.update(diagnosticar_scrapeabilidad(
            {"url": mejor.url, "titulo": mejor.titulo, "texto": mejor.texto,
             "http": mejor.http}))

    # Sin candidatas utiles NO se concluye ausencia: falta buscar, no falta web.
    respondio = any(c.http == 200 for c in candidatas)
    # NOT_FOUND es una conclusion fuerte y aca no esta ganada: solo se
    # agotaron los candidatos YA guardados. Que ninguno fuera la
    # inmobiliaria no demuestra que no tenga web, demuestra que hay que
    # seguir buscando.
    if salida.get("official_web_status") == "OFFICIAL_WEB_NOT_FOUND":
        salida["official_web_status"] = "SEARCH_API_PENDING"
        salida["reason"] = (str(salida.get("reason") or "")
                            + " | candidatos guardados agotados,"
                              " falta busqueda externa")
    if not respondio and not salida.get("discovered_domain"):
        salida["official_web_status"] = "SEARCH_API_PENDING"
        salida["needs_external_search"] = True
    else:
        salida["needs_external_search"] = not salida.get("discovered_domain")

    salida["presupuesto_agotado"] = agotado
    salida["candidatos_abiertos"] = len(candidatas)
    salida["candidatos_que_respondieron"] = sum(1 for c in candidatas if c.http == 200)
    salida["estado_previo"] = fila.get("status")
    salida["city"] = fila.get("city")
    salida["province"] = fila.get("province")
    salida["franchise"] = fila.get("franchise")
    salida["eretz_id"] = fila.get("eretz_id")
    salida["checked_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    salida["runner_version"] = RUNNER_VERSION
    salida["segundos"] = round(time.time() - t0, 1)
    return salida


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default=r"D:\INMO CAPITAL\ERETZ_AGENCY_DATA")
    ap.add_argument("--salida", default="")
    ap.add_argument("--lote", choices=("1", "2", "todos"), default="todos",
                    help="1 = sin url historica; 2 = historicas problematicas")
    ap.add_argument("--limite", type=int, default=0)
    ap.add_argument("--concurrencia", type=int, default=6)
    ap.add_argument("--intervalo", type=float, default=1.0)
    a = ap.parse_args()

    dd = Path(a.data_dir)
    salida = Path(a.salida) if a.salida else dd / "web_identity_resolved.jsonl"

    ents = {x["stable_id"]: x for x in leer_jsonl(dd / "crosswalk_final.jsonl")}
    awd = leer_jsonl(dd / "agency_web_directory.jsonl")

    pend = [f for f in awd
            if f.get("status") in SIN_RESOLVER and f.get("candidate_urls")]
    if a.lote == "1":
        pend = [f for f in pend if not f.get("previous_url")]
    elif a.lote == "2":
        pend = [f for f in pend if f.get("previous_url")]

    hechas = {r.get("canonical_agency_id") for r in leer_jsonl(salida)}
    pend = [f for f in pend if f["canonical_agency_id"] not in hechas]
    pend.sort(key=lambda f: f["canonical_agency_id"])
    if a.limite:
        pend = pend[:a.limite]

    print("### RESOLUCION DE CANDIDATOS YA GUARDADOS ###")
    print(f"  lote:          {a.lote}")
    print(f"  ya resueltas:  {len(hechas)}")
    print(f"  pendientes:    {len(pend)}")
    print(f"  concurrencia:  {a.concurrencia} | cortesia {a.intervalo}s por host")
    print("  sin API de busqueda: solo se abren candidatos ya guardados\n",
          flush=True)
    if not pend:
        return 0

    esc = Escritor(salida)
    lim = LimitadorDeRitmo(a.intervalo)
    cuenta: Counter = Counter()
    t0 = time.time()
    hecho = 0
    lock = threading.Lock()

    def tarea(fila: dict) -> None:
        nonlocal hecho
        cid = fila["canonical_agency_id"]
        ent = ents.get(cid) or {"stable_id": cid,
                                "nombre_original": fila.get("canonical_name")}
        try:
            r = resolver(ent, fila, lim)
        except Exception as e:  # nunca tumbar la corrida por una entidad
            r = {"canonical_agency_id": cid, "official_web_status": "ERROR",
                 "reason": f"{type(e).__name__}: {str(e)[:120]}",
                 "runner_version": RUNNER_VERSION,
                 "checked_at": time.strftime("%Y-%m-%dT%H:%M:%S")}
        esc.escribir(r)
        with lock:
            hecho += 1
            cuenta[r.get("official_web_status")] += 1
            if hecho % 25 == 0 or hecho == len(pend):
                tr = time.time() - t0
                print(f"  {hecho}/{len(pend)} | {tr/60:.1f} min | "
                      f"{hecho/max(tr,1)*3600:,.0f} ent/h", flush=True)

    with ThreadPoolExecutor(max_workers=a.concurrencia) as ex:
        list(ex.map(tarea, pend))

    print("\n  RESULTADO")
    for k, v in cuenta.most_common():
        print(f"    {str(k):34} {v:5}")
    print(f"\n  artefacto -> {salida}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
