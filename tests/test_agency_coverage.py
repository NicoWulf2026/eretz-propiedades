# -*- coding: utf-8 -*-
"""Tests del tooling de cobertura de inmobiliarias.

Cubren los casos que rompieron de verdad durante la campana (entidades HTML,
apostrofos, parentesis, sufijos societarios) y las reglas que impiden que algo
se declare nuevo o se fusione sin evidencia.
"""
from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


cw = _load("agency_crosswalk")
fr = _load("franchise_analysis")
imp = _load("import_roomix_coverage_to_staging")


# ------------------------------------------------------------- normalizacion
@pytest.mark.parametrize("a,b", [
    # La entidad HTML rompia el match: el apostrofo se volvia un token "x27".
    ("Estela D&#x27;onofrio Propiedades", "ESTELA D'ONOFRIO Propiedades"),
    ("O&#x27;Reilly Inmobiliaria", "O'Reilly Inmobiliaria"),
    # Acentos.
    ("Lopez Baena Propiedades", "López Baena Propiedades"),
    # Calificador entre parentesis.
    ("Marcel Gestion Inmobiliaria", "Marcel Gestion Inmobiliaria (Pinamar)"),
    # Sufijo societario final.
    ("Benuzzi Inmobiliaria SA", "Benuzzi inmobiliaria"),
    ("Perez Propiedades SRL", "Perez Propiedades"),
])
def test_nombres_equivalentes_normalizan_igual(a, b):
    assert cw.norm_name(a) == cw.norm_name(b)


def test_normalizacion_no_colapsa_entidades_distintas():
    # Dos oficinas reales distintas no deben volverse el mismo nombre.
    assert cw.norm_name("RE/MAX Uno San Isidro") != cw.norm_name("RE/MAX Uno IV Colegiales")
    assert cw.norm_name("Mauro Sola Negocios Inmobiliarios") != cw.norm_name(
        "Mauro Musso Negocios Inmobiliarios")


def test_raw_se_conserva_intacto():
    raw = "ESTELA D'ONOFRIO Propiedades"
    assert cw.norm_name(raw) != raw  # normaliza
    row = imp.build_row({"agent_id": "x", "raw_name": raw, "evidence_url": "u",
                         "listings_observed": 1, "match_state": "NEW_HIGH_CONFIDENCE",
                         "match_signal": "s"}, None)
    assert row["nombre"] == raw
    assert row["metadata_zonaprop"]["roomix_raw_name"] == raw


# ------------------------------------------------------------- clasificacion
@pytest.mark.parametrize("name,kind", [
    ("Mizrahi Real Estate", "INMOBILIARIA"),
    ("Alberto Dacal Propiedades", "INMOBILIARIA"),
    ("RE/MAX Uno - San Isidro", "RED_FRANQUICIA"),
    ("Century 21 Errico", "RED_FRANQUICIA"),
    ("Coldwell Banker Acqua", "RED_FRANQUICIA"),
    ("Grupo Constructor Sur Desarrollos", "DESARROLLADORA"),
    ("Dueño directo", "DUENO_DIRECTO"),
])
def test_clasificacion_por_tipo(name, kind):
    assert cw.classify(name) == kind


def test_agente_individual_no_es_inmobiliaria():
    assert cw.classify("Juan Perez") == "AGENTE"
    assert cw.classify("Maria Lucia Gomez") == "AGENTE"


# --------------------------------------------------------------- basura
@pytest.mark.parametrize("name,expected", [
    ("", True), ("-", True), ("null", True), ("Usuario", True),
    ("Particular", True), ("roomix", True), ("12345", True),
    ("<div>x</div>", True),
    ("x" * 130, True),
    ("Mizrahi Real Estate", False),
])
def test_deteccion_de_basura(name, expected):
    bad, _ = cw.is_garbage(name)
    assert bad is expected


# --------------------------------------------------------------- matching
def _idx(names):
    eretz = [{"slug": f"s{i}", "name": n, "location": None, "listings": 1}
             for i, n in enumerate(names)]
    return cw.build_index(eretz)


def test_match_exacto():
    idx = _idx(["Mizrahi Real Estate"])
    state, cands, _ = cw.match({"raw_name": "Mizrahi Real Estate"}, idx)
    assert state == "EXACT_EXISTING" and len(cands) == 1


