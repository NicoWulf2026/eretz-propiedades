"""Evidence collectors do not read secrets, execute old services or write DBs."""
import json

from scripts import audit_project_lineage as lineage
from scripts.audit_unification_incidents import audit
from scripts.replay_unification_sample import (LOCAL, compare_detail_discovery,
                                               load_git_module, NoEnvironment)


def test_lineage_never_opens_environment_files_even_with_a_code_extension(tmp_path, monkeypatch):
    (tmp_path / 'pure.py').write_text('def useful(): return 1', encoding='utf-8')
    def fake_git(root, *args):
        if args[0] == 'for-each-ref':
            return ''
        if args[0] == 'ls-files':
            return '' if '--others' in args else '.env.ts\npure.py'
        if args[0] == 'rev-parse':
            return 'audit-test-head'
        return ''
    monkeypatch.setattr(lineage, 'git', fake_git)
    report = lineage.audit(tmp_path, [tmp_path])
    assert [row['path'] for row in report['worktrees'][0]['code']] == ['pure.py']
    assert report['worktrees'][0]['code'][0]['symbols'] == ['useful']


def test_incident_matching_does_not_confuse_cip_and_cipollone(tmp_path):
    rows = [dict(canonical_agency_id='roomix:cipollone', status='NEEDS_FIX'),
            dict(canonical_agency_id='roomix:cip', status='COMPLETE')]
    (tmp_path / 'AGENCY_CERTIFICATION_RESULTS.jsonl').write_text(
        '\n'.join(json.dumps(row) for row in rows) + '\ninvalid-json', encoding='utf-8')
    report = audit(tmp_path)
    assert report['malformed_lines'] == 1
    assert report['controls']['cip'][0]['canonical_id'] == 'roomix:cip'
    assert len(report['controls']['cip']) == 1
    assert report['database_writes'] == 0


def test_environment_calls_are_replaced_without_observing_their_values():
    import ast
    tree = ast.fix_missing_locations(NoEnvironment().visit(
        ast.parse("import os\nanswer = os.getenv('NEVER_READ', 'fallback')")))
    namespace = {}
    exec(compile(tree, 'pure-env-test', 'exec'), namespace)
    assert namespace['answer'] == 'fallback'


def test_actual_historical_and_current_url_behavior_is_reproducible_without_network(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('network attempted during an offline replay')
    monkeypatch.setattr('socket.create_connection', forbidden)
    monkeypatch.setattr('urllib.request.urlopen', forbidden)
    monkeypatch.setattr('requests.sessions.Session.request', forbidden)
    baseline = load_git_module(LOCAL, 'connectors/generico.py', 'connectors.test_audit_baseline')
    report = compare_detail_discovery(baseline)
    assert report['correct'] == {'historical': 8, 'local_before': 6, 'unified': 9}
    provider = next(row for row in report['rows'] if row['case'] == 'provider_root_not_tenant')
    assert provider['correct']['historical'] is False
    assert provider['correct']['unified'] is True
