#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""La base de firmas de defectos. §20, §21, §78.4.

No escribe en la base. `database_writes: 0`. Lee las diferidas y los
resultados, agrupa por PATRÓN y deja el artefacto.

El objetivo está escrito en el §20 y es medible: **la cuarta agencia con el
mismo bug no debería requerir un rediagnóstico completo.** Hoy sí lo requiere,
y se nota: la familia de perfiles de portal se diagnosticó SIETE veces, una por
agencia, y costó más de 27 h de cola parada en 48 h.

Agrupa por patrón y no por agencia (§21). Dos agencias con la misma causa son
un defecto, no dos. Lo que define el patrón es la combinación de:

    componente + estrategia + campo afectado

y no el nombre de la inmobiliaria, que es lo que el archivo de diferidas usa
como clave.

Lo que este script NO hace es inventar causas. Si una diferida no dice contra
qué se verificó, el patrón queda `SIN_DIAGNOSTICO` y se cuenta aparte: un
patrón sin causa no es conocimiento, es una lista de pendientes.

Uso:
    python scripts/defect_kb.py
    python scripts/defect_kb.py --familia portal
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

CERT = Path(r"D:\INMO CAPITAL\ERETZ_AGENCY_CERTIFICATION_20260827")
SALIDA = CERT / "ERETZ_DEFECT_KB.jsonl"

# Familias: el agrupador de más alto nivel. Sale de la evidencia escrita en la
# diferida, no del nombre del componente, porque el mismo componente aparece en
# causas distintas.
FAMILIAS = [
    ("PORTAL_COMO_FUENTE",
     r"(?i)perfil (dentro de un |en un )?portal|portal ajeno|"
     r"NO ES SU SITIO|url declarada es UNA FICHA|seccion de terceros"),
    ("SUPERFICIE_DE_ENUMERACION",
     r"(?i)seleccion rotativa|superficie equivocada|el catalogo real esta en|"
     r"enumerando la superficie"),
    ("FORMA_DE_URL_NO_RECONOCIDA",
     # `SLUGS` en plural: la primera version decia `slug` y por eso doce
     # agencias con la misma causa quedaban SIN_CLASIFICAR. Un agrupador que
     # no agrupa es peor que no tenerlo, porque parece que agrupo.
     r"(?i)slugs? en la raiz|no reconoce la forma|forma de sus urls|"
     r"marcador|patron_ficha|slug en la raiz"),
    ("URL_CON_QUERY_STRING",
     r"(?i)\?recordid|\?id=|query string|inmueble_ver\.php|detalle\.php"),
    ("PLATAFORMA_MAL_CLASIFICADA",
     r"(?i)plataforma UNKNOWN|el directorio dice plataforma|"
     r"conector elegido es|consume la API de|no es un frontend de"),
    ("CAMPO_EN_LUGAR_EQUIVOCADO",
     r"(?i)titulo editorial|lo buscamos en el lugar equivocado|"
     r"lo saca(mos)? del|esta en el <title>|en su propio <title>"),
    ("DATO_DENTRO_DE_JAVASCRIPT",
     r"(?i)initMap|dentro de un script|en el javascript|bloque de script"),
    ("CAMPO_EN_NODO_SEPARADO",
     r"(?i)nodos separados|rotulo y (el )?valor|etiqueta y el valor"),
    ("DATO_SOLO_EN_PROSA",
     r"(?i)dentro de la descripcion|solo en la prosa|escribio las medidas|"
     r"texto libre"),
    ("FUENTE_NO_PUBLICA_EL_CAMPO",
     r"(?i)no publica|no aplica|un lote no tiene|el campo no falta"),
    ("PAGINA_CONTENEDORA",
     r"(?i)pagina de categoria|vista filtrada|emprendimiento|barrio privado|"
     r"404 blando|JavaScript is disabled"),
    ("PRESUPUESTO_AGOTADO",
     r"(?i)presupuesto agotado|ran out of time budget|se quedo sin tiempo"),
    ("REGISTRO_BASURA_DE_LA_FUENTE",
     r"(?i)relleno|ya vendid|se encuentra Vendida|numero mal formado|"
     r"dos puntos"),
]


