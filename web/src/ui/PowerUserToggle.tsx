/**
 * The switch for power-user mode.
 *
 * A checkbox rather than a styled button: the state is a binary the reader
 * needs to perceive at a glance, and a native checkbox reports it to
 * assistive technology without any aria plumbing.
 */

import { usePreferences } from "./preferences.js";

export function PowerUserToggle() {
  const { powerUser, setPowerUser } = usePreferences();

  return (
    <label
      className="power-toggle"
      title={
        "Hides the explanatory text and tightens the layout. " +
        "Warnings, errors and units are always shown."
      }
    >
      <input
        type="checkbox"
        checked={powerUser}
        onChange={(e) => setPowerUser(e.target.checked)}
      />
      <span>Power user</span>
    </label>
  );
}
