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


class BrowserForecastInputTests(unittest.TestCase):
    def test_missing_absence_counts_default_to_zero_in_browser_model(self):
        source = Path("index.html").read_text(encoding="utf-8")
        self.assertIn("(1-.04*(Number(H.out)||0))", source)
        self.assertIn("(1-.04*(Number(A.out)||0))", source)


class FinishedMatchForecastIntegrityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = Path("index.html").read_text(encoding="utf-8")

    def test_finished_fixture_cards_use_only_archived_pre_match_forecasts(self):
        self.assertIn("const saved=tab==='done'?P[String(m.id)]:null;", self.html)
        self.assertIn("tab==='done'?(saved&&saved.p?savedForecast(saved.p):null):model(m.s)", self.html)
        self.assertIn("No archived pre-match forecast", self.html)

    def test_finished_match_detail_never_reconstructs_a_forecast(self):
        self.assertIn("f.status==='FINISHED'?P[String(f.id)]:null", self.html)
        self.assertIn("No forecast was archived before kickoff for this fixture", self.html)
        self.assertIn("const r=archived?savedForecast(archived.p):model(s)", self.html)
        self.assertIn("if(f.status==='FINISHED'){const editor=$('#res').nextElementSibling;if(editor)editor.remove();res();return}", self.html)

    def test_saved_scoreline_grid_uses_archived_expected_goal_rates(self):
        self.assertIn("function savedForecast(p)", self.html)
        self.assertIn("const lh=Number(p&&p.lh),la=Number(p&&p.la)", self.html)
        self.assertIn("top:all.slice(0,5).map(([h,a,value])=>[h,a,value/total])", self.html)


class InternationalMatchCentreTests(unittest.TestCase):
    def test_international_tab_shows_filtered_live_upcoming_and_completed_counts(self):
        source = Path("index.html").read_text(encoding="utf-8")
        self.assertIn('aria-label="International fixture summary"', source)
        self.assertIn("INTERNATIONAL MATCH CENTRE", source)
        self.assertIn("live.length+'</b><span>Live now", source)
        self.assertIn("upcoming.length+'</b><span>Upcoming", source)
        self.assertIn("completed.length+'</b><span>Completed", source)
        self.assertIn("counts reflect the filters selected below", source.lower())
        self.assertIn("const inactiveStatuses=new Set(['PST','CANC','SUSP','ABD'])", source)
        self.assertIn("!inactiveStatuses.has(f.status)&&Array.isArray(f.score)", source)
        self.assertIn("!inactiveStatuses.has(f.status)&&new Date(f.utc).getTime()>now", source)
        self.assertIn("tabsHtml()+filterHtml+summaryHtml+coverageHtml", source)
    def test_international_fixture_sections_use_responsive_two_column_grid(self):
        source = Path("index.html").read_text(encoding="utf-8")
        self.assertIn("items.length?'<div class=\"fixture-grid\">'+items.map(card).join('')+'</div>'", source)
        self.assertIn(".fixture-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr))", source)
        self.assertIn(".fixture-grid{grid-template-columns:1fr", source)


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




class NewsAndSocialContactTests(unittest.TestCase):
    def test_news_tab_exposes_all_confirmed_pitchiq_social_contacts(self):
        source = Path("index.html").read_text(encoding="utf-8")
        for value in (
            "FOLLOW PITCH IQ", "Join the conversation",
            "https://www.tiktok.com/@pitch.iq04",
            "https://www.instagram.com/pitch.iq04/",
            "https://x.com/PitchIQ04",
            "https://t.me/pitchiq_picks",
            "https://t.me/PitchIQPicks_bot",
            "Facebook", "Ray Spencer", "profile link to be confirmed",
        ):
            with self.subTest(value=value):
                self.assertIn(value, source)

    def test_social_contact_links_open_safely_in_new_tabs(self):
        source = Path("index.html").read_text(encoding="utf-8")
        self.assertIn('class="social-grid" aria-label="PitchIQ social media contacts"', source)
        self.assertIn('target="_blank" rel="noopener noreferrer"><b>TikTok</b>', source)
        self.assertIn('target="_blank" rel="noopener noreferrer"><b>Instagram</b>', source)
        self.assertIn('target="_blank" rel="noopener noreferrer"><b>X</b>', source)


class NestedFixtureSearchTests(unittest.TestCase):
    def test_team_search_filters_nested_fixture_grid_cards_and_day_headings(self):
        source = Path("index.html").read_text(encoding="utf-8")
        self.assertIn("document.querySelectorAll('button.card[data-id], .results-card').forEach(card=>", source)
        self.assertIn(".results-card", source)
        self.assertIn("document.querySelectorAll('.day').forEach(day=>", source)
        self.assertIn("let sibling=day.nextElementSibling,any=false", source)
        self.assertIn("sibling.matches('button.card[data-id]')", source)
        self.assertNotIn("[...$('#app').children].forEach(el=>", source)


