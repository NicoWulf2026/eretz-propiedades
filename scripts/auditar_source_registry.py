#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Clasificar la FUENTE de cada agencia antes de scrapearla. §4, §5, §78.

No escribe en la base ni en el padrón. `database_writes: 0`. Sólo clasifica y
deja el artefacto; corregir es un paso aparte y con autorización.

Por qué existe: en 48 h, SIETE agencias pararon la cola por lo mismo —su "web"
declarada no era su sitio— y cada una costó horas. Diagnosticarlas de a una es
tratar el síntoma. Esto las busca todas de una vez.

La clasificación NO se decide por host compartido. Ese atajo confunde dos cosas
distintas, y el §5 lo prohíbe explícitamente:

    century21.com.ar/oficina/nombre     es su casa dentro de su franquicia
    buscainmueble.com/inmobiliarias/x   es un perfil en un marketplace ajeno

Las dos comparten host con muchas otras agencias. Sólo una es un portal.

Lo que se mira, en este orden y parando en la primera certeza:

  1. la RUTA. `/inmobiliarias/<slug>` en un host que no es la agencia es un
     perfil de terceros, sin importar cuál sea el host. Así se detectaron
     `buscainmueble` y `proppies`, que ninguna lista conocía;
  2. una ruta de FICHA en un host ajeno —`/propiedades/<hash>`— es todavía
     peor: la web declarada es un aviso suelto. Es el caso `danisa robledo`;
  3. el host, contra las listas conocidas de portales, redes y sociales;
  4. cuántas agencias comparten el host. Muchas agencias en un host es un
     INDICIO que manda a revisión, no un veredicto.

`inventory_allowed` es el campo que importa: dice si de esa fuente se puede
sacar inventario. Un perfil de portal puede seguir siendo evidencia válida de
que la inmobiliaria existe —y por eso no se borra— sin ser fuente de avisos.

Uso:
    python scripts/auditar_source_registry.py
    python scripts/auditar_source_registry.py --solo-cambios
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import urlparse

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "scripts"))

import verificador_identidad_v2 as v2  # noqa: E402

CERT = Path(r"D:\INMO CAPITAL\ERETZ_AGENCY_CERTIFICATION_20260827")
DATOS = Path(r"D:\INMO CAPITAL\ERETZ_AGENCY_DATA")
SALIDA = CERT / "ERETZ_SOURCE_REGISTRY.jsonl"

# Los estados del §4.
OFFICIAL_WEB = "OFFICIAL_WEB"
OFFICIAL_OFFICE_PAGE = "OFFICIAL_OFFICE_PAGE"
EXTERNAL_PORTAL_PROFILE = "EXTERNAL_PORTAL_PROFILE"
EXTERNAL_PORTAL_LISTING = "EXTERNAL_PORTAL_LISTING"
SOCIAL_ONLY = "SOCIAL_ONLY"
NO_OFFICIAL_WEB = "NO_OFFICIAL_WEB"
IDENTITY_REVIEW = "IDENTITY_REVIEW"
UNKNOWN = "UNKNOWN"

# Una seccion de un sitio dedicada a listar OTRAS inmobiliarias. Si la url de
# una agencia cae aca y el host no es suyo, es un perfil ajeno.
RUTA_DE_PERFIL = re.compile(
    r"(?i)/(inmobiliarias?|agencias?|agency|agencies|agente|agent|agents|"
    r"brokers?|corredores?|empresas?|directorio|profile|perfil|e)/[^/]+")

# Una ficha suelta: la web declarada es UN AVISO, no un sitio. `danisa
# robledo` declaraba /propiedades/69019270b5bada00113d470b.
RUTA_DE_FICHA = re.compile(
    r"(?i)/(propiedades?|inmuebles?|listing|listings|ficha|aviso|p|prop)/"
    r"[a-z0-9_-]*[0-9a-f]{6,}")

# La pagina de una oficina DENTRO de su propia red. No es un portal ajeno.
RED = re.compile(r"(?i)^(www\.)?(century21|c21|remax|remax-|kellerwilliams|kw|"
                 r"coldwellbanker|engelvoelkers|sothebysrealty|interwin)")

MUCHAS_AGENCIAS = 4      # a partir de aca, el host comparte y se revisa


