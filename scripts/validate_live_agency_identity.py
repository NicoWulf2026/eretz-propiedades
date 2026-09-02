#!/usr/bin/env python
"""Validate canonical agency mappings against a SELECT-only live snapshot.

Rows are streamed through stdin by the orchestration layer so this script has
no credentials and cannot contact or modify Supabase itself.
"""
from __future__ import annotations

import argparse
import ctypes
import json
import os
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit


def disable_console_echo() -> None:
    if os.name != "nt" or not sys.stdin.isatty():
        return
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.GetStdHandle(-10)
    mode = ctypes.c_uint()
    if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
        kernel32.SetConsoleMode(handle, mode.value & ~0x0004)


def norm(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or "").lower())
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def host(value: object) -> str:
    raw = str(value or "").strip()
    if raw and "://" not in raw:
        raw = "https://" + raw
    try:
        return (urlsplit(raw).hostname or "").lower().removeprefix("www.")
    except ValueError:
        return ""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    disable_console_echo()
    manifest = {}
    with Path(args.manifest).open(encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            if row.get("resolution_status") == "RESOLVED":
                manifest[int(row["eretz_id"])] = row
    live = {}
    for line in sys.stdin:
        if not line.strip():
            continue
        payload = json.loads(line)
        if payload.get("_end"):
            break
        for row in payload.get("rows", []):
            live[int(row["id"])] = row
    counts: Counter[str] = Counter()
    output = Path(args.output)
    with output.open("w", encoding="utf-8") as handle:
        for ident, canonical in sorted(manifest.items()):
            row = live.get(ident)
            name_exact = bool(row and norm(row.get("nombre")) == norm(canonical.get("agency_name")))
            official_host = host(canonical.get("official_domain"))
            live_host = host(row.get("web") if row else None)
            domain_match = bool(official_host and live_host and official_host == live_host)
            status = "VALIDATED" if name_exact else "CONTRADICTION"
            counts[status] += 1
            evidence = {
                "canonical_agency_id": canonical["canonical_agency_id"],
                "eretz_id": ident,
                "validation_status": status,
                "signals": {
                    "live_row_exists": row is not None,
                    "normalized_name_exact": name_exact,
                    "official_domain_matches_live_web": domain_match,
                    "live_city_present": bool(row and row.get("ciudad")),
                    "live_province_present": bool(row and row.get("provincia")),
                    "live_phone_present": bool(row and row.get("phone_present")),
                    "live_email_present": bool(row and row.get("email_present")),
                },
            }
            handle.write(json.dumps(evidence, ensure_ascii=False, sort_keys=True) + "\n")
    missing = set(live) - set(manifest)
    if missing:
        raise RuntimeError(f"received {len(missing)} unexpected live agency rows")
    print(json.dumps({"expected": len(manifest), "received": len(live), **counts}, sort_keys=True))
    return 0 if counts["CONTRADICTION"] == 0 and len(live) == len(manifest) else 2


if __name__ == "__main__":
    raise SystemExit(main())
