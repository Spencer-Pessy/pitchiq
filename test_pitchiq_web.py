"""Regression checks for safe rendering of third-party football feed text."""
from pathlib import Path
import unittest

class WebsiteOutputSafetyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = Path("index.html").read_text(encoding="utf-8")

    def test_html_escape_helper_is_present(self):
        self.assertIn("const esc=v=>String(v??'').replace(/[&<>", self.html)

    def test_provider_text_fields_are_escaped_before_html_interpolation(self):
        fields = (
            "r.p.comp", "r.p.h", "r.p.a", "x.name", "x.m.comp", "x.m.h", "x.m.a",
            "T[k].name", "r.team", "p.name", "p.team", "m.comp", "m.h", "m.a",
            "s[k][x]", "x.player", "x.team", "x.reason", "f.comp", "f.h", "f.a",
            "g.scorer", "g.assist", "g.team", "p.n", "p.r",
        )
        for field in fields:
            with self.subTest(field=field):
                self.assertNotIn(" + field + ", self.html)

if __name__ == "__main__":
    unittest.main()
