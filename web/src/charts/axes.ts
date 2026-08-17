/**
 * Axis helpers shared by both charts.
 *
 * d3-scale supplies the mapping; ticks are chosen here because d3's default log
 * ticks put a label on every 2,3,4…9 within a decade, which on an eight-decade
 * axis is unreadable. Decades only, thinned to fit.
 */

export interface Margin {
  top: number;
  right: number;
  bottom: number;
  left: number;
}

export const DEFAULT_MARGIN: Margin = { top: 8, right: 16, bottom: 38, left: 58 };

/**
 * Decade ticks inside [lo, hi], thinned so labels do not collide.
 *
 * `maxTicks` is the budget; the step grows to 2, 3… decades until the count
 * fits, so a 1→5.4e8 axis shows 10^0, 10^2, 10^4… rather than nine crowded
 * labels.
 */
export function logDecadeTicks(lo: number, hi: number, maxTicks = 8): number[] {
  if (!(lo > 0) || !(hi > lo)) return [];
  const first = Math.ceil(Math.log10(lo));
  const last = Math.floor(Math.log10(hi));
  if (last < first) return [lo, hi];

  const decades: number[] = [];
  for (let e = first; e <= last; e++) decades.push(e);

  const step = Math.max(1, Math.ceil(decades.length / maxTicks));
  return decades.filter((_, i) => i % step === 0).map((e) => 10 ** e);
}

/** Round linear ticks: 0, 1000, 2000… chosen from a 1/2/5 progression. */
export function linearTicks(lo: number, hi: number, maxTicks = 7): number[] {
  if (!(hi > lo)) return [lo];
  const span = hi - lo;
  const rough = span / maxTicks;
  const magnitude = 10 ** Math.floor(Math.log10(rough));
  const normalized = rough / magnitude;
  const step =
    (normalized <= 1 ? 1 : normalized <= 2 ? 2 : normalized <= 5 ? 5 : 10) * magnitude;

  const ticks: number[] = [];
  for (let v = Math.ceil(lo / step) * step; v <= hi + step * 1e-9; v += step) {
    ticks.push(Number(v.toPrecision(12)));
  }
  return ticks;
}

/**
 * Build an SVG path from parallel arrays, skipping non-plottable points.
 *
 * Hand-rolled rather than `d3-shape`'s line generator because the log scales
 * reject zero and negatives, and a `defined` predicate plus a generator is more
 * machinery than a loop for two charts.
 */
export function polyline(
  xs: readonly number[],
  ys: readonly number[],
  sx: (v: number) => number,
  sy: (v: number) => number,
  isPlottable: (x: number, y: number) => boolean,
): string {
  let path = "";
  let pen: "M" | "L" = "M";
  for (let i = 0; i < xs.length; i++) {
    const x = xs[i];
    const y = ys[i];
    if (!isPlottable(x, y)) {
      pen = "M";
      continue;
    }
    path += `${pen}${sx(x).toFixed(2)},${sy(y).toFixed(2)}`;
    pen = "L";
  }
  return path;
}

/** Index of the array entry closest to `value`, for crosshair snapping. */
export function nearestIndex(values: readonly number[], value: number): number {
  if (values.length === 0) return -1;
  let lo = 0;
  let hi = values.length - 1;
  while (hi - lo > 1) {
    const mid = (lo + hi) >> 1;
    if (values[mid] <= value) lo = mid;
    else hi = mid;
  }
  return Math.abs(values[lo] - value) <= Math.abs(values[hi] - value) ? lo : hi;
}
