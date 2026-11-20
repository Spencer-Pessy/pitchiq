# PITCH IQ — Master Product & Technical Blueprint

**Status:** Living blueprint; implementation is active, not declared complete  
**Last reviewed:** 20 November 2026  
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
- `model_evaluation.json` — separate forward-only research forecasts and their eventual results. The updater validates the existing ledger and stops rather than resetting it when history is unreadable or malformed.
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
- Telegram picks: every three hours at minute 43 UTC (01:43–22:43 UTC), only when eligible unpublished club fixtures exist within the next 36 hours.
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

The picks bot checks every three hours and posts up to three eligible club forecasts when available, then reports the results for those same saved picks. It must not substitute unrelated results or generate picks for international matches. The news channel posts sourced football headlines with original links; transfer speculation must be labelled unconfirmed. Social content should build conversation and trust rather than turn every post into a sales pitch.

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
- The current club fixture snapshot contains 238 published matches. The H2H cache contains 25 fixture entries: 21 with at least one verified meeting and 4 where the provider returned no meetings. The live Match Centre was checked using Troyes vs Le Havre (zero meetings), Como 1907 vs Cagliari (four), and Napoli vs Torino (five). The empty state, actual counts, five-row display limit, dates, scores, and home/away orientation all matched the cached data. H2H remains display-only and coverage is being expanded gradually under the free request limit.
- The public forecast ledger contains 323 records, including 86 completed records. The separate forward-only evaluation ledger contains 237 research forecasts; it must not be counted as public settled performance.
- The international fixture feed is separate and does not publish predictions or analysis. The live International listing and two fixture detail pages (Japan vs Brazil and China vs Malaysia) were checked: only fixture information is shown, with no picks, probabilities, confidence, model analysis, form, H2H, or betting recommendations.
- The latest chart change passed the model tests, offline tests, and Pages deployment; the portable backup workflow also completed successfully.
- The News tab footer was checked live: “Send feedback” appears at the bottom after the social links, between “How it works” and “Telegram alerts”; Feedback is not a separate navigation tab.

## 11. Remaining work and completion criteria

PITCH IQ is **not yet declared finished**. The blueprint is now documented, but implementation and monitoring continue.

1. **H2H coverage:** The live Match Centre display audit passed for zero, fewer-than-five, and five-meeting examples, including correct score orientation. Continue gradual cache enrichment and show honest sample counts. Do not increase API usage beyond the free allowance.
2. **Performance evidence:** Let more forecasts settle before interpreting rolling or competition charts. Keep the 10-match chart window and minimum competition sample visible in the interface.
3. **International coverage:** The live fixture-only boundary was verified on the listing and two match details. Improve source coverage and reliability without introducing national-team predictions or analysis.
4. **User feedback:** The News-tab footer placement is live and verified; review responses before prioritizing interface changes.
5. **Quality and backup:** Continue regression tests, Pages checks, and portable-backup verification after material changes.
6. **Blueprint maintenance:** Update this document when a feature, source, workflow, data schema, or product rule changes; distinguish implemented, tested, and planned work.

A feature is complete only when its data source and limitations are documented, tests pass, the live website is verified, and no paid service has been introduced without approval.


## 12. Verified operational status on 19 November 2026

This is a dated monitoring snapshot, not a completion declaration.

