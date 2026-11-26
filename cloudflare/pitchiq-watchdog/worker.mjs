const OWNER = "Spencer-Pessy";
const REPOSITORY = "pitchiq";
const WORKFLOW_FILE = "pipeline-watchdog.yml";
const BRANCH = "main";
const MINIMUM_RUN_AGE_MS = 12 * 60 * 1000;
const API_ROOT = `https://api.github.com/repos/${OWNER}/${REPOSITORY}`;

function githubHeaders(token) {
  return {
    Accept: "application/vnd.github+json",
    Authorization: `Bearer ${token}`,
    "X-GitHub-Api-Version": "2022-11-28",
    "User-Agent": "PitchIQ-External-Watchdog",
  };
}

async function checkedJson(response, label) {
  if (!response.ok) {
    let detail = "";
    try {
      detail = await response.text();
    } catch {
      detail = "";
    }
    throw new Error(`${label} failed: GitHub HTTP ${response.status} ${detail.slice(0, 300)}`);
  }
  return response.json();
}

/**
 * Dispatch the repository watchdog only when GitHub has not run it recently.
 * This worker never calls football-data providers or changes repository files.
 */
export async function checkAndDispatch(env, fetchImpl = fetch, nowMs = Date.now()) {
  const token = env?.PITCHIQ_GITHUB_TOKEN;
  if (typeof token !== "string" || !token.trim()) {
    throw new Error("PITCHIQ_GITHUB_TOKEN secret is missing.");
  }

  const headers = githubHeaders(token);
  const runsUrl =
    `${API_ROOT}/actions/workflows/${WORKFLOW_FILE}/runs?branch=${BRANCH}&per_page=1`;
  const runsResponse = await fetchImpl(runsUrl, { method: "GET", headers });
  const payload = await checkedJson(runsResponse, "Reading watchdog run history");

  if (!payload || !Array.isArray(payload.workflow_runs)) {
    throw new Error("GitHub returned an incomplete watchdog run-history response.");
  }

  const latest = payload.workflow_runs[0] ?? null;
  if (latest) {
    if (latest.status === "queued" || latest.status === "in_progress") {
      return { action: "skipped_active", run_id: latest.id ?? null };
    }

    const createdAt = Date.parse(latest.created_at);
    if (!Number.isFinite(createdAt)) {
      throw new Error("Latest watchdog run has an invalid created_at timestamp.");
    }

    const ageMs = nowMs - createdAt;
    if (ageMs < MINIMUM_RUN_AGE_MS) {
      return {
        action: "skipped_recent",
        run_id: latest.id ?? null,
        age_minutes: Math.max(0, Math.floor(ageMs / 60000)),
      };
    }
  }

  const dispatchUrl = `${API_ROOT}/actions/workflows/${WORKFLOW_FILE}/dispatches`;
  const dispatchResponse = await fetchImpl(dispatchUrl, {
    method: "POST",
    headers: { ...headers, "Content-Type": "application/json" },
    body: JSON.stringify({ ref: BRANCH }),
  });

  if (!dispatchResponse.ok) {
    let detail = "";
    try {
      detail = await dispatchResponse.text();
    } catch {
      detail = "";
    }
    throw new Error(
      `Dispatching watchdog failed: GitHub HTTP ${dispatchResponse.status} ${detail.slice(0, 300)}`,
    );
  }

  return { action: "dispatched", previous_run_id: latest?.id ?? null };
}

export default {
  async scheduled(controller, env) {
    const result = await checkAndDispatch(env);
    console.log(
      JSON.stringify({
        event: "pitchiq-watchdog-heartbeat",
        cron: controller.cron,
        scheduled_time: new Date(controller.scheduledTime).toISOString(),
        ...result,
      }),
    );
  },
};
