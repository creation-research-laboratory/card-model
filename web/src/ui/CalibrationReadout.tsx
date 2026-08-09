/**
 * The solved parameters and how well they honour their constraints.
 *
 * Residuals are shown unconditionally, not behind an "advanced" toggle: they
 * are how a reader knows the fit is exact rather than approximate, and hiding
 * them would make the strongest thing about this solve invisible.
 */

import type { Calibration } from "../model/types.js";
import type { SourceKind } from "../model/ModelSource.js";
import { formatAge, formatMultiplier, trim } from "../charts/format.js";

interface Props {
  calibration: Calibration;
  sourceKind: SourceKind;
  /**
   * Where the selected Flood-boundary model lands on this curve. An output of
   * the calibration, never an input — which is how a Flood model gets tested.
   */
  floodEnd?: {
    label: string; secular_age: number; in_range: boolean;
    true_age?: number; years_after_flood?: number; flood_days?: number;
  };
}

export function CalibrationReadout({
  calibration, sourceKind, floodEnd,
}: Props) {
  const { params, constraints, residuals, maxAbsResidual, exact } = calibration;

  return (
    <section className="panel" aria-labelledby="calibration-heading">
      <h2 id="calibration-heading">Calibration</h2>

      <dl className="readout">
        <dt>λ<sub>F</sub></dt>
        <dd>{formatMultiplier(params.lambda_F)}× background</dd>
        <dt>k<sub>F</sub></dt>
        <dd>{trim(params.k_F, 6)} yr⁻¹</dd>
        <dt>λ<sub>c</sub> / k<sub>c</sub></dt>
        <dd>{formatMultiplier(params.lambda_c)}× / {trim(params.k_c, 4)}</dd>
        <dt>oldest apparent</dt>
        <dd>{exact ? "" : "≈ "}{formatAge(calibration.maxSecularAge, exact ? 6 : 3)}</dd>
      </dl>

      <h2 style={{ marginTop: "1.1rem" }}>Constraints</h2>
      <dl className="readout stacked">
        {constraints.map((c, i) => (
          <div key={c.label} style={{ display: "contents" }}>
            <dt>{c.label}</dt>
            <dd>
              {formatAge(c.trueAge)} → {formatAge(c.secularAge)}
              <br />
              <span style={{ color: "var(--text-muted)" }}>
                residual {residuals[i] === 0 ? "0" : residuals[i].toExponential(1)}
              </span>
            </dd>
          </div>
        ))}
        <dt>worst</dt>
        <dd>
          {maxAbsResidual === 0 ? "0" : maxAbsResidual.toExponential(1)}
          {maxAbsResidual < 1e-12 ? (
            <span style={{ color: "var(--ok)" }}> — exact</span>
          ) : null}
        </dd>
      </dl>

      {floodEnd ? (
        <>
          <h2 style={{ marginTop: "1.1rem" }}>Flood boundary — result</h2>
          <dl className="readout stacked">
            <dt>{floodEnd.label}</dt>
            <dd>
              {floodEnd.in_range ? (
                <>
                  {formatAge(floodEnd.secular_age)} lands at{" "}
                  {formatAge(floodEnd.true_age!, 5)} BP —{" "}
                  <strong>
                    {floodEnd.flood_days! < 400
                      ? `Flood day ${Math.round(floodEnd.flood_days!)}`
                      : `${Math.round(floodEnd.years_after_flood!)} yr after the Flood`}
                  </strong>
                  <br />
                  <span style={{ color: "var(--text-muted)" }}>
                    an output, not an input — this is what testing a Flood model
                    means
                  </span>
                </>
              ) : (
                <>beyond this calibration&rsquo;s range</>
              )}
            </dd>
          </dl>
        </>
      ) : null}

      {sourceKind === "precomputed" ? (
        <p className="notice" style={{ marginTop: "1rem", marginBottom: 0 }}>
          Values marked <strong>≈</strong> are interpolated between precomputed
          points and are good to about 0.3%. The parameters, residuals and the
          plotted curves themselves are exact — the solver produced them
          directly. Load the full model to make every value exact.
        </p>
      ) : null}
    </section>
  );
}