- **Club data:** The latest published `data.json` snapshot is `2026-11-19T00:21:06Z`. At 05:52 UTC it was about 5 hours 31 minutes old despite the 30-minute schedule. The latest observed scheduled updater run was #153 (00:17 UTC), which succeeded; no later updater run appeared in the Actions history at the time of review. GitHub Status reported all systems operational on 19 November, so the cause of the missed runs is not confirmed. Do not claim the schedule is restored.
- **Coverage:** The snapshot contains 419 published fixtures. Provider metadata covers all 12 configured free-tier competitions; 10 competitions have current standings and there are zero reported standings failures. The club feed remains the priority.
- **Forecast integrity:** The public ledger contains 504 forecasts, including 86 settled. The most-likely 1X2 outcome was correct in 49/86 (57.0%); the 95% Wilson interval is 46.4%–66.9%. The separate forward-only ledger contains 418 forecasts and no completed matches. Comparing the 500 public records at the updater's starting commit with the current ledger found all 500 retained and no changes to their saved pre-match forecast fields; four new records were added.
- **Tests and deployment:** The latest model test run (#785) passed 307 tests and the latest offline run (#288) passed 285 tests on source commit `d61a85c`. The successful updater run #153 also ran 268 offline tests on `978e629` before publishing. The intervening commits through `053df94` changed only generated data/health ledgers, not source code. Pages deployment #1098 succeeded for `053df94`. No separate test workflow was attached to that exact data-only HEAD at the time of this review.
- **Optional feeds:** The international snapshot contains 180 fixtures and was last updated at `2026-11-18T20:43:59Z`; the updater logs recorded ESPN HTTP 503 responses. International coverage remains separate and must not delay club coverage. The odds snapshot contains 184 events and was last updated at `2026-11-18T16:36:16Z`; its next daily refresh was not yet due at the review time.
- **Dependency maintenance:** Dependabot PRs #17–#19 each have successful offline and model-test runs on their PR heads, but each branch is 46 commits behind `main`. They were not merged; synchronize and rerun checks before considering them.
- **Next actions:** Investigate the missing scheduled club updater runs, verify actual Telegram delivery separately from workflow success, and revisit the stale dependency branches after synchronization. Keep the free-only policy and forecast-history protections unchanged.


## 13. Operational review on 20 November 2026

This point-in-time review was collected at 05:43 UTC (08:43 Qatar time), before the fail-closed research-ledger change in the same commit. The inspected base `main` SHA was `54607bb`.

- **Club feed and schedule:** `data.json` was last updated at `2026-11-19T23:50:25Z`, about 5 hours 53 minutes old at review time. It contained 446 published match rows (437 future, 6 finished, 2 live and 1 cancelled). Provider metadata covered 3,595 fixtures across all 12 configured free-tier competitions; 10 standings competitions were available with no reported standings failures. The latest observed scheduled club updater was run #44640417484 at 23:46:18Z on 19 November and succeeded. No later scheduled updater appeared in the latest 100 Actions runs; the newest run in that list was at 03:16:40Z on 20 November. This is a missed schedule, not a recorded failing updater job; the cause is unconfirmed. Keep club refresh the priority.
- **Forecast integrity:** The public ledger contained 531 forecasts, including 92 settled; the most-likely 1X2 outcome was correct in 53/92 (57.6%), with a 95% Wilson interval of 47.4%–67.2%. Comparing the ledger at source-test commit `d1be1af` with the reviewed snapshot found all 504 shared records retained with identical probabilities, saved inputs, original timestamps, kickoff, teams and competition; 27 records were added. The separate forward-only research ledger contained 445 forecasts, including 6 completed. No production model weights were changed.
- **Tests and Pages:** The latest model workflow passed 307 tests and the offline workflow passed 285 tests on `d1be1af`. The comparison from that commit to reviewed base `54607bb` contained only generated JSON snapshots and ledgers, with no source-code changes. There was no test workflow on that exact data-only base commit, so do not describe it as tested on the exact SHA. Pages deployment #1123 succeeded for the exact base SHA `54607bb`. The new research-ledger guard must still pass the workflows triggered by this commit before it is marked complete.
- **Telegram:** The latest picks run at 23:13Z on 19 November passed bot preflight but found no eligible matches in its next-36-hour window, so it sent no picks. The latest news run at 23:13Z confirmed a Telegram message (message ID 31). The latest results-only run at 03:16Z on 20 November completed and found no new results to post. The monitor snapshot was also checked at 03:16Z and is no longer current at this review time; `telegram_delivery_verified` remains false because workflow health is not proof of delivery.
- **Optional feeds and odds:** The separate international feed contained 157 fixtures and was last updated at 20:49Z on 19 November. The last club updater logs included ESPN HTTP 503 responses; international coverage remains optional and must not delay club fixtures. The odds snapshot contained 190 events and was last updated at 16:40Z on 19 November; it remains a separate daily free-tier workflow.
- **Portable backup:** Backup run #44469758857 succeeded on `d1be1af`; its 1,161,900-byte archive remains available until 17 February 2027. It predates the later generated JSON updates, so download a newer successful artifact after the next push-triggered backup completes.
- **Workflow history:** The latest 100 Actions runs contained no failed conclusions. Ten cancelled Pages runs were superseded builds, not failed deployments.

**Next actions:** Investigate the missing scheduled club refresh and publisher runs without adding paid services; verify the next scheduled executions, confirm this commit's test workflows and Pages deployment, and continue the H2H, backup and data-quality checks. Do not claim the schedule is restored until a new scheduled run is observed.
