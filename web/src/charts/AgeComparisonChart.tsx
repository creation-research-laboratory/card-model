/**
 * The relationship between true age and apparent age, in either direction.
 *
 * Mirrors `card.plotting.plot_age_comparison`. Two series, so a legend is
 * always present: the CARD model, and the constant-rate reference where
 * apparent equals true. The gap between them is the whole claim.
 *
 * TWO ORIENTATIONS, because there are two questions and they are not the same
 * question:
 *
 *   "apparent"  — true age on x, apparent age on y. Both logarithmic. This is
 *                 the model's forward map and the package's own figure.
 *   "true"      — apparent age on x, true age on y, **y descending**. This is
 *                 the question a reader usually arrives with: they have a
 *                 published radiometric age and want the young-earth date. The
 *                 descending y axis puts recent at the top, the way a
 *                 stratigraphic column is drawn.
 *
 * The curve has a *kink* at the Flood, not a step: `forward_age` is the
 * integral of a bounded rate and so is continuous. The step belongs to λ(t).
 */

import { useMemo, useRef, useState } from "react";
import { scaleLinear, scaleLog } from "d3-scale";

import { DEFAULT_MARGIN, linearTicks, logDecadeTicks, nearestIndex, polyline } from "./axes.js";
import { formatAge, formatAgeTick, significantFor } from "./format.js";
import type { Calibration, Series } from "../model/types.js";

/** Which quantity the vertical axis carries. */
export type AgeOrientation = "apparent" | "true";

interface Props {
  series: Series;
  calibration: Calibration;
  orientation: AgeOrientation;
  width?: number;
  height?: number;
}

