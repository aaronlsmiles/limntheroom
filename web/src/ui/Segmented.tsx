// Copied from the StillDrawn Explorer (prototypes/stilldrawn-explorer/web/src/ui/Segmented.tsx), unchanged.
import { useId } from "react";

/** A native radio group drawn as a segmented control. */
export function Segmented<T extends string>({
  label, value, options, onChange, hideLabel = false, className = "",
}: {
  label: string; value: T; options: { value: T; label: string; disabled?: boolean }[];
  onChange: (v: T) => void; hideLabel?: boolean; className?: string;
}) {
  const name = useId();
  return (
    <fieldset className={`seg ${className}`}>
      <legend className={hideLabel ? "visually-hidden" : "seg-label"}>{label}</legend>
      <div className="seg-track">
        {options.map((o) => (
          <label key={o.value} className={`seg-opt${o.value === value ? " is-on" : ""}${o.disabled ? " is-off" : ""}`}>
            <input type="radio" name={name} value={o.value} checked={o.value === value} disabled={o.disabled}
              onChange={() => onChange(o.value)} />
            <span>{o.label}</span>
          </label>
        ))}
      </div>
    </fieldset>
  );
}
