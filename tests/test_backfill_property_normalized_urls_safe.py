from scripts.backfill_property_normalized_urls_safe import classify


def test_classify_accepts_unique_canonical_agency_url():
    rows = [
        {
            "id": 1,
            "inmobiliaria_id": 10,
            "url": "HTTPS://WWW.Example.com/Propiedad/1/?utm_source=x",
            "url_normalizada": None,
        }
    ]

    _, safe, ambiguous = classify(rows)

    assert safe[0]["new_url_normalizada"] == "example.com/propiedad/1"
    assert ambiguous == []


def test_classify_rejects_prospective_identity_collisions():
    rows = [
        {"id": 1, "inmobiliaria_id": 10, "url": "https://example.com/p/1", "url_normalizada": None},
        {"id": 2, "inmobiliaria_id": 10, "url": "https://www.example.com/p/1/", "url_normalizada": None},
    ]

    _, safe, ambiguous = classify(rows)

    assert safe == []
    assert {row["property_id"] for row in ambiguous} == {1, 2}


def test_classify_allows_same_url_for_distinct_agencies():
    rows = [
        {"id": 1, "inmobiliaria_id": 10, "url": "https://example.com/p/1", "url_normalizada": None},
        {"id": 2, "inmobiliaria_id": 20, "url": "https://example.com/p/1", "url_normalizada": None},
    ]

    _, safe, ambiguous = classify(rows)

    assert len(safe) == 2
    assert ambiguous == []