export function AgeComparisonChart({
  series,
  calibration,
  orientation,
  width = 720,
  height = 380,
}: Props) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const [hover, setHover] = useState<{ index: number; left: number; top: number } | null>(null);
  const swapped = orientation === "true";
  // The descending linear axis needs room for its title; the log one does not.
  const m = DEFAULT_MARGIN;
  const innerW = width - m.left - m.right;
  const innerH = height - m.top - m.bottom;

  const view = useMemo(() => {
    // Log scales reject zero, and the grid deliberately includes a 0 row.
    const trueAges: number[] = [];
    const secularAges: number[] = [];
    for (let i = 0; i < series.trueAge.length; i++) {
      if (series.trueAge[i] > 0 && series.secularAge[i] > 0) {
        trueAges.push(series.trueAge[i]);
        secularAges.push(series.secularAge[i]);
      }
    }
    const trueMax = calibration.chronology.ageOfEarth;
    const secularMax = Math.max(...secularAges, calibration.maxSecularAge);

    if (swapped) {
      // Apparent age spans eight decades, so x must be log. True age spans a
      // few thousand years, so y is linear — and runs downward, oldest at the
      // bottom.
      return {
        xs: secularAges,
        ys: trueAges,
        x: scaleLog().domain([1, secularMax]).range([0, innerW]).clamp(true),
        y: scaleLinear().domain([0, trueMax]).range([0, innerH]),
        xTicks: withEndpoint(logDecadeTicks(1, secularMax, 7), secularMax),
        yTicks: linearTicks(0, trueMax, 6),
        xTitle: "Apparent age (yr)",
        yTitle: "True age (years before present)",
        xFormat: formatAgeTick,
        yFormat: formatAgeTick,
      };
    }
    return {
      xs: trueAges,
      ys: secularAges,
      x: scaleLog().domain([1, trueMax]).range([0, innerW]).clamp(true),
      y: scaleLog().domain([1, secularMax]).range([innerH, 0]).clamp(true),
      xTicks: withEndpoint(logDecadeTicks(1, trueMax, 6), trueMax),
      yTicks: logDecadeTicks(1, secularMax, 7),
      xTitle: "True age (years before present)",
      yTitle: "Apparent age (yr)",
      xFormat: formatAgeTick,
      yFormat: formatAgeTick,
    };
  }, [series, calibration, innerW, innerH, swapped]);

  const { xs, ys, x, y } = view;
  const plottable = (a: number, b: number) => a > 0 && b >= 0;

  const modelPath = polyline(xs, ys, x, y, plottable);

  // The constant-rate baseline: apparent age equals true age, by definition.
  // Sampled rather than drawn as two endpoints, because in the swapped
  // orientation (log x, linear y) the identity is a curve, not a straight line.
  const referencePath = useMemo(() => {
    const limit = calibration.chronology.ageOfEarth;
    const points: number[] = [];
    const steps = 160;
    for (let i = 0; i <= steps; i++) {
      points.push(10 ** ((i / steps) * Math.log10(limit)));
    }
    return polyline(points, points, x, y, plottable);
  }, [calibration, x, y]);

  function onMove(event: React.PointerEvent<SVGSVGElement>) {
    const rect = event.currentTarget.getBoundingClientRect();
    // The SVG scales to its container, so client pixels must be converted back
    // into view-box units before they mean anything to the scales.
    const scale = rect.width / width;
    const localX = (event.clientX - rect.left) / scale - m.left;
    if (localX < 0 || localX > innerW) return setHover(null);
    const index = nearestIndex(xs, x.invert(localX));
    if (index < 0) return setHover(null);
    setHover({
      index,
      left: (m.left + x(xs[index])) * scale,
      top: (m.top + y(ys[index])) * scale,
    });
  }

  const digits = significantFor(series.exact);
  const point = hover
    ? {
        trueAge: swapped ? ys[hover.index] : xs[hover.index],
        secularAge: swapped ? xs[hover.index] : ys[hover.index],
      }
    : null;

  const constraintAt = (trueAge: number, secularAge: number) =>
    swapped ? { cx: x(secularAge), cy: y(trueAge) } : { cx: x(trueAge), cy: y(secularAge) };

  return (
    <figure className="chart">
      <figcaption>
        <h3>{swapped ? "True age vs. apparent age" : "Apparent age vs. true age"}</h3>
        <p>
          {swapped ? (
            <>
              What young-earth age a published radiometric age corresponds to
              under this calibration. Apparent age is logarithmic; true age runs
              downward, most recent at the top.
            </>
          ) : (
            <>
              How old rock of a given true age appears under this calibration.
              Both axes logarithmic; ages are years before present.
            </>
          )}
        </p>
      </figcaption>

      <div className="chart-wrap" ref={wrapRef}>
        <svg
          className="chart-svg"
          viewBox={`0 0 ${width} ${height}`}
          role="img"
          aria-label={
            swapped
              ? `True age against apparent age. An apparent age of ` +
                `${formatAge(calibration.maxSecularAge)} corresponds to the oldest ` +
                `true age the model allows, ${formatAge(calibration.chronology.ageOfEarth)}.`
              : `Apparent age against true age. The model reaches ` +
                `${formatAge(calibration.maxSecularAge)} apparent at ` +
                `${formatAge(calibration.chronology.ageOfEarth)} true.`
          }
          onPointerMove={onMove}
          onPointerLeave={() => setHover(null)}
        >
          <g transform={`translate(${m.left},${m.top})`}>
            {view.yTicks.map((t) => (
              <g key={`y${t}`} transform={`translate(0,${y(t)})`}>
                <line className="grid-line" x1={0} x2={innerW} />
                <text className="axis-label" x={-8} dy="0.32em" textAnchor="end">
                  {view.yFormat(t)}
                </text>
              </g>
            ))}
            {view.xTicks.map((t) => (
              <g key={`x${t}`} transform={`translate(${x(t)},0)`}>
                <line className="grid-line" y1={0} y2={innerH} />
                <text className="axis-label" y={innerH + 16} textAnchor="middle">
                  {view.xFormat(t)}
                </text>
              </g>
            ))}
            <line className="axis-line" x1={0} y1={innerH} x2={innerW} y2={innerH} />

            <path
              d={referencePath} fill="none" stroke="var(--series-2)"
              strokeWidth={2} strokeLinecap="round" strokeLinejoin="round"
            />
            <path
              d={modelPath} fill="none" stroke="var(--series-1)"
              strokeWidth={2} strokeLinecap="round" strokeLinejoin="round"
            />

            {/* Calibration anchors, with a 2px surface ring so they stay
                legible where they sit on the line. */}
            {calibration.constraints.map((c) => {
              if (!(c.trueAge > 0 && c.secularAge > 0)) return null;
              const { cx, cy } = constraintAt(c.trueAge, c.secularAge);
              return (
                <g key={c.label} transform={`translate(${cx},${cy})`}>
                  <circle r={5} fill="var(--series-1)"
                          stroke="var(--surface-2)" strokeWidth={2} />
                  <title>
                    {`${c.label}: ${formatAge(c.trueAge)} true → ${formatAge(c.secularAge)} apparent`}
                  </title>
                </g>
              );
            })}

            {hover ? (
              <g>
                <line
                  className="axis-line"
                  x1={x(xs[hover.index])} y1={0}
                  x2={x(xs[hover.index])} y2={innerH}
                />
                <circle
                  cx={x(xs[hover.index])} cy={y(ys[hover.index])} r={4.5}
                  fill="var(--series-1)" stroke="var(--surface-2)" strokeWidth={2}
                />
              </g>
            ) : null}

            <text
              className="axis-title"
              transform={`translate(${-m.left + 12},${innerH / 2}) rotate(-90)`}
              textAnchor="middle"
            >
              {view.yTitle}
            </text>
            <text
              className="axis-title" x={innerW / 2} y={innerH + 32}
              textAnchor="middle"
            >
              {view.xTitle}
            </text>
          </g>
        </svg>

        {hover && point ? (
          <div
            className="tooltip"
            style={{
              left: `${hover.left + 12}px`,
              top: `${hover.top - 8}px`,
              transform: hover.left > width * 0.6
                ? "translateX(-100%) translateX(-24px)" : undefined,
            }}
          >
            <div className="tt-row">
              <span className="tt-key" style={{ background: "var(--series-1)" }} />
              apparent {series.exact ? "" : "≈ "}{formatAge(point.secularAge, digits)}
            </div>
            <div className="tt-row">
              <span className="tt-key" style={{ background: "var(--series-1)" }} />
              true {formatAge(point.trueAge, digits)}
            </div>
          </div>
        ) : null}
      </div>

      <div className="legend">
        <span className="legend-item">
          <span className="legend-key" style={{ background: "var(--series-1)" }} />
          CARD model
        </span>
        <span className="legend-item">
          <span className="legend-key" style={{ background: "var(--series-2)" }} />
          Constant rate (apparent = true)
        </span>
      </div>
    </figure>
  );
}

/**
 * Append the domain endpoint unless a decade already sits close to it.
 *
 * Decades alone leave a log axis looking unfinished: 1…6056 labels 1, 10, 100,
 * 1k and then stops, so a reader cannot see where it ends.
 */
function withEndpoint(decades: number[], limit: number): number[] {
  const last = decades[decades.length - 1] ?? 1;
  return limit / last > 2 ? [...decades, limit] : decades;
}
