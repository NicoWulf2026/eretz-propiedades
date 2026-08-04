from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRAPER_DIR = REPO_ROOT / "scraper"
for path in (REPO_ROOT, SCRAPER_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from extractors import DataCleaner  # noqa: E402
from models import Propiedad  # noqa: E402
from playwright_scraper import parse_cards  # noqa: E402
from scripts.validate_raw_properties import title_from_property_url  # noqa: E402
from scripts.backend_final_data_quality import (  # noqa: E402
    ANOMALY_FIELDS,
    RULES,
    load_streamed_anomalies,
)
from scripts.repair_deterministic_property_quality import (  # noqa: E402
    repair_mojibake,
    stable_json,
    transform,
)


def test_clean_title_strips_residual_html_and_property_id_markup():
    raw = '<span class="property-id">ID del Inmueble: 2805</span> Casa en venta'

    assert DataCleaner.clean_title(raw) == "Casa en venta"


def test_clean_description_strips_html_before_persisting():
    raw = "<div>Excelente casa familiar con patio, parrilla y cochera.</div>"

    assert DataCleaner.clean_description(raw) == "Excelente casa familiar con patio, parrilla y cochera."


def test_clean_price_rejects_concatenated_outlier_instead_of_persisting_false_value():
    price, currency = DataCleaner.clean_price("USD 100000225000")

    assert price is None
    assert currency == "USD"


def test_propiedad_rejects_generic_fallback_title():
    prop = Propiedad(
        url="https://example.com/propiedad/casa-123",
        titulo="Sin título",
        barrio="Centro",
        tipo_propiedad="casa",
    )

    assert prop.is_valid() is False


def test_parse_cards_uses_url_title_fallback_instead_of_generic_placeholder():
    html = """
    <article class="property-card">
      <strong>USD 100000</strong><span>Casa en venta, 3 ambientes</span>
      <a href="/propiedad/casa-en-venta-centro-123">Ver</a>
    </article>
    """

    properties = parse_cards(html, "venta", "fixture", "https://demo.test", "Cordoba")

    assert len(properties) == 1
    assert properties[0].titulo == "Casa En Venta Centro"
    assert properties[0].is_valid()


def test_raw_validator_derives_title_only_from_detail_evidence():
    assert (
        title_from_property_url("https://example.test/propiedad/casa-en-venta-centro-123")
        == "Casa En Venta Centro"
    )
    assert title_from_property_url("https://example.test/propiedades/page/6/") is None
    assert title_from_property_url("https://example.test/propiedades/") is None


def test_quality_rules_do_not_label_absent_source_evidence_as_internal():
    categories = {name: category for _, name, category, *_ in RULES}

    assert categories["MISSING_CURRENCY"] == "EXTERNAL_SOURCE_MISSING_DATA"
    assert categories["MISSING_NORMALIZED_URL"] == "AMBIGUOUS"
    assert categories["HOME_OR_NON_DETAIL_URL"] == "AMBIGUOUS"
    assert categories["INVALID_CURRENCY"] == "INTERNAL_CORRECTABLE"


def test_completed_quality_stream_can_rebuild_bounded_aggregates(tmp_path: Path):
    rows = [
        {
            "property_id": "1",
            "inmobiliaria_id": "10",
            "fuente_extraccion": "source-a",
            "url": "https://example.test/1",
            "field": "titulo",
            "anomaly_type": "MISSING_TITLE",
            "category": "EXTERNAL_SOURCE_MISSING_DATA",
            "root_cause": "DETAIL_PARSER",
            "severity": "high",
            "detail": "blank title",
        },
        {
            "property_id": "2",
            "inmobiliaria_id": "10",
            "fuente_extraccion": "source-a",
            "url": "https://example.test/2",
            "field": "url",
            "anomaly_type": "MISSING_NORMALIZED_URL",
            "category": "AMBIGUOUS",
            "root_cause": "DEDUPLICATION",
            "severity": "medium",
            "detail": "identity collision",
        },
    ]
    with (tmp_path / "row_level_anomalies.csv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=ANOMALY_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    (tmp_path / "progress.json").write_text(
        json.dumps({"status": "anomaly_stream_complete", "anomalies_written": 2}),
        encoding="utf-8",
    )

    grouped, categories, total = load_streamed_anomalies(tmp_path)

    assert total == 2
    assert categories == {"EXTERNAL_SOURCE_MISSING_DATA": 1, "AMBIGUOUS": 1}
    assert sum(item["affected_rows"] for item in grouped.values()) == 2
    assert {source for item in grouped.values() for source in item["affected_sources"]} == {
        "source-a"
    }


def test_incomplete_quality_stream_is_not_reused(tmp_path: Path):
    (tmp_path / "progress.json").write_text(
        json.dumps({"status": "running", "anomalies_written": 2}),
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="not complete"):
        load_streamed_anomalies(tmp_path)


def test_deterministic_repair_removes_false_values_without_touching_ambiguity():
    patch, reasons = transform(
        {
            "titulo": "Propiedad",
            "descripcion": "<div>Todos los derechos reservados 2026</div>",
            "operacion": None,
            "superficie_total": 0,
            "superficie_cubierta": -1,
            "imagenes": [
                "https://example.test/logo.png",
                "https://example.test/property-1.jpg",
            ],
        }
    )

    assert patch == {
        "titulo": None,
        "descripcion": None,
        "operacion": "consultar",
        "superficie_total": None,
        "superficie_cubierta": None,
        "imagenes": ["https://example.test/property-1.jpg"],
    }
    assert "REMOVE_GENERIC_TITLE" in reasons


def test_deterministic_repair_preserves_clean_values_and_repairs_mojibake():
    assert repair_mojibake("Casa en ConstituciÃ³n") == "Casa en Constitución"
    assert repair_mojibake("Departamento Â\u0096 Centro") == "Departamento – Centro"
    assert repair_mojibake("Piso 2Âº") == "Piso 2º"
    patch, reasons = transform(
        {
            "titulo": "Casa en venta",
            "descripcion": "Casa luminosa con patio y cochera.",
            "operacion": "venta",
            "superficie_total": 100,
            "superficie_cubierta": 80,
            "imagenes": ["https://example.test/property-1.jpg"],
        }
    )
    assert patch == {}
    assert reasons == []


def test_quality_snapshot_redacts_url_query_parameters():
    rendered = stable_json(
        {"imagenes": ["https://maps.google.test/tile?key=secret&token=secret"]}
    )

    assert rendered == '{"imagenes":["https://maps.google.test/tile"]}'
