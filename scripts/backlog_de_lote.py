#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""El backlog del proximo lote semantico, armado solo y ordenado por impacto.

Solo lectura sobre artefactos locales. `database_writes: 0`. No difiere, no
certifica, no toca la cola: contesta "que familia de defectos va primero".

Por que existe
--------------
Hasta el 2026-10-01 el backlog del lote se escribia a mano, paro por paro, en
`docs/agent/lotes/README.md`. Ese dia la cuenta B firmo 23 paros y anoto 10
patrones; dos de ellos (Houzez `icon-pin`) eran la misma familia vista en dos
agencias, y eso se noto leyendo, no midiendo. Con la diferida automatica por
precedente (`diferir_por_precedente.py`) un paro repetido ya no espera a nadie,
y por eso mismo hace falta un lugar donde NO desaparezca: diferir no es
arreglar, y una familia que se difiere sola veinte veces es la primera del lote.

Que agrupa
----------
Los paros VIVOS (`deuda_de_paros.deuda`: el ultimo STOP por agencia y
componente que la realidad no cerro despues) por FAMILIA: firma exacta del
patron (`defect_triage.firma`) + plataforma. La plataforma sale del host
(`ya_lo_vimos.plataforma_del_host`) o de una palabra de la lista cerrada
`PLATAFORMAS` escrita en el diagnostico humano. Si no hay ninguna de las dos,
la familia es solo la firma: no se adivina.

Que mide por familia: agencias, primera y ultima aparicion, diferidas
automaticas y humanas, campos afectados, radio, y propiedades en juego (de los
paquetes de cada agencia: fichas con el campo fallido, fichas fallidas,
declaradas no enumeradas).

Como ordena (pedido del usuario, 2026-10-01, en este orden)
-----------------------------------------------------------
    1. riesgo de falso cero / falso certificado
    2. perdida masiva de inventario (>= 100 propiedades)
    3. muchas agencias afectadas (>= 3)
    4. campos importantes afectados
    5. el resto (long tail)
y dentro de cada clase por IMPACTO = propiedades x agencias / costo del radio
(AGENCIA 1, FAMILIA 3, COMPARTIDO 10). No es una formula perfecta: es la regla
escrita para que un bug compartido de 20 agencias no quede detras de 5 sitios
chicos.

Uso:
    python scripts/backlog_de_lote.py            # tabla
    python scripts/backlog_de_lote.py --json     # y deja ERETZ_BACKLOG_DE_LOTE.json
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "scripts"))
try:  # raiz del estado operativo configurable (ERETZ_DATA_ROOT)
    from scripts.rutas_de_datos import dato  # noqa: E402
except ImportError:  # corrido como `python scripts/x.py`
    from rutas_de_datos import dato  # noqa: E402

CERT = Path(str(dato("ERETZ_AGENCY_CERTIFICATION_20260827")))
SALIDA = CERT / "ERETZ_BACKLOG_DE_LOTE.json"

# Lista CERRADA: una palabra que no esta aca no crea una plataforma.
PLATAFORMAS = (
    "Houzez", "Estatik", "Synapsis", "Tecnogestion", "Wix", "Strapi", "Pixel Inmobiliario",
    "Kiteprop", "Inmobiliatica", "Tokko", "WPResidence", "RealHomes", "Divi", "Xintel",
    "Mapaprop", "Amaira", "DonWeb", "BuscadorProp", "Terravirtual", "wpcasa", "Elementor",
    "Next.js", "Inmoclick", "Argenprop", "Zonaprop",
)
COSTO_DEL_RADIO = {"AGENCIA": 1, "FAMILIA": 3, "COMPARTIDO": 10}
COMPONENTES_FALSO_CERO = {"posible_perdida_de_inventario", "perdida_sistematica_de_inventario"}
COMPONENTES_INVENTARIO = COMPONENTES_FALSO_CERO | {
    "catalogo_declarado_mayor_que_el_enumerado", "enumeracion_compartida",
    "guardian_de_forma_compartido", "inventario_inestable_entre_corridas"}
CAMPOS_IMPORTANTES = {"precio", "moneda", "operacion", "tipo_propiedad", "ciudad", "provincia"}


def _jsonl(ruta: Path):
    if not ruta.exists():
        return
    for linea in ruta.open(encoding="utf-8", errors="replace"):
        linea = linea.strip()
        if linea:
            try:
                yield json.loads(linea)
            except ValueError:
                continue


def paquetes(cert: Path = CERT) -> dict[str, str]:
    """canonical_agency_id -> carpeta de su paquete de evidencia."""
    salida: dict[str, str] = {}
    for run in glob.glob(str(cert / "agencies" / "*" / "run1.json")):
        try:
            agencia = json.load(open(run, encoding="utf-8")).get("canonical_agency_id")
        except (OSError, ValueError):
            continue
        if agencia:
            salida[agencia] = os.path.dirname(run)
    return salida


