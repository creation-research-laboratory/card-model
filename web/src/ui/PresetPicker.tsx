/**
 * The two dropdowns.
 *
 * The axes are different kinds of thing and the UI says so: a **chronology**
 * changes the timeline itself, a **boundary** changes which stratigraphic
 * horizon the Flood is pinned to. Presenting them as one flat list of six
 * would hide that.
 *
 * Options come from the data, never from a hardcoded list, so adding a preset
 * to `presets.json` adds an option here with no change to this file.
 */

import type { PrecomputedData } from "../model/PrecomputedSource.js";
import { formatAge } from "../charts/format.js";

interface Props {
  data: PrecomputedData;
  chronology: string;
  boundary: string;
  onChronology(key: string): void;
  onBoundary(key: string): void;
  disabled?: boolean;
}

export function PresetPicker({
  data, chronology, boundary, onChronology, onBoundary, disabled,
}: Props) {
  const chron = data.chronologies[chronology];

  return (
    <section className="panel" aria-labelledby="preset-heading">
      <h2 id="preset-heading">Preset</h2>

      <label className="field">
        <span>Chronology</span>
        <select
          value={chronology}
          disabled={disabled}
          onChange={(e) => onChronology(e.target.value)}
        >
          {Object.entries(data.chronologies).map(([key, c]) => (
            <option key={key} value={key}>{c.label}</option>
          ))}
        </select>
      </label>

      {chron?.provisional ? (
        <p className="notice" style={{ marginTop: "-.4rem" }}>
          <strong>Provisional values.</strong> This chronology&rsquo;s dates are
          placeholders pending review and a citation. Treat the numbers as
          illustrative.
        </p>
      ) : null}

      <label className="field">
        <span>Post-Flood boundary (1 yr after onset)</span>
        <select
          value={boundary}
          disabled={disabled}
          onChange={(e) => onBoundary(e.target.value)}
        >
          {Object.entries(data.boundaries).map(([key, b]) => (
            <option key={key} value={key}>{b.label}</option>
          ))}
        </select>
      </label>

      <p style={{ fontSize: ".8rem", color: "var(--text-secondary)", margin: "0 0 .8rem" }}>
        The Flood <em>begins</em> at the {data.calibration.flood_start.label}{" "}
        contact in every scenario, and the rate spikes there. This choice sets
        where it has fallen to a year later. A third date &mdash; the end of the
        Ice Age &mdash; fixes how slowly it relaxes over the millennia after.
      </p>

      <h2 style={{ marginTop: "1.1rem" }}>Calibrated on</h2>
      <dl className="readout stacked">
        <dt>Flood onset — {data.calibration.flood_start.label}</dt>
        <dd>
          {formatAge(chron.flood_start_age)} BP → appears{" "}
          {formatAge(data.calibration.flood_start.secular_age)}
        </dd>
        <dt>One year later — {data.boundaries[boundary].label}</dt>
        <dd>
          {formatAge(chron.post_flood_boundary_age)} BP → appears{" "}
          {formatAge(data.boundaries[boundary].secular_age)}
        </dd>
        <dt>{data.calibration.ice_age_end.label}</dt>
        <dd>
          {formatAge(chron.ice_age_end_age)} BP → appears{" "}
          {formatAge(data.calibration.ice_age_end.secular_age)}
        </dd>
        <dt>Age of the Earth</dt>
        <dd>{formatAge(chron.age_of_earth)}</dd>
      </dl>
    </section>
  );
}
