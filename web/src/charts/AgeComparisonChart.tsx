/**
 * Apparent (secular) age against true age — the headline figure.
 *
 * Mirrors `card.plotting.plot_age_comparison`. Two series, so a legend is
 * always present: the CARD model, and the constant-rate reference where
 * apparent equals true. The gap between them is the whole claim.
 *
 * Both axes are logarithmic. True age spans 1 → ~6,000 years and apparent age
 * 1 → 5.4e8; on linear axes the entire pre-Flood story collapses into the top
 * pixel row.
 *
 * Note the curve has a *kink* at the Flood, not a step: `forward_age` is the
 * integral of a bounded rate and so is continuous. The step belongs to λ(t).
 */

import { useMemo, useRef, useState } from "react";
import { scaleLog } from "d3-scale";

import { DEFAULT_MARGIN, logDecadeTicks, nearestIndex, polyline } from "./axes.js";
import { formatAge, formatAgeTick, significantFor } from "./format.js";
import type { Calibration, Series } from "../model/types.js";

interface Props {
  series: Series;
  calibration: Calibration;
  width?: number;
  height?: number;
}

interface HoverState {
  index: number;
  left: number;
  top: number;
}

export function AgeComparisonChart({
  series,
  calibration,
  width = 720,
  height = 380,
}: Props) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const [hover, setHover] = useState<HoverState | null>(null);
  const m = DEFAULT_MARGIN;
  const innerW = width - m.left - m.right;
  const innerH = height - m.top - m.bottom;

  const view = useMemo(() => {
    // Log scales reject zero, and the grid deliberately includes a 0 row.
    const xs: number[] = [];
    const ys: number[] = [];
    for (let i = 0; i < series.trueAge.length; i++) {
      if (series.trueAge[i] > 0 && series.secularAge[i] > 0) {
        xs.push(series.trueAge[i]);
        ys.push(series.secularAge[i]);
      }
    }
    const xMax = calibration.chronology.ageOfEarth;
    const yMax = Math.max(...ys, calibration.maxSecularAge);
    const x = scaleLog().domain([1, xMax]).range([0, innerW]).clamp(true);
    const y = scaleLog().domain([1, yMax]).range([innerH, 0]).clamp(true);
    return { xs, ys, x, y, xMax, yMax };
  }, [series, calibration, innerW, innerH]);

  const { xs, ys, x, y } = view;
  const plottable = (a: number, b: number) => a > 0 && b > 0;

  const modelPath = polyline(xs, ys, x, y, plottable);
  // The constant-rate baseline: apparent age equals true age, by definition.
  const referencePath = polyline(
    [1, view.xMax], [1, view.xMax], x, y, plottable,
  );

  // Decades alone leave the axis looking unfinished: 1..6056 labels 1, 10,
  // 100, 1k and then just stops, so a reader cannot see where it ends. The
  // domain endpoint is added unless a decade already sits close to it.
  const decades = logDecadeTicks(1, view.xMax, 6);
  const last = decades[decades.length - 1] ?? 1;
  const xTicks = view.xMax / last > 2 ? [...decades, view.xMax] : decades;
  const yTicks = logDecadeTicks(1, view.yMax, 7);

  function onMove(event: React.PointerEvent<SVGSVGElement>) {
    const svg = event.currentTarget;
    const rect = svg.getBoundingClientRect();
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
  const hovered = hover ? { trueAge: xs[hover.index], secularAge: ys[hover.index] } : null;

  return (
    <figure className="chart">
      <figcaption>
        <h3>Apparent age vs. true age</h3>
        <p>
          How old rock of a given true age appears under this calibration. Both
          axes logarithmic; ages are years before present.
        </p>
      </figcaption>

      <div className="chart-wrap" ref={wrapRef}>
        <svg
          className="chart-svg"
          viewBox={`0 0 ${width} ${height}`}
          role="img"
          aria-label={
            `Apparent age against true age. The model reaches ` +
            `${formatAge(view.yMax)} apparent at ${formatAge(view.xMax)} true.`
          }
          onPointerMove={onMove}
          onPointerLeave={() => setHover(null)}
        >
          <g transform={`translate(${m.left},${m.top})`}>
            {yTicks.map((t) => (
              <g key={`y${t}`} transform={`translate(0,${y(t)})`}>
                <line className="grid-line" x1={0} x2={innerW} />
                <text className="axis-label" x={-8} dy="0.32em" textAnchor="end">
                  {formatAgeTick(t)}
                </text>
              </g>
            ))}
            {xTicks.map((t) => (
              <g key={`x${t}`} transform={`translate(${x(t)},0)`}>
                <line className="grid-line" y1={0} y2={innerH} />
                <text
                  className="axis-label" y={innerH + 16} textAnchor="middle"
                >
                  {formatAgeTick(t)}
                </text>
              </g>
            ))}
            <line className="axis-line" x1={0} y1={innerH} x2={innerW} y2={innerH} />

            <path
              d={referencePath}
              fill="none"
              stroke="var(--series-2)"
              strokeWidth={2}
              strokeLinecap="round"
              strokeLinejoin="round"
            />
            <path
              d={modelPath}
              fill="none"
              stroke="var(--series-1)"
              strokeWidth={2}
              strokeLinecap="round"
              strokeLinejoin="round"
            />

            {/* Calibration anchors. A 2px surface ring keeps them legible
                where they sit on the line. */}
            {calibration.constraints.map((c) => (
              c.trueAge > 0 && c.secularAge > 0 ? (
                <g key={c.label} transform={`translate(${x(c.trueAge)},${y(c.secularAge)})`}>
                  <circle r={5} fill="var(--series-1)"
                          stroke="var(--surface-2)" strokeWidth={2} />
                  <title>{`${c.label}: ${formatAge(c.trueAge)} true → ${formatAge(c.secularAge)} apparent`}</title>
                </g>
              ) : null
            ))}

            {hover && hovered ? (
              <g>
                <line
                  className="axis-line"
                  x1={x(hovered.trueAge)} y1={0}
                  x2={x(hovered.trueAge)} y2={innerH}
                />
                <circle
                  cx={x(hovered.trueAge)} cy={y(hovered.secularAge)} r={4.5}
                  fill="var(--series-1)" stroke="var(--surface-2)" strokeWidth={2}
                />
              </g>
            ) : null}

            <text
              className="axis-title"
              transform={`translate(${-m.left + 12},${innerH / 2}) rotate(-90)`}
              textAnchor="middle"
            >
              Apparent age (yr)
            </text>
            <text
              className="axis-title"
              x={innerW / 2} y={innerH + 32}
              textAnchor="middle"
            >
              True age (years before present)
            </text>
          </g>
        </svg>

        {hover && hovered ? (
          <div
            className="tooltip"
            style={{
              left: `${hover.left + 12}px`,
              top: `${hover.top - 8}px`,
              transform: hover.left > width * 0.6 ? "translateX(-100%) translateX(-24px)" : undefined,
            }}
          >
            <div className="tt-row">
              <span className="tt-key" style={{ background: "var(--series-1)" }} />
              true {formatAge(hovered.trueAge, digits)}
            </div>
            <div className="tt-row">
              <span className="tt-key" style={{ background: "var(--series-1)" }} />
              apparent {series.exact ? "" : "≈ "}{formatAge(hovered.secularAge, digits)}
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
