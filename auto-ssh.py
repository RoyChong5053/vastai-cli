#!/usr/bin/env python3
"""
Auto-SSH: Simplified workflow for connecting to VastAI instances
- Fetches latest instance info from VastAI API
- Auto copies SSH key if needed
- Auto connects via SSH
"""

import os
import sys
import json
import logging
import argparse
import subprocess
from typing import Optional, Dict, Any

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_VENV_DIR = os.path.join(_SCRIPT_DIR, "venv")
_VENV_PYTHON = os.path.join(_VENV_DIR, "bin", "python")

# Re-exec inside the local venv so we never touch the system/CachyOS Python.
if os.path.exists(_VENV_PYTHON) and os.path.realpath(sys.prefix) != os.path.realpath(
    _VENV_DIR
):
    os.execv(_VENV_PYTHON, [_VENV_PYTHON, os.path.abspath(__file__), *sys.argv[1:]])

sys.path.insert(0, _SCRIPT_DIR)

from config import Config
from utils import setup_logging


def get_venv_python() -> str:
    """Get path to venv python"""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(script_dir, "venv", "bin", "python")


def get_venv_pip() -> str:
    """Get path to venv pip"""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(script_dir, "venv", "bin", "pip")


def get_venv_bin() -> str:
    """Get path to venv bin"""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(script_dir, "venv", "bin")


def run_venv_cmd(cmd: list, timeout: int = 30) -> subprocess.CompletedProcess:
    """Run command using venv"""
    env = os.environ.copy()
    env["PATH"] = get_venv_bin() + ":" + env.get("PATH", "")
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=env)


def find_ssh_key() -> Optional[str]:
    """Find the user's SSH public key"""
    for key_path in Config.SSH_KEY_PATHS:
        expanded_path = os.path.expanduser(key_path)
        if os.path.exists(expanded_path):
            logging.info(f"Found SSH key: {expanded_path}")
            return expanded_path
    logging.warning("No SSH public key found")
    return None


def update_instances_json() -> Optional[Dict[str, Any]]:
    """Fetch instances from VastAI and save to instances.json"""
    instances_file = "instances.json"

    print("📥 Fetching instances from VastAI...")

    result = run_venv_cmd(["vastai", "show", "instances", "--raw"], timeout=30)

    if result.returncode != 0:
        print(f"❌ Failed to fetch instances: {result.stderr}")
        return None

    try:
        # Parse the output - vastai show instances returns JSON
        instances = json.loads(result.stdout)

        if not instances:
            print("❌ No instances found")
            return None

        # Save to file
        with open(instances_file, "w") as f:
            json.dump(instances, f, indent=2)

        print(f"✓ Updated {instances_file}")
        return instances

    except json.JSONDecodeError as e:
        print(f"❌ Failed to parse instances: {e}")
        return None


def attach_ssh_key(instance_id: int, ssh_key_path: str) -> bool:
    """Attach SSH public key to instance via VastAI CLI"""
    logging.info(f"Attaching SSH key to instance {instance_id}")

    cmd = ["vastai", "attach", "ssh", str(instance_id), ssh_key_path]
    print(f"🔑 Attaching SSH key to instance {instance_id}...")

    result = run_venv_cmd(cmd, timeout=30)

    if result.returncode == 0:
        print("✓ SSH key attached successfully")
        return True
    else:
        error_msg = result.stderr.lower()
        if "already" in error_msg:
            print("✓ SSH key already attached")
            return True
        print(f"❌ Failed to attach SSH key: {result.stderr}")
        return False


def get_ssh_url(instance_id: int) -> Optional[str]:
    """Get SSH URL from vastai"""
    cmd = ["vastai", "ssh-url", str(instance_id)]
    result = run_venv_cmd(cmd, timeout=10)

    if result.returncode == 0:
        return result.stdout.strip()
    return None


def parse_ssh_url(ssh_url: str) -> Optional[Dict[str, str]]:
    """Parse SSH URL to get host, port, user"""
    if ssh_url.startswith("ssh://"):
        ssh_url = ssh_url[6:]

    if "@" not in ssh_url:
        return None

    user_host, host_port = ssh_url.split("@", 1)
    if ":" not in host_port:
        return None

    host, port = host_port.split(":", 1)
    return {"host": host, "port": port, "user": user_host}


def build_ssh_command(host: str, port: str, user: str = "root") -> list:
    """Build SSH command with port forwarding"""
    return [
        "ssh",
        "-p",
        str(port),
        f"{user}@{host}",
        "-L",
        "8080:localhost:8080",
        "-L",
        "8288:localhost:8288",
        "-o",
        "StrictHostKeyChecking=no",
        "-o",
        "UserKnownHostsFile=/dev/null",
        "-t",
        "TERM=xterm-256color",
        "bash",
    ]


