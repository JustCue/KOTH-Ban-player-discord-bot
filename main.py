# main.py
import os
import discord
from discord.ext import commands
import asyncio
import traceback
from dotenv import load_dotenv
from typing import Dict, Any

# Import from new structure
from utils.db_utils import PlayerDatabaseConnection
from utils.permissions_utils import is_moderator
from utils.config_manager import load_config # Import the new config loader
from ban_history import ban_tracker

load_dotenv()

# --- Global Bot Application State ---
bot_user_form_state: Dict[int, Dict[str, Any]] = {}

# --- Bot Setup ---
intents = discord.Intents.all()
bot = commands.Bot(command_prefix="--!", intents=intents, help_command=None)

# --- Attach shared resources and configurations to the bot instance ---
bot.user_form_state = bot_user_form_state
bot.config = load_config() # Load config from config.json
bot.is_moderator_check_func = lambda interaction: is_moderator(interaction, bot.config.get("moderator_roles", []))
bot.player_db = PlayerDatabaseConnection()

# List of cogs to load
cogs_to_load = [
    "cogs.admin_cog",
    "cogs.ban_cog",
    "cogs.history_cog",
    "cogs.setup_cog",
    "cogs.help_cog",
]

async def load_all_extensions():
    print("--- Loading Cogs ---")
    for cog_path in cogs_to_load:
        try:
            await bot.load_extension(cog_path)
            print(f"✅ Successfully loaded cog: {cog_path}")
        except commands.ExtensionAlreadyLoaded:
            print(f"ℹ️ Cog already loaded: {cog_path}")
        except Exception as e:
            print(f"❌ Failed to load cog {cog_path}: {type(e).__name__} - {e}")
            traceback.print_exc()

@bot.event
async def on_ready():
    print(f"🚀 Bot {bot.user} (ID: {bot.user.id}) is ready and online!")
    print(f"Connected to {len(bot.guilds)} guild(s).")
    
    # Initialize database connections
    await bot.player_db.initialize()
    await ban_tracker.initialize()

    if not hasattr(bot, 'extensions_loaded_once'):
        await load_all_extensions()
        bot.extensions_loaded_once = True

    try:
        if not hasattr(bot, 'synced_commands_once'):
            print("Syncing slash commands...")
            synced = await bot.tree.sync()
            print(f"✅ Synced {len(synced)} slash commands globally.")
            bot.synced_commands_once = True
        else:
            print("ℹ️ Slash commands appear to be previously synced.")
    except Exception as e:
        print(f"❌ Failed to sync slash commands: {e}")

# Global error handler for application commands
@bot.tree.error
async def on_app_command_error(
    interaction: discord.Interaction, error: discord.app_commands.AppCommandError
):
    if isinstance(error, discord.app_commands.CommandOnCooldown):
        msg = f"This command is on cooldown. Try again in {error.retry_after:.2f}s."
        color = discord.Color.yellow()
    elif isinstance(error, (discord.app_commands.MissingPermissions, discord.app_commands.MissingRole, discord.app_commands.NoPrivateMessage)):
        msg = f"Action Restricted: {error}"
        color = discord.Color.red()
    elif isinstance(error, discord.app_commands.CheckFailure):
        msg = "A permission check failed for this command."
        color = discord.Color.red()
    else:
        msg = "An unexpected error occurred while running this command."
        color = discord.Color.dark_red()
        print(f"Unhandled App Command error for '{interaction.command.name if interaction.command else 'UnknownCmd'}' by {interaction.user}: {type(error).__name__} - {error}")
        traceback.print_exc()

    embed = discord.Embed(title="Command Error", description=msg, color=color)
    try:
        if interaction.response.is_done():
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message(embed=embed, ephemeral=True)
    except discord.HTTPException as http_exc:
        print(f"Failed to send error message for command error: {http_exc}")

async def main_async_runner():
    TOKEN = os.getenv("DISCORD_TOKEN")
    if not TOKEN:
        print("❌ DISCORD_TOKEN environment variable not found. Please set it in your .env file.")
        return

    async with bot:
        try:
            await bot.start(TOKEN)
        except discord.LoginFailure:
            print("❌ Discord Login Failed: Improper token provided.")
        except discord.PrivilegedIntentsRequired:
            print("❌ Privileged Intents Required: Please enable necessary intents in the Discord Developer Portal.")
        except Exception as e:
            print(f"❌ An error occurred while running the bot: {e}")
        finally:
            print("Bot shutdown sequence initiated...")
            if hasattr(bot.player_db, 'pool') and bot.player_db.pool:
                await bot.player_db.close()
            if hasattr(ban_tracker, 'pool') and ban_tracker.pool:
                await ban_tracker.close()
            print("Bot shutdown complete.")

if __name__ == "__main__":
    try:
        asyncio.run(main_async_runner())
    except KeyboardInterrupt:
        print("\n⌨️ Bot shutdown requested via KeyboardInterrupt.")