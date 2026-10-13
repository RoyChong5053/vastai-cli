#!/usr/bin/env python3
"""
Example agent script for finding and destroying costly VastAI instances left running
This demonstrates how an AI agent can clean up resources to prevent unnecessary costs
"""

import subprocess
import json
import sys
import os

def run_command(cmd):
    """Run a command and return the result"""
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=60)
        return result.returncode == 0, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return False, "", "Command timed out"
    except Exception as e:
        return False, "", str(e)

def main():
    print("🤖 Agent: Starting cleanup process for costly VastAI instances")
    
    # Step 1: Get list of all running instances
    print("\n🔍 Step 1: Finding all running instances...")
    success, stdout, stderr = run_command("vastai show instances --raw")
    
    if not success:
        print(f"❌ Failed to get instance list: {stderr}")
        return 1
    
    try:
        instances_data = json.loads(stdout)
        if not isinstance(instances_data, list):
            instances_data = [instances_data] if instances_data else []
    except json.JSONDecodeError:
        print(f"❌ Failed to parse instance data: {stdout}")
        return 1
    
    # Filter for running instances
    running_instances = []
    for instance in instances_data:
        state = instance.get('state', '').lower()
        if state in ['running', 'starting', 'provisioning', 'pending']:
            running_instances.append(instance)
    
    print(f"📊 Found {len(instances_data)} total instances, {len(running_instances)} running")
    
    if not running_instances:
        print("✅ No running instances found - nothing to clean up!")
        return 0
    
    # Step 2: Analyze running instances for potential cleanup
    print("\n📋 Step 2: Analyzing running instances...")
    costly_instances = []
    
    for instance in running_instances:
        instance_id = instance.get('id')
        gpu_name = instance.get('gpu_name', 'Unknown')
        dph_total = float(instance.get('dph_total', 0))
        cpu_ram = instance.get('cpu_ram', 0) // 1024  # Convert to GB
        disk_space = instance.get('disk_space', 0)
        
        # Calculate estimated hourly cost
        hourly_cost = dph_total
        
        # Flag instances that are likely costly or unnecessary
        is_costly = (
            hourly_cost > 1.0 or  # More than $1/hour
            gpu_name in ['RTX 4090', 'RTX 3090', 'RTX 3080', 'RTX 4080', 'RTX 4070'] or  # High-end GPUs
            cpu_ram > 32 or  # More than 32GB RAM
            disk_space > 100  # More than 100GB disk
        )
        
        if is_costly:
            costly_instances.append({
                'id': instance_id,
                'gpu': gpu_name,
                'hourly_cost': hourly_cost,
                'ram_gb': cpu_ram,
                'disk_gb': disk_space,
                'instance_data': instance
            })
            print(f"   ⚠️  Instance {instance_id}: {gpu_name} - ${hourly_cost:.3f}/hr - {cpu_ram}GB RAM - {disk_space}GB Disk")
        else:
            print(f"   ✅ Instance {instance_id}: {gpu_name} - ${hourly_cost:.3f}/hr - {cpu_ram}GB RAM - {disk_space}GB Disk (low cost)")
    
    if not costly_instances:
        print("\n✅ No costly instances found that require cleanup!")
        return 0
    
    print(f"\n💰 Found {len(costly_instances)} potentially costly instances to review")
    
    # Step 3: Ask for confirmation to destroy costly instances (in a real agent, this might be automatic based on policies)
    print("\n🗑️  Step 3: Preparing to destroy costly instances...")
    instance_ids_to_destroy = [str(inst['id']) for inst in costly_instances]
    
    print(f"   Instances to be destroyed: {', '.join(instance_ids_to_destroy)}")
    
    # For demonstration, we'll automatically confirm (in a real policy-based agent, this would follow rules)
    print("   🤖 Agent policy: Automatically cleaning up costly instances to prevent unnecessary charges")
    
    # Step 4: Destroy the instances
    print("\n💥 Step 4: Destroying instances...")
    destroyed_count = 0
    failed_count = 0
    
    for instance_id in instance_ids_to_destroy:
        print(f"   Destroying instance {instance_id}...")
        success, stdout, stderr = run_command(f"vastai destroy instance {instance_id}")
        
        if success:
            print(f"   ✅ Instance {instance_id} destroyed successfully")
            destroyed_count += 1
        else:
            print(f"   ❌ Failed to destroy instance {instance_id}: {stderr}")
            failed_count += 1
    
    # Step 5: Report results
    print("\n📈 Step 5: Cleanup results:")
    print(f"   ✅ Successfully destroyed: {destroyed_count} instances")
    if failed_count > 0:
        print(f"   ❌ Failed to destroy: {failed_count} instances")
    
    if destroyed_count > 0:
        # Calculate estimated savings
        total_hourly_savings = sum(inst['hourly_cost'] for inst in costly_instances[:destroyed_count])
        daily_savings = total_hourly_savings * 24
        monthly_savings = daily_savings * 30
        
        print(f"\n💰 Estimated cost savings:")
        print(f"   Hourly: ${total_hourly_savings:.3f}/hr")
        print(f"   Daily: ${daily_savings:.2f}/day")
        print(f"   Monthly: ${monthly_savings:.2f}/month")
    
    print("\n🎉 Agent cleanup task completed!")
    
    return 0 if failed_count == 0 else 1

if __name__ == "__main__":
    sys.exit(main())