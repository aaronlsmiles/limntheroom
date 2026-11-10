// Copied from the StillDrawn Explorer (prototypes/stilldrawn-explorer/web/src/views/Explore/useFrameClock.ts), unchanged.
// One clock for the player: frame index from requestVideoFrameCallback (rAF fallback),
// frame-accurate seeks, and an optional second video slaved to the first (compare mode).
import { useCallback, useEffect, useRef, useState } from "react";

/** Frame index for a currentTime we set ourselves (mid-frame seeks). */
export const frameAt = (t: number, fps: number) => Math.floor(t * fps + 1e-3);
/** Frame index for a presented frame's media time (its timestamp is n / fps). */
export const frameOfMediaTime = (t: number, fps: number) => Math.round(t * fps);
/** Seek target for frame n: mid-frame, so the decoder lands on n. */
export const timeFor = (n: number, fps: number) => (n + 0.5) / fps;
export const wrap = (n: number, count: number) => ((n % count) + count) % count;

type VFC = (now: number, md: { mediaTime: number }) => void;
type VideoWithVFC = HTMLVideoElement & {
  requestVideoFrameCallback?: (cb: VFC) => number;
  cancelVideoFrameCallback?: (h: number) => void;
};

export function usePlayer({ fps, nFrames, clipKey, autoplay }: { fps: number; nFrames: number; clipKey: string; autoplay: boolean }) {
  const a = useRef<HTMLVideoElement>(null);
  const b = useRef<HTMLVideoElement>(null);
  const [frame, setFrame] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [rate, setRateState] = useState(1);
  const rateRef = useRef(rate);
  rateRef.current = rate;
  const frameRef = useRef(frame);
  frameRef.current = frame;

  const syncB = useCallback(() => {
    const A = a.current, B = b.current;
    if (!A || !B || B.readyState < 1) return;
    if (Math.abs(B.currentTime - A.currentTime) > 1 / fps) B.currentTime = A.currentTime;
  }, [fps]);

  // Track presented frames on A
  useEffect(() => {
    const v = a.current as VideoWithVFC | null;
    if (!v) return;
    setFrame(0);
    let handle = 0, raf = 0, stop = false;
    if (v.requestVideoFrameCallback) {
      const tick: VFC = (_now, md) => {
        if (stop) return;
        if (!v.paused) setFrame(Math.min(nFrames - 1, frameOfMediaTime(md.mediaTime, fps)));
        syncB();
        handle = v.requestVideoFrameCallback!(tick);
      };
      handle = v.requestVideoFrameCallback(tick);
    } else {
      const loop = () => {
        if (stop) return;
        if (!v.paused) setFrame(Math.min(nFrames - 1, frameAt(v.currentTime, fps)));
        syncB();
        raf = requestAnimationFrame(loop);
      };
      raf = requestAnimationFrame(loop);
    }
    const onPlay = () => setPlaying(true), onPause = () => setPlaying(false);
    v.addEventListener("play", onPlay);
    v.addEventListener("pause", onPause);
    return () => {
      stop = true;
      if (handle) v.cancelVideoFrameCallback?.(handle);
      if (raf) cancelAnimationFrame(raf);
      v.removeEventListener("play", onPlay);
      v.removeEventListener("pause", onPause);
    };
  }, [clipKey, fps, nFrames, syncB]);

  // Start (or not) when the clip changes
  useEffect(() => {
    const A = a.current, B = b.current;
    for (const v of [A, B]) if (v) v.playbackRate = rateRef.current;
    if (autoplay && A) {
      A.play().catch(() => setPlaying(false));
      B?.play().catch(() => undefined);
    }
  }, [clipKey, autoplay]);

  const play = useCallback(() => {
    a.current?.play().catch(() => setPlaying(false));
    b.current?.play().catch(() => undefined);
  }, []);
  const pause = useCallback(() => {
    a.current?.pause();
    b.current?.pause();
  }, []);
  const toggle = useCallback(() => (a.current?.paused ? play() : pause()), [play, pause]);

  const seekFrame = useCallback((n: number) => {
    const f = Math.max(0, Math.min(nFrames - 1, n));
    for (const v of [a.current, b.current]) if (v) v.currentTime = timeFor(f, fps);
    setFrame(f);
  }, [fps, nFrames]);

  const step = useCallback((d: number) => {
    pause();
    const f = wrap(frameRef.current + d, nFrames);
    for (const v of [a.current, b.current]) if (v) v.currentTime = timeFor(f, fps);
    frameRef.current = f;
    setFrame(f);
  }, [pause, fps, nFrames]);

  const setRate = useCallback((r: number) => {
    setRateState(r);
    for (const v of [a.current, b.current]) if (v) v.playbackRate = r;
  }, []);

  return { a, b, frame, playing, rate, play, pause, toggle, step, seekFrame, setRate };
}
export type Player = ReturnType<typeof usePlayer>;
