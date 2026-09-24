# -*- coding: utf-8 -*-
"""Un texto que es el mismo en la mitad de las fichas no describe a ninguna.

`coldwell banker de la vera cruz` tenía la misma descripción en sus 266
propiedades —el pie del sitio— y quedó CERTIFIED_COMPLETE.
"""
from __future__ import annotations

from types import SimpleNamespace

from scripts.run_rollout import descartar_descripciones_compartidas

PIE = ("© 2026 Coldwell Banker. Todos los derechos reservados. Coldwell "
       "Banker y los logotipos de Coldwell Banker son marcas de servicio")


def _prop(descripcion):
    return SimpleNamespace(descripcion=descripcion, extra={})


def test_MUERDE_la_misma_descripcion_en_todas_las_fichas_se_descarta():
    props = [_prop("Texto institucional de la inmobiliaria, igual en todas las fichas")
             for _ in range(12)]
    assert descartar_descripciones_compartidas(props) == 12
    assert all(p.descripcion is None for p in props)
    assert props[0].extra["descripcion_descartada"] == "compartida_por_la_agencia"


def test_MUERDE_un_aviso_legal_no_es_una_descripcion_aunque_sea_uno_solo():
    """`coldwell banker andes`: 5 de 174, que la regla de frecuencia no ve."""
    props = [_prop(f"Casa numero {i} con jardin y pileta en barrio tranquilo")
             for i in range(20)]
    props.append(_prop(PIE))
    assert descartar_descripciones_compartidas(props) == 1
    assert props[-1].descripcion is None
    assert props[-1].extra["descripcion_descartada"] == "aviso_legal"
    assert props[0].descripcion is not None


def test_unidades_de_un_mismo_edificio_pueden_compartir_texto():
    """Cuatro unidades con el mismo texto en un catálogo de veinte no son la
    mitad: el texto se conserva."""
    compartido = "Departamento en desarrollo, entrega 2027, amenities completos"
    props = [_prop(compartido) for _ in range(4)]
    props += [_prop(f"Propiedad distinta numero {i} con su propia descripcion")
              for i in range(16)]
    assert descartar_descripciones_compartidas(props) == 0
    assert props[0].descripcion == compartido


def test_con_pocas_fichas_no_se_juzga_la_frecuencia():
    props = [_prop("Texto igual en las tres fichas de una agencia chica") for _ in range(3)]
    assert descartar_descripciones_compartidas(props) == 0
