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
  /** Not a constraint: what the model says the Ice Age should date to. */
  iceAgePrediction?: { true_age: number; secular_age: number };
}

export function CalibrationReadout({
  calibration, sourceKind, iceAgePrediction,
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
      <dl className="readout">
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

      {iceAgePrediction ? (
        <>
          <h2 style={{ marginTop: "1.1rem" }}>Prediction</h2>
          <dl className="readout">
            <dt>End of the Ice Age</dt>
            <dd>
              {formatAge(iceAgePrediction.true_age)} →{" "}
              {formatAge(iceAgePrediction.secular_age)}
              <br />
              <span style={{ color: "var(--text-muted)" }}>
                not a constraint — with the acceleration confined to the Flood,
                post-Flood rock is essentially uninflated
              </span>
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
