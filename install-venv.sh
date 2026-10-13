#!/usr/bin/env bash
# Build an ISOLATED virtualenv (.venv) so pip installs never collide with the
# conda/miniforge envs (comfyui, qwen3-tts, vastai). This is what fixes the
# classic "pip vs cachyos/conda" package conflict.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$ROOT/.venv"
PY="${PYTHON:-python3}"

if [ -x "$ROOT/venv/bin/python" ]; then
  echo "!! old symlinked venv present — remove it before rebuild:" >&2
  echo "   rm -rf $ROOT/venv" >&2
fi

rm -rf "$VENV"
"$PY" -m venv "$VENV"
source "$VENV/bin/activate"
echo "== upgrading pip/wheel =="
pip install --upgrade pip wheel >/dev/null
echo "== installing requirements.txt (this can take a few minutes) =="
python -m pip install -r "$ROOT/requirements.txt"
deactivate

cat <<EOF

✅ .venv ready at $VENV

verify isolation:
  $VENV/bin/python -c "import sys; print(sys.executable)"
  # should point INSIDE .venv (NOT /usr/bin/python3.14)

then launch the toolbox:
  ./run.sh
EOF
