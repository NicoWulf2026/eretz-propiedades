#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Descubrir la web de las agencias SIN web con busqueda paga (Brave), con tope de gasto y compuertas.

Mision 08-10: de 12.483 entidades del registro, 3.476 canonicas no tienen web; sin web no hay nada que
scrapear. El usuario aprobo el gasto de busqueda (08-10, "Yes all") con la condicion de medir primero un piloto
y proyectar el total antes de seguir.

- Resolutor: `canario_brave_50_v2.resolver`, el MISMO medido en el A/B (no se copia: copiar fue como se colo el
  defecto del TTL). Primero prueba gratis los dominios derivados del nombre; paga solo si hace falta (max 3).
- Antes de afirmar, las compuertas del circuito: `dominio_propio` (el host es de la agencia), `es_argentina`,
  un solo reclamante del host. Solo eso entra a AGENCY_OFFICIAL_WEB_VERIFIED.jsonl (con `--aplicar`).
- Tope duro de gasto (`--tope-usd`); se corta antes de pasarlo. No guarda payload del proveedor.
- Registro de cada agencia en ERETZ_AGENCY_DATA/BRAVE_DESCUBRIMIENTO.jsonl (lo hecho no se vuelve a pagar).

    python scripts/descubrir_webs_brave.py --limite 100 --tope-usd 3          # piloto, sin aplicar
    python scripts/descubrir_webs_brave.py --limite 100 --tope-usd 3 --aplicar
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path

sys.path[:0] = [str(Path(__file__).resolve().parents[1]), str(Path(__file__).resolve().parent)]
from scripts import canario_brave_50_v2 as canario, search_provider as sp  # noqa: E402
from scripts.rutas_de_datos import dato  # noqa: E402
from promover_webs_verificadas import es_argentina  # noqa: E402
from verificar_webs_del_directorio import DESTINO, dominio_propio, host_de, reclamantes_por_host  # noqa: E402

DATOS = dato("ERETZ_AGENCY_DATA")
PADRON = DATOS / "roomix_agency_directory.jsonl"
REGISTRO = DATOS / "BRAVE_DESCUBRIMIENTO.jsonl"
USD_POR_CONSULTA = canario.USD_POR_MIL / 1000


def _jsonl(ruta: Path):
    if ruta.exists():
        for linea in ruta.read_text(encoding="utf-8", errors="replace").splitlines():
            if linea.strip():
                try:
                    yield json.loads(linea)
                except ValueError:
                    continue


