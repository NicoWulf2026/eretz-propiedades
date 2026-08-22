#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Control de identidad de las fuentes READY que comparten host.

Cuando varias inmobiliarias distintas apuntan al mismo dominio hay dos
situaciones muy distintas mezcladas:

  - un proveedor white-label legitimo, donde cada inmobiliaria tiene su perfil
    propio dentro de la plataforma (inmoup.com.ar/322750-akev-propiedades/);
  - una adjudicacion heredada equivocada, donde a la inmobiliaria se le asigno
    la pagina de busqueda de otra empresa
    (inmobiliariabertero.com.ar/provincia-de-buenos-aires/... para DANPROP).

La diferencia importa mucho: scrapear la segunda le atribuiria a una
inmobiliaria el inventario de un competidor. Este control las separa antes de
que se escriba un solo conector.

Sin buscadores. Reusa la URL ya guardada y la evidencia que ERETZ ya tiene.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


aud = _load("audit_existing_webs")
ident = _load("identity_scoring")
wd = _load("agency_web_discovery")
rh = _load("reaudit_historical")

IDENTITY_VERSION = "ready_identity_v1"

VERIFIED = "IDENTITY_VERIFIED"
ALTA = "IDENTITY_HIGH_CONFIDENCE"
AMBIGUA = "IDENTITY_AMBIGUOUS"
AJENA = "IDENTITY_WRONG_ENTITY"

# Rutas que identifican a UNA inmobiliaria dentro de una plataforma compartida.
PERFIL = re.compile(
    r"/(inmobiliaria|inmobiliarias|agencia|agencias|agencia-inmobiliaria|"
    r"broker|brokers|office|offices|oficina|sucursal|agente|agents|inmo|"
    r"corredor|corredores|realtor|empresa)/[a-z0-9-]{3,}"
    r"|/\d{4,}-[a-z0-9-]{3,}", re.I)

# Rutas de busqueda por zona: no identifican a nadie, son del dueno del sitio.
GEOGRAFICA = re.compile(
    r"/(provincia-de-|partido-de-|partido-|barrio-|zona-|localidad-|"
    r"buenos-aires/|capital-federal|cordoba/|santa-fe/|mendoza/|rosario/|"
    r"venta[s]?/|alquiler(es)?/|inmuebles-en-|propiedades-en-|busqueda|"
    r"resultados|search)|\?.*provincia=", re.I)

# Ficha de UNA propiedad. Aunque sea de esta inmobiliaria, desde ahi no se
# puede enumerar su inventario: no es una fuente, es un aviso suelto.
FICHA_UNICA = re.compile(
    r"/(property|propiedad|propiedades|inmueble|inmuebles|ficha|aviso|"
    r"listing|sandbox)/\d{3,}", re.I)

# Registros institucionales: colegios, matriculas, resenas, denuncias. Hablan
# DE la inmobiliaria pero no publican su inventario.
INSTITUCIONAL = re.compile(
    r"(colegiado|colegio-?inmobiliario|martilleros?|infractores|matriculados|"
    r"/rese|/review|/opiniones|padron|sancion)", re.I)


def host_de(url: str) -> str:
    return re.sub(r"^https?://(www\.)?", "", url or "").split("/")[0].lower()


def registrable(host: str) -> str:
    reg = re.sub(r"\.(com|net|org|info|io|site|app|ai)?\.?(ar)?$", "", host)
    return re.sub(r"[^a-z0-9]", "", reg)


def slug_lleva_el_nombre(url: str, nombre: str) -> bool:
    """La ruta nombra a la inmobiliaria, sin prefijo que lo anuncie.

    Muchas plataformas usan la raiz para el perfil: inmobusqueda.com/abalsamo
    propiedades o inmoup.com.ar/438-de-lucia. Sin esto se descartarian perfiles
    white-label perfectamente validos por no llevar /inmobiliaria/ adelante.
    """
    ruta = re.sub(r"^https?://[^/]+", "", url or "").strip("/")
    if not ruta:
        return False
    partes = [re.sub(r"[^a-z0-9]", "", x.split("?")[0].lower())
              for x in ruta.split("/")]
    partes = [x for x in partes if len(x) >= 5]
    if not partes:
        return False
    toks = sorted((t for t in wd.tokens_distintivos(nombre or "") if len(t) >= 4),
                  key=len, reverse=True)
    if not toks:
        return False
    # Sirve el primer segmento o el ultimo: unas plataformas ponen el perfil en
    # la raiz y otras lo cuelgan de /office/ o /inmobiliaria/.
    for slug in {partes[0], partes[-1]}:
        dentro = [t for t in toks if t in slug]
        if len(dentro) >= 2 or (dentro and len(dentro[0]) >= 5):
            return True
    return False


