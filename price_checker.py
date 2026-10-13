"""
Price checker module for VastAI offers
"""

import json
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional
import re

from config import Config
from utils import run_command, save_json_file, load_json_file, format_price, format_size

class PriceChecker:
    """Handles fetching and processing VastAI price data"""

    def __init__(self):
        self.price_file = Config.PRICE_LIST_FILE

    def fetch_offers_raw(self) -> Optional[str]:
        """Fetch raw offers data from VastAI CLI"""
        logging.info("Fetching offers from VastAI...")
        try:
            result = run_command([Config.VASTAI_CMD, "search", "offers", "--raw"])
            if result.returncode == 0 and result.stdout.strip():
                logging.info("Successfully fetched offers data")
                return result.stdout
            else:
                logging.error(f"Failed to fetch offers: {result.stderr}")
                return None
        except Exception as e:
            logging.error(f"Error fetching offers: {e}")
            return None

    def parse_offers_json(self, raw_data: str) -> Optional[List[Dict[str, Any]]]:
        """Parse offers data as JSON"""
        try:
            offers = json.loads(raw_data)
            if isinstance(offers, list):
                logging.info(f"Parsed {len(offers)} offers from JSON")
                return offers
            else:
                logging.warning("Parsed data is not a list")
                return None
        except json.JSONDecodeError:
            logging.warning("Failed to parse as JSON, trying tabular format")
            return None

    def parse_offers_tabular(self, raw_data: str) -> Optional[List[Dict[str, Any]]]:
        """Parse offers data from tabular format (fallback)"""
        try:
            lines = raw_data.strip().split('\n')
            if not lines:
                return None

            # Skip empty lines at the beginning
            while lines and not lines[0].strip():
                lines.pop(0)

            if not lines:
                return None

            # First line should be headers
            header_line = lines[0]
            headers = re.split(r'\s{2,}', header_line.strip())

            offers = []
            for line in lines[1:]:
                if not line.strip():
                    continue

                values = re.split(r'\s{2,}', line.strip())
                if len(values) != len(headers):
                    continue  # Skip malformed lines

                offer = {}
                for i, header in enumerate(headers):
                    value = values[i].strip()
                    # Try to convert to appropriate type
                    try:
                        if '.' in value:
                            offer[header] = float(value)
                        else:
                            offer[header] = int(value)
                    except ValueError:
                        offer[header] = value

                offers.append(offer)

            logging.info(f"Parsed {len(offers)} offers from tabular format")
            return offers

        except Exception as e:
            logging.error(f"Error parsing tabular format: {e}")
            return None

    def filter_and_sort_offers(self, offers: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Filter and sort offers based on criteria"""
        filtered_offers = []

        for offer in offers:
            try:
                price = offer.get('dph_total', offer.get('$hr'))
                disk_size = offer.get('disk_space', offer.get('Disk', 0))
                inet_down_cost = offer.get('internet_down_cost_per_tb', offer.get('inet_down_cost', 0))
                inet_up_cost = offer.get('internet_up_cost_per_tb', offer.get('inet_up_cost', 0))

                # Convert price to float if it's string
                if isinstance(price, str):
                    price = float(price.replace('$', ''))

                # Convert disk_size to float if needed
                if isinstance(disk_size, str):
                    disk_size = float(disk_size.replace('GB', '').strip())

                # Convert internet costs to float if needed
                if isinstance(inet_down_cost, str):
                    inet_down_cost = float(inet_down_cost.replace('$', '').replace('/TB', '').strip())
                if isinstance(inet_up_cost, str):
                    inet_up_cost = float(inet_up_cost.replace('$', '').replace('/TB', '').strip())

                # Apply filters
                if (price and price <= Config.MAX_PRICE_PER_HOUR and
                    disk_size and disk_size >= Config.MIN_DISK_SIZE and
                    inet_down_cost <= Config.MAX_INTERNET_DOWN_COST_PER_TB and
                    inet_up_cost <= Config.MAX_INTERNET_UP_COST_PER_TB):
                    filtered_offers.append(offer)
                else:
                    # Log why this offer was filtered out
                    if price and price > Config.MAX_PRICE_PER_HOUR:
                        logging.debug(f"Filtered out offer {offer.get('id', 'unknown')}: price ${price} > ${Config.MAX_PRICE_PER_HOUR}")
                    if disk_size and disk_size < Config.MIN_DISK_SIZE:
                        logging.debug(f"Filtered out offer {offer.get('id', 'unknown')}: disk {disk_size}GB < {Config.MIN_DISK_SIZE}GB")
                    if inet_down_cost > Config.MAX_INTERNET_DOWN_COST_PER_TB:
                        logging.debug(f"Filtered out offer {offer.get('id', 'unknown')}: inet_down ${inet_down_cost}/TB > ${Config.MAX_INTERNET_DOWN_COST_PER_TB}/TB")
                    if inet_up_cost > Config.MAX_INTERNET_UP_COST_PER_TB:
                        logging.debug(f"Filtered out offer {offer.get('id', 'unknown')}: inet_up ${inet_up_cost}/TB > ${Config.MAX_INTERNET_UP_COST_PER_TB}/TB")

            except (ValueError, TypeError) as e:
                logging.warning(f"Skipping offer due to parsing error: {e}")
                continue

        # Sort by price, then by network efficiency (dlperf_per_dphtotal descending)
        filtered_offers.sort(key=lambda x: (
            x.get('dph_total', x.get('$hr', float('inf'))),
            -x.get('dlperf_per_dphtotal', x.get('DLP/$', 0))
        ))

        return filtered_offers[:Config.MAX_OFFERS_TO_SHOW]

    def get_timestamp(self) -> str:
        """Get current timestamp"""
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def fetch_and_process_offers(self) -> Optional[Dict[str, Any]]:
        """Main method to fetch and process offers"""
        # Clear old price file
        from utils import clear_file
        clear_file(self.price_file)

        # Fetch raw data
        raw_data = self.fetch_offers_raw()
        if not raw_data:
            return None

        # Try parsing as JSON first
        offers = self.parse_offers_json(raw_data)
        if offers is None:
            # Fallback to tabular parsing
            offers = self.parse_offers_tabular(raw_data)

        if not offers:
            logging.error("Failed to parse offers data")
            return None

        # Filter and sort
        top_offers = self.filter_and_sort_offers(offers)

        # Prepare output data
        output_data = {
            "timestamp": self.get_timestamp(),
            "total_offers_found": len(offers),
            "top_offers": top_offers
        }

        # Save to file
        if save_json_file(self.price_file, output_data):
            logging.info(f"Saved {len(top_offers)} top offers to {self.price_file}")
            return output_data
        else:
            logging.error("Failed to save price data")
            return None

    def load_price_data(self) -> Optional[Dict[str, Any]]:
        """Load price data from file"""
        return load_json_file(self.price_file)

    def display_offers(self, offers_data: Dict[str, Any]):
        """Display offers in a readable format"""
        offers = offers_data.get('top_offers', [])
        if not offers:
            print("No offers available")
            return

        print(f"\n--- Available VastAI Instances (Total found: {offers_data.get('total_offers_found', 0)}) ---")
        print(f"Timestamp: {offers_data.get('timestamp', 'Unknown')}")
        print("Filtering: GPU price ≤ $5/hr, Disk ≥ 10GB, Internet ≤ $5/TB")

        for i, offer in enumerate(offers, 1):
            print(f"{i}.")
            print(f"   ID: {offer.get('id', offer.get('ID', 'Unknown'))}")
            print(f"   GPU: {offer.get('num_gpus', 1)} x {offer.get('gpu_name', 'Unknown')}")
            print(f"   CPU: {offer.get('cpu_cores', 'Unknown')} cores, {offer.get('cpu_ram', 0)//1024}GB RAM")
            print(f"   Disk: {format_size(offer.get('disk_space', offer.get('Disk', 0)))}")
            print(f"   Price: {format_price(offer.get('dph_total', offer.get('$hr', 0)))}/hr")

            # Display internet costs
            inet_down = offer.get('internet_down_cost_per_tb', offer.get('inet_down_cost', 0))
            inet_up = offer.get('internet_up_cost_per_tb', offer.get('inet_up_cost', 0))
            print(f"   Internet: ↓${inet_down}/TB ↑${inet_up}/TB")

            print(f"   Location: {offer.get('geolocation', 'Unknown')}")
            if offer.get('dlperf_per_dphtotal'):
                print(f"   Network Efficiency: {offer.get('dlperf_per_dphtotal'):.1f} MB/$")
            print("-" * 50)
