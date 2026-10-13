#!/usr/bin/env python3
"""
SSH connector for VastAI instances v2.1
Reads instances.json and connects to the instance via SSH
With environment detection for different terminals (hyprland+kitty, termux, etc.)
"""

import os
import sys
import json
import logging
import platform
import subprocess
from typing import Optional, Dict, Any

from config import Config
from utils import setup_logging, run_command

class SSHVastAIV2:
    """Handles SSH connection to VastAI instances with environment detection"""

    def __init__(self):
        self.instances_file = "instances.json"
        self.instance_info = None
        
        # Enhanced error handling
        self.last_error = None
        self.retry_count = 0
        self.environment = self.detect_environment()

    def detect_environment(self) -> Dict[str, Any]:
        """Detect the current environment (terminal, OS, etc.)"""
        env_info = {
            "os": platform.system().lower(),
            "terminal": os.environ.get('TERM', 'unknown'),
            "desktop": os.environ.get('XDG_CURRENT_DESKTOP', 'unknown').lower(),
            "term_program": os.environ.get('TERM_PROGRAM', 'unknown').lower(),
            "in_termux": False,
            "in_kitty": False,
            "in_hyprland": False
        }
        
        # Check for Termux
        if 'termux' in env_info["terminal"].lower() or 'android' in env_info["os"].lower():
            env_info["in_termux"] = True
            
        # Check for Kitty terminal
        if 'kitty' in env_info["terminal"].lower() or 'kitty' in env_info["term_program"]:
            env_info["in_kitty"] = True
            
        # Check for Hyprland
        if 'hyprland' in env_info["desktop"]:
            env_info["in_hyprland"] = True
            
        # Additional checks
        try:
            # Check if we're in a TTY
            result = subprocess.run(['tty'], capture_output=True, text=True)
            if 'pts' in result.stdout:
                env_info["terminal_type"] = "graphical"
            else:
                env_info["terminal_type"] = "tty"
        except:
            env_info["terminal_type"] = "unknown"
            
        logging.info(f"Detected environment: {env_info}")
        return env_info

    def load_instance_info(self) -> bool:
        """Load instance information from JSON file"""
        try:
            with open(self.instances_file, 'r', encoding='utf-8') as f:
                self.instance_info = json.load(f)
            logging.info(f"Loaded instance info from {self.instances_file}")
            return True
        except FileNotFoundError:
            logging.error(f"Instances file not found: {self.instances_file}")
            print(f"❌ Error: Instances file '{self.instances_file}' not found.")
            print("Please run the instance manager first to create an instance.")
            return False
        except json.JSONDecodeError as e:
            logging.error(f"Error parsing instances JSON: {e}")
            print(f"❌ Error: Invalid JSON in {self.instances_file}")
            return False

    def find_ssh_key(self) -> Optional[str]:
        """Find the user's SSH public key"""
        for key_path in Config.SSH_KEY_PATHS:
            expanded_path = Config.expand_path(key_path)
            if os.path.exists(expanded_path):
                logging.info(f"Found SSH key: {expanded_path}")
                return expanded_path

        logging.warning("No SSH public key found")
        print("❌ No SSH public key found.")
        print("Please generate one with: ssh-keygen -t rsa -b 4096")
        return None

    def copy_ssh_key(self) -> bool:
        """Copy SSH public key to the instance using VastAI CLI with enhanced error handling"""
        if not self.instance_info:
            logging.error("No instance information available")
            return False

        instance_id = self.instance_info.get('id')
        if not instance_id:
            logging.error("No instance ID available")
            print("❌ No instance ID found in instances.json")
            return False

        ssh_key_path = self.find_ssh_key()
        if not ssh_key_path:
            return False

        logging.info(f"Copying SSH key to instance {instance_id} using VastAI CLI")

        try:
            # Use VastAI CLI to add SSH key
            cmd = [Config.VASTAI_CMD, "attach", "ssh", str(instance_id), ssh_key_path]

            print(f"🔑 Adding SSH key to instance {instance_id}...")
            print(f"   Key file: {ssh_key_path}")
            
            result = run_command(cmd, timeout=30)

            if result.returncode == 0:
                logging.info("SSH key added successfully using VastAI CLI")
                print("✓ SSH key added successfully using VastAI CLI")
                
                # Parse the response to get key info
                try:
                    response = json.loads(result.stdout)
                    if response.get('success'):
                        key_id = response.get('key', {}).get('id')
                        if key_id:
                            print(f"   Key ID: {key_id}")
                        # Wait a moment for the key to propagate to SSH daemon
                        import time
                        time.sleep(2)
                        return True
                    else:
                        logging.warning(f"VastAI CLI returned unsuccessful response: {response}")
                        error_msg = response.get('msg', 'Unknown error')
                        print(f"   Error: {error_msg}")
                        return False
                except json.JSONDecodeError:
                    logging.warning("Could not parse VastAI CLI response")
                    # If we can't parse but command succeeded, assume it worked
                    print("   Warning: Could not parse response, but key may have been added")
                    # Wait a moment for the key to propagate to SSH daemon
                    import time
                    time.sleep(2)
                    return True
            else:
                logging.error(f"Failed to add SSH key: {result.stderr}")
                print(f"❌ Failed to add SSH key: {result.stderr}")
                
                # Provide helpful error messages
                error_output = result.stderr.lower()
                if "permission" in error_output or "denied" in error_output:
                    print("💡 Tip: Check that you have permission to modify this instance.")
                elif "key" in error_output:
                    print("💡 Tip: The SSH key may already be attached or there may be a format issue.")
                elif "instance" in error_output:
                    print("💡 Tip: The instance may not be in the correct state for SSH key attachment.")
                
                return False

        except subprocess.TimeoutExpired:
            logging.error(f"SSH key attachment timed out after 30 seconds")
            print("❌ SSH key attachment timed out")
            print("💡 Tip: This may be due to network issues or high server load.")
            return False
        except Exception as e:
            logging.error(f"Error copying SSH key: {e}")
            print(f"❌ Unexpected error copying SSH key: {e}")
            return False

    def get_ssh_url_from_vastai(self) -> Optional[str]:
        """Get SSH URL using vastai ssh-url command"""
        if not self.instance_info:
            return None

        instance_id = self.instance_info.get('id')
        if not instance_id:
            return None

        try:
            result = run_command([Config.VASTAI_CMD, "ssh-url", str(instance_id)], timeout=10)
            if result.returncode == 0:
                ssh_url = result.stdout.strip()
                logging.info(f"Got SSH URL from vastai: {ssh_url}")
                return ssh_url
            else:
                logging.warning(f"Failed to get SSH URL: {result.stderr}")
                return None
        except Exception as e:
            logging.error(f"Error getting SSH URL: {e}")
            return None

    def parse_ssh_url(self, ssh_url: str) -> Optional[Dict[str, str]]:
        """Parse SSH URL to get host and port"""
        try:
            # ssh://root@62.107.25.198:43317
            if ssh_url.startswith("ssh://"):
                ssh_url = ssh_url[6:]  # Remove ssh://
            
            # root@62.107.25.198:43317
            if "@" in ssh_url:
                user_host = ssh_url.split("@")
                if len(user_host) == 2:
                    host_port = user_host[1]
                    if ":" in host_port:
                        host, port = host_port.split(":")
                        return {"host": host, "port": port, "user": user_host[0]}
            return None
        except Exception as e:
            logging.error(f"Error parsing SSH URL {ssh_url}: {e}")
            return None

    def get_ssh_command_for_environment(self) -> Optional[list]:
        """Get SSH command based on detected environment"""
        if not self.instance_info:
            return None

        # First try to get SSH URL from vastai CLI
        ssh_url = self.get_ssh_url_from_vastai()
        if ssh_url:
            ssh_info = self.parse_ssh_url(ssh_url)
            if ssh_info:
                host = ssh_info.get('host')
                port = ssh_info.get('port')
                user = ssh_info.get('user', 'root')
                
                if host and port:
                    return self._build_ssh_command(host, port, user)

        # Fallback to using info from instances.json
        ssh_host = self.instance_info.get('ssh_host')
        ssh_port = self.instance_info.get('ssh_port')
        public_ip = self.instance_info.get('public_ipaddr') or self.instance_info.get('ip')

        if public_ip and ssh_port:
            # Use public IP directly
            return self._build_ssh_command(public_ip, ssh_port, "root")
        elif ssh_host and ssh_port:
            # Use SSH host (proxy)
            return self._build_ssh_command(ssh_host, ssh_port, "root")

        logging.error("Missing SSH connection information")
        return None

    def _build_ssh_command(self, host: str, port: str, user: str = "root") -> list:
        """Build SSH command based on environment"""
        base_cmd = [
            "ssh",
            "-p", str(port),
            f"{user}@{host}",
            "-L", "8080:localhost:8080",  # Port forwarding for Jupyter
            "-L", "8188:localhost:8188",  # Port forwarding for ComfyUI
            "-o", "StrictHostKeyChecking=no",
            "-o", "UserKnownHostsFile=/dev/null"
        ]
        
        # Adjust command based on environment
        if self.environment["in_termux"]:
            # Termux environment
            base_cmd.extend(["-t", "TERM=xterm-256color", "bash"])
        elif self.environment["in_kitty"] and self.environment["in_hyprland"]:
            # Kitty terminal in Hyprland
            base_cmd.extend(["-t", "TERM=xterm-256color", "bash"])
        elif self.environment["in_kitty"]:
            # Kitty terminal
            base_cmd.extend(["-t", "TERM=xterm-256color", "bash"])
        elif self.environment["terminal_type"] == "graphical":
            # Graphical terminal
            base_cmd.extend(["-t", "TERM=xterm-256color", "bash"])
        else:
            # Default for most terminals
            base_cmd.extend(["-t", "TERM=xterm", "bash"])
            
        return base_cmd

    def connect_to_instance(self) -> bool:
        """Connect to the instance via SSH with enhanced error handling"""
        if not self.instance_info:
            logging.error("No instance information available")
            return False

        instance_id = self.instance_info.get('id')
        public_ip = self.instance_info.get('public_ipaddr') or self.instance_info.get('ip')
        ssh_host = self.instance_info.get('ssh_host')
        ssh_port = self.instance_info.get('ssh_port')

        # Get SSH command
        ssh_cmd = self.get_ssh_command_for_environment()
        if not ssh_cmd:
            print("❌ Failed to create SSH command")
            print("💡 Tip: Check that the instance is running and has valid connection information.")
            return False

        # Get SSH URL for display
        ssh_url = self.get_ssh_url_from_vastai()

        print(f"\n🔗 Connecting to instance {instance_id}")
        print(f"🌍 Detected environment: {self.environment['os']} / {self.environment['terminal']}")
        
        if public_ip:
            print(f"Public IP: {public_ip}")
        
        if ssh_host and ssh_port:
            print(f"SSH Proxy: {ssh_host}:{ssh_port}")
        
        if ssh_url:
            print(f"SSH URL: {ssh_url}")
        
        print("\n📡 Port Forwarding:")
        print("   - Jupyter: http://localhost:8080")
        print("   - ComfyUI: http://localhost:8188")
        
        # Show actual service addresses
        if public_ip:
            print(f"\n🌐 Service URLs (direct access):")
            print(f"   ComfyUI: http://{public_ip}:8188")
            print(f"   Jupyter: http://{public_ip}:8080")
            print(f"   Instance Portal: http://{public_ip}:1111")
        
        print(f"\n🔧 SSH Command for {self.environment['terminal']}:")
        print("   " + " ".join(ssh_cmd))
        print("\nUse 'exit' to disconnect when done.")
        print("-" * 60)

        try:
            # Execute SSH command (this will take over the terminal)
            os.execvp("ssh", ssh_cmd)
            # If we reach here, execvp failed
            return False
        except FileNotFoundError:
            logging.error("SSH command not found")
            print("❌ SSH command not found")
            print("💡 Tip: Make sure SSH is installed on your system.")
            return False
        except PermissionError:
            logging.error("Permission denied when executing SSH command")
            print("❌ Permission denied when executing SSH command")
            print("💡 Tip: Check that you have permission to execute SSH.")
            return False
        except Exception as e:
            logging.error(f"Failed to execute SSH command: {e}")
            print(f"❌ Failed to execute SSH command: {e}")
            
            # Fallback: show manual connection instructions
            print("\n💡 Manual connection instructions:")
            if ssh_url:
                print(f"   ssh -p {ssh_url.split(':')[-1]} root@{ssh_url.split('@')[1].split(':')[0]} -L 8080:localhost:8080 -L 8188:localhost:8188 -t 'TERM=xterm bash'")
            elif public_ip and ssh_port:
                print(f"   ssh -p {ssh_port} root@{public_ip} -L 8080:localhost:8080 -L 8188:localhost:8188 -t 'TERM=xterm bash'")
            
            return False

    def show_instance_info(self):
        """Display current instance information"""
        if not self.instance_info:
            print("❌ No instance information available")
            return

        print("\n📋 Instance Information:")
        print(f"   ID: {self.instance_info.get('id', 'N/A')}")
        print(f"   Machine ID: {self.instance_info.get('machine_id', 'N/A')}")
        print(f"   State: {self.instance_info.get('state', self.instance_info.get('cur_state', 'N/A'))}")
        print(f"   GPU: {self.instance_info.get('gpu_name', 'N/A')}")
        # vCPUs: use cpu_cores_effective
        vcpus = self.instance_info.get('cpu_cores_effective', 'N/A')
        if vcpus != 'N/A':
            try:
                vcpus = f"{float(vcpus):.1f}"
            except (ValueError, TypeError):
                pass
        print(f"   vCPUs: {vcpus}")
        # RAM: convert from MB to GB
        ram_mb = self.instance_info.get('cpu_ram', 'N/A')
        if ram_mb != 'N/A':
            try:
                ram_gb = float(ram_mb) / 1024
                ram_str = f"{ram_gb:.1f}"
            except (ValueError, TypeError):
                ram_str = 'N/A'
        else:
            ram_str = 'N/A'
        print(f"   RAM: {ram_str} GB")
        # Storage: disk_space is already in GB
        storage = self.instance_info.get('disk_space', 'N/A')
        if storage != 'N/A':
            try:
                storage = f"{float(storage):.1f}"
            except (ValueError, TypeError):
                pass
        print(f"   Storage: {storage} GB")

        # Show both IP addresses
        ip = self.instance_info.get('ip', 'N/A')
        public_ip = self.instance_info.get('public_ipaddr', 'N/A')

        if ip != 'N/A' and public_ip != 'N/A' and ip != public_ip:
            print(f"   Internal IP: {ip}")
            print(f"   Public IP: {public_ip}")
        elif public_ip != 'N/A':
            print(f"   IP: {public_ip}")
        else:
            print(f"   IP: {ip}")

        print(f"   SSH Host: {self.instance_info.get('ssh_host', 'N/A')}")
        print(f"   SSH Port: {self.instance_info.get('ssh_port', 'N/A')}")
        # Price: use dph_total
        price = self.instance_info.get('dph_total', 'N/A')
        if price != 'N/A':
            try:
                price = f"{float(price):.6f}"
            except (ValueError, TypeError):
                pass
        print(f"   Price: ${price}/hour")
        print(f"   Image: {self.instance_info.get('image_uuid', 'N/A')}")

        # Show service URLs if IP is available
        if public_ip != 'N/A':
            print(f"\n🌐 Service URLs:")
            print(f"   ComfyUI: http://{public_ip}:8188")
            print(f"   Jupyter: http://{public_ip}:8080")
            print(f"   Instance Portal: http://{public_ip}:1111")

