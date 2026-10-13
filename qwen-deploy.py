#!/usr/bin/env python3
"""Unify the three monolithic qwen36 deployers (run-scripts/qwen36-*.sh) behind a
small CLI so you can also inspect / stop them without re-running the full build:

  qwen-deploy.py <action> <variant>

actions : deploy | status | stop | logs
variants: 8B | 12B | 24B   (maps to run-scripts/qwen36-27B-{8,12,24}B.sh)

"deploy" runs the existing script in the foreground. "status/stop/logs" resolve
the latest running instance via the VastAI API and SSH into it (root@<ip>:<port>)
using ~/.ssh/id_ed25519 or id_rsa; if no key is attached yet, deploy first so one
gets added automatically.
"""

import os
import sys
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VAST_API = "https://console.vast.ai/api/v0"
SCRIPTS = {
    "8B": "qwen36-27B-8GB.sh",
    "12B": "qwen36-27B-12B.sh",
    "24B": "qwen36-27B-24B.sh",
}
VARIANT_PORTS = {
    "8B": 12888,
    "12B": 12889,
    "24B": 12890,
}


def fail(msg):
    print(f"!! {msg}", file=sys.stderr)
    sys.exit(1)


def _api_key():
    keyfile = os.path.expanduser("~/.config/vastai/vast_api_key")
    if not os.path.exists(keyfile):
        fail(f"API key missing at {keyfile}")
    return Path(keyfile).read_text().strip()


def latest_running_instance(api_key: str, verbose=False) -> dict | None:
    cmd = ["curl", "-sL", f"{VAST_API}/instances?owner=me&api_key={api_key}"]
    out = subprocess.run(cmd, capture_output=True, text=True).stdout.strip()
    try:
        data = json.loads(out)
    except Exception as e:
        fail(f"could not parse API response ({e})")
    running = [i for i in data.get("instances", []) if i.get("cur_state") == "running"]
    if not running:
        return None
    latest = max(running, key=lambda x: x.get("id", 0))
    if verbose:
        print(f"latest running instance id={latest.get('id')} gpu={latest.get('gpu_name')}", file=sys.stderr)
    return latest


def _ssh_command(host: str, port: int):
    for name in ("~/.ssh/id_ed25519", "~/.ssh/id_rsa"):
        key = os.path.expanduser(name)
        if os.path.exists(key):
            base = ["ssh", "-p", str(port), "-o", "StrictHostKeyChecking=no",
                    "-o", "UserKnownHostsFile=/dev/null", "-o", "ConnectTimeout=15",
                    "-i", key, "-o", "LogLevel=ERROR", f"root@{host}"]
            return base
    fail("no ssh private key found under ~/.ssh (deploy adds one automatically)")


def _latest_ssh(target_variant=None):
    api_key = _api_key()
    inst = latest_running_instance(api_key)
    if not inst:
        fail("no running instance. Run 'qwen-deploy.py deploy <variant>' first.")
    host = inst.get("public_ipaddr") or "0.0.0.0"
    port = int(inst.get("direct_port_start", 22))
    return _ssh_command(host, port)


def action_deploy(variant: str):
    script = ROOT / "run-scripts" / SCRIPTS[variant]
    if not script.exists():
        fail(f"{script.name} not found")
    print(f"[qwen-deploy] running {script.name} (foreground)...", file=sys.stderr)
    return subprocess.run(["bash", str(script)]).returncode


def action_status(variant: str):
    ssh = _latest_ssh(variant)
    local_port = VARIANT_PORTS[variant]
    checks = {
        "gpu": f'nvidia-smi --query-gpu=name,memory.used,memory.total,utilization.gpu --format=csv,noheader,nounits',
        "health": f'curl -s --max-time 5 http://localhost:{local_port}/health || echo "server not reachable on :{local_port}"',
        "process": "ps aux | grep -i llama-server | grep -v grep | head -n 1 || true",
    }
    for label, cmd in checks.items():
        r = subprocess.run(ssh + ["bash", "-lc", cmd], capture_output=True, text=True)
        print(f"\n== {label} ==")
        out = (r.stdout or "").strip()
        print(out if out else "(no output / server not responding)")


def action_stop(variant: str):
    ssh = _latest_ssh(variant)
    local_port = VARIANT_PORTS[variant]
    r = subprocess.run(ssh + ["bash", "-lc", f"pkill -f llama-server || echo killed"], capture_output=True, text=True)
    print("stop result:", (r.stdout or "").strip() or "(nothing running)")


def action_logs(variant: str):
    ssh = _latest_ssh(variant)
    lines = len(sys.argv[2:]) > 1 and sys.argv[-1].lstrip("-").isdigit()
    n = int(sys.argv[-1]) if isinstance(lines, bool) and lines else 50
    r = subprocess.run(ssh + ["tail", "-n", str(n), "/workspace/llama-server.log"], capture_output=True, text=True)
    print((r.stdout or "").strip() or "(no log yet)")


USAGE = """usage: qwen-deploy.py <action> <variant>

  action : deploy | status | stop | logs
  variant: 8B | 12B | 24B
"""


def main():
    if len(sys.argv) != 3 or sys.argv[1] not in ("deploy", "status", "stop", "logs"):
        print(USAGE, file=sys.stderr)
        return 1
    action, variant = sys.argv[1], sys.argv[2]
    if variant not in SCRIPTS:
        fail(f"unknown variant {variant!r} (expected one of {', '.join(SCRIPTS)})")
    dispatch = {"deploy": action_deploy, "status": action_status, "stop": action_stop, "logs": action_logs}[action]
    return dispatch(variant)


if __name__ == "__main__":
    raise SystemExit(main())
