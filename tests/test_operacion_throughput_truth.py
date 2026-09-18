import json
from datetime import datetime, timezone

import pytest

from scripts.operacion_reporte import caudal_por_ventana, eta, rendimiento


def replay(tmp_path, monkeypatch, rows):
    monkeypatch.setattr('scripts.operacion_reporte.time.time', lambda: 1_800_000_000)
    (tmp_path / 'AGENCY_CERTIFICATION_RESULTS.jsonl').write_text(
        ''.join(json.dumps(row) + '\n' for row in rows), encoding='utf-8')
    return rendimiento(tmp_path, horas=2)


def row(agency, age, status='NEEDS_FIX', **fields):
    return {'canonical_agency_id': agency,
            'checked_at': datetime.fromtimestamp(1_800_000_000 - age, timezone.utc).isoformat(),
            'status': status, **fields}


def test_attempt_failure_and_external_block_are_not_certification(tmp_path, monkeypatch):
    result = replay(tmp_path, monkeypatch, [row('a', 10), row('b', 20, 'BLOCKED_EXTERNAL')])
    assert result['agencias_nuevas'] == 2
    assert result['new_attempt_throughput_agencias_por_hora'] == 1
    assert result['certified_throughput_agencias_nuevas_por_hora'] == 0
    assert eta({'terminales': 0}, result)['estado'] == 'SIN_ETA'


def test_first_success_after_old_failure_counts_once_even_when_log_unordered(tmp_path, monkeypatch):
    success = row('a', 10, 'CERTIFIED_COMPLETE', enumeration_audit={'enumerated': 12})
    result = replay(tmp_path, monkeypatch, [success, row('a', 30_000), success])
    assert result['agencias_nuevas'] == 0
    assert result['agencias_con_primer_cierre_exitoso'] == 1
    assert result['propiedades_nuevas'] == 12


def test_recertification_is_not_new_inventory(tmp_path, monkeypatch):
    result = replay(tmp_path, monkeypatch, [row('a', 30_000, 'CERTIFIED_COMPLETE'),
        row('a', 10, 'CERTIFIED_COMPLETE', enumeration_audit={'enumerated': 12})])
    assert result['agencias_con_primer_cierre_exitoso'] == result['propiedades_nuevas'] == 0


@pytest.mark.parametrize('bad', [None, True, -1, float('nan'), '20', []])
def test_unknown_worker_duration_is_not_measured_zero(tmp_path, monkeypatch, bad):
    result = replay(tmp_path, monkeypatch, [row('a', 10, operational_metrics={'duration_seconds': bad})])
    assert result['corridas_sin_duracion_verificada'] == 1


@pytest.mark.parametrize('bad', [None, True, -1, 1.5, '12'])
def test_unknown_inventory_is_not_fabricated(tmp_path, monkeypatch, bad):
    result = replay(tmp_path, monkeypatch, [row('a', 10, 'CERTIFIED_COMPLETE',
        enumeration_audit={'enumerated': bad})])
    assert result['propiedades_nuevas'] == 0
    assert result['cierres_sin_inventario_verificado'] == 1


def test_bad_dates_disable_eta_instead_of_counting_fake_new_agency(tmp_path, monkeypatch):
    result = replay(tmp_path, monkeypatch, [row('a', 10, 'CERTIFIED_COMPLETE'),
        {'canonical_agency_id': 'a', 'checked_at': 'unknown'}, [],
        row('b', -10, 'CERTIFIED_COMPLETE')])
    assert result['registros_ilegibles_o_sin_fecha_valida'] == 3
    assert result['eta_eligible'] is False
    assert eta({'terminales': 0}, result)['estado'] == 'SIN_ETA'


@pytest.mark.parametrize('bad', [0, -1, True, float('nan'), float('inf')])
def test_invalid_measurement_window_fails(tmp_path, bad):
    with pytest.raises(ValueError, match='positiva y finita'):
        rendimiento(tmp_path, horas=bad)


def test_multiple_window_rates_use_same_first_success_boundary(tmp_path, monkeypatch):
    replay(tmp_path, monkeypatch, [row('a', 10), row('b', 20, 'BLOCKED_EXTERNAL'),
        row('c', 100, 'CERTIFIED_COMPLETE'), row('c', 50, 'CERTIFIED_COMPLETE'),
        row('d', 8_000, 'CERTIFIED_BEST_AVAILABLE')])
    assert caudal_por_ventana(tmp_path, horas=(2, 4)) == {'2h': 0.5, '4h': 0.5}


def test_invalid_history_does_not_produce_any_window_eta_rate(tmp_path, monkeypatch):
    replay(tmp_path, monkeypatch, [row('a', 10, 'CERTIFIED_COMPLETE'),
        {'canonical_agency_id': 'a', 'checked_at': 'unknown'}])
    assert caudal_por_ventana(tmp_path, horas=(2, 4)) == {'2h': 0.0, '4h': 0.0}


@pytest.mark.parametrize('status', [[], {}, None])
def test_invalid_status_cannot_be_counted_as_success_or_crash_report(tmp_path, monkeypatch, status):
    result = replay(tmp_path, monkeypatch, [row('a', 10, status)])
    assert result['corridas'] == 1
    assert result['agencias_con_primer_cierre_exitoso'] == 0


def test_multiple_windows_decode_log_once_and_capture_one_clock(tmp_path, monkeypatch):
    from scripts import operacion_reporte as report
    reads = []
    clocks = []
    source = [row('a', 10, 'CERTIFIED_COMPLETE')]
    monkeypatch.setattr(report, '_jsonl', lambda path: reads.append(path) or source)
    monkeypatch.setattr(report.time, 'time', lambda: clocks.append(True) or 1_800_000_000)
    before = json.dumps(source)
    assert report.caudal_por_ventana(tmp_path, horas=(2, 4)) == {'2h': 0.5, '4h': 0.25}
    assert len(reads) == len(clocks) == 1
    assert json.dumps(source) == before
