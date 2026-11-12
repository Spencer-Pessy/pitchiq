# PitchIQ

Football match analysis and probability forecasts.

**Live site:** https://spencer-pessy.github.io/pitchiq/

PitchIQ combines recent team performance, home/away scoring rates, Elo ratings and a Poisson goal model. Match details disclose the number of venue-specific matches supporting each scoring rate; those rates are shrunk toward the league average, while the form input uses the team's latest five matches across venues. It presents model probabilities, likely scorelines, selected market comparisons where odds are available, league tables and a public record of pre-match forecasts.

> Forecasts are statistical estimates for information and discussion. They are not betting advice, tips or guarantees.

## Current features

- Fixtures, scores, standings and scorers from football-data.org, including free-tier FIFA World Cup and UEFA European Championship tournament coverage (where fixtures are available). The main match list publishes upcoming fixtures up to 30 days ahead so international breaks do not leave the schedule looking empty.
- A separate international fixture feed combining OpenFootball's CC0 World Cup archive with ESPN's public, no-key scoreboard for international friendlies and selected confederation competitions. ESPN's endpoint is unofficial and coverage may be incomplete, so source and coverage metadata are retained and fixtures remain separate from the club prediction engine. International fixtures are listed without model forecasts until a reliable national-team history dataset is integrated.
- A separate national-team historical research pipeline builds chronological Elo strength ratings from Mart Jürisoo's CC0 men's full-international results dataset. It records source checksum, data-through date, team match counts and neutral-venue handling. This is a strength-prior research artifact only: it does not create international probabilities, alter club forecasts, or feed Telegram picks. The source includes some non-FIFA representative teams and is men's-only; international predictions remain disabled until the team scope, model calibration and chronological out-of-sample results are independently validated.
- Competition top-goalscorer comparison with goals, assists, appearances, goals per appearance, assists per appearance and combined goal contributions per appearance (not per 90; minutes played are not supplied). The provider returns a top-goalscorer list rather than a complete assists leaderboard, so alternate sorts compare only those listed players and unavailable stats remain blank.
- Home/draw/away, over 2.5 goals and both-teams-to-score probabilities.
- Likeliest scorelines and expected goals.
- Optional bookmaker-odds comparison from The Odds API. The odds publisher rejects malformed responses and refuses to replace the last good snapshot when no requested competition is active or no complete three-way markets are returned.
- Manual key-player absence adjustments in match details. Automated injury reports are currently unavailable; PitchIQ does not guess or fabricate injury information.
- Historical prediction ledger and a public performance record showing 1X2 accuracy with a 95% Wilson confidence interval, Brier score, log loss, home/draw/away one-vs-rest probability calibration, overall and competition-level home/away expected-goals MAE and signed bias (predicted minus actual), plus home/away expected-goals calibration bands comparing mean forecast goals with mean actual goals, bias and MAE (bands under ten matches are monitoring-only), and additional market hit rates. The Results tab highlights the exact Telegram picks that have settled, with their original pre-match selection, probability, final score and hit/miss status; it also retains the wider completed-fixture list. The Record tab compares forecasts with no-look-ahead global and competition-aware rolling outcome priors; the competition prior is smoothed toward the global prior using five prior-match equivalents. Where saved pre-match odds exist, it also compares PitchIQ with a de-vigged bookmaker consensus on the exact same match sample. All baseline probabilities use only results available before each kickoff, and matches sharing a kickoff timestamp share the same prior. New schema-2 forecast-input snapshots preserve the exact pre-match team/league inputs and calibration used for each forecast. A separate forward-only `model_evaluation.json` ledger also captures fresh research forecasts for upcoming fixtures already present in the public list, without changing any published prediction. It records the original inputs/calibration, then adds the final score after the match. Controlled same-match replays switch Elo and/or recent form off and compare them with the full model on this identical prospective sample. Paired bootstrap 95% intervals show uncertainty in each Brier-score difference; intervals crossing zero do not establish a clear improvement. Older public forecasts are never reconstructed from later data. Snapshot groups below ten completed forecasts are explicitly monitoring-only. Competition samples are displayed as monitoring signals, not league rankings.
- Telegram match-day forecasts only when eligible, unpublished fixtures are available. The picks bot does not fill quiet days with unrelated headlines or transfer gossip. It keeps a persistent ledger of the exact top picks it published (match ID and original pre-match probabilities), then posts each pick's full-time score and correct/missed status after the result is recorded. Unfinished picks stay pending; unrelated results and replacement forecasts are never substituted. An hourly results-only workflow checks for completed picks without generating new picks or news; the daily picks workflow remains separate.
- Shareable forecast/record graphics, match reminders, phone-local notes and a mobile-friendly installable web app with offline shell and last-known-data caching.

