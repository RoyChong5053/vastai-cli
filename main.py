#!/usr/bin/env python3
"""
VastAI Instance Manager v2.2 - Main entry point
Enhanced version: supports both interactive and non-interactive (agent) modes
"""

import sys
import logging
import argparse
import json
from typing import Optional, Dict, Any

from config import Config
from utils import setup_logging, check_vastai_cli, get_confirmation
from price_checker import PriceChecker
from instances_manager import InstancesManagerV2

def select_offer_interactive(offers: list) -> Optional[Dict[str, Any]]:
    """Let user select an offer interactively"""
    if not offers:
        print("No offers available")
        return None

    price_checker = PriceChecker()
    price_checker.display_offers({"top_offers": offers})

    while True:
        try:
            choice = input("\nEnter the number of the instance you want to rent (0 to exit): ").strip()
            if choice == '0':
                return None

            choice_idx = int(choice) - 1
            if 0 <= choice_idx < len(offers):
                selected = offers[choice_idx]
                print(f"\nSelected: {selected.get('gpu_name', 'Unknown GPU')}")
                print(f"Price: ${selected.get('dph_total', 0):.6f}/hr")
                return selected
            else:
                print("Invalid choice. Please enter a number from the list.")

        except ValueError:
            print("Invalid input. Please enter a number.")
        except KeyboardInterrupt:
            print("\nOperation cancelled.")
            return None


