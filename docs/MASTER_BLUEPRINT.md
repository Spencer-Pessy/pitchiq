# PITCH IQ — Master Product & Technical Blueprint

**Status:** Living blueprint; implementation is active, not declared complete  
**Last reviewed:** 14 November 2026  
**Live website:** https://spencer-pessy.github.io/pitchiq/  
**Repository:** https://github.com/Spencer-Pessy/pitchiq

## 1. Product purpose

PITCH IQ is a free, mobile-friendly football information and analysis platform for a global audience. It combines fixtures, results, standings, transparent club-match probability forecasts, historical performance evaluation, and sourced football news.

The product should earn trust through useful analysis, clear limitations, and honest records—not by encouraging betting or promising guaranteed outcomes.

### Non-negotiable product rules

- Keep the platform free. Do not add paid APIs, subscriptions, premium services, or paid infrastructure without the owner's explicit approval.
- Do not describe model probabilities as betting tips, financial advice, or guarantees.
- Never invent fixtures, scores, injuries, H2H meetings, statistics, odds, or news.
- Keep international fixtures separate from the club prediction engine. International matches are fixture-information only: no predictions, model analysis, confidence scores, form analysis, H2H analysis, or Telegram picks.
- Keep all published forecasts time-stamped and pre-match. Do not rewrite historical probabilities or reconstruct old forecasts from later data.
- Preserve the last good published data snapshot when an upstream feed fails or returns malformed/incomplete data.
- Protect API keys and bot tokens in GitHub Actions Secrets; never place credentials in source files or public data.
- Keep the visual identity black, red, and white, with responsive layouts suitable for phones.

## 2. Website structure and user experience

The main navigation contains:

1. **Upcoming** — upcoming club fixtures and available match information.
2. **Picks** — eligible model forecasts, with probabilities and clear disclaimers.
3. **Results** — completed matches and the original saved selections/results for published Telegram picks.
4. **Record** — historical forecast performance, calibration, baselines, and model diagnostics.
5. **Table** — available league standings.
6. **International** — separate international fixture information, without predictions or analysis.
7. **News** — sourced football headlines and links to the Pitch IQ Telegram news and picks channels, plus social/contact links.

The dedicated Match Centre can show the model's 1X2 probability bar and accessible doughnut chart, available H2H meetings, recent form, team-strength and goal-rate comparisons, expected goals, goal-market probabilities, likely scorelines, verified goal events, and saved odds snapshots. The doughnut represents the existing model probabilities; it does not change model weights.

The Record area includes the rolling 10-match 1X2 accuracy line graph and competition accuracy bars. Competition bars are shown only when a competition has at least 10 completed forecasts. Detailed tables remain available alongside the visual comparisons. Charts are descriptive monitoring tools, not claims of future performance.

**Feedback placement:** Keep the independent feedback form link at the bottom of the News tab. Do not add a separate Feedback item to the main navigation. Current responder link: https://forms.gle/gJ19T2NeSWWbZmgy6

## 3. Forecasting approach and evaluation

The production club model uses recent form, venue-specific scoring rates, Elo strength, league scoring averages, and a Poisson goal model with Dixon–Coles scoreline handling. Home/away goal-rate inputs are shrunk toward league averages when samples are limited. The form input uses the latest five matches across venues. Match details should disclose sample sizes and the information actually available.

The site presents home/draw/away probabilities, over-2.5 and both-teams-to-score probabilities, likely scorelines, and expected goals where valid inputs exist. Key-player absences can be adjusted manually; automated injury reporting is not enabled because a sufficiently reliable unrestricted free feed has not been validated.

### Evaluation principles

- Evaluate only forecasts with valid saved pre-match probabilities and completed scores.
- Report sample sizes with accuracy and error metrics.
- Use 95% Wilson intervals for 1X2 accuracy, alongside Brier score, log loss, expected-goals MAE/bias, and calibration diagnostics.
- Compare baselines only on the exact same completed-match sample and use no-look-ahead historical information.
- Keep public prediction history separate from the forward-only research ledger in `model_evaluation.json`.
- Treat small samples as monitoring signals, not competition rankings or proof of model superiority.
- Do not tune the production model from a noisy chart or a small sample alone.

