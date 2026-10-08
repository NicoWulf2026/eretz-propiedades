#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Verificar la web del directorio de plataformas de las agencias fuera de `main` (P6, fase 2).

Politica P6 del usuario (29-09): certificar por identidad canonica cuando la
identidad quede demostrada. 1.028 agencias fuera de `main` tienen una web oficial
en el directorio de plataformas que nadie ABRIO para establecer que es de esa
agencia: `free_web_audit_v1` puntuo URLs sin visitarlas (597 de 598 salian de
confianza alta), asi que ese estado no prueba nada.

Para cada una, con la misma evidencia que el resto del circuito:
  1. se abre la web y se decide con `agency_web_discovery.verificar` (identidad);
  2. se comprueba que sea argentina (`promover_webs_verificadas.es_argentina`);
  3. se CUENTA cuantas agencias del universo reclaman el mismo host: un dominio
     compartido no identifica a nadie.
Solo lo que pasa las tres cosas se agrega a `AGENCY_OFFICIAL_WEB_VERIFIED.jsonl`
como AFIRMABLE, con el estado real del resolver y el conteo real del host. Todo
lo demas queda en el registro de esta corrida con su razon.

Reanudable. Sin consultas pagas. No escribe en ninguna base.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.parse
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import agency_web_discovery as wd  # noqa: E402
from promover_webs_verificadas import es_argentina  # noqa: E402
from verificar_candidatas_web import bajar  # noqa: E402
try:  # raiz del estado operativo configurable (ERETZ_DATA_ROOT)
    from scripts.rutas_de_datos import dato  # noqa: E402
except ImportError:  # corrido como `python scripts/x.py`
    from rutas_de_datos import dato  # noqa: E402

DATOS = Path(str(dato('ERETZ_AGENCY_DATA')))
V2 = Path(str(dato('ERETZ_SUPABASE_RECONCILIATION_V2_20260827')))
PLATAFORMAS = Path(str(dato('agency_platform_directory.jsonl')))
DESTINO = DATOS / "AGENCY_OFFICIAL_WEB_VERIFIED.jsonl"
REGISTRO = DATOS / "AGENCY_DIRECTORY_WEB_VERIFICATION.jsonl"
ESTABLECIDAS = (wd.VERIFIED, wd.HIGH_CONFIDENCE)
# Tokko sirve cientos de dominios desde un backend con limite compartido: entre
# agencias Tokko se espera mas, para no sumar un tercer pedido concurrente al del
# worker de certificacion (ver `run_agency_certification_queue.worker_de`).
PAUSA_TOKKO = 4.0


# --- El host tiene que ser DE la agencia (mision 08-10) -------------------------------------------
# La re-verificacion de 294 registros viejos dio AFIRMABLE a paginas de terceros que solo NOMBRAN a la
# agencia: respaldar.com.ar (garantias de alquiler) para `a zaccardi`, cucicba.org.ar/matriculados,
# asia.villas (Tailandia), xing.com, vlex, kasafinder.io, diarios locales. `wd.verificar` confirma que
# la pagina habla de la agencia, no que el sitio sea suyo. Se revirtio la escritura y se exige esto.
GENERICAS = frozenset({
    "propiedades", "propiedad", "inmobiliaria", "inmobiliarias", "negocios", "inmobiliarios", "bienes",
    "raices", "real", "estate", "servicios", "estudio", "grupo", "broker", "brokers", "consultora",
    "administracion", "asesores", "asociados", "group", "realty", "inversiones", "desarrollos",
    "emprendimientos", "operaciones", "soluciones", "gestion", "home", "homes", "casas", "agencia",
    "oficina", "sucursal", "argentina", "buenos", "aires", "rosario", "cordoba", "norte", "centro",
    # siglas de colegios y adhesiones que aparecen DENTRO del nombre cargado
    "cucicba", "cmcpsi", "cmcpdsn", "colegio", "matricula", "adherido", "sistema", "registro"})