def cohorte(limite: int) -> list[dict]:
    """Las SIN_WEB del registro que nunca se buscaron, por avisos observados (impacto) y repartidas por zona."""
    registro = {r["canonical_agency_id"]: r for r in _jsonl(dato("ERETZ_REGISTRO", "REGISTRO_INMOBILIARIAS.jsonl"))
                if r.get("origen") == "CANONICO"}
    hechas = {r.get("canonical_agency_id") for r in _jsonl(REGISTRO)}
    padron = {f["stable_id"]: f for f in _jsonl(PADRON) if f.get("stable_id")}
    # Las oficinas de una red (RE/MAX, Century 21...) no se buscan: su pagina vive dentro del sitio de la
    # red y la encuentra gratis el conector de la red.
    filas = [padron[c] for c, r in registro.items()
             if r["estado"] == "SIN_WEB" and c in padron and c not in hechas
             and not padron[c].get("red_franquicia")]
    filas.sort(key=lambda f: -(f.get("avisos_observados") or 0))
    por_zona: Counter = Counter()
    elegidas = []
    tope_zona = max(5, limite // 10)
    for f in filas:
        zona = ((f.get("zonas_observadas") or ["?"])[0] or "?").lower()
        if por_zona[zona] >= tope_zona:
            continue
        por_zona[zona] += 1
        elegidas.append(f)
        if len(elegidas) >= limite:
            break
    return elegidas


def aplicar_registradas(excluir: set[str]) -> int:
    """Escribe en DESTINO las AFIRMABLE ya registradas (revisadas a mano), sin volver a pagar busquedas."""
    ya = {f.get("canonical_agency_id") for f in _jsonl(DESTINO) if f.get("estado_del_resolver")}
    padron = {f["stable_id"]: f for f in _jsonl(PADRON) if f.get("stable_id")}
    n = 0
    with DESTINO.open("a", encoding="utf-8") as dest:
        for r in _jsonl(REGISTRO):
            cid = r.get("canonical_agency_id")
            if not r.get("afirmable") or cid in ya or cid in excluir:
                continue
            dest.write(json.dumps({
                "canonical_agency_id": cid, "nombre": (padron.get(cid) or {}).get("nombre_original"),
                "estado": "AFIRMABLE", "razon": r.get("razon"), "official_url": r["url"],
                "origen_descubierto": r["url"], "url_descubierta": r["url"], "era_ruta_profunda": False,
                "entidades_que_reclaman_el_host": 1, "estado_del_resolver": "OFFICIAL_WEB_VERIFIED",
                "identity_score": r.get("confianza"), "verificacion": r.get("verificacion"),
                "verificacion_razon": "es_argentina", "origen_del_dato": "descubrir_webs_brave",
                "cuando": r.get("cuando"), "database_writes": 0}, ensure_ascii=False) + "\n")
            ya.add(cid)
            n += 1
    print(json.dumps({"aplicadas": n, "excluidas_a_mano": sorted(excluir)}, ensure_ascii=False))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--aplicar-registradas", action="store_true",
                    help="aplicar las AFIRMABLE ya registradas (sin buscar ni pagar)")
    ap.add_argument("--excluir", action="append", default=[], help="canonical_agency_id a no aplicar")
    ap.add_argument("--limite", type=int, default=100)
    ap.add_argument("--tope-usd", type=float, default=0.0)
    ap.add_argument("--pausa", type=float, default=0.4)
    ap.add_argument("--aplicar", action="store_true")
    args = ap.parse_args()
    if args.aplicar_registradas:
        return aplicar_registradas(set(args.excluir))
    sp.cargar_env_local()
    buscador = sp.Brave()
    if not buscador.disponible():
        print("BRAVE_NO_DISPONIBLE (sin credencial en el entorno)")
        return 1
    elegidas = cohorte(args.limite)
    hosts = reclamantes_por_host()
    print(f"### DESCUBRIR WEBS (Brave) ### {len(elegidas)} agencias, tope USD {args.tope_usd}", flush=True)
    consultas = 0
    estados: Counter = Counter()
    with REGISTRO.open("a", encoding="utf-8") as reg, DESTINO.open("a", encoding="utf-8") as dest:
        for i, fila in enumerate(elegidas, 1):
            if (consultas + canario.CONSULTAS_MAXIMAS) * USD_POR_CONSULTA > args.tope_usd:
                print(f"   tope de gasto alcanzado en {i - 1}/{len(elegidas)}", flush=True)
                break
            cid = fila["stable_id"]
            try:
                r = canario.resolver(fila, buscador, args.pausa)
            except RuntimeError as e:
                print(f"   proveedor detenido en {i}/{len(elegidas)}: {type(e).__name__}", flush=True)
                break
            consultas += r["consultas"]
            ver = r["v"]
            url = getattr(ver, "url", None)
            estado, pais, razon = ver.clase, None, getattr(ver, "razon", None)
            afirmable = False
            if url and ver.clase == canario.v2.OFFICIAL_WEB:
                propio, razon_propio = dominio_propio(cid, url)
                n_host = len(hosts.get(host_de(url), set()) | {cid})
                if not propio:
                    estado, razon = "HOST_NO_PROPIO", razon_propio
                elif n_host != 1:
                    estado = "HOST_COMPARTIDO"
                else:
                    pais, _r = es_argentina(url)
                    afirmable = pais == "VERIFICADA_ARGENTINA"
                    if not afirmable:
                        estado = f"PAIS:{pais}"
            estados["AFIRMABLE" if afirmable else estado] += 1
            fila_reg = {"canonical_agency_id": cid, "estado": estado, "url": url, "via": r["via"],
                        "consultas": r["consultas"], "confianza": getattr(ver, "confianza", None),
                        "razon": razon, "verificacion": pais, "afirmable": afirmable,
                        "cuando": time.strftime("%Y-%m-%dT%H:%M:%S"), "database_writes": 0}
            reg.write(json.dumps(fila_reg, ensure_ascii=False) + "\n")
            reg.flush()
            if afirmable:
                hosts[host_de(url)].add(cid)
                if args.aplicar:
                    dest.write(json.dumps({
                        "canonical_agency_id": cid, "nombre": fila.get("nombre_original"), "estado": "AFIRMABLE",
                        "razon": razon, "official_url": url, "origen_descubierto": url, "url_descubierta": url,
                        "era_ruta_profunda": False, "entidades_que_reclaman_el_host": 1,
                        "estado_del_resolver": "OFFICIAL_WEB_VERIFIED", "identity_score": getattr(ver, "confianza", None),
                        "verificacion": pais, "verificacion_razon": "es_argentina",
                        "origen_del_dato": "descubrir_webs_brave", "cuando": fila_reg["cuando"],
                        "database_writes": 0}, ensure_ascii=False) + "\n")
                    dest.flush()
            if i % 10 == 0:
                print(f"  {i}/{len(elegidas)} consultas={consultas} usd={consultas * USD_POR_CONSULTA:.2f} "
                      f"{dict(estados)}", flush=True)
    print(json.dumps({"agencias": sum(estados.values()), "estados": dict(estados), "consultas_pagas": consultas,
                      "usd": round(consultas * USD_POR_CONSULTA, 2), "aplicado": args.aplicar},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
