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
from contextlib import contextmanager
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import psutil

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
    current_code_evidence,
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
# Y no alcanza para tapar nada. Hay dos grados de diferimiento, y el segundo
# cuesta mas caro de escribir:
#
#   SIN FIRMA   la entrada trae solo `diagnostico`. Difiere del corte por
#               LOTE y nada mas; un radio transversal para igual. Es el caso
#               de `armanino`, `attaguile` y `andrea gianfelice`.
#
#   CON FIRMA   la entrada trae ademas `componente` y `radio`. Entonces
#               tambien atraviesa el PARO, pero unicamente si el defecto que
#               aparece es EXACTAMENTE ese: mismo componente y mismo radio.
#
# La firma es lo que evita que esto sea un interruptor de apagado. Si una
# agencia diferida vuelve con OTRO componente -o con el mismo y un radio
# mayor- el paro se dispara igual, porque eso ya no es el defecto que alguien
# miro y decidio postergar: es uno nuevo. `--continue-after-fix`, en cambio,
# apaga el corte para cualquier cosa que aparezca, incluida una corrupcion, y
# por eso no sirve para sostener una pasada entera.
DIFERIDOS = "AGENCY_DEFECTS_DIFERIDOS.jsonl"


def _fecha(iso: str | None) -> float | None:
    """ISO-8601 a epoch. `None` si no se puede leer: sin fecha no hay TTL."""
    if not iso:
        return None
    try:
        return time.mktime(time.strptime(str(iso)[:19], "%Y-%m-%dT%H:%M:%S"))
    except (ValueError, TypeError):
        return None


def diferidos(output: Path) -> dict[str, dict[str, str]]:
    """Que agencias tienen su defecto diagnosticado y postergado, y por que."""
    ruta = output / DIFERIDOS
    if not ruta.exists():
        return {}
    # Una agencia puede tener VARIAS entradas, y todas valen.
    #
    # `carlos castano` lo mostro el 2026-09-11: estaba diferida por no leer
    # unos atributos, y despues su sitio entro en obra y aparecio un defecto
    # distinto -colapso de inventario-. Con una sola entrada por agencia la
    # segunda pisaba a la primera, asi que la agencia quedaba cubierta para el
    # defecto nuevo y descubierta para el viejo, sin que nadie lo decidiera.
    #
    # Guardarlas todas no afloja nada: cada firma sigue teniendo que coincidir
    # entera con el defecto que aparece.
    fuera: dict[str, list[dict[str, str]]] = {}
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
            fuera.setdefault(fila["canonical_agency_id"], []).append({
                "diagnostico": fila["diagnostico"],
                "componente": fila.get("componente") or "",
                "radio": fila.get("radio") or "",
                # Sin la fecha, el TTL no puede vencer nunca ni valer nunca.
                "cuando": fila.get("cuando") or "",
            })
    return fuera


def diagnostico_de(postergadas: list[dict[str, str]] | None) -> str:
    """Lo que se anota en el log. Con varias, la ultima escrita."""
    return postergadas[-1]["diagnostico"] if postergadas else ""


def paro_ya_diagnosticado(postergadas: list[dict[str, str]] | None,
                          triage: dict[str, Any]) -> dict[str, str] | None:
    """¿Alguna de las firmas de esta agencia es el paro que aparece?

    Devuelve la entrada que coincide -para poder anotar SU diagnostico y no
    el de otra- o None. Cada firma exige sus dos mitades: sin componente y
    radio no cubre nada, y el paro se respeta.
    """
    for postergado in postergadas or []:
        componente = postergado.get("componente")
        radio = postergado.get("radio")
        if not componente or not radio:
            continue
        if (triage.get("componente_sospechoso") == componente
                and triage.get("radio_estimado") == radio):
            return postergado
    return None


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
    temporal = ruta.with_name(f'{ruta.name}.{os.getpid()}.{threading.get_ident()}.tmp')
    temporal.write_text(json.dumps({
        "pid": os.getpid(),
        "heartbeat": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "heartbeat_epoch": time.time(),
        "current_agency": canonical_id,
    }, ensure_ascii=False), encoding="utf-8")
    os.replace(temporal, ruta)


