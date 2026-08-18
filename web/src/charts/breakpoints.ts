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
 *   * **Calibration anchors** — matched dates the curve was *fitted* to which
 *     are not breakpoints. The end of the Ice Age is one: nothing happens to
 *     lambda there, it is what pins `k_PF`. Drawing it like a breakpoint would
 *     claim a rate change the model does not have.
 *
 * Breakpoints are named from the constraints rather than from a list here.
 * That matters because the second breakpoint *is* the boundary the reader
 * picked: `t_F2` is the Flood/post-Flood contact, so it lands on K/Pg or N/Q
 * according to the preset, and a marker that just said "Flood ends" hid the
 * fact that the exponential changes at the boundary they chose.
 *
 * `t_c` is included only when it is a real transition. In the flood-only mode
 * `lambda_c` is pinned to background and `k_c` to zero, so the first two
 * regions are both flat background and `t_c` is a formal boundary where
 * nothing observable happens — marking it would be noise.
 */

import type { Calibration, Constraint, GeneralParams } from "../model/types.js";

export type MarkerKind = "rate" | "anchor";

export interface Marker {
  readonly key: string;
  /** AGE — years before present, which is what the chart axes use. */
  readonly trueAge: number;
  /** What happens here, in the model's terms. */
  readonly label: string;
  /** The geological contact this coincides with, when it still does. */
  readonly boundary?: string;
  /**
   * A contact this breakpoint was calibrated onto but has since been moved
   * off, by a parameter override. Set instead of `boundary`.
   */
  readonly displaced?: string;
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

/**
 * Split "Flood ends — Cretaceous-Paleogene (K/Pg)" into its two halves.
 *
 * The generator and the live source both build constraint labels as
 * `role — contact`, so the contact can be recovered rather than duplicated in
 * a table here that would drift from theirs.
 */
function splitConstraintLabel(label: string): { role: string; boundary?: string } {
  const parts = label.split("—").map((s) => s.trim()).filter(Boolean);
  if (parts.length < 2) return { role: label.trim() };
  return { role: parts[0], boundary: parts.slice(1).join(" — ") };
}

/** "Cretaceous-Paleogene (K/Pg)" → "K/Pg"; anything unparenthesised is kept. */
export function abbreviate(boundary: string): string {
  return boundary.match(/\(([^)]+)\)/)?.[1] ?? boundary;
}

/**
 * How far out of fit a constraint may be while still counting as "met".
 *
 * Residuals are `predicted / target - 1`. A solved calibration sits below
 * 1e-12, so anything above this is an override, not arithmetic noise.
 */
const CONTACT_TOLERANCE = 1e-6;

export function markersFor(calibration: Calibration): Marker[] {
  const p = calibration.params;
  const { ageOfEarth } = calibration.chronology;
  // Parameters are DATEs (years after Day 1); the axes are AGEs (years before
  // present). Getting this backwards is a documented past bug in the package,
  // so the conversion happens once, here.
  const age = (date: number) => ageOfEarth - date;

  const constraints: readonly Constraint[] = calibration.constraints ?? [];
  const claimed = new Set<Constraint>();

  /**
   * The constraint sitting on a breakpoint, if any.
   *
   * The tolerance has to be far below the Flood year, or `t_F` and `t_F2`
   * would both match the same pair.
   */
  const contactAt = (
    trueAge: number,
  ): { boundary?: string; displaced?: string } => {
    const i = constraints.findIndex(
      (c) => Math.abs(c.trueAge - trueAge) < 1e-6 * Math.max(1, Math.abs(trueAge)),
    );
    if (i < 0) return {};
    claimed.add(constraints[i]);
    const name = splitConstraintLabel(constraints[i].label).boundary;
    if (!name) return {};

    // A constraint is a *target*: its trueAge never moves. Whether the model
    // still puts the contact there is a different question, and once a slider
    // breaks the fit the answer is no -- raising lambda_F by a factor of three
    // walks the K/Pg contact ~200 years off t_F2 while the constraint stays at
    // 4399. Claiming the contact regardless would label the marker with a
    // boundary the model no longer places there.
    const residual = calibration.residuals?.[i];
    const met = residual === undefined || Math.abs(residual) < CONTACT_TOLERANCE;
    return met ? { boundary: name } : { displaced: name };
  };

  const markers: Marker[] = [];

  if (p.lambda_c > p.lambda_bg || p.k_c > 0) {
    const trueAge = age(p.t_c);
    markers.push({
      key: "t_c",
      trueAge,
      label: "Creation week ends",
      ...contactAt(trueAge),
      kind: "rate",
      detail:
        `λ leaves its initial ${say(p.lambda_c)}× and begins relaxing toward ` +
        `background at k_c = ${say(p.k_c)}/yr.`,
    });
  }

  const floodStart = age(p.t_F);
  markers.push({
    key: "t_F",
    trueAge: floodStart,
    label: "Flood begins",
    ...contactAt(floodStart),
    kind: "rate",
    detail:
      `λ jumps to ${say(p.lambda_F)}× background and starts falling at ` +
      `k_F = ${say(p.k_F)}/yr. This is the only point where λ is discontinuous.`,
  });

  const floodEnd = age(p.t_F2);
  const endContact = contactAt(floodEnd);
  markers.push({
    key: "t_F2",
    trueAge: floodEnd,
    label: "Flood ends",
    ...endContact,
    kind: "rate",
    detail:
      `λ is continuous here — it has already fallen to ${say(lambdaF2(p))}× — ` +
      `but the relaxation constant switches from k_F = ${say(p.k_F)} to ` +
      `k_PF = ${say(p.k_PF)}/yr, which governs the millennia after.` +
      (endContact.boundary
        ? ` This is the ${endContact.boundary} contact.`
        : endContact.displaced
          ? ` The ${endContact.displaced} contact no longer falls here: the ` +
            "parameters have been changed, so the model now places it elsewhere."
          : ""),
  });

  // Whatever the fit used that is not a breakpoint. Derived rather than
  // hardcoded, so a fourth pair would appear here without a code change.
  for (const c of constraints) {
    if (claimed.has(c)) continue;
    const { role, boundary } = splitConstraintLabel(c.label);
    const residual = calibration.residuals?.[constraints.indexOf(c)];
    const met = residual === undefined || Math.abs(residual) < CONTACT_TOLERANCE;
    markers.push({
      key: `anchor:${c.label}`,
      trueAge: c.trueAge,
      label: role,
      ...(boundary ? (met ? { boundary } : { displaced: boundary }) : {}),
      kind: "anchor",
      detail:
        "A calibration anchor, not a rate change: nothing happens to λ here. " +
        `It is one of the ${constraints.length} matched dates, and what it ` +
        "pins is k_PF.",
    });
  }

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
