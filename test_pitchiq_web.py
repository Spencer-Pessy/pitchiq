"""Regression checks for safe rendering of third-party football feed text."""
from pathlib import Path
import unittest


class DynamicInputAccessibilityTests(unittest.TestCase):
    def test_adjustment_inputs_have_associated_names(self):
        source = Path("index.html").read_text(encoding="utf-8")
        self.assertIn('<label for="${k}-${x}">${l}</label>', source)
        self.assertIn('aria-label="${esc(n)} ${l}"', source)
        self.assertIn('aria-label="Home decimal odds"', source)
        self.assertIn('aria-label="Draw decimal odds"', source)
        self.assertIn('aria-label="Away decimal odds"', source)

    def test_keyboard_focus_and_reduced_motion_are_supported(self):
        source = Path("index.html").read_text(encoding="utf-8")
        self.assertIn('textarea:focus-visible', source)
        self.assertIn('prefers-reduced-motion:reduce', source)
        self.assertIn('#splash{display:none!important}', source)


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




class PublishedResultsPresentationTests(unittest.TestCase):
    def test_results_view_has_published_pick_summary_and_empty_state(self):
        source = Path("index.html").read_text(encoding="utf-8")
        self.assertIn("PITCH IQ PUBLISHED PICK TRACKER", source)
        self.assertIn("Results that match our picks.", source)
        self.assertIn("Settled picks", source)
        self.assertIn("Awaiting full time", source)
        self.assertIn("No published picks to score yet", source)
        self.assertIn("No forecasts are invented to fill the record", source)

    def test_results_accuracy_uses_only_valid_settled_published_picks(self):
        source = Path("index.html").read_text(encoding="utf-8")
        self.assertIn("typeof r.correct==='boolean'", source)
        self.assertIn("const hits=sorted.filter(r=>r.correct===true).length,misses=sorted.length-hits", source)
        self.assertIn("Accuracy uses settled published picks only; pending picks are excluded", source)
        self.assertIn("saved pre-match pick and probability are never replaced", source)


class PicksPresentationTests(unittest.TestCase):
    def test_picks_screen_explains_shortlist_and_market_freshness(self):
        source = Path("index.html").read_text(encoding="utf-8")
        self.assertIn("PITCH IQ MODEL WATCHLIST", source)
        self.assertIn("Next 36 hours", source)
        self.assertIn("eligible matches", source)
        self.assertIn("Market snapshot fresh", source)
        self.assertIn("Market snapshot paused", source)
        self.assertIn("Confidence is not certainty", source)

    def test_pick_cards_show_probability_without_changing_model_selection(self):
        source = Path("index.html").read_text(encoding="utf-8")
        self.assertIn('class="card pick-card"', source)
        self.assertIn('class="pick-meter" aria-label="Leading outcome probability"', source)
        self.assertIn("Math.max(0,Math.min(100,Math.round(x.c*100)))", source)
        self.assertIn("sort((a,b)=>pk=='gap'", source)
        self.assertIn("No eligible fixtures right now", source)


class MatchPreviewTests(unittest.TestCase):
    def test_match_detail_has_dynamic_preview_and_discloses_missing_context(self):
        source = Path("index.html").read_text(encoding="utf-8")
        self.assertIn("const outcomeNames=[f.h+' win','Draw',f.a+' win']", source)
        self.assertIn("<h2>Match preview</h2>", source)
        self.assertIn("Form comparison", source)
        self.assertIn("Team strength", source)
        self.assertIn("Expected goal balance", source)
        self.assertIn("confirmed lineups, tactics, weather or late team news", source)
        self.assertIn("${preview}<div class=\"stats\">", source)