def registrable(host: str) -> str:
    h = (host or "").lower().removeprefix("www.")
    p = h.split(".")
    if len(p) >= 3 and p[-2] in ("com", "net", "org", "gob", "edu"):
        return ".".join(p[-3:])
    return ".".join(p[-2:])


def nucleo_del_nombre(nombre: str) -> str:
    genericas = {"propiedades", "inmobiliaria", "inmobiliarias", "bienes",
                 "raices", "negocios", "inmobiliarios", "servicios", "estudio",
                 "real", "estate", "grupo", "realty", "inmuebles", "de", "y"}
    return "".join(p for p in v2._normalizar(nombre).split()
                   if p not in genericas)


def clasificar(agencia: str, nombre: str, url: str,
               agencias_por_host: dict[str, set]) -> dict:
    """Devuelve el tipo de fuente y la evidencia que lo sostiene."""
    try:
        partes = urlparse(url or '')
        partes.port  # Reject malformed ports as well as malformed host syntax.
    except (ValueError, TypeError):
        return {"source_type": NO_OFFICIAL_WEB, "confidence": "ALTA",
                "evidence": "URL inválida", "inventory_allowed": False}
    if (partes.scheme not in ('http', 'https') or not partes.hostname
            or partes.username is not None or partes.password is not None):
        return {"source_type": NO_OFFICIAL_WEB, "confidence": "ALTA",
                "evidence": "no hay url declarada", "inventory_allowed": False}

    host = (partes.hostname or "").lower().removeprefix("www.")
    reg = registrable(host)
    ruta = partes.path or "/"
    n = nucleo_del_nombre(nombre)
    # Contra el HOST ENTERO, subdominio incluido, y no solo contra el dominio
    # registrable. `aimaropropiedades.tuinmobiliaria.com.ar` ES el sitio de
    # AIMARO -su titulo dice "AIMARO PROPIEDADES" y no nombra a nadie mas-;
    # `tuinmobiliaria.com.ar` es un proveedor white-label, no un marketplace.
    # Comparando solo el registrable, las cuatro agencias de ese proveedor
    # quedaban marcadas como perfiles de portal. Es justo el error que el §5
    # advierte: compartir host no prueba que sea un portal.
    aplastado_host = re.sub(r"[^a-z0-9]", "", host)
    host_es_suyo = bool(n) and n in aplastado_host
    vecinas = len(agencias_por_host.get(reg, ()))

    if reg in v2.SOCIALES:
        return {"source_type": SOCIAL_ONLY, "confidence": "ALTA",
                "evidence": f"{reg} es una red social",
                "inventory_allowed": False}

    # 1. una FICHA en un host que no es suyo: la web declarada es un aviso.
    if not host_es_suyo and RUTA_DE_FICHA.search(ruta):
        return {"source_type": EXTERNAL_PORTAL_LISTING, "confidence": "ALTA",
                "evidence": f"la url declarada es UNA FICHA en {reg}, "
                            f"que no es su dominio: {ruta[:60]}",
                "inventory_allowed": False}

    # 2. un PERFIL en un host que no es suyo.
    if not host_es_suyo and RUTA_DE_PERFIL.search(ruta):
        if RED.match(host):
            return {"source_type": OFFICIAL_OFFICE_PAGE, "confidence": "ALTA",
                    "evidence": f"{reg} es su red y {ruta[:50]} es la pagina "
                                f"de su oficina, no un portal ajeno",
                    "inventory_allowed": False}
        return {"source_type": EXTERNAL_PORTAL_PROFILE, "confidence": "ALTA",
                "evidence": f"la ruta {ruta[:60]} es una seccion de terceros "
                            f"en {reg}, que no es su dominio",
                "inventory_allowed": False}

    # 3. el host, contra lo conocido.
    if v2.es_portal_url(url) and not RED.match(host):
        return {"source_type": EXTERNAL_PORTAL_PROFILE, "confidence": "ALTA",
                "evidence": f"{reg} figura como portal o directorio conocido",
                "inventory_allowed": False}
    if RED.match(host) and not host_es_suyo:
        return {"source_type": OFFICIAL_OFFICE_PAGE, "confidence": "MEDIA",
                "evidence": f"{reg} es una red; su pagina de oficina no es "
                            f"fuente de inventario propio",
                "inventory_allowed": False}

    # 4. host compartido: INDICIO, no veredicto.
    if vecinas >= MUCHAS_AGENCIAS and not host_es_suyo:
        return {"source_type": IDENTITY_REVIEW, "confidence": "BAJA",
                "evidence": f"{vecinas} agencias comparten {reg} y el nombre "
                            f"no esta en el dominio. Compartir host NO prueba "
                            f"que sea un portal: hay que mirarlo",
                "inventory_allowed": False}

    if host_es_suyo:
        return {"source_type": OFFICIAL_WEB, "confidence": "ALTA",
                "evidence": f"'{n}' esta en su propio dominio {reg}",
                "inventory_allowed": True}
    return {"source_type": UNKNOWN, "confidence": "BAJA",
            "evidence": f"{reg} no coincide con el nombre y no cayo en "
                        f"ninguna regla: queda para mirar",
            "inventory_allowed": False}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--solo-cambios", action="store_true")
    ap.parse_args()

    ult = {}
    for line in (CERT / "AGENCY_CERTIFICATION_RESULTS.jsonl").read_text(
            encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if r.get("canonical_agency_id"):
            ult[r["canonical_agency_id"]] = r

    por_host: dict[str, set] = defaultdict(set)
    for a, r in ult.items():
        u = r.get("official_url") or ""
        if u.startswith("http"):
            por_host[registrable(urlparse(u).hostname or '')].add(a)

    filas = []
    for a, r in sorted(ult.items()):
        url = r.get("official_url") or ""
        nombre = r.get("agency_name") or a.split(":")[-1]
        c = clasificar(a, nombre, url, por_host)
        filas.append({
            "agency_id": a, "agency_name": nombre,
            "declared_url": url,
            "canonical_host": registrable(urlparse(url).hostname or '') if url else None,
            "status_certificacion": r.get("status"),
            "enumeradas": (r.get("enumeration_audit") or {}).get("enumerated"),
            **c,
        })

    SALIDA.write_text("".join(json.dumps(f, ensure_ascii=False) + "\n"
                              for f in filas), encoding="utf-8")

    print(f"agencias clasificadas: {len(filas)}\n")
    print(f"{'source_type':28} {'n':>5}  {'inventario':>10}")
    for k, n in Counter(f["source_type"] for f in filas).most_common():
        permitido = sum(1 for f in filas
                        if f["source_type"] == k and f["inventory_allowed"])
        print(f"{k:28} {n:5}  {permitido:10}")

    # Las que importan: fuente no propia y todavia scrapeable o ya scrapeada.
    malas = [f for f in filas
             if f["source_type"] in (EXTERNAL_PORTAL_PROFILE,
                                     EXTERNAL_PORTAL_LISTING)
             and f["status_certificacion"] != "BLOCKED_EXTERNAL"]
    print(f"\n{'='*74}")
    print(f"PERFILES/FICHAS DE PORTAL QUE NO ESTAN CERRADAS: {len(malas)}")
    print(f"{'='*74}")
    print(f"{'agencia':30} {'estado':20} {'enum':>5}  url")
    for f in sorted(malas, key=lambda x: -(x["enumeradas"] or 0)):
        print(f"{f['agency_name'][:28]:30} {str(f['status_certificacion'])[:18]:20} "
              f"{str(f['enumeradas'] or 0):>5}  {f['declared_url'][:52]}")
    ajeno = sum(f["enumeradas"] or 0 for f in malas)
    print(f"\n  propiedades AJENAS que enumeramos desde esas fuentes: {ajeno:,}")

    revisar = [f for f in filas if f["source_type"] == IDENTITY_REVIEW]
    if revisar:
        print(f"\n  a revisar por host compartido (indicio, no veredicto): "
              f"{len(revisar)}")
        for f in revisar[:10]:
            print(f"     {f['agency_name'][:26]:28} {f['canonical_host']}")

    print(f"\nartefacto: {SALIDA}")
    print("\n  Esto NO corrige nada. Corregir el registro es el paso siguiente")
    print("  y va con backup, before/after y audit trail.")
    print("\ndatabase_writes: 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
