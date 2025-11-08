"""
Configuration management for the Marketing Command Centre Discord Bot
"""

import json
import os
from typing import Dict, Any, Optional
from threading import Lock

class ConfigManager:
    """Thread-safe configuration manager that loads from JSON"""
    
    def __init__(self, config_file: str = "settings.json"):
        self.config_file = os.path.join(os.path.dirname(__file__), config_file)
        self._config: Dict[str, Any] = {}
        self._lock = Lock()
        self.load_config()
    
    def load_config(self) -> None:
        """Load configuration from JSON file"""
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                with self._lock:
                    self._config = json.load(f)
            print(f"✅ Loaded configuration from {os.path.basename(self.config_file)}")
        except FileNotFoundError:
            print(f"❌ Configuration file {self.config_file} not found!")
            self._create_default_config()
        except json.JSONDecodeError as e:
            print(f"❌ Invalid JSON in {self.config_file}: {e}")
            raise
        except Exception as e:
            print(f"❌ Error loading configuration: {e}")
            raise
    
    def reload_config(self) -> bool:
        """Reload configuration from file (useful for runtime updates)"""
        try:
            self.load_config()
            return True
        except Exception as e:
            print(f"❌ Failed to reload configuration: {e}")
            return False
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get a configuration value by key"""
        with self._lock:
            return self._config.get(key, default)
    
    def get_nested(self, *keys: str, default: Any = None) -> Any:
        """Get a nested configuration value"""
        with self._lock:
            current = self._config
            for key in keys:
                if isinstance(current, dict) and key in current:
                    current = current[key]
                else:
                    return default
            return current
    
    def set_nested(self, *keys: str, value: Any) -> None:
        """Set a nested configuration value"""
        with self._lock:
            current = self._config
            for key in keys[:-1]:
                if key not in current:
                    current[key] = {}
                current = current[key]
            current[keys[-1]] = value
    
    def save_config(self) -> bool:
        """Save current configuration to file"""
        try:
            with self._lock:
                with open(self.config_file, 'w', encoding='utf-8') as f:
                    json.dump(self._config, f, indent=2, ensure_ascii=False)
            print(f"✅ Saved configuration to {os.path.basename(self.config_file)}")
            return True
        except Exception as e:
            print(f"❌ Failed to save configuration: {e}")
            return False
    
    def _create_default_config(self) -> None:
        """Create a default configuration file if none exists"""
        default_config = {
            "roles": {
                "admin": "Admin",
                "content_creator": "Content Creator",
                "graphic_designer": "Graphic Designer",
                "social_media_manager": "Social Media Manager"
            },
            "departments": {},
            "department_subgroups": {},
            "categories": {
                "queue": "📥 In Queue",
                "progress": "🔄 In Progress",
                "awaiting": "⏳ Awaiting Posting",
                "done": "✅ Done"
            }
        }
        
        with self._lock:
            self._config = default_config
        self.save_config()

# Create global config manager instance
config = ConfigManager()

# Legacy compatibility functions
def _update_legacy_vars():
    """Update legacy variable names for backward compatibility"""
    global ROLES, DEPARTMENTS, CATEGORIES, REQUEST_TYPES, PRIORITIES
    global BOT_CONFIG, EMBED_COLORS, MESSAGES, DATE_FORMATS, DEPARTMENT_SUBGROUPS
    
    # Convert to uppercase keys for legacy compatibility
    ROLES = {k.upper(): v for k, v in config.get("roles", {}).items()}
    DEPARTMENTS = config.get("departments", {})
    CATEGORIES = config.get("categories", {})
    DEPARTMENT_SUBGROUPS = config.get("department_subgroups", {})  # New
    
    # Convert request types to match legacy format
    REQUEST_TYPES = {}
    for req_type, data in config.get("request_types", {}).items():
        REQUEST_TYPES[req_type] = {
            "emoji": data.get("emoji", "📄"),
            "prefix": data.get("prefix", f"[{req_type.upper()}]"),
            "color": data.get("color", 0x3498db),
            "role": data.get("role", "").upper()
        }
    
    PRIORITIES = config.get("priorities", {})
    BOT_CONFIG = config.get("bot_config", {})
    EMBED_COLORS = config.get("embed_colors", {})
    MESSAGES = config.get("messages", {})
    DATE_FORMATS = config.get("date_formats", {
        "input": "%m/%d/%Y",
        "display": "%B %d, %Y",
        "channel": "%m/%d"
    })

# Status mapping between Discord display names and backend enum values
STATUS_MAPPING = {
    # Discord display name -> Backend enum value
    "📥 In Queue": "IN_QUEUE",
    "🔄 In Progress": "IN_PROGRESS",
    "⏳ Awaiting Posting": "AWAITING_POSTING",
    "✅ Done": "DONE",
    "🚫 Blocked": "BLOCKED"
}

# Reverse mapping for backend enum -> Discord display name
REVERSE_STATUS_MAPPING = {v: k for k, v in STATUS_MAPPING.items()}

# Initialize legacy variables
_update_legacy_vars()

# Status conversion functions
def discord_status_to_backend(discord_status: str) -> str:
    """Convert Discord display status to backend enum value
    
    Args:
        discord_status: Discord status like "📥 In Queue"
        
    Returns:
        Backend enum value like "IN_QUEUE"
    """
    return STATUS_MAPPING.get(discord_status, "IN_QUEUE")

def backend_status_to_discord(backend_status: str) -> str:
    """Convert backend enum value to Discord display status
    
    Args:
        backend_status: Backend status like "IN_QUEUE"
        
    Returns:
        Discord display status like "📥 In Queue"
    """
    return REVERSE_STATUS_MAPPING.get(backend_status, "📥 In Queue")

# Convenience functions
def reload_config() -> bool:
    """Reload configuration from file and update legacy variables"""
    if config.reload_config():
        _update_legacy_vars()
        return True
    return False

def get_marketing_role_id() -> Optional[int]:
    """Get the marketing role ID from server config"""
    return config.get_nested("server_config", "marketing_role_id")

def get_reminder_channel_id() -> Optional[int]:
    """Get the reminder channel ID from server config"""
    return config.get_nested("server_config", "reminder_channel_id")

def add_department_member(department: str, user_id: int) -> bool:
    """Add a member to a department"""
    try:
        current_members = config.get_nested("departments", department, "members", default=[])
        if user_id not in current_members:
            current_members.append(user_id)
            config.set_nested("departments", department, "members", value=current_members)
            config.save_config()
            _update_legacy_vars()
            return True
        return False
    except Exception as e:
        print(f"Error adding department member: {e}")
        return False

def remove_department_member(department: str, user_id: int) -> bool:
    """Remove a member from a department"""
    try:
        current_members = config.get_nested("departments", department, "members", default=[])
        if user_id in current_members:
            current_members.remove(user_id)
            config.set_nested("departments", department, "members", value=current_members)
            config.save_config()
            _update_legacy_vars()
            return True
        return False
    except Exception as e:
        print(f"Error removing department member: {e}")
        return False

# New helper accessors for subgroups
def get_department_subgroup_members(department: str, subgroup: str):
    try:
        subgroups = config.get("department_subgroups", {})
        dept_subgroups = subgroups.get(department, {})
        subgroup_data = dept_subgroups.get(subgroup, {})
        members = subgroup_data.get("members", [])
        print(f"🔍 Getting subgroup members for {department}.{subgroup}: {members}")
        return members
    except Exception as e:
        print(f"Error getting subgroup members: {e}")
        return []

def get_department_role_id(dept_key: str) -> Optional[int]:
    try:
        return config.get_nested('departments', dept_key, 'role_id')
    except Exception:
        return None

def get_subdepartment_role_id(dept_key: str, subgroup_key: str) -> Optional[int]:
    try:
        return config.get_nested('department_subgroups', dept_key, subgroup_key, 'role_id')
    except Exception:
        return None


# Creation utilities
def create_department(dept_key: str, display_name: str) -> bool:
    """Create a new department entry if it doesn't exist."""
    try:
        if config.get_nested('departments', dept_key) is not None:
            return False  # already exists
        config.set_nested('departments', dept_key, value={'name': display_name, 'members': [], 'role_name': display_name, 'role_id': None})
        config.save_config()
        _update_legacy_vars()
        return True
    except Exception as e:
        print(f"Error creating department: {e}")
        return False

