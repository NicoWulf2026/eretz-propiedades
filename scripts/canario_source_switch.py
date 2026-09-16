#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Canario de cambio de fuente: verificar antes de mover nada. §7, §8, §86.

Sólo lectura. No escribe en la base, no toca el padrón, no cambia ninguna
fuente. `database_writes: 0`. Aplicar el cambio es un paso aparte, con
respaldo y rastro de auditoría.

Hay 10 agencias cuya fuente de scrapeo es un perfil de portal ajeno teniendo
dominio propio vivo. La tentación es redirigirlas a las 10. El §86 dice que no:
primero 2–3, y sólo si la evidencia es inequívoca.

La verificación anterior comprobó cuatro cosas —el dominio responde, su título
nombra a la agencia, no es un portal, se le ve catálogo—. Son necesarias y **no
alcanzan**. El §8 pide una quinta que ninguna de esas cubre:

    "fichas pertenecen a agencia; no hay contaminación cross-agency"

Un sitio puede responder, llamarse como la agencia y publicar 45 fichas que son
de otro. Es exactamente el daño que se acaba de reparar apagando seis portales:
si cambiamos la fuente a ciegas, volvemos a ingerir inventario ajeno por la
puerta de adelante en vez de por la de atrás.

Así que acá se abren fichas de verdad y se pregunta de quién son:

  1. la ficha responde y vive en el MISMO host que el catálogo;
  2. la ficha nombra a la agencia, o al menos no nombra a otra;
  3. el sitio no es multi-inmobiliaria disfrazado —sin rutas de tipo
     /inmobiliarias/<slug>, sin varias marcas propias en el mismo catálogo—;
  4. ninguna otra agencia del padrón aparece como marca en las fichas.

Una candidata que falla cualquiera de las cuatro **no entra al canario**. No se
descarta para siempre: queda con su motivo escrito.

Uso:
    python scripts/canario_source_switch.py
    python scripts/canario_source_switch.py --fichas 5 --pausa 2
