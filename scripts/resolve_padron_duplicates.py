#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Cuando dos entidades del padron se disputan el mismo sitio.

El clasificador cross-agency marca SAME_AGENCY_DUPLICATED_IN_ERETZ y retiene las
propiedades. Hace bien en retener: saber que dos fichas comparten dominio y
apellido no dice cual de las dos es la duena, y adjudicar por tamano de
inventario le da el aviso a la mas grande sin mirar de quien es.

Pero retener no es resolver. Este script busca la evidencia que decide, y es la
misma que resolvio el caso Bustamante: el sitio se presenta solo. Una
inmobiliaria nombra las zonas donde trabaja -en el titulo, en el encabezado, en
la pagina de contacto- y esas zonas pertenecen a una de las dos fichas, no a las
dos.

Tres desenlaces posibles, y ninguno se fuerza:

  DUENO_DEMOSTRADO   el sitio nombra las zonas de una sola ficha. La otra no es
                     duena de ESE sitio: se le quita la atribucion y vuelve a la
                     cola de busqueda. No se concluye que no tenga web propia,
                     porque eso no se probo.

  MISMA_EMPRESA      comparten agent_id de Roomix, o el sitio nombra las zonas
                     de las dos. Ahi si hay que unificar el padron, y esa
                     decision no es de la ingesta.

  AMBIGUO            el sitio no nombra las zonas de ninguna, o no respondio.
                     Las propiedades siguen retenidas. Es el desenlace correcto
                     cuando no hay evidencia: inventar un dueno contamina todo
                     lo que venga despues.

Solo lee artefactos y el sitio en disputa. Con --aplicar corrige la atribucion
equivocada en el directorio de plataformas. No toca la base ni borra entidades.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from connectors.base import Descargador, LimitadorDeRitmo  # noqa: E402
from scripts.investigate_bustamante import GENERICAS, zonas  # noqa: E402
from scripts.resolve_web_candidates import abrir  # noqa: E402

VERSION = "padron_duplicate_resolution_v1"

DEMOSTRADO = "DUENO_DEMOSTRADO"
MISMA = "MISMA_EMPRESA"
AMBIGUO = "AMBIGUO"

# Paginas donde una inmobiliaria dice donde trabaja. No se piden todas si la
# primera ya alcanza.
CAMINOS = ("", "/contacto", "/nosotros", "/quienes-somos", "/institucional")

PRESUPUESTO_POR_CASO = 120

# Palabras que aparecen en cualquier sitio inmobiliario y no ubican nada.
RUIDO = {"centro", "comercial", "terrenos", "capital", "barrio", "zona",
         "norte", "sur", "este", "oeste", "casa", "casas", "depto", "lote",
         "campo", "local", "ciudad", "provincia", "argentina", "venta",
         "alquiler", "propiedad", "propiedades", "inmobiliaria"}


def norm(t: str) -> str:
    t = unicodedata.normalize("NFKD", (t or "").lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9 ]+", " ", t)


def senas_de(entidad: dict) -> set:
    """Las palabras con las que esta ficha se ubica en el mapa.

    Se trabaja con palabras y no con la zona entera porque las zonas del padron
    vienen sucias -"martin cordoba capital", "comercial empalme"- y el sitio
    escribe "San Martin" o "Empalme" a secas. Comparar cadenas completas no
    encuentra nada que si esta.
    """
    salida = set()
    for z in zonas(entidad) - GENERICAS:
        for palabra in norm(z).split():
            if len(palabra) >= 4 and palabra not in RUIDO:
                salida.add(palabra)
    return salida


RE_TEL = re.compile(r"\(?(\d{2,4})\)?[\s.-]?\d{3,4}[\s.-]?\d{4}")
RE_MAIL = re.compile(r"[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}", re.I)


def extraer_contacto(texto: str) -> str:
    """Telefono, mail y lo que los rodea.

    Es la evidencia mas dura que da un sitio chico: la caracteristica telefonica
    ubica la ciudad sin ambiguedad -351 es Cordoba, 223 es Mar del Plata- y la
    direccion suele decir el partido con todas las letras.
    """
    partes = []
    m = RE_MAIL.search(texto or "")
    if m:
        partes.append(texto[max(0, m.start() - 90):m.start() + 90])
    else:
        m = RE_TEL.search(texto or "")
        if m:
            partes.append(texto[max(0, m.start() - 90):m.start() + 60])
    return re.sub(r"\s+", " ", " | ".join(partes)).strip()[:260]


def leer(ruta: Path) -> list:
    if not ruta.exists():
        return []
    out = []
    for l in ruta.open(encoding="utf-8"):
        l = l.strip()
        if l:
            try:
                out.append(json.loads(l))
            except ValueError:
                pass
    return out