def select_offer_non_interactive(offers: list, criteria: Optional[Dict[str, Any]] = None, offer_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
    """Select an offer based on criteria or specific ID for non-interactive mode"""
    if not offers:
        print("No offers available")
        return None

    # If specific offer ID is requested
    if offer_id is not None:
        for offer in offers:
            if offer.get('id') == offer_id:
                print(f"Selected offer ID {offer_id}: {offer.get('gpu_name', 'Unknown GPU')}")
                print(f"Price: ${offer.get('dph_total', 0):.6f}/hr")
                return offer
        print(f"Offer ID {offer_id} not found in available offers")
        return None

    # Filter offers based on criteria
    filtered_offers = offers
    if criteria:
        filtered_offers = []
        for offer in offers:
            match = True
            for key, value in criteria.items():
                if key in offer:
                    # Handle special comparison for price (less than or equal)
                    if key == 'max_price_per_hour':
                        price = offer.get('dph_total', offer.get('$hr', float('inf')))
                        if isinstance(price, str):
                            try:
                                price = float(price.replace('$', ''))
                            except ValueError:
                                match = False
                                continue
                        if price > value:
                            match = False
                            break
                    # Handle exact match for other fields
                    elif offer[key] != value:
                        match = False
                        break
                else:
                    match = False
                    break
            if match:
                filtered_offers.append(offer)

    if not filtered_offers:
        print("No offers match the specified criteria")
        return None

    # Sort by price (ascending) and return the cheapest matching offer
    filtered_offers.sort(key=lambda x: x.get('dph_total', x.get('$hr', float('inf'))))
    selected = filtered_offers[0]
    print(f"Selected offer ID {selected.get('id')}: {selected.get('gpu_name', 'Unknown GPU')}")
    print(f"Price: ${selected.get('dph_total', 0):.6f}/hr")
    return selected

def main():
    """Main function"""
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="VastAI Instance Manager - Rent and manage VastAI instances")
    parser.add_argument("--non-interactive", action="store_true", help="Run in non-interactive mode for agent use")
    parser.add_argument("--offer-id", type=int, help="Specific offer ID to use (bypasses selection)")
    parser.add_argument("--criteria", type=str, help="JSON string of offer criteria (e.g., '{\"max_price_per_hour\": 2.0, \"gpu_name\": \"RTX 4090\"}')")
    parser.add_argument("--no-confirm", action="store_true", help="Skip instance creation confirmation")
    parser.add_argument("--no-monitor", action="store_true", help="Skip post-creation monitoring")
    parser.add_argument("--timeout", type=int, help="Custom timeout for instance readiness (seconds)")
    parser.add_argument("--profile", type=str, help="Use predefined configuration profile (comfyui, llama.cpp, ollama, etc.)")
    parser.add_argument("--output-format", choices=["json", "text"], default="text", help="Output format for machine-readable information")
    parser.add_argument("--setup-script", type=str, help="Path or URL to setup script to run on instance after creation")
    
    args = parser.parse_args()
    
    # Setup logging
    setup_logging(Config.LOG_FILE)
    logging.info("Starting VastAI Instance Manager v2.2")
    
    # Apply profile if specified
    if args.profile:
        apply_profile(args.profile)
    
    # Print header only in interactive mode or if output format is text
    if not args.non_interactive or args.output_format == "text":
        print("🚀 VastAI Instance Manager v2.2")
        print("=" * 40)
        print("Enhanced version: Improved error handling and user experience")
        print("Cleanup check on exit to prevent unnecessary costs")
        print("=" * 40)

    # Check if VastAI CLI is available
    if not check_vastai_cli():
        print("❌ VastAI CLI is not available. Please install it first.")
        print("Visit: https://vast.ai/docs/cli")
        sys.exit(1)

    # Initialize components
    price_checker = PriceChecker()
    instance_manager = InstancesManagerV2()

    try:
        # Step 1: Clear old instances file
        print("\n🧹 Clearing old instances file to avoid ID confusion...")
        instance_manager.clear_old_instances_file()

        # Step 2: Fetch and process offers (always refresh)
        print("\n📊 Fetching latest VastAI offers...")
        offers_data = price_checker.fetch_and_process_offers()

        if not offers_data or not offers_data.get('top_offers'):
            print("❌ Failed to fetch offers. Please check your internet connection and VastAI CLI setup.")
            sys.exit(1)

        offers = offers_data['top_offers']
        print(f"✅ Found {len(offers)} suitable offers")

        # Step 3: Select an offer
        if args.non_interactive:
            # Parse criteria if provided
            criteria = None
            if args.criteria:
                try:
                    criteria = json.loads(args.criteria)
                except json.JSONDecodeError as e:
                    print(f"❌ Invalid criteria JSON: {e}")
                    sys.exit(1)
            
            selected_offer = select_offer_non_interactive(offers, criteria, args.offer_id)
            if not selected_offer:
                print("ℹ️  No instance selected. Exiting.")
                sys.exit(0)
        else:
            selected_offer = select_offer_interactive(offers)
            if not selected_offer:
                print("ℹ️  No instance selected. Exiting.")
                sys.exit(0)

        # Step 4: Confirm creation
        price = selected_offer.get('dph_total', 0)
        gpu_name = selected_offer.get('gpu_name', 'Unknown')
        location = selected_offer.get('geolocation', 'Unknown')

        # Print summary only in interactive mode or text output
        if not args.non_interactive or args.output_format == "text":
            print(f"\n📋 Instance Summary:")
            print(f"   GPU: {gpu_name}")
            print(f"   Location: {location}")
            print(f"   Price: ${price:.6f}/hour")
            print(f"   Disk: {selected_offer.get('disk_space', 0):.1f} GB")

        # Handle confirmation
        if args.no_confirm:
            # In non-interactive mode with no-confirm, proceed automatically
            if not args.non_interactive:
                print("ℹ️  Skipping confirmation (--no-confirm flag)")
        else:
            # Interactive confirmation or explicit confirmation required
            if not get_confirmation("Create this instance?"):
                print("ℹ️  Instance creation cancelled.")
                sys.exit(0)

        # Step 5: Create instance
        if not args.non_interactive or args.output_format == "text":
            print("\n🏗️  Creating instance...")
        if not instance_manager.create_instance(selected_offer):
            if args.output_format == "json":
                print(json.dumps({"error": "Failed to create instance"}))
            else:
                print("❌ Failed to create instance. Please check VastAI CLI output above.")
            sys.exit(1)

        if args.output_format == "json":
            # Output instance info as JSON for agent consumption
            instance_info = instance_manager.get_instance_detailed_info()
            if instance_info:
                print(json.dumps(instance_info))
            else:
                print(json.dumps({"instance_id": instance_manager.current_instance_id, "status": "created"}))
        else:
            print("✅ Instance creation initiated")
            print(f"📄 Instance info saved to instances.json")

        # Step 6: Wait for instance to be ready
        timeout_to_use = args.timeout if args.timeout else None
        if not wait_for_instance_ready_with_timeout(instance_manager, timeout_to_use):
            if args.output_format == "json":
                print(json.dumps({"error": "Instance failed to start or timed out"}))
            else:
                print("❌ Instance failed to start or timed out.")
                print("💡 You can check instance status manually with: vastai show instances")
            sys.exit(1)

        # Step 6b: Run setup script if specified
        if args.setup_script:
            if args.output_format == "json":
                print(json.dumps({"status": "running_setup_script", "script": args.setup_script}))
            elif not args.non_interactive:
                print(f"\n🚀 Running setup script: {args.setup_script}")
            
            # Import and run the setup script via SSH agent utility
            try:
                from ssh_agent import run_script_on_instance
                
                # Read script content (could be a URL or file path)
                script_content = None
                if args.setup_script.startswith(('http://', 'https://')):
                    # Download script from URL
                    import urllib.request
                    try:
                        with urllib.request.urlopen(args.setup_script) as response:
                            script_content = response.read().decode('utf-8')
                    except Exception as e:
                        error_msg = f"Failed to download setup script from URL: {e}"
                        if args.output_format == "json":
                            print(json.dumps({"error": error_msg}))
                        else:
                            print(f"❌ {error_msg}")
                        sys.exit(1)
                else:
                    # Read script from local file
                    try:
                        with open(args.setup_script, 'r') as f:
                            script_content = f.read()
                    except Exception as e:
                        error_msg = f"Failed to read setup script file: {e}"
                        if args.output_format == "json":
                            print(json.dumps({"error": error_msg}))
                        else:
                            print(f"❌ {error_msg}")
                        sys.exit(1)
                
                if script_content is not None:
                    success, stdout, stderr = run_script_on_instance(script_content)
                    if args.output_format == "json":
                        result = {
                            "status": "setup_script_completed",
                            "success": success,
                            "stdout": stdout,
                            "stderr": stderr
                        }
                        print(json.dumps(result))
                    else:
                        if success:
                            print("✅ Setup script completed successfully")
                            if stdout.strip():
                                print(f"Script output:\n{stdout}")
                        else:
                            print("❌ Setup script failed")
                            if stderr.strip():
                                print(f"Script error:\n{stderr}")
                            # Don't exit on setup script failure - just warn
                            print("⚠️  Continuing despite setup script failure")
                else:
                    if args.output_format == "json":
                        print(json.dumps({"error": "Setup script content is empty"}))
                    else:
                        print("❌ Setup script content is empty")
                        sys.exit(1)
                        
            except ImportError:
                error_msg = "SSH agent utility not available for setup script execution"
                if args.output_format == "json":
                    print(json.dumps({"error": error_msg}))
                else:
                    print(f"❌ {error_msg}")
                sys.exit(1)
            except Exception as e:
                error_msg = f"Unexpected error running setup script: {e}"
                if args.output_format == "json":
                    print(json.dumps({"error": error_msg}))
                else:
                    print(f"❌ {error_msg}")
                sys.exit(1)

        # Step 7: Show initial status
        if not args.no_monitor and (not args.non_interactive or args.output_format == "text"):
            print("\n" + "=" * 60)
            print("✅ Instance is ready! Starting status monitoring...")
            print("=" * 60)
            print("")
            instance_manager.show_instances_status()

        # Step 8: Start simple monitoring
        if not args.no_monitor and (not args.non_interactive or args.output_format == "text"):
            print("\n📈 Starting instance monitoring...")
            print("   This will show instance status periodically.")
            print("   Press Ctrl+C to stop monitoring and check for cleanup.")
            print("")
            instance_manager.monitor_instances_simple(interval=30)

    except KeyboardInterrupt:
        if args.non_interactive and args.output_format == "json":
            print(json.dumps({"error": "Operation interrupted by user", "instance_id": getattr(instance_manager, 'current_instance_id', None)}))
        else:
            print("\n\n⚠️  Operation interrupted by user.")
            
            # Check if we have a current instance
            if instance_manager.current_instance_id:
                if not args.non_interactive or args.output_format == "text":
                    print(f"\nCurrent instance ID: {instance_manager.current_instance_id}")
                    
                    # Offer to destroy current instance
                    if get_confirmation(f"Destroy current instance {instance_manager.current_instance_id}?"):
                        instance_manager.destroy_current_instance()
            
            # Always check for cleanup of any running instances
            if not args.non_interactive or args.output_format == "text":
                print("\n" + "=" * 60)
                print("🧹 Checking for any running instances that might be costing money...")
                instance_manager.check_and_cleanup_instances(non_interactive=args.non_interactive)

    except Exception as e:
        logging.error(f"Unexpected error: {e}")
        print(f"\n❌ An unexpected error occurred: {e}")
        print("Check the log file for more details.")

        # Cleanup on error
        if instance_manager.current_instance_id:
            print("Attempting to destroy failed instance...")
            instance_manager.destroy_current_instance()

        sys.exit(1)

    finally:
        # Final cleanup check
        if not args.non_interactive or args.output_format == "text":
            print("\n" + "=" * 60)
            print("🔚 Final cleanup check before exit...")
            instance_manager.check_and_cleanup_instances(non_interactive=args.non_interactive)
            print("\n👋 Exiting VastAI Instance Manager v2.2")

