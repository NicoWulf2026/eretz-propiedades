from __future__ import annotations

import json
from pathlib import Path

from scripts.agency_certifier import (
    classify_field,
    collapse_ratio,
    compare_runs,
    certification_status,
    diagnose_enumeration,
    external_portal,
    field_audit,
    needs_exhaustive_review,
    operational_metrics,
    source_signals,
    tokko_source_signals,
    wasi_source_signals,
    stable_signature,
)
from connectors.base import ErrorPermanente, Fuente
from connectors.generico import GenericoConnector, normalizar_texto_campos
from connectors.tokko import _tipo_propiedad
from connectors.wasi import _campos_descriptivos, _campos_wasi
from scripts import run_agency_certification_queue as certification_queue
from scripts.agency_fingerprints import (
    fingerprint_components,
    fingerprint_from_components,
    strategy_for,
)
from scripts.backfill_strategy_fingerprints import safe_to_backfill


def _property(url: str, fingerprint: str = "same", change: str = "SIN_CAMBIOS") -> dict:
    return {"source_url": url, "hash_dedup": url, "fingerprint": fingerprint,
            "_cambio": change}


def test_second_run_is_idempotent_when_inventory_and_content_match() -> None:
    run1 = {"_props": [_property("https://agency.test/p/1", change="NUEVA")]}
    run2 = {"_props": [_property("https://agency.test/p/1")]}
    assert compare_runs(run1, run2)["idempotent"] is True


def test_changed_page_two_is_not_hidden_by_stable_page_one() -> None:
    run1 = {"_props": [_property("https://agency.test/p/1"),
                        _property("https://agency.test/p/2")]}
    run2 = {"_props": [_property("https://agency.test/p/1"),
                        _property("https://agency.test/p/3", change="NUEVA")]}
    result = compare_runs(run1, run2)
    assert result["same_url_set"] is False
    assert result["missing_in_run2"] == 1
    assert result["new_in_run2"] == 1


def test_listings_sharing_one_identity_are_not_counted_as_inventory() -> None:
    """Regresion de `roomix:alcami inmobiliaria`.

    Tres tarjetas de una landing se enumeraban con URLs distintas que
    `hash_dedup` normalizaba a una sola —urlparse descarta el fragmento—, y la
    certificacion informaba tres propiedades donde la base habria guardado
    una. Contar cadenas no es contar inventario, y la enumeracion puede ser
    perfectamente estable y aun asi estar mal.
    """
    props = [
        {"source_url": "https://agency.test/#a", "hash_dedup": "una-sola",
         "fingerprint": "f1", "_cambio": "SIN_CAMBIOS"},
        {"source_url": "https://agency.test/#b", "hash_dedup": "una-sola",
         "fingerprint": "f2", "_cambio": "SIN_CAMBIOS"},
    ]
    result = compare_runs({"_props": props}, {"_props": props})
    assert result["run2_urls"] == 2
    assert result["run2_identities"] == 1
    assert result["identity_collisions"] == 1
    assert result["idempotent"] is True


def test_identity_collision_blocks_certification() -> None:
    """Certificar un inventario que colapsa seria afirmar una cantidad de
    propiedades que la base nunca va a tener."""
    enumeration = {"enumerated": 2, "pages_observed": 2,
                   "exhaustive_review_required": False, "review_reasons": []}
    comparison = {"same_url_set": True, "idempotent": True,
                  "identity_collisions": 1}
    run = {"estado": "OK", "detalles_fallidos": 0}
    status, reasons = certification_status(
        run, run, comparison, enumeration, {})
    assert status == "NEEDS_FIX"
    assert any("collapse into another identity" in r for r in reasons)


def test_repeated_pagination_response_is_visible_in_evidence() -> None:
    pages = {
        "https://agency.test/propiedades?p=1": {"sha256": "same", "requires_javascript_signal": False},
        "https://agency.test/propiedades?p=2": {"sha256": "same", "requires_javascript_signal": False},
    }
    result = diagnose_enumeration({"urls_unicas": 12, "total_declarado": 12,
                                    "enumeracion_completa": True, "cobertura": 1.0}, 12, pages)
    assert result["repeated_response_digests"] == 1


def test_sitemap_or_api_total_above_scraper_marks_independent_gap() -> None:
    result = diagnose_enumeration({"urls_unicas": 80, "total_declarado": 100,
                                    "enumeracion_completa": False, "cobertura": 0.8}, 90, {})
    assert result["independent_max_inventory_signal"] == 100
    assert result["independent_gap"] == 20
    assert result["independent_source_exceeds_scraper"] is True


def test_home_only_or_infinite_scroll_javascript_signal_is_visible() -> None:
    pages = {"https://agency.test": {"sha256": "a", "requires_javascript_signal": True}}
    result = diagnose_enumeration({"urls_unicas": 4, "total_declarado": None,
                                    "enumeracion_completa": True, "cobertura": None}, None, pages)
    assert result["javascript_signals"] == 1
    assert "LOW_INVENTORY_0_11" in result["review_reasons"]


def test_category_fragmentation_is_caught_by_baseline_collapse() -> None:
    review, reasons = needs_exhaustive_review(30, 180)
    assert review is True
    assert "COLLAPSE_GT_80_PERCENT" in reasons


def test_low_inventory_always_requires_exhaustive_review() -> None:
    assert needs_exhaustive_review(0, None) == (True, ["LOW_INVENTORY_0_11"])
    assert needs_exhaustive_review(11, 11)[0] is True
    assert needs_exhaustive_review(12, 12)[0] is False


def test_collapse_boundary_is_strictly_greater_than_eighty_percent() -> None:
    assert collapse_ratio(20, 100) == 0.8
    assert "COLLAPSE_GT_80_PERCENT" not in needs_exhaustive_review(20, 100)[1]
    assert "COLLAPSE_GT_80_PERCENT" in needs_exhaustive_review(19, 100)[1]


