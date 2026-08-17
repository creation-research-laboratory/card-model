/**
 * Two-way age conversion — the thing most readers actually arrive wanting.
 *
 * Type a published radiometric age and get the young-earth date, or the other
 * way round. Both directions are the same calibrated model: `forward_age` and
 * `inverse_age`, straight from `card`.
 *
 * One field is authoritative at a time — whichever was last edited — and the
 * other is derived. That matters because the conversion is a round trip through
 * an async worker: without it, a value typed into one box would be overwritten
 * mid-keystroke by the answer computed from the other.
 *
 * Errors are the package's own. `forward_age` and `inverse_age` reject
 * out-of-domain input with prose written for a human — it explains the AGE
 * convention, and names the oldest apparent age the model can produce and why.
 * Rewording that here would be strictly worse, so it is shown verbatim.
 */

import { useCallback, useEffect, useRef, useState } from "react";

import { formatAge, significantFor } from "../charts/format.js";

/** Which box the reader last typed in; the other is computed from it. */
type Side = "true" | "apparent";

interface Props {
  forward(trueAge: number): Promise<number>;
  inverse(secularAge: number): Promise<number>;
  /** False when answers are interpolated, so digits and the "≈" follow. */
  exact: boolean;
  /** Seeds the apparent field on first render — usually a boundary's age. */
  initialApparent: number;
  disabled?: boolean;
  debounceMs?: number;
}

/** Accepts `66e6`, `6.6e7`, `66000000`, and rejects the rest. */
function parse(text: string): number | null {
  const trimmed = text.trim().replace(/,/g, "");
  if (!trimmed) return null;
  const value = Number(trimmed);
  return Number.isFinite(value) ? value : NaN;
}

export function AgeConverter({
  forward, inverse, exact, initialApparent,
  disabled, debounceMs = 200,
}: Props) {
  // One authoritative text and one derived, rather than two editable states.
  // Holding both as peers meant the effect depended on the derived value too,
  // so writing an answer re-triggered the conversion that produced it — a
  // second round trip per keystroke, and ~1.6 s to settle instead of ~200 ms.
  const [side, setSide] = useState<Side>("apparent");
  const [input, setInput] = useState(String(initialApparent));
  const [derived, setDerived] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // Guards against an out-of-order answer landing after a newer one, which a
  // debounced async round trip makes easy to hit.
  const generation = useRef(0);

  const convert = useCallback(async (from: Side, text: string) => {
    const value = parse(text);
    const mine = ++generation.current;

    if (value === null) {
      setError(null);
      setDerived("");
      return;
    }
    if (Number.isNaN(value)) {
      setError(`"${text.trim()}" is not a number.`);
      setDerived("");
      return;
    }

    setBusy(true);
    try {
      const answer = from === "apparent" ? await inverse(value) : await forward(value);
      if (mine !== generation.current) return;
      setDerived(formatAge(answer, significantFor(exact)));
      setError(null);
    } catch (caught) {
      if (mine !== generation.current) return;
      // The package's own words — it explains the domain better than we could.
      setError(caught instanceof Error ? caught.message : String(caught));
      setDerived("");
    } finally {
      if (mine === generation.current) setBusy(false);
    }
  }, [forward, inverse, exact]);

  // Depends on the authoritative text only. `derived` is deliberately absent:
  // including it is what made writing an answer schedule another conversion.
  // `convert` changes when the calibration does, so moving a slider updates the
  // answer without the reader retyping it.
  useEffect(() => {
    const timer = setTimeout(() => void convert(side, input), debounceMs);
    return () => clearTimeout(timer);
  }, [side, input, convert, debounceMs]);

  // Only mark a value that exists; an empty field prefixed with "≈ " reads as
  // an answer of approximately nothing.
  const show = (text: string) => (text && !exact ? `≈ ${text}` : text);
  const edit = (from: Side) => (event: { target: { value: string } }) => {
    setSide(from);
    setInput(event.target.value);
  };

  return (
    <section className="panel" aria-labelledby="converter-heading">
      <h2 id="converter-heading">Convert an age</h2>

      <label className="field">
        <span>Apparent (radiometric) age, years</span>
        <input
          type="text"
          inputMode="decimal"
          value={side === "apparent" ? input : show(derived)}
          disabled={disabled}
          aria-describedby="converter-status"
          onChange={edit("apparent")}
        />
      </label>

      <div className="converter-arrow" aria-hidden="true">
        {side === "apparent" ? "↓" : "↑"}
      </div>

      <label className="field">
        <span>True age, years before present</span>
        <input
          type="text"
          inputMode="decimal"
          value={side === "true" ? input : show(derived)}
          disabled={disabled}
          aria-describedby="converter-status"
          onChange={edit("true")}
        />
      </label>

      <p id="converter-status" className="param-help" aria-live="polite">
        {error ? (
          <span className="converter-error">{error}</span>
        ) : busy ? (
          "converting…"
        ) : exact ? (
          "Computed by the model."
        ) : (
          "Interpolated from precomputed points — good to about 1%."
        )}
      </p>
    </section>
  );
}
