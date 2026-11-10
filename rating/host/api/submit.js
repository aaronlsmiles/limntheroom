// POST /api/submit: one rater's session, validated by its own study's handler; nothing personal is stored.
import { handlers } from "./_lib.js";

export const POST = (req) => handlers(process.env).submit(req);
