"""El plan de escritura: orden, claves e idempotencia declaradas."""
from __future__ import annotations

import json

from scripts.plan_de_escritura import PLAN_VERSION, construir


def _artefactos(tmp_path):
    cert = tmp_path / "cert"
    cert.mkdir()
    (cert / "AGENCY_PROMOTION_GATE.jsonl").write_text("\n".join(
        json.dumps(f) for f in (
            {"canonical_agency_id": "a", "promotion_state": "SAFE_TO_PROMOTE"},
            {"canonical_agency_id": "b", "promotion_state": "SAFE_TO_PROMOTE"},
            {"canonical_agency_id": "c", "promotion_state": "REQUIRES_REVIEW"},
        )) + "\n", encoding="utf-8")
    (cert / "AGENCY_PROMOTION_WEB_RECHECK.jsonl").write_text(
        json.dumps({"canonical_agency_id": "b", "veredicto": "RECHAZADA"}) + "\n",
        encoding="utf-8")
    (cert / "AGENCY_MAIN_LINK_DRYRUN.jsonl").write_text(
        json.dumps({"canonical_agency_id": "z"}) + "\n", encoding="utf-8")

    geo = tmp_path / "geo"
    geo.mkdir()
    (geo / "CIUDAD_DRYRUN_AUDIT.jsonl").write_text("\n".join(
        json.dumps(f) for f in ({"apta_para_escritura": True},
                                {"apta_para_escritura": False})) + "\n",
        encoding="utf-8")

    pre = tmp_path / "pre"
    pre.mkdir()
    (pre / "PROPERTY_QUALITY_GATE.jsonl").write_text("\n".join(
        json.dumps(f) for f in ({"publicable": True}, {"publicable": True},
                                {"publicable": False})) + "\n",
        encoding="utf-8")
    # El directorio de plataformas: de aca sale de quien es cada web. Una
    # inmobiliaria cuya web cargada es de un tercero no aporta propiedades.
    directorio = tmp_path / "agency_platform_directory.jsonl"
    directorio.write_text(
        json.dumps({"canonical_agency_id": "a",
                    "web_kind": "OFFICIAL_WEB"}) + "\n",
        encoding="utf-8")
    return cert, geo, pre, directorio


def test_el_plan_no_escribe_nada(tmp_path):
    """Prepara; la ejecución requiere autorización humana explícita."""
    plan = construir(*_artefactos(tmp_path))
    assert plan["database_writes"] == 0
    assert plan["estado"] == "WAITING_USER_AUTHORIZATION"
    assert plan["plan_version"] == PLAN_VERSION


def test_una_web_rechazada_no_se_promueve(tmp_path):
    """La verificación se hizo abriendo la página: manda sobre el puntaje."""
    plan = construir(*_artefactos(tmp_path))
    promocion = [p for p in plan["pasos"] if "promover" in p["paso"]][0]
    assert promocion["filas"] == 1, "b fue rechazada al abrir su web"


def test_las_retenidas_de_geografia_no_entran(tmp_path):
    plan = construir(*_artefactos(tmp_path))
    geo = [p for p in plan["pasos"] if "geografia" in p["paso"]][0]
    assert geo["filas"] == 1


def test_las_inmobiliarias_van_antes_que_las_propiedades(tmp_path):
    """Las propiedades apuntan a esos ids: escribirlas antes las dejaría
    colgadas."""
    plan = construir(*_artefactos(tmp_path))
    orden = {p["paso"]: p["orden"] for p in plan["pasos"]}
    promover = next(o for p, o in orden.items() if "promover" in p)
    ingestar = next(o for p, o in orden.items() if "ingestar" in p)
    assert promover < ingestar


def test_cada_paso_declara_clave_precondicion_invariante_y_rollback(tmp_path):
    """Sin clave declarada, un reintento duplica en vez de actualizar; sin
    rollback, una interrupción a la mitad no se puede deshacer."""
    plan = construir(*_artefactos(tmp_path))
    for paso in plan["pasos"]:
        for campo in ("clave_de_upsert", "precondicion", "invariante",
                      "rollback", "por_que_primero"):
            assert paso.get(campo), f"{paso['paso']} sin {campo}"


def test_la_propiedad_incompleta_sigue_entrando(tmp_path):
    """La regla que no se negocia, escrita como invariante del paso."""
    plan = construir(*_artefactos(tmp_path))
    ingesta = [p for p in plan["pasos"] if "ingestar" in p["paso"]][0]
    assert "no existencia" in ingesta["invariante"].replace(",", "")