class HomepageOverviewTests(unittest.TestCase):
    def test_upcoming_tab_has_live_dataset_overview_panel(self):
        source = Path("index.html").read_text(encoding="utf-8")
        self.assertIn("function overviewHtml()", source)
        self.assertIn("FREE FOOTBALL INTELLIGENCE", source)
        self.assertIn("Upcoming fixtures", source)
        self.assertIn("Live matches", source)
        self.assertIn("Competitions covered", source)
        self.assertIn("Data refreshed", source)
        self.assertIn("(tab==='up'?overviewHtml():'')", source)
        self.assertIn("$('#app').innerHTML=head()+tabsHtml()+(tab=='up'?overviewHtml():'')+", source)
        self.assertIn("if(tab=='up'&&ms.length)html+='<div class=\"fixture-grid\">';", source)
        self.assertIn(".fixture-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr))", source)
        self.assertIn(".fixture-grid{grid-template-columns:1fr", source)



class OddsFreshnessWebTests(unittest.TestCase):
    def test_market_value_comparison_requires_fresh_snapshot(self):
        source = Path("index.html").read_text(encoding="utf-8")
        self.assertIn("const oddsFresh=Number.isFinite(oh)&&oh>=0&&oh<=36", source)
        self.assertIn("if(oddsFresh&&Array.isArray(m.odds)", source)
        self.assertIn("Market snapshot is stale", source)

    def test_invalid_market_prices_are_not_used_for_value_comparison(self):
        source = Path("index.html").read_text(encoding="utf-8")
        self.assertIn("Number.isFinite(Number(x))&&Number(x)>1&&Number(x)<1000", source)

class PublishedPicksResultsWebTests(unittest.TestCase):
    def test_results_tab_shows_only_published_picks_and_keeps_pending_separate(self):
        source = Path("index.html").read_text(encoding="utf-8")
        self.assertIn("fetch('daily/published_picks.json?'", source)
        self.assertIn("function publishedResultsHtml()", source)
        self.assertIn("Q?.pending", source)
        self.assertIn("Q?.results", source)
        self.assertIn("Awaiting full time", source)
        self.assertIn("Settled published picks", source)
        self.assertIn("Pending picks are not counted in the accuracy rate", source)
        self.assertIn("original fixture ID", source)

    def test_social_preview_metadata_and_small_screen_layout_exist(self):
        source = Path("index.html").read_text(encoding="utf-8")
        self.assertIn('property="og:title"', source)
        self.assertIn('property="og:description"', source)
        self.assertIn('property="og:image"', source)
        self.assertIn('name="twitter:card"', source)
        self.assertIn("@media(max-width:480px)", source)
        self.assertIn(".cols,.stats{grid-template-columns:1fr}", source)


class InternationalStatusPresentationTests(unittest.TestCase):
    def test_international_view_groups_live_and_non_playable_statuses_safely(self):
        source = Path("index.html").read_text(encoding="utf-8")
        self.assertIn("const liveStatuses=new Set(['1H','HT','2H','ET','P','LIVE'])", source)
        self.assertIn("!['PST','CANC','SUSP','ABD'].includes(f.status)", source)
        self.assertIn("ABD:'ABANDONED',LIVE:'LIVE'", source)


if __name__ == "__main__":
    unittest.main()


class InputSignalDiagnosticsWebTests(unittest.TestCase):
    def test_record_view_discloses_saved_input_diagnostics_and_small_samples(self):
        source = Path("index.html").read_text(encoding="utf-8")
        self.assertIn("Input-signal diagnostics", source)
        self.assertIn("const snapRows=rows.filter(r=>r.p.inputs?.schema===2)", source)
        self.assertIn("Forward-only controlled model ablation", source)
        self.assertIn("without_elo_or_form", source)
        self.assertIn("original saved calibration", source)
        self.assertIn("const diagSummary=(name,items)=>", source)
        self.assertIn("New forecasts will populate these checks after their matches finish", source)
        self.assertIn("Only forecasts with complete saved inputs and calibration are included", source)
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


class BinaryMarketCalibrationWebTests(unittest.TestCase):
    def test_record_view_scores_goal_market_probabilities(self):
        source = Path("index.html").read_text(encoding="utf-8")
        self.assertIn("const binaryMetric=key=>", source)
        self.assertIn("Over 2.5 · Brier / ECE", source)
        self.assertIn("BTTS · Brier / ECE", source)


