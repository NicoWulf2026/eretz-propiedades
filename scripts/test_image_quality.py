from __future__ import annotations

import unittest

from scripts.image_quality import is_branding_or_logo_image, normalize_property_images


PAGLIARO_LOGO = "https://www.pagliaropropiedades.com.ar/imgs/inmobiliaria-pagliaro-tandil.png"
SV_LOGO = "https://www.svestudioinmobiliario.com.ar/imgs/inmobiliaria-sv-tandil.png"
REAL_PHOTO = "https://www.casasdehoy.com.ar/fotos_nuevas/media_174412382311e5067f72ad4843a4fe4a904eed449fjpg.jpeg"
SECOND_REAL_PHOTO = "https://cdn.example.com/uploads/property-living-room.jpg"


class ImageQualityTest(unittest.TestCase):
    def test_pagliaro_logo_is_filtered(self) -> None:
        self.assertTrue(is_branding_or_logo_image(PAGLIARO_LOGO))

    def test_sv_logo_is_filtered(self) -> None:
        self.assertTrue(is_branding_or_logo_image(SV_LOGO))

    def test_real_photo_is_preserved(self) -> None:
        images, discarded = normalize_property_images([REAL_PHOTO])

        self.assertEqual(images, [REAL_PHOTO])
        self.assertEqual(discarded, [])

    def test_logo_plus_photos_returns_photos_first(self) -> None:
        images, discarded = normalize_property_images([PAGLIARO_LOGO, REAL_PHOTO, SECOND_REAL_PHOTO])

        self.assertEqual(images, [REAL_PHOTO, SECOND_REAL_PHOTO])
        self.assertEqual(discarded, [PAGLIARO_LOGO])

    def test_only_logos_returns_no_usable_real_image(self) -> None:
        images, discarded = normalize_property_images([PAGLIARO_LOGO, SV_LOGO])

        self.assertEqual(images, [])
        self.assertEqual(discarded, [PAGLIARO_LOGO, SV_LOGO])

    def test_normal_url_is_not_filtered(self) -> None:
        image = "https://media.example.com/properties/front-house.webp"
        images, discarded = normalize_property_images([image])

        self.assertEqual(images, [image])
        self.assertEqual(discarded, [])


if __name__ == "__main__":
    unittest.main()