@contextmanager
def _claim_guard(ruta: Path):
    """Serialize claims with an OS lock that is released even on process death.

    The persistent sidecar is not a lease: its existence never blocks recovery.
    Both first acquisition and stale recovery pass through this same lock.
    """
    with ruta.with_name(ruta.name + '.claim').open('a+b') as guard:
        try:
            if os.name == 'nt':
                import msvcrt
                guard.seek(0)
                msvcrt.locking(guard.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(guard.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise SystemExit('Ya hay un runner activo tomando este checkpoint') from None
        try:
            yield
        finally:
            if os.name == 'nt':
                guard.seek(0)
                msvcrt.locking(guard.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(guard.fileno(), fcntl.LOCK_UN)


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
    with _claim_guard(ruta):
        if ruta.exists():
            try:
                previo = json.loads(ruta.read_text(encoding="utf-8"))
                edad = time.time() - float(previo['heartbeat_epoch'])
                pid = int(previo['pid'])
            except (OSError, ValueError, KeyError, TypeError):
                raise SystemExit(f'Cerrojo ilegible: revisar propietario de {ruta}; no se reemplaza') from None
            if edad < LATIDO_VENCIDO or pid <= 0 or psutil.pid_exists(pid):
                raise SystemExit(
                    f"Ya hay un runner activo (pid {pid}, ultimo "
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


# Cuánto vale una diferida antes de volver a mirar la fuente.
#
# No es eterna, y el motivo tiene nombre: `baron inmobiliaria` pasó de enumerar
# 0 a enumerar 182 sin que tocáramos una línea. Una fuente cambia sola, y una
# diferida permanente convertiría ese cambio en invisible.
TTL_DIFERIDA_HORAS = 72
# Los defectos que, si el diagnóstico envejece mal, publican algo falso. Se
# revisan tres veces más seguido.
TTL_CRITICO_HORAS = 24
FIRMAS_CRITICAS = {
    "inventario_inestable_entre_corridas",
    "posible_perdida_de_inventario",
    "perdida_sistematica_de_inventario",
    "catalogo_declarado_mayor_que_el_enumerado",
    "enumeracion_compartida",
}


def diferida_vigente(previous: dict[str, Any],
                     postergadas: list[dict[str, str]] | None,
                     ahora: float | None = None) -> bool:
    """¿Hay una diferida firmada, sin vencer, para el defecto de ESTE resultado?

    Las tres condiciones se exigen juntas y cada una cubre un riesgo distinto:
    la firma prueba que alguien miró el defecto contra la fuente, el TTL
    impide que ese diagnóstico valga para siempre, y el llamador comprueba
    aparte que la huella no cambió.

    El TTL se mide contra **la última vez que miramos la agencia**, no contra
    la fecha de la firma. La diferencia se midió sobre 24 h de historial real:
    anclado en la firma, una diferida de hace 200 h queda vencida para siempre
    y su agencia vuelve a correrse en cada pasada de la cola. Eran 112
    corridas sobre 20 agencias, 14,6 h de worker, y 108 de esas 112 terminaron
    idénticas -mismo estado, misma huella, mismo enumerado-. Las otras 4
    movieron entre 1 y 4 avisos, que es rotación de catálogo y no un hallazgo.

    Anclado en la última observación, el TTL hace lo que se le pidió: obliga a
    volver a mirar cada 72 h -24 h si la firma es crítica-, una vez por
    ventana en lugar de una vez por pasada. ``previous`` es siempre una
    corrida realmente ejecutada, porque las salteadas no escriben resultado,
    así que su ``checked_at`` es la fecha de la última mirada.
    """
    if not postergadas:
        return False
    ahora = time.time() if ahora is None else ahora
    observada = _fecha(previous.get("checked_at"))
    for postergada in postergadas:
        firma = postergada.get("componente")
        if not firma or not postergada.get("radio"):
            continue
        # Sin fecha no se puede saber si vencio, y una diferida sin fecha no
        # puede valer indefinidamente.
        emitida = _fecha(postergada.get("cuando"))
        if emitida is None:
            continue
        # El ancla es la ultima mirada real. Una fecha futura no se usa:
        # renovaria el TTL sin haber mirado nada.
        ancla = emitida
        if observada is not None and emitida <= observada <= ahora:
            ancla = observada
        tope = (TTL_CRITICO_HORAS if firma in FIRMAS_CRITICAS
                else TTL_DIFERIDA_HORAS)
        if (ahora - ancla) > tope * 3600:
            continue
        return True
    return False


def _sin_barra(url: str | None) -> str:
    """Normaliza lo justo para comparar dos urls: espacios y barra final."""
    return (url or "").strip().rstrip("/")


def is_current_result(previous: dict[str, Any],
                      record: dict[str, dict[str, Any]],
                      postergadas: list[dict[str, str]] | None = None,
                      fuente_de_hoy: str | None = None) -> bool:
    """Decide si un cierre persistido sigue vigente.

    ``IDENTITY_PENDING`` y los bloqueos resueltos antes de elegir conector no
    tienen ``connector_version`` por diseño: dependen del certificador de
    identidad, no del parser de propiedades. Exigirles una huella inexistente
    hacía que cada reanudación repitiera miles de cierres terminales. Los
    resultados que sí usaron un conector mantienen la comparación estricta de
    fingerprint.

    Y desde el 2026-09-15, un ``NEEDS_FIX`` YA DIAGNOSTICADO tambien cuenta
    como vigente mientras su diferida no venza.

    El motivo se midio con replay sobre el historial real de 24 h: 350
    certificaciones, de las cuales 19 fueron trabajo nuevo y 331 repeticiones.
    La politica nueva evita 229 de esas repeticiones -48 agencias- y baja el
    dia de 41,6 h de worker a 22,8. El NEW_WORK_RATIO pasa de 5,4 % a 15,7 %.

    Esas cifras son del replay, no de una estimacion: cada repeticion se
    volvio a juzgar con el estado que el sistema tenia EN ESE MOMENTO, y se
    sumo su duracion medida. Una diferida escrita despues de una corrida no
    podria haberla evitado, y por eso no se cuenta a favor.

    El diseño original era correcto cuando cada paro terminaba en un arreglo:
    reejecutar comprobaba si el arreglo funciono. Bajo el freeze no se arregla
    nada, asi que reejecutar comprueba que nada cambio.

    Esto NO cambia ningun resultado de certificacion: solo evita volver a
    ejecutar trabajo cuyo diagnostico ya esta escrito.
    """
    # Antes que cualquier huella: ¿el resultado salió de la MISMA fuente que
    # usaríamos hoy?
    #
    # Esto faltaba, y no se notó hasta que hizo falta. El 2026-09-16 se movió
    # la fuente de tres agencias de un perfil de portal ajeno a su dominio
    # propio, y el cambio habría quedado **inerte**: `emir elhelou` tiene una
    # diferida vigente y su huella de estrategia no cambió, así que la cola la
    # daba por vigente y la salteaba. El canario habría parecido estar
    # corriendo sin correr nunca.
    #
    # La regla es evidente una vez enunciada: una certificación describe lo que
    # vimos en una url. Si la url es otra, no dice nada sobre la fuente de hoy,
    # por más que el código no haya cambiado.
    anterior = _sin_barra(previous.get("official_url"))
    if anterior and fuente_de_hoy and anterior != _sin_barra(fuente_de_hoy):
        return False

    status = previous.get("status")
    if status == "NEEDS_FIX" and diferida_vigente(previous, postergadas):
        # La huella se comprueba igual, mas abajo: si el codigo cambio, hay que
        # rehacerla aunque el defecto este diagnosticado.
        connector = previous.get("connector")
        firma = previous.get("strategy_fingerprint")
        if connector and firma:
            strategy = previous.get("connector_strategy") or strategy_for(
                connector, previous.get("publication_mechanism"))
            return firma == strategy_fingerprint(connector, strategy)
        return False
    if status not in TERMINAL:
        return False
    if previous.get('fingerprint_backfilled_from_terminal_evidence', False) is not False:
        return False
    if status == "IDENTITY_PENDING" or (
            status == "BLOCKED_EXTERNAL" and not previous.get("connector_version")):
        return previous.get("certifier_version") == CERTIFIER_VERSION
    if status in {'CERTIFIED_COMPLETE', 'CERTIFIED_BEST_AVAILABLE', 'NO_INVENTORY_CONFIRMED'}:
        return current_code_evidence(previous)
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


def is_current_catalog_result(previous: dict[str, Any],
                              record: dict[str, dict[str, Any]],
                              canonical_id: str,
                              postergadas: list[dict[str, str]] | None = None) -> bool:
    """Queue boundary: historical closure must still describe today's identity.

    No network, ID translation or alternate source policy. Identity-only
    closures can remain deferred only while the same classification persists;
    parser closures require a currently executable official identity. A failed
    identity read is not permission to reuse historical success.
    """
    if not isinstance(previous, dict) or previous.get('canonical_agency_id') != canonical_id:
        return False
    status = previous.get('status')
    if not isinstance(status, str):
        return False
    try:
        identity = resolve_identity(record, canonical_id)
        if not isinstance(identity, dict):
            return False
        current_status = identity.get('identity_status')
        identity_only = status == 'IDENTITY_PENDING' or (
            status == 'BLOCKED_EXTERNAL' and not previous.get('connector_version'))
        if identity_only:
            if current_status != status:
                return False
        elif current_status != 'READY':
            return False
        else:
            for url in (previous.get('official_url'), identity.get('official_url')):
                if not isinstance(url, str) or not url.strip():
                    return False
            old_id, current_id = previous.get('eretz_id'), identity.get('eretz_id')
            if (type(old_id) is not int or old_id <= 0 or type(current_id) is not int
                    or current_id <= 0 or old_id != current_id):
                return False
        return is_current_result(previous, record, postergadas, identity.get('official_url'))
    except Exception:
        # Selection is read-only. A malformed catalog or unavailable code
        # invalidates reuse; certify/runner_error will record the actual failure.
        return False


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
    # Las diferidas se leen ANTES de armar la cola, no despues: son parte de
    # decidir que entra, no solo de decidir si un paro detiene.
    diferidas_al_armar = diferidos(output)

    def current(key: str) -> bool:
        # La fuente de hoy se resuelve con la misma precedencia que usa el
        # certificador, llamando a `resolve_identity`: no se reimplementa acá,
        # porque dos copias de una precedencia terminan divergiendo.
        return is_current_catalog_result(existing.get(key, {}), catalog[key], key,
                                         diferidas_al_armar.get(key))

    stale = [key for key in queue if key in existing and not current(key)
             and existing[key].get("status") in TERMINAL]
    for key in stale:
        append_jsonl(output / "AGENCY_MASTER_PROGRESS.jsonl", {
            "canonical_agency_id": key, "status": "RECERTIFICATION_REQUIRED",
            "reason": "certification evidence or current source identity no longer matches",
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
            # corte cada doce horas. Un paro transversal solo se atraviesa si
            # la entrada diferida trae la firma del defecto y coincide.
            postergadas = pospuestos.get(canonical_id)
            coincide = paro_ya_diagnosticado(postergadas, triage)
            if postergadas and (triage["decision"] != STOP or coincide):
                # El diagnostico que se anota es el de la firma que coincidio;
                # si no coincidio ninguna -defecto continuable- alcanza con el
                # ultimo escrito.
                triage["diferido_por"] = (coincide or {}).get(
                    "diagnostico") or diagnostico_de(postergadas)
                if coincide:
                    triage["paro_diferido"] = True
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
            if triage.get("paro_diferido"):
                # El paro es el que ya se miro y se posterga. Se anota entero
                # -la agencia igual cierra NEEDS_FIX y el defecto queda en la
                # cola- pero no detiene a nadie.
                print(json.dumps({
                    "paro_diferido": canonical_id,
                    "componente": triage["componente_sospechoso"],
                    "radio": triage["radio_estimado"],
                    "diagnostico": triage["diferido_por"]},
                    ensure_ascii=False), flush=True)
            elif triage["decision"] == STOP:
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
