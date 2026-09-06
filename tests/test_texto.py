"""Normalización de texto: los cuatro casos que ya rompieron una regla."""
from __future__ import annotations

from connectors.texto import (equivalentes, patron, plegar, reparar,
                              sin_acentos)


# --------------------------------------------------- los cuatro históricos

def test_caso_1_banos_con_la_enie_rota():
    """`_es_tabla_estructurada` no veía `Baños` con la ñ rota y leía prosa
    donde había tabla, así que una ficha tabulada contaba sus atributos como
    si fueran texto corrido."""
    assert plegar("BaÃ±os") == "banos"      # mojibake reparable
    assert plegar("Baños") == "banos"
    # El irrecuperable no se inventa, pero se puede afirmar que es el mismo.
    assert equivalentes("Ba�os", "Banos")
    assert equivalentes("Ba�os", "Baños")


def test_caso_2_la_senal_de_fuente_y_su_extraccion_en_alfabetos_distintos():
    """Un campo publicado figuraba como no publicado porque la señal miraba el
    marcado crudo y la extracción el texto ya decodificado."""
    assert plegar("DescripciÃ³n") == plegar("Descripción")
    assert plegar("SUPERFICIE CUBIERTA") == plegar("Superficie Cubierta")


def test_caso_3_remax_no_matcheaba_remax():
    """`Remax Cuore` quedaba fuera de su propia verificación de web porque el
    sitio escribe la marca con barra."""
    assert (plegar("RE/MAX", conservar_espacios=False)
            == plegar("remax", conservar_espacios=False))
    assert (plegar("Remax Cuore", conservar_espacios=False)
            == plegar("RE/MAX  Cuore", conservar_espacios=False))


def test_caso_4_una_mayuscula_no_hace_distinta_a_una_direccion():
    """72 grupos duplicados salieron clasificados como "pueden ser dos
    unidades" por una mayúscula y un baño de diferencia."""
    assert (plegar("Tissera Esquina Los Cedros")
            == plegar("Tissera esquina Los Cedros"))
    assert plegar("Chacra del Norte 1") != plegar("Chacra del Norte 2")


# ------------------------------------------------------- las tres formas

def test_el_original_nunca_se_pierde():
    """`plegar` es una forma de comparación: no muta ni reemplaza al dato."""
    original = "Circunvalación"
    assert plegar(original) == "circunvalacion"
    assert original == "Circunvalación"


def test_la_reparacion_solo_se_aplica_si_mejora():
    """Preferir el texto raro al texto inventado: si no se puede demostrar que
    es mojibake, no se toca."""
    limpio = "Mendiolaza"
    assert reparar(limpio) == limpio
    assert reparar("Ya está bien") == "Ya está bien"
    assert reparar(None) is None
    assert reparar("") == ""


def test_el_caracter_de_reemplazo_no_se_puede_deshacer():
    """La información no está: adivinar qué letra era sería inventarla."""
    roto = "Circunvalaci�n"
    assert reparar(roto) == roto
    # Pero se puede admitir que puede ser cualquiera.
    import re
    assert re.fullmatch(patron(roto), "Circunvalacion")
    assert re.fullmatch(patron(roto), "Circunvalacien")


# ---------------------------------------------------------- lo intocable

def test_una_url_no_se_repara():
    """Arreglarle un carácter a una URL la rompe."""
    u = "https://www.aagaard.com.ar/p/6257229-PH-en-Venta"
    assert reparar(u) == u


def test_un_id_y_un_numero_no_tienen_ortografia():
    for token in ("8156666", "roomix:alfa", "06280040", "USD", "-31.36261"):
        assert reparar(token) == token


def test_los_numeros_sobreviven_al_plegado():
    """Plegar es para comparar texto libre, y no puede alterar una cantidad."""
    assert plegar("USD 140.000") == "usd 140 000"
    assert "140" in plegar("140 m2")


# ------------------------------------------------------------ propiedades

def test_es_determinista():
    """Dos veces el mismo texto da dos veces el mismo resultado."""
    for t in ("BaÃ±os", "Circunvalaci�n", "RE/MAX", "Miramar"):
        assert plegar(t) == plegar(t)
        assert reparar(t) == reparar(t)


def test_plegar_es_idempotente():
    """Plegar lo ya plegado no cambia nada; si cambiara, el orden en que se
    aplican las reglas alteraría el resultado."""
    for t in ("Tissera Esquina Los Cedros", "RE/MAX", "BaÃ±os"):
        una = plegar(t)
        assert plegar(una) == una


def test_sin_acentos_no_usa_una_tabla_escrita_a_mano():
    """Una tabla cubre los que alguien recordó; `unicodedata` los que hay."""
    assert sin_acentos("àèìòù") == "aeiou"
    assert sin_acentos("ÿŷẅ") == "yyw"
    assert sin_acentos("Ñandú") == "Nandu"


def test_no_confunde_dos_textos_distintos():
    """La tolerancia al carácter perdido no puede volverse un comodín."""
    assert not equivalentes("Ba�os", "Cocheras")
    assert not equivalentes("Miramar", "Mar del Plata")
    assert not equivalentes(None, "Miramar")
