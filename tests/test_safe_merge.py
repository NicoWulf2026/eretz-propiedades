from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import Mock

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRAPER_ROOT = REPO_ROOT / "scraper"
if str(SCRAPER_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRAPER_ROOT))

from clients import SupabaseClient  # noqa: E402
from models import _compute_hash_dedup  # noqa: E402
from safe_merge import (  # noqa: E402
    ACCEPTED_IMPROVEMENT,
    ACCEPTED_INSERT,
    ACCEPTED_SOURCE_CHANGE,
    REJECTED_AMBIGUOUS_IDENTITY,
    REJECTED_CROSS_PROPERTY_CONTAMINATION,
    REJECTED_PLACEHOLDER,
    UNCHANGED_EQUAL,
    build_merge_plan,
)


def incoming(**overrides):
    payload = {
        "inmobiliaria_id": 10,
        "url": "https://www.agencia.test/propiedad/123?utm_source=x",
        "titulo": "Casa luminosa en Palermo",
        "descripcion": "Casa luminosa con patio propio, tres ambientes y excelente estado.",
        "precio": 120_000,
        "moneda": "USD",
        "tipo_propiedad": "casa",
        "operacion": "venta",
        "ambientes": 3,
        "dormitorios": 2,
        "banos": 1,
        "superficie_total": 90,
        "direccion": "Av. Santa Fe 3200",
        "barrio": "Palermo",
        "ciudad": "Ciudad Autónoma de Buenos Aires",
        "latitud": -34.588,
        "longitud": -58.41,
        "imagenes": ["https://cdn.agencia.test/propiedad/123/frente.jpg"],
        "fuente_extraccion": "agencia_test",
        "estado": "activa",
    }
    payload.update(overrides)
    payload["hash_dedup"] = _compute_hash_dedup(
        payload.get("inmobiliaria_id"), payload.get("url")
    )
    return payload


def existing(**overrides):
    payload = incoming()
    payload.update(
        {
            "id": 500,
            "url_normalizada": "agencia.test/propiedad/123",
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
        }
    )
    payload.update(overrides)
    return payload


def decision(plan, field):
    return next(item for item in plan["audit"] if item["field"] == field)


def test_new_property_gets_sanitized_insert_and_field_audit():
    plan = build_merge_plan(incoming(), [], source_id="10")
    assert plan["status"] == "insert"
    assert plan["payload"]["url_normalizada"] == "agencia.test/propiedad/123"
    assert plan["payload"]["hash_dedup"] == incoming()["hash_dedup"]
    assert all(item["decision"] == ACCEPTED_INSERT for item in plan["audit"])


def test_new_property_uses_explicit_unknown_operation_state():
    plan = build_merge_plan(incoming(operacion=None), [], source_id="10")

    assert plan["status"] == "insert"
    assert plan["payload"]["operacion"] == "consultar"


def test_new_property_does_not_persist_operation_as_title():
    plan = build_merge_plan(incoming(titulo="Venta"), [], source_id="10")

    assert plan["status"] == "insert"
    assert plan["payload"]["titulo"] is None


def test_unambiguous_existing_property_is_matched():
    plan = build_merge_plan(incoming(), [existing()], source_id="10")
    assert plan["status"] == "matched"
    assert plan["property"]["id"] == 500
    assert plan["patch"] == {}


def test_normalized_url_ignores_www_slash_and_tracking_query():
    old = existing(url="https://agencia.test/propiedad/123/")
    plan = build_merge_plan(incoming(), [old], source_id="10")
    assert plan["status"] == "matched"


def test_external_id_is_compatible_identity_evidence():
    new = incoming(id_externo=" ABC-123 ")
    old = existing(id_externo="abc-123")
    plan = build_merge_plan(new, [old], source_id="10")
    assert plan["status"] == "matched"


def test_compatible_hash_is_required_when_present():
    old = existing(hash_dedup="contradictory-hash")
    plan = build_merge_plan(incoming(), [old], source_id="10")
    assert plan["status"] == "rejected"
    assert decision(plan, "__identity__")["decision"] == REJECTED_CROSS_PROPERTY_CONTAMINATION


def test_multiple_candidates_reject_ambiguous_identity():
    candidates = [existing(id=1, hash_dedup=""), existing(id=2, hash_dedup="")]
    plan = build_merge_plan(incoming(), candidates, source_id="10")
    assert plan["status"] == "rejected"
    assert decision(plan, "__identity__")["decision"] == REJECTED_AMBIGUOUS_IDENTITY


