from scripts.agency_certifier import choose_connector, external_portal, resolve_identity
from scripts import agency_certifier


def record():
    return dict(resolution=dict(resolution_status='RESOLVED', eretz_id=7),
                live=dict(validation_status='VALIDATED'), source={}, directory={},
                platform=dict(domain='https://www.argenprop.com:443/inmobiliarias/perfil/7',
                              web_kind='EXTERNAL_PORTAL_PROFILE', connector='wasi'),
                verificada=dict(official_url='https://estudioelhelou.com.ar',
                                verificacion='VERIFICADA_ARGENTINA'))


def test_verified_official_domain_recovers_a_portal_without_inheriting_its_technology():
    data = record()
    identity = resolve_identity(data, 'agency:7')
    assert identity['official_url'] == 'https://estudioelhelou.com.ar'
    assert identity['identity_status'] == 'READY'
    assert identity['identity_evidence']['source_origin'] == 'verified_recovery'
    assert choose_connector(data) == 'generico'
    assert data['platform']['connector'] == 'wasi'  # original evidence preserved


def test_unverified_candidate_cannot_authorize_recovery():
    data = record()
    data['verificada']['verificacion'] = 'CANDIDATE'
    assert resolve_identity(data, 'agency:7')['identity_status'] == 'BLOCKED_EXTERNAL'
def test_portal_cannot_be_authorized_by_verified_label():
    data = record()
    data['verificada']['official_url'] = 'https://zonaprop.com.ar/inmobiliarias/7'
    assert resolve_identity(data, 'agency:7')['identity_status'] == 'BLOCKED_EXTERNAL'


def test_explicit_official_override_is_not_replaced_by_discovery():
    data = record()
    data['platform'].update(domain='https://actual-official.test', web_kind='OFFICIAL_WEB')
    assert resolve_identity(data, 'agency:7')['official_url'] == 'https://actual-official.test'
    assert choose_connector(data) == 'wasi'


def test_source_recovery_does_not_bypass_foreign_key_identity():
    data = record()
    data['resolution']['resolution_status'] = 'PENDING'
    assert resolve_identity(data, 'agency:7')['identity_status'] == 'IDENTITY_PENDING'


def test_forbidden_inventory_domains_with_ports_and_subdomains_remain_forbidden():
    assert external_portal('https://www.argenprop.com:443/p/1')
    assert external_portal('https://x.zonaprop.com.ar:443/p/1')
    assert not external_portal('https://zonaprop.com.ar.official.test/p/1')


def test_certification_uses_the_effective_url_and_drops_rejected_pattern(tmp_path, monkeypatch):
    data = record()
    data['platform']['pattern_ficha'] = '/portal-only/.*'
    data['source']['detected_platform'] = 'WASI'
    seen = []
    def stop_after_selection(connector, source, *args):
        seen.append((connector, source.official_url, source.detected_platform,
                     source.extra['patron_ficha']))
        raise RuntimeError('offline test stops before any request')
    monkeypatch.setattr(agency_certifier, 'run_once', stop_after_selection)
    agency_certifier.certify('agency:7', {'agency:7': data}, tmp_path,
                             tmp_path / 'absent.sqlite3', 1, 5, 10)
    assert seen == [('generico', 'https://estudioelhelou.com.ar', None, None)]
def test_social_and_other_marketplaces_cannot_be_verified_into_official_inventory():
    for url in ('https://facebook.com/agency', 'https://properati.com.ar/agency',
                'https://www.zonaprop.com/agency'):
        data = record()
        data['verificada']['official_url'] = url
        assert resolve_identity(data, 'agency:7')['identity_status'] == 'BLOCKED_EXTERNAL'


def test_network_root_cannot_be_recovered_as_an_official_independent_agency():
    data = record()
    data['verificada']['official_url'] = 'https://remax.com.ar'
    assert resolve_identity(data, 'agency:7')['identity_status'] == 'BLOCKED_EXTERNAL'
