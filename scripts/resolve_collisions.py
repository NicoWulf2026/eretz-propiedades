#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Clasifica las colisiones staging <-> main con el motor de dedupe.

Las 31 filas del manifest salieron de una sola regla: main tiene
`nombre_normalizado` en NULL y su `nombre` en minusculas coincide con el
normalizado de staging. Esa regla alcanza para SOSPECHAR, no para decidir. Aca
se vuelve a mirar cada par con todas las senales disponibles y se separa lo que
se puede resolver de lo que necesita una persona.

Es de solo lectura: produce un manifest clasificado y no toca la base.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


d = _load("eretz_dedupe")

# Traduccion a los nombres que pidio el encargo.
ETIQUETA = {
    d.EXACT: "SAME_ENTITY_HIGH_CONFIDENCE",
    d.HIGH_CONFIDENCE: "SAME_ENTITY_HIGH_CONFIDENCE",
    d.AMBIGUOUS: "AMBIGUOUS",
    d.DISTINCT: "DISTINCT_ENTITY",
    d.INSUFFICIENT: "AMBIGUOUS",
}


def cargar_provenance(data_dir: Path) -> dict[str, dict]:
    """Lo que sabemos del lado de staging por haberlo descubierto nosotros."""
    p = data_dir / "staging_rows.jsonl"
    if not p.exists():
        return {}
    out = {}
    for linea in p.open(encoding="utf-8"):
        if not linea.strip():
            continue
        r = json.loads(linea)
        out[(r.get("nombre_normalizado") or "").lower()] = r
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default=r"D:\INMO CAPITAL\ERETZ_AGENCY_DATA")
    a = ap.parse_args()
    dd = Path(a.data_dir)

    filas = [json.loads(l) for l in
             (dd / "collision_manifest_staging_main.jsonl").open(encoding="utf-8") if l.strip()]
    prov = cargar_provenance(dd)

    izq, der, meta = [], [], {}
    for f in filas:
        sid, mid = f"s{f['staging_id']}", f"m{f['main_id']}"
        pr = prov.get((f.get("staging_normalizado") or "").lower(), {})
        pm = pr.get("metadata_zonaprop") or {}
        izq.append(d.Entidad(
            ident=sid, nombre=f["staging_nombre"], web=pr.get("web"),
            telefono_raw=pr.get("telefono"), ciudad=f.get("staging_ciudad"),
            provincia=f.get("staging_provincia"), fuente="roomix_agency_coverage",
            normalizado_guardado=f.get("staging_normalizado")))
        der.append(d.Entidad(
            ident=mid, nombre=f["main_nombre"], web=f.get("main_web"),
            ciudad=f.get("main_ciudad"), provincia=f.get("main_provincia"),
            fuente=f.get("main_fuente"), normalizado_guardado=None))
        meta[(sid, mid)] = {"fila": f, "prov": pm}

    pares = d.cruzar(izq, der)
    card = d.cardinalidad(pares)

    # Solo interesan los pares que el manifest ya proponia.
    salida, resumen, cardres = [], Counter(), Counter()
    esperados = set(meta)
    for p in pares:
        clave = (p.izquierda.ident, p.derecha.ident)
        if clave not in esperados:
            continue
        c = card[f"{p.izquierda.ident}->{p.derecha.ident}"]
        m = meta[clave]
        f = m["fila"]
        etiqueta = ETIQUETA[p.veredicto.estado]
        # Un par de alta confianza que NO es uno a uno no se puede resolver
        # solo: si dos filas apuntan al mismo destino, elegir una borraria a la
        # otra.
        if etiqueta == "SAME_ENTITY_HIGH_CONFIDENCE" and c != "uno_a_uno":
            etiqueta = "AMBIGUOUS"
        # Cuanta evidencia INDEPENDIENTE del nombre sostiene el par. Importa
        # para elegir la accion: no promover una fila staged es reversible y el
        # nombre alcanza; fusionar o borrar no lo es y el nombre solo no alcanza.
        corrobora = [s for s in p.veredicto.senales
                     if s.split(" ")[0] in ("matricula", "dominio", "email", "telefono")]
        fuerza = "corroborada" if corrobora else "solo_nombre"
        resumen[etiqueta] += 1
        cardres[c] += 1
        salida.append({
            "clasificacion": etiqueta,
            "estado_motor": p.veredicto.estado,
            "cardinalidad": c,
            "fuerza_evidencia": fuerza,
            "resoluble_automaticamente": d.resoluble(p, c) and etiqueta == "SAME_ENTITY_HIGH_CONFIDENCE",
            # Reversible en ambos casos. Nunca se propone borrar ni fusionar:
            # con evidencia de un solo tipo eso no seria justificable.
            "accion_propuesta": ("no_promover_staged_y_vincular"
                                 if etiqueta == "SAME_ENTITY_HIGH_CONFIDENCE" else "revision_humana"),
            "accion_destructiva_habilitada": False,
            "similitud": round(p.veredicto.similitud, 4),
            "senales": p.veredicto.senales,
            "contradicciones": p.veredicto.contras,
            "explicacion": p.veredicto.explicacion,
            "matcher_version": p.veredicto.matcher_version,
            "staging_id": f["staging_id"], "staging_nombre": f["staging_nombre"],
            "staging_normalizado": f.get("staging_normalizado"),
            "staging_ciudad": f.get("staging_ciudad"),
            "staging_provincia": f.get("staging_provincia"),
            "main_id": f["main_id"], "main_nombre": f["main_nombre"],
            "main_ciudad": f.get("main_ciudad"), "main_provincia": f.get("main_provincia"),
            "main_web": f.get("main_web"), "main_fuente": f.get("main_fuente"),
            "roomix_agent_id": m["prov"].get("roomix_agent_id"),
            "listings_observed": m["prov"].get("listings_observed"),
            "evidence_url": m["prov"].get("evidence_url"),
        })

    out = dd / "collision_manifest_classified.jsonl"
    out.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in salida) + "\n",
                   encoding="utf-8")

    print("### CLASIFICACION DE COLISIONES ###", flush=True)
    print(f"  pares en el manifest:   {len(filas)}", flush=True)
    print(f"  pares clasificados:     {len(salida)}", flush=True)
    print(f"  por clasificacion:      {dict(resumen)}", flush=True)
    print(f"  por cardinalidad:       {dict(cardres)}", flush=True)
    print(f"  resolubles solos:       {sum(1 for r in salida if r['resoluble_automaticamente'])}",
          flush=True)
    fz = Counter(r["fuerza_evidencia"] for r in salida)
    print(f"  fuerza de evidencia:    {dict(fz)}", flush=True)
    if fz.get("solo_nombre"):
        print("  NOTA: los pares 'solo_nombre' no tienen senal independiente que los\n"
              "        corrobore. Alcanza para no promover la fila staged, que es\n"
              "        reversible; NO alcanza para fusionar ni borrar.", flush=True)
    print(f"\n  manifest -> {out}", flush=True)

    senales = Counter(s.split(" (")[0] for r in salida for s in r["senales"])
    print(f"\n  senales que decidieron: {dict(senales)}", flush=True)
    contras = Counter(c.split(" (")[0] for r in salida for c in r["contradicciones"])
    print(f"  contradicciones:        {dict(contras) or 'ninguna'}", flush=True)

    dudosos = [r for r in salida if r["clasificacion"] != "SAME_ENTITY_HIGH_CONFIDENCE"]
    if dudosos:
        print("\n  casos que NO se resuelven solos:", flush=True)
        for r in dudosos:
            print(f"    s{r['staging_id']} <-> m{r['main_id']}  {r['clasificacion']:12} "
                  f"{r['explicacion'][:80]}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
