#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Snapshot del universo de inmobiliarias de ERETZ desde el Preview protegido.

Lee el directorio publico paginado del propio producto. No toca la base: es la
via de lectura disponible mientras las credenciales de conexion directa esten
caducadas.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


def bypass_cookie(base: str) -> str:
    fd, tmp = tempfile.mkstemp(prefix="eqa_", suffix=".hdr")
    os.close(fd)
    try:
        subprocess.run(
            ["vercel.cmd", "curl", base + "/api/properties/counts?x-vercel-set-bypass-cookie=true",
             "-i", "--yes"],
            stdout=open(tmp, "wb"), stderr=subprocess.DEVNULL, timeout=180)
        raw = Path(tmp).read_bytes().decode("utf-8", "ignore")
        m = re.search(r"(?i)set-cookie:\s*_vercel_jwt=([^;\r\n]+)", raw)
        if not m:
            raise RuntimeError("no se pudo obtener la cookie de bypass")
        return m.group(1)
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass


CARD = re.compile(
    r'href="/inmobiliaria/([a-z0-9-]{2,110})"[^>]*>(.*?)</a>', re.S)
NAME = re.compile(r'class="entity-name"[^>]*>([^<]{2,120})<')
META = re.compile(r'class="entity-meta"[^>]*>([^<]{1,120})<')
COUNT = re.compile(r'class="entity-count"[^>]*>([^<]{1,60})<')


def parse_page(html: str) -> list[dict]:
    out = []
    for slug, blob in CARD.findall(html):
        name = NAME.search(blob)
        meta = META.search(blob)
        cnt = COUNT.search(blob)
        n = None
        if cnt:
            digits = re.sub(r"[^\d]", "", cnt.group(1))
            n = int(digits) if digits else None
        out.append({
            "slug": slug,
            "name": (name.group(1).strip() if name else None),
            "location": (meta.group(1).strip() if meta else None),
            "listings": n,
        })
    return out


def _flush(seen: dict[str, dict], outp: Path) -> None:
    outp.parent.mkdir(parents=True, exist_ok=True)
    tmp = outp.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        for v in seen.values():
            fh.write(json.dumps(v, ensure_ascii=False) + "\n")
    tmp.replace(outp)


def enumerate_all(base: str, ck: str, outp: Path | None = None) -> dict[str, dict]:
    """El directorio devuelve LIMIT 60 con filtro ILIKE por nombre. Se enumera
    por refinamiento: se consulta un termino y, si devuelve 60 filas (saturado),
    se refina agregando un caracter mas. Asi se cubre el universo sin depender de
    una paginacion que el endpoint no ofrece."""
    import string
    seen: dict[str, dict] = {}
    alphabet = string.ascii_lowercase + string.digits + " "
    pending = [""] + list(string.ascii_lowercase)
    tried: set[str] = set()
    saturated = 0

    while pending:
        q = pending.pop(0)
        if q in tried or len(q) > 3:
            continue
        tried.add(q)
        url = f"{base}/inmobiliarias" + (f"?q={urllib.parse.quote(q)}" if q else "")
        req = urllib.request.Request(url, headers={"Cookie": "_vercel_jwt=" + ck})
        try:
            with urllib.request.urlopen(req, timeout=150) as r:
                html = r.read().decode("utf-8", "ignore")
        except Exception as e:
            print("  q=%-4r error %s" % (q, str(e)[:44]), flush=True)
            continue
        rows = parse_page(html)
        new_rows = [r for r in rows if r["slug"] not in seen]
        for r in rows:
            seen.setdefault(r["slug"], r)
        flag = ""
        if len(rows) >= 60:
            saturated += 1
            flag = " SATURADO -> refina"
            for ch in alphabet:
                nxt = q + ch
                if nxt not in tried:
                    pending.append(nxt)
        print("  q=%-5r filas=%-3d nuevas=%-3d total=%-5d%s" % (q, len(rows), len(new_rows), len(seen), flag), flush=True)
        # Persistir en cada vuelta: una interrupcion no debe perder el avance.
        if outp is not None and new_rows:
            _flush(seen, outp)
        time.sleep(0.25)
    print("  consultas: %d | saturadas: %d" % (len(tried), saturated), flush=True)
    return seen


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    ap.add_argument("--out", default=r"D:\INMO CAPITAL\ERETZ_AGENCY_DATA\eretz_agencies.jsonl")
    a = ap.parse_args()
    ck = bypass_cookie(a.base)
    outp = Path(a.out)
    seen = enumerate_all(a.base, ck, outp)
    outp.parent.mkdir(parents=True, exist_ok=True)
    with outp.open("w", encoding="utf-8") as fh:
        for v in seen.values():
            fh.write(json.dumps(v, ensure_ascii=False) + "\n")
    print("\ninmobiliarias ERETZ: %d -> %s" % (len(seen), outp), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