HOSTS_AJENOS = ("cucicba", "cmcpsi", "colegio", "century21", "remax", "coldwellbanker", "kellerwilliams",
                "engelvoelkers", "sothebysrealty", "kasafinder", "xing.com", "vlex.com", "archivo.biz",
                "evisos", "facebook", "instagram", "linkedin")
# Nombres de pila frecuentes: solos no distinguen a una agencia de otra persona con el mismo nombre.
NOMBRES_DE_PILA = frozenset({
    "maria", "jose", "juan", "carlos", "jorge", "luis", "miguel", "pablo", "javier", "diego", "daniel",
    "alejandro", "alejandra", "andrea", "natalia", "mariana", "mariano", "martin", "martina", "gustavo",
    "fernando", "fernanda", "ricardo", "roberto", "claudia", "claudio", "silvia", "patricia", "laura",
    "marcelo", "sergio", "eduardo", "gabriel", "gabriela", "sebastian", "nicolas", "pedro", "lucia",
    "valeria", "veronica", "monica", "susana", "graciela", "liliana", "adriana", "cecilia", "carolina",
    "florencia", "paula", "paola", "marisa", "marina", "silvina", "karina", "viviana", "hector", "oscar",
    "raul", "ruben", "hugo", "mario", "jorgelina", "ezequiel", "facundo", "agustin", "esteban", "matias",
    "santiago", "federico", "ignacio", "lorena", "romina", "vanesa", "cristina", "beatriz", "norma",
    "gaby", "vicky", "nora", "miriam", "maribel", "sonia", "rosa", "lautaro", "mauricio", "renato",
    "rodrigo", "lucas", "bruno", "abelardo", "graciela", "mateo", "atilio", "denis"})
RUTA_DE_CATALOGO = ("propiedad", "inmueble", "venta", "alquiler", "buscar", "busqueda", "listado",
                    "catalogo", "site/", "/p/", "property", "properties", "ficha")


def _plano(texto: str) -> str:
    import unicodedata
    return unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode().lower()


def dominio_propio(cid: str, url: str) -> tuple[bool, str]:
    """El sitio es de la agencia: su dominio (o subdominio en un SaaS) lleva el nombre de la agencia.

    Fail-closed: si no se puede afirmar, no es propio. Acepta una palabra distintiva del nombre (>= 4
    letras, no generica) dentro del host, o la concatenacion de las dos primeras palabras (siglas:
    `ieb real estate` -> iebrealestate, `grupo sur` -> gruposurneuquen). Rechaza hosts de colegios,
    redes de franquicia y directorios, y entradas profundas que no son catalogo (una nota, un edicto).
    """
    import re
    p = urllib.parse.urlparse(url or "")
    host = p.netloc.lower().removeprefix("www.")
    if not host:
        return False, "sin host"
    if any(a in host for a in HOSTS_AJENOS):
        return False, "host de colegio, red o directorio"
    ruta = (p.path or "/").strip("/")
    if ruta.count("/") >= 2 and not any(k in (p.path + "?" + p.query).lower() for k in RUTA_DE_CATALOGO):
        return False, "entrada profunda que no es catalogo"
    # Solo la etiqueta propia (sin TLD): `nataliacura.com.ar` -> `nataliacura`; en un SaaS, el subdominio.
    etiqueta = re.sub(r"[^a-z0-9]", "", host.split(".")[0])
    plano_host = re.sub(r"[^a-z0-9]", "", host)
    palabras = [w for w in re.split(r"[^a-z0-9]+", _plano(cid.split(":", 1)[-1])) if w]
    distintivas = [w for w in palabras if len(w) >= 4 and w not in GENERICAS and not w.isdigit()]
    rubro = GENERICAS | {"inmuebles", "inmo", "prop", "props", "adm", "red", "mi", "the", "estudio", "bienes",
                         "raices", "brokers", "bienesraices", "realestate", "negociosinmobiliarios",
                         "propiedadesinmobiliaria", "operacionesinmobiliarias"}

    def en_borde(w: str) -> bool:
        """La palabra empieza la etiqueta o la precede un rubro, otra palabra del nombre o un nombre de pila.
        `dirosapropiedades` no es `rosa propiedades`; `estudiocalle` si es `abelardo calle`."""
        for m in re.finditer(re.escape(w), etiqueta):
            antes = etiqueta[:m.start()]
            if (not antes or any(antes.endswith(r) for r in rubro) or any(antes.endswith(p) for p in palabras)
                    or any(antes.endswith(n) for n in NOMBRES_DE_PILA)):
                return True
        return False

    propias = [w for w in distintivas if w not in NOMBRES_DE_PILA and en_borde(w)]
    if propias:
        return True, "palabra del nombre en el host"
    de_pila = [w for w in distintivas if w in NOMBRES_DE_PILA]
    # Un nombre de pila solo identifica si la etiqueta es ESE nombre + rubro (`marianopropiedades`):
    # `nataliacura` no es `natalia r cangiani`.
    if any(etiqueta.startswith(w) and (etiqueta[len(w):] in rubro or not etiqueta[len(w):]) for w in de_pila):
        return True, "nombre de pila + rubro como etiqueta"
    if len(palabras) >= 2 and len(palabras[0] + palabras[1]) >= 4 and plano_host.startswith(palabras[0] + palabras[1]):
        return True, "nombre concatenado al inicio del host"
    if palabras and 2 <= len(palabras[0]) <= 4 and plano_host.startswith(palabras[0]) and any(
            g in plano_host for g in ("propiedades", "inmobiliaria", "realestate", "bienesraices", "inmuebles")):
        return True, "sigla del nombre + rubro en el host"
    return False, "el host no lleva el nombre de la agencia"


