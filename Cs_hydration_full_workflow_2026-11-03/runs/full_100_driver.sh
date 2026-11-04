#!/usr/bin/env bash
# Linux counterpart of full_100_driver.ps1: same process, same lock, same stages.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PATH="/usr/local/bin:/opt/xtb-6.7.1/xtb-dist/bin:${PATH}"
export XTBHOME="/opt/xtb-6.7.1/xtb-dist"
export XTBPATH="${XTBHOME}/share/xtb"
export PYTHONUNBUFFERED=1
export PYTHONUTF8=1
export PYTHONIOENCODING=utf-8
export OMP_NUM_THREADS="${OMP_NUM_THREADS:-1}"
export MKL_NUM_THREADS="${MKL_NUM_THREADS:-1}"
export OMP_DYNAMIC=FALSE
PY="${ROOT}/.venv/bin/python"
exec "$PY" "${ROOT}/scripts/cs_driver.py" --critfreq 125.0 --workers 5 --relax-workers 4 --threads 1 "$@"