def test_entidad_html_en_eretz_ahora_matchea():
    idx = _idx(["Estela D&#x27;onofrio Propiedades"])
    state, _, _ = cw.match({"raw_name": "ESTELA D'ONOFRIO Propiedades"}, idx)
    assert state == "EXACT_EXISTING"


def test_vecino_cercano_no_puede_declararse_nuevo():
    idx = _idx(["Constantino L. Osso - Negocios Inmobiliarios"])
    state, cands, signal = cw.match({"raw_name": "Constantino Osso Negocios Inmobiliarios"}, idx)
    assert state != "NEW_HIGH_CONFIDENCE"
    assert cands, "debe conservar el vecino como evidencia"


def test_colision_muchos_a_uno_queda_ambigua():
    # Dos publicadores distintos que caen cerca del mismo registro de ERETZ:
    # fusionar cualquiera seria incorrecto.
    idx = _idx(["Mauro Negocios Inmobiliarios"])
    s1, _, _ = cw.match({"raw_name": "Mauro Sola Negocios Inmobiliarios"}, idx)
    s2, _, _ = cw.match({"raw_name": "Mauro Musso Negocios Inmobiliarios"}, idx)
    assert s1 != "NEW_HIGH_CONFIDENCE" and s2 != "NEW_HIGH_CONFIDENCE"


def test_multiples_candidatos_es_ambiguo():
    idx = _idx(["Perez Propiedades", "Perez Propiedades"])
    state, _, _ = cw.match({"raw_name": "Perez Propiedades"}, idx)
    assert state == "AMBIGUOUS"


def test_nucleo_corto_no_alcanza_para_decidir():
    idx = _idx(["Otra Cosa Propiedades"])
    state, _, _ = cw.match({"raw_name": "AB Propiedades"}, idx)
    assert state == "INSUFFICIENT_DATA"


def test_sin_parecido_es_nueva():
    idx = _idx(["Alberto Dacal Propiedades"])
    state, _, _ = cw.match({"raw_name": "Zzyzx Bienes Raices Patagonia"}, idx)
    assert state == "NEW_HIGH_CONFIDENCE"


# --------------------------------------------------------------- franquicias
def test_marca_y_oficina_se_separan():
    brand, suffix = fr.brand_of("RE/MAX Uno - San Isidro")
    assert brand == "RE/MAX" and "san isidro" in suffix


def test_oficinas_distintas_no_colapsan():
    _, s1 = fr.brand_of("RE/MAX Uno - San Isidro")
    _, s2 = fr.brand_of("RE/MAX Uno IV Colegiales")
    assert s1 and s2 and s1 != s2


def test_marca_madre_sin_sufijo():
    brand, suffix = fr.brand_of("RE/MAX")
    assert brand == "RE/MAX" and suffix == ""


def test_c21_se_reconoce_en_sus_variantes():
    for name in ("Century 21 Errico", "C21 Errico Ostrofsky", "Century21 Norte"):
        brand, _ = fr.brand_of(name)
        assert brand == "Century 21", name


# --------------------------------------------------------------- matriculas
def test_extraccion_de_matricula():
    lic = imp.extract_licences("Juan Pablo Sanguinetti CMCPSI 6449 CUCICBA 6630 Pilar")
    assert "CMCPSI 6449" in lic and "CUCICBA 6630" in lic


def test_nombre_limpio_saca_la_matricula():
    limpio = imp.clean_name("Fernando J Vaz Bienes Raices CPI N 8465")
    assert "8465" not in limpio and "Fernando" in limpio


# --------------------------------------------------------------- fila destino
def test_fila_usa_solo_columnas_reales():
    row = imp.build_row({"agent_id": "a", "raw_name": "Zeta Propiedades",
                         "evidence_url": "u", "listings_observed": 3,
                         "match_state": "NEW_HIGH_CONFIDENCE", "match_signal": "x"}, None)
    assert set(row) == set(imp.COLUMNS)
    assert row["fuente"] == imp.SOURCE_NAME
    assert row["metadata_zonaprop"]["discovered_via"] == "roomix_public_property_page"


