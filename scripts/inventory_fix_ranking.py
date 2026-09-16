#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Qué arreglo de INVENTARIO va primero. §13.

No escribe en la base. `database_writes: 0`.

Separado a propósito del ranking de campos: **una propiedad entera que no
tenemos vale más que un campo que le falta a una que sí tenemos**. Mezclarlos
en un solo número deja que 1.206 precios le ganen a 328 propiedades, y eso es
una decisión, no una cuenta.

Cada cluster lleva su causa verificada contra la fuente y el día en que se
verificó. Los que no la tienen no entran: quedan en
`reconciliar_inventario.py` hasta que alguien los diagnostique.

El orden sale de:

    REAL_MISSING × CONFIANZA × RIESGO_SISTEMICO / COSTO

`CONFIANZA` no es una impresión: es qué tan verificable es el número. ALTA
significa que se descargó la fuente y se contó. MEDIA, que hay un número pero
la evidencia no dice cómo se obtuvo. BAJA, que sale de lo que declara la propia
fuente, que ya se equivocó antes.

Uso:
    python scripts/inventory_fix_ranking.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

CERT = Path(r"D:\INMO CAPITAL\ERETZ_AGENCY_CERTIFICATION_20260827")

CONFIANZA = {"ALTA": 1.0, "MEDIA": 0.6, "BAJA": 0.3}
COSTO = {"BAJO": 1.0, "MEDIO": 2.0, "ALTO": 4.0}

