// Shared by the functions (files starting with "_" are not routes). One host serves every rater's study, each at
// /<study id>/; the kit's page posts to /api/submit, so the submission is passed to its own study's handler, which
// validates it exactly as the kit does for a single study. The allowed origin comes from the environment, so this
// code names no address.
import { existsSync, readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { createKeepwarmHandler, createSubmitHandler, supabaseStore } from "blindpanel/server";

const PUBLIC = fileURLToPath(new URL("../public/", import.meta.url));

/** The staged studies: every folder under public/ that holds a study.json, sorted. */
export const studyIds = (root = PUBLIC) =>
  readdirSync(root, { withFileTypes: true })
    .filter((d) => d.isDirectory() && existsSync(join(root, d.name, "study.json")))
    .map((d) => d.name)
    .sort();

/** The site's origin from SITE_ORIGIN, plus this deployment's own origins on a preview (Vercel's system env). */
export function allowedOrigins(env) {
  if (!env.SITE_ORIGIN) throw new Error("SITE_ORIGIN must be set");
  const own = env.VERCEL_ENV === "preview"
    ? [env.VERCEL_URL, env.VERCEL_BRANCH_URL].filter(Boolean).map((h) => `https://${h}`)
    : [];
  return [env.SITE_ORIGIN, ...own];
}

const fail = (status, error) =>
  new Response(JSON.stringify({ error }), { status, headers: { "content-type": "application/json", "cache-control": "no-store" } });

export function handlers(env, { store, root = PUBLIC } = {}) {
  const origins = allowedOrigins(env);
  if (!store) {
    if (!env.SUPABASE_URL || !env.SUPABASE_SECRET_KEY) throw new Error("SUPABASE_URL and SUPABASE_SECRET_KEY must be set");
    store = supabaseStore({ url: env.SUPABASE_URL, key: env.SUPABASE_SECRET_KEY });
  }
  const ids = studyIds(root);
  const submitters = {};
  for (const id of ids) {
    const study = JSON.parse(readFileSync(join(root, id, "study.json"), "utf8"));
    if (study.id !== id) throw new Error(`public/${id}/study.json is study ${study.id}`);
    submitters[id] = createSubmitHandler({ study, store, allowedOrigins: origins });
  }
  return {
    async submit(req) {
      let id;
      try {
        id = (await req.clone().json())?.study;
      } catch {
        return fail(400, "body is not JSON");
      }
      if (typeof id !== "string" || !Object.hasOwn(submitters, id)) return fail(404, "unknown study");
      return submitters[id](req);
    },
    keepwarm: createKeepwarmHandler({ store, secret: env.CRON_SECRET, study: ids[0] }),
  };
}
