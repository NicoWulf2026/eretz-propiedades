#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Cuando la fuente registrada es UNA propiedad y no el catálogo. §6, §11, §19.

Dry-run por defecto: sin `--aplicar` no escribe nada. No toca producción, no
cambia extractores, no cambia huellas. `database_writes: 0`.

El caso
-------
`fios consultoria inmobiliaria` tiene registrada como fuente:

    https://www.fios.com.ar/emprendimiento-64427-condominio-en-fisherton

Es la página de **un solo emprendimiento**. La raíz del sitio está viva y
enlaza a `propiedades`. No falla nada del pipeline: apunta al lugar equivocado,
y por eso enumeró cero.

`danisa robledo` es el mismo error con peor desenlace: su fuente era una ficha
dentro de un marketplace, y de ahí salieron **6 propiedades ajenas** que sí
entraron.

Por qué conviene mirarlo ahora
------------------------------
Medido el 2026-09-17: hay **16** agencias así, y **14 todavía no se
certificaron**. Corregirlas ahora evita corridas desperdiciadas; corregirlas
después obliga a recertificar. Es el momento más barato que va a haber.

Se parten en dos problemas que no se arreglan igual:

  - **11 oficinas Century 21** apuntando a una propiedad suelta del portal
    nacional de la red, en locale inglés. El §1.7 admite la página de oficina
    dentro de una red como fuente legítima; una **ficha** no es una página de
    oficina. Acá no se propone reemplazo: haría falta descubrir la página de
    oficina de cada una, y adivinarla sería peor que dejarla marcada;
  - **5 sobre su propio dominio**, donde el reemplazo se puede **verificar**:
    se baja la raíz del sitio y se comprueba que publique catálogo antes de
    proponer nada.

Lo que NO se hace
-----------------
Inventar la ruta del catálogo. Si la raíz no muestra catálogo, la agencia queda
marcada y sin propuesta. Una URL propuesta que no existe convierte un error
visible —enumera cero— en uno silencioso.

Uso:
    python scripts/fuente_es_una_ficha.py
    python scripts/fuente_es_una_ficha.py --aplicar
"""
from __future__ import annotations

import argparse
import gzip
import json
import re
import shutil
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "scripts"))

import verificador_identidad_v2 as v2  # noqa: E402

DATOS = Path(r"D:\INMO CAPITAL\ERETZ_AGENCY_DATA")
CERT = Path(r"D:\INMO CAPITAL\ERETZ_AGENCY_CERTIFICATION_20260827")
REGISTRO = DATOS / "scrape_source_technology_map.jsonl"
AUDITORIA = CERT / "ERETZ_FUENTE_FICHA_CORREGIDA.jsonl"
SALIDA = CERT / "ERETZ_FUENTE_ES_UNA_FICHA.json"

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36",
      "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
      "Accept-Encoding": "gzip", "Accept-Language": "es-AR,es;q=0.9"}

# Una ficha tiene un IDENTIFICADOR de propiedad. Exigirlo es lo que evita
# marcar `/propiedades`, que es un catálogo y no una ficha.
FICHA = re.compile(r"""(?ix)
    /(?:propiedad|inmueble|emprendimiento|ficha|listing|property|aviso)
      [-_/](?:\d{3,}|[0-9a-f]{12,})
  | /(?:propiedad|inmueble|ficha)\.(?:php|aspx|html?)\?.*\bid=\d+
  | /propiedades/[0-9a-f]{16,}