def apply_profile(profile_name: str):
    """Apply a configuration profile"""
    # Use the profile manager to apply the profile
    success = profile_manager.apply_profile(profile_name, Config)
    if success:
        logging.info(f"Applied profile '{profile_name}'")
        if not args.non_interactive or args.output_format == "text":
            print(f"ℹ️  Applied profile '{profile_name}'")
    else:
        logging.error(f"Failed to apply profile '{profile_name}'")
        if not args.non_interactive or args.output_format == "text":
            print(f"❌ Failed to apply profile '{profile_name}'")


def wait_for_instance_ready_with_timeout(instance_manager, timeout_seconds: int = None) -> bool:
    """Wait for instance to be ready with optional custom timeout"""
    if timeout_seconds is not None:
        # Temporarily override the timeout in config
        original_timeout = Config.IP_CHECK_MAX_ATTEMPTS
        Config.IP_CHECK_MAX_ATTEMPTS = timeout_seconds // Config.IP_CHECK_INTERVAL
        if Config.IP_CHECK_MAX_ATTEMPTS < 1:
            Config.IP_CHECK_MAX_ATTEMPTS = 1
    
    try:
        result = instance_manager.wait_for_instance_ready()
        return result
    finally:
        # Restore original timeout if we changed it
        if timeout_seconds is not None:
            Config.IP_CHECK_MAX_ATTEMPTS = original_timeout


if __name__ == "__main__":
    main()