from __future__ import annotations

import csv
import json
from argparse import Namespace
from pathlib import Path

from connectors.base import a_entero
from connectors.tokko import _cantidad, _texto_plano
from scripts.preingestion_rebuild import (
    AMBIGUOUS,
    NOT_FOUND,
    build_agency_manifest,
    derive_contract,
    host,
    sanitize_count,
    sanitize_description,
)
import scripts.preingestion_rebuild as rebuild_module


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def write_main(path: Path, rows: list[dict]) -> None:
    fields = [
        "id", "nombre", "web", "ciudad", "provincia", "telefono",
        "telefono_principal", "email_principal",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def test_numeric_source_id_never_becomes_foreign_main_id(tmp_path: Path) -> None:
    crosswalk = tmp_path / "crosswalk.jsonl"
    web = tmp_path / "web.jsonl"
    platform = tmp_path / "platform.jsonl"
    main = tmp_path / "main.csv"
    write_jsonl(crosswalk, [{
        "stable_id": "roomix:guccione propiedades",
        "nombre_original": "Guccione Propiedades",
        "crosswalk": "HIGH_CONFIDENCE_EXISTING",
        "crosswalk_candidato": {"tabla": "staging", "id": "6136", "nombre": "Guccione Propiedades"},
    }])
    write_jsonl(web, [])
    write_jsonl(platform, [])
    write_main(main, [{"id": "6136", "nombre": "INMOBILIARIA GUSTAVO SATTLER"}])

    manifest, mapping = build_agency_manifest(crosswalk, web, platform, main)

    assert mapping == {}
    assert manifest[0]["eretz_id"] is None
    assert manifest[0]["resolution_status"] == NOT_FOUND
    assert manifest[0]["resolution_method"] == "STAGING_NAMESPACE_NOT_A_MAIN_FK"


def test_staging_evidence_is_measured_not_asserted(tmp_path: Path) -> None:
    """La evidencia decia "0/4920 candidates linked by main.staging_id_origen".

    Era un literal congelado de una medicion hecha una sola vez: si el enlace
    se poblara, el texto seguiria diciendo cero y 4.953 inmobiliarias
    quedarian declaradas irresolubles apoyadas en algo que nadie comprueba.
    """
    crosswalk = tmp_path / "crosswalk.jsonl"
    web = tmp_path / "web.jsonl"
    platform = tmp_path / "platform.jsonl"
    main = tmp_path / "main.csv"
    write_jsonl(crosswalk, [{
        "stable_id": "roomix:mizrahi real estate",
        "nombre_original": "Mizrahi Real Estate",
        "crosswalk": "HIGH_CONFIDENCE_EXISTING",
        "crosswalk_candidato": {"tabla": "staging", "id": "3080",
                                "nombre": "Mizrahi Real Estate"},
    }])
    write_jsonl(web, [])
    write_jsonl(platform, [])
    write_main(main, [{"id": "3080", "nombre": "Otra Inmobiliaria"}])

    manifest, _ = build_agency_manifest(crosswalk, web, platform, main)

    assert manifest[0]["resolution_method"] == "STAGING_NAMESPACE_NOT_A_MAIN_FK"
    assert manifest[0]["evidence"]["main_name_matches"] == 0
    assert "0/4920" not in json.dumps(manifest[0]["evidence"])


def test_staging_name_present_in_main_is_never_closed_as_not_found(
        tmp_path: Path) -> None:
    """Si el nombre existe en main pero sin FK declarada, no se puede afirmar
    que la inmobiliaria no este: elegir una seria inventar la identidad, y
    cerrarla como NOT_FOUND seria descartar una coincidencia real."""
    crosswalk = tmp_path / "crosswalk.jsonl"
    web = tmp_path / "web.jsonl"
    platform = tmp_path / "platform.jsonl"
    main = tmp_path / "main.csv"
    write_jsonl(crosswalk, [{
        "stable_id": "roomix:pastori propiedades",
        "nombre_original": "Pastori Propiedades",
        "crosswalk": "HIGH_CONFIDENCE_EXISTING",
        "crosswalk_candidato": {"tabla": "staging", "id": "9999",
                                "nombre": "Pastori Propiedades"},
    }])
    write_jsonl(web, [])
    write_jsonl(platform, [])
    write_main(main, [{"id": "4242", "nombre": "PASTORI PROPIEDADES"}])

    manifest, mapping = build_agency_manifest(crosswalk, web, platform, main)

    assert manifest[0]["resolution_status"] == AMBIGUOUS
    assert manifest[0]["resolution_method"] == "STAGING_NAME_COLLIDES_WITH_MAIN"
    assert manifest[0]["evidence"]["main_candidates"] == ["4242"]
    # Ambigua nunca se convierte en una asociacion escrita.
    assert manifest[0]["eretz_id"] is None
    assert mapping == {}


def test_two_canonical_agencies_cannot_silently_share_eretz_id(tmp_path: Path) -> None:
    crosswalk = tmp_path / "crosswalk.jsonl"
    web = tmp_path / "web.jsonl"
    platform = tmp_path / "platform.jsonl"
    main = tmp_path / "main.csv"
    write_jsonl(crosswalk, [
        {"stable_id": "roomix:a", "nombre_original": "A", "crosswalk": "EXACT_MATCH",
         "crosswalk_candidato": {"tabla": "main", "id": "10", "nombre": "A"}},
        {"stable_id": "roomix:a alias", "nombre_original": "A", "crosswalk": "EXACT_MATCH",
         "crosswalk_candidato": {"tabla": "main", "id": "10", "nombre": "A"}},
    ])
    write_jsonl(web, [])
    write_jsonl(platform, [])
    write_main(main, [{"id": "10", "nombre": "A"}])

    manifest, mapping = build_agency_manifest(crosswalk, web, platform, main)

    assert mapping == {}
    assert all(row["resolution_status"] == AMBIGUOUS for row in manifest)
    assert all("same_agency_duplicate" in row["evidence"] for row in manifest)


def test_external_portal_domain_invalidates_resolved_identity(tmp_path: Path) -> None:
    crosswalk = tmp_path / "crosswalk.jsonl"
    web = tmp_path / "web.jsonl"
    platform = tmp_path / "platform.jsonl"
    main = tmp_path / "main.csv"
    write_jsonl(crosswalk, [{
        "stable_id": "roomix:agency", "nombre_original": "Agency", "crosswalk": "EXACT_MATCH",
        "crosswalk_candidato": {"tabla": "main", "id": "10", "nombre": "Agency"},
    }])
    write_jsonl(web, [])
    write_jsonl(platform, [{
        "canonical_agency_id": "roomix:agency",
        "domain": "https://datoinmobiliario.com.ar/perfil/agency",
    }])
    write_main(main, [{"id": "10", "nombre": "Agency"}])

    manifest, mapping = build_agency_manifest(crosswalk, web, platform, main)

    assert mapping == {}
    assert manifest[0]["resolution_status"] == AMBIGUOUS
    assert manifest[0]["evidence"]["official_domain_rejected"] == "SHARED_EXTERNAL_PORTAL"


def test_datoinmobiliario_is_an_external_portal_host() -> None:
    assert host("http://datoinmobiliario.com.ar/casa-venta") == "datoinmobiliario.com.ar"


def test_tokko_multiple_bathroom_counts_do_not_concatenate() -> None:
    assert a_entero("1 + 1") is None
    assert a_entero("3 baños + 1 toilette") is None
    assert _cantidad("Baños 1 + 1 Dormitorios 2", "Baños") is None
    assert _cantidad("Baños 3 + 1 Dormitorios 2", "Baños") is None


def test_tokko_description_does_not_include_javascript() -> None:
    raw = "<div>Descripción Casa luminosa con patio propio</div><script>function getCookie(){return document.cookie}</script>"
    plain = _texto_plano(raw)
    assert "Casa luminosa" in plain
    assert "getCookie" not in plain
    assert "document.cookie" not in plain
    cleaned, contaminated = sanitize_description("Casa luminosa function getCookie() document.cookie")
    assert contaminated is True
    assert cleaned == "Casa luminosa"


def test_large_room_count_needs_explicit_hotel_evidence() -> None:
    street_like = {"ambientes": 150, "tipo_propiedad": "departamento", "direccion": "Calle 150"}
    assert sanitize_count(street_like, "ambientes") == (None, "IMPLAUSIBLE_UNPROVED_COUNT")
    hotel = {"ambientes": 150, "tipo_propiedad": "hotel", "descripcion": "Hotel con 150 ambientes"}
    assert sanitize_count(hotel, "ambientes") == (150, None)


def test_contract_is_only_derived_from_deterministic_text() -> None:
    operation, property_type, derived = derive_contract({
        "source_url": "https://agency.test/departamento-en-venta/123",
        "titulo": "Departamento",
    })
    assert operation == "venta"
    assert property_type == "departamento"
    assert set(derived) == {"operacion", "tipo_propiedad"}
    assert derive_contract({"source_url": "https://agency.test/aviso/123"})[:2] == (None, None)


def run_one_row_rebuild(
    tmp_path: Path,
    monkeypatch,
    *,
    crosswalk_row: dict,
    source_row: dict,
    platform_rows: list[dict] | None = None,
) -> dict:
    source_root = tmp_path / "source"
    source_dir = source_root / "sample"
    source_dir.mkdir(parents=True)
    write_jsonl(source_dir / "properties.jsonl", [source_row])
    monkeypatch.setattr(
        rebuild_module, "ENTRADAS", (("sample", "properties.jsonl", "tokko"),)
    )
    crosswalk = tmp_path / "crosswalk.jsonl"
    web = tmp_path / "web.jsonl"
    platform = tmp_path / "platform.jsonl"
    main = tmp_path / "main.csv"
    write_jsonl(crosswalk, [crosswalk_row])
    write_jsonl(web, [])
    write_jsonl(platform, platform_rows or [])
    write_main(main, [{"id": "10", "nombre": "Agency"}])
    output = tmp_path / "output"
    return rebuild_module.rebuild(Namespace(
        output_dir=str(output),
        source_root=str(source_root),
        crosswalk=str(crosswalk),
        web_directory=str(web),
        platform_directory=str(platform),
        main_backup=str(main),
    ))


def test_external_portal_profile_never_produces_insert(tmp_path: Path, monkeypatch) -> None:
    summary = run_one_row_rebuild(
        tmp_path,
        monkeypatch,
        crosswalk_row={
            "stable_id": "roomix:agency",
            "nombre_original": "Agency",
            "crosswalk": "EXACT_MATCH",
            "crosswalk_candidato": {"tabla": "main", "id": "10", "nombre": "Agency"},
        },
        source_row={
            "canonical_agency_id": "roomix:agency",
            "connector": "tokko",
            "source_url": "https://datoinmobiliario.com.ar/propiedad/12345",
            "source_listing_id": "12345",
            "titulo": "Dato Inmobiliario",
            "operacion": "venta",
            "tipo_propiedad": "departamento",
        },
        platform_rows=[{
            "canonical_agency_id": "roomix:agency",
            "domain": "https://datoinmobiliario.com.ar/perfil/agency",
        }],
    )
    assert summary["status_counts"] == {"INVALID_OR_REJECTED": 1}
    assert summary["quality"]["portal_contaminated_rows_removed"] == 1


def test_una_propiedad_sin_operacion_no_desaparece(tmp_path: Path,
                                                  monkeypatch) -> None:
    """Primer principio de ERETZ: una propiedad valida no deja de mostrarse
    porque le falte un dato enriquecible.

    Faltar operacion la marcaba INVALID_OR_REJECTED, el mismo estado que un
    perfil de portal, y con eso no llegaba nunca a la base: desaparecia del
    producto. Eran 13.518 propiedades reales.

    El propio esquema ya declaraba la politica -`operacion TEXT` lleva el
    comentario "FASE 1: no rechazar por operacion faltante"- y la pre-ingesta
    la contradecia.
    """
    summary = run_one_row_rebuild(
        tmp_path, monkeypatch,
        crosswalk_row={
            "stable_id": "roomix:agency",
            "nombre_original": "Agency",
            "crosswalk": "EXACT_MATCH",
            "crosswalk_candidato": {"tabla": "main", "id": "10",
                                    "nombre": "Agency"},
        },
        source_row={
            "canonical_agency_id": "roomix:agency",
            "connector": "tokko",
            "source_url": "https://agency.test/propiedad/12345",
            "source_listing_id": "12345",
            "titulo": "Casa con patio en el centro",
            "precio": 120000.0,
            "moneda": "USD",
            # Sin operacion ni tipo: la fuente no los publica.
        },
    )
    assert summary["status_counts"].get("INVALID_OR_REJECTED", 0) == 0
    assert summary["agency_mappings"]["resolved"] == 1


def test_lo_que_no_es_una_propiedad_si_se_rechaza(tmp_path: Path,
                                                  monkeypatch) -> None:
    """Conservar lo incompleto no puede volverse conservar cualquier cosa: una
    url de busqueda no identifica ninguna propiedad y sigue rechazandose."""
    summary = run_one_row_rebuild(
        tmp_path, monkeypatch,
        crosswalk_row={
            "stable_id": "roomix:agency",
            "nombre_original": "Agency",
            "crosswalk": "EXACT_MATCH",
            "crosswalk_candidato": {"tabla": "main", "id": "10",
                                    "nombre": "Agency"},
        },
        source_row={
            "canonical_agency_id": "roomix:agency",
            "connector": "tokko",
            "source_url": "https://agency.test/buscar-propiedades/casas",
            "source_listing_id": "casas",
            "titulo": "Casas en venta",
            "operacion": "venta",
            "tipo_propiedad": "casa",
        },
    )
    assert summary["status_counts"].get("INVALID_OR_REJECTED", 0) == 1


def test_ambiguous_agency_mapping_fails_closed_to_hold(tmp_path: Path, monkeypatch) -> None:
    summary = run_one_row_rebuild(
        tmp_path,
        monkeypatch,
        crosswalk_row={
            "stable_id": "roomix:agency",
            "nombre_original": "Agency",
            "crosswalk": "HIGH_CONFIDENCE_EXISTING",
            "crosswalk_candidato": {"tabla": "staging", "id": "10", "nombre": "Agency"},
        },
        source_row={
            "canonical_agency_id": "roomix:agency",
            "connector": "tokko",
            "source_url": "https://agency.test/propiedad/12345",
            "source_listing_id": "12345",
            "titulo": "Departamento en venta",
            "operacion": "venta",
            "tipo_propiedad": "departamento",
        },
    )
    # La fixture pone en main una fila homonima de la candidata de staging.
    # Coincidir de nombre no prueba que sean la misma inmobiliaria, asi que la
    # clasificacion queda ambigua en vez de cerrarse; lo que el test protege
    # es que nada de eso se convierta en una asociacion escrita.
    assert summary["status_counts"] == {"AGENCY_ID_UNRESOLVED": 1}
    assert summary["agency_mappings"]["ambiguous"] == 1
    assert summary["agency_mappings"]["resolved"] == 0
    assert summary["database_writes"] == 0
