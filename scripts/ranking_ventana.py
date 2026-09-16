#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Dos rankings separados: lo que falta y lo que está incompleto.

No escribe nada. `database_writes: 0`.

El §8 pide no mezclarlos, y la razón se ve en un ejemplo del propio proyecto:

    extraccion_transversal_de_atributos   15 agencias, 1.708 propiedades
    variante_no_soportada                 20 agencias,    54 propiedades

Por volumen de propiedades afectadas gana la primera por treinta veces. Pero
las 1.708 **ya están en ERETZ** y les falta un campo secundario, mientras que
detrás de las 54 hay **479 propiedades que no tenemos** —y sólo `bottai` aporta
333—.

Arreglar lo segundo trae propiedades nuevas al catálogo. Arreglar lo primero
mejora fichas que ya están. Los dos valen, pero no compiten por el mismo lugar.

    INVENTORY_RISK_SCORE   propiedades que existen y NO tenemos
    FIELD_QUALITY_SCORE    propiedades que tenemos con un campo faltante

Uso:
    python scripts/ranking_ventana.py
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

CERT = Path(r"D:\INMO CAPITAL\ERETZ_AGENCY_CERTIFICATION_20260827")

# Firmas que significan "faltan propiedades enteras".
DE_INVENTARIO = {
    "catalogo_declarado_mayor_que_el_enumerado",
    "posible_perdida_de_inventario",
    "perdida_sistematica_de_inventario",
    "inventario_inestable_entre_corridas",
    "variante_no_soportada",
    "enumeracion_compartida",
}
# Firmas que significan "la propiedad esta, le falta un campo".
DE_CAMPO = {
    "extraccion_transversal_de_atributos",
    "imagenes_compartidas",
    "extraccion_de_baja_magnitud",
}
# Riesgo de COMPLETE falso: que el defecto pase desapercibido y se publique.
RIESGO_FALSO_COMPLETE = {
    "catalogo_declarado_mayor_que_el_enumerado": 3,
    "inventario_inestable_entre_corridas": 3,
    "perdida_sistematica_de_inventario": 2,
    "posible_perdida_de_inventario": 2,
    "variante_no_soportada": 1,   # cierra NEEDS_FIX: no se publica sin verse
    "enumeracion_compartida": 2,
}
# Peso del campo para el producto: sin estos, la ficha no se puede filtrar.
PESO_DE_CAMPO = {
    "precio": 3, "moneda": 3, "operacion": 3, "tipo_propiedad": 3,
    "ciudad": 3, "provincia": 3, "ambientes": 2, "dormitorios": 2,
    "banos": 2, "superficie_total": 2, "superficie_cubierta": 1,
    "barrio": 2, "latitud": 1, "longitud": 1, "direccion": 1,
    "titulo": 2, "descripcion": 1, "imagenes": 2,
}


def cargar() -> tuple[list[dict], dict[str, dict]]:
    dif = [json.loads(l) for l in
           (CERT / "AGENCY_DEFECTS_DIFERIDOS.jsonl").read_text(
               encoding="utf-8", errors="replace").splitlines() if l.strip()]
    ult: dict[str, dict] = {}
    for linea in (CERT / "AGENCY_CERTIFICATION_RESULTS.jsonl").read_text(
            encoding="utf-8", errors="replace").splitlines():
        if not linea.strip():
            continue
        try:
            r = json.loads(linea)
        except ValueError:
            continue
        if r.get("canonical_agency_id"):
            ult[r["canonical_agency_id"]] = r
    return dif, ult