## 4. Data sources and boundaries

| Area | Source / method | Boundary |
|---|---|---|
| Club fixtures, results, standings, scorers | football-data.org | Respect the available plan, coverage, and request limits; preserve last good data on invalid responses. |
| H2H | football-data.org H2H endpoint | Display-only; cache responses; never feed H2H into model probabilities. |
| Odds comparison | The Odds API | Optional free-tier use only; designed around the provider's published 500-credit monthly allowance. No paid upgrade. |
| International fixtures | OpenFootball CC0 archive plus ESPN public scoreboard | Separate feed; ESPN is unofficial and coverage may be incomplete. No international predictions or analysis. |
| International history research | CC0 men's international results dataset | Research-only Elo diagnostic; not used for production predictions, website forecasts, or Telegram picks. |
| SportAPI | Manual smoke-test workflow | Authentication/coverage probe only; not a production feed unless separately reviewed and explicitly approved. |
| Football news | Sourced headlines with original source links | Label transfer rumours as unconfirmed; distinguish news from model forecasts. |

Third-party free quotas, endpoints, and coverage can change. Recheck terms and quotas before changing request volume or adding a source.

## 5. Data pipeline and repository architecture

- `update.py` coordinates club fixtures/results, statistics, forecasts, prediction history, and data publication.
- `pitchiq_model.py` contains forecasting calculations independently of API/file operations.
- `pitchiq_data.py` handles data normalization and competition/league inputs.
- `pitchiq_h2h.py` manages cached H2H enrichment and identity checks.
- `odds.py` and `pitchiq_odds.py` handle optional odds snapshots and validation.
- `international.py` publishes the separate international fixture feed.
- `international_history.py` builds the separate historical national-team research artifact.
- `telegram.py`, `pitchiq_telegram.py`, and `pitchiq_news.py` handle picks, settled-pick results, news, and validation.
- `index.html` renders the public website from published JSON snapshots.
- `sw.js` and `manifest.json` support installation and offline shell/last-known-data use.
- `test_*.py` and `test_sw.js` provide offline regression coverage.

### Important published data

- `data.json` — current club fixtures, match details, tables, feed-health metadata, and model diagnostics.
- `predictions.json` — immutable first pre-match forecast records with later result updates.
- `model_evaluation.json` — separate forward-only research forecasts and their eventual results.
- `h2h_cache.json` — quota-aware H2H cache.
- `international.json` — separate international fixtures.
- `international_ratings.json` and `international_team_registry.json` — research-only historical ratings and team identity checks.
- `odds.json` — optional saved odds snapshot.
- `daily/published_picks.json` — exact Telegram picks and their original probabilities.
- `daily/news_seen.json` and `daily/telegram_health.json` — news deduplication and workflow-health records.

## 6. Scheduled automation

The enabled GitHub Actions workflows provide the recurring data and publishing operations:

- Club data refresh: every 30 minutes.
- International fixtures: every six hours.
- Odds snapshot: once daily, subject to explicit free-tier confirmation and secret availability.
- Telegram picks: daily, only when eligible unpublished fixtures exist.
- Telegram news: every four hours, with deduplication and source links.
- Published-pick results: hourly, results-only.
- Telegram workflow health: every 30 minutes; checks workflow status and age but does not claim that a successful workflow proves message delivery.
- National-team historical research refresh: weekly.
- Backup and test workflows: run on their configured triggers; the portable backup remains a separate deliverable.

The exact cron expressions and required secrets are maintained in `.github/workflows/` and the repository settings. Never copy secret values into this document.

## 7. H2H coverage policy