CLUSTERS = [
    {
        "FIX_CLUSTER": "FORMA_DE_FICHA_NO_DECLARADA",
        "AGENCIES": ["bottai inmobiliaria", "cristina pozzobon inmobiliaria"],
        "REAL_MISSING_PROPERTIES": 328 + 9,
        "ROOT_CAUSE": (
            "el catalogo publica sus fichas con href RELATIVO y sin barra "
            "inicial -href=\"inmueble_6067\"- y la forma /inmueble_<num> no "
            "esta declarada para esa fuente. `_fichas_en` resuelve bien el "
            "relativo con urljoin; el que la rechaza es `_es_ficha_url`, "
            "porque ninguna forma global la cubre"),
        "ROOT_CAUSE_CONFIDENCE": "ALTA",
        "EVIDENCIA": (
            "2026-09-15: /inmuebles devuelve 563 KB con 329 rutas distintas "
            "/inmueble_<num>. Se bajaron tres y responden 200 con contenido "
            "PROPIO -se diferenciaron dos: 'MONTEVERA, 4 Hectareas con casa, "
            "Consultar' contra 'SAN JERONIMO 1771, Sembrando IX semipiso 3 "
            "dormitorios, $2.000.000'-. Con patron_ficha declarado, "
            "`_fichas_en` devuelve 328 y NO toma /contacto, /empresa, "
            "/quienes-somos ni los fideicomisos. "
            "`pozzobon` suma 9 por la misma via: /tomas-de-la-torre-63/ tiene "
            "por titulo una DIRECCION y un solo precio propio. "
            "CUIDADO con la forma: se probo tambien /<slug> a secas en "
            "`crestale` y devolvia 62 urls que son PAGINAS DE CATEGORIA "
            "-/venta-propiedades-rosario, titulo 'Propiedades en venta en "
            "Rosario', OCHO precios distintos en la misma pagina-. Esas 62 "
            "NO se cuentan. La forma segura es /<slug-con-id>, que exige un "
            "id numerico; /<slug> a secas arrastra el catalogo"),
        "HISTORICAL_REUSE": (
            "ALREADY_PRESENT: el mecanismo existe y se usa. `_patron_de()` lee "
            "`fuente.extra['patron_ficha']`, que viene del directorio de "
            "plataformas. Ya hay 65 sitios habilitados asi"),
        "FILES_TO_CHANGE": "agency_platform_directory.jsonl (DATOS)",
        "FINGERPRINT_RADIUS": "CERO — no se toca una linea de codigo",
        "EXPECTED_RECERTIFICATIONS": 1,
        "IMPLEMENTATION_COST": "BAJO",
        "RISK": (
            "BAJO. La forma /<slug-con-id> es amplia, y por eso cada url entra "
            "con por_forma=True y el guardian de detalle la valida una por "
            "una. Lo que NO esta medido: cuantas de las 328 pasan ese "
            "guardian. Hay que correrlo antes de prometer 328 publicables"),
        "SYSTEMIC_RISK": 1.0,
    },
    {
        "FIX_CLUSTER": "SUPERFICIE_DE_ENUMERACION_EQUIVOCADA",
        "AGENCIES": ["blangiforti propiedades"],
        "REAL_MISSING_PROPERTIES": 142,
        "ROOT_CAUSE": (
            "enumeramos la home y /propiedades, que muestran una SELECCION "
            "ROTATIVA de ~24 fichas. El catalogo real esta en /ventas, que "
            "devuelve 180 estables sin paginado, mas /alquileres con 3"),
        "ROOT_CAUSE_CONFIDENCE": "ALTA",
        "EVIDENCIA": (
            "2026-09-13: dos pedidos a la home separados por 4 segundos "
            "comparten 6 fichas de 24; dos pedidos a /ventas dan las mismas "
            "180. Los identificadores NO son efimeros, asi que no hay riesgo "
            "de duplicar en produccion"),
        "HISTORICAL_REUSE": "NEW_FIX_REQUIRED",
        "FILES_TO_CHANGE": "connectors/generico.py, descubrimiento de html_catalog",
        "FINGERPRINT_RADIUS": "strategy/generic/html_catalog — radio FAMILIA",
        "EXPECTED_RECERTIFICATIONS": 30,
        "IMPLEMENTATION_COST": "MEDIO",
        "RISK": (
            "MEDIO. Preferir el listado por operacion antes que la home cambia "
            "el punto de partida de 30 agencias, no de una"),
        "SYSTEMIC_RISK": 1.4,
    },
    {
        "FIX_CLUSTER": "WEB_REGISTRADA_CON_PAGINADO",
        "AGENCIES": ["cavacini propiedades"],
        "REAL_MISSING_PROPERTIES": 55,
        "ROOT_CAUSE": (
            "la web registrada no es la raiz del sitio: es una pagina interna "
            "con estado de paginado y filtros, "
            "…/site/properties/sale?opType=sale&page=3. Arrancamos desde la "
            "pagina 3 y enumeramos su resto"),
        "ROOT_CAUSE_CONFIDENCE": "ALTA",
        "EVIDENCIA": (
            "2026-09-14: el listado completo tiene 54 fichas de venta en 4 "
            "paginas (17+15+15+7) y 4 de alquiler. Enumeramos 3. Barrido sobre "
            "359 agencias: solo 5 tienen query string en la web registrada"),
        "HISTORICAL_REUSE": "NEW_FIX_REQUIRED",
        "FILES_TO_CHANGE": "la web declarada en el directorio (DATOS)",
        "FINGERPRINT_RADIUS": "CERO si se normaliza el dato, no el codigo",
        "EXPECTED_RECERTIFICATIONS": 1,
        "IMPLEMENTATION_COST": "BAJO",
        "RISK": "BAJO. Sacarle el paginado a una url es reversible y verificable",
        "SYSTEMIC_RISK": 1.0,
    },
    {
        "FIX_CLUSTER": "TAXONOMIA_WORDPRESS",
        "AGENCIES": ["cristina pozzobon inmobiliaria"],
        "REAL_MISSING_PROPERTIES": 80,
        "ROOT_CAUSE": (
            "WordPress sin plugin inmobiliario: enumeramos 0. Pero su "
            "wp-sitemap.xml declara taxonomias `tipo-de-propiedad` y "
            "`locacion`, y un wp-sitemap-posts-post-1.xml con 80 urls"),
        "ROOT_CAUSE_CONFIDENCE": "BAJA",
        "EVIDENCIA": (
            "las taxonomias prueban que son fichas y no articulos —un blog no "
            "declara 'tipo-de-propiedad'— pero las 80 salen del sitemap que "
            "declara la propia fuente, no de contarlas"),
        "HISTORICAL_REUSE": "NEW_FIX_REQUIRED",
        "FILES_TO_CHANGE": "descubrimiento wordpress",
        "FINGERPRINT_RADIUS": "connector/wordpress — radio FAMILIA",
        "EXPECTED_RECERTIFICATIONS": 20,
        "IMPLEMENTATION_COST": "MEDIO",
        "RISK": ("MEDIO. Un sitemap de posts puede traer articulos mezclados. "
                 "Y OJO: esta agencia tambien aparece en "
                 "FORMA_DE_FICHA_NO_DECLARADA con 9. Son DOS VIAS a la misma "
                 "agencia, no dos arreglos que se suman: si la forma entra "
                 "primero, lo que este cluster agrega son 71, no 80"),
        "SYSTEMIC_RISK": 1.0,
    },
    {
        "FIX_CLUSTER": "CONECTOR_EQUIVOCADO_POR_EL_PADRON",
        "AGENCIES": ["coldwell banker andes bienes raices"],
        "REAL_MISSING_PROPERTIES": 17,
        "ROOT_CAUSE": (
            "el directorio dice plataforma TOKKO y se elige el conector tokko, "
            "pero el sitio es PHP plano. El conector correcto no es el que "
            "dice el padron"),
        "ROOT_CAUSE_CONFIDENCE": "ALTA",
        "EVIDENCIA": "verificado contra la fuente el 2026-09-14",
        "HISTORICAL_REUSE": "NEW_FIX_REQUIRED",
        "FILES_TO_CHANGE": "la plataforma declarada en el directorio (DATOS)",
        "FINGERPRINT_RADIUS": "CERO si se corrige el dato",
        "EXPECTED_RECERTIFICATIONS": 1,
        "IMPLEMENTATION_COST": "BAJO",
        "RISK": "BAJO",
        "SYSTEMIC_RISK": 1.2,
    },
    {
        "FIX_CLUSTER": "WEB_REGISTRADA_ES_UN_PORTAL",
        "AGENCIES": ["alonso propiedades", "analia verga propiedades",
                     "emir elhelou estudio inmobiliario"],
        "REAL_MISSING_PROPERTIES": 0,
        "ROOT_CAUSE": (
            "la web registrada es un perfil dentro de un portal ajeno. Las 98 "
            "urls que enumeramos de cada una NO son propiedades: son las "
            "CATEGORIAS del portal -/departamentos/alquiler/mar-del-plata-, "
            "con un solo titulo distinto y cero precios"),
        "ROOT_CAUSE_CONFIDENCE": "ALTA",
        "EVIDENCIA": (
            "2026-09-15: las 98 de `alonso` tienen 1 titulo distinto "
            "-'JavaScript is disabled'-, 0 con precio, y sus urls son de Mar "
            "del Plata y Pilar cuando la inmobiliaria es de Lanus"),
        "HISTORICAL_REUSE": (
            "ALREADY_PRESENT parcial: `reclassify_portal_profiles.py` hace "
            "exactamente esto y ya reclasifico 513. Su lista de portales no "
            "conoce buscainmueble ni agroads, y dos de las tres no estan en su "
            "directorio de entrada con url"),
        "FILES_TO_CHANGE": "reclassify_portal_profiles.py (NO fingerprintado) + directorio",
        "FINGERPRINT_RADIUS": "CERO",
        "EXPECTED_RECERTIFICATIONS": 3,
        "IMPLEMENTATION_COST": "BAJO",
        "RISK": (
            "BAJO para el dato. NO recupera ninguna propiedad: saca 196 "
            "FALSAS del catalogo, que es correccion y no recuperacion"),
        "SYSTEMIC_RISK": 2.0,
    },
]