def forma_de_ruta(url: str, nombre: str = "") -> str:
    """Que representa esta URL dentro del host que la aloja.

    El orden va de lo mas especifico a lo mas vago: una ficha de propiedad
    tambien matchea PERFIL si se mira poco, y un registro del colegio tambien
    parece un perfil.
    """
    ruta = re.sub(r"^https?://[^/]+", "", url or "")
    if INSTITUCIONAL.search(ruta):
        return "REGISTRO_INSTITUCIONAL"
    if FICHA_UNICA.search(ruta):
        return "FICHA_DE_UNA_PROPIEDAD"
    if PERFIL.search(ruta) or slug_lleva_el_nombre(url, nombre):
        return "PERFIL_PROPIO"
    if GEOGRAFICA.search(ruta) or ruta in ("", "/"):
        return "GEOGRAFICA_O_RAIZ"
    return "OTRA"


def enriquecer(fila_dir: dict, cross: dict | None) -> dict:
    """Suma a la fila del directorio lo que ERETZ ya sabe de la inmobiliaria.

    El directorio no guarda telefono, matricula ni zonas; el crosswalk si. Sin
    esto la identidad se juzga solo por nombre y provincia, que es la mitad de
    la evidencia disponible.
    """
    ent = rh.como_entidad(fila_dir)
    if cross:
        ent["telefono"] = cross.get("telefono") or ent.get("telefono")
        ent["email"] = cross.get("email") or ent.get("email")
        ent["matricula"] = cross.get("matricula") or []
        ent["zonas_observadas"] = cross.get("zonas_observadas") or []
        ent["red_franquicia"] = cross.get("red_franquicia") or ent.get("red_franquicia")
        ent["official_office_page"] = cross.get("official_office_page")
        if cross.get("nombre_original"):
            ent["nombre_original"] = cross["nombre_original"]
    return ent


def host_lleva_el_nombre_de_otro(host: str, nombre_propio: str,
                                 nombres_del_host: list[str]) -> str | None:
    """Si el dominio lleva el nombre de OTRA inmobiliaria del mismo host, la
    pagina es de esa otra: el inventario que publique no es de esta.

    Nadie registra el dominio de un competidor, asi que esta senal es dura.
    """
    reg = registrable(host)
    if len(reg) < 6:
        return None
    propios = {t for t in wd.tokens_distintivos(nombre_propio or "") if len(t) >= 4}
    if any(t in reg for t in propios):
        return None
    for otro in nombres_del_host:
        if otro == nombre_propio:
            continue
        toks = [t for t in wd.tokens_distintivos(otro or "") if len(t) >= 5]
        if toks and sum(1 for t in toks if t in reg) >= min(2, len(toks)):
            return otro
    return None