def host_de(url: str | None) -> str:
    return urllib.parse.urlparse(url or "").netloc.lower().removeprefix("www.")


def _jsonl(ruta: Path):
    if not ruta.exists():
        return
    for linea in ruta.read_text(encoding="utf-8", errors="replace").splitlines():
        if linea.strip():
            try:
                yield json.loads(linea)
            except ValueError:
                continue


def reclamantes_por_host() -> dict[str, set[str]]:
    """Cuantas agencias del universo nombran cada host, en cualquier fuente."""
    por_host: dict[str, set[str]] = defaultdict(set)
    for fila in _jsonl(PLATAFORMAS):
        if fila.get("domain"):
            por_host[host_de(fila["domain"])].add(fila["canonical_agency_id"])
    for fila in _jsonl(DATOS / "agency_web_directory.jsonl"):
        if fila.get("official_url"):
            por_host[host_de(fila["official_url"])].add(fila["canonical_agency_id"])
    for fila in _jsonl(DESTINO):
        if fila.get("official_url"):
            por_host[host_de(fila["official_url"])].add(fila["canonical_agency_id"])
    return por_host


def cohorte(catalogo) -> list[tuple[str, dict]]:
    from scripts.agency_certifier import resolve_identity
    verificadas = {f["canonical_agency_id"] for f in _jsonl(DESTINO)}
    hechas = {f["canonical_agency_id"] for f in _jsonl(REGISTRO)}
    fuera = []
    for cid, rec in sorted(catalogo.items()):
        ide = resolve_identity(rec, cid)
        if (ide["identity_status"] == "IDENTITY_PENDING"
                and rec["resolution"].get("resolution_status") == "NOT_FOUND_IN_ERETZ"
                and rec["platform"].get("web_kind") == "OFFICIAL_WEB"
                and rec["platform"].get("domain")
                and cid not in verificadas and cid not in hechas):
            fuera.append((cid, rec))
    return fuera


