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
import { lambdaF2 } from "../charts/breakpoints.js";

interface Props {
  calibration: Calibration;
  sourceKind: SourceKind;
}

export function CalibrationReadout({ calibration, sourceKind }: Props) {
  // Derived from the parameters in hand, never looked up from the preset
  // table: `lambda_F2` is pinned by continuity at t_F2, so an overridden
  // lambda_F or k_F changes it, and a table lookup would keep reporting the
  // value the preset was solved with.
  const lambdaF2Value = lambdaF2(calibration.params);
  const { params, constraints, residuals, maxAbsResidual, exact } = calibration;

  return (
    <section className="panel" aria-labelledby="calibration-heading">
      <h2 id="calibration-heading">Calibration</h2>

      <dl className="readout">
        <dt>λ<sub>F</sub> (peak, at onset)</dt>
        <dd>{formatMultiplier(params.lambda_F)}× background</dd>
        <dt>k<sub>F</sub> (in Flood)</dt>
        <dd>{trim(params.k_F, 6)} yr⁻¹</dd>
        <dt>k<sub>PF</sub> (after)</dt>
        <dd>{trim(params.k_PF, 6)} yr⁻¹</dd>
        {Number.isFinite(lambdaF2Value) ? (
          <>
            <dt>λ at Flood&rsquo;s end</dt>
            <dd>
              {formatMultiplier(lambdaF2Value)}×{" "}
              <span style={{ color: "var(--text-muted)" }}>
                (÷{formatMultiplier(params.lambda_F / lambdaF2Value)} inside the year)
              </span>
            </dd>
          </>
        ) : null}
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

      {sourceKind === "precomputed" ? (
        <p className="notice" style={{ marginTop: "1rem", marginBottom: 0 }}>
          Values marked <strong>≈</strong> are interpolated between precomputed
          points: good to about 0.8% converting a true age forwards, and about
          0.9% converting an apparent age back. The parameters, residuals and the
          plotted curves themselves are exact — the solver produced them
          directly. Load the full model to make every value exact.
        </p>
      ) : null}
    </section>
  );
}
