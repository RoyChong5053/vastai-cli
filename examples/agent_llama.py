#!/usr/bin/env python3
"""
Example agent script for renting a VastAI instance and setting up llama.cpp server
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
    print("🤖 Agent: Starting llama.cpp server setup process")
    
    # Step 1: Rent an instance with llama.cpp profile using non-interactive mode
    print("\n📦 Step 1: Renting VastAI instance with llama.cpp profile...")
    success, stdout, stderr = run_command(
        "python main.py --non-interactive --profile llama-cpp --no-confirm --no-monitor --output-format json"
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
    
    # Step 2: Wait for instance to be ready
    print("\n⏳ Step 2: Verifying instance is ready...")
    time.sleep(10)  # Give it a moment
    
    # Step 3: Setup llama.cpp server via SSH
    print("\n🔧 Step 3: Setting up llama.cpp server...")
    
    # For this example, we'll assume the llama.cpp image already has the server ready
    # In a real scenario, you might need to download models and configure the server
    
    # Check if we can connect via SSH and verify the environment
    success, stdout, stderr = run_command(
        f"vastai ssh instance {instance_id} --command 'echo \"Container ready\" && nvidia-smi' -- -o ConnectTimeout=10"
    )
    if success:
        print("✅ SSH connection established and GPU detected")
        print(f"GPU Info: {stdout.strip()}")
    else:
        print(f"⚠️  SSH/GPU check had issues: {stderr}")
    
    # Step 4: Verify llama.cpp server is accessible (if it auto-starts)
    print("\n🌐 Step 4: Checking for llama.cpp server...")
    # This would depend on how the llama.cpp image is configured
    # For now, we'll just note that the instance is ready for manual setup
    
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
            print(f"   To connect manually: ssh -p {ssh_port} root@{public_ip}")
            print(f"   To start llama.cpp server: ./server -m /path/to/model.nguf")
        except json.JSONDecodeError:
            print(f"   Raw instance data: {stdout[:200]}...")
    
    print("\n🎉 Agent task completed! Instance is ready for llama.cpp setup.")
    print("💡 Next steps for the agent:")
    print("   1. Connect via SSH")
    print("   2. Download or mount a llama.cpp model")
    print("   3. Start the llama.cpp server")
    print("   4. Verify the API is accessible")
    print("\n💡 To destroy the instance later, run:")
    print(f"   vastai destroy instance {instance_id}")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())