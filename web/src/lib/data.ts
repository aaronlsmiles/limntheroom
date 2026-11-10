import { Seam, type SeamMeta } from "./seam";

export type Sketch = { meta: SeamMeta; seam: Seam; base: string };

// ?data=rehearsal reads the end-to-end rehearsal (tools/rehearsal_to_web.py); the default is the sketch.
export function dataBase(search: string): string {
  return new URLSearchParams(search).get("data") === "rehearsal" ? "/rehearsal/" : "/sketch/";
}

export async function loadSketch(base = "/sketch/"): Promise<Sketch> {
  const mr = await fetch(`${base}seam.json`);
  if (!mr.ok) throw new Error(`seam.json: ${mr.status}`);
  const meta = (await mr.json()) as SeamMeta;
  const br = await fetch(`${base}${meta.seam.file}`);
  if (!br.ok) throw new Error(`${meta.seam.file}: ${br.status}`);
  const seam = new Seam(new Uint8Array(await br.arrayBuffer()), meta.cols, meta.rows, meta.frames);
  return { meta, seam, base };
}
