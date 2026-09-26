#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
if [[ ! -x .venv/bin/python ]]; then
  echo 'Create the environment first: uv venv --python 3.12 && uv pip install -e ".[demo,dev]"' >&2
  exit 1
fi
lake build
exec env -u PYTHONPATH .venv/bin/python -m fluxkernel.demo.server "$@"
