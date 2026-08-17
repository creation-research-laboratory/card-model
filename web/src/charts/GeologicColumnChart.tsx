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
import { groupMarkers, markersFor } from "./breakpoints.js";
import { formatDuration, formatMultiplier, formatAge } from "./format.js";
import type { Calibration, GeologicColumn } from "../model/types.js";

interface Props {
  column: GeologicColumn;
  calibration: Calibration;
  /** Year the "present" refers to, for the calendar-date axis. */
  presentYear?: number;
  width?: number;
  /**
   * A boundary whose calibration reaches every unit, if one exists. Offered
   * from the out-of-range notice so the reader can act on it rather than being
   * told what they cannot see.
   */
  fullColumnBoundary?: { key: string; label: string } | null;
  onSelectBoundary?(key: string): void;
}

const ROW_HEIGHT = 22;
// The top band carries three tiers: marker labels, the calendar axis title,
// and the calendar tick labels.
const MARGIN = { top: 66, right: 20, bottom: 34, left: 104 };
/** Sub-pixel intervals still need to be visible; see `groupMarkers`. */
const MIN_BAND_PX = 3;

/**
 * A name for a cluster of markers.
 *
 * `t_F` and `t_F2` always cluster, and "Flood begins / Flood ends" is a poor
 * label for a mark three pixels wide. When every label in the group opens with
 * the same word, that word plus the span it covers says it better.
 */
function labelForGroup(markers: readonly { label: string; trueAge: number }[]): string {
  if (markers.length === 1) return markers[0].label;
  const first = markers.map((m) => m.label.split(" ")[0]);
  if (first.every((w) => w === first[0])) {
    const span = Math.abs(markers[0].trueAge - markers[markers.length - 1].trueAge);
    return span > 0 ? `${first[0]} (${formatDuration(span)})` : first[0];
  }
  return markers.map((m) => m.label).join(" / ");
}

export function GeologicColumnChart({
  column, calibration, presentYear = new Date().getUTCFullYear(), width = 720,
  fullColumnBoundary = null, onSelectBoundary,
}: Props) {
  const [hover, setHover] = useState<number | null>(null);
  const [openMarker, setOpenMarker] = useState<string | null>(null);

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

  // Only the markers this axis actually reaches — the same test the bars get.
  const groups = useMemo(() => {
    const visible = markersFor(calibration)
      .filter((m) => m.trueAge >= 0 && m.trueAge <= oldest);
    return groupMarkers(visible, x);
  }, [calibration, oldest, x]);

  const openDetail = useMemo(() => {
    const group = groups.find(
      (g) => g.markers.map((m) => m.key).join("+") === openMarker,
    );
    return group?.markers ?? null;
  }, [groups, openMarker]);

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

            {/* Where the model changes behaviour, and where it was pinned. */}
            {groups.map((group) => {
              const isRate = group.markers.some((m) => m.kind === "rate");
              const key = group.markers.map((m) => m.key).join("+");
              const isOpen = openMarker === key;
              const bandW = Math.max(MIN_BAND_PX, group.to - group.from);
              const mid = group.from + bandW / 2;

              return (
                <g
                  key={key}
                  onPointerEnter={() => setOpenMarker(key)}
                  onPointerLeave={() => setOpenMarker(null)}
                  style={{ cursor: "help" }}
                >
                  {/* Generous hit target: the mark itself is a few pixels. */}
                  <rect
                    x={group.from - 8} y={-52} width={bandW + 16}
                    height={innerH + 52} fill="transparent"
                  />
                  {group.markers.length > 1 ? (
                    // An interval, not an instant. Widened to stay visible, so
                    // the label carries the real duration.
                    <rect
                      x={group.from} y={-8} width={bandW} height={innerH + 8}
                      fill="var(--marker)" opacity={isOpen ? 0.3 : 0.18}
                    />
                  ) : null}
                  <line
                    x1={mid} y1={-8} x2={mid} y2={innerH}
                    stroke={isRate ? "var(--marker)" : "var(--text-muted)"}
                    strokeWidth={1}
                    // Dashed says "fitted here", solid says "changes here".
                    strokeDasharray={isRate ? undefined : "4 3"}
                    opacity={isOpen ? 1 : 0.75}
                  />
                  <text
                    className="axis-label" x={mid} y={-48}
                    textAnchor={
                      mid > innerW - 40 ? "end" : mid < 40 ? "start" : "middle"
                    }
                    fill={isRate ? "var(--marker)" : "var(--text-muted)"}
                  >
                    {labelForGroup(group.markers)}
                  </text>
                </g>
              );
            })}

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

      {/* Reserved height, so hovering a marker does not reflow the page. */}
      <div className="marker-detail" aria-live="polite">
        {openDetail ? (
          <dl>
            {openDetail.map((m) => (
              <div key={m.key}>
                <dt className={m.kind === "rate" ? "rate" : "anchor"}>
                  {m.label}
                  <span className="marker-age"> · {formatAge(m.trueAge, 4)} BP</span>
                </dt>
                <dd>{m.detail}</dd>
              </div>
            ))}
          </dl>
        ) : (
          <p>
            <span className="marker-key rate" aria-hidden="true" /> where λ or
            its relaxation constant changes ·{" "}
            <span className="marker-key anchor" aria-hidden="true" /> a date the
            model was fitted to. Hover either for detail.
          </p>
        )}
      </div>

      {inRangeCount < rows.length ? (
        <p className="notice" style={{ marginTop: ".6rem" }}>
          <strong>
            {rows.length - inRangeCount} of {rows.length} units are outside this
            calibration.
          </strong>{" "}
          This is the calibration talking, not missing data. Pinning the Flood
          to this boundary means Flood rock appears exactly that old, and
          everything formed before it decayed at background rate — which adds
          only{" "}
          {formatAge(column.maxSecularAge - calibration.constraints[0].secularAge)}{" "}
          of apparent age. So the model tops out at{" "}
          {formatAge(column.maxSecularAge)}, and no true age whatsoever looks
          older than that.
          {fullColumnBoundary && onSelectBoundary ? (
            <>
              {" "}
              <button
                className="action"
                style={{ marginTop: ".5rem" }}
                onClick={() => onSelectBoundary(fullColumnBoundary.key)}
              >
                Show the full column ({fullColumnBoundary.label})
              </button>
            </>
          ) : null}
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