def test_fk_incompatible_candidate_rejects_cross_property_write():
    other_agency = existing(id=900, inmobiliaria_id=99, hash_dedup="")
    plan = build_merge_plan(incoming(), [other_agency], source_id="10")
    assert plan["status"] == "rejected"
    assert decision(plan, "__identity__")["decision"] == REJECTED_CROSS_PROPERTY_CONTAMINATION


def test_source_id_must_match_canonical_agency_id():
    plan = build_merge_plan(incoming(), [], source_id="77")
    assert plan["status"] == "rejected"
    assert decision(plan, "__identity__")["decision"] == REJECTED_AMBIGUOUS_IDENTITY


def test_preflight_verified_source_id_space_can_map_to_canonical_agency():
    plan = build_merge_plan(
        incoming(),
        [],
        source_id="1976",
        identity_agency_id="10",
    )

    assert plan["status"] == "insert"


def test_preflight_verified_agency_still_rejects_wrong_payload_fk():
    plan = build_merge_plan(
        incoming(inmobiliaria_id=99),
        [],
        source_id="1976",
        identity_agency_id="10",
    )

    assert plan["status"] == "rejected"
    assert decision(plan, "__identity__")["decision"] == REJECTED_AMBIGUOUS_IDENTITY


@pytest.mark.parametrize(
    ("field", "old_value", "new_value"),
    [
        ("titulo", "Sin título", "Casa luminosa en Palermo"),
        ("descripcion", "cookie", "Casa luminosa con patio propio, tres ambientes y excelente estado."),
        ("ambientes", None, 3),
        ("direccion", "Argentina", "Av. Santa Fe 3200"),
    ],
)
def test_missing_or_invalid_value_is_improved(field, old_value, new_value):
    new = incoming(**{field: new_value})
    old = existing(**{field: old_value})
    plan = build_merge_plan(new, [old], source_id="10")
    assert plan["patch"][field] == new_value
    assert decision(plan, field)["decision"] == ACCEPTED_IMPROVEMENT


def test_valid_title_is_preserved_against_generic_replacement():
    plan = build_merge_plan(
        incoming(titulo="Propiedad"),
        [existing(titulo="Casa luminosa en Palermo")],
        source_id="10",
    )
    assert "titulo" not in plan["patch"]
    assert decision(plan, "titulo")["decision"] == REJECTED_PLACEHOLDER


@pytest.mark.parametrize(
    "placeholder",
    ["Detalle.Php", "Logo_1751918871981.Png\\", "/assets/logo.svg"],
)
def test_file_or_page_shell_label_is_rejected_for_text_and_location(placeholder):
    plan = build_merge_plan(
        incoming(titulo=placeholder, direccion=placeholder, barrio=placeholder),
        [existing(titulo="Sin título", direccion=None, barrio="Argentina")],
        source_id="10",
    )
    assert "titulo" not in plan["patch"]
    assert "direccion" not in plan["patch"]
    assert "barrio" not in plan["patch"]
    assert decision(plan, "titulo")["decision"] == REJECTED_PLACEHOLDER
    assert decision(plan, "direccion")["decision"] == REJECTED_PLACEHOLDER
    assert decision(plan, "barrio")["decision"] == REJECTED_PLACEHOLDER


def test_contaminated_description_is_rejected():
    plan = build_merge_plan(
        incoming(descripcion="<nav>Menú principal</nav> política de privacidad"),
        [existing()],
        source_id="10",
    )
    assert "descripcion" not in plan["patch"]
    assert decision(plan, "descripcion")["decision"] == REJECTED_CROSS_PROPERTY_CONTAMINATION


@pytest.mark.parametrize("bad_price", [None, 0, -1, float("inf"), 10**20])
def test_invalid_price_is_rejected_without_degrading_existing(bad_price):
    plan = build_merge_plan(
        incoming(precio=bad_price),
        [existing(precio=120_000)],
        source_id="10",
    )
    assert "precio" not in plan["patch"]
    assert decision(plan, "precio")["decision"].startswith("REJECTED_")


def test_valid_changed_price_is_an_audited_source_change():
    plan = build_merge_plan(
        incoming(precio=125_000),
        [existing(precio=120_000)],
        source_id="10",
    )
    assert plan["patch"]["precio"] == 125_000
    assert decision(plan, "precio")["decision"] == ACCEPTED_SOURCE_CHANGE


