#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Las candidatas a retiro, verificadas en vivo: muerta, viva o sin veredicto (P1).

Politica P1 del usuario (29-09): una ficha se retira solo con evidencia inequivoca
de muerte en su propia URL -404, 410, redireccion permanente fuera de la ficha, o
soft-404 DEMOSTRADO-. Una ficha viva no se retira por faltar en dos inventarios, y
una ausencia de catalogo nunca equivale a una propiedad inexistente.

Candidatas: las `retirables` de `snapshot_certificadas` (filas servidas que ya no
estan en el inventario COMPLETO vigente de su agencia). Para cada una se pide su
propia URL, con cortesia por host (un pedido a la vez por sitio, con pausa),
respetando robots.txt (politica P11) y validando cada salto de redireccion.

Veredictos:
  REMOVED           404/410, redireccion 301/308 fuera de la ficha, o soft-404
                    demostrado (texto de «no encontrada», o la pagina es la
                    portada del sitio sin rastro del aviso)
  VIVA              la pagina sigue mostrando el aviso (su id o su titulo)
  AMBIGUA           responde pero no se puede afirmar ni una cosa ni la otra
  NO_VERIFICABLE    error de red, TLS, 403/429, 5xx: no se asume nada
  ROBOTS_BLOCKED    robots.txt no permite pedirla: no se pide

Solo REMOVED se retira. Todo lo demas se sigue sirviendo. Sale un JSONL con la
evidencia de cada una (procedencia del retiro). No escribe en ninguna base.
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
import threading
import time
import urllib.parse
import urllib.robotparser
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

VERSION = "verificar_retiros_v1"
UA = "Mozilla/5.0 (compatible; ERETZ-PropertyBot/1.0; +contacto@eretz)"
PAUSA_POR_HOST = 1.5
# Tokko sirve cientos de dominios desde el mismo backend y limita por backend:
# el 29-09, seis hilos sobre dominios Tokko distintos dieron 1.241 respuestas 429
# (82 sitios con TODO 429). Para la cortesia, todo Tokko es un solo sitio.
RE_FICHA_TOKKO = re.compile(r"/p/\d{5,}-")
PAUSA_TOKKO = 4.0


def grupo_de(url: str) -> str:
    """El «sitio» al que se le debe cortesia: el host, o el backend compartido."""
    partes = urllib.parse.urlparse(url)
    if RE_FICHA_TOKKO.search(partes.path):
        return "backend:tokko"
    return partes.netloc.lower()
LIMITE_BYTES = 1_500_000

REMOVED, VIVA, AMBIGUA = "REMOVED", "VIVA", "AMBIGUA"
NO_VERIFICABLE, ROBOTS_BLOCKED = "NO_VERIFICABLE", "ROBOTS_BLOCKED"

# Frases con que un sitio dice que el aviso ya no esta. Solo en el titulo o en un
# encabezado: en el cuerpo aparecen en menus y pies («Vendidas», «Alquiladas»).
RE_NO_ESTA = re.compile(
    r"(?:p[aá]gina\s+no\s+encontrada|no\s+se\s+encontr[oó]|not\s+found|\b404\b|"
    r"(?:propiedad|aviso|inmueble|publicaci[oó]n)\s+(?:no\s+(?:existe|disponible|encontrad[ao])"
    r"|inexistente|dad[ao]\s+de\s+baja|ya\s+no\s+(?:est[aá]|se\s+encuentra)\s+disponible)|"
    r"ya\s+no\s+est[aá]\s+disponible)", re.I)


def _titulo_html(cuerpo: str) -> str:
    m = re.search(r"<title[^>]*>(.*?)</title>", cuerpo or "", re.S | re.I)
    return re.sub(r"\s+", " ", m.group(1)).strip() if m else ""


def _encabezados(cuerpo: str) -> str:
    return " ".join(re.sub(r"<[^>]+>", " ", h) for h in
                    re.findall(r"<h[1-3][^>]*>(.*?)</h[1-3]>", cuerpo or "", re.S | re.I))


