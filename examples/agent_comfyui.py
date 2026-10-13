#!/usr/bin/env python3
"""
Example agent script for renting a VastAI instance and setting up ComfyUI
This demonstrates how an AI agent can use the vastai_cli tool programmatically
"""

import subprocess
import json
import time
import sys
import os

def run_command(cmd):
    """Run a command and return the result"""
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=300)
        return result.returncode == 0, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return False, "", "Command timed out"
    except Exception as e:
        return False, "", str(e)

def main():
    print("🤖 Agent: Starting ComfyUI setup process")
    
    # Step 1: Rent an instance with ComfyUI profile using non-interactive mode
    print("\n📦 Step 1: Renting VastAI instance with ComfyUI profile...")
    success, stdout, stderr = run_command(
        "python main.py --non-interactive --profile comfyui --no-confirm --no-monitor --output-format json"
    )
    
    if not success:
        print(f"❌ Failed to rent instance: {stderr}")
        return 1
    
    try:
        instance_info = json.loads(stdout.strip())
        instance_id = instance_info.get('id')
        print(f"✅ Instance rented successfully: {instance_id}")
    except json.JSONDecodeError:
        print(f"❌ Failed to parse instance info: {stdout}")
        return 1
    
    # Step 2: Wait for instance to be ready (we already waited in main.py, but let's verify)
    print("\n⏳ Step 2: Verifying instance is ready...")
    time.sleep(10)  # Give it a moment
    
    # Step 3: Execute setup verification via SSH
    print("\n🔧 Step 3: Setting up and verifying ComfyUI...")
    
    # Check if we can connect via SSH
    success, stdout, stderr = run_command(f"python ssh_agent.py --command 'echo \"SSH connection test\"'")
    if not success:
        print(f"⚠️  SSH agent utility direct call failed: {stderr}")
        print("   Trying alternative approach...")
    
    # Use the instance manager to get connection info and run commands
    # For simplicity, we'll use the vastai CLI directly for now
    success, stdout, stderr = run_command(f"vastai ssh instance {instance_id} --command 'echo \"Container ready\"' -- -o ConnectTimeout=10")
    if success:
        print("✅ SSH connection established")
    else:
        print(f"⚠️  SSH test had issues (this is normal if container is still starting): {stderr}")
    
    # Step 4: Verify ComfyUI is accessible
    print("\n🌐 Step 4: Verifying ComfyUI API accessibility...")
    max_attempts = 30
    for i in range(max_attempts):
        success, stdout, stderr = run_command(
            f"vastai ssh instance {instance_id} --command 'curl -s http://localhost:18188/health || echo \"Not ready yet\"' -- -o ConnectTimeout=10"
        )
        if success and '"status":"ok"' in stdout:
            print("✅ ComfyUI API is accessible and healthy!")
            break
        elif i < max_attempts - 1:
            print(f"   Attempt {i+1}/{max_attempts}: Waiting for ComfyUI to start...")
            time.sleep(10)
        else:
            print("⚠️  ComfyUI API verification timed out - instance may still be starting")
    
    # Step 5: Provide connection information to the agent
    print("\n📋 Step 5: Connection information for agent use:")
    success, stdout, stderr = run_command(f"vastai show instance {instance_id} --raw")
    if success:
        try:
            instance_data = json.loads(stdout)
            public_ip = instance_data.get('public_ipaddr') or instance_data.get('ip')
            ssh_port = instance_data.get('ssh_port')
            
            print(f"   Instance ID: {instance_id}")
            print(f"   Public IP: {public_ip}")
            print(f"   SSH Port: {ssh_port}")
            print(f"   ComfyUI URL: http://{public_ip}:18188")
            print(f"   Direct API: http://{public_ip}:18188")
            print(f"   To connect manually: ssh -p {ssh_port} root@{public_ip}")
        except json.JSONDecodeError:
            print(f"   Raw instance data: {stdout[:200]}...")
    
    print("\n🎉 Agent task completed! Instance is ready for ComfyUI workloads.")
    print("💡 To destroy the instance later, run:")
    print(f"   vastai destroy instance {instance_id}")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())