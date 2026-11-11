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

    def test_competition_breakdown_includes_home_and_away_expected_goals_error(self):
        self.assertIn("homeError=0,awayError=0,homeBias=0,awayBias=0,goalN=0", self.html)
        self.assertIn("homeMae:goalN?homeError/goalN:null", self.html)
        self.assertIn("awayMae:goalN?awayError/goalN:null", self.html)
        self.assertIn("homeBias:goalN?homeBias/goalN:null", self.html)
        self.assertIn("awayBias:goalN?awayBias/goalN:null", self.html)
        self.assertIn("xG bias H/A", self.html)
        self.assertIn("xG MAE H/A", self.html)
        self.assertIn("not a league ranking or proof of model strength", self.html)

    def test_retired_api_football_injury_panel_is_not_rendered(self):
        self.assertNotIn("From API-Football", self.html)
        self.assertNotIn("if(f.inj)", self.html)

    def test_provider_text_is_escaped_before_html_interpolation(self):
        fields = (
            "r.p.comp", "r.p.h", "r.p.a", "x.name", "x.m.comp", "x.m.h", "x.m.a",
            "T[k].name", "r.team", "p.name", "p.team", "m.comp", "m.h", "m.a",
            "s[k][x]", "f.comp", "f.h", "f.a", "g.scorer", "g.assist", "g.team",
            "p.n",
        )
        for field in fields:
            with self.subTest(field=field):
                self.assertIn("esc(" + field, self.html)
                self.assertNotIn("${" + field + "}", self.html)


if __name__ == "__main__":
    unittest.main()


class InputSignalDiagnosticsWebTests(unittest.TestCase):
    def test_record_view_discloses_saved_input_diagnostics_and_small_samples(self):
        source = Path("index.html").read_text(encoding="utf-8")
        self.assertIn("Input-signal diagnostics", source)
        self.assertIn("const snapRows=rows.filter(r=>r.p.inputs?.schema===1)", source)
        self.assertIn("const diagSummary=(name,items)=>", source)
        self.assertIn("The existing ledger predates snapshot capture", source)
        self.assertIn("new forecasts will populate these checks as their matches finish", source)
        self.assertIn("Groups below 10 matches are monitoring-only", source)
        self.assertIn("Venue sample (weaker side)", source)
        self.assertIn("Recent form edge", source)
        self.assertIn("s.length>=1&&s.length<=5", source)


class CalibrationDisplayTests(unittest.TestCase):
    def test_record_view_shows_weighted_calibration_error_and_caution(self):
        source = Path("index.html").read_text(encoding="utf-8")
        self.assertIn("const ece=n?confBins.reduce", source)
        self.assertIn("Expected calibration error (lower is better)", source)
        self.assertIn("Largest populated-band gap", source)
        self.assertIn("not a reason to recalibrate on their own", source)
