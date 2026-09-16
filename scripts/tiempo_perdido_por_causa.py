#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Cuántas horas costó cada causa, no cuántos paros hubo. §68, §30, §51.

Sólo lectura sobre artefactos locales. `database_writes: 0`.

Contar paros trata igual a un paro de seis minutos y a uno de catorce horas.
El §68 pide lo otro: **horas perdidas por causa**, para que la ventana
semántica se ordene por lo que realmente cuesta y no por lo que más se repite.

Cómo se mide cada episodio
--------------------------
Un paro empieza cuando la certificación de una agencia cierra con un defecto de
radio transversal, y termina cuando alguien lo diagnostica, lo difiere firmado
y relanza. Los dos extremos están fechados en artefactos distintos:

    inicio  = `checked_at` del último resultado de esa agencia antes de la firma
    fin     = `cuando` de la diferida

Es una cota **superior** por unos minutos: entre que se escribe el resultado y
se levanta la bandera pasa un momento. Medido contra el único episodio con
registro independiente —`david rodriguez`, 2026-09-16—, la diferencia fue de
2,5 minutos sobre 32: sobreestima ~8%. Se informa así en vez de inventar una
precisión que no tenemos.

Sólo cuentan los radios que **paran la cola**. Una diferida de radio AGENCIA o
ESTRATEGIA no detiene a nadie: el worker escribe `continua_pese_a` y sigue. Que
esté en el mismo archivo no la convierte en tiempo perdido.

Atribución de causa
-------------------
El §30 prohíbe decidir desde texto humano, y el nombre que pone el triage
—`posible_perdida_de_inventario`— es un **síntoma**, no una causa: lo comparten
un portal ajeno, un sitio con navegación en JavaScript y una API de terceros,
que son tres arreglos distintos. Así que la causa no se lee de mi prosa: se
resuelve uniendo la agencia contra evidencia estructurada.

    1. ¿su fuente es un portal ajeno?      `es_portal_url()` sobre la URL
    2. ¿tiene firma técnica medida?        `ERETZ_FIRMA_NAVEGACION_JS.jsonl`
    3. si no                               queda el síntoma, sin atribuir

Lo que queda sin atribuir se informa como tal. Un cajón llamado "otros" que
concentra la mitad de las horas es un resultado, no un defecto del informe.

Uso:
    python scripts/tiempo_perdido_por_causa.py
    python scripts/tiempo_perdido_por_causa.py --json
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from collections import defaultdict
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "scripts"))

import verificador_identidad_v2 as v2  # noqa: E402

CERT = Path(r"D:\INMO CAPITAL\ERETZ_AGENCY_CERTIFICATION_20260827")
DIFERIDAS = CERT / "AGENCY_DEFECTS_DIFERIDOS.jsonl"
RESULTADOS = CERT / "AGENCY_CERTIFICATION_RESULTS.jsonl"
FIRMAS = CERT / "ERETZ_FIRMA_NAVEGACION_JS.jsonl"
SALIDA = CERT / "ERETZ_TIEMPO_PERDIDO_POR_CAUSA.json"

# Los únicos radios que detienen a los dos workers. El resto se anota y sigue.
RADIOS_QUE_PARAN = {"FAMILIA", "COMPARTIDO"}

# Un episodio más largo que esto no es un paro: es la cola apagada, una
# diferida escrita tarde, o las dos cosas. Contarlo como tiempo perdido por esa
# causa le atribuiría horas que no le corresponden.
TOPE_HORAS_CREIBLE = 36.0


def _epoch(iso: str | None) -> float | None:
    if not iso:
        return None
    try:
        return time.mktime(time.strptime(str(iso)[:19], "%Y-%m-%dT%H:%M:%S"))
    except (ValueError, TypeError):
        return None


def _jsonl(ruta: Path):
    if not ruta.exists():
        return
    for linea in ruta.open(encoding="utf-8", errors="replace"):
        linea = linea.strip()
        if not linea:
            continue
        try:
            yield json.loads(linea)
        except ValueError:
            continue


def observaciones_por_agencia() -> dict[str, list[tuple[float, dict]]]:
    """Todas las corridas fechadas de cada agencia, en orden."""
    por_agencia: dict[str, list[tuple[float, dict]]] = defaultdict(list)
    for fila in _jsonl(RESULTADOS):
        agencia = fila.get("canonical_agency_id")
        cuando = _epoch(fila.get("checked_at"))
        if agencia and cuando:
            por_agencia[agencia].append((cuando, fila))
    for lista in por_agencia.values():
        lista.sort(key=lambda par: par[0])
    return por_agencia


def firmas_medidas() -> dict[str, str]:
    return {f["agency_id"]: f["firma"] for f in _jsonl(FIRMAS)
            if f.get("agency_id") and f.get("firma")}


def causa_de(resultado: dict | None, firma: str | None,
             sintoma: str) -> tuple[str, str]:
    """Devuelve (causa, como_se_supo). Nunca lee prosa: sólo campos."""
    url = (resultado or {}).get("official_url") or ""
    if url.startswith("http") and v2.es_portal_url(url):
        return ("FUENTE_ES_PORTAL_AJENO", "es_portal_url() sobre official_url")
    if firma and firma != "FUENTE_ES_PORTAL_AJENO":
        return (firma, "ERETZ_FIRMA_NAVEGACION_JS.jsonl")
    if firma == "FUENTE_ES_PORTAL_AJENO":
        return ("FUENTE_ES_PORTAL_AJENO", "ERETZ_FIRMA_NAVEGACION_JS.jsonl")
    return (f"SIN_ATRIBUIR:{sintoma}", "no hay evidencia estructurada todavia")


