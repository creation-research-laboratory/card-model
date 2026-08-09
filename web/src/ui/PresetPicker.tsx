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
  const bound = data.boundaries[boundary];

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
        <span>Flood ends at</span>
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
        The Flood <em>begins</em> at the {data.flood_start_boundary.label}{" "}
        boundary in every scenario — that is the pre-Flood contact, and it is
        where the decay rate spikes. What you choose here is where Flood
        deposition <em>ceased</em>.
      </p>

      <dl className="readout">
        <dt>Earth</dt>
        <dd>{formatAge(chron.age_of_earth)}</dd>
        <dt>Flood onset</dt>
        <dd>
          {formatAge(chron.flood_start_age)} BP → appears{" "}
          {formatAge(data.flood_start_boundary.secular_age)}
        </dd>
        <dt>Flood ends</dt>
        <dd>
          {formatAge(chron.flood_deposition_end_age)} BP → appears{" "}
          {formatAge(bound.secular_age)}
        </dd>
      </dl>
    </section>
  );
}
