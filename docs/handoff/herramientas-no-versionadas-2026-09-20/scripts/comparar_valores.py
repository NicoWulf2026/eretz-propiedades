"""Que campos DIFIEREN de verdad, no solo cuales estan presentes.

El diff anterior sabia si un campo estaba de cada lado; este sabe si el valor
es el mismo. Produccion manda dos hexadecimales por campo -un md5 recortado del
valor NORMALIZADO- y la misma normalizacion se aplica aca.

Dos hexadecimales son 256 valores: dos textos distintos coinciden por azar una
vez cada 256. Sobre los campos que hay que comparar eso da unos pocos cientos
de "iguales" que en realidad difieren, siempre en la direccion segura -decir
que no hay que escribir algo que si habria que escribir-, nunca en la de pisar
un dato. Igual se informa.

La normalizacion tiene que ser LA MISMA de los dos lados o todo parece distinto.
Por eso el primer numero que imprime es el de control: si los campos que ambos
lados tienen dieran casi todos "distinto", la normalizacion no coincide y el
resultado no vale.
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from hashlib import md5
from pathlib import Path
from urllib.parse import unquote, urlsplit

CAMPOS = ("precio", "moneda", "ambientes", "dormitorios", "banos",
          "superficie_total", "superficie_cubierta", "latitud", "ciudad",
          "barrio", "provincia", "direccion", "titulo", "descripcion",
          "imagenes")
LARGO = 8 + 2 * len(CAMPOS)

CANDIDATAS = Path(r"D:\INMO CAPITAL\ERETZ_PREINGESTION_REBUILD_20260903"
                  r"\DB_WRITE_ELIGIBLE.jsonl")
DRY_RUN = Path(r"D:\INMO CAPITAL\Inmo-Capital-main\DATA_QUALITY"
               r"\dry_run_escritura.jsonl")

DECIMALES = {"precio": 2, "superficie_total": 2, "superficie_cubierta": 2,
             "latitud": 5}
ENTEROS = {"ambientes", "dormitorios", "banos"}
ESPACIOS = re.compile(r"\s+")


def texto(v) -> str:
    return ESPACIOS.sub(" ", str(v)).strip().lower()


def numero(v, decimales: int) -> str:
    """`round(x, n)::text` de Postgres, sin ceros ni punto al final."""
    s = f"{round(float(v), decimales):.{decimales}f}"
    return s.rstrip("0").rstrip(".")


def firma(campo: str, valor) -> str | None:
    if valor is None or (isinstance(valor, str) and not valor.strip()):
        return None
    if campo == "imagenes":
        if not isinstance(valor, (list, tuple)):
            return None
        s = str(len(valor))
    elif campo in DECIMALES:
        try:
            s = numero(valor, DECIMALES[campo])
        except (TypeError, ValueError):
            return None
    elif campo in ENTEROS:
        try:
            s = str(int(valor))
        except (TypeError, ValueError):
            return None
    else:
        s = texto(valor)
    return md5(s.encode()).hexdigest()[:2]


def normalizar_url(u: str | None) -> str:
    p = urlsplit(u or "")
    return p.netloc.lower().removeprefix("www.") + unquote(p.path).lower().rstrip("/")


def volcado(ruta: Path) -> dict[str, str]:
    crudo = ruta.read_text(encoding="utf-8", errors="replace")
    tira = max(re.findall("[0-9a-f]+", crudo), key=len, default="")
    if len(tira) % LARGO:
        raise SystemExit(f"la tira mide {len(tira)}, no es multiplo de {LARGO}")
    return {tira[i:i + 8]: tira[i + 8:i + LARGO]
            for i in range(0, len(tira), LARGO)}


def main() -> int:
    prod = volcado(Path(sys.argv[1]))
    print(f"produccion: {len(prod)} filas con firma de valor")

    clase = {}
    for linea in DRY_RUN.read_text(encoding="utf-8").splitlines():
        if linea.strip():
            f = json.loads(linea)
            clase[f["k"]] = f["clase"]

    iguales, distintos = Counter(), Counter()
    filas_sin_cambio = filas_con_cambio = 0
    vistas = 0
    cambios_por_fila = Counter()

    for linea in open(CANDIDATAS, encoding="utf-8"):
        if not linea.strip():
            continue
        r = json.loads(linea)
        aid = str(r.get("inmobiliaria_id") or "")
        un = normalizar_url(r.get("source_url"))
        if not aid or not un:
            continue
        k = md5(f"{aid}|{un}".encode()).hexdigest()[:8]
        firmas = prod.get(k)
        if firmas is None or clase.get(k) in (None, "NEW", "RETENIDA_WEB_AJENA",
                                              "DUPLICATE"):
            continue
        vistas += 1
        n_cambios = 0
        for pos, campo in enumerate(CAMPOS):
            suya = firmas[2 * pos:2 * pos + 2]
            mia = firma(campo, r.get(campo))
            if mia is None or suya == "00":
                continue          # falta de un lado: eso ya lo dijo el diff
            if mia == suya:
                iguales[campo] += 1
            else:
                distintos[campo] += 1
                n_cambios += 1
        if n_cambios:
            filas_con_cambio += 1
            cambios_por_fila[n_cambios] += 1
        else:
            filas_sin_cambio += 1

    tot_i, tot_d = sum(iguales.values()), sum(distintos.values())
    print(f"filas comparadas: {vistas}")
    print(f"\nCONTROL - campos presentes en ambos lados: {tot_i + tot_d}")
    print(f"  coinciden: {tot_i} ({100*tot_i/max(tot_i+tot_d,1):.1f} %)")
    print(f"  difieren:  {tot_d} ({100*tot_d/max(tot_i+tot_d,1):.1f} %)")
    if tot_i < tot_d / 10:
        print("  >> la normalizacion NO coincide: el resultado no vale <<")

    print(f"\n{'campo':22} {'coinciden':>10} {'difieren':>9}  {'% difiere':>9}")
    for c in CAMPOS:
        n = iguales[c] + distintos[c]
        pct = f"{100*distintos[c]/n:.1f}" if n else "-"
        print(f"{c:22} {iguales[c]:10} {distintos[c]:9}  {pct:>9}")

    print(f"\nfilas donde NINGUN campo compartido cambia: {filas_sin_cambio}")
    print(f"filas con al menos un cambio real:          {filas_con_cambio}")
    print("cambios por fila:",
          ", ".join(f"{k}:{v}" for k, v in sorted(cambios_por_fila.items())))
    print("\ndatabase_writes: 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