def test_provenance_completa():
    row = imp.build_row({"agent_id": "abc", "raw_name": "Zeta Propiedades",
                         "evidence_url": "https://x/y", "listings_observed": 3,
                         "match_state": "NEW_HIGH_CONFIDENCE", "match_signal": "sin_coincidencia",
                         "matching_version": "v1"}, {"brand": "RE/MAX", "modelado": "POR_OFICINA"})
    m = row["metadata_zonaprop"]
    for k in ("discovered_via", "roomix_agent_id", "roomix_raw_name", "evidence_url",
              "listings_observed", "match_state", "match_signal", "matcher_version", "franchise"):
        assert k in m, k


def test_clave_de_dedupe_es_estable():
    a = imp.build_row({"agent_id": "1", "raw_name": "Zeta Propiedades SA",
                       "evidence_url": "", "listings_observed": 1,
                       "match_state": "NEW_HIGH_CONFIDENCE", "match_signal": ""}, None)
    b = imp.build_row({"agent_id": "2", "raw_name": "Zeta Propiedades",
                       "evidence_url": "", "listings_observed": 1,
                       "match_state": "NEW_HIGH_CONFIDENCE", "match_signal": ""}, None)
    # Misma entidad escrita distinto: misma clave logica, no se duplica.
    assert a["nombre_normalizado"] == b["nombre_normalizado"]


# ------------------------------------------------------------------ rollout
ro = _load("agency_coverage_rollout")


def test_canary_es_representativo_y_determinista():
    rows = []
    for i in range(40):
        brand = ["RE/MAX", "Century 21", None, None][i % 4]
        rows.append({
            "nombre_normalizado": f"agencia {i}",
            "metadata_zonaprop": {"franchise": {"brand": brand} if brand else None},
        })
    a = ro.pick_canary(rows, 12)
    b = ro.pick_canary(rows, 12)
    assert [r["nombre_normalizado"] for r in a] == [r["nombre_normalizado"] for r in b]
    marcas = {(r["metadata_zonaprop"].get("franchise") or {}).get("brand") for r in a}
    assert len([m for m in marcas if m]) >= 2, "debe incluir mas de una franquicia"
    assert None in marcas, "debe incluir independientes"


def test_canary_no_repite_entidad():
    rows = [{"nombre_normalizado": "misma", "metadata_zonaprop": {"franchise": None}}
            for _ in range(10)]
    assert len(ro.pick_canary(rows, 12)) == 1


class _Cur:
    """Cursor falso: registra el SQL en vez de ejecutarlo."""
    def __init__(self):
        self.sql = []
        self.rowcount = 1

    def execute(self, q, params=None):
        self.sql.append((q, params))


def test_insert_solo_usa_columnas_existentes():
    cur = _Cur()
    row = {"nombre": "X", "fuente": "roomix_coverage_v1", "columna_inexistente": "y"}
    ro.insert_batch(cur, "public", {"nombre", "fuente"}, [row])
    q = cur.sql[0][0]
    assert "columna_inexistente" not in q
    assert '"nombre"' in q and '"fuente"' in q


def test_insert_es_idempotente_por_construccion():
    cur = _Cur()
    ro.insert_batch(cur, "public", {"nombre"}, [{"nombre": "X"}])
    assert "on conflict do nothing" in cur.sql[0][0].lower()


def test_insert_solo_escribe_en_staging():
    cur = _Cur()
    ro.insert_batch(cur, "public", {"nombre"}, [{"nombre": "X"}])
    q = cur.sql[0][0].lower()
    assert "inmobiliarias_staging" in q
    assert "inmobiliarias_main" not in q
    assert " update " not in q and "delete" not in q


def test_jsonb_se_serializa():
    cur = _Cur()
    ro.insert_batch(cur, "public", {"metadata_zonaprop"},
                    [{"metadata_zonaprop": {"discovered_via": "roomix"}}])
    params = cur.sql[0][1]
    assert isinstance(params[0], str) and "discovered_via" in params[0]


def test_variable_de_entorno_es_la_dedicada():
    assert ro.ENV_VAR == "ERETZ_AGENCY_COVERAGE_DATABASE_URL"
    assert ro.ENV_VAR not in ("SUPABASE_DATABASE_URL", "INTERNAL_DB_URL")


# ------------------------------------- puente temporal de Preview
rp = _load("agency_coverage_rollout_via_preview")

FRONT = ROOT / "frontend" / "src"
WRITER = (FRONT / "lib" / "coverage-writer.ts").read_text(encoding="utf-8")
ROUTE = (FRONT / "app" / "api" / "agency-coverage" / "route.ts").read_text(encoding="utf-8")


