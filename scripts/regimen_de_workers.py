#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Cuantos workers de certificacion conviene correr: 2 o 3, medido (politica P5).

Politica del usuario (29-09): hasta 3, adaptativo. 3 solo si la medicion muestra
que mejora; si empeora bloqueos, estabilidad o throughput neto, se vuelve a 2.
Nunca mas de 3 sin una politica nueva.

Lo que se mide, siempre con los propios artefactos de la cola (sin red):
- throughput: agencias cerradas por HORA ACTIVA (horas con al menos un cierre;
  una cola detenida por un paro no es un regimen lento);
- bloqueos: fraccion de esas agencias con `Bloqueado` (403/429) en alguna
  corrida, o con el ritmo cedido;
- paros: decisiones STOP del triaje por agencia cerrada;
- recursos: memoria y CPU de la maquina al evaluar.

El regimen vigente vive en `ERETZ_WORKERS.json` y lo lee `relanzar_la_cola.py`,
que es el unico que lanza workers. Cada decision queda en
`ERETZ_WORKERS_REGIMEN.jsonl`. No escribe en ninguna base.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
try:  # raiz del estado operativo configurable (ERETZ_DATA_ROOT)
    from scripts.rutas_de_datos import dato  # noqa: E402
except ImportError:  # corrido como `python scripts/x.py`
    from rutas_de_datos import dato  # noqa: E402

SALIDA = Path(str(dato('ERETZ_AGENCY_CERTIFICATION_20260827')))
REGIMEN = "ERETZ_WORKERS.json"
BITACORA = "ERETZ_WORKERS_REGIMEN.jsonl"
MAXIMO = 3

# Cuanto tiene que durar la prueba de 3 antes de juzgarla, y con cuantas agencias.
PRUEBA_HORAS = 6
PRUEBA_AGENCIAS = 30
# Que es "mejorar": 10 % mas por hora activa, sin mas bloqueos ni mas paros.
MEJORA_MINIMA = 1.10
BLOQUEO_TOLERADO = 0.05          # puntos absolutos por encima de la linea base
MEMORIA_MAXIMA = 90.0            # porcentaje de RAM usada
# Una prueba rechazada no se repite enseguida.
REINTENTO_DIAS = 7

FORMATO = "%Y-%m-%dT%H:%M:%S"


def _fecha(texto: Any) -> datetime | None:
    try:
        return datetime.strptime(str(texto)[:19], FORMATO)
    except (TypeError, ValueError):
        return None


def _jsonl(ruta: Path):
    if not ruta.exists():
        return
    for linea in ruta.open(encoding="utf-8", errors="replace"):
        linea = linea.strip()
        if linea:
            try:
                yield json.loads(linea)
            except ValueError:
                continue


def estado(salida: Path) -> dict[str, Any]:
    try:
        dato = json.loads((salida / REGIMEN).read_text(encoding="utf-8"))
        return dato if isinstance(dato, dict) else {}
    except (OSError, ValueError):
        return {}


def _bloqueado(corrida: dict[str, Any]) -> bool:
    errores = corrida.get("errores_por_etapa") or {}
    return bool(corrida.get("ritmo_cedido")) or any("Bloqueado" in str(k) for k in errores)


def medir(salida: Path, desde: datetime, hasta: datetime,
          paquetes: dict[tuple[str, str], dict[str, Any]] | None = None) -> dict[str, Any]:
    """Las metricas de una ventana, desde el ledger, el triaje y los paquetes."""
    cierres = [f for f in _jsonl(salida / "AGENCY_CERTIFICATION_RESULTS.jsonl")
               if (d := _fecha(f.get("checked_at"))) is not None and desde <= d < hasta]
    horas = {str(f.get("checked_at"))[:13] for f in cierres}
    paros = sum(1 for f in _jsonl(salida / "AGENCY_DEFECT_QUEUE.jsonl")
                if f.get("decision") == "STOP"
                and (d := _fecha(f.get("cuando"))) is not None and desde <= d < hasta)
    if paquetes is None:
        paquetes = _paquetes(salida)
    bloqueadas = 0
    for f in cierres:
        cert = paquetes.get((f.get("canonical_agency_id"), str(f.get("checked_at"))[:19]))
        if cert and any(_bloqueado(cert.get(k) or {}) for k in ("run1", "run2")):
            bloqueadas += 1
    n = len(cierres)
    return {"desde": desde.strftime(FORMATO), "hasta": hasta.strftime(FORMATO),
            "agencias": n, "horas_activas": len(horas),
            "por_hora_activa": round(n / len(horas), 2) if horas else 0.0,
            "bloqueo": round(bloqueadas / n, 4) if n else 0.0,
            "paros_por_agencia": round(paros / n, 4) if n else 0.0}


