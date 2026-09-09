#!/usr/bin/env python
"""Cola deterministica y reanudable para AGENCY_CERTIFIER.

Procesa una inmobiliaria por vez. Ante NEEDS_FIX se detiene para que el defecto
se corrija antes de contaminar la evaluacion de las siguientes fuentes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import threading
import time
import urllib.parse
import urllib.request
import traceback
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.preingestion_manifest import base_canonica  # noqa: E402
from scripts.property_observations import (  # noqa: E402
    registrar as registrar_observacion)
from scripts.defect_triage import senales_de_catalogo  # noqa: E402
from scripts.defect_triage import (STOP, clasificar,  # noqa: E402
                                   debe_cortar_por_lote)
from scripts.agency_certifier import (
    CERTIFIER_VERSION,
    append_jsonl,
    certify,
    choose_connector,
    load_catalog,
    read_jsonl,
    resolve_identity,
    update_rollups,
    version_del_codigo,
    write_json,
)
from scripts.run_rollout import PRESUPUESTO_POR_FUENTE
from scripts.agency_fingerprints import (
    GENERIC_STRATEGY_METHODS,
    strategy_fingerprint,
    strategy_for,
)

TERMINAL = {
    "CERTIFIED_COMPLETE", "CERTIFIED_BEST_AVAILABLE", "BLOCKED_EXTERNAL",
    "IDENTITY_PENDING", "NO_INVENTORY_CONFIRMED",
}


CERROJO = "AGENCY_CERTIFICATION_RUNNER.lock"
# La bandera que corta a TODOS los workers. Un defecto transversal lo es para
# los dos: si uno para por radio FAMILIA y el otro sigue, el segundo certifica
# con el mismo codigo sospechado y hay que rehacer su trabajo igual.
# Defectos ya diagnosticados que NO se van a arreglar en esta pasada.
#
# El corte por lote existe para que cinco defectos sueltos obliguen a una
# tanda de diagnostico, y esta bien. Pero cuenta tambien los que ya
# tuvieron su tanda: `armanino` y `attaguile` sirven el catalogo por
# JavaScript y `andrea gianfelice` pierde una ficha de 147 cuya url el
# propio sitio no sirve. Los tres estan diagnosticados y ninguno se
# arregla sin un cambio que invalida la pasada entera, asi que se quedan
# en la lista de pendientes y hacen saltar el umbral de las 12 horas una y
# otra vez, sin que haya nada nuevo que mirar.
#
# Diferir NO es ocultar: el defecto se sigue anotando entero en
# `AGENCY_DEFECT_QUEUE.jsonl` y la agencia sigue cerrando `NEEDS_FIX`. Lo
# unico que cambia es que deja de contar para el corte por LOTE.
#
# Y no alcanza para tapar nada: solo se difiere lo que el triage ya decidio
# CONTINUE. Un defecto de radio transversal para las dos colas igual, este
# o no en la lista.
DIFERIDOS = "AGENCY_DEFECTS_DIFERIDOS.jsonl"


def diferidos(output: Path) -> dict[str, str]:
    """Que agencias tienen su defecto diagnosticado y postergado, y por que."""
    ruta = output / DIFERIDOS
    if not ruta.exists():
        return {}
    fuera: dict[str, str] = {}
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        if not linea.strip():
            continue
        try:
            fila = json.loads(linea)
        except ValueError:
            continue
        # Sin diagnostico escrito no se difiere: la lista tiene que costar
        # algo, o se vuelve el lugar donde van a parar los defectos
        # incomodos.
        if fila.get("canonical_agency_id") and fila.get("diagnostico"):
            fuera[fila["canonical_agency_id"]] = fila["diagnostico"]
    return fuera


BANDERA_DE_PARO = "AGENCY_CERTIFICATION_STOP.json"
# Tope duro. Mas de dos procesos contra sitios de inmobiliarias chicas deja de
# ser paralelismo y pasa a ser una molestia para ellas.
WORKERS_MAXIMO = 2
# El latido se refresca CADA MINUTO desde un hilo aparte, mientras la
# inmobiliaria se certifica.
#
# Antes se refrescaba solo al empezar cada una, y ese diseno se calibro cuando
# la corrida mas larga de 74 medidas tardaba 927 s. Con presupuesto de 5.400 s
# por corrida y dos corridas por inmobiliaria, una sola puede tardar tres
# horas: `abriola propiedades` llevaba una hora y catorce minutos con el
# proceso VIVO y su cerrojo ya figuraba vencido.
#
# Eso no es un problema de reporte. `tomar_cerrojo` usa el mismo umbral, asi
# que un segundo runner habria dado por muerto a un worker vivo y tomado su
# particion: dos procesos pidiendole a los mismos sitios al doble del ritmo
# acordado y escribiendo el mismo checkpoint, que es exactamente lo que el
# cerrojo existe para impedir.
LATIDO_VENCIDO = 3600.0
INTERVALO_DE_LATIDO = 60.0


def latir(ruta: Path, canonical_id: str | None) -> None:
    ruta.write_text(json.dumps({
        "pid": os.getpid(),
        "heartbeat": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "heartbeat_epoch": time.time(),
        "current_agency": canonical_id,
    }, ensure_ascii=False), encoding="utf-8")


def particion(cola: list[str], catalogo: dict[str, dict[str, Any]],
              worker: int, workers: int) -> list[str]:
    """Reparte la cola por HOST, no por agencia.

    Por host y no por posicion por una razon concreta: la cortesia se le debe
    al sitio, y el limitador vive dentro de cada proceso. Si dos workers
    pudieran tocar el mismo host, le estariamos pidiendo al doble del ritmo que
    acordamos, sin que ninguno de los dos se entere.

    Sobre las 767 hay 765 hosts distintos y dos hosts con dos agencias cada
    uno: repartir por host mantiene esas cuatro juntas en el mismo worker y
    deja el reparto casi perfectamente parejo igual.

    Es deterministico: la misma cola y el mismo numero de workers dan siempre
    el mismo reparto, asi que reiniciar un worker no le cambia el trabajo.
    """
    if workers <= 1:
        return cola
    mias = []
    for canonical_id in cola:
        anfitrion = host_de(catalogo.get(canonical_id) or {}, canonical_id)
        digest = hashlib.sha256(anfitrion.encode("utf-8")).hexdigest()
        if int(digest, 16) % workers == worker:
            mias.append(canonical_id)
    return mias


def host_de(entrada: dict[str, Any], canonical_id: str) -> str:
    """El host de la fuente, o el id como sustituto si no se puede leer."""
    try:
        url = resolve_identity(entrada, canonical_id).get("official_url")
    except Exception:  # noqa: BLE001 - repartir nunca puede tumbar la cola
        url = None
    anfitrion = urllib.parse.urlparse(url or "").netloc.lower()
    return anfitrion.removeprefix("www.") or canonical_id


def pedir_paro(output: Path, canonical_id: str, triage: dict[str, Any]) -> None:
    """Deja escrito que hay que parar, para el worker que todavia no se entero."""
    write_json(output / BANDERA_DE_PARO, {
        "canonical_agency_id": canonical_id,
        "componente": triage.get("componente_sospechoso"),
        "radio": triage.get("radio_estimado"),
        "evidencia": triage.get("evidencia"),
        "cuando": time.strftime("%Y-%m-%dT%H:%M:%S")})


def hay_que_parar(output: Path) -> dict[str, Any] | None:
    ruta = output / BANDERA_DE_PARO
    if not ruta.exists():
        return None
    try:
        return json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"canonical_agency_id": "desconocida"}


def sufijado(nombre: str, worker: int, workers: int) -> str:
    """El mismo nombre de archivo cuando hay un worker; uno propio si hay dos.

    Con un solo worker no cambia nada, asi que las corridas viejas y sus
    artefactos siguen siendo los mismos archivos.
    """
    if workers <= 1:
        return nombre
    raiz, punto, extension = nombre.partition(".")
    return f"{raiz}.w{worker}{punto}{extension}"


class Latido:
    """Mantiene vivo el cerrojo mientras dura el trabajo.

    Un hilo aparte y no un `latir()` adentro del certificador: el certificador
    no sabe que hay un cerrojo, y ensenarselo lo ataria a como se orquesta la
    cola. Con un hilo, la unica coordinacion es "empeza" y "para".
    """

    def __init__(self, ruta: Path, canonical_id: str) -> None:
        self.ruta = ruta
        self.canonical_id = canonical_id
        self._parar = threading.Event()
        self._hilo = threading.Thread(target=self._latir, daemon=True)

    def _latir(self) -> None:
        while not self._parar.wait(INTERVALO_DE_LATIDO):
            try:
                latir(self.ruta, self.canonical_id)
            except OSError:
                # Un fallo al escribir el latido no puede tumbar la corrida:
                # el cerrojo vencido se detecta solo y el trabajo sigue.
                pass

    def __enter__(self) -> "Latido":
        latir(self.ruta, self.canonical_id)
        self._hilo.start()
        return self

    def __exit__(self, *_) -> None:
        self._parar.set()
        self._hilo.join(timeout=INTERVALO_DE_LATIDO)


def tomar_cerrojo(output: Path, worker: int = 0, workers: int = 1) -> Path:
    """Impide dos runners sobre el mismo checkpoint.

    Dos procesos escribiendo el mismo progreso se pisan el cursor y le vuelven
    a pedir a las mismas fuentes el mismo inventario: rompe la recuperabilidad
    y golpea sitios ajenos al doble del ritmo que acordamos con ellos.
    """
    ruta = output / sufijado(CERROJO, worker, workers)
    if ruta.exists():
        try:
            previo = json.loads(ruta.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            previo = {}
        edad = time.time() - float(previo.get("heartbeat_epoch") or 0)
        if edad < LATIDO_VENCIDO:
            raise SystemExit(
                f"Ya hay un runner activo (pid {previo.get('pid')}, ultimo "
                f"latido hace {edad:.0f}s, en {previo.get('current_agency')}). "
                f"Si comprobaste que murio, borra {ruta}.")
    latir(ruta, None)
    return ruta


def runner_error(output: Path, canonical_id: str,
                 error: BaseException) -> dict[str, Any]:
    """Convierte un fallo del runner en un resultado NO terminal.

    Un crash no dice nada sobre la inmobiliaria: no prueba que no publique, ni
    que su sitio este roto. Guardarlo como estado terminal convertiria un
    problema nuestro en un hecho sobre la fuente, que es exactamente la clase
    de dato que despues no se distingue de uno real. Al quedar fuera de
    TERMINAL, la fuente vuelve sola a la cola en la proxima corrida.
    """
    detalle = {"canonical_agency_id": canonical_id, "status": "RUNNER_ERROR",
               "reasons": [f"{type(error).__name__}: {error}"],
               "traceback": traceback.format_exc(),
               "checked_at": time.strftime("%Y-%m-%dT%H:%M:%S")}
    append_jsonl(output / "AGENCY_RUNNER_ERRORS.jsonl", detalle)
    return {clave: valor for clave, valor in detalle.items()
            if clave != "traceback"}


def queue_fingerprint(queue: list[str], mode: str) -> str:
    payload = json.dumps({"mode": mode, "queue": queue},
                         ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def fingerprint_inventory() -> dict[str, dict[str, str]]:
    connectors = {
        name: version_del_codigo(name)
        for name in ("century21", "generico", "tokko", "wasi", "wordpress")
    }
    strategies = {
        strategy: strategy_fingerprint("generico", strategy)
        for strategy in sorted(GENERIC_STRATEGY_METHODS)
    }
    strategies.update({
        name: strategy_fingerprint(name, name)
        for name in ("century21", "tokko", "wasi", "wordpress")
    })
    return {"connector_fingerprints": connectors,
            "strategy_fingerprints": strategies}


def progress_payload(*, mode: str, universe: int, queue: list[str],
                     pending: list[str], current_count: int,
                     started_at: str, global_cursor: int = 0,
                     last_terminal_agency: str | None = None,
                     current_agency: str | None = None,
                     current_phase: str = "READY") -> dict[str, Any]:
    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    return {
        "checkpoint_schema_version": 2,
        "mode": mode,
        "universe": universe,
        "queue_size": len(queue),
        "queue_fingerprint": queue_fingerprint(queue, mode),
        "global_cursor": global_cursor,
        "last_terminal_agency": last_terminal_agency,
        "next_agency": pending[0] if pending else None,
        "pending_count": len(pending),
        "remaining": len(pending),
        "certified_count": current_count,
        "started_at": started_at,
        "last_heartbeat": now,
        "updated_at": now,
        "current_agency": current_agency,
        "current_phase": current_phase,
        **fingerprint_inventory(),
    }


def is_current_result(previous: dict[str, Any],
                      record: dict[str, dict[str, Any]]) -> bool:
    """Decide si un cierre persistido sigue vigente.

    ``IDENTITY_PENDING`` y los bloqueos resueltos antes de elegir conector no
    tienen ``connector_version`` por diseño: dependen del certificador de
    identidad, no del parser de propiedades. Exigirles una huella inexistente
    hacía que cada reanudación repitiera miles de cierres terminales. Los
    resultados que sí usaron un conector mantienen la comparación estricta de
    fingerprint.
    """
    status = previous.get("status")
    if status not in TERMINAL:
        return False
    if status == "IDENTITY_PENDING" or (
            status == "BLOCKED_EXTERNAL" and not previous.get("connector_version")):
        return previous.get("certifier_version") == CERTIFIER_VERSION
    connector = previous.get("connector") or choose_connector(record)
    if previous.get("strategy_fingerprint"):
        strategy = previous.get("connector_strategy") or strategy_for(
            connector, previous.get("publication_mechanism"))
        return previous.get("strategy_fingerprint") == strategy_fingerprint(
            connector, strategy)
    return previous.get("connector_version") == version_del_codigo(connector)


def inventory(record: dict[str, dict[str, Any]]) -> int:
    platform = record["platform"]
    values = [platform.get("declared_inventory"), platform.get("enumerated_inventory"),
              platform.get("properties_normalized")]
    return max([int(x) for x in values if isinstance(x, (int, float))] or [0])


def bucket(record: dict[str, dict[str, Any]]) -> str:
    amount = inventory(record)
    if amount <= 11:
        return "low"
    if amount <= 100:
        return "medium"
    return "large"


def pilot_queue(catalog: dict[str, dict[str, Any]], limit: int) -> list[str]:
    groups: dict[tuple[str, str], list[str]] = defaultdict(list)
    for canonical_id in sorted(catalog):
        identity = resolve_identity(catalog[canonical_id], canonical_id)
        if identity["identity_status"] != "READY":
            continue
        groups[(choose_connector(catalog[canonical_id]), bucket(catalog[canonical_id]))].append(canonical_id)
    # Intercala plataforma y tamano; no toma las mas grandes primero porque el
    # objetivo del piloto es descubrir clases de fallo, no maximizar filas.
    selected: list[str] = []
    keys = sorted(groups)
    while len(selected) < limit and any(groups.values()):
        for key in keys:
            if groups[key] and len(selected) < limit:
                selected.append(groups[key].pop(0))
    return selected


def ready_queue(catalog: dict[str, dict[str, Any]]) -> list[str]:
    """Solo las fuentes cuya identidad ya resuelve a una inmobiliaria real.

    Certificar una fuente cuya identidad no resuelve gasta dos corridas en vivo
    contra un sitio de terceros para producir inventario que despues no se
    puede asociar a ninguna fila de `main`. Sobre el universo actual son 753
    de 6.597: el resto espera a que se decida que hacer con las inmobiliarias
    descubiertas y todavia no promovidas.
    """
    return [canonical_id for canonical_id in sorted(catalog)
            if resolve_identity(catalog[canonical_id],
                                canonical_id)["identity_status"] == "READY"]


def full_queue(catalog: dict[str, dict[str, Any]]) -> list[str]:
    return sorted(catalog)


# Cuantas inmobiliarias por familia se certifican ANTES del bulk. Con una sola
# no se distingue un defecto de familia de una fuente rara; con muchas se paga
# el canario como si fuera el bulk.
CANARIOS_POR_FAMILIA = 3

# Lo que ya se sabe que tarda o que nos rechaza. No se saca del universo: se
# corre al final, para que no bloquee a las 700 que si avanzan.
SENALES_DE_COLA_LARGA = ("BLOCKED_EXTERNAL",)


def _familia(resultado: dict[str, Any]) -> str:
    return (resultado.get("connector_strategy")
            or resultado.get("connector") or "sin familia")


def _es_cola_larga(resultado: dict[str, Any]) -> bool:
    """Fuentes lentas, inaccesibles, o que rechazan el acceso.

    La inaccesible cuesta MAS que una que funciona: `varelanegociosinmobiliarios`
    consume dos corridas de cien segundos cada una agotando reintentos para no
    traer nada, y en el canario se llevo doce minutos por delante de las
    agencias que si tenian algo que decir sobre el codigo.

    Que no responda hoy no la saca del universo: la vuelve a intentar al final,
    que es donde no le hace perder tiempo a nadie.
    """
    if resultado.get("status") in SENALES_DE_COLA_LARGA:
        return True
    corridas = [c or {} for c in (resultado.get("run1"), resultado.get("run2"))]
    if any(c.get("presupuesto_agotado") for c in corridas):
        return True
    inaccesibles = [c for c in corridas
                    if c.get("estado") in ("ERROR_DISCOVERY", "ERROR_LISTADO")]
    return len(inaccesibles) == len(corridas) and bool(corridas)


def ordenar_para_correr(cola: list[str],
                        resultados: dict[str, dict[str, Any]]) -> list[str]:
    """Canarios, bulk, long tail. El universo NO cambia: cambia el orden.

    Procesar por orden alfabetico deja que un defecto de familia aparezca en
    el dia tres. `alta`, `alma di matteo` y `altos servicios` fueron tres
    paradas seguidas de la misma clase de problema -catalogos que no se
    enumeraban- y cada una costo una ventana entera.

    Con canarios, una familia rota se descubre en la primera hora, se arregla
    una vez, y el bulk corre sobre codigo ya validado en esa familia. Es la
    diferencia entre pagar una recertificacion y pagarla por cada agencia que
    ya habia pasado.

    La cola larga va al final por la misma razon al reves: un sitio que nos
    rechaza o que agota el presupuesto no aporta informacion nueva sobre el
    codigo, y adelante frena a las que si.
    """
    canarios: list[str] = []
    bulk: list[str] = []
    larga: list[str] = []
    vistos_por_familia: Counter = Counter()

    conocidos = [c for c in cola if c in resultados]
    for canonical_id in conocidos:
        resultado = resultados[canonical_id]
        if _es_cola_larga(resultado):
            larga.append(canonical_id)
            continue
        familia = _familia(resultado)
        if vistos_por_familia[familia] < CANARIOS_POR_FAMILIA:
            vistos_por_familia[familia] += 1
            canarios.append(canonical_id)
        else:
            bulk.append(canonical_id)

    # Las que nunca se certificaron no tienen familia conocida todavia: van al
    # bulk, que es donde se descubre.
    bulk.extend(c for c in cola if c not in resultados)
    return canarios + bulk + larga


def latest_results(output: Path) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for row in read_jsonl(output / "AGENCY_CERTIFICATION_RESULTS.jsonl"):
        latest[row["canonical_agency_id"]] = row
    return latest


def render_summary(output: Path, universe: int, latest: dict[str, dict[str, Any]],
                   mode: str, stopped_on: str | None) -> None:
    counts = Counter(row["status"] for row in latest.values())
    lines = [
        "# AGENCY CERTIFICATION SUMMARY", "",
        f"- Updated: {time.strftime('%Y-%m-%dT%H:%M:%S')}",
        f"- Mode: {mode}", f"- Canonical universe: {universe:,}",
        f"- Agencies attempted: {len(latest):,}",
        f"- Agencies not started: {universe - len(latest):,}",
        f"- Stopped on: {stopped_on or 'none'}", "", "## Status", "",
    ]
    lines += [f"- {status}: {count:,}" for status, count in sorted(counts.items())]
    lines += ["", "This report certifies read-only evidence only. It does not authorize a canary or write.", ""]
    (output / "AGENCY_CERTIFICATION_SUMMARY.md").write_text("\n".join(lines), encoding="utf-8")



def senales_en_la_portada(url: str | None) -> list[str]:
    """Baja la portada una vez y busca estructura de catalogo.

    Una sola peticion, y solo cuando el connector no reconocio la forma del
    sitio. Si no se puede leer se devuelve vacio: no poder mirar no es haber
    mirado y no haber encontrado nada, y el triage ya trata la ausencia de
    senales como motivo para NO detener, asi que un fallo de red no puede
    fabricar una parada.
    """
    if not url:
        return []
    try:
        with urllib.request.urlopen(urllib.request.Request(
                url, headers={"User-Agent": "Mozilla/5.0 (compatible; ERETZ/1.0)"}),
                timeout=25) as respuesta:
            html = respuesta.read(400_000).decode("utf-8", "replace")
    except Exception:  # noqa: BLE001 - no poder mirar no decide nada
        return []
    return senales_de_catalogo(html)


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--pilot", type=int, metavar="N")
    mode.add_argument("--full", action="store_true")
    mode.add_argument("--ready", action="store_true",
                      help="solo inmobiliarias con identidad resuelta")
    parser.add_argument("--v2-dir", default=r"D:\INMO CAPITAL\ERETZ_SUPABASE_RECONCILIATION_V2_20260827")
    parser.add_argument("--data-dir", default=r"D:\INMO CAPITAL\ERETZ_AGENCY_DATA")
    parser.add_argument("--platform-directory", default=r"D:\INMO CAPITAL\agency_platform_directory.jsonl")
    # La vigente la declara `ERETZ_DATA_MANIFEST.json`, no una ruta escrita a
    # mano: una ruta a mano envejece en silencio, que es exactamente como este
    # runner termino apuntando a la snapshot del 27 de agosto.
    parser.add_argument("--preingestion-db", default=str(base_canonica()))
    parser.add_argument("--output", default=r"D:\INMO CAPITAL\ERETZ_AGENCY_CERTIFICATION_20260827")
    parser.add_argument("--interval", type=float, default=1.5)
    # El default sale del modulo, no de un numero repetido aca: tenerlo en dos
    # lugares hizo que subir el presupuesto no tuviera ningun efecto, porque el
    # CLI seguia pasando el viejo.
    parser.add_argument("--budget", type=float,
                        default=PRESUPUESTO_POR_FUENTE)
    parser.add_argument("--max-listings", type=int, default=0)
    parser.add_argument("--continue-after-fix", action="store_true")
    parser.add_argument("--worker", type=int, default=0,
                        help="cual de los workers es este (0..N-1)")
    parser.add_argument("--workers", type=int, default=1,
                        help=f"cuantos workers en paralelo (maximo {WORKERS_MAXIMO})")
    parser.add_argument("--limit", type=int, default=0,
                        help="cuantas inmobiliarias procesar en esta corrida "
                             "(0 = hasta agotar la cola)")
    args = parser.parse_args()
    if not 1 <= args.workers <= WORKERS_MAXIMO:
        raise SystemExit(
            f"--workers tiene que estar entre 1 y {WORKERS_MAXIMO}: mas procesos "
            f"contra sitios de inmobiliarias chicas dejan de ser paralelismo.")
    if not 0 <= args.worker < args.workers:
        raise SystemExit(f"--worker tiene que estar entre 0 y {args.workers - 1}")
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    catalog = load_catalog(Path(args.v2_dir), Path(args.data_dir),
                           Path(args.platform_directory))
    if args.pilot:
        queue, mode_name = pilot_queue(catalog, args.pilot), f"pilot-{args.pilot}"
    elif args.ready:
        queue, mode_name = ready_queue(catalog), "ready"
    else:
        queue, mode_name = full_queue(catalog), "full"
    existing = latest_results(output)
    if not args.pilot:
        # El universo no cambia; cambia el orden. Ver `ordenar_para_correr`.
        queue = ordenar_para_correr(queue, existing)
    # La cola COMPLETA se conserva para el checkpoint y el resumen: repartir no
    # puede cambiar de que universo se esta hablando.
    cola_completa = queue
    if args.workers > 1:
        queue = particion(queue, catalog, args.worker, args.workers)
        mode_name = f"{mode_name}-w{args.worker}de{args.workers}"
        print(f"### worker {args.worker} de {args.workers}: "
              f"{len(queue)} de {len(cola_completa)} inmobiliarias ###",
              flush=True)
    def current(key: str) -> bool:
        return is_current_result(existing.get(key, {}), catalog[key])

    stale = [key for key in queue if key in existing and not current(key)
             and existing[key].get("status") in TERMINAL]
    for key in stale:
        append_jsonl(output / "AGENCY_MASTER_PROGRESS.jsonl", {
            "canonical_agency_id": key, "status": "RECERTIFICATION_REQUIRED",
            "reason": "connector code fingerprint changed",
            "mode": mode_name, "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S")})
    pending = [key for key in queue if not current(key)]
    if args.limit > 0:
        pending = pending[:args.limit]
    progress_path = output / sufijado("AGENCY_CERTIFICATION_PROGRESS.json",
                                     args.worker, args.workers)
    previous_progress: dict[str, Any] = {}
    if progress_path.exists():
        try:
            previous_progress = json.loads(progress_path.read_text(encoding="utf-8"))
        except ValueError:
            previous_progress = {}
    current_queue_fingerprint = queue_fingerprint(queue, mode_name)
    same_queue = previous_progress.get("queue_fingerprint") == current_queue_fingerprint
    started_at = (previous_progress.get("started_at") if same_queue else None)
    started_at = started_at or time.strftime("%Y-%m-%dT%H:%M:%S")
    last_terminal = (previous_progress.get("last_terminal_agency")
                     if same_queue else None)
    global_cursor = int(previous_progress.get("global_cursor") or 0) if same_queue else 0
    write_json(progress_path, progress_payload(
        mode=mode_name, universe=len(catalog), queue=queue, pending=pending,
        current_count=sum(current(key) for key in queue),
        started_at=started_at, global_cursor=global_cursor,
        last_terminal_agency=last_terminal))
    cerrojo = tomar_cerrojo(output, args.worker, args.workers)
    # Una bandera de una corrida anterior no puede frenar la siguiente: si
    # quedo puesta, el defecto ya se atendio o el preflight lo habria visto.
    (output / BANDERA_DE_PARO).unlink(missing_ok=True)
    stopped_on: str | None = None
    defectos_pendientes: list[dict[str, Any]] = []
    pospuestos = diferidos(output)
    for index, canonical_id in enumerate(pending, 1):
        # Un defecto transversal lo es para los dos workers. Se mira ANTES de
        # empezar la siguiente, que es el unico momento en que parar no
        # desperdicia una corrida a medias.
        ajeno = hay_que_parar(output) if args.workers > 1 else None
        if ajeno:
            stopped_on = ajeno.get("canonical_agency_id")
            print(json.dumps({"para_por_otro_worker": stopped_on,
                              "componente": ajeno.get("componente"),
                              "radio": ajeno.get("radio")},
                             ensure_ascii=False), flush=True)
            break
        write_json(progress_path, progress_payload(
            mode=mode_name, universe=len(catalog), queue=queue,
            pending=pending[index - 1:],
            current_count=sum(current(key) for key in queue),
            started_at=started_at, global_cursor=global_cursor,
            last_terminal_agency=last_terminal,
            current_agency=canonical_id, current_phase="CERTIFY"))
        try:
            with Latido(cerrojo, canonical_id):
                result = certify(canonical_id, catalog, output,
                                 Path(args.preingestion_db), args.interval,
                                 args.max_listings, args.budget)
        except KeyboardInterrupt:
            raise
        except Exception as error:  # noqa: BLE001 - una fuente no tumba la cola
            result = runner_error(output, canonical_id, error)
        update_rollups(output, result)
        # El registro de que se vio y cuando. Sin esto el ciclo de vida no se
        # puede activar nunca: el checkpoint y el paquete guardan la ultima
        # corrida y se sobrescriben, asi que cada pasada borraba la evidencia
        # de la anterior.
        registrar_observacion(
            output / "agencies" / hashlib.sha256(
                canonical_id.encode()).hexdigest()[:16],
            result, output)
        append_jsonl(output / "AGENCY_MASTER_PROGRESS.jsonl", {
            "canonical_agency_id": canonical_id, "status": result["status"],
            "mode": mode_name, "position": index, "queue_size": len(queue),
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S")})
        existing[canonical_id] = result
        terminal = result["status"] in TERMINAL
        if terminal:
            last_terminal = canonical_id
            global_cursor = queue.index(canonical_id) + 1
        remaining_pending = [key for key in pending[index:] if not current(key)]
        phase = ("STOPPED_NEEDS_FIX" if result["status"] == "NEEDS_FIX"
                 else "READY")
        if phase == "STOPPED_NEEDS_FIX":
            remaining_pending.insert(0, canonical_id)
        checkpoint = progress_payload(
            mode=mode_name, universe=len(catalog), queue=queue,
            pending=remaining_pending,
            current_count=sum(current(key) for key in queue),
            started_at=started_at, global_cursor=global_cursor,
            last_terminal_agency=last_terminal,
            current_agency=(canonical_id if phase != "READY" else None),
            current_phase=phase)
        triage = None
        if result["status"] in {"NEEDS_FIX", "RUNNER_ERROR"}:
            # Parar en cada defecto cuesta semanas de cola detenida; seguir
            # siempre certifica agencias con un defecto conocido encima. Lo que
            # decide es el RADIO: un parser roto que comparten 343 agencias no
            # puede seguir corriendo, y un sitio que anduvo lento media hora no
            # justifica detener 758.
            # "No reconoci la forma del sitio" no es "el sitio no tiene
            # inventario". Antes de clasificar se mira la portada: si publica
            # estructura de catalogo, lo que esta en juego son propiedades
            # reales que no estamos leyendo. `alta.com.ar` tenia 16 detras de
            # un /buscador y `almadimatteo.com.ar` 28 en paginas de categoria.
            if any((result.get(r) or {}).get("estado") == "VARIANTE_NO_SOPORTADA"
                   for r in ("run1", "run2")):
                result["senales_de_catalogo"] = senales_en_la_portada(
                    result.get("official_url"))
            triage = clasificar(result)
            triage.update({"position": index, "queue_size": len(queue),
                           "epoch": time.time()})
            # Un defecto que ya tuvo su tanda de diagnostico y se posterga a
            # conciencia se sigue anotando, pero no vuelve a hacer saltar el
            # corte por lote cada doce horas. Solo aplica a los que el triage
            # dejo en CONTINUE: un radio transversal para igual.
            postergado = pospuestos.get(canonical_id)
            if postergado and triage["decision"] != STOP:
                triage["diferido_por"] = postergado
            else:
                defectos_pendientes.append(triage)
            append_jsonl(output / "AGENCY_DEFECT_QUEUE.jsonl", {
                **triage,
                "reasons": result.get("reasons", []),
                "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S")})
        checkpoint.update({"attempted_in_this_run": index,
                           "last_agency": canonical_id,
                           "last_status": result["status"]})
        write_json(progress_path, checkpoint)
        print(json.dumps({"position": index, "total": len(pending),
                          "agency": canonical_id, "status": result["status"]}), flush=True)
        if triage is not None and not args.continue_after_fix:
            corta, motivo_lote = debe_cortar_por_lote(defectos_pendientes)
            if triage["decision"] == STOP:
                stopped_on = canonical_id
                # El otro worker no puede enterarse solo: un defecto
                # transversal lo es para los dos, y si sigue certificando con
                # el codigo sospechado hay que rehacer su trabajo igual.
                if args.workers > 1:
                    pedir_paro(output, canonical_id, triage)
                print(json.dumps({
                    "detiene": canonical_id,
                    "motivo": "radio transversal",
                    "componente": triage["componente_sospechoso"],
                    "radio": triage["radio_estimado"],
                    "evidencia": triage["evidencia"]}, ensure_ascii=False),
                    flush=True)
                break
            if corta:
                # El defecto era continuable, pero el lote acumulado ya no.
                # Se corta ACA, que es un checkpoint recien escrito.
                stopped_on = canonical_id
                if args.workers > 1:
                    pedir_paro(output, canonical_id,
                               {"componente_sospechoso": "corte por lote",
                                "radio_estimado": triage["radio_estimado"],
                                "evidencia": motivo_lote})
                print(json.dumps({"detiene": canonical_id,
                                  "motivo": "corte por lote",
                                  "detalle": motivo_lote},
                                 ensure_ascii=False), flush=True)
                break
            print(json.dumps({
                "continua_pese_a": canonical_id,
                "radio": triage["radio_estimado"],
                "componente": triage["componente_sospechoso"],
                "pendientes": len(defectos_pendientes)}, ensure_ascii=False),
                flush=True)
    render_summary(output, len(catalog), existing, mode_name, stopped_on)
    cerrojo.unlink(missing_ok=True)
    return 2 if stopped_on else 0


if __name__ == "__main__":
    raise SystemExit(main())
