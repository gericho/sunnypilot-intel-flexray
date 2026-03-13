#!/usr/bin/env bash
set -euo pipefail

cd "$HOME/sunnypilot"

# Attiva il virtualenv
# shellcheck disable=SC1091
source .venv/bin/activate

# Lancia Cabana
exec tools/cabana/cabana "$@"
