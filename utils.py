"""
Utility functions for VastAI CLI tool
"""

import subprocess
import json
import logging
import sys
from typing import Optional, Dict, Any
from pathlib import Path
import time

def setup_logging(log_file: str = "vastai.log", level: int = logging.INFO):
    """Setup logging configuration"""
    # Determine log level based on config
    from config import Config
    if Config.DEBUG_MODE:
        level = logging.DEBUG
    elif Config.VERBOSE_LOGGING:
        level = logging.DEBUG
    
    # Create formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Setup handlers
    handlers = []
    
    # File handler
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setFormatter(formatter)
    handlers.append(file_handler)
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    handlers.append(console_handler)
    
    # Configure logging
    logging.basicConfig(
        level=level,
        handlers=handlers
    )
    
    # Prevent duplicate logs
    logging.getLogger().propagate = False

def run_command(cmd: list, capture_output: bool = True, timeout: int = None, retry_attempts: int = None) -> subprocess.CompletedProcess:
    """Run a command and return the result with retry logic and exponential backoff"""
    from config import Config
    
    # Use config defaults if not provided
    if retry_attempts is None:
        retry_attempts = Config.MAX_RETRY_ATTEMPTS
    
    last_exception = None
    
    for attempt in range(retry_attempts + 1):
        try:
            logging.debug(f"Running command (attempt {attempt + 1}/{retry_attempts + 1}): {' '.join(cmd)}")
            result = subprocess.run(
                cmd,
                capture_output=capture_output,
                text=True,
                check=False,
                timeout=timeout
            )
            
            # If command succeeded, return result
            if result.returncode == 0:
                if attempt > 0:
                    logging.info(f"Command succeeded on attempt {attempt + 1}")
                return result
            else:
                # Command failed but didn't raise exception
                # Check if this is a transient error worth retrying
                error_output = result.stderr.lower()
                is_transient = (
                    "timeout" in error_output or 
                    "connection" in error_output or
                    "temporary" in error_output or
                    "busy" in error_output or
                    result.returncode in [500, 502, 503, 504]  # HTTP-like error codes
                )
                
                if attempt < retry_attempts and is_transient:
                    # Exponential backoff: 2^attempt * base_delay seconds
                    delay = min(Config.RETRY_DELAY * (2 ** attempt), 60)  # Cap at 60 seconds
                    logging.warning(f"Command failed (attempt {attempt + 1}) with transient error, retrying in {delay} seconds...")
                    time.sleep(delay)
                    continue
                elif attempt < retry_attempts:
                    # Non-transient error, still retry with standard delay
                    logging.warning(f"Command failed (attempt {attempt + 1}) with non-transient error, retrying in {Config.RETRY_DELAY} seconds...")
                    time.sleep(Config.RETRY_DELAY)
                    continue
                else:
                    logging.error(f"Command failed after {retry_attempts + 1} attempts")
                    return result
                   
        except subprocess.TimeoutExpired as e:
            last_exception = e
            logging.error(f"Command timed out after {timeout} seconds (attempt {attempt + 1})")
            if attempt < retry_attempts:
                # Exponential backoff for timeouts too
                delay = min(Config.RETRY_DELAY * (2 ** attempt), 60)  # Cap at 60 seconds
                logging.info(f"Retrying in {delay} seconds...")
                time.sleep(delay)
                continue
            else:
                raise e
        except Exception as e:
            last_exception = e
            logging.error(f"Error running command (attempt {attempt + 1}): {e}")
            if attempt < retry_attempts:
                # Exponential backoff for other exceptions
                delay = min(Config.RETRY_DELAY * (2 ** attempt), 60)  # Cap at 60 seconds
                logging.info(f"Retrying in {delay} seconds...")
                time.sleep(delay)
                continue
            else:
                raise e
    
    # If we get here, all retries failed
    raise last_exception

def check_vastai_cli() -> bool:
    """Check if vastai CLI is installed and available"""
    try:
        result = run_command(["vastai", "--version"])
        if result.returncode == 0:
            logging.info("VastAI CLI is available")
            return True
        else:
            logging.error("VastAI CLI is not working properly")
            return False
    except FileNotFoundError:
        logging.error("VastAI CLI is not installed. Please install it first.")
        return False

def load_json_file(file_path: str) -> Optional[Dict[str, Any]]:
    """Load data from JSON file"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        logging.warning(f"File not found: {file_path}")
        return None
    except json.JSONDecodeError as e:
        logging.error(f"Error decoding JSON from {file_path}: {e}")
        return None

def save_json_file(file_path: str, data: Dict[str, Any]) -> bool:
    """Save data to JSON file"""
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        logging.info(f"Data saved to {file_path}")
        return True
    except Exception as e:
        logging.error(f"Error saving data to {file_path}: {e}")
        return False

def format_price(price: float) -> str:
    """Format price for display"""
    return f"${price:.6f}"

def format_size(size: float) -> str:
    """Format size in GB for display"""
    return f"{size:.1f} GB"

def print_progress_bar(current: int, total: int, prefix: str = "", suffix: str = "", length: int = 50):
    """Print a progress bar"""
    percent = current / total
    filled_length = int(length * percent)
    bar = "█" * filled_length + "░" * (length - filled_length)
    sys.stdout.write(f"\r{prefix} [{bar}] {percent:.1%} {suffix}")
    sys.stdout.flush()
    if current == total:
        sys.stdout.write("\n")

def wait_with_progress(seconds: int, message: str = "Waiting"):
    """Wait for specified seconds with progress indication"""
    for i in range(seconds):
        print_progress_bar(i + 1, seconds, prefix=message, suffix=f"{seconds - i}s remaining")
        time.sleep(1)

def get_confirmation(message: str) -> bool:
    """Get user confirmation with enhanced input handling"""
    from config import Config
    
    # Skip confirmation in auto-cleanup mode or when disabled
    if not Config.CONFIRM_DESTROY_ON_EXIT:
        return True
    
    while True:
        try:
            response = input(f"{message} (y/N): ").lower().strip()
            if response in ['y', 'yes', 'Y', 'YES']:
                return True
            elif response in ['n', 'no', 'N', 'NO', '']:
                return False
            elif response in ['q', 'quit', 'exit']:
                print("Operation cancelled by user.")
                sys.exit(0)
            else:
                print("Please enter 'y' for yes, 'n' for no, or 'q' to quit.")
        except KeyboardInterrupt:
            print("\nOperation cancelled by user.")
            sys.exit(0)
        except EOFError:
            print("\nInput stream ended. Assuming 'no'.")
            return False

def clear_file(file_path: str):
    """Delete a file if it exists"""
    try:
        Path(file_path).unlink(missing_ok=True)
        logging.info(f"File {file_path} deleted")
    except Exception as e:
        logging.warning(f"Could not delete {file_path}: {e}")