## Data flow

1. `update.py` retrieves competition fixtures/results and standings, calculates team statistics and forecasts, and updates `data.json` and `predictions.json`.
2. `odds.py` refreshes the optional odds snapshot in `odds.json`.
3. `international.py` refreshes a separate national-team fixture snapshot from OpenFootball's CC0 World Cup archive and ESPN's public scoreboard for selected international competitions; individual ESPN league failures are isolated, and the previous snapshot is preserved if every ESPN scoreboard request fails.
4. `international_history.py` downloads the CC0 men's international results CSV, validates and deduplicates completed matches, then replays them chronologically to create `international_ratings.json`. The Elo snapshot is not a prediction model and is not consumed by the website or Telegram publisher.
4. `telegram.py` posts the top three upcoming forecasts only when new eligible picks exist; otherwise it sends nothing. It also supports a results-only mode that checks `daily/published_picks.json` and posts full-time results for those same saved picks, preserving their original probabilities and selection.
5. `index.html` reads the published JSON files and renders the website.

The prediction ledger preserves the first forecast recorded before kickoff. Completed results are added after matches finish. When bookmaker odds become available later, the updater can attach the first valid pre-kickoff market snapshot to an existing upcoming forecast and records its separate `odds_updated` timestamp; it never replaces an existing odds snapshot or changes the forecast probabilities, inputs or original `made` timestamp. This keeps the forecast and market-data timing distinguishable. New records also capture a versioned snapshot of the team and league inputs used at forecast time, including venue/form sample sizes, so later diagnostics can test input signals without reconstructing them from changed data. Older records remain valid but do not have these snapshots; they are deliberately not reconstructed from later data. The Record tab explains this while the first snapshot-backed results accumulate. Do not manually edit historical prediction probabilities or final scores.

The forecasting calculations live in `pitchiq_model.py`, separate from API and file operations. `pitchiq_data.py` keeps international tournament goal averages separate from club-football averages. Offline unit tests in `test_pitchiq_model.py` and `test_pitchiq_data.py` cover the probability model, evaluation metrics and competition grouping. Run them with `python -m unittest -v test_pitchiq_model test_pitchiq_data test_international test_international_history`. Run `python model_metrics.py` to calculate accuracy with a 95% Wilson interval, multiclass Brier score, log loss and expected-goals mean absolute error from the saved prediction ledger.

## GitHub Actions

The enabled workflows in `.github/workflows/` run on their schedules or, where enabled, can be run manually with **Actions → select workflow → Run workflow**:

- **Update data** — every 30 minutes.
- **Update odds** — paused by default pending explicit approval to use Odds API credits. The scheduled job is disabled and makes no requests; the existing odds snapshot remains available to the site.
- **Update international fixtures** — daily; public no-key scoreboard requests plus the OpenFootball CC0 archive. ESPN's scoreboard is unofficial and may change without notice.
- **Update national-team historical ratings** — weekly; refreshes a CC0 men's international results snapshot and rebuilds a separate chronological Elo research artifact. No paid API or prediction publication.
- **Telegram picks** — daily.
- **Published-pick results** — hourly; checks only the saved picks ledger and does not call odds services or post new picks.

The data updater now stops if a competition fixture request fails, rather than publishing a partial fixture feed. A successful response containing zero eligible fixtures is valid. Each successful refresh also writes a `data_health` summary into `data.json`, including fixture counts by competition, international fixture totals, standings coverage and the number of matches published. This makes feed coverage easier to audit without exposing API credentials.

## Repository secrets

Configure secrets under **Settings → Secrets and variables → Actions**. Never put API keys or bot tokens in source files.