def test_la_candidate_key_es_el_id_de_publicador_y_no_el_nombre():
    """Estable entre corridas y ajena a como se limpie el nombre."""
    it = rp.item_of({"nombre": "X", "fuente": "lo_que_sea",
                     "metadata_zonaprop": {"roomix_agent_id": "abc-123"}})
    assert it["candidateKey"] == "abc-123"


def test_el_cliente_no_manda_la_fuente():
    """La fija la funcion server-side; mandarla abriria la puerta a escribir en
    nombre de otro import."""
    it = rp.item_of({"nombre": "X", "fuente": "impostor",
                     "metadata_zonaprop": {"roomix_agent_id": "k"}})
    assert "fuente" not in it["payload"]
    assert it["payload"]["nombre"] == "X"


def test_el_campo_de_estado_se_descubre_no_se_asume():
    assert rp.status_field([{"id": 1, "status": "STAGED"}]) == "status"
    assert rp.status_field([{"id": 1, "resultado": "DUPLICADA"}]) == "resultado"
    assert rp.status_field([]) is None


def test_el_tally_cuenta_los_fallos_de_transporte_aparte():
    res = [{"ok": True, "rows": [{"status": "STAGED"}]},
           {"ok": True, "rows": [{"status": "STAGED"}]},
           {"ok": False, "error": "boom"},
           {"ok": True, "rows": []}]
    t = rp.tally(res, "status")
    assert t["STAGED"] == 2 and t["ERROR_TRANSPORTE"] == 1 and t["SIN_FILA"] == 1


# --- garantias sobre el puente, verificadas en el propio codigo ---

def test_el_puente_solo_puede_ejecutar_las_sentencias_declaradas():
    """Ningun request elige funcion, tabla ni columna: las sentencias son
    constantes del modulo y lo unico que viaja desde afuera son los dos
    parametros ligados de stage."""
    cuerpo = WRITER[WRITER.index("const RPC = {"):WRITER.index("} as const;")]
    assert "${" not in cuerpo, "no puede haber interpolacion en las sentencias"
    llamadas = set(re.findall(r"eretz_agency_coverage_\w+", WRITER))
    assert llamadas == {"eretz_agency_coverage_preflight_v1",
                        "eretz_agency_coverage_snapshot_v1",
                        "eretz_agency_coverage_stage_v1"}


def test_el_puente_no_hace_sql_directo_contra_las_tablas():
    """El rol no se usa para tocar main ni staging por fuera de las funciones.
    Lo unico que las nombra es el chequeo de privilegios, que consulta el
    catalogo y no lee ninguna fila."""
    directo = re.findall(r"(?i)(?:from|into|update|join)\s+public\.inmobiliarias_\w+", WRITER)
    assert directo == [], directo
    bajo = WRITER.lower()
    assert "insert into" not in bajo
    assert "update public" not in bajo
    assert "delete from" not in bajo


def test_ningun_secreto_puede_salir_en_un_error():
    assert "safeError" in WRITER
    assert "<redacted>" in WRITER and "<dsn>" in WRITER
    assert "console.log" not in WRITER and "console.log" not in ROUTE
    assert "ERETZ_WRITE_DATABASE_URL" not in ROUTE


def test_la_ruta_es_solo_de_preview_y_en_production_no_existe():
    assert 'process.env.VERCEL_ENV === "preview"' in WRITER
    assert "isPreviewEnvironment" in ROUTE
    # 404 y no 403: en Production la ruta no se anuncia.
    assert "status: 404" in ROUTE and "not found" in ROUTE


def _sin_comentarios(ts: str) -> str:
    """Los comentarios explican el mecanismo y nombran cosas que el codigo no
    debe hacer; mirarlos daria falsos positivos."""
    ts = re.sub(r"/\*.*?\*/", "", ts, flags=re.S)
    return re.sub(r"^\s*//.*$", "", ts, flags=re.M)


def test_la_ruta_no_replica_el_dedupe():
    """Replicarlo daria una segunda respuesta que puede discrepar de la de la
    funcion, y la que manda es la de la funcion."""
    codigo = _sin_comentarios(ROUTE).lower()
    assert "advisory" not in codigo
    assert "on conflict" not in codigo