# Firmas MEDIDAS contra el sitio, que le ganan a cualquier regex sobre prosa.
#
# La clasificación por texto es frágil y este archivo ya lo pagó: la primera
# versión decía `slug` en singular y doce agencias con la misma causa quedaron
# SIN_CLASIFICAR. Cuando existe una señal que salió de abrir el sitio, esa
# manda, porque no depende de cómo redacté el diagnóstico.
FIRMA_MEDIDA_A_FAMILIA = {
    "FUENTE_ES_PORTAL_AJENO": "PORTAL_COMO_FUENTE",
    "CATALOGO_POR_POST": "CATALOGO_PEDIDO_POR_POST",
    "NAVEGACION_SOLO_JAVASCRIPT": "NAVEGACION_SOLO_JAVASCRIPT",
    "SITEMAP_CON_FICHAS": "SITEMAP_IGNORADO_POR_LA_ESTRATEGIA",
    "API_DE_TERCEROS": "PLATAFORMA_MAL_CLASIFICADA",
    "CONTENEDOR_VACIO_JS": "CATALOGO_QUE_RELLENA_JAVASCRIPT",
}

# Estas NO son diagnósticos y no deben tratarse como tales.
#
# `SIN_RASTRO_DE_CATALOGO` significa que fuimos al sitio y no se ve catálogo.
# Es **evidencia**, y por eso merece su propio cajón, pero no explica nada: la
# pregunta que abre no es "qué conector hay que arreglar" sino la del §71,
# "¿esta agencia tiene inventario, y si no, cuál es su estado terminal
# justificable?". Meterlas entre las familias diagnosticadas convertiría un
# hueco de evidencia en progreso aparente, que es peor que dejar el hueco.
FIRMA_MEDIDA_SIN_DIAGNOSTICO = {
    "SIN_RASTRO_DE_CATALOGO": "SIN_CATALOGO_VISIBLE_FALTA_DECIDIR_TERMINAL",
    "SIN_CONTENIDO": "SIN_CATALOGO_VISIBLE_FALTA_DECIDIR_TERMINAL",
    "NO_RESPONDE": "FUENTE_NO_RESPONDE",
}


def firmas_medidas() -> dict[str, str]:
    """Lo que `firma_navegacion_javascript.py` midió abriendo cada sitio."""
    ruta = CERT / "ERETZ_FIRMA_NAVEGACION_JS.jsonl"
    medidas: dict[str, str] = {}
    if not ruta.exists():
        return medidas
    for linea in ruta.open(encoding="utf-8", errors="replace"):
        linea = linea.strip()
        if not linea:
            continue
        try:
            fila = json.loads(linea)
        except ValueError:
            continue
        agencia, firma = fila.get("agency_id"), fila.get("firma")
        if agencia and firma:
            medidas[agencia.split(":")[-1].lower()] = firma
    return medidas


def familia_de(texto: str, agencia: str = "",
               medidas: dict[str, str] | None = None) -> str:
    """La señal medida primero; el texto sólo si no hay medición útil."""
    firma = (medidas or {}).get((agencia or "").split(":")[-1].lower())
    if firma in FIRMA_MEDIDA_A_FAMILIA:
        return FIRMA_MEDIDA_A_FAMILIA[firma]
    for nombre, patron in FAMILIAS:
        if re.search(patron, texto or ""):
            return nombre
    # Recién acá, cuando ni la medición diagnóstica ni el texto alcanzaron, se
    # usa el cajón honesto de la medición.
    if firma in FIRMA_MEDIDA_SIN_DIAGNOSTICO:
        return FIRMA_MEDIDA_SIN_DIAGNOSTICO[firma]
    return "SIN_CLASIFICAR"