def cohorte_sin_resolver(catalogo) -> list[tuple[str, dict]]:
    """Las que tienen un registro AFIRMABLE viejo SIN `estado_del_resolver` y por eso no entran a la cola.

    Mision 08-10: 294 registros de `verificar_candidatas_web` (14-09) quedaron sin el estado del resolver
    que P6 exige, y algunos son malos (`posse propiedades` -> una pagina de infractores del colegio). No se
    los asciende por decreto: se vuelven a abrir con el verificador vigente. La url a abrir es la del
    registro viejo; si pasa, la fila nueva (completa) reemplaza a la vieja porque la ultima manda.
    """
    from scripts.agency_certifier import resolve_identity
    ultimo = {f["canonical_agency_id"]: f for f in _jsonl(DESTINO)}
    fuera = []
    for cid, rec in sorted(catalogo.items()):
        viejo = ultimo.get(cid)
        if (viejo and not viejo.get("estado_del_resolver") and viejo.get("official_url")
                and rec["resolution"].get("resolution_status") == "NOT_FOUND_IN_ERETZ"
                and resolve_identity(rec, cid)["identity_status"] == "IDENTITY_PENDING"):
            fuera.append((cid, dict(rec, platform=dict(rec.get("platform") or {},
                                                       domain=viejo["official_url"]))))
    return fuera


def cohorte_candidatas_sin_web(catalogo) -> list[tuple[str, dict]]:
    """Las agencias SIN web, una entrada por cada candidata de dominio propio (las raices primero).

    Mision 08-10: de 3.476 canonicas sin web, 271 tienen al menos una candidata de la busqueda ya pagada
    (exa/serper/tavily) cuyo host lleva su nombre; nadie las abrio. Se prueban con la misma compuerta
    (identidad + pais + un solo reclamante); el bucle principal corta en la primera que pasa.
    """
    from scripts.agency_certifier import resolve_identity
    fuera = []
    for cid, rec in sorted(catalogo.items()):
        if resolve_identity(rec, cid)["official_url"]:
            continue
        candidatas = []
        for c in (rec.get("directory") or {}).get("candidate_urls") or []:
            url = c if isinstance(c, str) else (c.get("url") if isinstance(c, dict) else None)
            if url and not wd.es_portal(url) and dominio_propio(cid, url)[0]:
                candidatas.append(url)
        candidatas.sort(key=lambda u: (urllib.parse.urlparse(u).path.strip("/").count("/"), len(u)))
        for url in candidatas:
            fuera.append((cid, dict(rec, platform=dict(rec.get("platform") or {}, domain=url))))
    return fuera


def entidad(cid: str, rec: dict) -> dict:
    d, p = rec.get("directory") or {}, rec.get("platform") or {}
    zonas = [z for z in (d.get("city") or p.get("city"), d.get("province") or p.get("province")) if z]
    return {"stable_id": cid,
            "nombre_original": d.get("canonical_name") or p.get("agency_name") or cid.split(":", 1)[-1],
            "red_franquicia": d.get("franchise"), "zonas_observadas": zonas, "matricula": []}