- `FOOTBALL_DATA_KEY` — football-data.org.
- `ODDS_API_KEY` — The Odds API.
- `TELEGRAM_BOT_TOKEN` — Telegram bot token.
- `TELEGRAM_CHAT_ID` — destination chat/channel ID.

Third-party API quotas and free-plan limits can change. PitchIQ's scheduled integrations should stay within available free allowances; do not add paid services or subscriptions without explicit approval.

## Local checks

Python automation scripts use the Python standard library except `telegram.py`, which uses Pillow to create the forecast image. Telegram publication uses side-effect-free validation helpers in `pitchiq_telegram.py` to skip malformed fixture/score records and validate its persistent published-pick ledger instead of letting one bad row break a scheduled post. The GitHub Actions Telegram workflow installs Pillow at runtime.

- Check Python syntax: `python -m py_compile update.py international.py international_history.py odds.py telegram.py pitchiq_model.py pitchiq_data.py model_metrics.py test_pitchiq_model.py test_pitchiq_data.py test_pitchiq_web.py test_international.py test_international_history.py pitchiq_telegram.py test_pitchiq_telegram.py`
- Run the website by serving the repository root over HTTP; opening `index.html` directly may prevent JSON fetches from working.
- The service worker caches the app shell and last successful JSON snapshots for offline viewing; the next connection refreshes them.
- To test scheduled integrations, use the corresponding GitHub Actions workflow and inspect its logs.

## Privacy and limitations

There are no user accounts. Match notes and manual absence adjustments are stored in the visitor's browser. External data may be delayed or incomplete; reported absences do not automatically alter model probabilities. Odds coverage depends on the relevant provider's availability and quota; automated injury reports are disabled.


### Feed-health diagnostics

The published `data_health` object reports fixture counts by competition, total and international fixture counts, available standings competitions, and the names/count of standings feeds that failed. A failed or malformed fixture response aborts the update so the last good `data.json` is preserved; standings failures are recorded explicitly because tables are optional to fixture forecasts. The website surfaces unavailable standings feeds instead of presenting coverage as complete.


### International fixtures and free API quota

The international feed combines the 2026 FIFA World Cup archive from OpenFootball's public-domain (CC0) repository with ESPN's unauthenticated scoreboard for international friendlies and selected confederation competitions. Neither source requires a paid subscription or private API key. ESPN's site API is unofficial/undocumented, may change without notice, and its competition coverage is not guaranteed; the snapshot records which scoreboard leagues responded. Fixtures remain separate from club forecasts until a validated national-team historical dataset is integrated. Automated injury reports are paused because no sufficiently reliable, unrestricted free replacement has been validated; users can still adjust key-player absences manually. No API-Football secret is required by PitchIQ.


### Exact-scoreline diagnostics

The Record tab replays the model's normalised 8×8 Poisson + Dixon–Coles score grid from each completed forecast's saved pre-match expected-goal rates. It reports exact-score negative log likelihood and the most-likely exact-score hit rate. Rates are stored rounded to four decimals, so this is a close retrospective replay rather than a bit-for-bit reconstruction of the original unrounded matrix. Results outside the 0–7 goals-per-team grid and rows without valid saved rates are excluded and counted. Exact-score hit rate is a secondary diagnostic; negative log likelihood is the more informative probability score. Neither metric establishes betting value or future performance.


The exact-scoreline Record panel also compares the average probability assigned to each forecast's single most likely score with its observed hit rate, grouped into confidence bands. It reports the combined probability mass of the three most likely scorelines against the observed top-three coverage. These are descriptive calibration checks; sparse bins should not drive model changes.


### Dixon–Coles scoreline baseline

The Record diagnostics compare the saved Dixon–Coles scoreline distribution with an independent Poisson model using the same saved pre-match expected-goal rates, the same 8×8 (0–7 goals) grid, and separate normalisation. It reports paired exact-score negative log likelihood, the mean Dixon–Coles-minus-independent difference, a deterministic paired-bootstrap 95% interval, and match-level wins/ties. A negative difference favours Dixon–Coles; an interval crossing zero does not establish a clear improvement. Invalid rates and scores outside the grid are excluded and counted. This is a retrospective diagnostic, not an automatic model switch.

The fixture updater no longer reads a stale injury cache: automated injury feeds remain disabled until a reliable free source is validated. Manual key-player absence adjustments remain available in the website.