class MobileTouchTargetTests(unittest.TestCase):
    def test_mobile_interactive_controls_have_minimum_44px_touch_targets(self):
        source = Path("index.html").read_text(encoding="utf-8")
        self.assertIn("@media(max-width:600px){button,input,select,textarea{min-height:44px}}", source)


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



class HeadToHeadPresentationTests(unittest.TestCase):
    def test_club_and_international_details_render_h2h_sections(self):
        source = Path("index.html").read_text(encoding="utf-8")
        self.assertIn("function h2hPanel(home,away,summary)", source)
        self.assertIn("function internationalH2H(f)", source)
        self.assertIn("${h2hPanel(f.h,f.a,f.h2h)}", source)
        self.assertIn("h2hPanel(f.h,f.a,internationalH2H(f))", source)
        self.assertIn("Only completed meetings before this fixture’s kickoff are counted", source)

    def test_h2h_international_matches_are_gender_scoped_and_pre_kickoff(self):
        source = Path("index.html").read_text(encoding="utf-8")
        self.assertIn("t<cutoff", source)
        self.assertIn("m.gender===f.gender", source)
        self.assertIn("['FT','AET','PEN'].includes(m.status)", source)


class OddsFreshnessWebTests(unittest.TestCase):
    def test_market_value_comparison_requires_fresh_snapshot(self):
        source = Path("index.html").read_text(encoding="utf-8")
        self.assertIn("oddsFresh=marketSnapshotFresh(D.odds_updated)", source)
        self.assertEqual(source.count("oddsFresh=marketSnapshotFresh(D.odds_updated)"), 2)
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
        self.assertIn("const inactiveStatuses=new Set(['PST','CANC','SUSP','ABD'])", source)
        self.assertIn("!inactiveStatuses.has(f.status)&&Array.isArray(f.score)", source)
        self.assertIn("!inactiveStatuses.has(f.status)&&new Date(f.utc).getTime()>now", source)
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


class FeedHealthLabelTests(unittest.TestCase):
    def test_world_cup_euro_archive_is_not_mislabeled_as_all_international_fixtures(self):
        source = Path("index.html").read_text(encoding="utf-8")
        self.assertIn("World Cup/EURO archive", source)
        self.assertNotIn("fixtures · international '", source)


class ServiceWorkerLiveDataTests(unittest.TestCase):
    def test_published_pick_ledger_uses_network_first_live_data_cache(self):
        source = Path("sw.js").read_text(encoding="utf-8")
        self.assertIn("pitchiq-cache-v9", source)
        self.assertIn("url.pathname.endsWith('/daily/published_picks.json')", source)
        self.assertIn("fetch(request)", source)
        self.assertIn("{version: 1, pending: [], results: [], sent_ids: []}", source)

    def test_service_worker_precaches_every_manifest_install_icon(self):
        import json
        manifest = json.loads(Path("manifest.json").read_text(encoding="utf-8"))
        source = Path("sw.js").read_text(encoding="utf-8")
        core_line = next(line for line in source.splitlines() if line.startswith("const CORE = "))
        for icon in manifest["icons"]:
            with self.subTest(icon=icon["src"]):
                self.assertIn("'./" + icon["src"] + "'", core_line)
                self.assertTrue(Path(icon["src"]).is_file())


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

    def test_international_tab_discloses_source_and_gender_coverage(self):
        source = Path("index.html").read_text(encoding="utf-8")
        self.assertIn("SNAPSHOT COVERAGE", source)
        self.assertIn("genderCounts.men", source)
        self.assertIn("genderCounts.women", source)
        self.assertIn("feed.espn_leagues_checked", source)
        self.assertIn("successful response can contain zero fixtures", source)
        self.assertIn("ESPN scoreboard requests:", source)
        self.assertIn("leagues responded at least once", source)
        self.assertIn("not a guarantee of competition coverage", source)

    def test_international_feed_warns_when_snapshot_is_older_than_12_hours(self):
        source = Path("index.html").read_text(encoding="utf-8")
        self.assertIn("const stale=age===null||age>12", source)
        self.assertIn("International feed may be stale", source)
        self.assertIn("last successful snapshot is '+age+' hours old", source)
        self.assertIn("ageMs>=0?Math.round(ageMs/36e5):null", source)
        self.assertIn("International feed freshness is unavailable", source)

    def test_international_tab_still_omits_league_table(self):
        source = Path("index.html").read_text(encoding="utf-8")
        self.assertIn("if(tab=='intl')return international()", source)
        self.assertIn("tab==='intl'?'':(' · standings '", source)
        self.assertNotIn("section('League table'", source)