def update_rclone_config(host: str, port: str) -> bool:
    """Update rclone config for vastai remote"""
    rclone_config = os.path.expanduser("~/.config/rclone/rclone.conf")

    if not os.path.exists(rclone_config):
        print(f"⚠️  rclone config not found: {rclone_config}")
        return False

    print(f"\n📝 Updating rclone config...")

    # Read existing config
    with open(rclone_config, "r") as f:
        config_lines = f.readlines()

    # Find and update vastai remote
    new_config = []
    in_vastai_section = False
    updated = False

    for line in config_lines:
        if line.strip().startswith("[") and "vastai" in line.lower():
            in_vastai_section = True
            new_config.append(line)
            continue

        if in_vastai_section:
            if line.strip().startswith("["):
                in_vastai_section = False

            if line.startswith("host = "):
                new_config.append(f"host = {host}\n")
                print(f"   Updated host: {host}")
                updated = True
                continue
            elif line.startswith("port = "):
                new_config.append(f"port = {port}\n")
                print(f"   Updated port: {port}")
                updated = True
                continue

        new_config.append(line)

    if updated:
        # Backup original
        backup_file = rclone_config + ".bak"
        with open(backup_file, "w") as f:
            f.writelines(config_lines)

        # Write updated config
        with open(rclone_config, "w") as f:
            f.writelines(new_config)

        print(f"✓ rclone config updated (backup: {backup_file})")
        return True
    else:
        print("⚠️  No vastai remote found in config")
        return False


def connect_ssh(ssh_cmd: list) -> None:
    """Execute SSH connection"""
    print(f"\n🔗 Connecting...")
    print("   " + " ".join(ssh_cmd))
    print("\nUse 'exit' to disconnect.\n")
    print("-" * 50)

    os.execvp("ssh", ssh_cmd)


def get_latest_instance(instances: list) -> Optional[Dict[str, Any]]:
    """Get the most recently created running instance"""
    if not instances:
        return None

    # Filter running instances and sort by ID descending
    running = [i for i in instances if i.get("state") == "running"]
    if running:
        sorted_instances = sorted(running, key=lambda x: x.get("id", 0), reverse=True)
        return sorted_instances[0]

    # If no running, get any instance
    sorted_instances = sorted(instances, key=lambda x: x.get("id", 0), reverse=True)
    return sorted_instances[0]


def main():
    parser = argparse.ArgumentParser(description="Auto-SSH to VastAI instance")
    parser.add_argument("--instance-id", type=int, help="Specific instance ID")
    parser.add_argument(
        "--skip-key", action="store_true", help="Skip SSH key attachment"
    )
    parser.add_argument(
        "-y", "--yes", action="store_true", help="Auto-confirm all actions"
    )
    parser.add_argument(
        "--skip-rclone", action="store_true", help="Skip rclone config update"
    )
    args = parser.parse_args()

    setup_logging("auto-ssh.log")
    logging.info("Starting Auto-SSH")

    print("🤖 Auto-SSH for VastAI")
    print("=" * 40)

    # Fetch latest instances from VastAI
    instances = update_instances_json()
    if not instances:
        sys.exit(1)

    # Get instance
    if args.instance_id:
        instance = next((i for i in instances if i.get("id") == args.instance_id), None)
        if not instance:
            print(f"❌ Instance {args.instance_id} not found")
            sys.exit(1)
    else:
        instance = get_latest_instance(instances)
        if not instance:
            print("❌ No instances found")
            sys.exit(1)

    instance_id = instance.get("id")
    state = instance.get("state", instance.get("cur_state", "")).lower()

    print(f"\n📋 Instance: {instance_id}")
    print(f"   State: {state}")
    print(f"   GPU: {instance.get('gpu_name', 'N/A')}")
    print(f"   IP: {instance.get('public_ipaddr', instance.get('ip', 'N/A'))}")

    if state != "running":
        print(f"\n⚠���  Instance is not running (state: {state})")
        sys.exit(1)

    # Get SSH URL
    ssh_url = get_ssh_url(instance_id)
    if not ssh_url:
        print("❌ Failed to get SSH URL")
        sys.exit(1)

    print(f"   SSH URL: {ssh_url}")

    # Parse SSH URL
    ssh_info = parse_ssh_url(ssh_url)
    if not ssh_info:
        print("❌ Failed to parse SSH URL")
        sys.exit(1)

    # Update rclone config
    if not args.skip_rclone and (
        args.yes
        or input("\n📂 Update rclone config? (Y/n): ").lower().strip()
        in ["", "y", "yes"]
    ):
        update_rclone_config(ssh_info["host"], ssh_info["port"])

    # Find SSH key
    ssh_key = find_ssh_key()

    # Attach SSH key if needed and key found
    if ssh_key and not args.skip_key:
        should_attach = args.yes
        if not should_attach:
            try:
                response = input("\n🔑 Attach SSH key? (Y/n): ").lower().strip()
                should_attach = response in ["", "y", "yes"]
            except EOFError:
                should_attach = True

        if should_attach:
            if not attach_ssh_key(instance_id, ssh_key):
                print("⚠️  Continuing without attaching key...")

    # Build and execute SSH command
    ssh_cmd = build_ssh_command(
        ssh_info["host"], ssh_info["port"], ssh_info.get("user", "root")
    )

    connect_ssh(ssh_cmd)


if __name__ == "__main__":
    main()
