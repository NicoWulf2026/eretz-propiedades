"""El descargador verifica contra el almacen del sistema y el de certifi."""
from __future__ import annotations

import ssl

import certifi

from connectors.base import contexto_tls


def test_suma_las_raices_de_certifi_sin_aflojar_la_verificacion():
    ctx = contexto_tls()
    assert ctx.verify_mode == ssl.CERT_REQUIRED and ctx.check_hostname
    base = ssl.create_default_context()
    base_count = len(base.get_ca_certs())
    solo_certifi = ssl.create_default_context(cafile=certifi.where())
    assert len(ctx.get_ca_certs()) >= max(base_count, len(solo_certifi.get_ca_certs()))
