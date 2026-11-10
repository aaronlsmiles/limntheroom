import { useCallback, useEffect, useMemo, useState } from "react";
import { dataBase, loadSketch, type Sketch } from "./lib/data";
import { parseParams, type View } from "./lib/params";
import { clock, describe, keptPercent, summarise } from "./lib/seam";
import { prefersReducedMotion, useTheme } from "./lib/theme";
import { usePlayer } from "./lib/useFrameClock";
import { clampWipe } from "./lib/wipe";
import { Segmented } from "./ui/Segmented";
import { Stage } from "./ui/Stage";
import { Timeline } from "./ui/Timeline";

declare global {
  interface Window { __limn?: { seek: (n: number) => Promise<void>; setWipe: (x: number) => void; frames: number } }
}

export function App() {
  const [sketch, setSketch] = useState<Sketch | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { loadSketch(dataBase(window.location.search)).then(setSketch, (e) => setError(String(e?.message ?? e))); }, []);
  if (error) return <main className="page"><p role="alert">The sketch data did not load: {error}</p></main>;
  if (!sketch) return <main className="page"><p className="muted" role="status">Loading the sketch</p></main>;
  return <Shell sketch={sketch} />;
}

function Shell({ sketch }: { sketch: Sketch }) {
  const { meta, seam } = sketch;
  const params = useMemo(() => parseParams(window.location.search, meta.frames), [meta.frames]);
  const reduced = useMemo(prefersReducedMotion, []);
  const startPaused = reduced || params.pause || params.capture;
  const startFrame = params.frame ?? (startPaused ? Math.round(5.0 * meta.fps) : null);
  const player = usePlayer({ fps: meta.fps, nFrames: meta.frames, clipKey: "sketch", autoplay: !startPaused });
  const { frame, playing } = player;
  const [wipe, setWipe] = useState(params.wipe);
  const [view, setView] = useState<View>(params.view);
  const [overlay, setOverlay] = useState(params.overlay);
  const [theme, setTheme] = useTheme();
  const summary = useMemo(() => summarise(seam), [seam]);
  const counts = useMemo(() => seam.counts(frame), [seam, frame]);
  const nowPct = keptPercent(counts);

  // land on the requested frame once the clip can seek; loop when it ends
  const { a: videoA, seekFrame, play } = player;
  useEffect(() => {
    const v = videoA.current;
    if (!v) return;
    const land = () => { if (startFrame !== null) seekFrame(startFrame); };
    if (v.readyState >= 1) land(); else v.addEventListener("loadedmetadata", land, { once: true });
    const again = () => { if (!startPaused) { seekFrame(0); play(); } };
    v.addEventListener("ended", again);
    return () => { v.removeEventListener("loadedmetadata", land); v.removeEventListener("ended", again); };
  }, [videoA, seekFrame, play, startFrame, startPaused]);

  // capture hook for the promo stills and loop (?capture=1): seek and wait for both frames to be presented
  const { b: videoB } = player;
  useEffect(() => {
    if (!params.capture) return;
    const presented = (v: HTMLVideoElement | null) => new Promise<void>((res) => {
      const vv = v as (HTMLVideoElement & { requestVideoFrameCallback?: (cb: () => void) => number }) | null;
      if (!vv) return res();
      let done = false;
      const fin = () => { if (!done) { done = true; res(); } };
      vv.requestVideoFrameCallback?.(fin);
      vv.addEventListener("seeked", () => setTimeout(fin, 30), { once: true });
      setTimeout(fin, 700);
    });
    window.__limn = {
      frames: meta.frames,
      setWipe: (x) => setWipe(clampWipe(x)),
      seek: async (n) => {
        const w = Promise.all([presented(videoA.current), presented(videoB.current)]);
        seekFrame(n);
        await w;
        await new Promise<void>((r) => requestAnimationFrame(() => requestAnimationFrame(() => r())));
      },
    };
    return () => { delete window.__limn; };
  }, [params.capture, meta.frames, videoA, videoB, seekFrame]);

  const step = useCallback((d: number) => player.step(d), [player]);
  const fps = meta.fps;
  const cues = meta.cues;
  const nowT = (frame + 0.5) / fps;
  const isNow = (c: (typeof cues)[number]) => (c.t_end !== undefined ? nowT >= c.t && nowT < c.t_end : nowT >= c.t && nowT < c.t + 0.5);

  const rows = useMemo(() => Array.from({ length: Math.floor(meta.frames / fps) }, (_, s) => ({ s, p: summary.pct[s * fps] })), [meta.frames, fps, summary]);

  return (
    <>
      <header className="bar">
        <a className="brand" href="/" aria-label="Limn the Room, seam view sketch">
          <svg className="mark" viewBox="0 0 20 20" aria-hidden="true"><rect x="1.5" y="3.5" width="17" height="13" fill="none" stroke="currentColor" strokeWidth="1.6" /><rect x="10" y="3.5" width="8.5" height="13" fill="#c4922a" opacity=".85" /><path d="M10 3.5v13" stroke="currentColor" strokeWidth="1.6" /></svg>
          <span>Limn the Room</span>
        </a>
        <button type="button" className="btn" onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
          aria-label={`Switch to the ${theme === "dark" ? "paper (light)" : "ink (dark)"} theme`}>
          {theme === "dark" ? "Paper theme" : "Ink theme"}
        </button>
      </header>
      <main className="page">
        <div className="head">
          <div>
            <h1>The seam view</h1>
            <p className="muted sub">Take under render. Gold where the room was kept, hatching where it was limned.</p>
          </div>
          <p className="chip" data-testid="synthetic-label"><span className="chip-dot" aria-hidden="true" />{meta.label}</p>
        </div>

        <div className="grid">
          <div className="col-main">
            <Stage sketch={sketch} player={player} frame={frame} wipe={wipe} onWipe={(x) => setWipe(clampWipe(x))} view={view} overlay={overlay} />

            <div className="transport">
              <button type="button" className="btn" onClick={player.toggle}>{playing ? "Pause" : "Play"}</button>
              <button type="button" className="btn btn-sq" onClick={() => step(-1)} aria-label="Back one frame">&#9664;</button>
              <button type="button" className="btn btn-sq" onClick={() => step(1)} aria-label="Forward one frame">&#9654;</button>
              <span className="num mono clock" data-testid="clock">{clock(frame / fps)}<span className="faint"> / {clock(meta.frames / fps)}</span></span>
              <div className="transport-end">
                <Segmented label="View" hideLabel value={view} onChange={setView}
                  options={[{ value: "wipe", label: "Wipe" }, { value: "take", label: "Take" }, { value: "render", label: "Render" }]} />
                <Segmented label="Overlay" hideLabel value={overlay ? "on" : "off"} onChange={(v) => setOverlay(v === "on")}
                  options={[{ value: "on", label: "Overlay on" }, { value: "off", label: "Overlay off" }]} />
              </div>
            </div>

            <section className="panel" aria-labelledby="tl-h">
              <h2 id="tl-h" className="visually-hidden">Timeline</h2>
              <Timeline meta={meta} summary={summary} frame={frame} onSeek={player.seekFrame} onStep={step} />
              <ul className="cues" aria-label="Cues">
                {cues.map((c) => (
                  <li key={c.id}>
                    <button type="button" className={`cue${isNow(c) ? " is-now" : ""}`} aria-current={isNow(c) ? "true" : undefined}
                      onClick={() => player.seekFrame(Math.round(c.t * fps))}>
                      <span className="cue-label">{c.label}</span>
                      <span className="mono num faint">{c.t_end !== undefined ? `${clock(c.t)}\u2013${clock(c.t_end)}` : clock(c.t)}</span>
                    </button>
                  </li>
                ))}
              </ul>
            </section>
          </div>

          <aside className="col-side">
            <section className="panel" aria-labelledby="lg-h">
              <h2 id="lg-h">Legend</h2>
              <ul className="legend">
                <li><span className="sw sw-kept" aria-hidden="true" /><span><strong>kept</strong><span className="muted"> the room as filmed</span></span></li>
                <li><span className="sw sw-limned" aria-hidden="true" /><span><strong>limned</strong><span className="muted"> redrawn by the render</span></span></li>
                <li><span className="sw sw-creature" aria-hidden="true" /><span><strong>not scored</strong><span className="muted"> where the ink creature is</span></span></li>
              </ul>
              <p className="gloss"><em>limn</em>: to draw. <span className="muted">From the illuminators, who drew in ink and gold.</span></p>
            </section>

            <section className="panel" aria-labelledby="rd-h">
              <h2 id="rd-h">Room kept</h2>
              <p className="big num" data-testid="kept-now" aria-live="off">{nowPct === null ? "none" : `${nowPct.toFixed(0)}%`}</p>
              <p className="small muted num">
                at {clock(nowT)}: {counts.kept} kept, {counts.limned} limned, {counts.creature} not scored
              </p>
              <p className="eq" data-testid="text-equivalent">{describe(summary, fps)}</p>
              <details className="table">
                <summary>Kept by second, as a table</summary>
                <table>
                  <caption className="visually-hidden">Share of cells kept at each second of the take</caption>
                  <thead><tr><th scope="col">Time</th><th scope="col" className="r">Kept</th></tr></thead>
                  <tbody>
                    {rows.map((r) => (
                      <tr key={r.s}><th scope="row" className="mono num">{clock(r.s)}</th><td className="r num">{r.p === null ? "none" : `${r.p.toFixed(0)}%`}</td></tr>
                    ))}
                  </tbody>
                </table>
              </details>
            </section>

            <section className="panel note" aria-labelledby="nt-h">
              <h2 id="nt-h">What this is</h2>
              <p className="small">{meta.note}</p>
            </section>
          </aside>
        </div>
      </main>
    </>
  );
}
