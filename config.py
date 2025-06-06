# config.py
import os

# Important: Configure these for your server!
# Role names (case-sensitive) or Role IDs (as integers)
# Example: MODERATOR_ROLES = ["Head Admin", "Moderator", 123456789012345678]
MODERATOR_ROLES_CONFIG = ["Moderator", "Admin"]

# Example for channel IDs if you want to use specific channels for logs/pending bans
# Make sure to set these in your .env file if you use them
LOG_CHANNEL_ID = int(os.getenv("PENDING_BAN_CHANNEL_ID", 0))
PENDING_BAN_CHANNEL_ID = int(os.getenv("PENDING_BAN_CHANNEL_ID", 0))

# Bot prefix (if you decide to re-enable prefix commands alongside slash commands)
BOT_PREFIX = os.getenv("BOT_PREFIX", "!")