def get_category_id_for_status(status: str) -> Optional[int]:
    """Get the Discord category ID for a given request status.
    
    Args:
        status: The request status (e.g., 'in_queue', 'in_progress', etc.)
        
    Returns:
        The Discord category ID, or None if not configured
    """
    status_mapping = {
        'in_queue': 'queue',
        'in_progress': 'progress', 
        'awaiting_posting': 'awaiting',
        'done': 'done',
        'blocked': 'blocked'
    }
    
    category_key = status_mapping.get(status)
    if category_key:
        return config.get_nested("categories", category_key, "category_id")
    return None

def get_category_name_for_status(status: str) -> Optional[str]:
    """Get the Discord category name for a given request status.
    
    Args:
        status: The request status (e.g., 'in_queue', 'in_progress', etc.)
        
    Returns:
        The Discord category name, or None if not configured
    """
    status_mapping = {
        'in_queue': 'queue',
        'in_progress': 'progress',
        'awaiting_posting': 'awaiting', 
        'done': 'done',
        'blocked': 'blocked'
    }
    
    category_key = status_mapping.get(status)
    if category_key:
        return config.get_nested("categories", category_key, "name")
    return None

def set_category_id_for_status(status: str, category_id: int) -> bool:
    """Set the Discord category ID for a given request status.
    
    Args:
        status: The request status (e.g., 'in_queue', 'in_progress', etc.)
        category_id: The Discord category ID to associate with this status
        
    Returns:
        True if successful, False otherwise
    """
    status_mapping = {
        'in_queue': 'queue',
        'in_progress': 'progress',
        'awaiting_posting': 'awaiting',
        'done': 'done',
        'blocked': 'blocked'
    }
    
    category_key = status_mapping.get(status)
    if category_key:
        try:
            config.set_nested("categories", category_key, "category_id", value=category_id)
            return config.save_config()
        except Exception as e:
            print(f"Error setting category ID for status {status}: {e}")
            return False
    return False

