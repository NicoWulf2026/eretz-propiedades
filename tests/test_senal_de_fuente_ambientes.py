# -*- coding: utf-8 -*-
"""`MONOambiente` no es un ambiente.

**Rojo a propósito. El arreglo NO está aplicado** y toca `shared/certifier`,
que está bajo freeze. Marcado `xfail(strict=True)`: el día que se aplique, la
suite se rompe y obliga a sacar el marcador.

Esto NO es un arreglo de inventario ni de extracción: es un arreglo de
**medición**. No recupera una sola propiedad ni un solo campo. Lo que corrige
es el número que decide qué arreglar primero, y por eso importa: un ranking
construido sobre `source_provided` inflado manda a trabajar al lugar
equivocado.

LO MEDIDO, 2026-09-15, descargando una ficha de cada agencia:

    blanco propiedades      ambientes  1.089   'ambiente 1' dentro de MONOambiente
    bartolelli maini        ambientes     28   idem, en el menu de navegacion
    cuini propiedades       ambientes     16   idem
                                        -----
                                        1.133  fichas que el ranking contaba de mas

El ranking pasó de 3.992 recuperables a **2.859**.

`espina propiedades` da 100 % de `source_provided` igual que las otras y NO
está en la lista: se descargó su ficha y su `Ambientes 2` es un atributo real
de la propiedad. La proporción sola no alcanza para descartar; hay que mirar.
"""
import re

import pytest

from scripts.agency_certifier import SOURCE_SIGNALS

AMBIENTES = SOURCE_SIGNALS["ambientes"]

# El arreglo propuesto: un limite de palabra ANTES de la etiqueta.
AMBIENTES_CON_LIMITE = re.compile(
    r"(?:\b[1-9]\d?\s*\b(?:ambientes?|amb\.)|\b(?:ambientes?|amb\.)\s*:?\s*[1-9]\d?)",
    re.I)


# --- lo que el patron actual hace bien, y el arreglo no puede romper ------

@pytest.mark.parametrize("texto", [
    "Casa de 3 ambientes",
    "Ambientes: 4",
    "Departamento 2 Ambientes con balcon Banfield",
    "Tipo de operacion En alquiler Ambientes 2 Dormitorios 1",
    "PH 5 amb.",
])
def test_los_ambientes_de_verdad_se_siguen_reconociendo(texto):
    assert AMBIENTES.search(texto), "hoy lo reconoce"
    assert AMBIENTES_CON_LIMITE.search(texto), "y con el arreglo tambien"


# --- el rojo -------------------------------------------------------------

@pytest.mark.xfail(strict=True, reason="defecto abierto en shared/certifier: "
                                       "el patron no exige limite de palabra")
@pytest.mark.parametrize("texto", [
    "Cant. de Domitorios Monoambiente 1 Dorm. 2 Dorm.",
    "Propiedades Departamentos Ver todo Monoambiente 1 dormitorio",
    "Alquileres Departamento Monoambiente 1 dormitorio 2 dormitorios",
])
def test_ROJO_monoambiente_del_menu_no_es_un_atributo(texto):
    """Estos tres textos son menús de filtro, idénticos en todas las fichas
    del sitio. Ninguno dice cuántos ambientes tiene la propiedad."""
    assert not AMBIENTES.search(texto), (
        "el certificador cuenta la fuente como proveedora de `ambientes` "
        "leyendo una opcion de menu")


def test_el_arreglo_propuesto_resuelve_los_tres():
    """El `\\b` separa bien: mata el menú, conserva el atributo."""
    for menu in ("Monoambiente 1 Dorm.", "Monoambiente 1 dormitorio"):
        assert not AMBIENTES_CON_LIMITE.search(menu)
    for real in ("3 ambientes", "Ambientes: 4", "2 Ambientes con balcon"):
        assert AMBIENTES_CON_LIMITE.search(real)


# --- una segunda familia que NO se pudo sostener -----------------------
#
# Durante la auditoria del 2026-09-15 anote que el patron de `ciudad` contaba
# un NOMBRE DE CLASE CSS como si fuera la ciudad, en `ente inmobiliaria`. Salio
# de una salida truncada a 44 caracteres -`class="ere-property-wrap
# single-property-are`- y al ir a comprobar el match COMPLETO el patron no
# matchea eso: exige `ciudad` o `localidad` adentro del atributo. Lo que
# realmente matcheo pudo ser una clase de taxonomia de WordPress como
# `property-localidad-mendoza`, que SI codifica la ciudad y entonces no seria
# un artefacto.
#
# No se pudo terminar de verificar: la ficha ya no responde 200 y esa agencia
# no tiene paquete guardado. Asi que la afirmacion se retira y las 18 fichas
# vuelven al ranking. Queda anotado como pregunta abierta, no como hallazgo.

# --- el radio, escrito para que no se subestime -------------------------

def test_el_radio_de_este_arreglo_esta_documentado():
    """`SOURCE_SIGNALS` vive en `agency_certifier.py`, o sea `shared/certifier`.

    Ese componente entra en la huella del 99 % de las certificaciones: tocarlo
    invalida prácticamente la pasada entera. Para un arreglo que **no recupera
    ni una propiedad ni un campo**, ese precio no se paga solo.

    Va cuando ya haya que recertificar por otra cosa. Mientras tanto, el
    ranking descuenta los TRES casos verificados y lo dice.
    """
    import scripts.agency_certifier as cert
    assert hasattr(cert, "SOURCE_SIGNALS")
    assert "ambientes" in cert.SOURCE_SIGNALS
