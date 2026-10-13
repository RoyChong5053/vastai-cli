"""
Enhanced SSH utility for agent use - non-interactive command execution and file operations
"""

import os
import sys
import json
import time
import base64
import tempfile
from typing import Optional, Dict, Any, Tuple, List

sys.path.insert(0, os.path.dirname(__file__))

from config import Config
from utils import setup_logging, run_command
import subprocess
import platform


class SSHAgentUtility:
    """Enhanced SSH utility for agent use - non-interactive command execution and file operations"""
    
    def __init__(self, instances_file: str = "instances.json"):
        self.instances_file = instances_file
        self.instance_info = None
        self.environment = self._detect_environment()
        
        # Setup logging
        setup_logging("ssh_agent.log")
        
        # Load instance info if available
        self.load_instance_info()
    
    def _detect_environment(self) -> Dict[str, Any]:
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
            
        return env_info
    
    def load_instance_info(self) -> bool:
        """Load instance information from JSON file"""
        try:
            with open(self.instances_file, 'r', encoding='utf-8') as f:
                self.instance_info = json.load(f)
            return True
        except FileNotFoundError:
            return False
        except json.JSONDecodeError:
            return False
    
    def get_ssh_connection_info(self) -> Optional[Dict[str, Any]]:
        """Get SSH connection information from instance data"""
        if not self.instance_info:
            return None
            
        # First try to get SSH URL from vastai CLI
        ssh_url = self._get_ssh_url_from_vastai()
        if ssh_url:
            ssh_info = self._parse_ssh_url(ssh_url)
            if ssh_info:
                return ssh_info
        
        # Fallback to using info from instances.json
        ssh_host = self.instance_info.get('ssh_host')
        ssh_port = self.instance_info.get('ssh_port')
        public_ip = self.instance_info.get('public_ipaddr') or self.instance_info.get('ip')
        
        if public_ip and ssh_port:
            # Use public IP directly
            return {
                "host": public_ip,
                "port": ssh_port,
                "user": "root"
            }
        elif ssh_host and ssh_port:
            # Use SSH host (proxy)
            return {
                "host": ssh_host,
                "port": ssh_port,
                "user": "root"
            }
            
        return None
    
    def _get_ssh_url_from_vastai(self) -> Optional[str]:
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
                return ssh_url
        except Exception:
            pass
        return None
    
    def _parse_ssh_url(self, ssh_url: str) -> Optional[Dict[str, str]]:
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
        except Exception:
            pass
        return None
    
    def _build_ssh_command(self, host: str, port: str, user: str = "root", 
                          extra_args: List[str] = None) -> List[str]:
        """Build SSH command with optional extra arguments"""
        if extra_args is None:
            extra_args = []
            
        base_cmd = [
            "ssh",
            "-p", str(port),
            f"{user}@{host}",
            "-o", "StrictHostKeyChecking=no",
            "-o", "UserKnownHostsFile=/dev/null"
        ] + extra_args
        
        return base_cmd
    
    def execute_command(self, command: str, timeout: int = 30) -> Tuple[bool, str, str]:
        """
        Execute a command on the remote instance via SSH
        
        Returns:
            Tuple of (success, stdout, stderr)
        """
        ssh_info = self.get_ssh_connection_info()
        if not ssh_info:
            return False, "", "Could not get SSH connection information"
        
        # Build SSH command
        ssh_cmd = self._build_ssh_command(
            ssh_info["host"], 
            ssh_info["port"], 
            ssh_info.get("user", "root")
        )
        ssh_cmd.append(command)
        
        try:
            result = run_command(ssh_cmd, timeout=timeout)
            return result.returncode == 0, result.stdout, result.stderr
        except subprocess.TimeoutExpired:
            return False, "", f"Command timed out after {timeout} seconds"
        except Exception as e:
            return False, "", f"Error executing command: {str(e)}"
    
    def upload_file(self, local_path: str, remote_path: str) -> Tuple[bool, str]:
        """
        Upload a file to the remote instance via SCP
        
        Returns:
            Tuple of (success, message)
        """
        ssh_info = self.get_ssh_connection_info()
        if not ssh_info:
            return False, "Could not get SSH connection information"
        
        # Build SCP command
        scp_cmd = [
            "scp",
            "-P", str(ssh_info["port"]),
            "-o", "StrictHostKeyChecking=no",
            "-o", "UserKnownHostsFile=/dev/null",
            local_path,
            f"{ssh_info.get('user', 'root')}@{ssh_info['host']}:{remote_path}"
        ]
        
        try:
            result = run_command(scp_cmd, timeout=60)
            if result.returncode == 0:
                return True, f"File uploaded successfully to {remote_path}"
            else:
                return False, f"Failed to upload file: {result.stderr}"
        except subprocess.TimeoutExpired:
            return False, "File upload timed out after 60 seconds"
        except Exception as e:
            return False, f"Error uploading file: {str(e)}"
    
    def download_file(self, remote_path: str, local_path: str) -> Tuple[bool, str]:
        """
        Download a file from the remote instance via SCP
        
        Returns:
            Tuple of (success, message)
        """
        ssh_info = self.get_ssh_connection_info()
        if not ssh_info:
            return False, "Could not get SSH connection information"
        
        # Build SCP command
        scp_cmd = [
            "scp",
            "-P", str(ssh_info["port"]),
            "-o", "StrictHostKeyChecking=no",
            "-o", "UserKnownHostsFile=/dev/null",
            f"{ssh_info.get('user', 'root')}@{ssh_info['host']}:{remote_path}",
            local_path
        ]
        
        try:
            result = run_command(scp_cmd, timeout=60)
            if result.returncode == 0:
                return True, f"File downloaded successfully to {local_path}"
            else:
                return False, f"Failed to download file: {result.stderr}"
        except subprocess.TimeoutExpired:
            return False, "File download timed out after 60 seconds"
        except Exception as e:
            return False, f"Error downloading file: {str(e)}"
    
    def execute_script(self, script_content: str, timeout: int = 60) -> Tuple[bool, str, str]:
        """
        Execute a script on the remote instance
        
        The script is uploaded to a temporary location and then executed
        
        Returns:
            Tuple of (success, stdout, stderr)
        """
        # Create a temporary script file
        
        try:
            # Create temporary file
            with tempfile.NamedTemporaryFile(mode='w', suffix='.sh', delete=False) as f:
                f.write(script_content)
                temp_script_path = f.name
            
            # Upload the script
            upload_success, upload_msg = self.upload_file(temp_script_path, f"/tmp/{os.path.basename(temp_script_path)}")
            if not upload_success:
                os.unlink(temp_script_path)
                return False, "", f"Failed to upload script: {upload_msg}"
            
            # Make executable after upload
            self.execute_command(f"chmod +x /tmp/{os.path.basename(temp_script_path)}")
            script_path = f"/tmp/{os.path.basename(temp_script_path)}"
            
            # Execute the script
            success, stdout, stderr = self.execute_command(f"bash {script_path}", timeout=timeout)
            
            # Clean up remote script
            self.execute_command(f"rm -f {script_path}")
            
            # Clean up local temp file
            os.unlink(temp_script_path)
            
            return success, stdout, stderr
            
        except Exception as e:
            # Clean up if we created a temp file
            if 'temp_script_path' in locals() and os.path.exists(temp_script_path):
                os.unlink(temp_script_path)
            return False, "", f"Error executing script: {str(e)}"
    
    def wait_for_port(self, port: int, timeout: int = 60, interval: int = 5) -> bool:
        """
        Wait for a specific port to become available on the remote instance
        
        Returns:
            True if port becomes available, False if timeout
        """
        start_time = time.time()
        while time.time() - start_time < timeout:
            # Try to connect to the port using netcat or similar
            success, stdout, stderr = self.execute_command(
                f"timeout 1 bash -c '</dev/tcp/localhost/{port}' && echo 'open' || echo 'closed'",
                timeout=5
            )
            
            if success and 'open' in stdout:
                return True
                
            time.sleep(interval)
        
        return False
    
    def get_instance_status(self) -> Optional[Dict[str, Any]]:
        """Get current instance status"""
        if not self.instance_info:
            return None
            
        instance_id = self.instance_info.get('id')
        if not instance_id:
            return None
            
        try:
            result = run_command([Config.VASTAI_CMD, "show", "instance", str(instance_id), "--raw"])
            if result.returncode == 0:
                return json.loads(result.stdout)
        except Exception:
            pass
        return None


# Convenience functions for easy agent use
def execute_on_instance(command: str, instances_file: str = "instances.json", timeout: int = 30) -> Tuple[bool, str, str]:
    """Execute a command on the instance specified in instances.json"""
    ssh_util = SSHAgentUtility(instances_file)
    return ssh_util.execute_command(command, timeout)

def upload_to_instance(local_path: str, remote_path: str, instances_file: str = "instances.json") -> Tuple[bool, str]:
    """Upload a file to the instance specified in instances.json"""
    ssh_util = SSHAgentUtility(instances_file)
    return ssh_util.upload_file(local_path, remote_path)

def download_from_instance(remote_path: str, local_path: str, instances_file: str = "instances.json") -> Tuple[bool, str]:
    """Download a file from the instance specified in instances.json"""
    ssh_util = SSHAgentUtility(instances_file)
    return ssh_util.download_file(remote_path, local_path)

def run_script_on_instance(script_content: str, instances_file: str = "instances.json", timeout: int = 60) -> Tuple[bool, str, str]:
    """Run a script on the instance specified in instances.json"""
    ssh_util = SSHAgentUtility(instances_file)
    return ssh_util.execute_script(script_content, timeout)