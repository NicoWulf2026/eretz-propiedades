from types import SimpleNamespace

from scripts.image_quality import normalize_property_images
from scripts.run_rollout import descartar_imagenes_compartidas


def test_whatsapp_export_is_a_photo_but_widget_is_not():
    photo = 'https://agency.test/uploads/WhatsApp%20Image%202026-09-18.jpeg'
    widget = 'https://agency.test/assets/whatsapp.png'
    real, discarded = normalize_property_images([photo, widget])
    assert real == [photo]
    assert discarded == [widget]


def test_shared_render_is_preserved_with_review_evidence():
    render = 'https://agency.test/building/render.jpg'
    objects = [SimpleNamespace(imagenes=[render], extra={}) for _ in range(12)]
    assert descartar_imagenes_compartidas(objects) == 0
    assert all(p.imagenes == [render] for p in objects)
    assert all(p.extra['imagenes_repetidas_revision'] == [render] for p in objects)
