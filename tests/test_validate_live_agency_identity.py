# -*- coding: utf-8 -*-
"""Que el nombre coincida no prueba que sea la misma inmobiliaria.

Codex dejó esto anotado como pendiente abierto, detectado por lectura y **no
corregido**:

    `validate_live_agency_identity.py`: revisión sólo lectura detectó
    name_exact como VALIDATED aunque domain_match sea false; IDs de
    manifest/live sobrescritos en dict, unexpected rows chequeados después de
    escribir output.

Los tres son del mismo tipo: el validador afirma más de lo que comprobó.

«Lopez Propiedades» hay muchas. El nombre normalizado coincidiendo es
evidencia; el dominio coincidiendo es otra. Declarar `VALIDATED` con la
primera sola es exactamente confundir evidencia de nombre con identidad, que
es la línea que este proyecto no cruza —«no mezclar agencias»—.

El módulo no está en ninguna huella, así que corregirlo cuesta **cero
recertificaciones**.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
GUION = RAIZ / "scripts" / "validate_live_agency_identity.py"


def correr(manifest: list[dict], vivas: list[dict], tmp_path: Path):
    ruta_manifest = tmp_path / "manifest.jsonl"
    ruta_manifest.write_text(
        "".join(json.dumps(r) + "\n" for r in manifest), encoding="utf-8")
    salida = tmp_path / "salida.jsonl"
    entrada = json.dumps({"rows": vivas}) + "\n" + json.dumps({"_end": True}) + "\n"
    proceso = subprocess.run(
        [sys.executable, str(GUION), "--manifest", str(ruta_manifest),
         "--output", str(salida)],
        input=entrada, capture_output=True, text=True)
    filas = []
    if salida.exists():
        filas = [json.loads(l) for l in salida.read_text(encoding="utf-8").splitlines()
                 if l.strip()]
    return proceso, filas, salida


def canonica(ident=1, nombre="Lopez Propiedades", dominio="https://lopez.com.ar"):
    return {"eretz_id": ident, "resolution_status": "RESOLVED",
            "canonical_agency_id": f"roomix:{nombre.lower()}",
            "agency_name": nombre, "official_domain": dominio}


def viva(ident=1, nombre="Lopez Propiedades", web="https://lopez.com.ar"):
    return {"id": ident, "nombre": nombre, "web": web, "ciudad": "Rosario",
            "provincia": "Santa Fe", "phone_present": True,
            "email_present": True}


def test_nombre_y_dominio_coinciden_es_validado(tmp_path):
    proceso, filas, _ = correr([canonica()], [viva()], tmp_path)
    assert filas[0]["validation_status"] == "VALIDATED", proceso.stdout
    assert proceso.returncode == 0


def test_MUERDE_el_nombre_solo_no_alcanza_para_validar(tmp_path):
    """El defecto que Codex encontró y no corrigió.

    Mismo nombre, otro dominio. Antes salía `VALIDATED` y el `domain_match`
    quedaba como una señal informativa que nadie miraba.
    """
    _, filas, _ = correr([canonica(dominio="https://lopez.com.ar")],
                         [viva(web="https://otra-inmobiliaria.com.ar")],
                         tmp_path)
    assert filas[0]["validation_status"] != "VALIDATED"
    assert filas[0]["validation_status"] == "NOMBRE_SIN_DOMINIO"


def test_un_dominio_en_conflicto_hace_fallar_la_corrida(tmp_path):
    """No basta con anotarlo: la corrida tiene que terminar en rojo.

    Un validador que escribe la contradicción y devuelve 0 deja que el
    pipeline siga como si nada.
    """
    proceso, _, _ = correr([canonica()],
                           [viva(web="https://otra.com.ar")], tmp_path)
    assert proceso.returncode != 0


def test_sin_web_en_la_fila_viva_no_se_puede_comparar_y_se_dice(tmp_path):
    """Distinguir «no coincide» de «no se pudo comparar».

    Si la fila viva no trae web, el dominio no contradice nada. Tratarlo como
    contradicción convertiría en error una ausencia de dato, y tratarlo como
    validación afirmaría lo que no se comprobó.
    """
    proceso, filas, _ = correr([canonica()], [viva(web=None)], tmp_path)
    assert filas[0]["validation_status"] == "NOMBRE_SIN_WEB_VIVA"
    assert proceso.returncode == 0


def test_el_nombre_distinto_sigue_siendo_contradiccion(tmp_path):
    proceso, filas, _ = correr([canonica()],
                               [viva(nombre="Perez Inmuebles")], tmp_path)
    assert filas[0]["validation_status"] == "CONTRADICTION"
    assert proceso.returncode != 0


def test_MUERDE_dos_filas_vivas_con_el_mismo_id_no_se_pisan(tmp_path):
    """`live[int(row["id"])] = row` se quedaba con la última, en silencio.

    Dos filas con el mismo id son evidencia en conflicto sobre una identidad.
    Quedarse con una es elegir sin decir que se eligió.
    """
    proceso, _, _ = correr([canonica()],
                           [viva(nombre="Lopez Propiedades"),
                            viva(nombre="Lopez Propiedades SRL")], tmp_path)
    assert proceso.returncode != 0
    assert "id" in (proceso.stderr + proceso.stdout).lower()


def test_MUERDE_dos_filas_del_manifest_con_el_mismo_id_tampoco(tmp_path):
    proceso, _, _ = correr([canonica(nombre="Lopez Propiedades"),
                            canonica(nombre="Otra Cosa")],
                           [viva()], tmp_path)
    assert proceso.returncode != 0


def test_MUERDE_las_filas_inesperadas_se_detectan_ANTES_de_escribir(tmp_path):
    """Antes se escribía el artefacto y después se levantaba la excepción.

    Un archivo de evidencia escrito por una corrida que terminó en error es
    peor que ninguno: parece bueno.
    """
    proceso, _, salida = correr([canonica(ident=1)],
                                [viva(ident=1), viva(ident=99)], tmp_path)
    assert proceso.returncode != 0
    assert not salida.exists(), "no se debe dejar un artefacto de una corrida fallida"