def clasificar_identidad(ent: dict, sitio: dict, url: str, forma: str,
                         dueno_del_host: str | None) -> tuple[str, dict]:
    ev: dict = {"forma_de_ruta": forma, "http": sitio.get("http"),
                "titulo": (sitio.get("titulo") or "")[:120]}

    if dueno_del_host:
        ev["dominio_de"] = dueno_del_host
        ev["motivo"] = (f"el dominio lleva el nombre de otra inmobiliaria "
                        f"({dueno_del_host}) y la ruta no identifica a esta")
        return AJENA, ev

    p = ident.puntuar(ent, sitio)
    veredicto = ident.clasificar(p)
    ev["identity_score"] = p.total
    ev["identity_verdict_base"] = veredicto
    ev["senales"] = [s.clave for s in p.positivas][:6]
    ev["penas"] = [s.clave for s in p.negativas][:4]

    if p.total <= ident.PENAS["otro_rubro"] or p.rubro_detectado:
        ev["motivo"] = f"el sitio es de otro rubro ({p.rubro_detectado})"
        return AJENA, ev

    propio = rh.dominio_lleva_el_nombre(sitio.get("url") or url,
                                        ent.get("nombre_original") or "")
    ev["dominio_propio"] = propio

    # El dominio propio es lo unico que sobrevive a estar en un host compartido:
    # nadie registra el dominio de un competidor.
    if propio and p.total > 0:
        ev["motivo"] = "el dominio lleva el nombre de la inmobiliaria"
        return VERIFIED, ev

    # A partir de aca el host es de otro. Que la pagina NOMBRE a la inmobiliaria
    # no prueba nada: los portales listan a todo el mundo. Solo cuenta que la
    # RUTA la identifique.
    if forma == "REGISTRO_INSTITUCIONAL":
        ev["motivo"] = ("registro de colegio, matricula o resenas: habla de la "
                        "inmobiliaria pero no publica su inventario")
        return AJENA, ev
    if forma == "FICHA_DE_UNA_PROPIEDAD":
        ev["motivo"] = ("es la ficha de una sola propiedad: desde ahi no se "
                        "puede enumerar el inventario de la inmobiliaria")
        return AJENA, ev
    if forma == "GEOGRAFICA_O_RAIZ":
        ev["motivo"] = ("ruta de busqueda por zona en un host ajeno: publica "
                        "inventario de muchas inmobiliarias, no de esta")
        return AJENA, ev
    if forma == "PERFIL_PROPIO":
        # Un perfil nominado dentro de una plataforma es la fuente white-label
        # legitima: la ruta, no el texto, es lo que lo identifica.
        ev["motivo"] = "perfil nominado de esta inmobiliaria en una plataforma"
        return ALTA if p.total > 0 else AMBIGUA, ev
    if veredicto == "VERIFIED":
        ev["motivo"] = "senales fuertes propias (matricula, telefono o email)"
        return VERIFIED, ev
    ev["motivo"] = "no hay evidencia suficiente para adjudicar el sitio"
    return AMBIGUA, ev


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default=r"D:\INMO CAPITAL\ERETZ_AGENCY_DATA")
    ap.add_argument("--hilos", type=int, default=6)
    a = ap.parse_args()
    dd = Path(a.data_dir)

    mapa = [json.loads(l) for l in
            (dd / "scrape_source_technology_map.jsonl").open(encoding="utf-8") if l.strip()]
    directorio = {x["canonical_agency_id"]: x for x in
                  (json.loads(l) for l in
                   (dd / "agency_web_directory.jsonl").open(encoding="utf-8") if l.strip())}
    cross = {}
    ruta_cross = dd / "crosswalk_final.jsonl"
    if ruta_cross.exists():
        for l in ruta_cross.open(encoding="utf-8"):
            if not l.strip():
                continue
            r = json.loads(l)
            k = r.get("stable_id") or r.get("canonical_agency_id")
            if k:
                cross[k] = r

    por_host: dict[str, list] = defaultdict(list)
    for x in mapa:
        por_host[host_de(x["official_url"])].append(x)
    compartidos = {h: g for h, g in por_host.items()
                   if len({y["canonical_agency_id"] for y in g}) >= 2}
    sospechosas = [x for g in compartidos.values() for x in g]

    formas = Counter(forma_de_ruta(x["official_url"], x.get("agency_name") or "")
                     for x in sospechosas)
    print("### CONTROL DE IDENTIDAD SOBRE HOSTS COMPARTIDOS ###", flush=True)
    print(f"  fuentes READY en el mapa:        {len(mapa):,}", flush=True)
    print(f"  hosts compartidos por >=2:       {len(compartidos):,}", flush=True)
    print(f"  fuentes a auditar:               {len(sospechosas):,}", flush=True)
    for k, v in formas.most_common():
        print(f"    {k:22} {v:5,}", flush=True)

    nombres_por_host = {h: sorted({y.get("agency_name") or "" for y in g})
                        for h, g in compartidos.items()}

    def procesar(x: dict) -> dict:
        url = x["official_url"]
        host = host_de(url)
        fila = directorio.get(x["canonical_agency_id"], {})
        ent = enriquecer(fila, cross.get(x["canonical_agency_id"]))
        forma = forma_de_ruta(url, ent.get("nombre_original")
                              or x.get("agency_name") or "")
        dueno = None
        if forma != "PERFIL_PROPIO":
            dueno = host_lleva_el_nombre_de_otro(
                host, ent.get("nombre_original") or x.get("agency_name") or "",
                nombres_por_host[host])
        sitio = aud.bajar(url) if not dueno else {"http": None, "url": url}
        estado, ev = clasificar_identidad(ent, sitio, url, forma, dueno)
        return {
            "canonical_agency_id": x["canonical_agency_id"],
            "agency_name": x.get("agency_name"),
            "official_url": url,
            "host": host,
            "agencias_en_el_host": len({y["canonical_agency_id"]
                                        for y in compartidos[host]}),
            "identity_status": estado,
            "evidence": ev,
            "checked_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "identity_version": IDENTITY_VERSION,
        }

    salida = dd / "ready_identity_audit.jsonl"
    filas = []
    with salida.open("w", encoding="utf-8") as fh:
        for i in range(0, len(sospechosas), 30):
            with ThreadPoolExecutor(max_workers=a.hilos) as ex:
                for r in ex.map(procesar, sospechosas[i:i + 30]):
                    fh.write(json.dumps(r, ensure_ascii=False) + "\n")
                    filas.append(r)
            fh.flush()
            time.sleep(0.2)

    print(f"\n### RESULTADO ###", flush=True)
    for k, v in Counter(r["identity_status"] for r in filas).most_common():
        print(f"    {k:28} {v:5,}  ({v/max(len(filas),1)*100:5.1f}%)", flush=True)
    fuera = [r for r in filas if r["identity_status"] in (AJENA, AMBIGUA)]
    print(f"\n  se quitan de READY: {len(fuera):,} "
          f"({sum(1 for r in fuera if r['identity_status']==AJENA):,} ajenas, "
          f"{sum(1 for r in fuera if r['identity_status']==AMBIGUA):,} ambiguas)", flush=True)
    print(f"  artefacto -> ready_identity_audit.jsonl", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
