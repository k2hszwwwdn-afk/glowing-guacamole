import unittest

from translations import LANGUAGE_NAMES, translate


class TranslationTests(unittest.TestCase):
    def test_supported_languages_have_event_and_photo_labels(self):
        self.assertEqual(set(LANGUAGE_NAMES), {"en", "zh", "es", "ar"})
        for language in LANGUAGE_NAMES:
            with self.subTest(language=language):
                self.assertTrue(translate(language, "event_details"))
                self.assertTrue(translate(language, "satellite_view"))
                self.assertTrue(translate(language, "photo_disclaimer"))
                self.assertTrue(translate(language, "map_controls"))
                self.assertTrue(translate(language, "pulse_legend"))
                self.assertTrue(translate(language, "tsunami_legend"))
                self.assertTrue(translate(language, "tsunami_flag_detail"))
                self.assertTrue(translate(language, "buy_me_coffee"))

    def test_named_values_are_formatted_in_each_language(self):
        for language in LANGUAGE_NAMES:
            with self.subTest(language=language):
                self.assertEqual(
                    translate(language, "magnitude_label", magnitude=4.2),
                    "M 4.2",
                )
                self.assertIn("3", translate(language, "plotted", count=3))

    def test_unknown_language_falls_back_to_english(self):
        self.assertEqual(translate("fr", "language"), "Language")


if __name__ == "__main__":
    unittest.main()
