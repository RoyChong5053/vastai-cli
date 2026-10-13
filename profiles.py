"""
Profile management system for VastAI CLI tool
Handles loading and applying configuration profiles for different software stacks
"""

import os
import yaml
from typing import Dict, Any, Optional, List


class ProfileManager:
    """Manages configuration profiles for different software stacks"""
    
    def __init__(self, profiles_dir: str = None):
        if profiles_dir is None:
            # Default to profiles directory relative to this file
            self.profiles_dir = os.path.join(os.path.dirname(__file__), 'profiles')
        else:
            self.profiles_dir = profiles_dir
        
        # Ensure profiles directory exists
        os.makedirs(self.profiles_dir, exist_ok=True)
        
        # Cache for loaded profiles
        self._profiles_cache = {}
        
        # Load built-in profiles if they exist
        self._load_builtin_profiles()
    
    def _load_builtin_profiles(self):
        """Load built-in profiles from the profiles directory"""
        builtin_profiles = ['base.yaml', 'comfyui.yaml', 'llama-cpp.yaml', 'ollama.yaml']
        
        for profile_file in builtin_profiles:
            profile_path = os.path.join(self.profiles_dir, profile_file)
            if os.path.exists(profile_path):
                try:
                    with open(profile_path, 'r') as f:
                        profile_data = yaml.safe_load(f)
                        if profile_data and 'name' in profile_data:
                            self._profiles_cache[profile_data['name']] = profile_data
                except Exception as e:
                    print(f"Warning: Failed to load profile {profile_file}: {e}")
    
    def list_profiles(self) -> List[str]:
        """List all available profiles"""
        # Reload profiles from disk to pick up any new ones
        self._load_builtin_profiles()
        return list(self._profiles_cache.keys())
    
    def get_profile(self, name: str) -> Optional[Dict[str, Any]]:
        """Get a profile by name"""
        if name in self._profiles_cache:
            return self._profiles_cache[name]
        
        # Try to load from file directly
        profile_path = os.path.join(self.profiles_dir, f"{name}.yaml")
        if os.path.exists(profile_path):
            try:
                with open(profile_path, 'r') as f:
                    profile_data = yaml.safe_load(f)
                    if profile_data and 'name' in profile_data:
                        self._profiles_cache[profile_data['name']] = profile_data
                        return profile_data
            except Exception as e:
                print(f"Warning: Failed to load profile {name}: {e}")
        
        return None
    
    def apply_profile(self, profile_name: str, config_class) -> bool:
        """Apply a profile to override settings in a config class"""
        profile = self.get_profile(profile_name)
        if not profile:
            print(f"Error: Profile '{profile_name}' not found")
            return False
        
        # Apply profile settings to config class
        try:
            # Override image if specified
            if 'image' in profile:
                config_class.DEFAULT_IMAGE = profile['image']
            
            # Override disk size if specified
            if 'disk_size' in profile:
                config_class.DEFAULT_DISK_SIZE = profile['disk_size']
            
            # Override onstart command if specified
            if 'onstart_cmd' in profile:
                config_class.ONSTART_CMD = profile['onstart_cmd']
            
            # Override environment variables if specified
            if 'env_vars' in profile:
                config_class.DEFAULT_ENV_VARS = profile['env_vars']
            
            # Note: Port forwards and setup script would be handled elsewhere
            # as they're not part of the basic Config class
            
            return True
        except Exception as e:
            print(f"Error applying profile '{profile_name}': {e}")
            return False


# Global profile manager instance
profile_manager = ProfileManager()