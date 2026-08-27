#!/usr/bin/env python3
"""Check PostgREST availability without exposing the supplied publishable key."""

from __future__ import annotations

import argparse
import ctypes
import os
import sys
import urllib.error
import urllib.request


def disable_echo() -> None:
    if os.name != "nt" or not sys.stdin.isatty():
        return
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.GetStdHandle(-10)
    mode = ctypes.c_uint()
    if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
        kernel32.SetConsoleMode(handle, mode.value & ~0x0004)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--path", default="/rest/v1/propiedades?select=id&limit=1")
    args = parser.parse_args()
    disable_echo()
    key = sys.stdin.readline().strip()
    if not key:
        print("status=NO_KEY")
        return 2
    request = urllib.request.Request(
        args.url.rstrip("/") + args.path,
        headers={"apikey": key, "Authorization": "Bearer " + key},
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            status = response.status
    except urllib.error.HTTPError as error:
        status = error.code
    except urllib.error.URLError:
        print("status=NETWORK_ERROR")
        return 3
    finally:
        key = ""
    print(f"status={status}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