def test_placeholder_image_array_is_rejected_and_old_array_preserved():
    plan = build_merge_plan(
        incoming(imagenes=["https://cdn.test/assets/logo.png"]),
        [existing(imagenes=["https://cdn.test/propiedades/real.jpg"])],
        source_id="10",
    )
    assert "imagenes" not in plan["patch"]
    assert decision(plan, "imagenes")["decision"] == REJECTED_PLACEHOLDER


def test_real_images_are_union_merged_without_removing_existing():
    plan = build_merge_plan(
        incoming(
            imagenes=[
                "https://cdn.test/propiedades/old.jpg",
                "https://cdn.test/assets/logo.png",
                "https://cdn.test/propiedades/new.jpg",
            ]
        ),
        [existing(imagenes=["https://cdn.test/propiedades/old.jpg"])],
        source_id="10",
    )
    assert plan["patch"]["imagenes"] == [
        "https://cdn.test/propiedades/old.jpg",
        "https://cdn.test/propiedades/new.jpg",
    ]


def test_generic_location_never_replaces_specific_location():
    plan = build_merge_plan(
        incoming(ciudad="Argentina"),
        [existing(ciudad="Rosario")],
        source_id="10",
    )
    assert "ciudad" not in plan["patch"]
    assert decision(plan, "ciudad")["decision"] == REJECTED_PLACEHOLDER


def test_second_execution_is_idempotent():
    first = build_merge_plan(
        incoming(precio=125_000, banos=2),
        [existing(precio=120_000, banos=None)],
        source_id="10",
    )
    merged = existing(precio=120_000, banos=None)
    merged.update(first["patch"])
    second = build_merge_plan(
        incoming(precio=125_000, banos=2),
        [merged],
        source_id="10",
    )
    assert first["patch"] == {"precio": 125_000, "banos": 2}
    assert second["patch"] == {}
    assert decision(second, "precio")["decision"] == UNCHANGED_EQUAL
    assert decision(second, "banos")["decision"] == UNCHANGED_EQUAL


def test_client_safe_merge_uses_only_authorized_rpcs():
    session = Mock()
    lookup = Mock(status_code=200)
    lookup.json.return_value = []
    session.get.return_value = lookup
    rpc = Mock(status_code=200)
    rpc.json.return_value = {"status": "inserted", "property_id": 99, "audit_rows": 10}
    session.post.return_value = rpc
    client = SupabaseClient(session, "https://db.test", "secret", "propiedades")

    stats = client.batch_save_safe_merge(
        [incoming()], source_id="10", run_id="run-1"
    )

    assert stats["db_inserts"] == 1
    assert stats["db_updates"] == 0
    assert "/rest/v1/rpc/insert_property_safe" in session.post.call_args.args[0]
    session.patch.assert_not_called()


def test_client_uses_verified_canonical_agency_for_rpc_identity():
    session = Mock()
    lookup = Mock(status_code=200)
    lookup.json.return_value = []
    session.get.return_value = lookup
    rpc = Mock(status_code=200)
    rpc.json.return_value = {"status": "inserted", "property_id": 99, "audit_rows": 10}
    session.post.return_value = rpc
    client = SupabaseClient(session, "https://db.test", "secret", "propiedades")

    client.batch_save_safe_merge(
        [incoming()],
        source_id="1976",
        identity_agency_id="10",
        run_id="run-mapped-source",
    )

    assert session.post.call_args.kwargs["json"]["p_source_id"] == "10"


def test_rollback_is_non_destructive_and_revokes_safe_merge():
    sql = (REPO_ROOT / "migrations" / "property_safe_merge_audit_rollback.sql").read_text(
        encoding="utf-8"
    ).upper()
    assert "DROP " not in sql
    assert "TRUNCATE " not in sql
    assert "REVOKE EXECUTE" in sql
    assert "SERVICE_ROLE" in sql


def test_migration_write_scope_is_only_properties_and_merge_audit():
    sql = (REPO_ROOT / "migrations" / "property_safe_merge_audit.sql").read_text(
        encoding="utf-8"
    ).lower()
    assert "public.propiedades" in sql
    assert "public.property_merge_audit" in sql
    for forbidden in (
        "inmobiliarias_main",
        "publish_queue",
        "propiedades_raw",
        "propiedades_staging",
        "neon",
        "truncate ",
        "drop table",
    ):
        assert forbidden not in sql
