"""
Instances manager for VastAI v2.1
Simplified version: focuses on renting instances and showing status
No unnecessary pinging, just reliable vastai CLI feedback
"""

import time
import logging
import json
import signal
import sys
from typing import Optional, Dict, Any

from config import Config
from utils import run_command, wait_with_progress, print_progress_bar, clear_file, get_confirmation
from ssh_agent import SSHAgentUtility

class InstancesManagerV2:
    """Handles VastAI instance creation and monitoring - Simplified v2.1"""

    def __init__(self):
        self.current_instance_id = None
        self.instances_file = "instances.json"
        self.should_exit = False
        
        # Setup signal handler for graceful shutdown
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)
        
        # Enhanced error handling
        self.last_error = None
        self.retry_count = 0

    def signal_handler(self, signum, frame):
        """Handle Ctrl+C gracefully"""
        print("\n\n⚠️  Interrupt received. Preparing for graceful shutdown...")
        self.should_exit = True

    def clear_old_instances_file(self):
        """Clear old instances file to avoid ID confusion"""
        clear_file(self.instances_file)
        logging.info("Cleared old instances.json file")

    def create_instance(self, offer: Dict[str, Any]) -> bool:
        """Create a VastAI instance based on selected offer with enhanced error handling"""
        offer_id = offer.get('id')
        if not offer_id:
            logging.error("No offer ID provided")
            return False

        logging.info(f"Creating instance with offer ID: {offer_id}")

        # Build the vastai create command
        cmd = [
            Config.VASTAI_CMD, "create", "instance", str(offer_id),
            "--image", Config.DEFAULT_IMAGE,
            "--disk", str(Config.DEFAULT_DISK_SIZE),
            "--onstart-cmd", Config.ONSTART_CMD
        ]

        # Add environment variables
        for env_var in Config.DEFAULT_ENV_VARS:
            cmd.extend(["--env", env_var])

        # Add other options
        cmd.extend(["--jupyter", "--ssh", "--direct"])

        try:
            logging.debug(f"Running create command: {' '.join(cmd)}")
            result = run_command(cmd, timeout=Config.INSTANCE_CREATION_TIMEOUT)

            if result.returncode == 0:
                logging.info("Instance creation command executed successfully")
                
                # Try to extract instance ID from output
                self.current_instance_id = self._extract_instance_id(result.stdout)

                # If extraction failed, try to find the instance from the instances list
                if not self.current_instance_id:
                    logging.info("Could not extract instance ID from create output, trying to find it from instances list...")
                    self.current_instance_id = self._find_recent_instance()
                    if self.current_instance_id:
                        logging.info(f"Found instance ID from instances list: {self.current_instance_id}")
                    else:
                        logging.warning("Could not find instance ID")
                        print("⚠️  Warning: Could not determine instance ID. You may need to check manually.")
                        return False

                # Save instance info to JSON
                if self._save_instance_info():
                    logging.info(f"Instance {self.current_instance_id} info saved to {self.instances_file}")
                    return True
                else:
                    logging.error("Failed to save instance info")
                    return False
            else:
                logging.error(f"Instance creation failed: {result.stderr}")
                print(f"❌ Instance creation failed: {result.stderr}")
                
                # Provide helpful error messages
                error_output = result.stderr.lower()
                if "budget" in error_output or "insufficient" in error_output:
                    print("💡 Tip: You may need to increase your budget or check your account balance.")
                elif "quota" in error_output:
                    print("💡 Tip: You may have reached your instance quota limit.")
                elif "image" in error_output:
                    print("💡 Tip: The specified image may not be available or valid.")
                
                return False

        except subprocess.TimeoutExpired:
            logging.error(f"Instance creation timed out after {Config.INSTANCE_CREATION_TIMEOUT} seconds")
            print(f"❌ Instance creation timed out after {Config.INSTANCE_CREATION_TIMEOUT} seconds")
            print("💡 Tip: This may be due to high demand or network issues. Try again later.")
            return False
        except Exception as e:
            logging.error(f"Error creating instance: {e}")
            print(f"❌ Unexpected error creating instance: {e}")
            return False

    def _extract_instance_id(self, output: str) -> Optional[int]:
        """Extract instance ID from command output"""
        import re
        logging.debug(f"Extracting instance ID from output: {output}")

        # Look for various patterns
        patterns = [
            r'instance\s+(\d+)',
            r'ID:\s*(\d+)',
            r'instance\s*#?(\d+)',
            r'created\s+instance\s+(\d+)',
            r'instance\s+(\d+)\s+created',
            r'(\d{6,})',  # Fallback: any 6+ digit number (instance IDs are typically 6-8 digits)
        ]

        for pattern in patterns:
            matches = re.findall(pattern, output, re.IGNORECASE)
            for match in matches:
                try:
                    instance_id = int(match)
                    # Validate instance ID range (VastAI instance IDs are typically 6-8 digits)
                    if 100000 <= instance_id <= 99999999:
                        logging.info(f"Extracted instance ID: {instance_id}")
                        return instance_id
                except ValueError:
                    continue

        logging.warning("Could not extract instance ID from output")
        return None

    def _find_recent_instance(self) -> Optional[int]:
        """Find the most recently created instance"""
        try:
            result = run_command([Config.VASTAI_CMD, "show", "instances", "--raw"])
            if result.returncode != 0:
                logging.error(f"Failed to get instances list: {result.stderr}")
                return None

            try:
                instances_data = json.loads(result.stdout)
            except json.JSONDecodeError:
                logging.error("Failed to parse instances JSON")
                return None

            instances = []
            if isinstance(instances_data, list):
                instances = instances_data
            elif isinstance(instances_data, dict):
                instances = [instances_data]

            # Find instances that are running or starting (indicating they were recently created)
            recent_instances = []
            for instance in instances:
                state = instance.get('state', '').lower()
                if state in ['running', 'starting', 'pending', 'provisioning']:
                    instance_id = instance.get('id')
                    if instance_id:
                        try:
                            recent_instances.append(int(instance_id))
                        except ValueError:
                            continue

            if recent_instances:
                # Return the highest instance ID (most recently created)
                recent_instance_id = max(recent_instances)
                logging.info(f"Found recent instance ID: {recent_instance_id}")
                return recent_instance_id
            else:
                logging.warning("No recent instances found")
                return None

        except Exception as e:
            logging.error(f"Error finding recent instance: {e}")
            return None

    def _save_instance_info(self) -> bool:
        """Save current instance info to JSON file"""
        if not self.current_instance_id:
            return False

        # Get detailed instance info
        instance_info = self.get_instance_detailed_info()
        if not instance_info:
            return False

        # Save to JSON file
        try:
            with open(self.instances_file, 'w', encoding='utf-8') as f:
                json.dump(instance_info, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            logging.error(f"Error saving instance info: {e}")
            return False

    def get_instance_detailed_info(self) -> Optional[Dict[str, Any]]:
        """Get detailed information for the current instance"""
        if not self.current_instance_id:
            return None

        try:
            result = run_command([Config.VASTAI_CMD, "show", "instance", str(self.current_instance_id), "--raw"])
            if result.returncode == 0:
                return json.loads(result.stdout)
        except Exception as e:
            logging.error(f"Error getting instance details: {e}")
        return None

    def wait_for_instance_ready(self) -> bool:
        """Wait for instance to be ready using vastai CLI feedback with enhanced error handling"""
        if not self.current_instance_id:
            logging.error("No instance ID available")
            return False

        logging.info(f"Waiting for instance {self.current_instance_id} to be ready...")
        print("⏳ Waiting for instance to start (this may take 5-15 minutes)...")
        print("   Checking status using vastai CLI...")

        max_attempts = Config.IP_CHECK_MAX_ATTEMPTS
        for attempt in range(max_attempts):
            if self.should_exit:
                print("\n⚠️  Interrupt detected during instance startup")
                return False

            try:
                # Check instance status using vastai CLI
                result = run_command([Config.VASTAI_CMD, "show", "instances", "--raw"])

                if result.returncode != 0:
                    logging.warning(f"Failed to check instance status: {result.stderr}")
                    # Don't immediately continue - check if this is a temporary issue
                    if attempt < max_attempts - 1:
                        time.sleep(Config.IP_CHECK_INTERVAL)
                        continue
                    else:
                        print("❌ Failed to get instance status after multiple attempts")
                        print("💡 Tip: Check your internet connection and VastAI CLI status")
                        return False

                # Parse instance data
                try:
                    instances_data = json.loads(result.stdout)
                except json.JSONDecodeError as e:
                    logging.warning(f"Failed to parse instances JSON: {e}")
                    if attempt < max_attempts - 1:
                        time.sleep(Config.IP_CHECK_INTERVAL)
                        continue
                    else:
                        print("❌ Failed to parse instance data")
                        print("💡 Tip: This may be a temporary API issue")
                        return False

                # Find our instance
                instance_info = None
                if isinstance(instances_data, list):
                    for instance in instances_data:
                        instance_id = instance.get('id', '')
                        if str(instance_id) == str(self.current_instance_id):
                            instance_info = instance
                            break
                elif isinstance(instances_data, dict):
                    instance_id = instances_data.get('id', '')
                    if str(instance_id) == str(self.current_instance_id):
                        instance_info = instances_data

                if not instance_info:
                    # Instance not found - this could mean it's still being created
                    if attempt < max_attempts - 1:
                        time.sleep(Config.IP_CHECK_INTERVAL)
                        continue
                    else:
                        print("❌ Instance not found in the system")
                        print("💡 Tip: The instance creation may have failed. Check your budget and try again.")
                        return False

                # Check instance state
                state = instance_info.get('state', instance_info.get('cur_state', '')).lower()

                if state == 'running':
                    ip_address = instance_info.get('ip') or instance_info.get('public_ipaddr')
                    ssh_host = instance_info.get('ssh_host')
                    ssh_port = instance_info.get('ssh_port')
                    
                    if ip_address:
                        print(f"\n✅ Instance ready!")
                        print(f"   ID: {self.current_instance_id}")
                        print(f"   State: {state}")
                        print(f"   IP: {ip_address}")
                        print(f"   SSH: {ssh_host}:{ssh_port}")
                        
                        # Verify SSH connectivity before considering instance fully ready
                        if self._verify_ssh_connectivity():
                            # Update instance info with SSH details
                            updated_info = self.get_instance_detailed_info()
                            if updated_info:
                                self._save_instance_info()
                            return True
                        else:
                            print("\n⚠️  Instance is running but SSH is not yet available")
                            print("💡 Waiting a bit longer for SSH daemon to start...")
                            # Continue waiting for SSH to become available
                    else:
                        logging.warning("Instance is running but no IP address found")
                        if attempt < max_attempts - 1:
                            time.sleep(Config.IP_CHECK_INTERVAL)
                            continue
                        else:
                            print("⚠️  Instance is running but no IP address available")
                            print("💡 Tip: This may be a network configuration issue")
                            return False
                elif state in ['error', 'failed']:
                    logging.error(f"Instance failed with state: {state}")
                    print(f"\n❌ Instance failed with state: {state}")
                    
                    # Try to get more details about the failure
                    try:
                        detailed_info = self.get_instance_detailed_info()
                        if detailed_info and detailed_info.get('error_msg'):
                            print(f"   Error details: {detailed_info['error_msg']}")
                    except:
                        pass
                    
                    return False
                elif state in ['starting', 'pending', 'provisioning']:
                    remaining = max_attempts - attempt - 1
                    print_progress_bar(attempt + 1, max_attempts,
                                     prefix="Starting instance",
                                     suffix=f"{remaining * Config.IP_CHECK_INTERVAL}s remaining")
                else:
                    logging.info(f"Instance state: {state}")
                    if attempt < max_attempts - 1:
                        time.sleep(Config.IP_CHECK_INTERVAL)
                        continue
                    else:
                        print(f"⚠️  Instance is in unexpected state: {state}")
                        print("💡 Tip: Check the instance status manually with 'vastai show instances'")

            except Exception as e:
                logging.warning(f"Error checking instance status: {e}")
                if attempt < max_attempts - 1:
                    time.sleep(Config.IP_CHECK_INTERVAL)
                    continue
                else:
                    print(f"❌ Error checking instance status: {e}")
                    print("💡 Tip: This may be a network or API issue")
                    return False

            time.sleep(Config.IP_CHECK_INTERVAL)

        logging.error("Timeout waiting for instance to be ready")
        print("\n⏰ Timeout: Instance did not become ready within the expected time")
        print("💡 Tip: Try checking the instance status manually with 'vastai show instances'")
        return False

    def show_instances_status(self):
        """Show current instances status using vastai CLI"""
        print("\n" + "=" * 60)
        print("📊 Current VastAI Instances Status")
        print("=" * 60)
        
        try:
            result = run_command([Config.VASTAI_CMD, "show", "instances", "--raw"])
            if result.returncode == 0:
                try:
                    instances_data = json.loads(result.stdout)
                    
                    if isinstance(instances_data, list):
                        if instances_data:
                            print(f"\nFound {len(instances_data)} instance(s):")
                            for i, instance in enumerate(instances_data, 1):
                                instance_id = instance.get('id', 'N/A')
                                state = instance.get('state', 'unknown').lower()
                                ip = instance.get('ip') or instance.get('public_ipaddr') or 'N/A'
                                gpu = instance.get('gpu_name', 'N/A')
                                price = instance.get('dph_total', 'N/A')
                                
                                status_icon = "✅" if state == 'running' else "⏳" if state in ['starting', 'pending'] else "❌"
                                
                                print(f"\n{i}. {status_icon} Instance {instance_id}")
                                print(f"   State: {state}")
                                print(f"   GPU: {gpu}")
                                print(f"   IP: {ip}")
                                print(f"   Price: ${price}/hour" if price != 'N/A' else "   Price: N/A")
                                
                                # Highlight current instance
                                if instance_id == self.current_instance_id:
                                    print("   👈 Current instance (managed by this script)")
                        else:
                            print("\nNo instances found.")
                    else:
                        print("\nUnexpected response format from vastai CLI")
                        
                except json.JSONDecodeError as e:
                    print(f"\n❌ Failed to parse instances data: {e}")
            else:
                print(f"\n❌ Failed to get instances list: {result.stderr}")
                
        except Exception as e:
            print(f"\n❌ Error checking instances status: {e}")

    def monitor_instances_simple(self, interval: int = 30):
        """Simple monitoring - just show instances status periodically"""
        print(f"\n🔍 Monitoring instances every {interval} seconds...")
        print("Press Ctrl+C to stop monitoring and check for cleanup")
        print("-" * 60)

        try:
            while not self.should_exit:
                self.show_instances_status()
                
                if interval > 0:
                    print(f"\n⏳ Next update in {interval} seconds...")
                    for i in range(interval):
                        if self.should_exit:
                            break
                        time.sleep(1)
                        
        except KeyboardInterrupt:
            print("\n\n⚠️  Monitoring interrupted by user")
            self.should_exit = True

    def check_and_cleanup_instances(self, non_interactive=False):
        """Check for running instances and offer to destroy them"""
        print("\n" + "=" * 60)
        print("🧹 Instance Cleanup Check")
        print("=" * 60)
        
        # Temporarily ignore signals to ensure cleanup check completes
        original_handler = signal.getsignal(signal.SIGINT)
        signal.signal(signal.SIGINT, signal.SIG_IGN)

        try:
            result = run_command([Config.VASTAI_CMD, "show", "instances", "--raw"])
            if result.returncode == 0:
                try:
                    instances_data = json.loads(result.stdout)
                    
                    running_instances = []
                    if isinstance(instances_data, list):
                        for instance in instances_data:
                            state = instance.get('state', '').lower()
                            # Check for any active state, not just running
                            if state in ['running', 'starting', 'provisioning', 'pending']:
                                instance_id = instance.get('id')
                                if instance_id:
                                    running_instances.append(instance_id)
                    
                    if running_instances:
                        print(f"\n⚠️  Found {len(running_instances)} active instance(s): {running_instances}")
                        print("   These instances are currently costing money!")
                        
                        if non_interactive:
                            # In non-interactive mode, destroy all without asking
                            print("\n🗑️  Destroying all active instances (non-interactive mode)...")
                            destroyed_count = 0
                            for instance_id in running_instances:
                                print(f"   Destroying instance {instance_id}...")
                                try:
                                    destroy_result = run_command([
                                        Config.VASTAI_CMD, "destroy", "instance", str(instance_id)
                                    ])
                                    if destroy_result.returncode == 0:
                                        print(f"   ✅ Instance {instance_id} destroyed")
                                        destroyed_count += 1
                                    else:
                                        print(f"   ❌ Failed to destroy instance {instance_id}: {destroy_result.stderr}")
                                except Exception as e:
                                    print(f"   ❌ Error destroying instance {instance_id}: {e}")
                            print(f"\n✅ Destroyed {destroyed_count} out of {len(running_instances)} instances")
                        else:
                            # Re-enable signal for confirmation
                            signal.signal(signal.SIGINT, original_handler)
                            confirm = get_confirmation("Do you want to destroy all active instances?")
                            signal.signal(signal.SIGINT, signal.SIG_IGN) # Ignore again for destruction
                            
                            if confirm:
                                print("\n🗑️  Destroying instances (DO NOT INTERRUPT)...")
                                destroyed_count = 0
                                for instance_id in running_instances:
                                    print(f"   Destroying instance {instance_id}...")
                                    try:
                                        destroy_result = run_command([
                                            Config.VASTAI_CMD, "destroy", "instance", str(instance_id)
                                        ])
                                        if destroy_result.returncode == 0:
                                            print(f"   ✅ Instance {instance_id} destroyed")
                                            destroyed_count += 1
                                        else:
                                            print(f"   ❌ Failed to destroy instance {instance_id}: {destroy_result.stderr}")
                                    except Exception as e:
                                        print(f"   ❌ Error destroying instance {instance_id}: {e}")
                                print(f"\n✅ Destroyed {destroyed_count} out of {len(running_instances)} instances")
                            else:
                                print("\nℹ️  Instances left running. They will continue to cost money.")
                    else:
                        print("\n✅ No active instances found. No cleanup needed.")
                        
                except json.JSONDecodeError:
                    print("\n❌ Failed to parse instances data")
            else:
                print(f"\n❌ Failed to get instances list: {result.stderr}")
                
        except Exception as e:
            print(f"\n❌ Error during cleanup check: {e}")
        finally:
            # Restore signal handler
            signal.signal(signal.SIGINT, original_handler)

    def destroy_current_instance(self) -> bool:
        """Destroy the current instance"""
        if not self.current_instance_id:
            logging.warning("No instance to destroy")
            return False

        if not get_confirmation(f"Destroy instance {self.current_instance_id}?"):
            return False

        try:
            result = run_command([
                Config.VASTAI_CMD, "destroy", "instance", str(self.current_instance_id)
            ])

            if result.returncode == 0:
                logging.info(f"Instance {self.current_instance_id} destroyed successfully")
                print(f"✅ Instance {self.current_instance_id} destroyed successfully")
                self.current_instance_id = None
                clear_file(self.instances_file)
                return True
            else:
                logging.error(f"Failed to destroy instance: {result.stderr}")
                print(f"❌ Failed to destroy instance: {result.stderr}")
                return False
        except Exception as e:
            logging.error(f"Error destroying instance: {e}")
            print(f"❌ Error destroying instance: {e}")
            return False

    def _verify_ssh_connectivity(self) -> bool:
        """Verify SSH connectivity to the instance."""
        ssh_util = SSHAgentUtility(self.instances_file)
        ssh_info = ssh_util.get_ssh_connection_info()
        if not ssh_info:
            return False
        success, _, _ = ssh_util.execute_command('echo "SSH connected"', timeout=10)
        return success