def _plano(texto: str) -> str:
    import unicodedata
    t = unicodedata.normalize("NFKD", texto or "").lower()
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


def ids_del_aviso(url: str, aviso: str | None) -> set[str]:
    """Identificadores que una pagina viva del aviso deberia mencionar."""
    partes = urllib.parse.urlparse(url or "")
    ids = set(re.findall(r"\d{4,}", partes.path + "?" + partes.query))
    if aviso and re.fullmatch(r"\d{3,}", str(aviso)):
        ids.add(str(aviso))
    return ids


def es_raiz_de_catalogo(original: str, final: str) -> bool:
    """El destino es la portada o la raiz del catalogo del MISMO sitio: sin id, a lo sumo un nivel."""
    a, b = urllib.parse.urlparse(original), urllib.parse.urlparse(final)
    if a.netloc.lower().removeprefix("www.") != b.netloc.lower().removeprefix("www."):
        return False
    segmentos = [s for s in b.path.split("/") if s]
    return (len(segmentos) <= 1 and not re.search(r"\d", b.path)
            and not ids_del_aviso(final, None))


def es_la_ficha(original: str, final: str) -> bool:
    """El destino sigue siendo la misma ficha (mismo host y el mismo id o la misma ruta)."""
    a, b = urllib.parse.urlparse(original), urllib.parse.urlparse(final)
    if a.netloc.lower().removeprefix("www.") != b.netloc.lower().removeprefix("www."):
        return False
    if a.path.rstrip("/") == b.path.rstrip("/") and a.query == b.query:
        return True
    ids = ids_del_aviso(original, None)
    return bool(ids) and bool(ids & ids_del_aviso(final, None))


def clasificar(url: str, saltos: list[tuple[int, str]], cuerpo: str,
               titulo_guardado: str | None, aviso: str | None,
               titulo_portada: str | None) -> tuple[str, str]:
    """(veredicto, evidencia). `saltos`: [(status, url)] en orden, el ultimo es el final."""
    if not saltos:
        return NO_VERIFICABLE, "sin respuesta"
    status, final = saltos[-1]
    if status in (404, 410):
        return REMOVED, f"HTTP {status}"
    if status in (401, 403, 429) or status >= 500:
        return NO_VERIFICABLE, f"HTTP {status}"
    if status != 200:
        return NO_VERIFICABLE, f"HTTP {status}"
    redirigio = len(saltos) > 1
    if redirigio and not es_la_ficha(url, final):
        permanentes = [s for s, _ in saltos[:-1] if s in (301, 308)]
        if permanentes:
            return REMOVED, f"redireccion permanente {permanentes[0]} fuera de la ficha -> {final}"
    titulo = _titulo_html(cuerpo)
    if RE_NO_ESTA.search(titulo) or RE_NO_ESTA.search(_encabezados(cuerpo)):
        return REMOVED, f"soft-404: «{titulo[:80]}»"
    plano = _plano(re.sub(r"<script.*?</script>|<style.*?</style>", " ", cuerpo or "", flags=re.S | re.I))
    ids = ids_del_aviso(url, aviso)
    menciona_id = any(re.search(rf"(?<!\d){i}(?!\d)", cuerpo or "") for i in ids)
    guardado = _plano(titulo_guardado or "")
    menciona_titulo = bool(guardado) and len(guardado) >= 12 and guardado[:40] in plano
    if menciona_id or menciona_titulo:
        if redirigio and not es_la_ficha(url, final):
            return AMBIGUA, f"redirige a {final} pero la pagina menciona el aviso"
        return VIVA, "la pagina menciona el aviso (" + ("id" if menciona_id else "titulo") + ")"
    if (redirigio and not es_la_ficha(url, final) and titulo_portada
            and _plano(titulo) == _plano(titulo_portada)):
        return REMOVED, f"soft-404: redirige a la portada ({final}) sin rastro del aviso"
    if redirigio and not es_la_ficha(url, final) and es_raiz_de_catalogo(url, final):
        # La URL de la ficha ya no sirve la ficha: sirve el catalogo del sitio
        # (`candelraul` /propiedad/536440 -> /propiedades), sin rastro del aviso.
        return REMOVED, f"soft-404: redirige al catalogo ({final}) sin rastro del aviso"
    return AMBIGUA, f"responde {'redirigida' if redirigio else '200'} sin mencionar el aviso"


