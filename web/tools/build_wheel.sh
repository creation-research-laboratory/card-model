#!/usr/bin/env bash
# Build the card wheel from this repo into web/public/.
#
# Built from the checkout rather than installed from PyPI, so the model running
# in the browser is the model in src/ at the commit that deployed it. That is
# what makes the whole approach drift-free.
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
web="$(dirname "$here")"
repo="$(dirname "$web")"
python="${PYTHON:-python3}"

mkdir -p "$web/public"
rm -f "$web/public"/card_model-*.whl
"$python" -m build --wheel --outdir "$web/public" "$repo"
ls -la "$web/public"/card_model-*.whl
