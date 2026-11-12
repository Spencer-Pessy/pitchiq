const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

const source = fs.readFileSync("sw.js", "utf8");

async function requestData({networkResponse, networkError, cachedResponse, path = "/pitchiq/data.json"}) {
  const handlers = {};
  const writes = [];
  let matchedKey = null;
  const cache = {
    async put(key, response) {
      writes.push({key, response});
    },
  };
  const caches = {
    async open() { return cache; },
    async match(key) {
      matchedKey = key;
      return cachedResponse || null;
    },
    async keys() { return []; },
    async delete() { return true; },
  };
  const context = {
    URL,
    Request,
    Response,
    caches,
    console,
    fetch: async () => {
      if (networkError) throw networkError;
      return networkResponse;
    },
    self: {
      location: {origin: "https://example.test"},
      registration: {scope: "https://example.test/pitchiq/"},
      clients: {claim: async () => {}},
      addEventListener(name, handler) { handlers[name] = handler; },
      skipWaiting() {},
    },
  };
  vm.runInNewContext(source, context, {filename: "sw.js"});
  let responsePromise;
  const request = new Request("https://example.test" + path + "?cacheBust=123");
  handlers.fetch({
    request,
    respondWith(value) { responsePromise = value; },
  });
  assert.ok(responsePromise, "data request should be intercepted");
  const response = await responsePromise;
  return {response, writes, matchedKey};
}

async function main() {
  const cached = new Response('{"updated":"old"}', {
    headers: {"Content-Type": "application/json"},
  });
  const httpError = await requestData({
    networkResponse: new Response("upstream error", {status: 503}),
    cachedResponse: cached,
  });
  assert.equal(httpError.response, cached, "HTTP errors should return the last good snapshot");
  assert.equal(httpError.matchedKey.url, "https://example.test/pitchiq/data.json");
  assert.equal(httpError.writes.length, 0, "HTTP errors must not overwrite the cache");

  const offline = await requestData({networkError: new Error("offline"), cachedResponse: cached});
  assert.equal(offline.response, cached, "network failures should return the last good snapshot");

  const fresh = new Response('{"updated":"new"}', {status: 200});
  const online = await requestData({networkResponse: fresh});
  assert.equal(online.response, fresh, "successful network responses should be returned");
  assert.equal(online.writes.length, 1, "successful data responses should refresh the cache");
  assert.equal(online.writes[0].key.url, "https://example.test/pitchiq/data.json");

  const noCache = await requestData({networkError: new Error("offline"), path: "/pitchiq/international.json"});
  assert.equal(noCache.response.status, 200, "missing offline data should return a safe JSON fallback");
  const fallback = await noCache.response.json();
  assert.deepEqual(fallback, {fixtures: []});

  console.log("Service-worker runtime tests passed.");
}

main().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
