"""Regression checks for safe rendering of third-party football feed text."""
from pathlib import Path
import unittest


class WebsiteOutputSafetyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = Path("index.html").read_text(encoding="utf-8")

    def test_html_escape_helper_covers_html_metacharacters(self):
        self.assertIn("const esc=v=>String(v??'').replace(/[&<>", self.html)
        for replacement in ("&amp;", "&lt;", "&gt;", "&#39;"):
            with self.subTest(replacement=replacement):
                self.assertIn(replacement, self.html)

    def test_player_comparison_sort_is_null_safe_and_scope_is_clear(self):
        self.assertIn("playerSort='goals'", self.html)
        self.assertIn("playerSort==='assists'?'a':playerSort==='contributions'?'gapm':'g'", self.html)
        self.assertIn("if(av==null)return 1;if(bv==null)return -1", self.html)
        self.assertIn('complete league-wide assists ranking', self.html)
        self.assertIn("ps.onchange=e=>{playerSort=e.target.value;list()}", self.html)

    def test_provider_text_is_escaped_before_html_interpolation(self):
        fields = (
            "r.p.comp", "r.p.h", "r.p.a", "x.name", "x.m.comp", "x.m.h", "x.m.a",
            "T[k].name", "r.team", "p.name", "p.team", "m.comp", "m.h", "m.a",
            "s[k][x]", "f.comp", "f.h", "f.a", "g.scorer", "g.assist", "g.team",
            "p.n", "p.r",
        )
        for field in fields:
            with self.subTest(field=field):
                self.assertIn("esc(" + field, self.html)
                self.assertNotIn("${" + field + "}", self.html)


if __name__ == "__main__":
    unittest.main()