RE_404 = re.compile(r"^\s*(404|error\s*404|not found|pagina no encontrada)",
                    re.I)


def es_404_blando(titulo: str) -> bool:
    """Muchos sitios devuelven 200 con una pagina de error adentro.

    Leer ese cuerpo como si fuera contenido de la inmobiliaria mete texto ajeno
    en la evidencia: en el caso Salerno, /contacto devolvia 200 y un titulo
    "404". No cambio el veredicto, pero podria haberlo cambiado.
    """
    return bool(RE_404.match(titulo or ""))


def mirar_el_sitio(d: Descargador, host: str) -> tuple:
    """Lo que el sitio dice de si mismo.

    Devuelve (texto_normalizado, paginas_leidas, titulo, contacto)."""
    texto, leidas, titulo, contacto = "", [], "", ""
    arranque = time.time()
    for camino in CAMINOS:
        if time.time() - arranque > PRESUPUESTO_POR_CASO:
            break
        url = "https://" + host + camino
        c = abrir(d, url, "duplicado")
        if (c.http == 200 and c.texto and not c.texto.startswith("[")
                and not es_404_blando(c.titulo)):
            texto += " " + (c.titulo or "") + " " + c.texto
            leidas.append(camino or "/")
            if not titulo:
                titulo = c.titulo or ""
            if not contacto:
                contacto = extraer_contacto(c.texto)
            # Con la portada y una pagina institucional alcanza; no se insiste
            # sobre un sitio chico mas de lo necesario.
            if len(leidas) >= 2:
                break
    return norm(texto), leidas, titulo, contacto


