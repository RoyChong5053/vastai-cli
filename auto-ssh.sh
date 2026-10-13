#!/bin/bash
# Auto-SSH wrapper using local venv

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
"$SCRIPT_DIR/venv/bin/python" "$SCRIPT_DIR/auto-ssh.py" "$@"