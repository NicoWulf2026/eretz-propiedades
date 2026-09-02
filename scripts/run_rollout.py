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
                             LimitadorDeRitmo, calcular_hash_dedup,
                             ficha_sin_contenido)
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

# Cuanto puede tardar UNA fuente antes de que se le corte el detalle.
#
# Un host que acepta la conexion y despues no contesta cuesta 75 segundos por
# ficha -25 de espera, tres intentos- sin devolver nada. Una fuente de 47
# fichas asi retiene un worker durante una hora, y con la paginacion a ciegas
# -tres patrones por hasta 58 paginas- el peor caso son tres horas y media.
# Una corrida de 158 fuentes cerro 157 en dos horas y se quedo esperando a esa
# una.
#
# El presupuesto no descarta la fuente: corta el detalle, guarda lo que ya
# obtuvo y lo deja anotado. La corrida siguiente la vuelve a intentar, que es
# lo que corresponde con algo que puede haber sido pasajero.
PRESUPUESTO_POR_FUENTE = 1800

# Un presupuesto plano castiga a la inmobiliaria grande o lenta justamente por
# serlo, y lo que se pierde ahi es inventario. abriolapropiedades.com.ar sirve
# a 6,27 s por ficha: con 263 fichas necesita 1.649 s, y la primera corrida se
# corto exactamente en el tope con 238. La segunda las trajo todas, asi que la
# comparacion entre ambas no medía la fuente, medía el reloj.
#
# El presupuesto pasa a escalar con el trabajo pedido. El margen por ficha esta
# por encima del peor sitio medido; el limitador de ritmo solo ya impone 1,5 s.
SEGUNDOS_POR_FICHA_LENTA = 8.0
# Techo duro: una fuente patologica no puede quedarse con la cola entera.
PRESUPUESTO_MAXIMO = 5400


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


# Una imagen que aparece en la mitad o mas del catalogo de una inmobiliaria no
# es la foto de ninguna de sus propiedades.
MINIMO_PARA_JUZGAR = 8
FRACCION_COMPARTIDA = 0.5


