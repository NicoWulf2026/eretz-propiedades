"""El diff exacto de las candidatas contra produccion. No escribe nada.

Produccion no pasa por el contexto: se baja una sola vez como una tira de
claves -8 hexadecimales de `md5(inmobiliaria_id|url_normalizada)` seguidos de
quince banderas de "este campo tiene valor"- y el cruce se hace aca.

Ocho hexadecimales son 32 bits. Con 47.204 filas, la probabilidad de que dos
claves distintas choquen ronda el 0,03 %: unas quince filas sobre cincuenta
mil. Se informa, no se esconde, y por eso el artefacto es un DRY-RUN que hay
que verificar contra la base antes de escribir una sola fila.

Lo que este cruce puede decidir con certeza:

  - si la candidata YA EXISTE en produccion o es NUEVA;
  - para las que existen, que campos tiene produccion y nosotros no -o sea
    exactamente lo que un UPDATE ingenuo destruiria- y al reves.

Lo que NO puede decidir: si un campo que ambos tienen tiene el MISMO valor.
Para eso hace falta comparar valores, no presencias, y eso es la conexion
directa que hoy no tenemos.
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from hashlib import md5
from pathlib import Path
from urllib.parse import unquote, urlsplit

# El orden es el mismo que arma la consulta que bajo el volcado.
CAMPOS = ("precio", "moneda", "ambientes", "dormitorios", "banos",
          "superficie_total", "superficie_cubierta", "latitud", "ciudad",
          "barrio", "provincia", "direccion", "titulo", "descripcion",
          "imagenes")
LARGO = 8 + len(CAMPOS)

D = Path(__file__).parent
CANDIDATAS = Path(r"D:\INMO CAPITAL\ERETZ_PREINGESTION_REBUILD_20260903"
                  r"\DB_WRITE_ELIGIBLE.jsonl")


def normalizar(u: str | None) -> str:
    """La misma forma que guarda produccion en `url_normalizada`."""
    p = urlsplit(u or "")
    return p.netloc.lower().removeprefix("www.") + unquote(p.path).lower().rstrip("/")


def tiene(valor) -> bool:
    if valor is None:
        return False
    if isinstance(valor, str):
        return bool(valor.strip())
    if isinstance(valor, (list, tuple, dict)):
        return len(valor) > 0
    return True


def volcado(ruta: Path) -> tuple[dict[str, str], int]:
    crudo = ruta.read_text(encoding="utf-8", errors="replace")
    # El volcado viene con las comillas escapadas, asi que en vez de pelear
    # con el escape se busca lo que no puede confundirse con otra cosa: la
    # tirada mas larga de caracteres hexadecimales del archivo.
    tira = max(re.findall("[0-9a-f]+", crudo), key=len, default="")
    if len(tira) < 1000:
        raise SystemExit("no encuentro la tira de claves en el volcado")
    if len(tira) % LARGO:
        raise SystemExit(f"la tira mide {len(tira)}, no es multiplo de {LARGO}")
    filas: dict[str, str] = {}
    for i in range(0, len(tira), LARGO):
        filas[tira[i:i + 8]] = tira[i + 8:i + LARGO]
    return filas, len(tira) // LARGO


def main() -> int:
    prod, filas_prod = volcado(Path(sys.argv[1]))
    print(f"produccion .... {filas_prod} filas -> {len(prod)} claves distintas "
          f"({filas_prod - len(prod)} choques/duplicados)")

    clases = Counter()
    destruiria = Counter()   # produccion tiene, nosotros no
    aportaria = Counter()    # nosotros tenemos, produccion no
    coinciden = Counter()
    por_agencia = Counter()
    filas_con_riesgo = 0
    riesgo_por_fila = Counter()
    salida = []
    vistas = 0

    with open(CANDIDATAS, encoding="utf-8") as f:
        for linea in f:
            if not linea.strip():
                continue
            r = json.loads(linea)
            vistas += 1
            aid = str(r.get("inmobiliaria_id") or "")
            un = normalizar(r.get("source_url"))
            if not aid or not un:
                clases["SIN_CLAVE"] += 1
                continue
            k = md5(f"{aid}|{un}".encode()).hexdigest()[:8]
            mascara = prod.get(k)
            if mascara is None:
                clases["NEW"] += 1
                salida.append({"k": k, "clase": "NEW", "aid": aid,
                               "cid": r.get("canonical_agency_id")})
                continue

            perdidos, ganados = [], []
            for pos, campo in enumerate(CAMPOS):
                p = mascara[pos] == "1"
                n = tiene(r.get(campo))
                if p and not n:
                    destruiria[campo] += 1
                    perdidos.append(campo)
                elif n and not p:
                    aportaria[campo] += 1
                    ganados.append(campo)
                elif p and n:
                    coinciden[campo] += 1

            clase = "UPDATE_CON_RIESGO" if perdidos else (
                "UPDATE" if ganados else "SIN_APORTE")
            clases[clase] += 1
            por_agencia[r.get("canonical_agency_id")] += 1
            if perdidos:
                filas_con_riesgo += 1
                riesgo_por_fila[len(perdidos)] += 1
            salida.append({"k": k, "clase": clase, "aid": aid,
                           "cid": r.get("canonical_agency_id"),
                           "no_tocar": perdidos, "aporta": ganados})

    print(f"candidatas .... {vistas}\n")
    print("--- clasificacion ---")
    for c, n in clases.most_common():
        print(f"  {c:20} {n:7}  ({100*n/vistas:5.1f} %)")

    existentes = vistas - clases["NEW"] - clases["SIN_CLAVE"]
    print(f"\n--- que pasaria campo por campo sobre las {existentes} que ya existen ---")
    print(f"{'campo':22} {'destruiria':>11} {'aportaria':>10} {'ya coincide':>12}")
    for c in CAMPOS:
        print(f"{c:22} {destruiria[c]:11} {aportaria[c]:10} {coinciden[c]:12}")
    print(f"{'TOTAL':22} {sum(destruiria.values()):11} "
          f"{sum(aportaria.values()):10} {sum(coinciden.values()):12}")

    print(f"\nfilas donde un UPDATE ingenuo borraria algo: {filas_con_riesgo}"
          f" ({100*filas_con_riesgo/max(existentes,1):.1f} % de las existentes)")
    print("campos perdidos por fila:",
          ", ".join(f"{k}->{v}" for k, v in sorted(riesgo_por_fila.items())))

    destino = Path(r"D:\INMO CAPITAL\Inmo-Capital-main\DATA_QUALITY"
                   r"\dry_run_escritura.jsonl")
    destino.parent.mkdir(parents=True, exist_ok=True)
    with open(destino, "w", encoding="utf-8") as g:
        for fila in salida:
            g.write(json.dumps(fila, ensure_ascii=False) + "\n")
    print(f"\ndry-run escrito: {destino}  ({len(salida)} lineas)")
    print("database_writes: 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
