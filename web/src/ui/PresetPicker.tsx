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
import { usePowerUser } from "./preferences.js";

interface Props {
  data: PrecomputedData;
  chronology: string;
  boundary: string;
  onChronology(key: string): void;
  onBoundary(key: string): void;
  iceAge: string;
  onIceAge(key: string): void;
  disabled?: boolean;
}

export function PresetPicker({
  data, chronology, boundary, iceAge, onChronology, onBoundary, onIceAge,
  disabled,
}: Props) {
  const powerUser = usePowerUser();
  const chron = data.chronologies[chronology];

  /**
   * Help for one control, directly beneath it.
   *
   * Hidden rather than removed in power-user mode: each select points at its
   * help with `aria-describedby`, so dropping the node would strip the
   * description from the accessibility tree rather than merely from view —
   * the same bargain `ParameterPanel` makes with its parameter descriptions.
   */
  const help = (id: string, body: React.ReactNode) => (
    <p id={id} className={powerUser ? "visually-hidden" : "field-help"}>
      {body}
    </p>
  );

  return (
    <section className="panel" aria-labelledby="preset-heading">
      <h2 id="preset-heading">Preset</h2>

      {/*
        * The one fact that is not about any single control: it is true in
        * every scenario, so it frames the panel rather than sitting under the
        * last select — which is where it used to be, describing the two
        * controls above it as "this choice".
        */}
      {powerUser ? null : (
        <p className="field-help" style={{ margin: "-.25rem 0 .8rem" }}>
          The Flood <em>begins</em> at the{" "}
          {data.calibration.flood_start.label} contact in every scenario, and
          the decay rate spikes there. These three choices fix what happens
          next.
        </p>
      )}

      <label className="field">
        <span>Chronology</span>
        <select
          id="preset-chronology"
          aria-describedby="preset-chronology-help"
          value={chronology}
          disabled={disabled}
          onChange={(e) => onChronology(e.target.value)}
        >
          {Object.entries(data.chronologies).map(([key, c]) => (
            <option key={key} value={key}>{c.label}</option>
          ))}
        </select>
      </label>
      {help("preset-chronology-help",
        <>Sets the Flood&rsquo;s dates and the age of the Earth.</>)}

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
          id="preset-boundary"
          aria-describedby="preset-boundary-help"
          value={boundary}
          disabled={disabled}
          onChange={(e) => onBoundary(e.target.value)}
        >
          {Object.entries(data.boundaries).map(([key, b]) => (
            <option key={key} value={key}>{b.label}</option>
          ))}
        </select>
      </label>
      {help("preset-boundary-help",
        <>Which contact the Flood <em>ends</em> at, a year after it began — so
        this is how far the rate has fallen inside that year.</>)}

      <label className="field">
        <span>Ice Age ends (yr after the Flood)</span>
        <select
          id="preset-ice-age"
          aria-describedby="preset-ice-age-help"
          value={iceAge}
          disabled={disabled}
          onChange={(e) => onIceAge(e.target.value)}
        >
          {/*
            * Sorted by the offset this chronology gives, so the list reads in
            * time order. Each chronology's own date is one of the options, and
            * it is far later than the rest — 1,843 yr for Masoretic — so
            * leaving it unsorted would drop it in the middle.
            */}
          {Object.entries(data.ice_age_offsets.options)
            .sort((a, b) => a[1].years_after_flood[chronology]
                          - b[1].years_after_flood[chronology])
            .map(([key, o]) => (
              <option key={key} value={key}>
                {key === "default"
                  ? `${o.years_after_flood[chronology].toLocaleString()} yr (chronology default)`
                  : `${o.years_after_flood[chronology].toLocaleString()} yr`}
              </option>
            ))}
        </select>
      </label>

      {help("preset-ice-age-help",
        <>The third matched date. It fixes how slowly the rate relaxes over the
        millennia after the Flood.</>)}

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
          {/* The chosen offset, not the chronology's own, which is only right
              for the `default` option. */}
          {formatAge(
            chron.age_of_earth - chron.flood_end_date
            - data.ice_age_offsets.options[iceAge].years_after_flood[chronology],
          )} BP → appears{" "}
          {formatAge(data.calibration.ice_age_end.secular_age)}
        </dd>
        <dt>Age of the Earth</dt>
        <dd>{formatAge(chron.age_of_earth)}</dd>
      </dl>
    </section>
  );
}
