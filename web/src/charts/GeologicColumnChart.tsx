/**
 * The geological column, compressed into young-earth time.
 *
 * One horizontal bar per chronostratigraphic unit, spanning the true ages its
 * secular boundaries map to. The x axis is true age before present, running
 * **right to left** — most recent at the right — so time flows the way a
 * reader expects and the bars stack into something like a stratigraphic
 * column, youngest at the top.
 *
 * This is the view where the model's claim is most legible: the Phanerozoic
 * collapses into a few tens of years, with each bar labelled by how long it
 * lasted and how much faster the clock ran.
 *
 * A unit whose base is older than the calibration can produce gets a marker
 * rather than a bar. Pinning the Flood to the K/Pg boundary caps the model at
 * 66 Myr, so nine of the fourteen units simply have no young-earth date — and
 * showing an empty row says that far better than omitting it.
 */

import { useMemo, useState } from "react";
import { scaleLinear } from "d3-scale";

import { linearTicks } from "./axes.js";
import { formatDuration, formatMultiplier, formatAge } from "./format.js";
import type { Calibration, GeologicColumn } from "../model/types.js";

interface Props {
  column: GeologicColumn;
  calibration: Calibration;
  /** Year the "present" refers to, for the calendar-date axis. */
  presentYear?: number;
  width?: number;
}

const ROW_HEIGHT = 22;
const MARGIN = { top: 46, right: 20, bottom: 34, left: 104 };

