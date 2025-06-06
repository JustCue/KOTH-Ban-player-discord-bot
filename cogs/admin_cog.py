# cogs/admin_cog.py
import discord
from discord.ext import commands
from discord import app_commands
from typing import List, Dict, Optional

from ban_history import ban_tracker
# --- FIX: PlayerSearchModal is removed from this top-level import to prevent circular dependency ---
from ui.shared_ui import PlayerSearchView, search_channels_for_players_fallback
# PlayerDatabaseConnection is accessed via self.bot.player_db
# is_moderator from utils.permissions_utils accessed via self.bot.is_moderator_check_func (defined in main.py)

class AdminCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _handle_find_player_search_results(self, interaction: discord.Interaction, players: List[Dict], search_term: str):
        """Callback for PlayerSearchModal when used by /find_player."""
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True)

        if not players:
            embed = discord.Embed(title="No Players Found", description=f"No players found matching '{search_term}'.", color=discord.Color.red())
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        embed = discord.Embed(
            title=f"Player Search Results for '{search_term}'",
            description=f"Found {len(players)} player(s).",
            color=discord.Color.blue()
        )
        view = PlayerSearchView(
            players=players,
            search_term=search_term,
            interaction_to_followup=interaction,
            player_db_instance=self.bot.player_db,
            on_search_again_callback=self._trigger_find_player_search_again,
            channel_search_func=search_channels_for_players_fallback
        )
        message = await interaction.followup.send(embed=embed, view=view, ephemeral=True)
        view.message = message

    async def _trigger_find_player_search_again(self, interaction: discord.Interaction):
        """Called by PlayerSearchView's 'Search Again' button."""
        # --- FIX: Import is moved here to happen at runtime, breaking the import cycle. ---
        from ui.shared_ui import PlayerSearchModal
        
        modal = PlayerSearchModal(
            player_db_instance=self.bot.player_db,
            on_search_complete=self._handle_find_player_search_results,
            channel_search_func=search_channels_for_players_fallback
        )
        await interaction.response.send_modal(modal)


    @app_commands.command(name="find_player", description="Search for a player in the database or channels.")
    async def find_player_command(self, interaction: discord.Interaction):
        # --- FIX: Import is moved here to happen at runtime, breaking the import cycle. ---
        from ui.shared_ui import PlayerSearchModal

        modal = PlayerSearchModal(
            player_db_instance=self.bot.player_db,
            on_search_complete=self._handle_find_player_search_results,
            channel_search_func=search_channels_for_players_fallback
        )
        await interaction.response.send_modal(modal)

    @app_commands.command(name="delete_ban", description="ADMIN: Deletes a ban record by its Ban Number.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def delete_ban_command(self, interaction: discord.Interaction, ban_number: str):
        if not self.bot.is_moderator_check_func(interaction):
            await interaction.response.send_message(
                "❌ You do not have the necessary role to use this command.",
                ephemeral=True
            )
            return
            
        success = await ban_tracker.delete_ban(ban_number)
        if success:
            await interaction.response.send_message(f"🗑️ Ban record `{ban_number}` has been deleted.", ephemeral=True)
        else:
            await interaction.response.send_message(f"⚠️ Could not delete ban record `{ban_number}`. It might not exist or an error occurred.", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(AdminCog(bot))