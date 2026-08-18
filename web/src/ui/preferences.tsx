/**
 * Display preferences that outlive the tab.
 *
 * One preference so far — power-user mode, which strips the explanatory prose
 * and tightens the layout. It is a *display* choice and nothing else: no
 * number, unit, warning or error depends on it, and it never reaches the
 * model. That boundary is what makes it safe to persist and restore blind.
 *
 * Storage is best-effort. `localStorage` is not merely absent in some
 * configurations — reading the property itself throws when a browser is set to
 * block site data, and Safari's private mode has historically thrown on
 * `setItem` once a quota is hit. A preference is not worth a blank page, so
 * every access is guarded and failure degrades to the default rather than
 * propagating.
 */

import {
  createContext, useCallback, useContext, useEffect, useMemo, useState,
  type ReactNode,
} from "react";

export interface Preferences {
  /** Hide explanation, tighten spacing. */
  powerUser: boolean;
}

const DEFAULTS: Preferences = { powerUser: false };

/**
 * Versioned, so a future preference with a different shape can be added
 * without having to interpret whatever an older build wrote.
 */
export const STORAGE_KEY = "card.preferences.v1";

/** Never throws. Anything unreadable, unparseable or ill-typed is a default. */
export function readPreferences(): Preferences {
  let raw: string | null = null;
  try {
    raw = globalThis.localStorage?.getItem(STORAGE_KEY) ?? null;
  } catch {
    return { ...DEFAULTS };
  }
  if (!raw) return { ...DEFAULTS };

  try {
    const parsed: unknown = JSON.parse(raw);
    if (typeof parsed !== "object" || parsed === null) return { ...DEFAULTS };
    const { powerUser } = parsed as Record<string, unknown>;
    // Field by field rather than a cast: a stored `"true"` from some future
    // build must not turn into a truthy boolean by accident.
    return {
      powerUser: typeof powerUser === "boolean" ? powerUser : DEFAULTS.powerUser,
    };
  } catch {
    return { ...DEFAULTS };
  }
}

/** Never throws. A refused write just means the choice lasts one session. */
export function writePreferences(preferences: Preferences): void {
  try {
    globalThis.localStorage?.setItem(STORAGE_KEY, JSON.stringify(preferences));
  } catch {
    /* storage blocked or full; the in-memory value still applies */
  }
}

interface Store {
  powerUser: boolean;
  setPowerUser(value: boolean): void;
}

const PreferencesContext = createContext<Store>({
  powerUser: DEFAULTS.powerUser,
  setPowerUser: () => {},
});

export function PreferencesProvider({ children }: { children: ReactNode }) {
  // Read synchronously, so the first paint is already in the right mode.
  // Nothing renders before `precomputed.json` resolves, so this beats it.
  const [powerUser, setPowerUserState] = useState(() => readPreferences().powerUser);

  const setPowerUser = useCallback((value: boolean) => {
    setPowerUserState(value);
    writePreferences({ powerUser: value });
  }, []);

  // Spacing is a stylesheet's job, not a component's: one attribute drives
  // every density rule, instead of a conditional class on each panel.
  useEffect(() => {
    document.documentElement.dataset.power = powerUser ? "on" : "off";
  }, [powerUser]);

  const value = useMemo(
    () => ({ powerUser, setPowerUser }), [powerUser, setPowerUser],
  );
  return (
    <PreferencesContext.Provider value={value}>
      {children}
    </PreferencesContext.Provider>
  );
}

/**
 * True when the reader has asked for less explanation.
 *
 * Use it to drop *prose*. Never use it to drop a warning, an error, a unit or
 * a caveat — those are the content, and a reader who wants a denser view has
 * not asked to be told less about what the numbers mean.
 */
export function usePowerUser(): boolean {
  return useContext(PreferencesContext).powerUser;
}

export function usePreferences(): Store {
  return useContext(PreferencesContext);
}