class NewsTabRegressionTests(unittest.TestCase):
    def test_news_tab_is_reachable_and_keeps_news_separate_from_forecasts(self):
        source = Path("index.html").read_text(encoding="utf-8")
        self.assertIn("['news','News']", source)
        self.assertIn("if(tab=='news')return news();", source)
        self.assertIn("PITCH IQ NEWSROOM", source)
        self.assertIn("Football stories, with sources attached.", source)
        self.assertIn("https://t.me/pitchiq_picks", source)
        self.assertIn("https://t.me/PitchIQPicks_bot", source)
        self.assertIn("News is not a prediction", source)
        self.assertIn("does not manufacture transfer rumours", source)

    def test_news_tab_external_links_open_safely(self):
        source = Path("index.html").read_text(encoding="utf-8")
        self.assertIn('href="https://t.me/pitchiq_picks" target="_blank" rel="noopener noreferrer"', source)
        self.assertIn('href="https://t.me/PitchIQPicks_bot" target="_blank" rel="noopener noreferrer"', source)

class ServiceWorkerDataFallbackTests(unittest.TestCase):
    def test_http_errors_fall_back_to_last_known_good_data_snapshot(self):
        source = Path("sw.js").read_text(encoding="utf-8")
        self.assertIn("const cached = await caches.match(key);", source)
        self.assertIn("return cached || response;", source)
        self.assertIn("if (response.ok)", source)
        self.assertIn("await cache.put(key, response.clone());", source)

    def test_offline_data_cache_ignores_cache_busting_query_parameters(self):
        source = Path("sw.js").read_text(encoding="utf-8")
        self.assertIn("const key = new Request(url.origin + url.pathname);", source)
        self.assertIn("fetch(request)", source)
        self.assertIn("The page reads the snapshot's own updated timestamp", source)

class InternationalFixtureDetailTests(unittest.TestCase):
    def test_international_fixture_cards_open_a_fixture_only_detail_view(self):
        source = Path("index.html").read_text(encoding="utf-8")
        self.assertIn("function internationalDetail()", source)
        self.assertIn("if(tab==='intl'){internationalDetail();return}detail()", source)
        self.assertIn("INTERNATIONAL MATCH DETAIL", source)
        self.assertIn("Pitch IQ does not currently publish model forecasts for international fixtures", source)
        self.assertIn("$('#bk').onclick=()=>{tab='intl';list()}", source)

class MainFeedFreshnessEdgeCaseTests(unittest.TestCase):
    def test_missing_invalid_and_future_timestamps_are_not_shown_as_fresh(self):
        source = Path("index.html").read_text(encoding="utf-8")
        self.assertIn("const updatedAt=Date.parse(D.updated||'')", source)
        self.assertIn("ageMs>=0?Math.floor(ageMs/60000):null", source)
        self.assertIn("stale=mins===null||ageMs>90*60000", source)
        self.assertIn("Freshness unavailable", source)
        self.assertIn("freshness unavailable", source)

class InternationalFreshnessEdgeCaseTests(unittest.TestCase):
    def test_missing_invalid_and_future_timestamps_trigger_warning(self):
        source = Path("index.html").read_text(encoding="utf-8")
        self.assertIn("const updatedAt=Date.parse(I.updated||''),ageMs=now-updatedAt", source)
        self.assertIn("Number.isFinite(updatedAt)&&ageMs>=0", source)
        self.assertIn("const stale=age===null||age>12", source)
        self.assertIn("missing, invalid or in the future", source)

class OddsDisplayDisclosureTests(unittest.TestCase):
    def test_match_detail_discloses_saved_odds_snapshot_time_and_non_live_status(self):
        source = Path("index.html").read_text(encoding="utf-8")
        self.assertIn("saved market snapshot, editable", source)
        self.assertIn("Market snapshot captured", source)
        self.assertIn("Stored pre-match prices, not live odds.", source)
        self.assertIn("f.odds_updated||D.odds_updated", source)
        self.assertIn("Snapshot is stale; automatic value comparisons are paused.", source)
        self.assertIn("No verified bookmaker snapshot is available for this fixture.", source)

class OddsFreshnessSafetyTests(unittest.TestCase):
    def test_market_snapshot_freshness_rejects_missing_invalid_future_and_old_times(self):
        source = Path("index.html").read_text(encoding="utf-8")
        self.assertIn("function marketSnapshotFresh(value)", source)
        self.assertIn("age>=0&&age<=36*3600e3", source)
        self.assertIn("automatic value comparisons are paused", source)

    def test_saved_odds_are_not_used_for_value_comparisons_after_expiry(self):
        source = Path("index.html").read_text(encoding="utf-8")
        self.assertIn("oddsUsable=!!(f.odds_manual||marketSnapshotFresh(oddsAt))", source)
        self.assertIn("if(oddsUsable&&odds&&odds.every(x=>x>1))", source)

    def test_share_images_and_top_three_ignore_stale_market_prices(self):
        source = Path("index.html").read_text(encoding="utf-8")
        self.assertIn("if(oddsFresh&&m.odds&&m.odds.every(o=>o>1))", source)
        self.assertIn("f.odds_manual||marketSnapshotFresh(f.odds_updated||D.odds_updated)", source)
