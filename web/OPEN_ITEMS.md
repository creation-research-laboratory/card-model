# Open items — CARD web front end

Things known to be unresolved, with enough context to act on them without the
conversation that produced them. Kept in `web/` so it travels with the subtree
if this ever splits into its own repository.

Ordered by what would block publication first.

---

## 1. The Septuagint chronology is provisional

**Status:** blocks publication. Flagged in the data, surfaced in the UI.

`web/presets/presets.json` declares two chronologies, and they are **not on the
same footing**:

| | Masoretic | Septuagint |
| --- | --- | --- |
| `age_of_earth` | 6056 | **7500 — placeholder** |
| `flood_start_date` | 1656 | 2176 |
| Flood AGE | 4400 BP | 5324 BP *(the author's figure)* |
| `ice_age_end_date` | 3500 → 2556 BP | 3300 → 4200 BP |
| `provisional` | `false` | `true` |

The Masoretic entry is the package default (`card.chronology.DEFAULT_CHRONOLOGY`)
and is sound. For the Septuagint, only the Flood's AGE comes from the author's
presentation; `age_of_earth` was invented to make the arithmetic work, and the
Ice Age date is the author's stated AGE taken at face value rather than derived
the way Masoretic's is.

**To close:** get `age_of_earth`, `flood_start_date`, `flood_end_date` and
`ice_age_end_date` for the Septuagint from Rick, with a citation to display, then
set `provisional: false`. The UI already renders a warning notice while the flag
is true, so nothing else needs changing.

**Watch out for:** the DATE/AGE trap. `ice_age_end_date` counts years *after*
Creation. The author's presentation quotes "3,500 years before present" for the
Masoretic Ice Age; the package stores `3500` as a DATE, giving **2556 BP**, and
[CLAUDE.md](../CLAUDE.md) records fitting at 3500 YBP rather than 2556 as a past
bug. Same numeral, opposite convention. We deliberately use the DATE reading.

---

## 2. The anchor values are the author's, not the package's

**Status:** a decision, not a defect. One line either way.

`presets.json` uses **541 Ma / 66 Ma / 12 ka**, taken from the presentation.
The package's own shipped run config (`src/card/data/flood_only.yaml`) uses
**540 Ma / 66 Ma / 11.5 kyr**.

The consequence, for Masoretic / K-Pg:

| | this app (541 / 12 ka) | `card` reference (540 / 11.5 kyr) |
| --- | --- | --- |
| λ_F | 4.55e9 | 4.53e9 |
| k_F | 9.571 | 9.56 |
| k_PF | 0.00480 | 4.83e-3 |

Both are defensible. Switching to the package's would make the app reproduce
`card`'s documented numbers exactly, which has some value for anyone comparing
the two. Switching is editing `calibration` in `presets.json` and regenerating.

---

## 3. ICS unit boundaries are unverified

**Status:** blocks publication. Flagged in the data and shown in the UI.

`web/data/ics-units.json` carries 14 chronostratigraphic units, and the
generated payload records `ics: {version: "v2023/09", url:
"https://stratigraphy.org/chart", reviewed: false}`. The boundary ages were
entered from memory, **not transcribed from the published chart**.

**To close:** check each `base_secular_age` against the ICS chart at the recorded
version, then set `reviewed: true`. The geologic-column chart reads that flag and
labels itself provisional while it is false.

This is the same class of problem as item 1: no test in this repo can catch a
wrong boundary age, because the tests only check that the model computes
correctly on whatever it is handed.

---

## 4. The grid refinement window ignores the post-Flood tail

**Status:** accuracy, not correctness. Marked `KNOWN LIMITATION` in the code.

`_relaxation_span()` in `web/tools/generate_precomputed.py` sizes the age grid's
log-spaced refinement window from **`k_F` alone**. With two relaxation rates
three orders of magnitude apart, that covers the fast in-Flood drop (a few
years) and misses the millennia-long post-Flood tail.

Measured cost: the precomputed layer's worst interpolation error is **0.77%
forward / 0.86% inverse**, where the earlier single-rate curve managed 0.27%.
Those figures are advertised in the UI, in `types.ts`, in `interpolate.ts`, and
asserted in the live suite, so any fix has to move all four together.

**To close:** size the window from both rates — something like
`max(1.5·ln(λ_F)/k_F, 1.5·ln(λ_F2)/k_PF)` — re-measure, then update the four
places above. Expect the payload to grow; it is ~60 kB gzipped now, against a
~40 kB budget in the plan that has already been exceeded twice.

---

## 5. The Phase 2 boot stall was never explained

**Status:** open, not reproduced since.

During the Phase 2 spike, roughly half of repeated page loads in one long-lived
browser process hung inside `loadPyodide` — after the wasm had fully downloaded
(server logs confirm), promise neither resolving nor rejecting, no console error,
main-thread heap at 1.2 MB on a 32 GB machine. Headless Node ran 6/6 with the
identical sequence.

Phase 4 re-tested it: **4 load-and-boot cycles, no stall**, times 3.1 / 11.4 /
16.1 / 13.6 s — high variance on a loaded machine but not a monotonic climb.
`worker.terminate()` on `pagehide` is in place and was not sufficient on its own
when it did occur.

Four cycles is a small sample and the original failure needed repeated loads to
appear. Phase 5 makes boots far more frequent (a slider is the gesture that
triggers one), so it is worth watching there. If it recurs with real users it is
a go/no-go issue, and the fallback ladder is in `../frontend_plan.md` §14.

---

## 6. Untested on real low-end hardware

**Status:** open.

Pyodide holds ~50–100 MB resident. Every measurement so far is a desktop browser
or headless Node; the throttling used in Phase 2 models bandwidth but not a
slower CPU or a tighter memory ceiling. "Mid-range phone", from the original
Phase 2 brief, remains genuinely unmeasured.

---

## 7. Housekeeping

- **`experiment/two-part-flood-decay`** holds the plateau experiment
  (`experiments/two_part_flood.py`), committed but never pushed. Superseded by
  the authors' model — their in-Flood exponential is a better answer than its
  constant plateau — but its three-constraint solve is what diagnosed the
  disparity, so it is worth keeping until the model settles.
- **Merges from `main` need checking by hand.** PR #12 was authored against a
  Phase-3-era front end; git merged it without a conflict and the result blanked
  the app (a field the render path indexes had vanished from
  `precomputed.json`) and silently reverted ~20 tests. After any merge from
  main, confirm: `generate_precomputed.py --check` passes, the web test counts
  have not dropped, and the app renders.
- **`web/spike/`** is Phase 2 measurement scaffolding. It still builds and is
  the only thing exercising the Worker path by hand, but nothing depends on it.

---

## What is *not* open

Recorded so these do not get re-litigated:

- **The model structure.** The authors confirmed the GitHub model now matches
  the presentation: an in-Flood relaxation at `k_F` handing over continuously to
  a post-Flood one at `k_PF`. λ jumps only at `t_F`. Verified — 316,979 either
  side of `t_F2`.
- **Which pairs calibrate it.** Three: the pre-Flood contact at the onset, the
  post-Flood contact a year later, and the end of the Ice Age. Both the
  generator and `bridge.py` call `solve_flood_rate`.
- **That the Flood year is one year.** Confirmed twice, and the model treats its
  length as an input rather than an unknown.
