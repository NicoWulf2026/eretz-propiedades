#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Rollout de ingesta directa, agnostico de plataforma.

El mismo runner sirve para Tokko, WordPress o lo que venga: recibe el nombre del
connector y se ocupa de lo que es igual para todos — paralelismo entre fuentes,
cortesia por host, checkpoint durable, reanudacion y reconciliacion.

Dos cosas que se separan a proposito:

  - CONCURRENCIA es cuantas inmobiliarias se procesan a la vez;
  - CORTESIA es cuanto se espera entre pedidos A UN MISMO host.
    Mezclarlas convierte el limite de cortesia en un limite global y el rollout
    completo pasa de horas a dias.

  - MODO OBSERVACION: una propiedad que ya no aparece se anota como
    POTENTIAL_INACTIVE y nada mas. No se desactiva ni se borra hasta que la
    regla de bajas se haya validado contra corridas reales.

No escribe en Supabase. Produce artefactos fuera del repo.
"""
from __future__ import annotations

import argparse
import json
import sys
import threading
import time
import traceback
import urllib.parse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from connectors.base import (Bloqueado, Checkpoint, Descargador,  # noqa: E402
                             ErrorPermanente, ErrorTransitorio, Fuente,
                             LimitadorDeRitmo, calcular_hash_dedup)
from connectors.tokko import TokkoConnector  # noqa: E402
from connectors.wordpress import WordPressConnector  # noqa: E402
from connectors.century21 import Century21Connector  # noqa: E402
from connectors.generico import GenericoConnector  # noqa: E402
from connectors.wasi import WasiConnector  # noqa: E402
from scripts.run_tokko_canary import id_sustituto  # noqa: E402

CONNECTORS = {"tokko": TokkoConnector, "wordpress": WordPressConnector,
              "century21": Century21Connector, "generico": GenericoConnector,
              "wasi": WasiConnector}

# Umbral conservador: por debajo de esto el inventario se considera truncado.
# Una fuente que declara 299 y entrega 20 no puede quedar como PASS.
COBERTURA_MINIMA = 0.98


class EscritorDurable:
    """Append seguro a JSONL desde varios hilos.

    Abre y cierra en cada escritura a proposito. Un handle sostenido durante
    horas ya murio una vez en este proyecto con OSError errno 22 cuando el
    proceso quedo huerfano, y se llevo la corrida entera.
    """

    def __init__(self, ruta: Path):
        self.ruta = Path(ruta)
        self.ruta.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def escribir(self, filas: list[dict] | dict) -> None:
        if isinstance(filas, dict):
            filas = [filas]
        if not filas:
            return
        texto = "".join(json.dumps(f, ensure_ascii=False) + "\n" for f in filas)
        with self._lock:
            with self.ruta.open("a", encoding="utf-8") as fh:
                fh.write(texto)
                fh.flush()


def leer_jsonl(ruta: Path) -> list[dict]:
    """Tolerante a la ultima linea truncada por una caida."""
    if not ruta.exists():
        return []
    salida = []
    for linea in ruta.open(encoding="utf-8"):
        linea = linea.strip()
        if not linea:
            continue
        try:
            salida.append(json.loads(linea))
        except ValueError:
            continue
    return salida


# Se calcula al ARRANCAR, no al informar. Una corrida que empezo antes de una
# edicion seguia leyendo el codigo viejo en memoria pero reportaba la huella del
# archivo ya editado: las dos corridas parecian iguales cuando no lo eran, que
# es justo lo contrario de para lo que sirve la huella.
_VERSION_AL_ARRANCAR: dict[str, str] = {}


def version_del_codigo(connector: str) -> str:
    """Huella del codigo que produce las propiedades.

    Editar un connector mientras una corrida esta en vuelo hace que la segunda
    lea codigo distinto: todo aparece MODIFICADA y la idempotencia parece rota
    cuando lo unico que cambio fui yo. Ya paso dos veces y la unica pista era
    comparar campo por campo. Ahora queda escrito en el resumen de cada corrida
    y la diferencia salta a la vista.
    """
    import hashlib
    raiz = Path(__file__).resolve().parents[1]
    # Solo el connector en uso, la base y este runner. Hashear TODOS los
    # connectors hacia que agregar uno nuevo invalidara la comparacion de los
    # demas, y la huella dejaba de servir para lo unico que se hizo: saber si
    # dos corridas de la MISMA fuente vieron el mismo codigo.
    rutas = [raiz / "connectors" / "base.py",
             raiz / "connectors" / f"{connector}.py",
             raiz / "scripts" / "run_rollout.py"]
    if connector in _VERSION_AL_ARRANCAR:
        return _VERSION_AL_ARRANCAR[connector]
    h = hashlib.sha256()
    for ruta in rutas:
        if ruta.exists():
            h.update(ruta.read_bytes())
    _VERSION_AL_ARRANCAR[connector] = h.hexdigest()[:12]
    return _VERSION_AL_ARRANCAR[connector]


def host_de(url: str) -> str:
    return urllib.parse.urlparse(url).netloc.lower().replace("www.", "")


def universo(dd: Path, plataforma: str, variantes: set[str] | None,
             limite: int, filtro_url: str = "") -> list[dict]:
    """El universo sale del mapa vigente, no de un numero fijo.

    `filtro_url` acota por dominio cuando una red vive dentro de una plataforma
    mas amplia: las 42 oficinas de Century 21 estan clasificadas como UNKNOWN
    junto a otras 800 fuentes que no tienen nada que ver, y correr el conector
    sobre todas gasta miles de peticiones para que las rechace una por una.
    """
    mapa = leer_jsonl(dd / "scrape_source_technology_map.jsonl")
    fuentes = [x for x in mapa if x["detected_platform"] == plataforma]
    if filtro_url:
        fuentes = [x for x in fuentes if filtro_url in (x.get("official_url") or "")]
    if variantes:
        desc = {d["canonical_agency_id"]: d
                for d in leer_jsonl(dd / "tokko_discovery.jsonl")}
        conocidas = [x for x in fuentes
                     if desc.get(x["canonical_agency_id"], {}).get("variante") in variantes]
        # Las que nunca pasaron por discovery no se descartan: el connector
        # decide su variante al vuelo y reporta si no la soporta. Excluirlas
        # aca seria dar por perdida una fuente que nadie miro.
        sin_ver = [x for x in fuentes if x["canonical_agency_id"] not in desc]
        fuentes = conocidas + sin_ver
    # El mapa no guarda ciudad ni provincia; el directorio de agencias si. Se
    # unen aca para que el connector pueda completar ubicacion desde el padron
    # cuando la ficha no la publica.
    padron = {x["canonical_agency_id"]: x
              for x in leer_jsonl(dd / "agency_web_directory.jsonl")}
    for f in fuentes:
        d = padron.get(f["canonical_agency_id"]) or {}
        f["city"] = d.get("city")
        f["province"] = d.get("province")
        # El id real de la inmobiliaria en ERETZ. El crosswalk ya lo resolvio
        # con cuidado, asi que usarlo evita rehacer ese trabajo por nombre
        # contra la base -que es donde se cometen los errores de asociacion- y
        # hace que el hash_dedup salga desde el principio igual al que
        # produciria produccion.
        eid = d.get("eretz_id")
        f["eretz_id"] = int(eid) if str(eid).isdigit() else None

    fuentes.sort(key=lambda x: x["canonical_agency_id"])
    return fuentes[:limite] if limite else fuentes


def procesar(con, fuente: Fuente, max_fichas: int, observacion: bool,
             respaldo=None) -> dict:
    """Procesa una fuente; si el connector de plataforma no la reconoce, prueba
    el de respaldo.

    Una fuente que WordPress no sabe leer no es necesariamente una fuente sin
    inventario: de las 48 que quedaron asi, 21 tienen sitemap y 28 traen JSON
    embebido. El connector generico las lee sin saber nada de WordPress. Dar la
    fuente por perdida porque el conector especifico no la entendio es
    desperdiciar inventario que esta publicado y accesible.
    """
    r = _procesar_con(con, fuente, max_fichas, observacion)
    if respaldo is not None and r.get("estado") in ("VARIANTE_NO_SOPORTADA",
                                                    "ERROR_DISCOVERY"):
        alt = _procesar_con(respaldo, fuente, max_fichas, observacion)
        if alt.get("estado") == "OK" and alt.get("detalles_obtenidos"):
            alt["connector"] = respaldo.nombre
            alt["rescatada_por_respaldo"] = True
            alt["estado_original"] = r.get("estado")
            return alt
    return r


def _procesar_con(con, fuente: Fuente, max_fichas: int, observacion: bool) -> dict:
    t0 = time.time()
    r: dict = {"canonical_agency_id": fuente.canonical_agency_id,
               "agency_name": fuente.agency_name,
               "official_url": fuente.official_url,
               "host": host_de(fuente.official_url),
               "connector": con.nombre,
               "checked_at": time.strftime("%Y-%m-%dT%H:%M:%S")}
    props: list[dict] = []
    try:
        plan = con.discover(fuente)
    except Bloqueado as e:
        return {**r, "estado": "BLOQUEADA", "detalle": str(e)[:80],
                "segundos": round(time.time() - t0, 1), "_props": props}
    except (ErrorTransitorio, ErrorPermanente) as e:
        return {**r, "estado": "ERROR_DISCOVERY", "detalle": str(e)[:80],
                "segundos": round(time.time() - t0, 1), "_props": props}

    r.update({"variante": plan["variante"], "soportada": plan["soportada"],
              "total_declarado": plan["total_declarado"],
              "tokko_client_id": plan.get("tokko_client_id"),
              "ruta_listado": plan.get("ruta_listado")})
    if not plan["soportada"]:
        return {**r, "estado": "VARIANTE_NO_SOPORTADA",
                "segundos": round(time.time() - t0, 1), "_props": props}

    try:
        avisos = list(con.fetch_listing(fuente, plan))
    except Bloqueado as e:
        return {**r, "estado": "BLOQUEADA", "detalle": str(e)[:80],
                "segundos": round(time.time() - t0, 1), "_props": props}
    except ErrorTransitorio as e:
        return {**r, "estado": "ERROR_LISTADO", "detalle": str(e)[:80],
                "segundos": round(time.time() - t0, 1), "_props": props}

    ids = [a["source_listing_id"] for a in avisos]
    r["enumeradas"] = len(ids)
    r["ids_unicos"] = len(set(ids))
    r["duplicados_en_listado"] = len(ids) - len(set(ids))
    r["paginas"] = max((a["pagina"] for a in avisos), default=0)
    declarado = plan.get("total_declarado")
    r["cobertura"] = round(len(set(ids)) / declarado, 4) if declarado else None
    # Sin total declarado la paginacion se da por agotada cuando una pagina no
    # trae ids nuevos; con total declarado, la comparacion manda.
    r["enumeracion_completa"] = (r["cobertura"] is None or
                                 r["cobertura"] >= COBERTURA_MINIMA)

    seleccion = avisos if max_fichas <= 0 else avisos[:max_fichas]
    r["detalles_pedidos"] = len(seleccion)
    objetos = []
    fallidos = 0
    for a in seleccion:
        try:
            p = con.normalize(a, fuente)
        except Bloqueado:
            fallidos += 1
            break
        except (ErrorTransitorio, ErrorPermanente):
            fallidos += 1
            continue
        if p is None:
            fallidos += 1
            continue
        con.completar_ubicacion(p, fuente)
        cambio = con.registrar(fuente, p)
        d = p.a_dict()
        d["_cambio"] = cambio
        d["_run"] = r["checked_at"]
        props.append(d)
        objetos.append(p)

    r["detalles_obtenidos"] = len(props)
    r["detalles_fallidos"] = fallidos
    r["cambios"] = dict(Counter(p["_cambio"] for p in props))

    # --- ausencias, solo si la enumeracion merece confianza -----------------
    # Una fuente que respondio mal no puede dar por ausente a nada.
    confiable = r["enumeracion_completa"] and r["estado_ok"] if "estado_ok" in r else \
        r["enumeracion_completa"]
    # Las claves son hash_dedup, calculadas de la url enumerada: se conocen sin
    # bajar la ficha, asi que la deteccion de ausencias funciona aunque solo se
    # normalice una muestra.
    vistos = {calcular_hash_dedup(fuente.inmobiliaria_id, a["source_url"])
              for a in avisos}
    ausentes = con.identify_deleted_or_inactive(
        fuente, vistos, fuente_respondio=bool(confiable))
    if observacion:
        for x in ausentes:
            x["estado"] = "POTENTIAL_INACTIVE"
    r["ausentes"] = len(ausentes)
    r["_ausentes"] = ausentes

    if props:
        def lleno(c):
            return sum(1 for p in props if p.get(c) not in (None, "", []))
        r["completitud"] = {c: round(lleno(c) / len(props), 4) for c in (
            "titulo", "precio", "moneda", "operacion", "tipo_propiedad",
            "direccion", "barrio", "ciudad", "provincia", "dormitorios", "banos",
            "ambientes", "superficie_cubierta", "superficie_total", "latitud",
            "imagenes", "descripcion")}
        r["hash_unicos"] = len({p["hash_dedup"] for p in props})
        # Solo se cuenta donde el connector puede probarlo. En una plataforma
        # que no permite verificarlo, el conteo daria miles de falsos positivos
        # y taparia los casos reales de otra que si.
        if con.foto_verificable():
            r["fotos_ajenas"] = sum(
                1 for p, o in zip(props, objetos) for u in p["imagenes"]
                if not con.foto_es_de(o, u))
        else:
            r["fotos_verificables"] = False
        r["problemas"] = dict(Counter(q for p in props for q in p["problemas"]))
    r["estado"] = "OK" if r["enumeracion_completa"] else "ENUMERACION_INCOMPLETA"
    r["segundos"] = round(time.time() - t0, 1)
    return {**r, "_props": props}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default=r"D:\INMO CAPITAL\ERETZ_AGENCY_DATA")
    ap.add_argument("--salida", required=True)
    ap.add_argument("--connector", default="tokko")
    ap.add_argument("--plataforma", default="TOKKO")
    ap.add_argument("--variantes", default="TFW_ESTANDAR,TFW_SIN_AJAX")
    ap.add_argument("--limite", type=int, default=0)
    ap.add_argument("--max-fichas", type=int, default=0, help="0 = todas")
    ap.add_argument("--concurrencia", type=int, default=8)
    ap.add_argument("--intervalo", type=float, default=1.5)
    ap.add_argument("--corrida", default="1")
    ap.add_argument("--observacion", action="store_true", default=True)
    ap.add_argument("--filtro-url", default="", help="acota el universo por dominio")
    ap.add_argument("--censo", default="",
                    help="JSONL del censo: procesa solo las fuentes cuyo "
                         "connector_candidato coincide con --connector")
    ap.add_argument("--respaldo", default="",
                    help="connector a probar cuando el principal no soporta la fuente")
    a = ap.parse_args()
    dd, out = Path(a.data_dir), Path(a.salida)
    out.mkdir(parents=True, exist_ok=True)

    # Se fija apenas arranca, antes de bajar nada.
    version_del_codigo(a.connector)
    variantes = {v for v in a.variantes.split(",") if v} or None
    if a.censo:
        # El censo ya decidio que connector corresponde a cada fuente. Volver a
        # filtrar por plataforma aca las descartaria: justamente estan en el
        # censo porque su plataforma declarada era la equivocada.
        padron = {x["canonical_agency_id"]: x
                  for x in leer_jsonl(dd / "agency_web_directory.jsonl")}
        fuentes = []
        for r in leer_jsonl(Path(a.censo)):
            if r.get("connector_candidato") != a.connector:
                continue
            d = padron.get(r["canonical_agency_id"]) or {}
            eid = r.get("eretz_id") or d.get("eretz_id")
            fuentes.append({
                "canonical_agency_id": r["canonical_agency_id"],
                "agency_name": r.get("agency_name"),
                "official_url": r["official_url"],
                "detected_platform": r.get("clasificacion_nueva") or "CENSO",
                "city": d.get("city"), "province": d.get("province"),
                "eretz_id": int(eid) if str(eid).isdigit() else None,
            })
        if a.limite:
            fuentes = fuentes[:a.limite]
    else:
        fuentes = universo(dd, a.plataforma, variantes, a.limite, a.filtro_url)

    sufijo = f"_run{a.corrida}"
    esc_inv = EscritorDurable(out / f"source_inventory{sufijo}.jsonl")
    esc_props = EscritorDurable(out / f"properties{sufijo}.jsonl")
    esc_aus = EscritorDurable(out / f"absences{sufijo}.jsonl")
    esc_err = EscritorDurable(out / f"errors{sufijo}.jsonl")

    # Reanudacion: lo ya procesado en ESTA corrida no se repite.
    hechas = {r["canonical_agency_id"]
              for r in leer_jsonl(out / f"source_inventory{sufijo}.jsonl")}
    pendientes = [f for f in fuentes if f["canonical_agency_id"] not in hechas]

    print(f"### ROLLOUT {a.plataforma} — corrida {a.corrida} (modo observacion) ###")
    print(f"  universo:      {len(fuentes):,}")
    print(f"  ya procesadas: {len(hechas):,}")
    print(f"  pendientes:    {len(pendientes):,}")
    print(f"  concurrencia:  {a.concurrencia} fuentes | cortesia {a.intervalo}s por host")
    print(f"  fichas por fuente: {'todas' if a.max_fichas <= 0 else a.max_fichas}\n",
          flush=True)

    limitador = LimitadorDeRitmo(a.intervalo)
    checkpoint = Checkpoint(out / "checkpoint.json")
    cp_lock = threading.Lock()
    Clase = CONNECTORS[a.connector]

    t0 = time.time()
    contadores: Counter = Counter()
    hecho = 0

    def tarea(x: dict) -> dict:
        # Un connector por hilo, descargador propio, limitador COMPARTIDO: la
        # cortesia es del host, no del hilo.
        con = Clase(descargador=Descargador(limitador), checkpoint=checkpoint)
        alt = (CONNECTORS[a.respaldo](descargador=Descargador(limitador),
                                      checkpoint=checkpoint)
               if a.respaldo else None)
        f = Fuente(canonical_agency_id=x["canonical_agency_id"],
                   agency_name=x.get("agency_name") or "",
                   official_url=x["official_url"],
                   # Sin id real la propiedad no se puede asociar a nadie: se
                   # usa el sustituto para poder medir, y la carga al pipeline
                   # descarta despues lo que no tenga id del padron.
                   inmobiliaria_id=(x.get("eretz_id")
                                    or id_sustituto(x["canonical_agency_id"])),
                   detected_platform=x["detected_platform"],
                   extra={"city": x.get("city"), "province": x.get("province")})
        try:
            r = procesar(con, f, a.max_fichas, a.observacion, alt)
        except Exception as e:  # nunca tumbar el rollout por una fuente
            r = {"canonical_agency_id": x["canonical_agency_id"],
                 "agency_name": x.get("agency_name"), "official_url": x["official_url"],
                 "estado": "EXCEPCION", "detalle": f"{type(e).__name__}: {e}"[:160],
                 "traza": traceback.format_exc()[-400:], "_props": [], "segundos": 0}
        if con.errores:
            esc_err.escribir(con.errores)
        if alt is not None and alt.errores:
            esc_err.escribir(alt.errores)
        return r

    with ThreadPoolExecutor(max_workers=a.concurrencia) as ex:
        futuros = {ex.submit(tarea, x): x for x in pendientes}
        for fut in as_completed(futuros):
            r = fut.result()
            props = r.pop("_props", [])
            ausentes = r.pop("_ausentes", [])
            esc_props.escribir(props)
            if ausentes:
                esc_aus.escribir([{**x, "canonical_agency_id": r["canonical_agency_id"]}
                                  for x in ausentes])
            esc_inv.escribir(r)
            with cp_lock:
                checkpoint.guardar()
            contadores[r["estado"]] += 1
            contadores["propiedades"] += len(props)
            hecho += 1
            if hecho % 10 == 0 or hecho == len(pendientes):
                tr = time.time() - t0
                print(f"  {hecho}/{len(pendientes)} fuentes | "
                      f"{contadores['propiedades']:,} propiedades | "
                      f"{tr/60:.1f} min | "
                      f"{contadores['propiedades']/max(tr,1)*3600:,.0f} prop/h",
                      flush=True)

    # ---------------------------------------------------------- reconciliacion
    inv = leer_jsonl(out / f"source_inventory{sufijo}.jsonl")
    props = leer_jsonl(out / f"properties{sufijo}.jsonl")
    ok = [r for r in inv if r["estado"] == "OK"]
    por_hash = defaultdict(set)
    for p in props:
        por_hash[p["hash_dedup"]].add(p["canonical_agency_id"])

    resumen = {
        "corrida": a.corrida, "plataforma": a.plataforma, "connector": a.connector,
        "version_codigo": version_del_codigo(a.connector),
        "fuentes_intentadas": len(inv),
        "fuentes_por_estado": dict(Counter(r["estado"] for r in inv)),
        "propiedades_declaradas": sum(r.get("total_declarado") or 0 for r in ok),
        "propiedades_enumeradas": sum(r.get("enumeradas", 0) for r in ok),
        "detalles_pedidos": sum(r.get("detalles_pedidos", 0) for r in inv),
        "detalles_obtenidos": sum(r.get("detalles_obtenidos", 0) for r in inv),
        "detalles_fallidos": sum(r.get("detalles_fallidos", 0) for r in inv),
        "propiedades_escritas": len(props),
        "cambios": dict(Counter(p["_cambio"] for p in props)),
        "potential_inactive": len(leer_jsonl(out / f"absences{sufijo}.jsonl")),
        "duplicados_intra_fuente": len(props) - len({p["hash_dedup"] for p in props}),
        "hash_compartido_entre_agencias": sum(1 for v in por_hash.values() if len(v) > 1),
        "fotos_ajenas": sum(r.get("fotos_ajenas", 0) for r in inv),
        "fuentes_enumeracion_incompleta": sum(
            1 for r in inv if r.get("enumeracion_completa") is False),
        "errores": len(leer_jsonl(out / f"errors{sufijo}.jsonl")),
        "rescatadas_por_respaldo": sum(1 for r in inv if r.get("rescatada_por_respaldo")),
        "segundos": round(time.time() - t0, 1),
    }
    resumen["reconcilia"] = (
        resumen["detalles_obtenidos"] + resumen["detalles_fallidos"]
        == resumen["detalles_pedidos"]
        and resumen["propiedades_escritas"] == resumen["detalles_obtenidos"])
    if ok:
        campos = defaultdict(list)
        for r in ok:
            for c, v in (r.get("completitud") or {}).items():
                campos[c].append(v)
        resumen["completitud"] = {c: round(sum(v) / len(v), 4)
                                  for c, v in sorted(campos.items())}
    (out / f"quality_report{sufijo}.json").write_text(
        json.dumps(resumen, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n### RESUMEN corrida {a.corrida} ###")
    for k, v in resumen.items():
        if k != "completitud":
            print(f"  {k:34} {v}")
    print(f"\n  artefactos -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