# ---------------------------------------------------------------- en vivo

class Sitio:
    """Robots, portada y cortesia por host. Un pedido a la vez por sitio."""

    def __init__(self):
        self._lock = threading.Lock()
        self._robots: dict[str, urllib.robotparser.RobotFileParser | None] = {}
        self._portada: dict[str, str] = {}
        self._candados: dict[str, threading.Lock] = defaultdict(threading.Lock)
        self._ultimo: dict[str, float] = {}

    def candado(self, host: str) -> threading.Lock:
        with self._lock:
            return self._candados[host]

    def esperar(self, host: str) -> None:
        minimo = PAUSA_TOKKO if host == "backend:tokko" else PAUSA_POR_HOST
        pausa = minimo - (time.time() - self._ultimo.get(host, 0))
        if pausa > 0:
            time.sleep(pausa)
        self._ultimo[host] = time.time()


def pedir(url: str, sesion, maximo_saltos: int = 6) -> tuple[list[tuple[int, str]], str]:
    from scraper.network_security import validate_outbound_url
    saltos: list[tuple[int, str]] = []
    actual = url
    for _ in range(maximo_saltos):
        validate_outbound_url(actual)
        r = sesion.get(actual, allow_redirects=False, timeout=25, stream=True,
                       headers={"User-Agent": UA, "Accept": "text/html,application/xhtml+xml"})
        try:
            if r.is_redirect and r.headers.get("Location"):
                saltos.append((r.status_code, actual))
                actual = urllib.parse.urljoin(actual, r.headers["Location"])
                continue
            crudo = r.raw.read(LIMITE_BYTES, decode_content=True) or b""
            saltos.append((r.status_code, actual))
            return saltos, crudo.decode(r.encoding or "utf-8", "ignore")
        finally:
            r.close()
    return saltos, ""


def robots_permite(sitio: Sitio, url: str, sesion) -> bool | None:
    partes = urllib.parse.urlparse(url)
    base = f"{partes.scheme}://{partes.netloc}"
    if base not in sitio._robots:
        rp = urllib.robotparser.RobotFileParser()
        try:
            r = sesion.get(base + "/robots.txt", timeout=15, headers={"User-Agent": UA})
            if r.status_code in (401, 403):
                rp.disallow_all = True
            elif r.status_code >= 400:
                rp.allow_all = True
            else:
                rp.parse(r.text.splitlines())
        except Exception:
            rp = None  # sin robots legible no se afirma nada: se sigue con cortesia
        sitio._robots[base] = rp
    rp = sitio._robots[base]
    return True if rp is None else rp.can_fetch(UA, url)


def verificar(candidatas: list[dict[str, Any]], hilos: int = 6) -> list[dict[str, Any]]:
    import requests
    sitio = Sitio()
    por_host: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for c in candidatas:
        por_host[grupo_de(c["source_url"])].append(c)
    salida: list[dict[str, Any]] = []
    candado_salida = threading.Lock()

    def un_host(host: str, filas: list[dict[str, Any]]) -> None:
        sesion = requests.Session()
        with sitio.candado(host):
            portadas: dict[str, str] = {}
            for fila in filas:
                url = fila["source_url"]
                try:
                    if not robots_permite(sitio, url, sesion):
                        veredicto, evidencia = ROBOTS_BLOCKED, "robots.txt no lo permite"
                    else:
                        # La portada es la de ESTE host: el grupo de cortesia
                        # (todo Tokko) no es un sitio para compararlas.
                        p = urllib.parse.urlparse(url)
                        if p.netloc not in portadas:
                            sitio.esperar(host)
                            try:
                                _, cuerpo_portada = pedir(f"{p.scheme}://{p.netloc}/", sesion)
                                portadas[p.netloc] = _titulo_html(cuerpo_portada)
                            except Exception:
                                portadas[p.netloc] = ""
                        portada = portadas[p.netloc]
                        sitio.esperar(host)
                        saltos, cuerpo = pedir(url, sesion)
                        veredicto, evidencia = clasificar(url, saltos, cuerpo, fila.get("titulo"),
                                                          fila.get("source_listing_id"), portada)
                except Exception as error:  # noqa: BLE001
                    veredicto, evidencia = NO_VERIFICABLE, f"{type(error).__name__}"
                with candado_salida:
                    salida.append({**fila, "veredicto": veredicto, "evidencia": evidencia,
                                   "verificado_en": time.strftime("%Y-%m-%dT%H:%M:%S"),
                                   "version": VERSION})

    with ThreadPoolExecutor(max_workers=hilos) as pool:
        list(pool.map(lambda kv: un_host(*kv), por_host.items()))
    return salida