""")

# Enlaces que delatan un catálogo en la raíz del sitio.
#
# El `(?:/|^)` en vez de `/` a secas: `fios.com.ar` enlaza su catálogo como
# `href="propiedades"`, **relativo y sin barra inicial**, y la primera versión
# no lo veía. Es la tercera vez que este proyecto tropieza con lo mismo —la
# primera fue `bottai inmobiliaria`, cuyo conteo dio 0 porque sus enlaces son
# `href="inmueble_6067"`—. Exigir la barra es asumir una convención que medio
# internet no sigue.
RE_FICHA_EN_RAIZ = re.compile(
    r'href="((?:[^"]*/)?(?:propiedad|propiedades|inmueble|inmuebles|'
    r'emprendimiento|ficha|listing)[^"]*)"', re.I)

GENERICAS = {"propiedades", "inmobiliaria", "inmobiliarias", "bienes", "raices",
             "negocios", "inmobiliarios", "servicios", "estudio", "real",
             "estate", "grupo", "realty", "inmuebles", "de", "y", "sa", "srl",
             "operaciones", "consultoria", "international"}


def _jsonl(ruta: Path):
    if not ruta.exists():
        return
    for linea in ruta.open(encoding="utf-8", errors="replace"):
        linea = linea.strip()
        if not linea:
            continue
        try:
            yield json.loads(linea)
        except ValueError:
            continue


def es_una_ficha(url: str) -> bool:
    partes = urlparse(url)
    ruta = partes.path + (f"?{partes.query}" if partes.query else "")
    return bool(FICHA.search(ruta))


def bajar(url: str, limite: int = 600_000) -> tuple[int, str, str]:
    respuesta = urllib.request.urlopen(
        urllib.request.Request(url, headers=UA), timeout=25)
    crudo = respuesta.read(limite)
    if respuesta.headers.get("Content-Encoding") == "gzip":
        try:
            crudo = gzip.decompress(crudo)
        except OSError:
            pass
    return respuesta.status, respuesta.url, crudo.decode("utf-8", "replace")


def _partes_del_nombre(nombre: str) -> list[str]:
    return [p for p in v2._normalizar(nombre).split()
            if len(p) >= 4 and p not in GENERICAS]


def verificar_raiz(url_ficha: str, nombre: str) -> dict[str, Any]:
    """¿La raíz del mismo sitio es de ESTA agencia y publica catálogo?

    La pregunta de propiedad va primero, y la primera versión no la hacía. Por
    eso propuso, para `danisa robledo`, la raíz de `mercado-unico.com`: un
    **marketplace entero**. `es_portal_url()` no conoce ese host —hueco ya
    documentado— así que el sitio pasó por dominio propio, y apuntar el scraper
    ahí habría ingerido miles de propiedades ajenas.

    Subir de una ficha a la raíz es seguro **sólo** si la raíz sigue siendo de
    la agencia. Si la ficha vivía en un marketplace, subir empeora las cosas:
    pasa de ingerir una propiedad ajena a ingerirlas todas.
    """
    partes = urlparse(url_ficha)
    raiz = f"{partes.scheme}://{partes.netloc}/"
    try:
        http, final, html = bajar(raiz)
    except Exception as e:
        return {"propuesta": None,
                "porque": f"la raiz no responde: {type(e).__name__}"}
    if v2.es_portal_url(final):
        return {"propuesta": None, "http": http,
                "porque": f"la raiz es un portal ({urlparse(final).netloc})"}

    titulo = ""
    encontrado = re.search(r"(?is)<title[^>]*>(.*?)</title>", html)
    if encontrado:
        titulo = re.sub(r"\s+", " ", encontrado.group(1)).strip()
    aplanado = re.sub(r"[^a-z0-9]", "",
                      v2._normalizar(titulo + " " + urlparse(final).netloc))
    trozos = _partes_del_nombre(nombre)
    if trozos and not any(t in aplanado for t in trozos):
        return {"propuesta": None, "http": http, "titulo": titulo[:80],
                "porque": (f"la raiz no nombra a la agencia: ninguna parte de "
                           f"{trozos} esta en su titulo ni en su dominio. "
                           f"Subir de una ficha a la raiz de un sitio ajeno "
                           f"cambia UNA propiedad ajena por TODAS")}

    host = urlparse(final).netloc.lower()
    enlaces = {urljoin(final, u) for u in RE_FICHA_EN_RAIZ.findall(html)}
    propias = sorted(u for u in enlaces
                     if urlparse(u).netloc.lower() == host
                     and not es_una_ficha(u))
    fichas = sorted(u for u in enlaces if es_una_ficha(u))
    if not propias and len(fichas) < 3:
        return {"propuesta": None, "http": http,
                "porque": "la raiz responde pero no se le ve catalogo: "
                          "proponerla convertiria un error visible en uno mudo"}
    return {"propuesta": raiz, "http": http,
            "rutas_de_catalogo": propias[:5], "fichas_en_la_raiz": len(fichas),
            "porque": (f"la raiz enlaza {len(propias)} ruta(s) de catalogo y "
                       f"{len(fichas)} ficha(s)")}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--aplicar", action="store_true")
    ap.add_argument("--pausa", type=float, default=1.4)
    args = ap.parse_args()

    registro = {r["canonical_agency_id"]: r for r in _jsonl(REGISTRO)
                if r.get("canonical_agency_id")}
    certificadas = {r["canonical_agency_id"]: r
                    for r in _jsonl(CERT / "AGENCY_CERTIFICATION_RESULTS.jsonl")
                    if r.get("canonical_agency_id")}

    afectadas = [(a, r) for a, r in registro.items()
                 if (r.get("official_url") or "").startswith("http")
                 and es_una_ficha(r["official_url"])]

    portales = [(a, r) for a, r in afectadas if v2.es_portal_url(r["official_url"])]
    propias = [(a, r) for a, r in afectadas
               if not v2.es_portal_url(r["official_url"])]

    print(f"fuentes registradas que son UNA ficha: {len(afectadas)}")
    print(f"  dentro de un portal o red:  {len(portales)}")
    print(f"  sobre su propio dominio:    {len(propias)}")
    sin_certificar = sum(1 for a, _ in afectadas if a not in certificadas)
    print(f"  todavia SIN certificar:     {sin_certificar}  "
          f"(corregirlas ahora evita corridas desperdiciadas)\n")

    if portales:
        print("  Las de portal NO se tocan acá. El §1.7 admite la pagina de")
        print("  OFICINA dentro de una red; una ficha no lo es. Proponer un")
        print("  reemplazo exigiria descubrir la oficina de cada una, y")
        print("  adivinarla seria peor que dejarla marcada:")
        for a, r in portales[:4]:
            print(f"     {a.split(':')[-1][:36]:38} {r['official_url'][:58]}")
        if len(portales) > 4:
            print(f"     ... y {len(portales) - 4} mas")
        print()

    propuestas = []
    for agencia, fila in propias:
        nombre = (fila.get("agency_name")
                  or certificadas.get(agencia, {}).get("agency_name")
                  or agencia.split(":")[-1])
        senal = verificar_raiz(fila["official_url"], nombre)
        estado = certificadas.get(agencia, {}).get("status", "(sin certificar)")
        marca = "OK " if senal.get("propuesta") else "   "
        print(f"{marca}{agencia.split(':')[-1][:34]:36} {estado[:20]:22} "
              f"{senal['porque'][:48]}")
        print(f"      de : {fila['official_url'][:88]}")
        if senal.get("propuesta"):
            print(f"      a  : {senal['propuesta']}")
            propuestas.append((agencia, fila, senal))
        time.sleep(args.pausa)

    SALIDA.write_text(json.dumps(
        {"generado_en": time.strftime("%Y-%m-%dT%H:%M:%S"),
         "total": len(afectadas), "en_portal": len(portales),
         "propias": len(propias), "sin_certificar": sin_certificar,
         "propuestas": [{"agency": a, "de": f["official_url"],
                         "a": s["propuesta"], "porque": s["porque"]}
                        for a, f, s in propuestas],
         "database_writes": 0}, ensure_ascii=False, indent=1), encoding="utf-8")

    if not args.aplicar:
        print(f"\n  DRY-RUN: {len(propuestas)} propuestas verificadas, NO "
              f"escritas.")
        print("  Para aplicar: --aplicar")
        print(f"\nartefacto: {SALIDA}")
        print("\ndatabase_writes: 0")
        return 0

    if not propuestas:
        print("\nnada verificado para aplicar")
        return 0

    respaldo = REGISTRO.with_suffix(
        f".jsonl.bak_{time.strftime('%Y%m%d_%H%M%S')}")
    shutil.copy2(REGISTRO, respaldo)
    lineas, escritas = [], 0
    cambios = {a: (f, s) for a, f, s in propuestas}
    for fila in _jsonl(REGISTRO):
        agencia = fila.get("canonical_agency_id")
        if agencia in cambios:
            _, senal = cambios[agencia]
            fila = dict(fila)
            fila["previous_source_url"] = fila.get("official_url")
            fila["previous_source_kind"] = "UNA_FICHA_NO_EL_CATALOGO"
            fila["official_url"] = senal["propuesta"]
            fila["source_selection_reason"] = "RAIZ_DEL_MISMO_SITIO_VERIFICADA"
            fila["source_selection_evidence"] = senal["porque"]
            fila["source_selection_confidence"] = "ALTA"
            fila["checked_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
            escritas += 1
        lineas.append(json.dumps(fila, ensure_ascii=False))
    temporal = REGISTRO.with_suffix(".jsonl.tmp")
    temporal.write_text("\n".join(lineas) + "\n", encoding="utf-8")
    temporal.replace(REGISTRO)

    with AUDITORIA.open("a", encoding="utf-8") as fh:
        for agencia, fila, senal in propuestas:
            fh.write(json.dumps({
                "cuando": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "canonical_agency_id": agencia,
                "de": fila["official_url"], "a": senal["propuesta"],
                "porque": senal["porque"], "respaldo": respaldo.name,
                "database_writes": 0}, ensure_ascii=False) + "\n")

    print(f"\naplicadas: {escritas}   respaldo: {respaldo.name}")
    print(f"auditoria: {AUDITORIA.name}")
    print("\ndatabase_writes: 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