"""
from __future__ import annotations

import argparse
import gzip
import json
import re
import sys
import time
import urllib.request
from pathlib import Path
from urllib.parse import urljoin, urlparse

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "scripts"))

import verificador_identidad_v2 as v2  # noqa: E402

DATOS = Path(r"D:\INMO CAPITAL\ERETZ_AGENCY_DATA")
CERT = Path(r"D:\INMO CAPITAL\ERETZ_AGENCY_CERTIFICATION_20260827")
CANDIDATAS = CERT / "ERETZ_DOMINIO_PROPIO_CANDIDATAS.jsonl"
DIRECTORIO = DATOS / "agency_web_directory.jsonl"
SALIDA = CERT / "ERETZ_SOURCE_SWITCH_CANARIO.jsonl"

# El §9 es explícito y no se decide acá: su dominio propio se titula
# "Inmobiliaria en Mar del Plata" y su fuente actual apunta a un tercero con
# otro nombre. Queda en revisión de identidad hasta que haya evidencia.
IDENTITY_REVIEW = {"la plata propiedades"}

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36",
      "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
      "Accept-Encoding": "gzip", "Accept-Language": "es-AR,es;q=0.9"}

RE_FICHA = re.compile(r'href="([^"]*/(?:propiedad|propiedades|inmueble|inmuebles|'
                      r'ad|ficha|listing|detalle)[^"]*)"', re.I)
# La firma de un sitio multi-inmobiliaria: una sección de inmobiliarias.
RE_MULTI = re.compile(r"(?i)/(?:inmobiliarias|inmobiliaria|agencias|agentes|"
                      r"sucursales|brokers)/[a-z0-9\-]{3,}")

GENERICAS = {"propiedades", "inmobiliaria", "inmobiliarias", "bienes", "raices",
             "negocios", "inmobiliarios", "servicios", "estudio", "real",
             "estate", "grupo", "realty", "inmuebles", "de", "y", "sa", "srl",
             "del", "la", "el", "los", "las", "propiedad", "consultora"}


def aplanar(texto: str) -> str:
    return re.sub(r"[^a-z0-9]", "", v2._normalizar(texto))


def partes_del_nombre(nombre: str) -> list[str]:
    return [p for p in v2._normalizar(nombre).split()
            if len(p) >= 4 and p not in GENERICAS]


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


def texto_plano(html: str) -> str:
    sin_script = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", html)
    return re.sub(r"\s+", " ", re.sub(r"(?s)<[^>]+>", " ", sin_script))


def otras_marcas(directorio: Path, propia: str) -> list[tuple[str, str]]:
    """Nombres de OTRAS agencias del padrón, para buscar contaminación.

    Se queda sólo con los nombres largos y distintivos: "correa" aparecería en
    cualquier texto que hable de un apellido común, y un falso positivo acá
    bloquearía una candidata buena.
    """
    marcas = []
    propia_plana = aplanar(propia)
    for linea in directorio.open(encoding="utf-8", errors="replace"):
        linea = linea.strip()
        if not linea:
            continue
        try:
            fila = json.loads(linea)
        except ValueError:
            continue
        nombre = fila.get("agency_name") or ""
        partes = partes_del_nombre(nombre)
        if len(partes) < 2:
            continue
        clave = "".join(partes)
        if len(clave) < 12 or clave in propia_plana or propia_plana in clave:
            continue
        marcas.append((nombre, clave))
    return marcas


def verificar(nombre: str, propio: str, marcas: list[tuple[str, str]],
              cuantas_fichas: int, pausa: float) -> dict:
    partes = partes_del_nombre(nombre)
    try:
        http, final, html = bajar(propio)
    except Exception as e:
        return {"veredicto": "NO_APTO", "falla": "NO_RESPONDE",
                "porque": f"{type(e).__name__} {getattr(e, 'code', '')}".strip()}

    host = urlparse(final).netloc.lower()
    if v2.es_portal_url(final):
        return {"veredicto": "NO_APTO", "falla": "ES_PORTAL",
                "porque": f"termina en {host}"}

    # Una ruta `/inmobiliarias/<slug>` NO prueba que el sitio sea de varios.
    # `cassiaalfano.com.ar/inmobiliarias/cassia` y
    # `arevaloprop.com/inmobiliarias/001490` publican UNA sola, y es la de
    # ellos: son sitios de marca blanca sobre dominio propio, montados con la
    # misma plantilla que el portal. Rechazarlos por la forma de la URL es el
    # mismo error que ya se cometió con `aimaropropiedades.tuinmobiliaria.com.ar`
    # y apagaría agencias reales. Lo que sí delata a un multi-inmobiliaria es
    # que aparezca MÁS DE UN dueño distinto.
    slugs = sorted({m.rsplit("/", 1)[-1].lower()
                    for m in RE_MULTI.findall(html)})
    propia = aplanar(nombre)
    ajenos = [s for s in slugs
              if not (aplanar(s) and (aplanar(s) in propia or propia in aplanar(s)))
              and not s.isdigit()]
    if len(slugs) > 1 and ajenos:
        return {"veredicto": "NO_APTO", "falla": "SITIO_MULTI_INMOBILIARIA",
                "porque": f"publica {len(slugs)} inmobiliarias y {len(ajenos)} "
                          f"no son ella: {ajenos[:4]}",
                "host": host, "slugs": slugs[:8]}
    marca_blanca = bool(slugs)

    fichas = sorted({urljoin(final, u) for u in RE_FICHA.findall(html)
                     if urlparse(urljoin(final, u)).netloc.lower() == host})
    if len(fichas) < 3:
        return {"veredicto": "NO_APTO", "falla": "SIN_FICHAS_ENUMERABLES",
                "porque": f"solo {len(fichas)} enlaces de ficha en el mismo host",
                "host": host}

    revisadas, propias, ajenas, rotas = [], 0, [], 0
    for enlace in fichas[:cuantas_fichas]:
        time.sleep(pausa)
        try:
            f_http, f_final, f_html = bajar(enlace)
        except Exception as e:
            rotas += 1
            revisadas.append({"url": enlace, "estado": f"ERROR {type(e).__name__}"})
            continue
        if urlparse(f_final).netloc.lower() != host:
            ajenas.append({"url": enlace, "porque": "sale del host",
                           "destino": urlparse(f_final).netloc})
            continue
        plano = aplanar(texto_plano(f_html) + " " + f_final)
        suya = any(p in plano for p in partes)
        intrusas = [n for n, clave in marcas if clave in plano][:3]
        if intrusas:
            ajenas.append({"url": enlace, "porque": "nombra otra inmobiliaria",
                           "marcas": intrusas})
            continue
        propias += bool(suya)
        revisadas.append({"url": enlace, "http": f_http,
                          "nombra_a_la_agencia": suya})

    if ajenas:
        return {"veredicto": "NO_APTO", "falla": "CONTAMINACION_CROSS_AGENCY",
                "porque": f"{len(ajenas)} de {cuantas_fichas} fichas no son suyas",
                "host": host, "fichas_ajenas": ajenas}
    utiles = len(fichas[:cuantas_fichas]) - rotas
    if utiles < 2:
        return {"veredicto": "NO_APTO", "falla": "FICHAS_NO_ABREN",
                "porque": f"{rotas} de {cuantas_fichas} fichas no responden",
                "host": host}
    if propias == 0:
        return {"veredicto": "NO_APTO", "falla": "LAS_FICHAS_NO_LA_NOMBRAN",
                "porque": f"ninguna de las {utiles} fichas leidas nombra a "
                          f"'{nombre}'; no se puede probar que sean suyas",
                "host": host, "fichas_revisadas": revisadas}

    return {"veredicto": "APTO", "host": host,
            "enlaces_de_ficha": len(fichas),
            "fichas_leidas": utiles, "fichas_que_la_nombran": propias,
            "fichas_ajenas": 0, "sitio_de_marca_blanca": marca_blanca,
            "porque": f"{len(fichas)} fichas en su propio host, {propias} de "
                      f"{utiles} leidas la nombran, ninguna nombra a otra",
            "fichas_revisadas": revisadas}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fichas", type=int, default=4,
                    help="cuantas fichas se abren por candidata")
    ap.add_argument("--pausa", type=float, default=1.5)
    args = ap.parse_args()

    candidatas = []
    for linea in CANDIDATAS.open(encoding="utf-8", errors="replace"):
        linea = linea.strip()
        if not linea:
            continue
        fila = json.loads(linea)
        if fila.get("veredicto") == "CANDIDATA":
            candidatas.append(fila)
    # Las mejor evidenciadas primero: el canario es de 2–3, no de 10.
    candidatas.sort(key=lambda f: (f.get("fichas") or 0) + (f.get("precios") or 0),
                    reverse=True)

    print(f"candidatas verificadas previamente: {len(candidatas)}")
    print(f"se abren {args.fichas} fichas de cada una para preguntar de quien "
          f"son\n")

    filas = []
    for fila in candidatas:
        nombre = fila["agency_name"]
        if nombre.strip().lower() in IDENTITY_REVIEW:
            filas.append({**fila, "veredicto": "IDENTITY_REVIEW",
                          "falla": "CONFLICTO_DE_IDENTIDAD",
                          "porque": "§9: su dominio propio y su fuente actual "
                                    "nombran identidades distintas. No se "
                                    "decide sin evidencia"})
            print(f"   {nombre[:30]:32} IDENTITY_REVIEW            "
                  f"§9: no se toca")
            continue
        marcas = otras_marcas(DIRECTORIO, nombre)
        senal = verificar(nombre, fila["dominio_propio"], marcas,
                          args.fichas, args.pausa)
        filas.append({"agency_id": fila["agency_id"], "agency_name": nombre,
                      "dominio_propio": fila["dominio_propio"],
                      "fuente_elegida_hoy": fila["fuente_elegida_hoy"],
                      # §7: queda escrito POR QUE ganaria, no sólo que gana.
                      "source_selection_reason": "OWN_DOMAIN_VERIFIED_OWNERSHIP",
                      "source_selection_confidence":
                          "ALTA" if senal["veredicto"] == "APTO" else "BAJA",
                      **senal})
        marca = "OK " if senal["veredicto"] == "APTO" else "   "
        print(f"{marca}{nombre[:30]:32} {senal['veredicto']:12} "
              f"{senal.get('falla', ''):28} {senal['porque'][:56]}")
        time.sleep(args.pausa)

    SALIDA.write_text("".join(json.dumps(f, ensure_ascii=False) + "\n"
                              for f in filas), encoding="utf-8")

    aptas = [f for f in filas if f["veredicto"] == "APTO"]
    print(f"\n{'=' * 78}")
    print(f"  APTAS para el canario: {len(aptas)} de {len(filas)}")
    for f in aptas[:6]:
        print(f"     {f['agency_name'][:34]:36} {f['host']}")
    print(f"\n  El §86 pide empezar por 2-3. Las {min(3, len(aptas))} primeras "
          f"de esta lista")
    print("  son las de evidencia mas fuerte.")
    print("\n  NO se cambio ninguna fuente. Aplicar es un paso aparte, con")
    print("  respaldo, rastro de auditoria y recertificacion dirigida.")
    print(f"\nartefacto: {SALIDA}")
    print("\ndatabase_writes: 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