def decidir(a: dict, b: dict, texto: str) -> tuple:
    """Quien es el dueno, segun lo que el sitio nombra."""
    ev = []
    ids_a = set(a.get("raw_agent_ids") or [])
    ids_b = set(b.get("raw_agent_ids") or [])
    if ids_a & ids_b:
        ev.append("comparten agent_id de Roomix: %s" % sorted(ids_a & ids_b))
        return MISMA, None, ev

    sa, sb = senas_de(a), senas_de(b)
    propias_a, propias_b = sa - sb, sb - sa
    if not propias_a or not propias_b:
        ev.append("las zonas de las dos fichas no se distinguen entre si")
        return AMBIGUO, None, ev

    if not texto:
        ev.append("el sitio no respondio: no hay evidencia para adjudicar")
        return AMBIGUO, None, ev

    hit_a = sorted(p for p in propias_a if re.search(r"\b%s\b" % re.escape(p), texto))
    hit_b = sorted(p for p in propias_b if re.search(r"\b%s\b" % re.escape(p), texto))
    ev.append("zonas de %s nombradas en el sitio: %s"
              % (a.get("nombre_original"), hit_a or "ninguna"))
    ev.append("zonas de %s nombradas en el sitio: %s"
              % (b.get("nombre_original"), hit_b or "ninguna"))

    if hit_a and not hit_b:
        return DEMOSTRADO, a, ev
    if hit_b and not hit_a:
        return DEMOSTRADO, b, ev
    if hit_a and hit_b:
        ev.append("el sitio nombra las zonas de las dos: o son la misma empresa "
                  "con dos sucursales, o el padron las tiene mal separadas")
        return MISMA, None, ev
    ev.append("el sitio no nombra las zonas de ninguna de las dos")
    return AMBIGUO, None, ev


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default=r"D:\INMO CAPITAL\ERETZ_AGENCY_DATA")
    ap.add_argument("--manifiesto",
                    default=r"D:\INMO CAPITAL\AGENCY_DUPLICATE_RESOLUTION_MANIFEST.jsonl")
    ap.add_argument("--plataformas",
                    default=r"D:\INMO CAPITAL\agency_platform_directory.jsonl")
    ap.add_argument("--salida",
                    default=r"D:\INMO CAPITAL\PADRON_DUPLICATE_RESOLUTION.json")
    ap.add_argument("--aplicar", action="store_true")
    a = ap.parse_args()

    dd = Path(a.data_dir)
    cw = {x["stable_id"]: x for x in leer(dd / "crosswalk_final.jsonl")}
    awd = {x["canonical_agency_id"]: x for x in leer(dd / "agency_web_directory.jsonl")}
    casos = leer(Path(a.manifiesto))
    if not casos:
        print("no hay duplicados pendientes en el manifiesto")
        return 0

    d = Descargador(LimitadorDeRitmo(intervalo=2.0), timeout=20, reintentos=2)
    informes, correcciones = [], []

    print("### DUPLICADOS DEL PADRON ###")
    for caso in casos:
        ids = caso.get("ids_implicados") or []
        host = caso.get("dominio")
        if len(ids) != 2 or not host:
            continue
        a_ent, b_ent = cw.get(ids[0]), cw.get(ids[1])
        if not a_ent or not b_ent:
            print("  %s: falta alguna entidad en el padron" % host)
            continue

        texto, leidas, titulo_sitio, contacto = mirar_el_sitio(d, host)
        veredicto, dueno, ev = decidir(a_ent, b_ent, texto)
        perdedor = None
        if veredicto == DEMOSTRADO:
            perdedor = b_ent if dueno is a_ent else a_ent

        print()
        print("  %s   urls en conflicto: %s" % (host, caso.get("urls_en_conflicto")))
        for e in (a_ent, b_ent):
            w = awd.get(e["stable_id"]) or {}
            print("    eretz=%-6s %-34s zonas=%s"
                  % (w.get("eretz_id"), str(e.get("nombre_original"))[:34],
                     sorted(zonas(e))[:4]))
        print("    paginas leidas: %s" % (leidas or "ninguna"))
        print("    el sitio se titula: %s" % (titulo_sitio or "(sin titulo)")[:70])
        if contacto:
            print("    contacto en el sitio: %s" % contacto[:100])
        print("    --> %s%s" % (veredicto,
                                "" if not dueno else
                                "  dueno: %s" % dueno.get("nombre_original")))
        for x in ev:
            print("        - %s" % x[:110])

        informes.append({
            "host": host,
            "urls_en_conflicto": caso.get("urls_en_conflicto"),
            "veredicto": veredicto,
            "paginas_leidas": leidas,
            "titulo_del_sitio": titulo_sitio,
            "contacto_en_el_sitio": contacto,
            "evidencia": ev,
            "dueno": None if not dueno else {
                "canonical_agency_id": dueno["stable_id"],
                "eretz_id": (awd.get(dueno["stable_id"]) or {}).get("eretz_id"),
                "nombre": dueno.get("nombre_original")},
            "sin_derecho_sobre_el_sitio": None if not perdedor else {
                "canonical_agency_id": perdedor["stable_id"],
                "eretz_id": (awd.get(perdedor["stable_id"]) or {}).get("eretz_id"),
                "nombre": perdedor.get("nombre_original")},
            "entidades": [
                {"canonical_agency_id": e["stable_id"],
                 "nombre": e.get("nombre_original"),
                 "eretz_id": (awd.get(e["stable_id"]) or {}).get("eretz_id"),
                 "zonas": sorted(zonas(e)),
                 "avisos": e.get("avisos_observados")}
                for e in (a_ent, b_ent)],
            "checked_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "resolution_version": VERSION,
        })
        if perdedor:
            correcciones.append((perdedor["stable_id"], host,
                                 (awd.get(dueno["stable_id"]) or {}).get("eretz_id"),
                                 dueno.get("nombre_original")))

    Path(a.salida).write_text(
        json.dumps({"casos": informes, "resolution_version": VERSION,
                    "checked_at": time.strftime("%Y-%m-%dT%H:%M:%S")},
                   ensure_ascii=False, indent=2), encoding="utf-8")

    if correcciones and a.aplicar:
        filas = leer(Path(a.plataformas))
        n = 0
        for r in filas:
            for cid, host, eid_dueno, nombre_dueno in correcciones:
                if (r.get("canonical_agency_id") == cid
                        and host in (r.get("host") or r.get("domain") or "")):
                    r["domain_mal_atribuido"] = r.get("domain")
                    r["domain"] = None
                    r["host"] = None
                    # Que ese sitio no sea suyo no prueba que no tenga uno
                    # propio: nunca se busco. Vuelve a la cola, no a una
                    # conclusion.
                    r["web_kind"] = "SEARCH_API_PENDING"
                    r["web_kind_reason"] = (
                        "el sitio nombra las zonas de %s (eretz_id %s); esta "
                        "inmobiliaria opera en otro mercado"
                        % (nombre_dueno, eid_dueno))
                    r["needs_external_search"] = True
                    n += 1
        tmp = Path(a.plataformas).with_suffix(".jsonl.tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            for r in filas:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
        tmp.replace(Path(a.plataformas))
        print()
        print("  corregidas %d filas del directorio de plataformas" % n)
    elif correcciones:
        print()
        print("  (informe solamente; usar --aplicar para corregir la atribucion)")

    print()
    print("  artefacto -> %s" % a.salida)
    print("  pedidos: %d" % d.pedidos)
    return 0


if __name__ == "__main__":
    sys.exit(main())