def main():
    """Main function"""
    # Setup logging
    setup_logging("ssh_vastai.log")
    logging.info("Starting SSH VastAI Connector v2.1")

    print("🔗 SSH VastAI Connector v2.1")
    print("=" * 40)

    # Initialize SSH connector
    ssh_connector = SSHVastAIV2()

    # Load instance information
    if not ssh_connector.load_instance_info():
        sys.exit(1)

    # Display instance information
    ssh_connector.show_instance_info()

    # Check if instance is running
    state = ssh_connector.instance_info.get('state', ssh_connector.instance_info.get('cur_state', '')).lower()
    if state != 'running':
        print(f"\n⚠️  Instance is not in 'running' state. Current state: {state}")
        if state in ['error', 'failed']:
            print("❌ Instance has errors. Please check the instance status.")
            sys.exit(1)
        elif state in ['starting', 'pending', 'provisioning']:
            print("⏳ Instance is starting. Please wait for it to be ready.")
            sys.exit(1)
        else:
            print("ℹ️  Proceeding with SSH connection attempt...")

    # Ask user if they want to copy SSH key
    try:
        response = input("\n🔑 Copy SSH public key to instance? (Y/n): ").lower().strip()
        if response in ['', 'y', 'yes']:
            if not ssh_connector.copy_ssh_key():
                print("❌ Failed to copy SSH key.")
                print("💡 You may need to manually copy your SSH public key to the instance.")
                response = input("Continue with connection attempt? (y/N): ").lower().strip()
                if response not in ['y', 'yes']:
                    sys.exit(1)
    except KeyboardInterrupt:
        print("\n\nOperation cancelled by user.")
        sys.exit(0)

    # Connect to instance
    print("\n🚀 Connecting to instance...")
    if not ssh_connector.connect_to_instance():
        print("❌ Failed to connect to instance.")
        sys.exit(1)

if __name__ == "__main__":
    main()