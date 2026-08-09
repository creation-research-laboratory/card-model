/**
 * λ(t) — the decay rate through time.
 *
 * Mirrors `card.plotting.plot_lambda_history`. **The x axis is a DATE**, years
 * after Day 1 of Creation, not an age before present. It is the only chart in
 * the app that runs that direction, and the package's own history says this is
 * exactly the confusion that once caused a real fitting error — hence the
 * explicit label rather than a bare "Time".
 *
 * Unlike the age curve, this one genuinely steps at the Flood. The data carries
 * two samples a fraction of a year apart to render that edge, so the polyline
 * must be drawn straight through them with no smoothing.
 *
 * One series, so no legend box: the title already says what is plotted.
 */

import { useMemo, useRef, useState } from "react";
import { scaleLinear, scaleLog } from "d3-scale";

import { DEFAULT_MARGIN, linearTicks, logDecadeTicks, nearestIndex, polyline } from "./axes.js";
import { formatDate, formatMultiplier, trim } from "./format.js";
import type { LambdaSeries } from "../model/types.js";

/** Which slice of the timeline the x axis covers. */
export type LambdaZoom = "full" | "flood";

interface Props {
  history: LambdaSeries;
  zoom: LambdaZoom;
  onZoom?(zoom: LambdaZoom): void;
  width?: number;
  height?: number;
}