def _leer(carpeta: str, nombre: str) -> dict[str, Any]:
    try:
        return json.load(open(os.path.join(carpeta, nombre), encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def en_juego(carpeta: str | None, componente: str) -> tuple[int, list[str], str | None]:
    """(propiedades en juego, campos fallidos, url oficial) segun el paquete de la agencia."""
    if not carpeta:
        return 0, [], None
    run = _leer(carpeta, "run1.json")
    campos, peor = [], 0
    for campo, c in _leer(carpeta, "field_coverage.json").items():
        if isinstance(c, dict) and c.get("state") == "EXTRACTION_FAILED":
            campos.append(campo)
            faltan = int(c.get("source_provided") or 0) - int(c.get("normalized_present") or 0)
            peor = max(peor, int(c.get("extraction_failed") or 0), faltan)
    inventario = int(run.get("detalles_fallidos") or 0)
    declarado, enumeradas = run.get("total_declarado"), run.get("enumeradas")
    if isinstance(declarado, int) and isinstance(enumeradas, int) and declarado > enumeradas:
        inventario = max(inventario, declarado - enumeradas)
    props = inventario if componente in COMPONENTES_INVENTARIO else max(peor, inventario)
    return props, sorted(campos), run.get("official_url")


def plataforma(url: str | None, diagnosticos: list[str]) -> str | None:
    try:
        from ya_lo_vimos import plataforma_del_host
        host = plataforma_del_host(url or "")
    except Exception:  # noqa: BLE001 - sin el modulo, solo el texto
        host = None
    if host:
        return host
    texto = " ".join(diagnosticos)
    for nombre in PLATAFORMAS:
        if re.search(r"(?i)(?<![\w.])" + re.escape(nombre) + r"(?!\w)", texto):
            return nombre
    return None


def clase(componentes: set[str], propiedades: int, agencias: int, campos: set[str]) -> int:
    if componentes & COMPONENTES_FALSO_CERO:
        return 1
    if componentes & COMPONENTES_INVENTARIO and propiedades >= 100:
        return 2
    if agencias >= 3:
        return 3
    if campos & CAMPOS_IMPORTANTES:
        return 4
    return 5


def backlog(cert: Path = CERT) -> list[dict[str, Any]]:
    from deuda_de_paros import deuda
    vivos = deuda(cert)["vivos"]
    diferidas: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for d in _jsonl(cert / "AGENCY_DEFECTS_DIFERIDOS.jsonl"):
        diferidas[(d.get("canonical_agency_id"), d.get("componente"))].append(d)
    carpetas = paquetes(cert)
    familias: dict[tuple[str, str | None], dict[str, Any]] = {}
    for (agencia, componente), paro in vivos:
        filas = diferidas.get((agencia, componente), [])
        humanas = [d.get("diagnostico") or "" for d in filas if not d.get("diferida_por_precedente")]
        props, campos, url = en_juego(carpetas.get(agencia), componente)
        plat = plataforma(url, humanas)
        clave = (paro.get("firma_del_patron") or "sin_firma", plat)
        cuando = paro.get("cuando") or ""
        f = familias.setdefault(clave, {
            "firma": clave[0], "plataforma": plat, "componentes": set(), "radio": set(),
            "estrategias": set(), "agencias": [], "campos": set(), "propiedades": 0,
            "primera": cuando, "ultima": cuando, "diferidas_automaticas": 0,
            "diferidas_humanas": 0, "sin_diferida": 0, "sin_diagnostico_propio": [],
            "diagnostico": None})
        f["componentes"].add(componente)
        f["radio"].add(paro.get("radio_estimado") or "AGENCIA")
        f["estrategias"].add(paro.get("connector_strategy") or "")
        f["agencias"].append(agencia)
        f["campos"].update(campos)
        f["propiedades"] += props
        f["primera"] = min(f["primera"], cuando)
        f["ultima"] = max(f["ultima"], cuando)
        f["diferidas_automaticas"] += sum(1 for d in filas if d.get("diferida_por_precedente"))
        f["diferidas_humanas"] += len(humanas)
        f["sin_diferida"] += 0 if filas else 1
        # Diferida solo por precedente = nadie miro ESTA agencia. Medido el
        # 2026-10-01: dentro de una misma firma exacta los diagnosticos humanos
        # nombran causas distintas (a8580800972a: categorias, area de clientes,
        # formulario ajeno, portal como fuente, etiqueta rota...), asi que el
        # texto copiado no es la causa de esta. Es deuda de diagnostico.
        if not humanas:
            f["sin_diagnostico_propio"].append(agencia)
        f["diagnostico"] = f["diagnostico"] or (humanas[-1][:300] if humanas else None)
    salida = []
    for f in familias.values():
        costo = max(COSTO_DEL_RADIO.get(r, 3) for r in f["radio"])
        n = len(f["agencias"])
        salida.append({**f, "clase": clase(f["componentes"], f["propiedades"], n, f["campos"]),
                       "impacto": round(f["propiedades"] * n / costo, 1),
                       "componentes": sorted(f["componentes"]), "radio": sorted(f["radio"]),
                       "estrategias": sorted(f["estrategias"]), "campos": sorted(f["campos"]),
                       "agencias": sorted(f["agencias"]), "n_agencias": n,
                       "sin_diagnostico_propio": sorted(f["sin_diagnostico_propio"]),
                       "causas_humanas": f["diferidas_humanas"]})
    salida.sort(key=lambda f: (f["clase"], -f["impacto"], -f["n_agencias"]))
    return salida


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    ap.add_argument("--json", action="store_true", help="deja ERETZ_BACKLOG_DE_LOTE.json")
    ap.add_argument("--top", type=int, default=25)
    args = ap.parse_args(argv)
    filas = backlog()
    print(f"familias vivas: {len(filas)}  paros vivos: {sum(f['n_agencias'] for f in filas)}  "
          f"sin diagnostico propio: {sum(len(f['sin_diagnostico_propio']) for f in filas)}")
    print(f"{'cl':>2} {'impacto':>9} {'ag':>3} {'props':>6} {'radio':<11} {'plataforma':<16} componente / campos")
    for f in filas[:args.top]:
        print(f"{f['clase']:>2} {f['impacto']:>9} {f['n_agencias']:>3} {f['propiedades']:>6} "
              f"{','.join(f['radio']):<11} {(f['plataforma'] or '-')[:16]:<16} "
              f"{','.join(f['componentes'])[:34]} {','.join(f['campos'])[:40]}")
    if args.json:
        SALIDA.write_text(json.dumps(filas, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"escrito {SALIDA}")
    print("database_writes: 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