def main() -> int:
    from scripts.agency_certifier import load_catalog
    ap = argparse.ArgumentParser()
    ap.add_argument("--aplicar", action="store_true",
                    help="sin esto solo registra; con esto agrega las establecidas al artefacto de la cola")
    ap.add_argument("--limite", type=int, default=0)
    ap.add_argument("--pausa", type=float, default=0.4)
    ap.add_argument("--reverificar-sin-resolver", action="store_true",
                    help="volver a abrir los AFIRMABLE viejos sin estado del resolver (ver cohorte_sin_resolver)")
    ap.add_argument("--candidatas-sin-web", action="store_true",
                    help="probar las candidatas de dominio propio de las agencias sin web (ver cohorte_candidatas_sin_web)")
    args = ap.parse_args()
    catalogo = load_catalog(V2, DATOS, PLATAFORMAS)
    if args.reverificar_sin_resolver:
        pendientes = cohorte_sin_resolver(catalogo)
    elif args.candidatas_sin_web:
        pendientes = cohorte_candidatas_sin_web(catalogo)
    else:
        pendientes = cohorte(catalogo)
    if args.limite:
        pendientes = pendientes[:args.limite]
    hosts = reclamantes_por_host()
    if args.candidatas_sin_web:
        # Las candidatas tambien reclaman su host: si dos agencias de la cohorte apuntan al mismo
        # dominio, ninguna lo afirma (HOST_COMPARTIDO), en vez de quedarse con la primera que llega.
        for cid, rec in pendientes:
            hosts[host_de(rec["platform"]["domain"])].add(cid)
    print(f"### VERIFICAR WEBS DEL DIRECTORIO (P6 fase 2) ### {len(pendientes)} agencias", flush=True)
    estados: Counter = Counter()
    afirmadas_en_la_corrida: set[str] = set()
    with REGISTRO.open("a", encoding="utf-8") as reg, DESTINO.open("a", encoding="utf-8") as dest:
        for i, (cid, rec) in enumerate(pendientes, 1):
            if cid in afirmadas_en_la_corrida:
                continue
            url = rec["platform"]["domain"]
            veredicto_id, pais, razon_pais = None, None, None
            propio, razon_propio = dominio_propio(cid, url)
            if wd.es_portal(url):
                estado = "PORTAL"
            elif not propio:
                estado = "HOST_NO_PROPIO"
                razon_pais = razon_propio
            else:
                candidata = bajar(url)
                es_tokko = str(rec["platform"].get("platform") or rec["platform"].get("connector") or "").lower() == "tokko"
                time.sleep(PAUSA_TOKKO if es_tokko else args.pausa)
                if candidata.http is None:
                    estado = "NO_RESPONDE"
                else:
                    veredicto_id = wd.verificar(entidad(cid, rec), [candidata])
                    estado = veredicto_id.estado
            n_host = len(hosts.get(host_de(url), set()) | {cid})
            afirmable = False
            if estado in ESTABLECIDAS:
                web = veredicto_id.official_web or url
                if host_de(web) != host_de(url):
                    estado = "OTRA_WEB"
                elif n_host != 1:
                    estado = "HOST_COMPARTIDO"
                else:
                    pais, razon_pais = es_argentina(web)
                    afirmable = pais == "VERIFICADA_ARGENTINA"
                    if not afirmable:
                        estado = f"PAIS:{pais}"
            estados["AFIRMABLE" if afirmable else estado] += 1
            fila = {"canonical_agency_id": cid, "url": url, "estado": estado,
                    "confianza": getattr(veredicto_id, "confianza", None),
                    "razon": getattr(veredicto_id, "razon", None),
                    "entidades_que_reclaman_el_host": n_host,
                    "verificacion": pais, "verificacion_razon": razon_pais,
                    "afirmable": afirmable, "cuando": time.strftime("%Y-%m-%dT%H:%M:%S"),
                    "database_writes": 0}
            reg.write(json.dumps(fila, ensure_ascii=False) + "\n")
            reg.flush()
            if afirmable:
                afirmadas_en_la_corrida.add(cid)
            if afirmable and args.aplicar:
                dest.write(json.dumps({
                    "canonical_agency_id": cid, "nombre": entidad(cid, rec)["nombre_original"],
                    "estado": "AFIRMABLE", "razon": veredicto_id.razon,
                    "official_url": veredicto_id.official_web or url,
                    "origen_descubierto": url, "url_descubierta": url,
                    "era_ruta_profunda": False,
                    "entidades_que_reclaman_el_host": n_host,
                    "estado_del_resolver": estado,
                    "identity_score": veredicto_id.confianza,
                    "verificacion": pais, "verificacion_razon": razon_pais,
                    "origen_del_dato": "verificar_webs_del_directorio",
                    "cuando": fila["cuando"], "database_writes": 0}, ensure_ascii=False) + "\n")
                dest.flush()
            if i % 50 == 0:
                print(f"  {i}/{len(pendientes)} {dict(estados)}", flush=True)
    print(json.dumps(dict(estados), ensure_ascii=False))
    print("consultas pagas: 0\ndatabase_writes: 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
