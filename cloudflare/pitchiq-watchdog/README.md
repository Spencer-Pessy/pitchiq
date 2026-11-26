# PITCH IQ external watchdog (Cloudflare Workers Free)

This small Worker is an optional external clock for the existing GitHub Actions
pipeline watchdog. It does **not** fetch football data, publish files, or change
predictions. It only checks GitHub's latest watchdog run and dispatches
`.github/workflows/pipeline-watchdog.yml` when no recent run exists.

## Free-only design

- One Cron Trigger every five minutes (288 scheduled invocations per day).
- One GitHub Actions read request per invocation.
- A GitHub Actions dispatch is sent only when the latest watchdog run is at
  least 12 minutes old, or no run exists.
- An already queued or running watchdog is never duplicated.
- No football provider API calls, paid APIs, paid hosting, or custom domain.
- The Worker has no public HTTP handler.

Cloudflare Workers Free currently includes 100,000 requests per day. This
Worker's 288 scheduled invocations per day are comfortably below that limit.
Cron Triggers run in UTC. Cloudflare notes that trigger changes can take up to
15 minutes to propagate.

## GitHub token

Create a **fine-grained personal access token** in GitHub with:

1. Repository access limited to `Spencer-Pessy/pitchiq`.
2. Repository permission **Actions: Read and write**.
3. No other repository permissions.

Do not put the token in this repository, in a commit, or in ChatGPT. It must be
stored only as a Cloudflare Worker secret named `PITCHIQ_GITHUB_TOKEN`.

## Deploy from the Cloudflare dashboard

1. Sign in to Cloudflare and open **Workers & Pages**.
2. Create a Worker named `pitchiq-watchdog`.
3. Replace its starter code with the contents of `worker.mjs` from this folder,
   then deploy it.
4. Open the Worker **Settings → Variables and Secrets**.
5. Add `PITCHIQ_GITHUB_TOKEN` as a **Secret** (not a plain-text variable).
6. Open **Settings → Triggers → Cron Triggers**.
7. Add the cron expression `*/5 * * * *` and save.

No domain or public route is required. Allow up to 15 minutes for the Cron
Trigger to propagate. Check the Worker's logs for one of these outcomes:

- `dispatched`: no recent watchdog run was found; GitHub was asked to run it.
- `skipped_recent`: GitHub already ran the watchdog within the last 12 minutes.
- `skipped_active`: a watchdog run is already queued or running.

## Deploy with Wrangler (alternative)

From this folder, after authenticating Wrangler with your Cloudflare account:

```sh
npx wrangler secret put PITCHIQ_GITHUB_TOKEN
npx wrangler deploy
```

The schedule is defined in `wrangler.toml`. The dashboard and Wrangler
configuration should not both be used to manage the same Cron Trigger.

## Local test

Run the test file with Node.js 18 or newer:

```sh
node --test worker.test.mjs
```