def test_source_not_provided_is_distinct_from_extraction_failure() -> None:
    assert classify_field(False, False) == "SOURCE_NOT_PROVIDED"
    assert classify_field(True, False) == "EXTRACTION_FAILED"
    assert classify_field(False, True) == "EXTRACTED"


def test_stable_signature_ignores_property_order() -> None:
    first = [_property("u1", "a"), _property("u2", "b")]
    second = list(reversed(first))
    assert stable_signature(first) == stable_signature(second)


def test_external_portals_are_never_certified_as_official_inventory() -> None:
    assert external_portal("https://www.zonaprop.com.ar/inmobiliarias/test") is True
    assert external_portal("https://agency.test/propiedades") is False


def test_external_only_catalog_is_a_terminal_block_not_false_zero() -> None:
    pages = {"https://agency.test": {
        "sha256": "stable", "requires_javascript_signal": False,
        "external_catalog_hosts": ["zonaprop.com.ar", "argenprop.com"],
    }}
    enumeration = diagnose_enumeration(
        {"urls_unicas": 0, "total_declarado": None,
         "enumeracion_completa": None, "cobertura": None}, None, pages)
    run = {"estado": "VARIANTE_NO_SOPORTADA", "detalles_fallidos": 0}
    comparison = {"same_url_set": True, "idempotent": True}
    status, reasons = certification_status(
        run, run, comparison, enumeration, {})
    assert status == "BLOCKED_EXTERNAL"
    assert reasons == [
        "official site delegates inventory to an external property portal"]
    assert enumeration["external_catalog_hosts"] == [
        "argenprop.com", "zonaprop.com.ar"]


def test_queue_does_not_repeat_current_identity_terminal_results(monkeypatch) -> None:
    record = {"platform": {}, "source": {"detected_platform": "UNKNOWN"}}
    identity_pending = {
        "status": "IDENTITY_PENDING",
        "certifier_version": certification_queue.CERTIFIER_VERSION,
    }
    identity_blocked = {
        "status": "BLOCKED_EXTERNAL",
        "certifier_version": certification_queue.CERTIFIER_VERSION,
    }
    assert certification_queue.is_current_result(identity_pending, record)
    assert certification_queue.is_current_result(identity_blocked, record)

    monkeypatch.setattr(certification_queue, "version_del_codigo",
                        lambda _connector: "fingerprint-current")
    assert not certification_queue.is_current_result({
        "status": "CERTIFIED_COMPLETE", "connector": "generico",
        "connector_version": "fingerprint-old",
    }, record)
    assert certification_queue.is_current_result({
        "status": "CERTIFIED_COMPLETE", "connector": "generico",
        "connector_version": "fingerprint-current",
    }, record)


def test_una_corrida_truncada_no_se_juzga_por_idempotencia() -> None:
    """Regresion de `roomix:abriola propiedades`.

    Su sitio sirve a 6,27 s por ficha. La primera corrida se corto exactamente
    en el tope del presupuesto con 238 de 263 fichas y la segunda las trajo
    todas, asi que la comparacion entre ambas no medía la fuente: medía el
    reloj. La certificacion lo informaba como "second run is not idempotent",
    que manda a buscar un defecto de extraccion que no existe.
    """
    truncada = {"estado": "PRESUPUESTO_AGOTADO", "detalles_fallidos": 0,
                "presupuesto_agotado": True, "enumeracion_agotada": True}
    completa = {"estado": "OK", "detalles_fallidos": 0,
                "enumeracion_agotada": True}
    comparacion = {"same_url_set": False, "idempotent": False,
                   "identity_collisions": 0}
    enumeracion = {"enumerated": 263, "pages_observed": 279,
                   "exhaustive_review_required": False, "review_reasons": []}

    estado, razones = certification_status(
        truncada, completa, comparacion, enumeracion, {})
    assert estado == "NEEDS_FIX"
    assert len(razones) == 1
    assert "time budget" in razones[0]
    assert not any("idempotent" in r for r in razones)


def test_el_presupuesto_del_cli_es_el_del_modulo() -> None:
    """El valor estaba escrito en tres lugares, y por eso subirlo no tuvo
    ningun efecto: el modulo decia 5.400 y los dos CLI seguian pasando 1.800,
    asi que alagna se volvio a truncar exactamente igual.

    Un default duplicado es una constante que miente.
    """
    import re

    from scripts.run_rollout import PRESUPUESTO_POR_FUENTE

    for archivo in ("scripts/agency_certifier.py",
                    "scripts/run_agency_certification_queue.py"):
        texto = Path(archivo).read_text(encoding="utf-8")
        numeros = re.findall(r'--budget"[^)]*?default=([\d.]+)', texto,
                             re.S)
        assert not numeros, f"{archivo} repite el presupuesto: {numeros}"
        assert "default=PRESUPUESTO_POR_FUENTE" in texto, archivo
    assert PRESUPUESTO_POR_FUENTE == 5400


def test_el_presupuesto_alcanza_para_las_fuentes_lentas_medidas() -> None:
    """Un presupuesto que trunca sistematicamente a una fuente le impide
    certificar POR SIEMPRE: reintentarla no cambia nada.

    Con el tope viejo de 1.800 s, abriola -6,3 s por ficha, 263 fichas- y
    alagna -15 s por ficha, 209 fichas- no podian certificarse nunca. Lo que se
    pierde ahi es inventario, que esta muy por encima del throughput.
    """
    from scripts.run_rollout import PRESUPUESTO_POR_FUENTE

    assert PRESUPUESTO_POR_FUENTE >= 263 * 7.0    # abriola
    assert PRESUPUESTO_POR_FUENTE >= 209 * 15.0   # alagna