def main() -> int:
    dif, ult = cargar()

    inv: dict[str, dict] = defaultdict(
        lambda: {"agencias": set(), "recuperables": 0, "riesgo": 0})
    campos: dict[str, dict] = defaultdict(
        lambda: {"agencias": set(), "afectadas": 0, "peso": 0})

    for f in dif:
        firma = f.get("componente") or "(sin firma)"
        agencia = f["canonical_agency_id"]
        r = ult.get(agencia) or {}
        enumeradas = (r.get("enumeration_audit") or {}).get("enumerated") or 0

        if firma in DE_INVENTARIO:
            # Lo recuperable es lo que existe y no tenemos. Si la diferida lo
            # midio contra la fuente, se usa ese numero; si no, se usa 0 y se
            # dice, en vez de inventar una estimacion.
            real = f.get("inventario_real") or 0
            visto = f.get("inventario_que_vemos")
            visto = enumeradas if visto is None else visto
            inv[firma]["agencias"].add(agencia)
            inv[firma]["recuperables"] += max(0, real - visto)
            inv[firma]["riesgo"] = max(inv[firma]["riesgo"],
                                       RIESGO_FALSO_COMPLETE.get(firma, 1))
        elif firma in DE_CAMPO:
            campos[firma]["agencias"].add(agencia)
            campos[firma]["afectadas"] += enumeradas
            cob = r.get("field_coverage") or {}
            peor = 0
            for campo, d in cob.items():
                if (d or {}).get("extraction_failed"):
                    peor = max(peor, PESO_DE_CAMPO.get(campo, 1))
            campos[firma]["peso"] = max(campos[firma]["peso"], peor)

    print("=" * 66)
    print("P0/P1 — INVENTORY_RISK: propiedades que existen y NO tenemos")
    print("=" * 66)
    print(f"{'firma':42} {'agen':>5} {'recup':>7} {'riesgo':>7} {'score':>9}")
    filas = []
    for firma, d in inv.items():
        n = len(d["agencias"])
        score = d["recuperables"] * d["riesgo"] + n * d["riesgo"]
        filas.append((score, firma, n, d["recuperables"], d["riesgo"]))
    for score, firma, n, rec, riesgo in sorted(filas, reverse=True):
        print(f"{firma[:40]:42} {n:5} {rec:7,} {riesgo:7} {score:9,}")
    total_rec = sum(d["recuperables"] for d in inv.values())
    print(f"\n  propiedades recuperables medidas: {total_rec:,}")
    print("  (solo las que una diferida midio contra la fuente; el resto no se")
    print("   estima, se deja en cero y se dice)")

    print("\n" + "=" * 66)
    print("P2 — FIELD_QUALITY: propiedades que tenemos, con un campo faltante")
    print("=" * 66)
    print(f"{'firma':42} {'agen':>5} {'afect':>7} {'peso':>6} {'score':>9}")
    filas2 = []
    for firma, d in campos.items():
        n = len(d["agencias"])
        score = d["afectadas"] * d["peso"]
        filas2.append((score, firma, n, d["afectadas"], d["peso"]))
    for score, firma, n, af, peso in sorted(filas2, reverse=True):
        print(f"{firma[:40]:42} {n:5} {af:7,} {peso:6} {score:9,}")


    # ---------------- Qué arreglar, no qué firma ----------------
    #
    # El bucket por firma agrupa demasiado: `extraccion_transversal_de_atributos`
    # junta 16 agencias, y una sola de ellas puede ser la mitad del total. Esto
    # baja al par (agencia, campo), que es la unidad en la que efectivamente se
    # escribe un arreglo.
    # Pares (agencia, campo) donde `source_provided` esta INFLADO y por eso el
    # "recuperable" es falso. No se infieren: se verificaron descargando una
    # ficha de cada una el 2026-09-15.
    #
    # El patron de `ambientes` del certificador no exige limite de palabra
    # antes de "ambientes", asi que encuentra "ambiente 1" adentro de
    # **MONO**ambiente. Y "Monoambiente" es una opcion de menu que esta en
    # TODAS las paginas de esos sitios, no un atributo de la propiedad. Por eso
    # el delator es `source_provided == total`: una senal que aparece en el
    # 100 % de las fichas suele ser del sitio, no de la propiedad.
    #
    # `espina propiedades` da 100 % tambien y NO esta aca: se descargo su ficha
    # y su "Ambientes 2" es un atributo real. La lista es de casos
    # verificados, no de sospechas.
    ARTEFACTOS = {
        ("roomix:blanco propiedades", "ambientes"):
            "el patron encuentra 'ambiente 1' en MONOambiente, del menu de "
            "filtros; la ficha publica 'Cantidad de dormitorios'",
        ("roomix:bartolelli maini propiedades", "ambientes"):
            "'Monoambiente 1 dormitorio' en el menu de navegacion",
        ("roomix:cuini propiedades", "ambientes"):
            "'Monoambiente 1 dormitorio' en el menu de navegacion",
    }

    pares = []
    descontado = 0
    for agencia, r in ult.items():
        if r.get("status") != "NEEDS_FIX":
            continue
        for campo, d in (r.get("field_coverage") or {}).items():
            perdidas = (d.get("extraction_failed") or 0)
            provistas = (d.get("source_provided") or 0)
            # Solo cuenta si la FUENTE lo publica: si no lo publica, no hay
            # nada que recuperar y arreglarlo no agrega una sola ficha.
            if perdidas and provistas:
                if (agencia, campo) in ARTEFACTOS:
                    descontado += min(perdidas, provistas)
                    continue
                pares.append((min(perdidas, provistas), agencia, campo,
                              d.get("normalized_total") or 0,
                              r.get("connector_strategy") or ""))

    print("\n" + "=" * 66)
    print("QUE ARREGLAR PRIMERO — por (agencia, campo), no por firma")
    print("=" * 66)
    print(f"{'agencia':30} {'campo':18} {'recup':>7} {'de':>6}  estrategia")
    total = sum(p[0] for p in pares)
    acumulado = 0
    for recup, agencia, campo, tot, est in sorted(pares, reverse=True)[:12]:
        acumulado += recup
        print(f"{agencia.split(':')[-1][:28]:30} {campo[:16]:18} {recup:7,} "
              f"{tot:6,}  {est}")
    print(f"\n  fichas con un campo recuperable: {total:,} sobre "
          f"{len({p[1] for p in pares})} agencias")
    if total:
        print(f"  los 12 de arriba son el {acumulado/total:.0%} del total")
    print("  'recup' = fichas donde la fuente publica el campo y nuestra")
    print("  extraccion falla. Si la fuente no lo publica, no se cuenta.")
    if descontado:
        print("")
        print(f"  DESCONTADAS {descontado:,} fichas que este ranking contaba")
        print("  de mas, sobre "
              f"{len({a for a, _ in ARTEFACTOS})} agencias:")
        for (a, campo), porque in ARTEFACTOS.items():
            print(f"     {a.split(':')[-1][:24]:26} {campo:11} {porque[:44]}")
        print("  No son arreglos pendientes: la fuente no publica ese campo y")
        print("  el patron del certificador lo cuenta mal. Arreglarlo toca")
        print("  `shared/certifier`, que esta bajo freeze.")


    # ---------------- Vista B: por arreglo, no por campo ----------------
    #
    # Un cluster es "un arreglo": la unidad que se escribe, se testea y se
    # despliega junta. NO se arma sumando campos que fallan parecido, porque
    # eso promete un ROI que no existe: `blanco` perdia precio, moneda Y
    # ambientes, y los tres parecian un solo problema. Precio y moneda si lo
    # son -misma causa, se arreglan juntos-. `ambientes` no era un defecto:
    # la fuente no lo publica y el certificador lo contaba mal.
    #
    # Cada cluster lleva su causa verificada contra la fuente y su radio
    # medido. Los que no tienen causa verificada NO entran: quedan en la vista
    # A hasta que alguien los diagnostique.
    CLUSTERS = [
        {
            "cluster": "JSONLD_PRICE_SIN_CURRENCY",
            "causa": ("el JSON-LD publica price y no publica priceCurrency; "
                      "el parser toma el precio de ahi y por eso NO baja al "
                      "texto, que es donde esta la moneda; despues la guarda "
                      "'un numero sin moneda no es un precio' anula el precio"),
            "agencias": ["blanco propiedades"],
            "campos": ["precio", "moneda"],
            "valores_recuperables": 1206 + 1185,
            "propiedades_afectadas": 1206,
            "costo": "BAJO — una rama nueva de 4 lineas; la guarda no se toca",
            "radio": "generic/common: 14 estrategias, 57 agencias, 3.748 props",
            "riesgo": ("BAJO para el dato; ALTO para la cola: invalida 57 "
                       "certificaciones y hay que recertificarlas"),
            "verificado": "12 de 12 fichas reales, prediccion falsable",
        },
        {
            "cluster": "OPERACION_SOLO_EN_TITLE",
            "causa": ("la operacion se lee del titulo editorial que carga la "
                      "inmobiliaria; cuando ese titulo no trae la palabra, el "
                      "campo queda vacio aunque el titulo del documento la diga"),
            "agencias": ["fenix inmobiliaria"],
            "campos": ["operacion"],
            "valores_recuperables": 179,
            "propiedades_afectadas": 179,
            "costo": "BAJO — un fallback de 3 lineas",
            "radio": "generic/common: mismo radio que el anterior",
            "riesgo": ("BAJO: TRUE_RECOVERY 20/20 y FALSE_OPERATION_RISK 0 "
                       "sobre 35 fichas conocidas, 20 venta y 15 alquiler"),
            "verificado": "35 fichas reales, incluido el caso caro venta/alquiler",
        },
        {
            "cluster": "CATEGORY_PAGE_AS_PROPERTY",
            "causa": ("el enumerador admite vistas filtradas del catalogo como "
                      "si fueran fichas; una url de ALQUILER entro como venta"),
            "agencias": ["fenix inmobiliaria", "baron inmobiliaria",
                         "brunetti propiedades"],
            "campos": ["(no es un campo: es inventario falso)"],
            "valores_recuperables": 0,
            "propiedades_afectadas": 8,
            "costo": "MEDIO — regla de cuatro condiciones, hay que calibrarla",
            "radio": "enumeracion, no extraccion: radio distinto del anterior",
            "riesgo": ("MEDIO: descarta paginas. Se probo contra 378 agencias "
                       "y marca 8; con una condicion menos marcaba 395"),
            "verificado": "las 8 revisadas una por una contra la fuente",
        },
    ]

    print("\n" + "=" * 66)
    print("VISTA B — FIX_CLUSTER_RANKING: que arreglo escribir, y que cuesta")
    print("=" * 66)
    for c in sorted(CLUSTERS, key=lambda x: -x["valores_recuperables"]):
        print(f"\n{c['cluster']}")
        print(f"   valores recuperables   {c['valores_recuperables']:,}")
        print(f"   propiedades afectadas  {c['propiedades_afectadas']:,}")
        print(f"   agencias               {len(c['agencias'])}: "
              f"{', '.join(c['agencias'])}")
        print(f"   campos                 {', '.join(c['campos'])}")
        print(f"   costo                  {c['costo']}")
        print(f"   radio                  {c['radio']}")
        print(f"   riesgo                 {c['riesgo']}")
        print(f"   verificado             {c['verificado']}")
    print("\n   Los dos primeros comparten radio pero NO causa: se escriben y")
    print("   se despliegan por separado. Unirlos ataria dos arreglos a un")
    print("   solo rollback.")
    print("\n   NO entra a esta vista `blanco/ambientes`, que figuraba con")
    print("   1.089 recuperables. La fuente no publica ambientes: el patron")
    print("   del certificador encuentra 'ambiente 1' adentro de la palabra")
    print("   MONOambiente, que es una opcion del menu de filtros y esta")
    print("   igual en las 1.213 fichas. Era un error de medicion, no un")
    print("   arreglo pendiente.")

    print("\n" + "=" * 66)
    print("LECTURA")
    print("=" * 66)
    print("  Los dos rankings no compiten: el primero trae propiedades NUEVAS")
    print("  al catalogo, el segundo mejora fichas que ya estan. El §7 pide")
    print("  resolver inventario primero, y el orden de arriba es ese.")
    print("\ndatabase_writes: 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
