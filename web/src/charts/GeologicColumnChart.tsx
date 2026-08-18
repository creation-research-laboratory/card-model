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
import { abbreviate, groupMarkers, markersFor, type Marker } from "./breakpoints.js";
import { formatDuration, formatMultiplier, formatAge, trim } from "./format.js";
import type { Calibration, GeologicColumn } from "../model/types.js";
import { usePowerUser } from "../ui/preferences.js";

/** Which stretch of time the axis covers. */
export type ColumnZoom = "full" | "flood";

interface Props {
  column: GeologicColumn;
  calibration: Calibration;
  zoom?: ColumnZoom;
  onZoom?(zoom: ColumnZoom): void;
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
// The top band carries four tiers: the marker label, the contacts it names,
// the calendar axis title, and the calendar tick labels.
const MARGIN = { top: 78, right: 20, bottom: 34, left: 104 };
/** Sub-pixel intervals still need to be visible; see `groupMarkers`. */
const MIN_BAND_PX = 3;

/**
 * Names for a cluster of markers: what happens, and where.
 *
 * `t_F` and `t_F2` always cluster, and "Flood begins / Flood ends" is a poor
 * label for a mark three pixels wide. When every label in the group opens with
 * the same word, that word plus the span it covers says it better.
 *
 * The second line is the point of the whole exercise. `t_F2` is the
 * Flood/post-Flood contact, which is the boundary the reader selected — so the
 * band has to name it. A label reading only "Flood (1 yr)" hid the fact that
 * the exponential handover happens exactly at K/Pg (or N/Q).
 */
function labelForGroup(markers: readonly Marker[]): {
  primary: string; secondary?: string; displaced: boolean;
} {
  const contacts = markers
    .map((m) => m.boundary ?? m.displaced)
    .filter((b): b is string => Boolean(b))
    .map(abbreviate);
  // Groups arrive sorted by pixel, and the axis runs oldest-left, so joining
  // in order reads the way the figure does.
  const secondary = contacts.length ? contacts.join(" → ") : undefined;
  // A contact the model has been moved off is still worth naming — the reader
  // needs to see *which* one drifted — but it must not read as a fact.
  const displaced = markers.some((m) => m.displaced);

  if (markers.length === 1) {
    return { primary: markers[0].label, secondary, displaced };
  }

  const first = markers.map((m) => m.label.split(" ")[0]);
  if (first.every((w) => w === first[0])) {
    const span = Math.abs(markers[0].trueAge - markers[markers.length - 1].trueAge);
    return {
      primary: span > 0 ? `${first[0]} (${formatDuration(span)})` : first[0],
      secondary, displaced,
    };
  }
  return {
    primary: markers.map((m) => m.label).join(" / "), secondary, displaced,
  };
}

export function GeologicColumnChart({
  column, calibration, zoom = "full", onZoom,
  presentYear = new Date().getUTCFullYear(), width = 720,
  fullColumnBoundary = null, onSelectBoundary,
}: Props) {
  const powerUser = usePowerUser();
  const [hover, setHover] = useState<number | null>(null);
  const [openMarker, setOpenMarker] = useState<string | null>(null);

  const rows = column.units;
  const innerW = width - MARGIN.left - MARGIN.right;
  const innerH = rows.length * ROW_HEIGHT;
  const height = innerH + MARGIN.top + MARGIN.bottom;

  const { x, ticks, domain } = useMemo(() => {
    const { ageOfEarth } = calibration.chronology;
    const floodStart = ageOfEarth - calibration.params.t_F;
    const floodEnd = ageOfEarth - calibration.params.t_F2;

    let lo: number;
    let hi: number;
    if (zoom === "flood") {
      // The Flood year, which is where all but a handful of the units live.
      // For the K/Pg calibration every unit from the Cambrian to the
      // Cretaceous sits between t_F2 and t_F — one year out of six thousand,
      // sub-pixel on the full axis, and the whole reason for this view.
      const span = Math.max(floodStart - floodEnd, 1e-6);
      lo = floodEnd - span * 0.05;
      hi = floodStart + span * 0.05;
    } else {
      const oldestTrue = Math.max(
        ...rows.filter((u) => u.inRange).map((u) => u.baseTrueAge ?? 0),
        1,
      );
      // Round out to a whole thousand so the axis reads in familiar steps, and
      // never past the age of the Earth for this chronology.
      lo = 0;
      hi = Math.min(ageOfEarth, Math.ceil(oldestTrue / 500) * 500);
    }

    return {
      domain: [lo, hi] as const,
      // Reversed range: true age decreases left to right, so the present is on
      // the right and the deep past on the left. Clamped so a bar reaching
      // outside the zoom is cut at the frame rather than drawn beyond it.
      x: scaleLinear().domain([lo, hi]).range([innerW, 0]).clamp(true),
      ticks: linearTicks(lo, hi, zoom === "flood" ? 4 : 6),
    };
  }, [rows, calibration, innerW, zoom]);

  // Only the markers this axis actually reaches — the same test the bars get.
  const groups = useMemo(() => {
    const visible = markersFor(calibration)
      .filter((m) => m.trueAge >= domain[0] && m.trueAge <= domain[1])
      // The Flood-day marks live inside a year that is 0.13 px wide on the
      // full axis, so there they would simply be swallowed by the Flood band
      // and add two names to its hover text for no visible mark.
      .filter((m) => zoom === "flood" || m.kind !== "reference");
    return groupMarkers(visible, x);
  }, [calibration, domain, x, zoom]);

  /**
   * Place each label stack, dropping to a second tier when it would collide.
   *
   * "Precambrian-Cambrian" is 110px of text anchored at the Flood's start, and
   * the 40-day mark is 59px away — so without this the contact name runs
   * straight through the neighbouring label.
   *
   * The second tier exists only in the Flood view, which is also the only view
   * that needs it: hiding the calendar tier there frees the band at -34/-22,
   * and it is the view that puts four marks inside one year. The full view
   * keeps the calendar and carries two marks — the Flood band at one end and
   * the Ice Age millennia away — so it has neither the room nor the need.
   */
  const placed = useMemo(() => {
    const tiers = zoom === "flood"
      ? [{ primary: -60, secondary: -48 }, { primary: -34, secondary: -22 }]
      : [{ primary: -60, secondary: -48 }];
    // 11px sans, averaged. Only ever used to decide whether two labels clash.
    const CHAR_PX = 5.7;
    const rightEdge = tiers.map(() => -Infinity);

    return groups.map((group) => {
      const bandW = Math.max(MIN_BAND_PX, group.to - group.from);
      const mid = group.from + bandW / 2;
      const names = labelForGroup(group.markers);
      // Both label lines share an anchor, or they would splay apart at the
      // plot edges where one flips and the other does not.
      const anchor: "start" | "end" | "middle" =
        mid > innerW - 40 ? "end" : mid < 40 ? "start" : "middle";

      const text = Math.max(
        names.primary.length,
        (names.secondary?.length ?? 0) + (names.displaced ? 8 : 0),
      );
      const w = text * CHAR_PX;
      const left = anchor === "start" ? mid : anchor === "end" ? mid - w : mid - w / 2;

      let tier = tiers.findIndex((_, i) => left > rightEdge[i] + 6);
      if (tier < 0) tier = tiers.length - 1;
      rightEdge[tier] = left + w;

      return { group, names, mid, anchor, bandW, y: tiers[tier] };
    });
  }, [groups, innerW, zoom]);

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
        {powerUser ? null : (
          <p>
            Each unit&rsquo;s span, converted through this calibration. Time runs
            right to left, most recent at the right. Labels give the duration and,
            in brackets, how many secular years elapsed per young-earth year.{" "}
            {zoom === "flood" ? (
              <>Zoomed to the Flood year, where all but the youngest few units
              fall — on the full axis they are thinner than a pixel.</>
            ) : (
              <>Most of the column is compressed into the Flood year, too narrow
              to resolve here; the Flood view spreads it out.</>
            )}
          </p>
        )}
        {onZoom ? (
          <div className="segmented" style={{ marginTop: ".5rem" }} role="group"
               aria-label="Column time range">
            <button type="button" aria-pressed={zoom === "full"}
                    className={zoom === "full" ? "on" : ""}
                    onClick={() => onZoom("full")}>
              Full timeline
            </button>
            <button type="button" aria-pressed={zoom === "flood"}
                    className={zoom === "flood" ? "on" : ""}
                    onClick={() => onZoom("flood")}>
              The Flood year
            </button>
          </div>
        ) : null}
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
            {zoom === "flood" ? null : (
              <text className="axis-title" x={innerW} y={-32} textAnchor="end"
                    fill="var(--text-muted)">
                Calendar date
              </text>
            )}

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
                    {/* "4.4 kyr" cannot tell 4399 from 4400, and inside the
                        Flood year that is the only distinction there is. */}
                    {zoom === "flood" ? trim(t, 8) : t === 0 ? "0" : formatAge(t, 3)}
                  </text>
                  {/* Secondary axis: the same instants as calendar dates, which
                      is how a reader without the BP convention will read it.
                      Dropped in the Flood view — every tick falls in the same
                      calendar year, so the tier would repeat one label. */}
                  {zoom === "flood" ? null : (
                    <text className="axis-label" y={-16} textAnchor={anchor}
                          fill="var(--text-muted)">
                      {calendarLabel(t)}
                    </text>
                  )}
                </g>
              );
            })}

            {/* Where the model changes behaviour, and where it was pinned. */}
            {placed.map(({ group, names, mid, anchor, bandW, y }) => {
              const isRate = group.markers.some((m) => m.kind === "rate");
              const isReference = group.markers.every((m) => m.kind === "reference");
              // Solid: something changes. Dashed: fitted here. Dotted: a point
              // in the account, where the model does nothing at all.
              const dash = isRate ? undefined : isReference ? "1 3" : "4 3";
              const stroke = isRate ? "var(--marker)"
                : isReference ? "var(--text-secondary)" : "var(--text-muted)";
              const key = group.markers.map((m) => m.key).join("+");
              const isOpen = openMarker === key;

              return (
                <g
                  key={key}
                  onPointerEnter={() => setOpenMarker(key)}
                  onPointerLeave={() => setOpenMarker(null)}
                  style={{ cursor: "help" }}
                >
                  {/* Generous hit target: the mark itself is a few pixels. */}
                  <rect
                    x={group.from - 8} y={y.primary - 12} width={bandW + 16}
                    height={innerH - y.primary + 12} fill="transparent"
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
                    stroke={stroke}
                    strokeWidth={1}
                    strokeDasharray={dash}
                    opacity={isOpen ? 1 : 0.75}
                  />
                  <text
                    className="axis-label" x={mid} y={y.primary}
                    textAnchor={anchor}
                    fill={stroke}
                  >
                    {names.primary}
                  </text>
                  {names.secondary ? (
                    // The contacts this lands on. For the Flood band that is
                    // the pair the reader chose between, so it belongs on the
                    // figure rather than only in the hover text.
                    <text
                      className="axis-label" x={mid} y={y.secondary}
                      textAnchor={anchor}
                      fill={names.displaced ? "var(--warn)" : "var(--text-muted)"}
                    >
                      {names.secondary}
                      {names.displaced ? " (moved)" : null}
                    </text>
                  ) : null}
                </g>
              );
            })}

            {rows.map((unit, i) => {
              const yTop = i * ROW_HEIGHT;
              const label = unit.name;

              // Two different kinds of absence, said differently. A unit can
              // have no young-earth date at all, or have one that this zoom
              // does not cover. Clamping alone would turn the second into a
              // zero-width bar pinned to the frame edge, then widen it to the
              // 2px minimum — a mark exactly where the unit is not.
              const missing = !unit.inRange
                ? "beyond this calibration\u2019s range"
                : unit.baseTrueAge! < domain[0]
                  ? "after the Flood year"
                  : unit.topTrueAge! > domain[1]
                    ? "before the Flood year"
                    : null;

              if (missing) {
                return (
                  <g key={label} transform={`translate(0,${yTop})`}>
                    <text className="axis-label" x={-10} y={ROW_HEIGHT / 2}
                          dy="0.32em" textAnchor="end" fill="var(--text-muted)">
                      {label}
                    </text>
                    <text className="axis-label" x={4} y={ROW_HEIGHT / 2}
                          dy="0.32em" fill="var(--text-muted)">
                      {missing}
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
                <dt className={m.kind}>
                  {m.label}
                  {m.boundary ? (
                    <span className="marker-contact"> — {m.boundary}</span>
                  ) : m.displaced ? (
                    <span className="marker-contact" style={{ color: "var(--warn)" }}>
                      {" "}— {m.displaced} (no longer here)
                    </span>
                  ) : null}
                  <span className="marker-age"> · {formatAge(m.trueAge, 4)} BP</span>
                </dt>
                <dd>{m.detail}</dd>
              </div>
            ))}
          </dl>
        ) : (
          // Shortened, never dropped. Without a key the three line styles are
          // indistinguishable, so this is the figure's legend rather than
          // explanation — power-user mode trims the wording, not the keys.
          powerUser ? (
            <p>
              <span className="marker-key rate" aria-hidden="true" /> rate change
              {" · "}
              <span className="marker-key anchor" aria-hidden="true" /> fitted
              {zoom === "flood" ? (
                <>
                  {" · "}
                  <span className="marker-key reference" aria-hidden="true" />{" "}
                  Flood day
                </>
              ) : null}
            </p>
          ) : (
          <p>
            <span className="marker-key rate" aria-hidden="true" /> where λ or
            its relaxation constant changes ·{" "}
            <span className="marker-key anchor" aria-hidden="true" /> a date the
            model was fitted to
            {zoom === "flood" ? (
              <>
                {" "}·{" "}
                <span className="marker-key reference" aria-hidden="true" /> a
                day of the Flood account, where the model does nothing
              </>
            ) : null}
            . Hover any of them for detail.
          </p>
          )
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
