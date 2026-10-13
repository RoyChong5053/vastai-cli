"""
Configuration settings for VastAI CLI tool
"""

import os
from typing import Dict, Any

# Import profile manager
from profiles import profile_manager

class Config:
    """Configuration class for VastAI operations"""

    # VastAI CLI settings
    VASTAI_CMD = "vastai"

    # Instance creation settings
    DEFAULT_IMAGE = "vastai/comfy:@vastai-automatic-tag"
    DEFAULT_DISK_SIZE = 16
    ONSTART_CMD = "entrypoint.sh"

    # Complex environment configuration for ComfyUI
    # This entire string triggers the provisioning script correctly
    DEFAULT_ENV_VARS = [
        "-p 1111:1111 -p 8080:8080 -p 8384:8384 -p 72299:72299 -p 8188:8188 -p 8288:8288 -e COMFYUI_ARGS=\"--disable-auto-launch --port 18188 --enable-cors-header\" -e COMFYUI_API_BASE=http://localhost:18188 -e PROVISIONING_SCRIPT=https://raw.githubusercontent.com/vast-ai/base-image/refs/heads/main/derivatives/pytorch/derivatives/comfyui/provisioning_scripts/default.sh -e PORTAL_CONFIG=\"localhost:1111:11111:/:Instance Portal|localhost:8188:18188:/:ComfyUI|localhost:8288:18288:/docs:API Wrapper|localhost:8188:18188:/:ComfyUI|localhost:8080:18080:/:Jupyter|localhost:8080:8080:/terminals/1:Jupyter Terminal|localhost:8384:18384:/:Syncthing\" -e OPEN_BUTTON_PORT=1111 -e JUPYTER_DIR=/ -e DATA_DIRECTORY=/workspace/ -e OPEN_BUTTON_TOKEN=***"
    ]

    # SSH settings
    SSH_PORT = 42600
    SSH_KEY_PATHS = [
        "~/.ssh/id_rsa.pub",
        "~/.ssh/id_ed25519.pub",
        "~/.ssh/id_ecdsa.pub",
        "~/.ssh/id_dsa.pub"
    ]

    # Price filtering settings
    MAX_PRICE_PER_HOUR = 5.0  # $ per hour
    MIN_DISK_SIZE = 10  # GB
    MAX_OFFERS_TO_SHOW = 10

    # Internet cost filtering settings
    MAX_INTERNET_DOWN_COST_PER_TB = 5.0  # $ per TB download
    MAX_INTERNET_UP_COST_PER_TB = 5.0    # $ per TB upload

    # Timeout settings (in seconds)
    INSTANCE_CREATION_TIMEOUT = 1800  # 30 minutes
    IP_CHECK_INTERVAL = 10
    IP_CHECK_MAX_ATTEMPTS = 300  # 50 minutes total (increased for provisioning)

    # Terminal settings for different environments
    TERMINAL_TYPE = os.environ.get('TERM', 'xterm')

    # File paths
    PRICE_LIST_FILE = "price-list.json"
    LOG_FILE = "vastai.log"
    SSH_LOG_FILE = "ssh_vastai.log"

    # Enhanced configuration options for v2.2
    # Retry settings
    MAX_RETRY_ATTEMPTS = 3
    RETRY_DELAY = 5  # seconds

    # Instance monitoring settings
    MONITOR_INTERVAL = 30  # seconds
    PING_TIMEOUT = 5  # seconds for ping checks
    PING_COUNT = 2

    # SSH connection settings
    SSH_TIMEOUT = 30  # seconds
    SSH_RETRIES = 3

    # Cleanup settings
    AUTO_CLEANUP_ON_ERROR = True
    CONFIRM_DESTROY_ON_EXIT = True

    # Debug settings
    DEBUG_MODE = False
    VERBOSE_LOGGING = False

    # SSH connection verification settings
    SSH_CHECK_MAX_ATTEMPTS = 10
    SSH_CHECK_INTERVAL = 5  # seconds

    @classmethod
    def get_ssh_command(cls, instance_ip: str, terminal_type: str = None) -> list:
        """Get SSH command based on terminal type"""
        if terminal_type is None:
            terminal_type = cls.TERMINAL_TYPE

        base_cmd = [
            "ssh",
            "-p", str(cls.SSH_PORT),
            "-o", "StrictHostKeyChecking=no",
            "-o", "UserKnownHostsFile=/dev/null",
            f"root@{instance_ip}"
        ]

        # Handle different terminal types
        if 'kitty' in terminal_type.lower():
            # For Kitty terminal in Hyprland
            return base_cmd + ["-t", "TERM=xterm-256color", "bash"]
        elif 'alacritty' in terminal_type.lower():
            return base_cmd + ["-t", "TERM=xterm-256color", "bash"]
        else:
            # Default for most terminals
            return base_cmd + ["-t", "TERM=xterm", "bash"]

    @classmethod
    def get_env_vars_string(cls) -> str:
        """Get environment variables as string for vastai command"""
        return " ".join(f"--env '{var}'" for var in cls.DEFAULT_ENV_VARS)

    @classmethod
    def expand_path(cls, path: str) -> str:
        """Expand user path"""
        return os.path.expanduser(path)