export function GeologicColumnChart({
  column, calibration, presentYear = new Date().getUTCFullYear(), width = 720,
}: Props) {
  const [hover, setHover] = useState<number | null>(null);

  const rows = column.units;
  const innerW = width - MARGIN.left - MARGIN.right;
  const innerH = rows.length * ROW_HEIGHT;
  const height = innerH + MARGIN.top + MARGIN.bottom;

  const { x, ticks, oldest } = useMemo(() => {
    const oldestTrue = Math.max(
      ...rows.filter((u) => u.inRange).map((u) => u.baseTrueAge ?? 0),
      1,
    );
    // Round out to a whole thousand so the axis reads in familiar steps, and
    // never past the age of the Earth for this chronology.
    const limit = Math.min(
      calibration.chronology.ageOfEarth,
      Math.ceil(oldestTrue / 500) * 500,
    );
    return {
      oldest: limit,
      // Reversed range: true age decreases left to right, so the present is on
      // the right and the deep past on the left.
      x: scaleLinear().domain([0, limit]).range([innerW, 0]),
      ticks: linearTicks(0, limit, 6),
    };
  }, [rows, calibration, innerW]);

  /**
   * Calendar year for a true age. Uses astronomical year numbering internally
   * (there is no year zero in BC/AD), so the label is computed then converted.
   */
  const calendarLabel = (trueAge: number): string => {
    const astronomical = presentYear - trueAge;
    if (astronomical > 0) return `AD ${Math.round(astronomical)}`;
    return `${Math.round(1 - astronomical)} BC`;
  };

  const inRangeCount = rows.filter((u) => u.inRange).length;

  return (
    <figure className="chart">
      <figcaption>
        <h3>The geological column in young-earth time</h3>
        <p>
          Each unit&rsquo;s span, converted through this calibration. Time runs
          right to left, most recent at the right. Labels give the duration and,
          in brackets, how many secular years elapsed per young-earth year.
        </p>
      </figcaption>

      <div className="chart-wrap">
        <svg
          className="chart-svg"
          viewBox={`0 0 ${width} ${height}`}
          role="img"
          aria-label={
            `Geological column as young-earth durations. ` +
            `${inRangeCount} of ${rows.length} units fall within this ` +
            `calibration's range.`
          }
        >
          <g transform={`translate(${MARGIN.left},${MARGIN.top})`}>
            <text className="axis-title" x={innerW} y={-32} textAnchor="end"
                  fill="var(--text-muted)">
              Calendar date
            </text>

            {ticks.map((t) => {
              // The end ticks sit on the plot edges, and a centred label there
              // spills past the margin — "AD 2026" overflowed the figure box.
              const px = x(t);
              const anchor = px > innerW - 24 ? "end"
                : px < 24 ? "start" : "middle";
              return (
                <g key={t} transform={`translate(${px},0)`}>
                  <line className="grid-line" y1={-8} y2={innerH} />
                  <text className="axis-label" y={innerH + 16} textAnchor={anchor}>
                    {t === 0 ? "0" : formatAge(t, 3)}
                  </text>
                  {/* Secondary axis: the same instants as calendar dates, which
                      is how a reader without the BP convention will read it. */}
                  <text className="axis-label" y={-16} textAnchor={anchor}
                        fill="var(--text-muted)">
                    {calendarLabel(t)}
                  </text>
                </g>
              );
            })}

            {/* The Flood, which is where almost every bar piles up. */}
            {(() => {
              const floodAge = calibration.chronology.ageOfEarth
                - calibration.params.t_F;
              if (!(floodAge > 0 && floodAge <= oldest)) return null;
              return (
                <g>
                  <line
                    x1={x(floodAge)} y1={-8} x2={x(floodAge)} y2={innerH}
                    stroke="var(--text-muted)" strokeWidth={1} opacity={0.65}
                  />
                  <text className="axis-label" x={x(floodAge)} y={-30}
                        textAnchor="middle" fill="var(--text-secondary)">
                    Flood
                  </text>
                </g>
              );
            })()}

            {rows.map((unit, i) => {
              const yTop = i * ROW_HEIGHT;
              const label = unit.name;

              if (!unit.inRange) {
                return (
                  <g key={label} transform={`translate(0,${yTop})`}>
                    <text className="axis-label" x={-10} y={ROW_HEIGHT / 2}
                          dy="0.32em" textAnchor="end" fill="var(--text-muted)">
                      {label}
                    </text>
                    <text className="axis-label" x={4} y={ROW_HEIGHT / 2}
                          dy="0.32em" fill="var(--text-muted)">
                      beyond this calibration&rsquo;s range
                    </text>
                  </g>
                );
              }

              const left = x(unit.baseTrueAge!);
              const right = x(unit.topTrueAge!);
              // Bars for the older units are sub-pixel; widen to a visible
              // minimum so the row still reads as a mark rather than a gap.
              const barW = Math.max(2, right - left);
              const isHovered = hover === i;

              return (
                <g
                  key={label}
                  transform={`translate(0,${yTop})`}
                  onPointerEnter={() => setHover(i)}
                  onPointerLeave={() => setHover(null)}
                >
                  {/* Full-width hit target: the bars themselves are often 2px. */}
                  <rect x={0} y={0} width={innerW} height={ROW_HEIGHT}
                        fill="transparent" />
                  <text className="axis-label" x={-10} y={ROW_HEIGHT / 2}
                        dy="0.32em" textAnchor="end">
                    {label}
                  </text>
                  <rect
                    x={left} y={4} width={barW} height={ROW_HEIGHT - 10}
                    rx={2}
                    fill="var(--series-1)"
                    opacity={isHovered ? 1 : 0.85}
                    stroke="var(--surface-1)" strokeWidth={1}
                  />
                  <text
                    className="axis-label"
                    x={Math.min(left + barW + 6, innerW - 4)}
                    y={ROW_HEIGHT / 2} dy="0.32em"
                    textAnchor={left + barW > innerW * 0.7 ? "end" : "start"}
                    fill="var(--text-secondary)"
                  >
                    {formatDuration(unit.durationTrue!)}
                    {unit.acceleration
                      ? ` (${formatMultiplier(unit.acceleration)}×)`
                      : ""}
                  </text>
                </g>
              );
            })}

            <text className="axis-title" x={innerW / 2} y={innerH + 32}
                  textAnchor="middle">
              True age (years before present)
            </text>
          </g>
        </svg>
      </div>

      {inRangeCount < rows.length ? (
        <p className="notice" style={{ marginTop: ".6rem" }}>
          <strong>
            {rows.length - inRangeCount} of {rows.length} units are outside this
            calibration.
          </strong>{" "}
          Pinning the Flood to a younger boundary caps the oldest apparent age
          the model can produce at{" "}
          {formatAge(column.maxSecularAge)}, so anything older has no
          young-earth date here. Choose an older boundary to see the full
          column.
        </p>
      ) : null}

      <details className="table-view">
        <summary>Data table ({rows.length} units)</summary>
        <div className="scroll-x">
          <table className="data-table">
            <caption className="visually-hidden">
              Chronostratigraphic units with their secular spans and the
              young-earth durations this calibration gives them.
            </caption>
            <thead>
              <tr>
                <th scope="col">Unit</th>
                <th scope="col">Secular span</th>
                <th scope="col">True span (BP)</th>
                <th scope="col">Duration</th>
                <th scope="col">Acceleration</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((u) => (
                <tr key={u.name}>
                  <td>{u.name}</td>
                  <td>
                    {formatAge(u.baseSecularAge)} → {formatAge(u.topSecularAge)}
                  </td>
                  <td>
                    {u.inRange
                      ? `${formatAge(u.baseTrueAge!, 5)} → ${formatAge(u.topTrueAge!, 5)}`
                      : "—"}
                  </td>
                  <td>{u.inRange ? formatDuration(u.durationTrue!) : "—"}</td>
                  <td>
                    {u.inRange && u.acceleration
                      ? `${formatMultiplier(u.acceleration)}×`
                      : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </figure>
  );
}