def firma_id(familia: str, componente: str, estrategia: str) -> str:
    crudo = f"{familia}|{componente}|{estrategia}"
    return hashlib.sha256(crudo.encode()).hexdigest()[:12]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--familia")
    args = ap.parse_args()

    ult = {}
    for l in (CERT / "AGENCY_CERTIFICATION_RESULTS.jsonl").read_text(
            encoding="utf-8", errors="replace").splitlines():
        if not l.strip():
            continue
        try:
            r = json.loads(l)
        except ValueError:
            continue
        if r.get("canonical_agency_id"):
            ult[r["canonical_agency_id"]] = r

    difs = []
    for l in (CERT / "AGENCY_DEFECTS_DIFERIDOS.jsonl").read_text(
            encoding="utf-8", errors="replace").splitlines():
        if l.strip():
            try:
                difs.append(json.loads(l))
            except ValueError:
                continue

    medidas = firmas_medidas()

    firmas: dict[str, dict] = {}
    for f in difs:
        a = f.get("canonical_agency_id")
        r = ult.get(a) or {}
        texto = (f.get("diagnostico") or "") + " " + (f.get("por_que_se_difiere") or "")
        familia = familia_de(texto, a or "", medidas)
        comp = f.get("componente") or "(sin firma)"
        est = r.get("connector_strategy") or "(sin estrategia)"
        sid = firma_id(familia, comp, est)
        d = firmas.setdefault(sid, {
            "signature_id": sid, "family": familia, "component": comp,
            "strategy": est, "agencies": [], "affected_properties": 0,
            "first_seen": None, "last_seen": None,
            "root_cause": None, "evidence": None,
            "status": "NEW", "recert_required": None,
        })
        d["agencies"].append(a.split(":")[-1])
        d["affected_properties"] += (r.get("enumeration_audit") or {}).get("enumerated") or 0
        cuando = f.get("cuando")
        if cuando:
            d["first_seen"] = min(d["first_seen"] or cuando, cuando)
            d["last_seen"] = max(d["last_seen"] or cuando, cuando)
        # La causa se toma de la diferida MAS LARGA del grupo: es la que mas
        # evidencia trae. No se promedian textos ni se inventa un resumen.
        if f.get("firma_verificada_contra_la_fuente") and (
                not d["evidence"] or len(f.get("diagnostico") or "") > len(d["evidence"])):
            d["evidence"] = f.get("diagnostico")
            d["root_cause"] = (f.get("por_que_se_difiere") or "")[:200]
            d["status"] = "DIAGNOSED"

    for d in firmas.values():
        if d["status"] == "NEW":
            d["status"] = "SIN_DIAGNOSTICO"
        # Si el arreglo toca codigo compartido, recertificar es obligatorio.
        d["recert_required"] = bool(
            d["component"] and d["component"] not in
            ("extraccion_de_baja_magnitud", "sitio_externo"))

    filas = sorted(firmas.values(),
                   key=lambda d: (-len(d["agencies"]), -d["affected_properties"]))
    if args.familia:
        filas = [d for d in filas
                 if args.familia.lower() in d["family"].lower()]

    SALIDA.write_text("".join(json.dumps(d, ensure_ascii=False) + "\n"
                              for d in filas), encoding="utf-8")

    print(f"diferidas leidas: {len(difs)}")
    print(f"firmas distintas: {len(firmas)}\n")
    print(f"{'familia':30} {'componente':34} {'ag':>3} {'props':>7}  estado")
    for d in filas:
        print(f"{d['family'][:28]:30} {d['component'][:32]:34} "
              f"{len(d['agencies']):3} {d['affected_properties']:7,}  {d['status']}")

    print("\n" + "=" * 74)
    print("POR FAMILIA — esto es lo que un arreglo puede resolver de una vez")
    print("=" * 74)
    porf = defaultdict(lambda: {"ag": set(), "props": 0, "firmas": 0})
    for d in filas:
        p = porf[d["family"]]
        p["ag"].update(d["agencies"])
        p["props"] += d["affected_properties"]
        p["firmas"] += 1
    for fam, p in sorted(porf.items(), key=lambda kv: -len(kv[1]["ag"])):
        print(f"{fam[:34]:36} {len(p['ag']):3} agencias  {p['props']:7,} props  "
              f"{p['firmas']} firmas")

    sin = [d for d in filas if d["status"] == "SIN_DIAGNOSTICO"]
    print(f"\n  firmas SIN causa escrita: {len(sin)} "
          f"({sum(len(d['agencies']) for d in sin)} agencias)")
    print("  Un patron sin causa no es conocimiento: es una lista de pendientes.")

    grandes = [d for d in filas if len(d["agencies"]) >= 4]
    print(f"\n  firmas con 4 o mas agencias: {len(grandes)}")
    print("  El §20 pide que la CUARTA agencia no requiera rediagnostico.")
    for d in grandes:
        print(f"     {d['family'][:30]:32} {len(d['agencies'])} agencias: "
              f"{', '.join(d['agencies'][:5])}")

    print(f"\nartefacto: {SALIDA}")
    print("\ndatabase_writes: 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