class OutcomeClassCalibrationWebTests(unittest.TestCase):
    def test_record_view_compares_home_draw_away_probabilities_separately(self):
        source = Path("index.html").read_text(encoding="utf-8")
        self.assertIn("const outcomeClassRows=", source)
        self.assertIn("Home / draw / away calibration", source)
        self.assertIn("Mean probability", source)
        self.assertIn("Observed rate", source)
        self.assertIn("one outcome as a yes/no event", source)


class BaselineComparisonWebTests(unittest.TestCase):
    def test_record_view_discloses_rolling_prior_and_fair_bookmaker_comparison(self):
        source = Path("index.html").read_text(encoding="utf-8")
        self.assertIn("Baseline comparison", source)
        self.assertIn("Competition-aware rolling prior", source)
        self.assertIn("const rollingPrior=scoreSummary(priorRows),competitionRollingPrior=scoreSummary(competitionPriorRows)", source)
        self.assertIn("five prior-match equivalents", source)
        self.assertIn("updates only after earlier kickoffs", source)
        self.assertIn("matches at the same kickoff share the same prior", source)
        self.assertIn("overround removed", source)
        self.assertIn("PitchIQ and bookmaker rows use the exact same odds-available matches", source)
        self.assertIn("PitchIQ minus bookmaker · Brier", source)
        self.assertIn("Bookmaker comparison by competition", source)
        self.assertIn("small samples (especially below 20)", source)

class AccuracyConfidenceIntervalWebTests(unittest.TestCase):
    def test_record_view_shows_wilson_interval_for_accuracy(self):
        source = Path("index.html").read_text(encoding="utf-8")
        self.assertIn("const wilson=(successes,total)=>", source)
        self.assertIn("95% Wilson interval:", source)

class AblationUncertaintyWebTests(unittest.TestCase):
    def test_record_view_displays_paired_bootstrap_interval(self):
        source = Path("index.html").read_text(encoding="utf-8")
        self.assertIn("Paired 95% CI", source)
        self.assertIn("brier_delta_ci_95", source)
        self.assertIn("intervals crossing zero do not show a clear direction", source)


class ExactScorelineDiagnosticsWebTests(unittest.TestCase):
    def test_record_view_replays_normalised_dixon_coles_score_grid(self):
        source = Path("index.html").read_text(encoding="utf-8")
        self.assertIn("const scorelineRows=[];let scorelineExcluded=0", source)
        self.assertIn("for(let i=0;i<8;i++)for(let j=0;j<8;j++)", source)
        self.assertIn("pois(lh,i)*pois(la,j)*tau(i,j)", source)
        self.assertIn("actualProbability/total", source)
        self.assertIn("Exact-scoreline evaluation", source)
        self.assertIn("Exact-score negative log likelihood", source)
        self.assertIn("Most-likely exact score hit rate", source)
        self.assertIn("outside the grid are excluded", source)
        self.assertIn("rounded to four decimals", source)
        self.assertIn("lower negative log likelihood is better", source)



class ExactScorelineCalibrationWebTests(unittest.TestCase):
    def test_record_view_checks_top_score_confidence_and_top_three_coverage(self):
        source = Path("index.html").read_text(encoding="utf-8")
        self.assertIn("top1Probability:top1.p/total", source)
        self.assertIn("top3Probability:top3Mass/total", source)
        self.assertIn("top1Hit,top3Probability:top3Mass/total,top3Hit", source)
        self.assertIn("Top-score confidence calibration", source)
        self.assertIn("Top-score probability", source)
        self.assertIn("Actual hit rate", source)
        self.assertIn("Top-three probability mass / actual coverage", source)
        self.assertIn("Sparse bins are descriptive only", source)

class ExpectedGoalsCalibrationWebTests(unittest.TestCase):
    def test_record_view_displays_home_and_away_expected_goals_bands(self):
        source = Path("index.html").read_text(encoding="utf-8")
        self.assertIn("Expected-goals calibration", source)
        self.assertIn('xgCalibration("lh",0)', source)
        self.assertIn('xgCalibration("la",1)', source)
        self.assertIn("Mean predicted", source)
        self.assertIn("Mean actual", source)
        self.assertIn("monitoring-only", source)
        self.assertIn("no automatic model correction is applied", source)