def test_un_atributo_de_plataforma_que_parpadea_no_es_un_defecto() -> None:
    """Regresion de `roomix:alder inmobiliaria`.

    147 de 148 propiedades identicas entre corridas, y la restante difiere en
    un solo atributo opcional de `extra`: la fuente publico `superficie_privada`
    en una corrida y no en la otra. Verificado bajando la pagina tres veces
    seguidas: el valor esta siempre, asi que fue ruido transitorio de la fuente
    y no inestabilidad de la extraccion.

    La distincion no es de conveniencia. Los cinco defectos reales encontrados
    -prosa como barrio, tipo adivinado, ficha vacia, atributos corridos, fotos
    ajenas- se manifestaron TODOS en columnas del contrato. Ninguno en `extra`.
    """
    enumeracion = {"enumerated": 148, "pages_observed": 150,
                   "exhaustive_review_required": False, "review_reasons": [],
                   "collapse_ratio": 0.0}
    run = {"estado": "OK", "detalles_fallidos": 0, "enumeracion_agotada": True}
    comparacion = {"same_url_set": True, "idempotent": False,
                   "identity_collisions": 0, "same_contract_signature": True}

    estado, razones = certification_status(
        run, run, comparacion, enumeracion, {})
    assert estado == "CERTIFIED_BEST_AVAILABLE"
    assert razones == ["UNSTABLE_SOURCE_ATTRIBUTES"]


def test_una_columna_del_contrato_inestable_sigue_bloqueando() -> None:
    """La garantia que da el chequeo de idempotencia es sobre lo que el
    pipeline promete. Si eso cambia entre dos corridas separadas por segundos,
    es un defecto nuestro y bloquea."""
    enumeracion = {"enumerated": 148, "pages_observed": 150,
                   "exhaustive_review_required": False, "review_reasons": [],
                   "collapse_ratio": 0.0}
    run = {"estado": "OK", "detalles_fallidos": 0, "enumeracion_agotada": True}
    comparacion = {"same_url_set": True, "idempotent": False,
                   "identity_collisions": 0, "same_contract_signature": False}

    estado, razones = certification_status(
        run, run, comparacion, enumeracion, {})
    assert estado == "NEEDS_FIX"
    assert "second run is not idempotent" in razones


def test_la_firma_del_contrato_ignora_extra_pero_no_las_columnas() -> None:
    from scripts.agency_certifier import firma_de_columnas

    base = {"hash_dedup": "a", "titulo": "Casa", "precio": 100000,
            "extra": {"superficie_privada": 277.44}}
    sin_extra = {**base, "extra": {}}
    otro_precio = {**base, "precio": 120000}
    assert firma_de_columnas([base]) == firma_de_columnas([sin_extra])
    assert firma_de_columnas([base]) != firma_de_columnas([otro_precio])


def _enumeracion_corta() -> dict:
    return {"enumerated": 193, "pages_observed": 219, "collapse_ratio": 0.02,
            "exhaustive_review_required": False, "review_reasons": []}


def test_an_exhausted_pagination_below_the_declared_total_is_documented() -> None:
    """Regresion de `roomix:berrueta inmobiliaria`.

    Quedarse corto contra el total que el sitio declara DE SI MISMO se leia
    siempre como defecto nuestro. Verificado contra la fuente: el sitio declara
    197, su paginacion sirve 193, y la ficha 194 que aparecia era
    `/propiedad/0`, que devuelve el catalogo entero. El contador estaba mal, no
    la enumeracion.

    Llegar al final de la paginacion no prueba lo mismo que cortar por un
    error, asi que aqui es una limitacion documentada y no un defecto.
    """
    run = {"estado": "ENUMERACION_INCOMPLETA", "detalles_fallidos": 0,
           "enumeracion_agotada": True}
    comparison = {"same_url_set": True, "idempotent": True,
                  "identity_collisions": 0}
    status, reasons = certification_status(
        run, run, comparison, _enumeracion_corta(), {})
    assert status == "CERTIFIED_BEST_AVAILABLE"
    assert reasons == ["DECLARED_TOTAL_ABOVE_ENUMERATION"]


def test_an_interrupted_pagination_is_still_a_defect() -> None:
    """Cortar por un error no prueba nada sobre el inventario restante: puede
    faltar la mitad del catalogo y verse igual que haber terminado."""
    run = {"estado": "ENUMERACION_INCOMPLETA", "detalles_fallidos": 0,
           "enumeracion_agotada": False}
    comparison = {"same_url_set": True, "idempotent": True,
                  "identity_collisions": 0}
    status, reasons = certification_status(
        run, run, comparison, _enumeracion_corta(), {})
    assert status == "NEEDS_FIX"
    assert "one or both runs did not finish with connector state OK" in reasons


def test_a_severe_inventory_loss_is_not_excused_by_exhaustion() -> None:
    """La perdida grave la sigue atajando el colapso contra lo que esta
    inmobiliaria tenia, que es evidencia propia y no un numero que publica su
    propia pagina."""
    enumeracion = _enumeracion_corta()
    enumeracion["collapse_ratio"] = 0.9
    run = {"estado": "ENUMERACION_INCOMPLETA", "detalles_fallidos": 0,
           "enumeracion_agotada": True}
    comparison = {"same_url_set": True, "idempotent": True,
                  "identity_collisions": 0}
    status, reasons = certification_status(
        run, run, comparison, enumeracion, {})
    assert status == "NEEDS_FIX"
    assert any("collapsed" in r for r in reasons)


def test_zero_inventory_from_a_specific_connector_still_tries_the_generic() -> None:
    """Regresion de `roomix:analia requena propiedades`.

    El sitio es una app Laravel y se le asigno el connector de WordPress porque
    el HTML menciona `wp-content`. La corrida cerro en OK con cero propiedades
    y se reporto sin inventario, mientras el sitio publicaba trece paginas de
    fichas. Un connector que termina en OK con cero no distingue "no publica"
    de "elegimos el connector equivocado".
    """
    from scripts.agency_certifier import debe_reintentar_con_generico

    assert debe_reintentar_con_generico("wordpress", {"estado": "OK", "_props": []})
    assert debe_reintentar_con_generico(
        "tokko", {"estado": "VARIANTE_NO_SOPORTADA", "_props": []})


