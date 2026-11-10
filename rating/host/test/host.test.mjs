// The study host: one /api/submit for the five rater studies, each submission checked by its own study's handler.
import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, mkdirSync, copyFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { participantOrder } from "blindpanel";
import { memoryStore } from "blindpanel/server";
import { handlers, studyIds } from "../api/_lib.js";

const STUDIES = new URL("../../studies/", import.meta.url).pathname;     // the built studies (gitignored)
const ORIGIN = "https://rating.example";

function stage(ids) {
  const root = mkdtempSync(join(tmpdir(), "host-"));
  for (const id of ids) {
    mkdirSync(join(root, id));
    copyFileSync(join(STUDIES, id, "dist", "study.json"), join(root, id, "study.json"));
  }
  return root;
}

async function payload(root, id) {
  const study = (await import(join(root, id, "study.json"), { with: { type: "json" } })).default;
  const session = crypto.randomUUID();
  const o = await participantOrder(study, session);
  const answers = { baseline: Object.fromEntries(o.baseline.map((c) => [c, { q1b: 1, q2b: 1 }])),
                    clips: Object.fromEntries(o.clips.map((c) => [c, { q1: 1, q2: 1 }])) };
  return { format: "blindpanel/1", study: id, instrument: study.instrument, session,
           order: { baseline: o.baseline, clips: o.clips }, answers,
           delivery: { autoplay: true, keyboard: false, duration_s: 300, ui: "blindpanel@0.2.0" } };
}

const post = (body, origin = ORIGIN) => new Request("https://host.example/api/submit", {
  method: "POST", headers: { "content-type": "application/json", origin }, body: typeof body === "string" ? body : JSON.stringify(body) });

test("the staged study ids are the folders that hold a study.json", () => {
  assert.deepEqual(studyIds(stage(["rs-r1", "rs-r2"])), ["rs-r1", "rs-r2"]);
});

test("a submission goes to its own study's handler and is stored under that study", async () => {
  const root = stage(["rs-r1", "rs-r2"]);
  const store = memoryStore();
  const h = handlers({ SITE_ORIGIN: ORIGIN }, { store, root });
  const r = await h.submit(post(await payload(root, "rs-r2")));
  assert.equal(r.status, 200, await r.clone().text());
  const rows = await store.rows("rs-r2");
  assert.equal(rows.length, 1);
  assert.equal((await store.rows("rs-r1")).length, 0);
});

test("an unknown study, a body that is not JSON, and a foreign origin are refused", async () => {
  const root = stage(["rs-r1"]);
  const h = handlers({ SITE_ORIGIN: ORIGIN }, { store: memoryStore(), root });
  assert.equal((await h.submit(post({ study: "rs-r9" }))).status, 404);
  assert.equal((await h.submit(post("not json"))).status, 400);
  assert.equal((await h.submit(post(await payload(root, "rs-r1"), "https://elsewhere.example"))).status, 403);
});

test("the allowed origin comes only from the environment", () => {
  assert.throws(() => handlers({}, { store: memoryStore(), root: stage(["rs-r1"]) }), /SITE_ORIGIN/);
});

test("keepwarm needs the cron secret", async () => {
  const root = stage(["rs-r1"]);
  const h = handlers({ SITE_ORIGIN: ORIGIN, CRON_SECRET: "s3" }, { store: memoryStore(), root });
  assert.equal((await h.keepwarm(new Request("https://host.example/api/keepwarm"))).status, 401);
  const ok = await h.keepwarm(new Request("https://host.example/api/keepwarm", { headers: { authorization: "Bearer s3" } }));
  assert.equal(ok.status, 200);
});
