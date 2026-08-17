/**
 * The instants worth marking on a time axis, derived from the calibration.
 *
 * Two different kinds of thing get marked, and conflating them would be a
 * factual error rather than a presentational one:
 *
 *   * **Rate changes** — the DATEs where `lambda_func` changes character.
 *     `GeneralModel.breakpoints()` names exactly three: `t_c`, `t_F`, `t_F2`.
 *     At `t_F` the rate jumps; at `t_F2` it does not jump at all, but the
 *     constant governing its relaxation switches from `k_F` to `k_PF`.
 *   * **Calibration anchors** — the matched dates the curve was *fitted* to.
 *     The end of the Ice Age is one of these. Nothing happens to lambda there;
 *     it is the third constraint that pins the post-Flood relaxation. Drawing
 *     it in the same style as a breakpoint would claim a rate change the model
 *     does not have.
 *
 * `t_c` is included only when it is a real transition. In the flood-only mode
 * `lambda_c` is pinned to background and `k_c` to zero, so the first two
 * regions are both flat background and `t_c` is a formal boundary where
 * nothing observable happens — marking it would be noise.
 */

import type { Calibration, GeneralParams } from "../model/types.js";

export type MarkerKind = "rate" | "anchor";

export interface Marker {
  readonly key: string;
  /** AGE — years before present, which is what the chart axes use. */
  readonly trueAge: number;
  readonly label: string;
  readonly kind: MarkerKind;
  /** One line saying what changes here, for a tooltip or caption. */
  readonly detail: string;
}

/**
 * Lambda at the end of the Flood.
 *
 * A read-only property on `GeneralModelParams`, reproduced here because the
 * dataclass omits it from `to_dict` (it would not round-trip). Continuity at
 * `t_F2` pins it, and the floored form is what makes it >= background.
 */
export function lambdaF2(p: GeneralParams): number {
  return (p.lambda_F - p.lambda_bg) * Math.exp(-p.k_F * (p.t_F2 - p.t_F))
    + p.lambda_bg;
}

/** Compact multiplier for prose — `4.53×10^9`, not `4530000000`. */
function say(value: number): string {
  if (value === 0) return "0";
  if (Math.abs(value) >= 1e4 || Math.abs(value) < 1e-3) {
    const exp = Math.floor(Math.log10(Math.abs(value)));
    const mantissa = value / 10 ** exp;
    return `${mantissa.toFixed(2)}×10^${exp}`;
  }
  return String(Number(value.toPrecision(4)));
}

export function markersFor(calibration: Calibration): Marker[] {
  const p = calibration.params;
  const { ageOfEarth } = calibration.chronology;
  // Parameters are DATEs (years after Day 1); the axes are AGEs (years before
  // present). Getting this backwards is a documented past bug in the package,
  // so the conversion happens once, here.
  const age = (date: number) => ageOfEarth - date;

  const markers: Marker[] = [];

  const creationWeekActive = p.lambda_c > p.lambda_bg || p.k_c > 0;
  if (creationWeekActive) {
    markers.push({
      key: "t_c",
      trueAge: age(p.t_c),
      label: "Creation week ends",
      kind: "rate",
      detail:
        `λ leaves its initial ${say(p.lambda_c)}× and begins relaxing toward ` +
        `background at k_c = ${say(p.k_c)}/yr.`,
    });
  }

  markers.push({
    key: "t_F",
    trueAge: age(p.t_F),
    label: "Flood begins",
    kind: "rate",
    detail:
      `λ jumps to ${say(p.lambda_F)}× background and starts falling at ` +
      `k_F = ${say(p.k_F)}/yr. This is the only point where λ is discontinuous.`,
  });

  markers.push({
    key: "t_F2",
    trueAge: age(p.t_F2),
    label: "Flood ends",
    kind: "rate",
    detail:
      `λ is continuous here — it has already fallen to ${say(lambdaF2(p))}× — ` +
      `but the relaxation constant switches from k_F = ${say(p.k_F)} to ` +
      `k_PF = ${say(p.k_PF)}/yr, which governs the millennia after.`,
  });

  markers.push({
    key: "ice_age_end",
    trueAge: age(calibration.chronology.iceAgeEndDate),
    label: "Ice Age ends",
    kind: "anchor",
    detail:
      "A calibration anchor, not a rate change: nothing happens to λ here. " +
      "It is the third matched date, and what it pins is k_PF.",
  });

  return markers;
}

/**
 * Group markers that would land on top of each other.
 *
 * Not a nicety. The Flood lasts one year on an axis spanning millennia — at a
 * typical 596 px over 4500 yr that is 0.13 px — so `t_F` and `t_F2` always
 * resolve to the same pixel. Drawing two lines there would render one visible
 * mark while implying two were checked.
 *
 * @param toPixel maps a true age to an x coordinate
 * @param minGap  pixels below which two marks are treated as one
 */
export function groupMarkers(
  markers: readonly Marker[],
  toPixel: (trueAge: number) => number,
  minGap = 6,
): Array<{ markers: Marker[]; from: number; to: number }> {
  const placed = markers
    .map((m) => ({ marker: m, px: toPixel(m.trueAge) }))
    .sort((a, b) => a.px - b.px);

  const groups: Array<{ markers: Marker[]; from: number; to: number }> = [];
  for (const { marker, px } of placed) {
    const last = groups[groups.length - 1];
    if (last && px - last.to <= minGap) {
      last.markers.push(marker);
      last.to = Math.max(last.to, px);
    } else {
      groups.push({ markers: [marker], from: px, to: px });
    }
  }
  return groups;
}