def test_the_generic_fallback_never_replaces_a_connector_that_found_inventory() -> None:
    """El fallback reemplaza al especifico, no lo complementa: si el especifico
    trajo propiedades, mezclar dos lecturas del mismo sitio duplicaria
    inventario o lo contaminaria con otra estrategia."""
    from scripts.agency_certifier import debe_reintentar_con_generico

    assert not debe_reintentar_con_generico(
        "wasi", {"estado": "OK", "_props": [{"source_url": "u"}]})
    assert not debe_reintentar_con_generico(
        "generico", {"estado": "OK", "_props": []})


def test_a_blocked_source_is_not_hit_again_with_another_connector() -> None:
    """La fuente rechazo el acceso automatico: volver a pedirle lo mismo con
    otro connector la golpea sin aprender nada."""
    from scripts.agency_certifier import debe_reintentar_con_generico

    assert not debe_reintentar_con_generico(
        "tokko", {"estado": "BLOQUEADA", "_props": []})


def test_two_runners_cannot_share_a_checkpoint(tmp_path) -> None:
    """Dos procesos escribiendo el mismo progreso se pisan el cursor y le
    vuelven a pedir a las mismas fuentes el mismo inventario: rompe la
    recuperabilidad y golpea sitios ajenos al doble del ritmo acordado."""
    import pytest

    cerrojo = certification_queue.tomar_cerrojo(tmp_path)
    assert cerrojo.exists()
    with pytest.raises(SystemExit) as fallo:
        certification_queue.tomar_cerrojo(tmp_path)
    assert "runner activo" in str(fallo.value)


def test_a_dead_runner_does_not_block_the_queue_forever(tmp_path) -> None:
    """Si el proceso murio sin soltar el cerrojo, la cola no puede quedar
    trabada para siempre. El latido vencido es cuatro veces la corrida mas
    larga observada, no un numero elegido de la nada."""
    cerrojo = certification_queue.tomar_cerrojo(tmp_path)
    viejo = json.loads(cerrojo.read_text(encoding="utf-8"))
    viejo["heartbeat_epoch"] -= certification_queue.LATIDO_VENCIDO + 1
    cerrojo.write_text(json.dumps(viejo), encoding="utf-8")

    # No levanta: el latido vencido lo declara muerto.
    certification_queue.tomar_cerrojo(tmp_path)


def test_the_lock_says_which_agency_was_in_flight(tmp_path) -> None:
    """Sin saber en cual quedo, reanudar obliga a adivinar."""
    cerrojo = certification_queue.tomar_cerrojo(tmp_path)
    certification_queue.latir(cerrojo, "roomix:alfa")
    assert json.loads(cerrojo.read_text(encoding="utf-8"))["current_agency"] == (
        "roomix:alfa")


def test_ready_queue_only_includes_resolved_identities(monkeypatch) -> None:
    """Certificar una fuente cuya identidad no resuelve gasta dos corridas en
    vivo contra un sitio de terceros para producir inventario que despues no
    se puede asociar a ninguna inmobiliaria real."""
    catalog = {
        "roomix:resuelta": {"identity": "READY"},
        "roomix:pendiente": {"identity": "IDENTITY_PENDING"},
        "roomix:bloqueada": {"identity": "BLOCKED_EXTERNAL"},
    }
    monkeypatch.setattr(
        certification_queue, "resolve_identity",
        lambda record, key: {"identity_status": record["identity"]})
    assert certification_queue.ready_queue(catalog) == ["roomix:resuelta"]


def test_runner_failure_never_closes_an_agency(tmp_path) -> None:
    """Un crash del runner no es evidencia sobre la inmobiliaria.

    No prueba que no publique ni que su sitio este roto. Guardarlo como estado
    terminal escribiria un problema nuestro como un hecho sobre la fuente, y
    la cola no volveria a intentarla nunca.
    """
    try:
        raise TimeoutError("la fuente no respondio")
    except TimeoutError as error:
        result = certification_queue.runner_error(tmp_path, "roomix:x", error)

    assert result["status"] == "RUNNER_ERROR"
    assert result["status"] not in certification_queue.TERMINAL
    assert not certification_queue.is_current_result(
        result, {"platform": {}, "source": {"detected_platform": "UNKNOWN"}})

    # El traceback queda en el log de errores, no en el rollup de resultados.
    assert "traceback" not in result
    registrado = [json.loads(line) for line
                  in (tmp_path / "AGENCY_RUNNER_ERRORS.jsonl").read_text(
                      encoding="utf-8").splitlines() if line.strip()]
    assert len(registrado) == 1
    assert registrado[0]["reasons"] == ["TimeoutError: la fuente no respondio"]
    assert "TimeoutError" in registrado[0]["traceback"]


def test_runner_failure_result_survives_the_rollups(tmp_path) -> None:
    """El resultado de error viaja por las mismas agregaciones que un cierre
    normal: si no tuviera la forma esperada, el manejo del fallo seria el que
    tumbaria la corrida."""
    try:
        raise ValueError("fuente rota")
    except ValueError as error:
        result = certification_queue.runner_error(tmp_path, "roomix:x", error)
    certification_queue.update_rollups(tmp_path, result)
    filas = [json.loads(line) for line
             in (tmp_path / "AGENCY_CERTIFICATION_RESULTS.jsonl").read_text(
                 encoding="utf-8").splitlines() if line.strip()]
    assert [f["status"] for f in filas] == ["RUNNER_ERROR"]


def test_mapaprop_change_does_not_invalidate_php_strategy() -> None:
    mapaprop = fingerprint_components("generico", "generic/mapaprop")
    php = fingerprint_components("generico", "generic/php_query_catalog")
    mapaprop_before = fingerprint_from_components(mapaprop)
    php_before = fingerprint_from_components(php)
    changed = dict(mapaprop)
    changed["strategy/generic/mapaprop"] += b"mapaprop-change"
    assert fingerprint_from_components(changed) != mapaprop_before
    assert fingerprint_from_components(php) == php_before


