#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Normaliza publicadores de Roomix, los clasifica y los cruza contra ERETZ.

Entradas (directorio de datos, fuera del repo):
  observations.jsonl   apariciones {url, agent_id, agent_name}
  eretz_agencies.jsonl universo ERETZ {slug, name, location, listings}

Salidas:
  publishers.jsonl     publicadores unicos, normalizados y clasificados
  crosswalk.jsonl      un registro por publicador con su estado de match
  report.json          conteos agregados

No escribe en ninguna base. Ver docs/ROOMIX_AGENCY_ACQUISITION_PLAN_V1.md.
"""
from __future__ import annotations

import argparse
import html as _html
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from difflib import SequenceMatcher
from pathlib import Path

MATCHING_VERSION = "v1"

# --------------------------------------------------------------- normalizacion
# Sufijos societarios y de rubro que no aportan identidad y estorban al matching.
NOISE = [
    "sociedad anonima", "sa de cv", " srl", " s r l", " s a ", " sas", " s a s",
    "negocios inmobiliarios", "servicios inmobiliarios", "grupo inmobiliario",
    "estudio inmobiliario", "consultora inmobiliaria", "bienes raices",
    "real estate", "propiedades", "inmobiliaria", "inmobiliarias",
    "desarrollos", "desarrolladora", "constructora", "emprendimientos",
]

def strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def norm_name(raw: str) -> str:
    """Clave conservadora para comparar. NUNCA reemplaza al raw.

    Los nombres de ERETZ llegan con entidades HTML sin decodificar
    (`D&#x27;onofrio`); sin decodificarlas el apostrofo se convertia en tokens
    `x27` y partia el match. Tambien se quitan calificadores entre parentesis y
    sufijos societarios finales, que no cambian la identidad.
    """
    s = _html.unescape(raw or "")
    s = re.sub(r"\([^)]*\)", " ", s)
    s = strip_accents(s.lower())
    s = s.replace("&", " y ")
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    s = re.sub(r"\s+(sa|srl|sas|sh|scs)$", "", s)
    return s


def norm_core(raw: str) -> str:
    """Nucleo del nombre: quita sufijos de rubro. Solo para comparar."""
    s = " " + norm_name(raw) + " "
    for n in NOISE:
        s = s.replace(" " + n.strip() + " ", " ")
    return re.sub(r"\s+", " ", s).strip()


# ------------------------------------------------------------- clasificacion
FRANCHISES = ["re/max", "remax", "century 21", "century21", "keller williams",
              "coldwell banker", "engel", "volkers", "bairesprop", "tsg"]
DEV_HINTS = ["desarrollos", "desarrolladora", "constructora", "emprendimientos",
             "grupo constructor", "obras"]
OWNER_HINTS = ["dueno directo", "dueño directo", "particular", "propietario",
               "sin inmobiliaria", "owner"]
AGENCY_HINTS = ["inmobiliaria", "propiedades", "real estate", "bienes raices",
                "negocios inmobiliarios", "servicios inmobiliarios", "broker",
                "realty", "estudio inmobiliario", "consultora inmobiliaria"]

# Basura que no debe convertirse nunca en inmobiliaria.
GARBAGE_EXACT = {"", "-", "n/a", "na", "null", "none", "undefined", "usuario",
                 "user", "particular", "dueno directo", "dueño directo",
                 "sin datos", "test", "prueba", "admin", "sin nombre"}
PORTAL_NAMES = {"roomix", "zonaprop", "argenprop", "mercadolibre", "meli",
                "properati", "inmoup", "clasificados"}


def classify(raw: str) -> str:
    n = norm_name(raw)
    if not n or len(n) < 3:
        return "UNKNOWN"
    # "Dueno directo" es un TIPO real de publicador, no basura: se clasifica
    # antes de descartar, para poder contarlo.
    if any(h in n for h in (norm_name(x) for x in OWNER_HINTS)):
        return "DUENO_DIRECTO"
    if n in GARBAGE_EXACT:
        return "UNKNOWN"
    if n in PORTAL_NAMES or any(p == n for p in PORTAL_NAMES):
        return "OTRO"
    # Las listas se normalizan con la misma funcion que el nombre: comparar
    # "re/max" contra un texto ya normalizado a "re max" no coincide nunca.
    if any(f in n for f in (norm_name(x) for x in FRANCHISES) if f):
        return "RED_FRANQUICIA"
    if any(x in n for x in (norm_name(y) for y in DEV_HINTS) if x):
        return "DESARROLLADORA"
    if any(x in n for x in (norm_name(y) for y in AGENCY_HINTS) if x):
        return "INMOBILIARIA"
    # Nombre de persona: dos o tres palabras sin marcador de rubro.
    words = n.split()
    if 2 <= len(words) <= 3 and all(w.isalpha() for w in words):
        return "AGENTE"
    return "INMOBILIARIA" if len(words) >= 2 else "UNKNOWN"


def is_garbage(raw: str) -> tuple[bool, str]:
    n = norm_name(raw)
    if n in GARBAGE_EXACT:
        return True, "placeholder"
    if len(n) < 3:
        return True, "demasiado_corto"
    if len(raw) > 120:
        return True, "demasiado_largo"
    if "<" in raw and ">" in raw:
        return True, "html"
    if n in PORTAL_NAMES:
        return True, "nombre_de_portal"
    if re.fullmatch(r"[\d\s\-_.]+", n or "x"):
        return True, "solo_numeros"
    return False, ""


# ------------------------------------------------------------------- matching
def build_index(eretz: list[dict]) -> dict:
    by_name: dict[str, list[dict]] = defaultdict(list)
    by_core: dict[str, list[dict]] = defaultdict(list)
    for e in eretz:
        if not e.get("name"):
            continue
        by_name[norm_name(e["name"])].append(e)
        by_core[norm_core(e["name"])].append(e)
    for e in eretz:
        e["_norm"] = norm_name(e.get("name") or "")
        e["_toks"] = set(e["_norm"].split())
    return {"by_name": by_name, "by_core": by_core, "all": eretz}


def near_neighbour(n: str, eretz: list[dict], floor: float = 0.72):
    """Vecino mas parecido en ERETZ. Un candidato con vecino cercano no puede
    declararse nuevo: queda AMBIGUOUS para revision, nunca se auto-fusiona."""
    toks = set(n.split())
    best, score = None, 0.0
    for e in eretz:
        en = e.get("_norm") or ""
        if not en:
            continue
        et = e["_toks"]
        ov = len(toks & et) / max(1, len(toks | et))
        if ov < 0.34:
            continue
        sc = 0.5 * ov + 0.5 * SequenceMatcher(None, n, en).ratio()
        if sc > score:
            best, score = e, sc
    return (best, score) if score >= floor else (None, score)


def match(pub: dict, idx: dict) -> tuple[str, list[dict], str]:
    """Devuelve (estado, candidatos, senal usada)."""
    raw = pub["raw_name"]
    n, c = norm_name(raw), norm_core(raw)

    exact = idx["by_name"].get(n, [])
    if len(exact) == 1:
        return "EXACT_EXISTING", exact, "nombre_normalizado_exacto"
    if len(exact) > 1:
        return "AMBIGUOUS", exact, "nombre_exacto_multiple"

    core = [e for e in idx["by_core"].get(c, []) if c]
    if len(core) == 1 and len(c) >= 6:
        return "HIGH_CONFIDENCE_EXISTING", core, "nucleo_de_nombre"
    if len(core) > 1:
        return "AMBIGUOUS", core, "nucleo_multiple"

    # Nucleo demasiado generico para decidir por nombre solo.
    if len(c) < 6:
        return "INSUFFICIENT_DATA", [], "nucleo_corto"

    nb, sc = near_neighbour(n, idx["all"])
    if nb is not None:
        return "AMBIGUOUS", [nb], "vecino_cercano_%.2f" % sc

    return "NEW_HIGH_CONFIDENCE", [], "sin_coincidencia"


# ---------------------------------------------------------------------- main
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default=r"D:\INMO CAPITAL\ERETZ_AGENCY_DATA")
    a = ap.parse_args()
    d = Path(a.data_dir)

    freq: Counter = Counter()
    names: dict[str, str] = {}
    urls: dict[str, str] = {}
    obs_total = 0
    for line in (d / "observations.jsonl").open(encoding="utf-8"):
        try:
            o = json.loads(line)
        except Exception:
            continue
        obs_total += 1
        aid = o.get("agent_id")
        if not aid:
            continue
        freq[aid] += 1
        names.setdefault(aid, o.get("agent_name") or "")
        urls.setdefault(aid, o.get("url") or "")

    eretz = []
    ep = d / "eretz_agencies.jsonl"
    if ep.exists():
        for line in ep.open(encoding="utf-8"):
            try:
                eretz.append(json.loads(line))
            except Exception:
                pass
    idx = build_index(eretz)

    pubs, cross = [], []
    kinds, states, garbage = Counter(), Counter(), Counter()
    for aid, n in freq.most_common():
        raw = names[aid]
        bad, why = is_garbage(raw)
        kind = "GARBAGE" if bad else classify(raw)
        rec = {"agent_id": aid, "raw_name": raw, "norm": norm_name(raw),
               "core": norm_core(raw), "listings_observed": n, "type": kind,
               "evidence_url": urls[aid]}
        if bad:
            rec["garbage_reason"] = why
            garbage[why] += 1
        pubs.append(rec)
        kinds[kind] += 1

        if kind != "INMOBILIARIA":
            continue
        state, cands, signal = match(rec, idx)
        states[state] += 1
        cross.append({**rec, "match_state": state, "match_signal": signal,
                      "candidates": [{"slug": c["slug"], "name": c["name"],
                                      "location": c.get("location"),
                                      "listings": c.get("listings")} for c in cands[:4]],
                      "matching_version": MATCHING_VERSION,
                      "discovered_via": "roomix_public_property_page"})

    (d / "publishers.jsonl").write_text(
        "\n".join(json.dumps(p, ensure_ascii=False) for p in pubs), encoding="utf-8")
    (d / "crosswalk.jsonl").write_text(
        "\n".join(json.dumps(c, ensure_ascii=False) for c in cross), encoding="utf-8")

    report = {"observaciones": obs_total, "con_publicador": sum(freq.values()),
              "publicadores_unicos": len(freq), "eretz_universo": len(eretz),
              "tipos": dict(kinds), "estados_match": dict(states),
              "basura": dict(garbage)}
    (d / "report.json").write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8")

    print("### PUBLICADORES ###", flush=True)
    print("  observaciones: %d | con publicador: %d | unicos: %d"
          % (obs_total, sum(freq.values()), len(freq)), flush=True)
    for k, v in kinds.most_common():
        print("  %-18s %5d" % (k, v), flush=True)
    if garbage:
        print("  basura rechazada: %s" % dict(garbage), flush=True)
    print("\n### CRUCE CON ERETZ (universo ERETZ: %d) ###" % len(eretz), flush=True)
    for k, v in states.most_common():
        print("  %-26s %5d" % (k, v), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