def candidatas_de_la_snapshot(db: Path, paquetes: Path, ledger: Path, directorio: Path) -> list[dict[str, Any]]:
    from scripts.plan_de_escritura import agencias_con_web_ajena
    from scripts.snapshot_certificadas import conocidas_de, decidir, paquetes_vigentes
    origen = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
    d = decidir(paquetes_vigentes(paquetes, ledger), conocidas_de(origen),
                agencias_con_web_ajena(directorio))
    fuera = []
    for crudo in origen.execute("select row_json from rows where status='CANDIDATE'"):
        fila = json.loads(crudo[0])
        if fila.get("hash_dedup") in d.retirables:
            fuera.append({k: fila.get(k) for k in ("hash_dedup", "canonical_agency_id", "source_url",
                                                   "source_listing_id", "titulo")})
    return fuera


def main() -> int:
    from scripts.preingestion_manifest import base_canonica
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(base_canonica()))
    ap.add_argument("--paquetes", type=Path,
                    default=Path(r"D:\INMO CAPITAL\ERETZ_AGENCY_CERTIFICATION_20260827\agencies"))
    ap.add_argument("--directorio", type=Path, default=Path("D:/INMO CAPITAL/agency_platform_directory.jsonl"))
    ap.add_argument("--salida", type=Path, required=True, help="JSONL con el veredicto de cada candidata")
    ap.add_argument("--hilos", type=int, default=6)
    ap.add_argument("--reintentar", type=Path, default=None,
                    help="resultado anterior: se vuelven a pedir las NO_VERIFICABLE (429, 5xx, "
                         "timeouts) y las AMBIGUA, y se conserva el resto")
    args = ap.parse_args()
    previas: dict[str, dict] = {}
    if args.reintentar:
        for linea in args.reintentar.read_text(encoding="utf-8").splitlines():
            if linea.strip():
                fila = json.loads(linea)
                previas[fila["hash_dedup"]] = fila
        candidatas = [{k: f.get(k) for k in ("hash_dedup", "canonical_agency_id", "source_url",
                                              "source_listing_id", "titulo")}
                      for f in previas.values() if f["veredicto"] in (NO_VERIFICABLE, AMBIGUA)]
    else:
        candidatas = candidatas_de_la_snapshot(Path(args.db), args.paquetes,
                                               args.paquetes.parent / "AGENCY_CERTIFICATION_RESULTS.jsonl",
                                               args.directorio)
    print(f"candidatas: {len(candidatas)} en {len({c['canonical_agency_id'] for c in candidatas})} agencias",
          flush=True)
    resultado = verificar(candidatas, hilos=args.hilos)
    if previas:
        nuevas = {f["hash_dedup"]: f for f in resultado}
        resultado = [nuevas.get(h, f) for h, f in previas.items()]
    args.salida.parent.mkdir(parents=True, exist_ok=True)
    with args.salida.open("w", encoding="utf-8") as fh:
        for fila in sorted(resultado, key=lambda f: f["hash_dedup"]):
            fh.write(json.dumps(fila, ensure_ascii=False) + "\n")
    print(json.dumps(dict(Counter(f["veredicto"] for f in resultado)), ensure_ascii=False))
    print("database_writes: 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