def test_shared_base_and_certifier_changes_invalidate_both_strategies() -> None:
    for shared in ("shared/base", "shared/certifier"):
        fingerprints = []
        for strategy in ("generic/mapaprop", "generic/php_query_catalog"):
            components = fingerprint_components("generico", strategy)
            before = fingerprint_from_components(components)
            changed = dict(components)
            changed[shared] += b"shared-change"
            fingerprints.append((before, fingerprint_from_components(changed)))
        assert all(before != after for before, after in fingerprints)


def test_publication_mechanism_selects_persisted_strategy() -> None:
    assert strategy_for("generico", "MAPAPROP_HTML") == "generic/mapaprop"
    assert strategy_for("generico", "QUERY_CATALOG_HTML") == (
        "generic/php_query_catalog")
    assert strategy_for("tokko", "TFW_ESTANDAR") == "tokko"


def test_queue_uses_strategy_fingerprint_when_present(monkeypatch) -> None:
    record = {"platform": {}, "source": {"detected_platform": "UNKNOWN"}}
    monkeypatch.setattr(certification_queue, "strategy_fingerprint",
                        lambda connector, strategy: f"{connector}:{strategy}:ok")
    current = {
        "status": "CERTIFIED_COMPLETE", "connector": "generico",
        "publication_mechanism": "MAPAPROP_HTML",
        "connector_strategy": "generic/mapaprop",
        "strategy_fingerprint": "generico:generic/mapaprop:ok",
    }
    assert certification_queue.is_current_result(current, record)
    current["strategy_fingerprint"] = "stale"
    assert not certification_queue.is_current_result(current, record)


def test_fingerprint_backfill_requires_terminal_clean_evidence() -> None:
    clean = {
        "status": "CERTIFIED_COMPLETE", "connector": "generico",
        "comparison": {"idempotent": True},
        "run1": {"detalles_fallidos": 0},
        "run2": {"detalles_fallidos": 0},
    }
    assert safe_to_backfill(clean)
    assert not safe_to_backfill({**clean, "status": "NEEDS_FIX"})
    assert not safe_to_backfill({
        **clean, "run2": {"detalles_fallidos": 1}})
    assert safe_to_backfill({
        "status": "BLOCKED_EXTERNAL", "connector": "generico"})


def test_global_checkpoint_contains_resume_coordinates(monkeypatch) -> None:
    monkeypatch.setattr(certification_queue, "fingerprint_inventory", lambda: {
        "connector_fingerprints": {"generico": "whole"},
        "strategy_fingerprints": {"generic/html_catalog": "strategy"},
    })
    payload = certification_queue.progress_payload(
        mode="full", universe=3, queue=["a", "b", "c"],
        pending=["b", "c"], current_count=1,
        started_at="2026-09-01T00:00:00", global_cursor=1,
        last_terminal_agency="a", current_agency="b",
        current_phase="CERTIFY")
    assert payload["global_cursor"] == 1
    assert payload["last_terminal_agency"] == "a"
    assert payload["next_agency"] == "b"
    assert payload["pending_count"] == 2
    assert payload["certified_count"] == 1
    assert payload["current_agency"] == "b"
    assert payload["current_phase"] == "CERTIFY"
    assert payload["last_heartbeat"]
    assert payload["queue_fingerprint"]


def test_queue_fingerprint_detects_changed_order_or_mode() -> None:
    original = certification_queue.queue_fingerprint(["a", "b"], "full")
    assert original == certification_queue.queue_fingerprint(["a", "b"], "full")
    assert original != certification_queue.queue_fingerprint(["b", "a"], "full")
    assert original != certification_queue.queue_fingerprint(["a", "b"], "pilot-2")


def test_operational_metrics_are_explainable_and_local() -> None:
    first = type("Download", (), {"pedidos": 12})()
    second = type("Download", (), {"pedidos": 10})()
    metrics = operational_metrics(
        "agency", "generico", "generic/html_catalog",
        {"segundos": 4.5, "reintentos_diferidos": 1,
         "detalles_fallidos": 0},
        {"segundos": 5.5, "reintentos_diferidos": 0,
         "detalles_fallidos": 0, "detalles_obtenidos": 11},
        first, second, "CERTIFIED_COMPLETE")
    assert metrics["properties"] == 11
    assert metrics["requests"] == 22
    assert metrics["duration_seconds"] == 10.0
    assert metrics["requests_per_property"] == 2.0
    assert metrics["retries"] == 1
    assert metrics["network_errors"] == 0


def test_generic_connector_reads_buscadorprop_infinite_json_pagination() -> None:
    class Downloader:
        def bajar(self, url: str) -> str:
            if "sitemap" in url:
                raise ErrorPermanente("missing")
            if "infinito=1&pagina=2" in url:
                return '["<a href=\\"/propiedad/1003\\">three</a>"]'
            if "infinito=1&pagina=" in url:
                return "[]"
            if url.rstrip("/") == "https://agency.test/propiedades":
                return ('Se encontraron 3 resultados '
                        '<a href="/propiedad/1001">one</a>'
                        '<a href="/propiedad/1002">two</a>')
            return '<a href="/propiedad/1001">featured</a>'

    connector = GenericoConnector(Downloader())
    source = Fuente("canonical", "Agency", "https://agency.test")
    plan = connector.discover(source)
    listings = list(connector.fetch_listing(source, plan))
    assert plan["total_declarado"] == 3
    assert {row["source_listing_id"] for row in listings} == {"1001", "1002", "1003"}


def test_generic_connector_accepts_public_jsonld_with_literal_newline() -> None:
    html = '''<script type="application/ld+json">{
      "@type":"RealEstateListing",
      "description":"line one
line two",
      "address":{"streetAddress":"Calle 1 234","addressLocality":"Ciudad"}
    }</script>'''
    parsed = GenericoConnector._de_json_ld(html)
    assert parsed["direccion"] == "Calle 1 234"
    assert parsed["ciudad"] == "Ciudad"


