import test from "node:test";
import assert from "node:assert/strict";
import { checkAndDispatch } from "./worker.mjs";

const NOW = Date.parse("2026-11-26T16:00:00.000Z");
const TOKEN = "test-token";

function response(payload, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    async json() { return payload; },
    async text() { return typeof payload === "string" ? payload : JSON.stringify(payload); },
  };
}

test("dispatches when GitHub has no watchdog run history", async () => {
  const calls = [];
  const fakeFetch = async (url, options = {}) => {
    calls.push({ url, options });
    return options.method === "POST" ? response({}, 204) : response({ workflow_runs: [] });
  };

  const result = await checkAndDispatch({ PITCHIQ_GITHUB_TOKEN: TOKEN }, fakeFetch, NOW);

  assert.equal(result.action, "dispatched");
  assert.equal(calls.length, 2);
  assert.match(calls[0].url, /actions\/workflows\/pipeline-watchdog\.yml\/runs/);
  assert.equal(calls[0].options.method, "GET");
  assert.match(calls[0].options.headers.Authorization, /^Bearer /);
  assert.match(calls[1].url, /actions\/workflows\/pipeline-watchdog\.yml\/dispatches$/);
  assert.equal(calls[1].options.method, "POST");
  assert.deepEqual(JSON.parse(calls[1].options.body), { ref: "main" });
});

test("skips dispatch when the latest watchdog run is active", async () => {
  let calls = 0;
  const fakeFetch = async () => {
    calls += 1;
    return response({
      workflow_runs: [{ id: 12, status: "in_progress", created_at: "2026-11-26T15:00:00Z" }],
    });
  };

  const result = await checkAndDispatch({ PITCHIQ_GITHUB_TOKEN: TOKEN }, fakeFetch, NOW);

  assert.deepEqual(result, { action: "skipped_active", run_id: 12 });
  assert.equal(calls, 1);
});

test("skips dispatch when a completed watchdog run is less than 12 minutes old", async () => {
  let calls = 0;
  const fakeFetch = async () => {
    calls += 1;
    return response({
      workflow_runs: [{
        id: 13,
        status: "completed",
        created_at: new Date(NOW - 5 * 60 * 1000).toISOString(),
      }],
    });
  };

  const result = await checkAndDispatch({ PITCHIQ_GITHUB_TOKEN: TOKEN }, fakeFetch, NOW);

  assert.equal(result.action, "skipped_recent");
  assert.equal(result.run_id, 13);
  assert.equal(calls, 1);
});

test("dispatches when the latest completed watchdog run is stale", async () => {
  const calls = [];
  const fakeFetch = async (url, options = {}) => {
    calls.push({ url, options });
    return options.method === "POST"
      ? response({}, 204)
      : response({
          workflow_runs: [{
            id: 14,
            status: "completed",
            created_at: new Date(NOW - 13 * 60 * 1000).toISOString(),
          }],
        });
  };

  const result = await checkAndDispatch({ PITCHIQ_GITHUB_TOKEN: TOKEN }, fakeFetch, NOW);

  assert.deepEqual(result, { action: "dispatched", previous_run_id: 14 });
  assert.equal(calls.length, 2);
});

test("fails closed when GitHub returns incomplete run history", async () => {
  const fakeFetch = async () => response({});
  await assert.rejects(
    checkAndDispatch({ PITCHIQ_GITHUB_TOKEN: TOKEN }, fakeFetch, NOW),
    /incomplete watchdog run-history response/,
  );
});

test("fails closed when the GitHub read request is rejected", async () => {
  const fakeFetch = async () => response("forbidden", 403);
  await assert.rejects(
    checkAndDispatch({ PITCHIQ_GITHUB_TOKEN: TOKEN }, fakeFetch, NOW),
    /HTTP 403/,
  );
});

test("requires the token to be supplied as a Worker secret", async () => {
  await assert.rejects(
    checkAndDispatch({}, async () => response({ workflow_runs: [] }), NOW),
    /PITCHIQ_GITHUB_TOKEN secret is missing/,
  );
});