def episodios() -> tuple[list[dict], list[dict]]:
    """Los paros medibles y los que se descartaron, con su motivo."""
    observaciones = observaciones_por_agencia()
    firmas = firmas_medidas()
    medidos, descartados = [], []

    for diferida in _jsonl(DIFERIDAS):
        agencia = diferida.get("canonical_agency_id")
        radio = diferida.get("radio")
        sintoma = diferida.get("componente") or "sin_determinar"
        fin = _epoch(diferida.get("cuando"))
        if not agencia or radio not in RADIOS_QUE_PARAN:
            descartados.append({"agency_id": agencia, "radio": radio,
                                "motivo": "el radio no detiene la cola"})
            continue
        if fin is None:
            descartados.append({"agency_id": agencia, "radio": radio,
                                "motivo": "la diferida no tiene fecha"})
            continue
        previas = [(t, r) for t, r in observaciones.get(agencia, []) if t <= fin]
        if not previas:
            descartados.append({"agency_id": agencia, "radio": radio,
                                "motivo": "no hay corrida fechada anterior a "
                                          "la firma"})
            continue
        inicio, resultado = previas[-1]
        horas = (fin - inicio) / 3600.0
        causa, como = causa_de(resultado, firmas.get(agencia), sintoma)
        registro = {"agency_id": agencia, "sintoma": sintoma, "radio": radio,
                    "causa": causa, "causa_se_supo_por": como,
                    "inicio": time.strftime("%Y-%m-%dT%H:%M:%S",
                                            time.localtime(inicio)),
                    "fin": diferida.get("cuando"), "horas": round(horas, 2)}
        if horas <= 0 or horas > TOPE_HORAS_CREIBLE:
            registro["motivo"] = (f"{horas:.1f} h no es un paro creible "
                                  f"(tope {TOPE_HORAS_CREIBLE} h)")
            descartados.append(registro)
            continue
        medidos.append(registro)
    return medidos, descartados


def resumir(medidos: list[dict]) -> list[dict]:
    por_causa: dict[str, list[dict]] = defaultdict(list)
    for e in medidos:
        por_causa[e["causa"]].append(e)
    filas = []
    for causa, lista in por_causa.items():
        horas = sorted(e["horas"] for e in lista)
        filas.append({
            "CAUSE": causa,
            "INCIDENTS": len(lista),
            "TOTAL_LOST_HOURS": round(sum(horas), 1),
            "MEDIAN_LOST_HOURS": round(statistics.median(horas), 2),
            "MAX_LOST_HOURS": round(max(horas), 2),
            "agencias": sorted({e["agency_id"].split(":")[-1] for e in lista}),
            "sintomas": sorted({e["sintoma"] for e in lista}),
        })
    filas.sort(key=lambda f: f["TOTAL_LOST_HOURS"], reverse=True)
    return filas


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    medidos, descartados = episodios()
    filas = resumir(medidos)
    total = round(sum(f["TOTAL_LOST_HOURS"] for f in filas), 1)
    ventana = ""
    if medidos:
        ventana = f"{min(e['inicio'] for e in medidos)[:10]} a " \
                  f"{max(e['fin'] for e in medidos)[:10]}"

    reporte = {"generado_en": time.strftime("%Y-%m-%dT%H:%M:%S"),
               "ventana": ventana,
               "episodios_medidos": len(medidos),
               "episodios_descartados": len(descartados),
               "horas_perdidas_totales": total,
               "sobreestimacion_conocida": "~8% por alto: el inicio se toma del "
                                           "resultado, no de la bandera",
               "por_causa": filas,
               "descartados": descartados,
               "database_writes": 0}
    SALIDA.write_text(json.dumps(reporte, ensure_ascii=False, indent=1),
                      encoding="utf-8")

    if args.json:
        print(json.dumps(reporte, ensure_ascii=False, indent=1))
        return 0

    print(f"paros medibles: {len(medidos)}   descartados: {len(descartados)}")
    print(f"ventana: {ventana}")
    print(f"horas de cola parada: {total}\n")
    print(f"  {'CAUSA':38} {'N':>3} {'TOTAL':>7} {'MEDIANA':>8} {'MAX':>7}")
    print(f"  {'-' * 38} {'-' * 3} {'-' * 7} {'-' * 8} {'-' * 7}")
    for f in filas:
        print(f"  {f['CAUSE'][:38]:38} {f['INCIDENTS']:3} "
              f"{f['TOTAL_LOST_HOURS']:7.1f} {f['MEDIAN_LOST_HOURS']:8.2f} "
              f"{f['MAX_LOST_HOURS']:7.2f}")
    if filas:
        peor = filas[0]
        print(f"\n  La causa mas cara es {peor['CAUSE']}: {peor['INCIDENTS']} "
              f"paros y {peor['TOTAL_LOST_HOURS']} h.")
        print(f"  Agencias: {', '.join(peor['agencias'][:8])}")
    print(f"\nartefacto: {SALIDA}")
    print("\ndatabase_writes: 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
