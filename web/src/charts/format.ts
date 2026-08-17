/**
 * Number formatting for a chart whose axes span eight orders of magnitude.
 *
 * Secular ages run from single years to 5.4e8. Nothing readable comes out of a
 * single format, so ages carry their own unit — "11.5 kyr", "66 Myr" — the way
 * the literature quotes them.
 */

/** Format an age in years using the unit a geologist would use for it. */
export function formatAge(years: number, significant = 3): string {
  if (!Number.isFinite(years)) return "—";
  const abs = Math.abs(years);
  if (abs === 0) return "0";
  if (abs >= 1e9) return `${trim(years / 1e9, significant)} Gyr`;
  if (abs >= 1e6) return `${trim(years / 1e6, significant)} Myr`;
  if (abs >= 1e3) return `${trim(years / 1e3, significant)} kyr`;
  return `${trim(years, significant)} yr`;
}

/** Axis tick label: unit-suffixed but terser, since ticks sit close together. */
export function formatAgeTick(years: number): string {
  if (years === 0) return "0";
  const abs = Math.abs(years);
  if (abs >= 1e9) return `${trim(years / 1e9, 3)}G`;
  if (abs >= 1e6) return `${trim(years / 1e6, 3)}M`;
  if (abs >= 1e3) return `${trim(years / 1e3, 3)}k`;
  return trim(years, 3);
}

/** λ is a multiple of background and spans 1 → 3.2e6; powers of ten read best. */
export function formatMultiplier(value: number): string {
  if (!Number.isFinite(value)) return "—";
  if (value < 1000) return trim(value, 4);
  const exponent = Math.floor(Math.log10(value));
  const mantissa = value / 10 ** exponent;
  return Math.abs(mantissa - 1) < 5e-3
    ? `10^${exponent}`
    : `${trim(mantissa, 3)}×10^${exponent}`;
}

/**
 * A span of young-earth time, in whatever unit makes it legible.
 *
 * The geological column collapses across nine orders of magnitude under this
 * model — the Holocene lasts millennia while the Silurian lasts days — so a
 * single unit would render most rows as "0.03" or "0.0000008".
 */
export function formatDuration(years: number): string {
  if (!Number.isFinite(years) || years < 0) return "—";
  if (years >= 1) return `${trim(years, 4)} yr`;
  const days = years * 365.25;
  if (days >= 1) return `${trim(days, 3)} days`;
  const hours = days * 24;
  if (hours >= 1) return `${trim(hours, 3)} hours`;
  const minutes = hours * 60;
  if (minutes >= 1) return `${trim(minutes, 3)} min`;
  return `${trim(minutes * 60, 3)} s`;
}

/** A DATE — years after Day 1 of Creation. Always small, always plain. */
export function formatDate(date: number): string {
  return `${trim(date, 6)}`;
}

/** Significant-figure formatting without exponent noise for ordinary numbers. */
export function trim(value: number, significant: number): string {
  if (!Number.isFinite(value)) return "—";
  if (value === 0) return "0";
  const rounded = Number(value.toPrecision(significant));
  return Math.abs(rounded) >= 1e6 || (Math.abs(rounded) < 1e-3 && rounded !== 0)
    ? rounded.toExponential(Math.max(0, significant - 1))
    : String(rounded);
}

/**
 * Digits worth showing for a value from a given source.
 *
 * The precomputed layer interpolates to ~0.3% on a forward age, so quoting nine
 * digits from it would be inventing seven of them.
 */
export function significantFor(exact: boolean): number {
  return exact ? 6 : 3;
}
