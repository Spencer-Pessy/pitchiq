# PitchIQ

Football match analysis and probability forecasts.

**Live site:** https://spencer-pessy.github.io/pitchiq/

PitchIQ combines recent team performance, home/away scoring rates, Elo ratings and a Poisson goal model. It presents model probabilities, likely scorelines, selected market comparisons where odds are available, league tables and a public record of pre-match forecasts.

> Forecasts are statistical estimates for information and discussion. They are not betting advice, tips or guarantees.

## Current features

- Fixtures, scores, standings and scorers from football-data.org, including free-tier FIFA World Cup and UEFA European Championship tournament coverage (where fixtures are available).
- A separate no-key OpenFootball World Cup 2026 fixtures/results feed (CC0). It is tournament-only, not a complete international calendar; football-data.org separately supplies its free World Cup and EURO coverage. International fixtures are listed without model forecasts until a reliable national-team history dataset is integrated.
- Competition top-scorer comparison with goals, assists, appearances, goals per appearance, assists per appearance and combined goal contributions per appearance (not per 90; minutes played are not supplied by this source).
- Home/draw/away, over 2.5 goals and both-teams-to-score probabilities.
- Likeliest scorelines and expected goals.
- Optional bookmaker-odds comparison from The Odds API.
- Manual key-player absence adjustments in match details. Automated injury reports are currently unavailable; PitchIQ does not guess or fabricate injury information.
- Historical prediction ledger and a public performance record showing 1X2 accuracy, Brier score, log loss, expected-goals MAE and additional market hit rates.
- Telegram match-day forecasts and football headlines when there are no eligible matches.
- Shareable forecast/record graphics, match reminders, phone-local notes and a mobile-friendly installable web app with offline shell and last-known-data caching.

## Data flow

1. `update.py` retrieves competition fixtures/results and standings, calculates team statistics and forecasts, and updates `data.json` and `predictions.json`.
2. `odds.py` refreshes the optional odds snapshot in `odds.json`.
3. `international.py` refreshes a separate World Cup 2026 fixture/results snapshot from OpenFootball's public-domain JSON dataset; it validates the response and preserves the last good file if the source fails.
4. `telegram.py` posts the top three upcoming forecasts or a small set of linked football headlines to the configured Telegram destination.
5. `index.html` reads the published JSON files and renders the website.

The prediction ledger is intended to preserve the first forecast recorded before kickoff. Completed results are added after matches finish. Do not manually edit historical prediction probabilities or final scores.

The forecasting calculations live in `pitchiq_model.py`, separate from API and file operations. `pitchiq_data.py` keeps international tournament goal averages separate from club-football averages. Offline unit tests in `test_pitchiq_model.py` and `test_pitchiq_data.py` cover the probability model, evaluation metrics and competition grouping. Run them with `python -m unittest -v test_pitchiq_model test_pitchiq_data test_international`. Run `python model_metrics.py` to calculate accuracy, multiclass Brier score, log loss and expected-goals mean absolute error from the saved prediction ledger.

## GitHub Actions

The workflows in `.github/workflows/` can be run on their schedules or manually with **Actions → select workflow → Run workflow**:

- **Update data** — every 30 minutes.
- **Update odds** — twice daily.
- **Update international fixtures** — daily; one public JSON download, no API key.
- **Telegram picks** — daily.

The data updater now stops if a competition fixture request fails, rather than publishing a partial fixture feed. A successful response containing zero eligible fixtures is valid. Each successful refresh also writes a `data_health` summary into `data.json`, including fixture counts by competition, international fixture totals, standings coverage and the number of matches published. This makes feed coverage easier to audit without exposing API credentials.

## Repository secrets

Configure secrets under **Settings → Secrets and variables → Actions**. Never put API keys or bot tokens in source files.

- `FOOTBALL_DATA_KEY` — football-data.org.
- `ODDS_API_KEY` — The Odds API.
- `TELEGRAM_BOT_TOKEN` — Telegram bot token.
- `TELEGRAM_CHAT_ID` — destination chat/channel ID.

Third-party API quotas and free-plan limits can change. PitchIQ's scheduled integrations should stay within available free allowances; do not add paid services or subscriptions without explicit approval.

## Local checks

Python automation scripts use the Python standard library except `telegram.py`, which uses Pillow to create the forecast image. The GitHub Actions Telegram workflow installs Pillow at runtime.

- Check Python syntax: `python -m py_compile update.py international.py odds.py   telegram.py pitchiq_model.py pitchiq_data.py model_metrics.py test_pitchiq_model.py test_pitchiq_data.py`
- Run the website by serving the repository root over HTTP; opening `index.html` directly may prevent JSON fetches from working.
- The service worker caches the app shell and last successful JSON snapshots for offline viewing; the next connection refreshes them.
- To test scheduled integrations, use the corresponding GitHub Actions workflow and inspect its logs.

## Privacy and limitations

There are no user accounts. Match notes and manual absence adjustments are stored in the visitor's browser. External data may be delayed or incomplete; reported absences do not automatically alter model probabilities. Odds and injury coverage depend on the relevant provider's availability and quota.


### Feed-health diagnostics

The published `data_health` object reports fixture counts by competition, total and international fixture counts, available standings competitions, and the names/count of standings feeds that failed. A failed or malformed fixture response aborts the update so the last good `data.json` is preserved; standings failures are recorded explicitly because tables are optional to fixture forecasts. The website surfaces unavailable standings feeds instead of presenting coverage as complete.


### International fixtures and free API quota

The international feed downloads the 2026 FIFA World Cup dataset from OpenFootball's public-domain (CC0) repository once daily. It requires no API key, account, or subscription. Its scope is the World Cup tournament only; it does not provide a live calendar of friendlies or qualifiers. football-data.org's free tier separately includes World Cup and European Championship coverage. Automated injury reports are paused because no sufficiently reliable, unrestricted free replacement has been validated; users can still adjust key-player absences manually. No API-Football secret is required by PitchIQ.