def test_generic_connector_rejects_listing_sort_routes_as_properties() -> None:
    html = '''
      <a href="/propiedades/precio-menor-a-mayor">sort</a>
      <a href="/propiedades/mas-nuevas">newest</a>
      <a href="/propiedad/1001">property</a>
    '''
    assert GenericoConnector._fichas_en(html, "https://agency.test") == [
        "https://agency.test/propiedad/1001"
    ]


def test_generic_connector_detects_p_id_underscore_only_per_source_with_three_examples() -> None:
    html = "".join(
        f'<a href="p-{number}_duplex-interno-de-dos-dormitorios">property</a>'
        for number in (1752, 1751, 1750)
    )
    pattern = GenericoConnector._patron_raiz_local(html)
    assert pattern is not None
    assert len(GenericoConnector._fichas_en(html, "https://agency.test", pattern)) == 3


def test_generic_connector_does_not_enable_root_pattern_from_one_example() -> None:
    html = '<a href="/p-1752_duplex-interno-de-dos-dormitorios">property</a>'
    assert GenericoConnector._patron_raiz_local(html) is None


def test_source_signals_ignore_related_cards_and_icons_without_values() -> None:
    html = '''
      <main><img alt="direccion" src="pin.svg"><img src="logo.png"></main>
      <section id="relacionadas">
        <p class="direccion">Calle falsa 123</p><span>3 ambientes</span>
        <img src="/prop_new/1.jpg">
      </section>
    '''
    signals = source_signals(html)
    assert signals["direccion"] is False
    assert signals["ambientes"] is False
    assert signals["imagenes"] is False


def test_source_signals_require_real_main_property_values() -> None:
    html = '''
      <p class="direccion"><img alt="direccion"> Calle 1 234</p>
      <span>3 ambientes</span><meta property="og:image" content="/prop_new/1.jpg">
    '''
    signals = source_signals(html)
    assert signals["direccion"] is True
    assert signals["ambientes"] is True
    assert signals["imagenes"] is True


def test_generic_address_fallback_uses_only_structured_main_block() -> None:
    html = '''<p class="direccion"><img alt="direccion"> Calle 1 234, Ciudad</p>
              <section id="relacionadas"><p class="direccion">Otra 9</p></section>'''
    assert GenericoConnector._direccion_de(html) == "Calle 1 234, Ciudad"


def test_field_audit_distinguishes_validation_rejection_from_extraction_failure() -> None:
    props = [{"source_url": "https://agency.test/p/1", "ambientes": None,
              "extra": {"atributos_descartados": "dormitorios>ambientes"}}]
    pages = {"https://agency.test/p/1": {
        "source_signals": {field: field == "ambientes" for field in (
            "titulo", "descripcion", "precio", "moneda", "operacion",
            "tipo_propiedad", "direccion", "barrio", "ciudad", "provincia",
            "ambientes", "dormitorios", "banos", "superficie_total",
            "superficie_cubierta", "latitud", "longitud", "imagenes")}}}
    result = field_audit(props, pages)["ambientes"]
    assert result["state"] == "REJECTED_BY_VALIDATION"
    assert result["validation_rejected"] == 1
    assert result["extraction_failed"] == 0


def test_field_audit_wordpress_rest_uses_structured_source_evidence() -> None:
    props = [{
        "source_url": "https://agency.test/propiedad/1/", "connector": "wordpress",
        "operacion": "venta", "tipo_propiedad": None,
        "extra": {
            "via": "rest",
            "source_fields_provided": {"operacion": True, "tipo_propiedad": True},
            "atributos_descartados": "tipo_propiedad:taxonomia_no_mapeada",
        },
    }]
    # No existe una pagina HTML individual en la evidencia: la fuente es el
    # objeto REST y aun asi el auditor debe distinguir extraccion de rechazo.
    audit = field_audit(props, {})
    assert audit["operacion"]["state"] == "EXTRACTED"
    assert audit["tipo_propiedad"]["state"] == "REJECTED_BY_VALIDATION"
    assert audit["tipo_propiedad"]["extraction_failed"] == 0


def test_field_audit_wordpress_does_not_count_shared_site_images_as_source() -> None:
    props = [{
        "source_url": "https://agency.test/propiedad/1/", "connector": "wordpress",
        "imagenes": [], "extra": {
            "via": "rest", "source_fields_provided": {"imagenes": True}},
    }]
    result = field_audit(props, {})["imagenes"]
    assert result["state"] == "SOURCE_NOT_PROVIDED"
    assert result["source_provided"] == 0
    assert result["extraction_failed"] == 0


def test_field_audit_xintel_marks_invalid_coordinates_as_validation_rejection() -> None:
    props = [{
        "source_url": "https://agency.test/cochera-ficha-abc1",
        "latitud": None, "longitud": None,
        "extra": {
            "via": "xintel_api",
            "source_fields_provided": {"latitud": True, "longitud": True},
            "atributos_descartados": "coordenada_fuera_de_argentina",
        },
    }]
    audit = field_audit(props, {})
    assert audit["latitud"]["state"] == "REJECTED_BY_VALIDATION"
    assert audit["longitud"]["state"] == "REJECTED_BY_VALIDATION"
    assert audit["latitud"]["extraction_failed"] == 0


def test_verified_runtime_catalog_allows_property_without_price_or_schema() -> None:
    text = "Casa en venta con 3 dormitorios y 2 baños"
    images = ["1.jpg", "2.jpg", "3.jpg"]
    assert GenericoConnector._confirma_ficha(
        "<html></html>", text, None, images, None, catalogo_verificado=True) is True
    assert GenericoConnector._confirma_ficha(
        "<html></html>", text, None, images, None, catalogo_verificado=False) is False


def test_verified_runtime_catalog_accepts_real_property_with_one_photo() -> None:
    text = "Terreno en venta con superficie total y servicios"
    assert GenericoConnector._confirma_ficha(
        "<html></html>", text, 48000, ["1.jpg"], None,
        catalogo_verificado=True) is True
    assert GenericoConnector._confirma_ficha(
        "<html></html>", text, 48000, ["1.jpg"], None,
        catalogo_verificado=False) is False