def get_all_status_category_mappings() -> Dict[str, Optional[int]]:
    """Get all status to category ID mappings.
    
    Returns:
        Dictionary mapping status strings to category IDs
    """
    mappings = {}
    statuses = ['in_queue', 'in_progress', 'awaiting_posting', 'done', 'blocked']
    
    for status in statuses:
        mappings[status] = get_category_id_for_status(status)
    
    return mappings

def get_status_for_category_id(category_id: int) -> Optional[str]:
    """Get the request status for a given Discord category ID.
    
    Args:
        category_id: The Discord category ID
        
    Returns:
        The request status string (e.g., 'in_queue'), or None if not found
    """
    mappings = get_all_status_category_mappings()
    for status, cat_id in mappings.items():
        if cat_id == category_id:
            return status
    return None

# --- Department and Subdepartment mutation helpers ---
def create_subdepartment(dept_key: str, subgroup_key: str, display_name: str) -> bool:
    """Create a new sub-department entry under a department.
    Returns True if created, False if already exists or department missing.
    """
    try:
        existing_dept = config.get_nested('departments', dept_key)
        if existing_dept is None:
            return False
        subgroups = config.get('department_subgroups', {})
        if dept_key not in subgroups:
            subgroups[dept_key] = {}
        if subgroup_key in subgroups[dept_key]:
            return False
        subgroups[dept_key][subgroup_key] = {
            'name': display_name,
            'members': [],
            'role_name': display_name,
            'role_id': None
        }
        config.set_nested('department_subgroups', dept_key, value=subgroups[dept_key])
        config.save_config()
        _update_legacy_vars()
        return True
    except Exception as e:
        print(f"Error creating subdepartment: {e}")
        return False

def delete_department(dept_key: str) -> bool:
    """Delete a department and its subgroups from configuration.
    Note: This does not delete any Discord roles; handle that in calling code.
    """
    try:
        data = config.get('departments', {})
        if dept_key not in data:
            return False
        # Remove department
        with config._lock:
            # Directly mutate internal dict safely under lock
            config._config.get('departments', {}).pop(dept_key, None)
            # Remove any subgroups for this department
            if 'department_subgroups' in config._config:
                config._config['department_subgroups'].pop(dept_key, None)
        if config.save_config():
            _update_legacy_vars()
            return True
        return False
    except Exception as e:
        print(f"Error deleting department: {e}")
        return False

def delete_subdepartment(dept_key: str, subgroup_key: str) -> bool:
    """Delete a sub-department entry from configuration.
    Note: This does not delete any Discord roles; handle that in calling code.
    """
    try:
        subgroups = config.get('department_subgroups', {})
        if dept_key not in subgroups or subgroup_key not in subgroups.get(dept_key, {}):
            return False
        with config._lock:
            config._config.setdefault('department_subgroups', {}).get(dept_key, {}).pop(subgroup_key, None)
            # If no more subgroups under dept, clean up the key
            if not config._config['department_subgroups'].get(dept_key):
                config._config['department_subgroups'].pop(dept_key, None)
        if config.save_config():
            _update_legacy_vars()
            return True
        return False
    except Exception as e:
        print(f"Error deleting subdepartment: {e}")
        return False
