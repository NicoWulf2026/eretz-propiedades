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
import time
import traceback
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

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
# El latido se refresca al terminar cada inmobiliaria. Sobre 74 corridas
# medidas, la mas larga tardo 927 s, asi que un latido de mas de una hora
# significa que ese proceso ya no esta: es cuatro veces el peor caso observado,
# no un numero elegido de la nada.
LATIDO_VENCIDO = 3600.0


def latir(ruta: Path, canonical_id: str | None) -> None:
    ruta.write_text(json.dumps({
        "pid": os.getpid(),
        "heartbeat": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "heartbeat_epoch": time.time(),
        "current_agency": canonical_id,
    }, ensure_ascii=False), encoding="utf-8")


def tomar_cerrojo(output: Path) -> Path:
    """Impide dos runners sobre el mismo checkpoint.

    Dos procesos escribiendo el mismo progreso se pisan el cursor y le vuelven
    a pedir a las mismas fuentes el mismo inventario: rompe la recuperabilidad
    y golpea sitios ajenos al doble del ritmo que acordamos con ellos.
    """
    ruta = output / CERROJO
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
    parser.add_argument("--preingestion-db", default=r"D:\INMO CAPITAL\ERETZ_SUPABASE_RECONCILIATION_V2_20260827\PREINGESTION_REBUILD.sqlite3")
    parser.add_argument("--output", default=r"D:\INMO CAPITAL\ERETZ_AGENCY_CERTIFICATION_20260827")
    parser.add_argument("--interval", type=float, default=1.5)
    parser.add_argument("--budget", type=float, default=1800.0)
    parser.add_argument("--max-listings", type=int, default=0)
    parser.add_argument("--continue-after-fix", action="store_true")
    parser.add_argument("--limit", type=int, default=0,
                        help="cuantas inmobiliarias procesar en esta corrida "
                             "(0 = hasta agotar la cola)")
    args = parser.parse_args()
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
    progress_path = output / "AGENCY_CERTIFICATION_PROGRESS.json"
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
    cerrojo = tomar_cerrojo(output)
    stopped_on: str | None = None
    for index, canonical_id in enumerate(pending, 1):
        latir(cerrojo, canonical_id)
        write_json(progress_path, progress_payload(
            mode=mode_name, universe=len(catalog), queue=queue,
            pending=pending[index - 1:],
            current_count=sum(current(key) for key in queue),
            started_at=started_at, global_cursor=global_cursor,
            last_terminal_agency=last_terminal,
            current_agency=canonical_id, current_phase="CERTIFY"))
        try:
            result = certify(canonical_id, catalog, output,
                             Path(args.preingestion_db), args.interval,
                             args.max_listings, args.budget)
        except KeyboardInterrupt:
            raise
        except Exception as error:  # noqa: BLE001 - una fuente no tumba la cola
            result = runner_error(output, canonical_id, error)
        update_rollups(output, result)
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
        if result["status"] in {"NEEDS_FIX", "RUNNER_ERROR"}:
            # Cola de triage: con --continue-after-fix los defectos dejaban de
            # detener la corrida y tambien dejaban de ser visibles.
            append_jsonl(output / "AGENCY_DEFECT_QUEUE.jsonl", {
                "canonical_agency_id": canonical_id,
                "status": result["status"],
                "reasons": result.get("reasons", []),
                "position": index, "queue_size": len(queue),
                "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S")})
        checkpoint.update({"attempted_in_this_run": index,
                           "last_agency": canonical_id,
                           "last_status": result["status"]})
        write_json(progress_path, checkpoint)
        print(json.dumps({"position": index, "total": len(pending),
                          "agency": canonical_id, "status": result["status"]}), flush=True)
        if result["status"] == "NEEDS_FIX" and not args.continue_after_fix:
            stopped_on = canonical_id
            break
    render_summary(output, len(catalog), existing, mode_name, stopped_on)
    cerrojo.unlink(missing_ok=True)
    return 2 if stopped_on else 0


if __name__ == "__main__":
    raise SystemExit(main())