def test_verified_runtime_catalog_ignores_legacy_article_metadata() -> None:
    html = '<meta property="og:type" content="article">'
    text = "Departamento en venta con 2 dormitorios y 1 baño"
    images = ["1.jpg", "2.jpg", "3.jpg"]
    assert GenericoConnector._confirma_ficha(
        html, text, 185000, images, None, catalogo_verificado=True) is True
    assert GenericoConnector._confirma_ficha(
        html, text, 185000, images, None, catalogo_verificado=False) is False


def test_generic_legacy_portal_extracts_visible_description_and_toilette() -> None:
    html = '''<html><head><title>Local en alquiler</title></head><body>
      <div class="title_blue">Detalles</div>
      <ul><li>Toilettes: <span class="numero">1</span></li></ul>
      <div class="title_blue">Descripci&oacute;n</div>
      <div class="fck" id="fck_contain">Local comercial en esquina con
      amplia vidriera y doble altura.</div>
      <img src="/f/1.jpg"><img src="/f/2.jpg"><img src="/f/3.jpg">
    </body></html>'''
    connector = GenericoConnector(type("Downloader", (), {"bajar": lambda _self, _url: html})())
    source = Fuente("canonical", "Agency", "https://agency.test")
    prop = connector.normalize({
        "source_listing_id": "4759",
        "source_url": "https://agency.test/alquiler/local/local-esquina-4759",
        "por_forma": True,
        "catalogo_runtime_verificado": True,
        "pagina": 1,
    }, source)
    assert prop is not None
    assert prop.banos == 1
    assert prop.descripcion == (
        "Local comercial en esquina con amplia vidriera y doble altura.")
    assert source_signals(html)["descripcion"] is True


def test_generic_php_portal_extracts_explicit_separator_description() -> None:
    html = '''<html><head><title>Casa en Venta</title></head><body>
      <div class="separador-titulo">Descripción</div>
      <p>Casa moderna con amplio living comedor, cocina integrada y patio.</p>
      <div>Venta USD 98.000</div>
      <img src="/f/1.jpg"><img src="/f/2.jpg"><img src="/f/3.jpg">
      ''' + " relleno seguro" * 20 + "</body></html>"
    connector = GenericoConnector(
        type("Downloader", (), {"bajar": lambda _self, _url: html})())
    prop = connector.normalize({
        "source_listing_id": "9480098",
        "source_url": "https://agency.test/propiedad.php?id=9480098",
        "por_forma": False,
    }, Fuente("canonical", "Agency", "https://agency.test"))
    assert prop is not None
    assert prop.descripcion == (
        "Casa moderna con amplio living comedor, cocina integrada y patio.")


def test_generic_structured_count_label_wins_over_narrative_numbers() -> None:
    texto = "5 ambientes con baño sauna. Ambientes: 5 Dormitorios: 4 Baños: 5"
    assert GenericoConnector._cuenta(texto, r"dormitorios?", None) == 4
    assert GenericoConnector._cuenta(texto, r"ba[nñ]os?", None) == 5


def test_generic_zero_placeholder_allows_explicit_narrative_count() -> None:
    texto = "Propiedad con 1 baño completo. Baños: 0"
    assert GenericoConnector._cuenta(texto, r"ba[nñ]os?", None) == 1


def test_generic_count_uses_later_positive_alias_after_zero_placeholder() -> None:
    texto = "Ambientes: 2 Dormitorios: 0 Baños: 0 Toilettes: 2"
    assert GenericoConnector._cuenta(
        texto, r"ba[nñ]os?|toilettes?", None) == 2


def test_generic_legacy_labels_without_colon_are_structured_counts() -> None:
    html = ('<div class="desc">Dormitorios</div><div class="valor">10</div>'
            '<div class="desc">Ba�os</div><div class="valor">4</div>'
            '<div class="desc">Ambientes</div><div class="valor">5</div>')
    texto = "Caracteristicas Dormitorios 10 Baños 4 Cocheras 9 Ambientes 5"
    assert GenericoConnector._cuenta_de_ficha(
        html, texto, r"dormitorios?", None) == 10
    assert GenericoConnector._cuenta_de_ficha(
        html, texto, r"ba[nñ]os?", None) == 4
    assert GenericoConnector._cuenta_de_ficha(
        html, texto, r"ambientes?", None) == 5


def test_generic_structured_label_followed_by_number_span() -> None:
    html = ('<button><i class="fas fa-bed"></i> Dormitorios '
            '<span class="number">2</span></button>')
    assert GenericoConnector._cuenta_de_ficha(
        html, "Dormitorios 2", r"dormitorios?", None) == 2


def test_generic_legacy_mojibake_is_aligned_with_source_audit() -> None:
    html = "<main>Caracteristicas Ba�o 1 Ambientes 1</main>"
    signals = source_signals(html)
    assert signals["banos"] is True
    assert "Baño 1" in normalizar_texto_campos(html)


def test_generic_operation_and_source_status_from_explicit_copy() -> None:
    assert GenericoConnector._operacion_en_la_ficha(
        "Reservado. Contrato. Alquiler inicial $1.000.000") == "alquiler"
    assert GenericoConnector._estado_fuente("Reservado | Casa") == "reservado"


def test_consumated_source_status_preserves_operation() -> None:
    assert GenericoConnector._operacion_en_la_ficha(
        "Reservado. Alquilada. Consultar por credito hipotecario") == "alquiler"
    assert GenericoConnector._operacion_en_la_ficha(
        "Propiedad vendida. Consulte alternativas") == "venta"


def test_source_signals_ignore_zero_quantities_and_isolated_currency() -> None:
    signals = source_signals(
        "<html><head><meta content='USD'></head><body>"
        "<main>Dormitorios: 0 Baños: 0 Ambientes: 0</main></body></html>")
    assert signals["moneda"] is False
    assert signals["dormitorios"] is False
    assert signals["banos"] is False
    assert signals["ambientes"] is False


