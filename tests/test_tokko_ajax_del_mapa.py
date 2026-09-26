"""`global propiedades`: el primer $.ajax literal era el globo del mapa."""
from __future__ import annotations

from connectors.tokko import query_de_paginacion

HTML = """<script>
function abrir(id){ $.ajax('/infowindow_premium/' + id).done(function(r){}); }
function get_next_page(){
  var jqxhr = $.ajax(tfwListingUrl('', {o: '2,2', p: current_page}))
}
</script>"""


def test_la_paginacion_no_es_el_globo_del_mapa():
    q = query_de_paginacion(HTML)
    assert q is not None and q.endswith("p=") and "infowindow" not in q


def test_un_literal_de_paginacion_sigue_ganando():
    html = "<script>$.ajax('/Propiedades?o=2,2&p=' + current_page)</script>"
    assert query_de_paginacion(html) == "/Propiedades?o=2,2&p="