def puntaje(c: dict) -> float:
    return (c["REAL_MISSING_PROPERTIES"]
            * CONFIANZA[c["ROOT_CAUSE_CONFIDENCE"]]
            * c["SYSTEMIC_RISK"]
            / COSTO[c["IMPLEMENTATION_COST"]])


def main() -> int:
    print("=" * 74)
    print("INVENTORY_FIX_RANKING — propiedades ENTERAS que hoy no tenemos")
    print("=" * 74)
    for c in sorted(CLUSTERS, key=puntaje, reverse=True):
        print(f"\n{c['FIX_CLUSTER']}   [score {puntaje(c):.0f}]")
        print(f"   propiedades reales faltantes  {c['REAL_MISSING_PROPERTIES']}")
        print(f"   confianza de la causa         {c['ROOT_CAUSE_CONFIDENCE']}")
        print(f"   agencias                      {len(c['AGENCIES'])}: "
              f"{', '.join(c['AGENCIES'])}")
        print(f"   causa                         {c['ROOT_CAUSE'][:150]}")
        print(f"   evidencia                     {c['EVIDENCIA'][:150]}")
        print(f"   reuso historico               {c['HISTORICAL_REUSE'][:110]}")
        print(f"   archivos a cambiar            {c['FILES_TO_CHANGE']}")
        print(f"   radio de huella               {c['FINGERPRINT_RADIUS']}")
        print(f"   recertificaciones esperadas   {c['EXPECTED_RECERTIFICATIONS']}")
        print(f"   costo                         {c['IMPLEMENTATION_COST']}")
        print(f"   riesgo                        {c['RISK'][:150]}")

    # `pozzobon` esta en dos clusters por dos vias distintas. Sumar las dos
    # contaria 9 propiedades dos veces.
    SOLAPADAS = 9
    reales = sum(c["REAL_MISSING_PROPERTIES"] for c in CLUSTERS) - SOLAPADAS
    con_causa = sum(c["REAL_MISSING_PROPERTIES"] for c in CLUSTERS
                    if c["ROOT_CAUSE_CONFIDENCE"] == "ALTA")
    print("\n" + "=" * 74)
    print(f"propiedades en clusters CON causa escrita:        {reales}")
    print(f"de esas, con causa de confianza ALTA:             {con_causa}")
    print(f"total reconciliado de faltantes (todas las firmas): 687")
    print(f"o sea que {687 - reales} faltantes siguen SIN causa diagnosticada")
    print("=" * 74)
    print("\n  Comparar con FIELD_QUALITY no es sumar: son unidades distintas.")
    print("  Blanco recupera 1.206 PRECIOS de fichas que ya tenemos.")
    print("  Bottai recupera 328 PROPIEDADES que hoy no existen para nosotros.")
    print("  La regla del §11 dice cual pesa mas, y no es el numero mas grande.")

    salida = CERT / "ERETZ_INVENTORY_FIX_RANKING.json"
    salida.write_text(json.dumps(
        sorted(CLUSTERS, key=puntaje, reverse=True), ensure_ascii=False,
        indent=1), encoding="utf-8")
    print(f"\nartefacto: {salida}")
    print("\ndatabase_writes: 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
