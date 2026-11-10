// GET /api/keepwarm: Vercel Cron, daily, so the free database is not paused during the rating window.
import { handlers } from "./_lib.js";

export const GET = (req) => handlers(process.env).keepwarm(req);
