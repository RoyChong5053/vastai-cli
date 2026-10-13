#!/usr/bin/env bash
# VastAI CLI toolbox — single launcher for all sub-tools (instances, comfyui, ssh, qwen, rclone).
# Passes any extra args straight to the interactive TUI menu; `--no-tui` uses a simple text menu.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PY="$ROOT/.venv/bin/python"

if [ -x "$VENV_PY" ]; then
  EXEC=("$VENV_PY")
else
  echo "!! .venv not built yet. Run: bash install-venv.sh   (then re-run ./run.sh)" >&2
  exec python3 tui.py "$@"
fi

exec "$EXEC" "$ROOT/tui.py" "$@"