export function LambdaHistoryChart({
  history, zoom, onZoom, width = 720, height = 300,
}: Props) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const [hover, setHover] = useState<{ index: number; left: number; top: number } | null>(null);
  // Extra headroom over the shared margin: the Flood annotation sits above
  // the plot area. Inside it, it lands on the spike it is annotating —
  // lambda_F is at the top of the domain and the jump is vertical.
  const m = { ...DEFAULT_MARGIN, top: 22 };
  const innerW = width - m.left - m.right;
  const innerH = height - m.top - m.bottom;

  const view = useMemo(() => {
    const maxLambda = Math.max(...history.lambda);

    // How long the relaxation actually takes, read from the data rather than
    // assumed: the last date at which lambda is still meaningfully above
    // background. Calibrating an instantaneous onset drives k_F to ~2/yr, so
    // this is a handful of years out of six millennia — 0.08% of the full
    // axis, which is why the full view renders it as a bare vertical line. It
    // is not an artifact; it is what the model looks like at that scale.
    let settled = history.floodEndDate;
    for (let i = 0; i < history.date.length; i++) {
      if (history.lambda[i] > 1.001) settled = history.date[i];
    }
    const decaySpan = Math.max(settled - history.floodStartDate, 1e-3);

    const domain: [number, number] = zoom === "flood"
      ? [
          Math.max(0, history.floodStartDate - decaySpan * 0.08),
          Math.min(history.presentDate, history.floodEndDate + decaySpan * 1.15),
        ]
      : [0, history.presentDate];

    const x = scaleLinear().domain(domain).range([0, innerW]);
    // Domain starts at 1 because λ is normalized to background and cannot go
    // below it — the model describes accelerated decay, never slower.
    const y = scaleLog().domain([1, maxLambda * 1.2]).range([innerH, 0]).clamp(true);
    return { x, y, maxLambda, domain, decaySpan };
  }, [history, innerW, innerH, zoom]);

  const { x, y, maxLambda } = view;
  // Clip to the visible domain, with one sample either side so the line
  // reaches the edges instead of stopping short.
  const path = polyline(
    history.date, history.lambda, x, y,
    (d, l) => l > 0 && d >= view.domain[0] - view.decaySpan
      && d <= view.domain[1] + view.decaySpan,
  );

  const xTicks = linearTicks(view.domain[0], view.domain[1], 6);
  const yTicks = logDecadeTicks(1, maxLambda * 1.2, 6);

  function onMove(event: React.PointerEvent<SVGSVGElement>) {
    const rect = event.currentTarget.getBoundingClientRect();
    const scale = rect.width / width;
    const localX = (event.clientX - rect.left) / scale - m.left;
    if (localX < 0 || localX > innerW) return setHover(null);
    const index = nearestIndex(history.date, x.invert(localX));
    if (index < 0) return setHover(null);
    setHover({
      index,
      left: (m.left + x(history.date[index])) * scale,
      top: (m.top + y(history.lambda[index])) * scale,
    });
  }

  const floodX = x(history.floodStartDate);
  const floodWidth = Math.max(0, x(history.floodEndDate) - floodX);

  return (
    <figure className="chart">
      <figcaption>
        <h3>Decay rate through time</h3>
        <p>
          λ(t) as a multiple of the present-day rate. The horizontal axis is a{" "}
          <strong>date</strong> — years <em>after</em> Day 1 of Creation — which
          runs opposite to the ages on the chart above.{" "}
          {zoom === "full" ? (
            <>The relaxation takes about{" "}
            {view.decaySpan < 1
              ? `${(view.decaySpan * 365.25).toFixed(0)} days`
              : `${view.decaySpan.toFixed(1)} years`}
            , which is why it reads as a vertical line across six millennia.</>
          ) : (
            <>Zoomed to the decay itself.</>
          )}
        </p>
        {onZoom ? (
          <div className="segmented" style={{ marginTop: ".5rem" }} role="group"
               aria-label="Decay chart time range">
            <button type="button" aria-pressed={zoom === "full"}
                    className={zoom === "full" ? "on" : ""}
                    onClick={() => onZoom("full")}>
              Full timeline
            </button>
            <button type="button" aria-pressed={zoom === "flood"}
                    className={zoom === "flood" ? "on" : ""}
                    onClick={() => onZoom("flood")}>
              The decay
            </button>
          </div>
        ) : null}
      </figcaption>

      <div className="chart-wrap" ref={wrapRef}>
        <svg
          className="chart-svg"
          viewBox={`0 0 ${width} ${height}`}
          role="img"
          aria-label={
            `Decay rate against date. Background until the Flood at date ` +
            `${formatDate(history.floodStartDate)}, where it jumps to ` +
            `${formatMultiplier(maxLambda)} times background, then relaxes back.`
          }
          onPointerMove={onMove}
          onPointerLeave={() => setHover(null)}
        >
          <g transform={`translate(${m.left},${m.top})`}>
            {yTicks.map((t) => (
              <g key={`y${t}`} transform={`translate(0,${y(t)})`}>
                <line className="grid-line" x1={0} x2={innerW} />
                <text className="axis-label" x={-8} dy="0.32em" textAnchor="end">
                  {formatMultiplier(t)}
                </text>
              </g>
            ))}
            {xTicks.map((t) => (
              <g key={`x${t}`} transform={`translate(${x(t)},0)`}>
                <line className="grid-line" y1={0} y2={innerH} />
                <text className="axis-label" y={innerH + 16} textAnchor="middle">
                  {zoom === "flood" ? trim(t, 8) : formatDate(t)}
                </text>
              </g>
            ))}
            <line className="axis-line" x1={0} y1={innerH} x2={innerW} y2={innerH} />

            {/* The Flood window. Zero-width in the instantaneous limit that the
                flood-only mode uses, so it draws as a rule rather than a band.
                Muted ink, not a status color — this is an annotation. */}
            {floodWidth > 1 ? (
              <rect
                x={floodX} y={0} width={floodWidth} height={innerH}
                fill="var(--text-muted)" opacity={0.12}
              />
            ) : (
              <line
                x1={floodX} y1={0} x2={floodX} y2={innerH}
                stroke="var(--text-muted)" strokeWidth={1} opacity={0.65}
              />
            )}
            <text
              className="axis-label" x={floodX} y={-7}
              textAnchor={floodX > innerW * 0.85 ? "end" : "middle"}
              fill="var(--text-secondary)"
            >
              Flood
            </text>

            <path
              d={path}
              fill="none"
              stroke="var(--series-1)"
              strokeWidth={2}
              strokeLinecap="round"
              strokeLinejoin="round"
            />

            {hover ? (
              <g>
                <line
                  className="axis-line"
                  x1={x(history.date[hover.index])} y1={0}
                  x2={x(history.date[hover.index])} y2={innerH}
                />
                <circle
                  cx={x(history.date[hover.index])}
                  cy={y(history.lambda[hover.index])}
                  r={4.5} fill="var(--series-1)"
                  stroke="var(--surface-2)" strokeWidth={2}
                />
              </g>
            ) : null}

            <text
              className="axis-title"
              transform={`translate(${-m.left + 12},${innerH / 2}) rotate(-90)`}
              textAnchor="middle"
            >
              λ / λ background
            </text>
            <text
              className="axis-title"
              x={innerW / 2} y={innerH + 32} textAnchor="middle"
            >
              Date (years after Creation)
            </text>
          </g>
        </svg>

        {hover ? (
          <div
            className="tooltip"
            style={{
              left: `${hover.left + 12}px`,
              top: `${hover.top - 8}px`,
              transform: hover.left > width * 0.6 ? "translateX(-100%) translateX(-24px)" : undefined,
            }}
          >
            <div>date {formatDate(history.date[hover.index])}</div>
            <div className="tt-row">
              <span className="tt-key" style={{ background: "var(--series-1)" }} />
              λ {formatMultiplier(history.lambda[hover.index])}×
            </div>
          </div>
        ) : null}
      </div>
    </figure>
  );
}