class ScorelineBaselineComparisonWebTests(unittest.TestCase):
    def test_record_view_displays_paired_dixon_coles_baseline(self):
        source = Path("index.html").read_text(encoding="utf-8")
        self.assertIn("Dixon–Coles vs independent Poisson", source)
        self.assertIn("mean_delta_dc_minus_independent", source)
        self.assertIn("delta_ci_95", source)
        self.assertIn("Negative NLL difference favours Dixon–Coles", source)
        self.assertIn("D?.scoreline_baseline", source)


class ForwardResearchPendingStateTests(unittest.TestCase):
    def test_record_view_explains_when_forward_research_has_no_scored_sample(self):
        source = Path("index.html").read_text(encoding="utf-8")
        self.assertIn("No completed research sample has been scored yet.", source)
        self.assertIn("These forward-only forecasts are waiting for full-time results", source)
        self.assertIn("Research scores update as saved forecasts reach full time.", source)


class InternationalGenderPresentationTests(unittest.TestCase):
    def test_international_cards_label_mens_and_womens_streams(self):
        source = Path("index.html").read_text(encoding="utf-8")
        self.assertIn("f.gender==='women'?'Women':f.gender==='men'?'Men':''", source)
        self.assertIn("const meta=[gender,f.comp,f.country,kickoff]", source)


class InternationalFixtureGroupingTests(unittest.TestCase):
    def test_international_cards_show_local_kickoff_and_source(self):
        source = Path("index.html").read_text(encoding="utf-8")
        self.assertIn("date.toLocaleString([],{weekday:'short',day:'numeric',month:'short',hour:'2-digit',minute:'2-digit'})", source)
        self.assertIn("f.source||'public fixture feed'", source)
        self.assertIn("Kickoff times use your device local time.", source)

    def test_international_view_separates_upcoming_live_and_completed_matches(self):
        source = Path("index.html").read_text(encoding="utf-8")
        self.assertIn("section('Live now',liveSorted", source)
        self.assertIn("section('Upcoming fixtures',upcomingSorted", source)
        self.assertIn("section('Completed results',completedSorted.slice(0,12)", source)
        self.assertIn("No upcoming international fixtures are listed in the current snapshot.", source)
        self.assertIn("Showing the 12 most recent completed matches.", source)
        self.assertIn("I.scope||'Coverage may vary by competition and source.'", source)


class InternationalFixtureFilterTests(unittest.TestCase):
    def test_international_view_exposes_gender_competition_and_search_filters(self):
        source = Path("index.html").read_text(encoding="utf-8")
        self.assertIn('id="intlGender"', source)
        self.assertIn('id="intlCompetition"', source)
        self.assertIn('id="intlSearch"', source)
        self.assertIn("Team category", source)
        self.assertIn("Search teams, competition or country", source)

    def test_international_filter_state_is_applied_to_fixture_list(self):
        source = Path("index.html").read_text(encoding="utf-8")
        self.assertIn("intlGender='all',intlCompetition='all',intlQuery=''", source)
        self.assertIn("const allFixtures=(I.fixtures||[])", source)
        self.assertIn("intlGender==='all'||gender===intlGender", source)
        self.assertIn("intlCompetition==='all'||String(f.comp||'Unknown competition')===intlCompetition", source)
        self.assertIn("searchable.includes(query)", source)
        self.assertIn("Showing '+valid.length+' of '+allFixtures.length+' fixtures", source)

    def test_international_search_keeps_focus_and_cursor_while_typing(self):
        source = Path("index.html").read_text(encoding="utf-8")
        self.assertIn("const start=e.target.selectionStart,end=e.target.selectionEnd", source)
        self.assertIn("next.focus();next.setSelectionRange(start,end)", source)

    def test_international_tab_still_omits_league_table(self):
        source = Path("index.html").read_text(encoding="utf-8")
        self.assertIn("if(tab=='intl')return international()", source)
        self.assertIn("tab==='intl'?'':(' · standings '", source)
        self.assertNotIn("section('League table'", source)