def test_source_signals_accept_positive_quantities_and_priced_currency() -> None:
    signals = source_signals(
        "<html><body><main>USD 185.000 · 3 dormitorios · 2 baños</main></body></html>")
    assert signals["moneda"] is True
    assert signals["dormitorios"] is True
    assert signals["banos"] is True


def test_source_signals_development_does_not_borrow_child_unit_fields() -> None:
    html = """<main><h1>Proyecto Central</h1><p>Desarrollo en construcción</p>
      <h2>UNIDADES</h2><article>2 ambientes 1 dormitorio 1 baño en venta</article>
      </main>"""
    signals = source_signals(html, "https://agency.test/emprendimiento/1")
    assert signals["operacion"] is False
    assert signals["ambientes"] is False
    assert signals["dormitorios"] is False
    assert signals["banos"] is False


def test_source_signals_development_ignores_institutional_seo_operation() -> None:
    html = """<html><head><meta name="description"
      content="Propiedades en venta en Hurlingham"><title>Proyecto Central</title>
      </head><body><main><p>Desarrollo en construcción.</p>
      <h3>UNIDADES</h3><article>Departamento en venta</article></main></body></html>"""
    signals = source_signals(html, "https://agency.test/emprendimiento/1")
    assert signals["operacion"] is False


def test_source_signals_ignore_related_property_quantities() -> None:
    signals = source_signals(
        "<html><body><main>Terreno. Dormitorios: 0</main>"
        "<div class='titulo_prod_int'>Otras Propiedades</div>"
        "<article>Casa vecina de 2 dormitorios</article></body></html>")
    assert signals["dormitorios"] is False


def test_source_signals_ignore_legacy_catalog_filter_after_detail() -> None:
    html = """<main><h1>Terreno</h1><p>Superficie terreno: 728 m2</p>
      <button id="dProp_dorm">Dormitorios</button>
      <label name="search_filter[cntProp_rooms]">1 dormitorio</label>
      <label name="search_filter[cntProp_rooms]">3 ambientes</label></main>"""
    signals = source_signals(html)
    assert signals["dormitorios"] is False
    assert signals["ambientes"] is False


def test_numeric_property_family_excludes_catalog_filters() -> None:
    urls = [
        "https://agency.test/propiedad/101",
        "https://agency.test/propiedad/102",
        "https://agency.test/propiedad/103",
        "https://agency.test/propiedades/lomas-de-zamora",
    ]
    pattern = GenericoConnector._patron_catalogo_numerico(urls)
    assert pattern is not None
    assert pattern.match("/propiedad/101")
    assert not pattern.match("/propiedades/lomas-de-zamora")


def test_offset_portal_family_is_local_and_id_prefers_slug_tail() -> None:
    html = "".join([
        '<a href="/venta/casas/casa-2-dormitorios-4675">a</a>',
        '<a href="/venta/departamentos/depto-1-dormitorio-4616">b</a>',
        '<a href="/alquiler/local/local-2-plantas-4754">c</a>',
    ])
    pattern = GenericoConnector._patron_portal_offset_local(html)
    assert pattern is not None
    assert pattern.match("/venta/casas/casa-2-dormitorios-4675")
    assert GenericoConnector._id_de(
        "https://agency.test/venta/casas/casa-2-dormitorios-4675") == "4675"


def test_dpto_abbreviation_is_a_department() -> None:
    from connectors.base import detectar_tipo

    assert detectar_tipo("Impecable dpto en venta") == "departamento"


def test_tokko_property_type_normalizes_diacritics() -> None:
    assert _tipo_propiedad("Galpón en Venta") == "galpon"
    assert _tipo_propiedad("Depósito industrial") == "galpon"


def test_wasi_singular_and_mojibake_labels_are_structured() -> None:
    html = ('<li><strong>Ba�o:</strong> 1</li>'
            '<li><strong>N�mero de planta:</strong> 2</li>')
    fields = _campos_wasi(html)
    assert fields["banos"] == 1
    assert fields["plantas"] == 2


def test_wasi_description_only_accepts_unambiguous_scalars() -> None:
    fields, rejected = _campos_descriptivos(
        "Casa con 3 dormitorios, 2 baños. Superficie de Terreno 700 m2. "
        "Construidos 194 m2.", "casa")
    assert fields == {"dormitorios": 3, "banos": 2,
                      "superficie_total": 700,
                      "superficie_cubierta": 194}
    assert rejected == set()

    fields, rejected = _campos_descriptivos(
        "Cabaña 1: 2 baños. Cabaña 2: 2 baños.", "casa")
    assert "banos" not in fields
    assert "banos" in rejected


def test_wasi_audit_signals_match_description_contract() -> None:
    html = ('<script type="application/ld+json">{"description":"Casa con '
            '3 ambientes y superficie cubierta 80 m2","address":{}}</script>')
    signals = wasi_source_signals(html)
    assert signals["ambientes"] is True
    assert signals["superficie_cubierta"] is True


def test_declared_total_accepts_semantic_markup() -> None:
    assert GenericoConnector._total_declarado_en(
        "Se encontraron <strong>6.597 resultados</strong> en propiedades") == 6597


def test_tokko_audit_ignores_related_price_and_reads_structured_fields() -> None:
    body = (
        "<html><head><meta property=\"og:title\" content=\"Casa en Venta\"></head>"
        "<body>Dormitorios 3 Baños 2 Total construido 180 m² Terreno: 250 m² "
        "DESCRIPCIÓN Una descripción suficientemente larga de la propiedad "
        "con información útil para quien la consulta. Contacto "
        "Propiedades relacionadas USD 99.000</body></html>")
    signals = tokko_source_signals(body, "https://agency.test/p/123-casa")
    assert signals["precio"] is False
    assert signals["dormitorios"] is True
    assert signals["banos"] is True
    assert signals["superficie_total"] is True
    assert signals["superficie_cubierta"] is True
