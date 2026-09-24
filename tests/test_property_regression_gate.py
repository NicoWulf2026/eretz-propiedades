from scripts.regression_gate import compare


def row(identifier=123, **values):
    return {'canonical_agency_id': 'agency:a',
            'source_url': f'https://official.test/ficha.php?id={identifier}', **values}


def test_query_ids_are_distinct_and_one_property_cannot_hide_another_loss():
    report = compare([row(123, banos=2), row(456, banos=1)], [row(123, banos=None), row(456, banos=1)])
    assert report['matched_rows'] == 2
    assert report['counts'] == {'UNEXPLAINED_LOSS': 1}
    assert report['status'] == 'REVIEW_REQUIRED'


def test_aggregate_coverage_is_not_row_scoped_loss_evidence():
    report = compare([row(precio=12)], [row(precio=None, field_coverage={'precio': {'state': 'SOURCE_NOT_PROVIDED'}})])
    assert report['counts'] == {'UNEXPLAINED_LOSS': 1}


def test_geographic_move_requires_new_neighbor_not_old_duplicate():
    report = compare([row(barrio='Rosario', ciudad='Rosario')], [row(barrio=None, ciudad=None)])
    assert report['counts'] == {'UNEXPLAINED_LOSS': 2}
    report = compare([row(barrio='Rosario')], [row(barrio=None, ciudad='Rosario')])
    assert report['counts']['DIMENSION_MOVE_REVIEW'] == 1
    assert report['status'] == 'REVIEW_REQUIRED'


def test_zero_is_present_and_false_does_not_equal_zero():
    report = compare([row(banos=0, precio=0)], [row(banos=None, precio=False)])
    assert report['counts'] == {'FIELD_CHANGED': 1, 'UNEXPLAINED_LOSS': 1}


def test_equal_image_counts_do_not_prove_equal_images():
    report = compare([row(imagenes=['https://cdn.test/a.jpg'])], [row(imagenes=['https://cdn.test/b.jpg'])])
    assert report['counts'] == {'FIELD_CHANGED': 1}


def test_duplicate_identity_cannot_be_silently_last_wins():
    report = compare([row(banos=1), row(banos=2)], [row(banos=2)])
    assert report['matched_rows'] == 0
    assert report['old_issues'][0]['kind'] == 'AMBIGUOUS_IDENTITY'
    assert report['status'] == 'REVIEW_REQUIRED'


def test_absence_is_not_retirement_or_permission_to_publish():
    report = compare([row()], [])
    assert report['counts'] == {'INVENTORY_NOT_OBSERVED': 1}
    assert not report['publication_authorized'] and report['database_writes'] == 0


def test_row_rejection_requires_matching_source_identity_and_reason():
    evidence = {'state': 'PROVIDED_REJECTED', 'reason': 'invalid count',
                'source_url': 'https://official.test/ficha.php?id=123'}
    report = compare([row(banos=2)], [row(field_evidence={'banos': evidence})])
    assert report['counts'] == {'EXPLAINED_VALIDATION': 1}
    evidence['source_url'] = 'https://official.test/ficha.php?id=456'
    assert compare([row(banos=2)], [row(field_evidence={'banos': evidence})])['counts'] == {'UNEXPLAINED_LOSS': 1}


def test_credentials_in_urls_are_not_serialized():
    report = compare([dict(row(), source_url='https://user:SECRET@official.test/p/123')], [])
    assert 'SECRET' not in str(report)
    assert report['old_issues'] == [{'kind': 'INVALID_IDENTITY', 'position': 0}]


def test_malformed_field_evidence_cannot_explain_a_loss_or_crash_batch():
    report = compare([row(banos=2)], [row(field_evidence=['not a field map'])])
    assert report['counts'] == {'UNEXPLAINED_LOSS': 1}


def test_a_description_discarded_by_the_runner_is_explained_for_that_row_only():
    old = [row(1, descripcion='AB Negocios es una inmobiliaria de Rafaela'),
           row(2, descripcion='Casa con patio'), row(3, descripcion='Depto')]
    fresh = [row(1, descripcion=None, extra={'descripcion_descartada': 'compartida_por_la_agencia'}),
             row(2, descripcion=None),
             row(3, descripcion=None, extra={'otra_cosa': 'x'})]
    report = compare(old, fresh)
    assert report['counts'] == {'EXPLAINED_VALIDATION': 1, 'UNEXPLAINED_LOSS': 2}
    # The same mark never explains another field of the row.
    report = compare([row(precio=10)], [row(precio=None, extra={'descripcion_descartada': 'x'})])
    assert report['counts'] == {'UNEXPLAINED_LOSS': 1}


def test_validation_discards_recorded_on_the_row_explain_only_their_field():
    old = [row(1, ambientes=1, dormitorios=2), row(2, dormitorios=3), row(3, provincia='Buenos Aires'),
           row(4, provincia='Buenos Aires')]
    fresh = [row(1, ambientes=None, dormitorios=None, extra={'atributos_descartados': 'dormitorios>ambientes'}),
             row(2, dormitorios=None, extra={'atributos_descartados': 'dormitorios_en_un_terreno'}),
             row(3, provincia=None, extra={'provincia_supuesta_descartada': 'Buenos Aires'}),
             row(4, provincia=None, extra={'provincia_supuesta_descartada': 'Cordoba'})]
    report = compare(old, fresh)
    assert report['counts'] == {'EXPLAINED_VALIDATION': 4, 'UNEXPLAINED_LOSS': 1}
    # A discard of one field never explains another one on the same row.
    report = compare([row(banos=1)], [row(banos=None, extra={'atributos_descartados': 'ambientes'})])
    assert report['counts'] == {'UNEXPLAINED_LOSS': 1}
