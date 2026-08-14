#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Descubrimiento de publicadores inmobiliarios en el Roomix publico.

Ver docs/ROOMIX_AGENCY_ACQUISITION_PLAN_V1.md para el plan completo. Resumen:

  sitemap index -> 6 shards -> URLs de propiedad -> ficha -> agent{_id,name}

Roomix se usa como senal de descubrimiento de hechos publicos (que publicador
existe), no como base a clonar: no se guardan descripciones, fotos, logos,
precios ni metricas propietarias.

Respeta robots.txt: nunca toca /api/, /dashboard/ ni /profile/. Ante 403 se
detiene en vez de intentar evadirlo.

La campana es reanudable: el estado vive en un directorio de datos fuera del
repo y cada lote deja checkpoint.
"""
from __future__ import annotations

import argparse
import json
import random
import re
import sys
import threading
import time
import urllib.error
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

BASE = "https://roomix.ai"
SITEMAP_INDEX = f"{BASE}/sitemap_index.xml"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")

# Rutas que robots.txt prohibe. Se comprueba antes de cada request.
DISALLOWED = ("/api/", "/dashboard/", "/profile/")


class Aborted(Exception):
    """403: no se evade, se aborta."""


class Fetcher:
    """GET cortes: ritmo limitado, backoff acotado, sin rotacion de identidad."""

    def __init__(self, rate_per_s: float = 3.0, timeout: int = 45):
        self.min_gap = 1.0 / rate_per_s
        self.timeout = timeout
        self._lock = threading.Lock()
        self._next_at = 0.0
        self.stats = Counter()

    def _wait(self) -> None:
        with self._lock:
            now = time.monotonic()
            if now < self._next_at:
                time.sleep(self._next_at - now)
                now = time.monotonic()
            self._next_at = now + self.min_gap * random.uniform(0.85, 1.15)

    def get(self, url: str, retries: int = 2) -> str | None:
        if any(bad in url for bad in DISALLOWED):
            raise ValueError(f"ruta prohibida por robots.txt: {url}")
        for attempt in range(retries + 1):
            self._wait()
            req = urllib.request.Request(url, headers={
                "User-Agent": UA,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "es-AR,es;q=0.9",
            })
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as r:
                    self.stats["ok"] += 1
                    return r.read().decode("utf-8", "ignore")
            except urllib.error.HTTPError as e:
                if e.code == 403:
                    self.stats["403"] += 1
                    raise Aborted("403: el sitio bloquea; la campana se detiene sin evadirlo")
                if e.code == 404:
                    self.stats["404"] += 1
                    return None
                if e.code == 429:
                    self.stats["429"] += 1
                    time.sleep(min(60, 5 * (2 ** attempt)))
                    continue
                self.stats[f"http_{e.code}"] += 1
                if e.code >= 500 and attempt < retries:
                    time.sleep(2 ** attempt)
                    continue
                return None
            except Exception:
                self.stats["error"] += 1
                if attempt < retries:
                    time.sleep(1.5 * (attempt + 1))
                    continue
                return None
        return None


# ---------------------------------------------------------------- enumeracion
def property_urls(f: Fetcher) -> dict[str, list[str]]:
    """URLs de propiedad por shard, desde el sitemap index."""
    idx = f.get(SITEMAP_INDEX) or ""
    shards = [u for u in re.findall(r"<loc>([^<]+)</loc>", idx) if "/properties/sitemap/" in u]
    out: dict[str, list[str]] = {}
    for s in sorted(shards):
        body = f.get(s) or ""
        out[s.rsplit("/", 1)[-1]] = re.findall(r"<loc>([^<]+)</loc>", body)
    return out


# ------------------------------------------------------------------- parseo
AGENT_RE = re.compile(r'\\"agent\\":\{\\"_id\\":\\"([0-9a-f-]{16,})\\",\\"name\\":\\"([^\\"]{2,120})')
AGENT_ALT = re.compile(r'"agent":\{"_id":"([0-9a-f-]{16,})","name":"([^"]{2,120})')


def parse_publisher(html: str) -> tuple[str | None, str | None, str]:
    """Devuelve (agent_id, agent_name, metodo)."""
    m = AGENT_RE.search(html) or AGENT_ALT.search(html)
    if m:
        return m.group(1), _unescape(m.group(2)), "agent_block"
    # Fallback: bloque textual "Publicado por"
    i = html.find("Publicado por")
    if i > 0:
        seg = html[i:i + 4000]
        m2 = AGENT_RE.search(seg) or AGENT_ALT.search(seg)
        if m2:
            return m2.group(1), _unescape(m2.group(2)), "parse_fallback"
    return None, None, "not_found"


def _unescape(s: str) -> str:
    s = s.replace("\\u002F", "/").replace("\\/", "/")
    s = re.sub(r"\\u([0-9a-fA-F]{4})", lambda m: chr(int(m.group(1), 16)), s)
    return s.replace("\\\\", "\\").strip()


# ------------------------------------------------------------- convergencia
def chao1(freqs: Counter) -> float:
    """Cota inferior de riqueza total. S_obs + f1^2 / (2*f2)."""
    counts = Counter(freqs.values())
    f1, f2 = counts.get(1, 0), counts.get(2, 0)
    s_obs = len(freqs)
    if f2 == 0:
        return s_obs + f1 * (f1 - 1) / 2 if f1 > 1 else float(s_obs)
    return s_obs + (f1 * f1) / (2 * f2)


def good_turing_coverage(freqs: Counter, n: int) -> float:
    """Proporcion de avisos del universo que pertenece a publicadores ya vistos."""
    if n == 0:
        return 0.0
    f1 = sum(1 for v in freqs.values() if v == 1)
    return max(0.0, 1.0 - f1 / n)


# ------------------------------------------------------------------ campana
def run(data_dir: Path, batch: int, max_pages: int, rate: float, seed: int) -> int:
    data_dir.mkdir(parents=True, exist_ok=True)
    state_p = data_dir / "state.json"
    obs_p = data_dir / "observations.jsonl"

    f = Fetcher(rate_per_s=rate)
    state = json.loads(state_p.read_text(encoding="utf-8")) if state_p.exists() else {}

    if "queue" not in state:
        print("enumerando sitemaps...", flush=True)
        shards = property_urls(f)
        total = sum(len(v) for v in shards.values())
        print("  shards: %s | total URLs: %d" % ({k: len(v) for k, v in shards.items()}, total), flush=True)
        rnd = random.Random(seed)
        queue: list[str] = []
        # Muestreo estratificado: se intercalan los shards para que cualquier
        # corte del recorrido siga siendo representativo del universo.
        pools = []
        for k in sorted(shards):
            pool = shards[k][:]
            rnd.shuffle(pool)
            pools.append(pool)
        i = 0
        while any(pools):
            for p in pools:
                if p:
                    queue.append(p.pop())
            i += 1
        state = {"queue": queue, "done": 0, "universe": total,
                 "shards": {k: len(v) for k, v in shards.items()},
                 "started": time.strftime("%Y-%m-%dT%H:%M:%S")}
        state_p.write_text(json.dumps(state), encoding="utf-8")
        print("  cola construida: %d URLs (orden estratificado)" % len(queue), flush=True)

    freqs: Counter = Counter()
    if obs_p.exists():
        for line in obs_p.open(encoding="utf-8"):
            try:
                o = json.loads(line)
                if o.get("agent_id"):
                    freqs[o["agent_id"]] += 1
            except Exception:
                pass

    queue = state["queue"]
    done = state["done"]
    stable = 0
    out = obs_p.open("a", encoding="utf-8")

    try:
        while done < len(queue) and done < max_pages:
            chunk = queue[done:done + batch]
            before = len(freqs)

            def work(u: str) -> dict:
                html = f.get(u)
                if html is None:
                    return {"url": u, "error": "fetch"}
                aid, name, how = parse_publisher(html)
                return {"url": u, "agent_id": aid, "agent_name": name, "method": how,
                        "ts": int(time.time())}

            with ThreadPoolExecutor(max_workers=4) as ex:
                for rec in ex.map(work, chunk):
                    out.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    if rec.get("agent_id"):
                        freqs[rec["agent_id"]] += 1
            out.flush()

            done += len(chunk)
            state["done"] = done
            state_p.write_text(json.dumps(state), encoding="utf-8")

            n = sum(freqs.values())
            new = len(freqs) - before
            marginal = new / (len(chunk) / 1000.0)
            est = chao1(freqs)
            ratio = len(freqs) / est if est else 0.0
            cov = good_turing_coverage(freqs, n)
            print("  %6d fichas | publicadores %5d | nuevos/1k %6.1f | chao1 %7.0f "
                  "| obs/chao1 %.3f | cobertura %.4f | %s"
                  % (done, len(freqs), marginal, est, ratio, cov, dict(f.stats)), flush=True)

            if marginal < 2.0 and ratio >= 0.90 and cov >= 0.97:
                stable += 1
                if stable >= 3:
                    print("\nCONVERGENCIA ALCANZADA tras %d fichas." % done, flush=True)
                    break
            else:
                stable = 0
    except Aborted as e:
        print("\nABORTADO: %s" % e, flush=True)
        return 2
    except KeyboardInterrupt:
        print("\ninterrumpido; el estado quedo guardado, se puede reanudar", flush=True)
        return 130
    finally:
        out.close()
        state_p.write_text(json.dumps(state), encoding="utf-8")

    n = sum(freqs.values())
    print("\n=== RESUMEN ===", flush=True)
    print("  universo de propiedades:       %d" % state["universe"], flush=True)
    print("  fichas procesadas:             %d (%.2f%%)" % (done, 100.0 * done / state["universe"]), flush=True)
    print("  apariciones con publicador:    %d" % n, flush=True)
    print("  publicadores unicos:           %d" % len(freqs), flush=True)
    print("  chao1 (cota inferior total):   %.0f" % chao1(freqs), flush=True)
    print("  cobertura Good-Turing:         %.4f" % good_turing_coverage(freqs, n), flush=True)
    print("  http: %s" % dict(f.stats), flush=True)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data-dir", default=r"D:\INMO CAPITAL\ERETZ_AGENCY_DATA")
    ap.add_argument("--batch", type=int, default=400)
    ap.add_argument("--max-pages", type=int, default=20000)
    ap.add_argument("--rate", type=float, default=3.0)
    ap.add_argument("--seed", type=int, default=20260813)
    a = ap.parse_args()
    return run(Path(a.data_dir), a.batch, a.max_pages, a.rate, a.seed)


if __name__ == "__main__":
    sys.exit(main())