H2H is a display-only feature. The cache is keyed by fixture and both team IDs so that a response for a different pairing cannot be reused. The updater refreshes a small batch of nearest upcoming club fixtures, applies a 24-hour cooldown, and retains the last successful history if a request fails. Requests are paced for the free provider tier.

The Match Centre should display up to the five most recent finished meetings available from the provider before the upcoming kickoff, with correct home/away orientation. “All-time” means all history available from the selected provider—not a claim that every historical meeting worldwide is available. If the provider returns fewer than five meetings, show the actual count. Never fabricate missing H2H records.

## 8. Telegram and social presence

- Telegram news channel: https://t.me/pitchiq_picks
- Telegram picks bot: https://t.me/PitchIQPicks_bot
- TikTok and Instagram: @pitch.iq04
- X: @PitchIQ04

The picks bot posts up to three eligible forecasts on match days and later reports the results for those same saved picks. It must not substitute unrelated results or generate picks for international matches. The news channel posts sourced football headlines with original links; transfer speculation must be labelled unconfirmed. Social content should build conversation and trust rather than turn every post into a sales pitch.

## 9. Security, reliability, and release process

Before every manual GitHub write:

1. Read the latest `main` commit SHA.
2. Fetch the exact file contents and current blob SHA.
3. Confirm the branch and target file have not changed since inspection.
4. Make a focused change; do not overwrite concurrent edits.
5. Verify the resulting commit SHA and changed files.
6. Check relevant tests, Pages deployment, and the live site before reporting success.

Other safeguards:

- Use GitHub Actions Secrets for credentials.
- Validate provider responses before publishing.
- Keep scheduled workflows serialized where they write the same data.
- Do not publish partial or malformed fixture snapshots.
- Keep the public prediction ledger and research evaluation ledger separate.
- Test offline behavior and the portable backup after meaningful structural changes.
- Never claim a feature is live until the deployed site has been checked.

## 10. Verified status on 14 November 2026

The following is a point-in-time snapshot, not a promise that counts will remain unchanged:

- The live website is deployed on GitHub Pages.
- The Record page has 86 completed public forecasts across six competitions; the current aggregate 1X2 record is 49 correct from 86 (about 57%).
- The newly deployed rolling 10-match line graph and competition comparison bars were confirmed visible in the live Record page. No chart rendering errors were observed.
- Competition samples currently range from 11 to 18 completed forecasts; bars therefore meet the 10-match display threshold.
- The Match Centre doughnut chart remains separate.
- The current club fixture snapshot contains 238 published matches. Eighteen currently contain at least one cached H2H meeting; 220 have no H2H meeting data in that snapshot yet. The cache contains 20 fixture entries, including entries where the provider returned no meetings. Coverage is being expanded gradually under the free request limit.
- The public forecast ledger contains 323 records, including 86 completed records. The separate forward-only evaluation ledger contains 237 research forecasts; it must not be counted as public settled performance.
- The international fixture feed is separate and does not publish predictions or analysis.
- The latest chart change passed the model tests, offline tests, and Pages deployment; the portable backup workflow also completed successfully.

## 11. Remaining work and completion criteria

PITCH IQ is **not yet declared finished**. The blueprint is now documented, but implementation and monitoring continue.

1. **H2H coverage:** Continue gradual cache enrichment; audit zero-meeting responses and show honest sample counts. Do not increase API usage beyond the free allowance.
2. **Performance evidence:** Let more forecasts settle before interpreting rolling or competition charts. Keep the 10-match chart window and minimum competition sample visible in the interface.
3. **International coverage:** Improve source coverage and reliability while preserving the strict fixture-only boundary.
4. **User feedback:** Keep the feedback form at the bottom of News and review responses before prioritizing interface changes.
5. **Quality and backup:** Continue regression tests, Pages checks, and portable-backup verification after material changes.
6. **Blueprint maintenance:** Update this document when a feature, source, workflow, data schema, or product rule changes; distinguish implemented, tested, and planned work.

A feature is complete only when its data source and limitations are documented, tests pass, the live website is verified, and no paid service has been introduced without approval.
