/**
 * The chart's data as a table.
 *
 * Present for accessibility — a chart must never be the only way to reach its
 * numbers — and because a reader checking a specific age wants to read it, not
 * hover for it. Collapsed by default so it does not compete with the figures.
 *
 * Thinned to a readable number of rows: the full grid is ~600 points, and a
 * table nobody can scan is not an alternative to anything.
 */

import { useMemo } from "react";

import { formatAge, significantFor } from "../charts/format.js";
import type { Calibration, Series } from "../model/types.js";

interface Props {
  series: Series;
  calibration: Calibration;
  rows?: number;
}

export function SeriesTable({ series, calibration, rows = 24 }: Props) {
  const digits = significantFor(series.exact);

  const sampled = useMemo(() => {
    const anchors = new Set(calibration.constraints.map((c) => c.trueAge));
    const indices: number[] = [];
    const stride = Math.max(1, Math.floor(series.trueAge.length / rows));
    for (let i = 0; i < series.trueAge.length; i += stride) indices.push(i);
    // The constraint anchors are the rows a reader is most likely to be
    // checking, so they are never thinned away.
    series.trueAge.forEach((age, i) => {
      if (anchors.has(age) && !indices.includes(i)) indices.push(i);
    });
    return indices.sort((a, b) => a - b);
  }, [series, calibration, rows]);

  const anchorAges = new Set(calibration.constraints.map((c) => c.trueAge));

  return (
    <details className="table-view">
      <summary>
        Data table ({sampled.length} of {series.trueAge.length} sampled points)
      </summary>
      <div className="scroll-x">
        <table className="data-table">
          <caption className="visually-hidden">
            Apparent age against true age for the current calibration.
          </caption>
          <thead>
            <tr>
              <th scope="col">True age (YBP)</th>
              <th scope="col">Apparent age (yr)</th>
              <th scope="col">Ratio</th>
            </tr>
          </thead>
          <tbody>
            {sampled.map((i) => {
              const trueAge = series.trueAge[i];
              const secular = series.secularAge[i];
              const isAnchor = anchorAges.has(trueAge);
              return (
                <tr key={i}>
                  <td>
                    {formatAge(trueAge, digits)}
                    {isAnchor ? (
                      <span style={{ color: "var(--text-muted)" }}> · constraint</span>
                    ) : null}
                  </td>
                  <td>{series.exact ? "" : "≈ "}{formatAge(secular, digits)}</td>
                  <td>{trueAge > 0 ? formatAge(secular / trueAge, 3).replace(" yr", "×") : "—"}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </details>
  );
}
