import { useEffect, useState } from "react";

type Theme = "light" | "dark";
const systemTheme = (): Theme => (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");

/** Follows the system until the reader picks a theme; only an explicit pick is stored. */
export function useTheme() {
  const [picked, setPicked] = useState<Theme | null>(() => (document.documentElement.dataset.theme as Theme) || null);
  const [system, setSystem] = useState<Theme>(systemTheme);
  useEffect(() => {
    const mq = matchMedia("(prefers-color-scheme: dark)");
    const on = () => setSystem(mq.matches ? "dark" : "light");
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, []);
  const pick = (t: Theme) => {
    setPicked(t);
    document.documentElement.dataset.theme = t;
    try { localStorage.setItem("ltr-theme", t); } catch { /* storage may be unavailable */ }
  };
  return [picked ?? system, pick] as const;
}

export const prefersReducedMotion = () => matchMedia("(prefers-reduced-motion: reduce)").matches;