def descartar_imagenes_compartidas(objetos: list) -> int:
    """Saca de cada propiedad las imagenes que son de la PAGINA, no del aviso.

    El chinche del mapa, el icono del telefono, el boton de Pinterest y el
    banner de "Agenda un cafe" salen en todas las fichas del sitio. Medido sobre
    las 18.474 propiedades de WordPress: 91.836 referencias de imagen, el 15,8%
    del total, eran esto. Ademas de ensuciar el dataset hacian ruido en el
    incremental, porque el sitio las rota y cada rotacion se leia como que la
    propiedad habia cambiado de fotos.

    La senal es estructural y no depende del nombre del archivo: si la misma url
    esta en la mitad o mas de las propiedades de esa inmobiliaria, no es de
    ninguna. Se exige un minimo de propiedades para no castigar a una agencia
    con tres avisos del mismo edificio.
    """
    if len(objetos) < MINIMO_PARA_JUZGAR:
        return 0
    veces: Counter = Counter()
    for p in objetos:
        veces.update(set(p.imagenes or []))
    tope = max(MINIMO_PARA_JUZGAR // 2, len(objetos) * FRACCION_COMPARTIDA)
    compartidas = {u for u, n in veces.items() if n >= tope}
    if not compartidas:
        return 0
    descartadas = 0
    for p in objetos:
        antes = len(p.imagenes or [])
        p.imagenes = [u for u in (p.imagenes or []) if u not in compartidas]
        descartadas += antes - len(p.imagenes)
    return descartadas


def procesar(con, fuente: Fuente, max_fichas: int, observacion: bool,
             respaldo=None, presupuesto: float = PRESUPUESTO_POR_FUENTE) -> dict:
    """Procesa una fuente; si el connector de plataforma no la reconoce, prueba
    el de respaldo.

    Una fuente que WordPress no sabe leer no es necesariamente una fuente sin
    inventario: de las 48 que quedaron asi, 21 tienen sitemap y 28 traen JSON
    embebido. El connector generico las lee sin saber nada de WordPress. Dar la
    fuente por perdida porque el conector especifico no la entendio es
    desperdiciar inventario que esta publicado y accesible.
    """
    r = _procesar_con(con, fuente, max_fichas, observacion, presupuesto)
    if respaldo is not None and r.get("estado") in ("VARIANTE_NO_SOPORTADA",
                                                    "ERROR_DISCOVERY"):
        alt = _procesar_con(respaldo, fuente, max_fichas, observacion,
                            presupuesto)
        if alt.get("estado") == "OK" and alt.get("detalles_obtenidos"):
            alt["connector"] = respaldo.nombre
            alt["rescatada_por_respaldo"] = True
            alt["estado_original"] = r.get("estado")
            return alt
    return r


def _anotar_ficha_vacia(con, fuente: Fuente, prop) -> None:
    """Rastro de una ficha que no trajo nada, ni siquiera al reintentarla."""
    if not hasattr(con, "descartes"):
        con.descartes = []
    if len(con.descartes) < 500:
        con.descartes.append({
            "canonical_agency_id": fuente.canonical_agency_id,
            "source_url": prop.source_url,
            "motivo": "FICHA_SIN_CONTENIDO",
            "titulo": (prop.titulo or "")[:120],
            "tipo_propiedad": prop.tipo_propiedad,
        })


def _procesar_con(con, fuente: Fuente, max_fichas: int, observacion: bool,
                  presupuesto: float = PRESUPUESTO_POR_FUENTE) -> dict:
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
    # La identidad con la que se guarda una propiedad es su URL, no el id
    # que el sitio le pone: `_id_de` lo deriva de la ruta y dos fichas
    # distintas pueden dar el mismo numero. Midiendo la cobertura por ids,
    # una fuente que entrego sus 400 fichas figuraba con 50% -200 ids
    # unicos- y quedaba marcada ENUMERACION_INCOMPLETA con el inventario
    # entero en la mano.
    urls = {a["source_url"] for a in avisos}
    r["enumeradas"] = len(ids)
    r["ids_unicos"] = len(set(ids))
    r["urls_unicas"] = len(urls)
    r["duplicados_en_listado"] = (len(ids) - len(urls)
                                  + int(getattr(con, "duplicados_origen", 0)))
    r["paginas"] = max((a["pagina"] for a in avisos), default=0)
    declarado = plan.get("total_declarado")
    # El total humano de algunos CMS cuenta tarjetas, no identidades unicas.
    # Si una tarjeta se repite entre paginas, la cobertura esta contabilizada
    # pero se normaliza una sola propiedad. No confundir ese duplicado probado
    # con una URL faltante ni inflar el inventario de ERETZ.
    contabilizadas = len(urls) + r["duplicados_en_listado"]
    r["registros_declarados_contabilizados"] = contabilizadas
    r["cobertura"] = (round(min(contabilizadas, declarado) / declarado, 4)
                      if declarado else None)
    # Sin total declarado la paginacion se da por agotada cuando una pagina no
    # trae ids nuevos; con total declarado, la comparacion manda.
    r["enumeracion_completa"] = (r["cobertura"] is None or
                                 r["cobertura"] >= COBERTURA_MINIMA)
    # Si la paginacion llego hasta el final o si la cortaron. Sin esta
    # distincion, quedarse corto contra el total que declara el sitio se leia
    # siempre como un defecto nuestro, y el contador del sitio puede estar mal:
    # berruetainmob.com.ar declara 197 y sirve 193, con una ficha fantasma
    # /propiedad/0 que devuelve el catalogo entero.
    r["paginacion_interrumpida"] = bool(
        getattr(con, "paginacion_interrumpida", False))
    r["enumeracion_agotada"] = not r["paginacion_interrumpida"]

    seleccion = avisos if max_fichas <= 0 else avisos[:max_fichas]
    r["detalles_pedidos"] = len(seleccion)
    objetos = []
    fallidos = 0
    reintentos_diferidos: list[dict] = []
    recuperados_diferidos = 0
    if presupuesto:
        presupuesto = min(
            max(presupuesto, len(seleccion) * SEGUNDOS_POR_FICHA_LENTA),
            PRESUPUESTO_MAXIMO)
    limite = t0 + presupuesto if presupuesto else None
    r["presupuesto_efectivo"] = presupuesto or None
    for a in seleccion:
        if limite and time.time() > limite:
            r["presupuesto_agotado"] = True
            r["detalles_sin_pedir"] = (len(seleccion) - len(objetos)
                                       - fallidos)
            break
        errores_antes = len(con.errores)
        try:
            p = con.normalize(a, fuente)
        except Bloqueado:
            fallidos += 1
            break
        except (ErrorTransitorio, ErrorPermanente):
            fallidos += 1
            continue
        if p is None:
            # Algunos connectors convierten el fallo transitorio final del
            # downloader en ``None`` y lo dejan registrado en ``errores``.
            # Reintentarlo inmediatamente vuelve a caer dentro de la misma
            # ventana inestable. Se difiere hasta terminar el resto del lote:
            # conserva el limite de ritmo, no insiste ante 403/429 y permite
            # recuperar cortes aislados sin repetir toda la inmobiliaria.
            if (len(con.errores) > errores_antes
                    and con.errores[-1].get("etapa") in {
                        "detalle", "detalle_permanente"}):
                reintentos_diferidos.append(a)
                continue
            fallidos += 1
            continue
        if ficha_sin_contenido(p):
            # La pagina devolvio el cascaron: titulo del sitio y ningun campo
            # definitorio. Es un fallo de lectura, no una propiedad, y se
            # difiere igual que un timeout -la maquinaria que ya existe para
            # reintentar fuera de la ventana inestable-. Guardarla dejaria una
            # propiedad con el nombre de la inmobiliaria y un tipo adivinado.
            reintentos_diferidos.append(a)
            continue
        con.completar_ubicacion(p, fuente)
        objetos.append(p)

    fichas_vacias = 0
    for a in reintentos_diferidos:
        if limite and time.time() > limite:
            fallidos += 1
            continue
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
        if ficha_sin_contenido(p):
            # Segunda lectura y sigue sin traer nada. Cuenta como detalle
            # fallido -la url si era una ficha, lo que fallo fue leerla- con su
            # rastro: sin el, una url descartada es indistinguible de una que
            # nunca existio y nadie podria notar si el guardian se equivoca.
            fallidos += 1
            fichas_vacias += 1
            _anotar_ficha_vacia(con, fuente, p)
            continue
        con.completar_ubicacion(p, fuente)
        objetos.append(p)
        recuperados_diferidos += 1

    # El filtro va ANTES de registrar: la huella tiene que calcularse sobre lo
    # que efectivamente se guarda, o el checkpoint quedaria comparando contra
    # una version de la propiedad que no existe en el artefacto.
    r["fichas_sin_contenido"] = fichas_vacias

    r["imagenes_compartidas_descartadas"] = descartar_imagenes_compartidas(objetos)

    for p in objetos:
        cambio = con.registrar(fuente, p)
        d = p.a_dict()
        d["_cambio"] = cambio
        d["_run"] = r["checked_at"]
        props.append(d)

    r["detalles_obtenidos"] = len(props)
    r["detalles_fallidos"] = fallidos
    r["reintentos_diferidos"] = len(reintentos_diferidos)
    r["detalles_recuperados_diferidos"] = recuperados_diferidos
    # Cuantas descarto el guardian de forma. Separarlo de los fallos importa:
    # una pagina que no era ficha no es una fuente que respondio mal, y sin
    # esta cuenta las dos cosas se leen igual en el resumen.
    r["descartadas_por_forma"] = getattr(con, "descartadas_por_forma", 0)
    r["_descartes"] = getattr(con, "descartes", None) or []
    r["cambios"] = dict(Counter(p["_cambio"] for p in props))

    # --- ausencias, solo si la enumeracion merece confianza -----------------
    # Una fuente que respondio mal no puede dar por ausente a nada.
    confiable = r["enumeracion_completa"] and r["estado_ok"] if "estado_ok" in r else \
        r["enumeracion_completa"]
    # Y una fuente a la que se le corto el detalle tampoco: no la
    # terminamos de mirar, asi que no sabemos que dejo de estar.
    confiable = confiable and not r.get("presupuesto_agotado")
    # Las claves son hash_dedup calculadas de la url ENUMERADA: se conocen sin
    # bajar la ficha, asi que la deteccion de ausencias funciona aunque solo se
    # normalice una muestra.
    #
    # Pero un connector puede canonicalizar la url al normalizar, y entonces la
    # clave que guarda el checkpoint no es la de la url enumerada. Wasi sirve la
    # misma propiedad bajo dos slugs, y comparar una contra otra daba 33 bajas
    # falsas en la primera corrida de una sola fuente. Se comparan las dos
    # formas: la enumerada cubre lo que no se normalizo, la canonica cubre lo
    # que si. Es un superconjunto de lo visto, asi que no puede tapar una baja
    # real.
    vistos = {calcular_hash_dedup(fuente.inmobiliaria_id, a["source_url"])
              for a in avisos}
    vistos |= {p.hash_dedup for p in objetos}
    ausentes = con.identify_deleted_or_inactive(
        fuente, vistos, fuente_respondio=bool(confiable))
    if observacion:
        # En observacion nada se desactiva, pero la etiqueta tiene que seguir
        # diciendo la verdad. Pisar TODAS con POTENTIAL_INACTIVE borraba la
        # distincion entre "no la vimos, y eso significa algo" y "no la vimos, y
        # eso no significa nada": BTS entrego 3 de sus 13 fichas y sus 10
        # faltantes salieron como candidatas a baja, cuando el propio pipeline
        # ya habia decidido que esa enumeracion no era comparable -23% de
        # solapamiento- y no habia avanzado ni un contador.
        #
        # El contador estaba bien. Lo que enganaba era el renglon.
        for x in ausentes:
            if x.get("enumeracion_comparable"):
                x["estado"] = "POTENTIAL_INACTIVE"
            else:
                x["estado"] = "SIN_EVIDENCIA_ENUMERACION_NO_COMPARABLE"
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
    if r.get("presupuesto_agotado"):
        r["estado"] = "PRESUPUESTO_AGOTADO"
    else:
        r["estado"] = ("OK" if r["enumeracion_completa"]
                       else "ENUMERACION_INCOMPLETA")
    # Una enumeracion incompleta tiene que decir POR QUE lo esta. Deducirlo
    # despues, mirando numeros sueltos, es como se termina tratando igual a una
    # fuente que corto por falta de tiempo y a una que entrega la mitad de lo
    # que declara: la primera se reintenta, la segunda hay que investigarla.
    if not r.get("enumeracion_completa", True):
        if r.get("presupuesto_agotado"):
            r["motivo_incompleta"] = "se acabo el presupuesto de tiempo"
        elif r.get("total_declarado"):
            r["motivo_incompleta"] = (
                "el sitio declara %s avisos y la paginacion entrego %s"
                % (r.get("total_declarado"), r.get("urls_unicas")))
        else:
            r["motivo_incompleta"] = ("la paginacion se agoto sin traer ids "
                                      "nuevos y el sitio no declara un total")
        r["evidencia_incompleta"] = {
            "declarado": r.get("total_declarado"),
            "enumerado": r.get("urls_unicas"),
            "cobertura": r.get("cobertura"),
            "paginas_recorridas": r.get("paginas"),
            "cobertura_minima_exigida": COBERTURA_MINIMA,
        }
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
                # Forma de ficha verificada PARA ESTA FUENTE. Se pasa por el
                # censo en vez de aflojar el patron global: la evidencia se
                # comprobo en este sitio, no en los otros 2.258.
                "patron_ficha": r.get("patron_ficha"),
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
    # Lo que el guardian de forma no acepto como ficha, con la evidencia de por
    # que. Sirve para auditar el guardian sin volver a bajar nada.
    esc_desc = EscritorDurable(out / f"shape_rejects{sufijo}.jsonl")

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
                   extra={"city": x.get("city"), "province": x.get("province"),
                          "patron_ficha": x.get("patron_ficha")})
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
            descartes = r.pop("_descartes", [])
            esc_props.escribir(props)
            if descartes:
                esc_desc.escribir(descartes)
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
        "descartadas_por_forma": sum(r.get("descartadas_por_forma", 0) for r in inv),
        "propiedades_escritas": len(props),
        "cambios": dict(Counter(p["_cambio"] for p in props)),
        "potential_inactive": len(leer_jsonl(out / f"absences{sufijo}.jsonl")),
        "duplicados_intra_fuente": len(props) - len({p["hash_dedup"] for p in props}),
        "hash_compartido_entre_agencias": sum(1 for v in por_hash.values() if len(v) > 1),
        "fotos_ajenas": sum(r.get("fotos_ajenas", 0) for r in inv),
        "imagenes_de_la_pagina_descartadas": sum(
            r.get("imagenes_compartidas_descartadas", 0) for r in inv),
        "fuentes_enumeracion_incompleta": sum(
            1 for r in inv if r.get("enumeracion_completa") is False),
        "errores": len(leer_jsonl(out / f"errors{sufijo}.jsonl")),
        "rescatadas_por_respaldo": sum(1 for r in inv if r.get("rescatada_por_respaldo")),
        "segundos": round(time.time() - t0, 1),
    }
    # Lo que el presupuesto de tiempo no llego a pedir entra en la cuenta: si
    # no, cortar una fuente lenta haria fallar la reconciliacion de la corrida
    # entera y el numero dejaria de significar lo que dice.
    resumen["detalles_sin_pedir"] = sum(r.get("detalles_sin_pedir", 0)
                                        for r in inv)
    resumen["fuentes_sin_presupuesto"] = sum(
        1 for r in inv if r.get("presupuesto_agotado"))
    resumen["reconcilia"] = (
        resumen["detalles_obtenidos"] + resumen["detalles_fallidos"]
        + resumen["detalles_sin_pedir"] == resumen["detalles_pedidos"]
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