class _Paquetes(dict):
    """Los paquetes por (agencia, checked_at), leidos solo cuando se piden.

    Antes se leian los ~1.150 `certification.json` en cada pasada; en el disco USB (E:) eso
    llevo el plan del relanzador de ~7 s a 282 s. Una ventana solo pide los de sus cierres:
    el paquete vive en `agencies/<sha256(id)[:16]>` (`agency_certifier.py`) y guarda la
    ultima certificacion, asi que solo cuenta si su `checked_at` es el del cierre.
    """

    def __init__(self, salida: Path):
        super().__init__()
        self._salida = salida
        self._leidas: dict[str, dict[str, Any] | None] = {}

    def get(self, clave, defecto=None):
        agencia, cuando = clave
        if not agencia:
            return defecto
        if agencia not in self._leidas:
            archivo = (self._salida / "agencies"
                       / hashlib.sha256(str(agencia).encode()).hexdigest()[:16]
                       / "certification.json")
            try:
                cert = json.loads(archivo.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                cert = None
            self._leidas[agencia] = cert if isinstance(cert, dict) else None
        cert = self._leidas[agencia]
        if cert and (cert.get("canonical_agency_id"),
                     str(cert.get("checked_at"))[:19]) == (agencia, cuando):
            return cert
        return defecto


def _paquetes(salida: Path) -> _Paquetes:
    return _Paquetes(salida)


def recursos() -> dict[str, float]:
    try:
        import psutil
        return {"memoria": psutil.virtual_memory().percent,
                "cpu": psutil.cpu_percent(interval=1.0)}
    except Exception:  # sin psutil no se afirma nada
        return {"memoria": 0.0, "cpu": 0.0}


def decidir(vigente: dict[str, Any], ahora: datetime,
            medir_ventana, recursos_ahora: dict[str, float]) -> dict[str, Any] | None:
    """El regimen nuevo, o None si no cambia. `medir_ventana(desde, hasta)` mide."""
    workers = int(vigente.get("workers") or 2)
    desde = _fecha(vigente.get("desde"))
    if recursos_ahora.get("memoria", 0.0) > MEMORIA_MAXIMA and workers > 2:
        return {"workers": 2, "motivo": f"memoria {recursos_ahora['memoria']:.0f} % > {MEMORIA_MAXIMA:.0f} %",
                "prueba": "rechazada"}
    # El tope que fija el USUARIO manda sobre cualquier medicion: el 2026-10-02
    # pidio no pasar de 2 workers todavia, aunque la prueba de 3 habia salido
    # aprobada. Sin esto, al vencer `rechazada_en` la evaluacion volvia a
    # proponer 3 sola.
    tope = int(vigente.get("tope_usuario") or 0)
    if tope and workers > tope:
        return {"workers": tope, "motivo": f"tope del usuario: {tope}",
                "prueba": "suspendida_por_usuario"}
    if tope and workers >= tope:
        return None
    if workers <= 2:
        rechazada = _fecha(vigente.get("rechazada_en"))
        if rechazada is not None and ahora - rechazada < timedelta(days=REINTENTO_DIAS):
            return None
        base = medir_ventana(ahora - timedelta(hours=24), ahora)
        if base["agencias"] < PRUEBA_AGENCIAS:
            return None  # sin linea base no se puede juzgar la prueba
        return {"workers": 3, "motivo": "prueba de 3 workers contra la linea base de 2",
                "prueba": "en_curso", "linea_base": base}
    if desde is None:
        return None
    if ahora - desde < timedelta(hours=PRUEBA_HORAS) or vigente.get("prueba") != "en_curso":
        return None
    prueba = medir_ventana(desde, ahora)
    if prueba["agencias"] < PRUEBA_AGENCIAS:
        return None
    base = vigente.get("linea_base") or {}
    razones = []
    if prueba["por_hora_activa"] < MEJORA_MINIMA * float(base.get("por_hora_activa") or 0):
        razones.append(f"throughput {prueba['por_hora_activa']} < {MEJORA_MINIMA} x {base.get('por_hora_activa')}")
    if prueba["bloqueo"] > float(base.get("bloqueo") or 0) + BLOQUEO_TOLERADO:
        razones.append(f"bloqueo {prueba['bloqueo']} > {base.get('bloqueo')} + {BLOQUEO_TOLERADO}")
    tope_paros = max(2 * float(base.get("paros_por_agencia") or 0),
                     float(base.get("paros_por_agencia") or 0) + BLOQUEO_TOLERADO)
    if prueba["paros_por_agencia"] > tope_paros:
        razones.append(f"paros {prueba['paros_por_agencia']} > {tope_paros:.4f}")
    if razones:
        return {"workers": 2, "motivo": "; ".join(razones), "prueba": "rechazada",
                "linea_base": base, "medicion": prueba,
                "rechazada_en": ahora.strftime(FORMATO)}
    return {"workers": 3, "motivo": "3 mejora sin mas bloqueos ni paros", "prueba": "aprobada",
            "linea_base": base, "medicion": prueba}


def evaluar(salida: Path = SALIDA, aplicar: bool = False,
            ahora: datetime | None = None) -> dict[str, Any] | None:
    ahora = ahora or datetime.now()
    vigente = estado(salida)
    paquetes = _paquetes(salida)
    nuevo = decidir(vigente, ahora,
                    lambda d, h: medir(salida, d, h, paquetes), recursos())
    if nuevo is None or not aplicar:
        return nuevo
    nuevo["workers"] = max(1, min(MAXIMO, int(vigente.get("tope_usuario") or MAXIMO),
                                  int(nuevo["workers"])))
    if vigente.get("tope_usuario"):
        nuevo["tope_usuario"] = vigente["tope_usuario"]
    if int(nuevo["workers"]) != int(vigente.get("workers") or 2) or nuevo.get("prueba") != vigente.get("prueba"):
        nuevo["desde"] = (ahora.strftime(FORMATO)
                          if int(nuevo["workers"]) != int(vigente.get("workers") or 2)
                          else vigente.get("desde"))
        nuevo["database_writes"] = 0
        (salida / REGIMEN).write_text(json.dumps(nuevo, ensure_ascii=False, indent=1),
                                     encoding="utf-8")
        with (salida / BITACORA).open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"cuando": ahora.strftime(FORMATO), **nuevo},
                                ensure_ascii=False) + "\n")
    return nuevo


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--salida", default=str(SALIDA))
    ap.add_argument("--aplicar", action="store_true")
    args = ap.parse_args()
    salida = Path(args.salida)
    print(json.dumps({"vigente": estado(salida),
                      "ultimas_24h": medir(salida, datetime.now() - timedelta(hours=24), datetime.now()),
                      "decision": evaluar(salida, aplicar=args.aplicar)},
                     ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
