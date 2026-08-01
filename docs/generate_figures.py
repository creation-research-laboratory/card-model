#!/usr/bin/env python3
"""
Regenerate the figures the documentation gallery embeds.

Run before `mkdocs build` (the docs workflow does), or any time you want the
gallery to match the current code:

    python docs/generate_figures.py

The figures land in ``docs/img/``, which is **not** committed — ``*.png`` is
gitignored and these are derived artifacts. A local `mkdocs serve` without
running this shows the gallery's alt text instead of images, which is the right
failure: nothing is silently out of date.

Each example script writes its PNG to the current directory, so this simply
runs them with ``docs/img/`` as the working directory rather than duplicating
their plotting code.
"""

import os
import runpy
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
EXAMPLES = os.path.join(REPO_ROOT, "examples")
IMG_DIR = os.path.join(HERE, "img")

#: Scripts whose figures the gallery embeds.  The MCMC driver is deliberately
#: absent: it needs a sampling run, and the gallery links to the tutorial
#: instead of showing its output.
SCRIPTS = (
    "plot_general_model.py",
    "plot_model_calibration.py",
    "plot_model_calibration_joint.py",
    "demo_parameter_sweep.py",
)


def main() -> int:
    # Keep matplotlib off any windowing system.  Setting this here, in a
    # script, is fine; the package itself must never call matplotlib.use().
    os.environ.setdefault("MPLBACKEND", "Agg")

    os.makedirs(IMG_DIR, exist_ok=True)
    original_dir = os.getcwd()
    os.chdir(IMG_DIR)
    try:
        for script in SCRIPTS:
            path = os.path.join(EXAMPLES, script)
            print(f"running {script}")
            runpy.run_path(path, run_name="__main__")
    finally:
        os.chdir(original_dir)

    written = sorted(f for f in os.listdir(IMG_DIR) if f.endswith(".png"))
    print(f"\n{len(written)} figure(s) in docs/img/:")
    for name in written:
        print(f"  {name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
