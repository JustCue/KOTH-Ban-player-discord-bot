import json
import os

CONFIG_FILE = 'config.json'

def load_config():
    """Loads the configuration from config.json. Creates a default file if it doesn't exist."""
    if not os.path.exists(CONFIG_FILE):
        default_config = {
            "moderator_roles": [],
            "channels": {
                "pending_bans": None
            }
        }
        save_config(default_config)
        return default_config
    
    try:
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        # In case of a corrupted file, create a new default one
        return load_config() # Recursive call to create the default

def save_config(data):
    """Saves the configuration data to config.json."""
    with open(CONFIG_FILE, 'w') as f:
        json.dump(data, f, indent=4)