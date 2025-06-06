# cogs/history_cog.py
import discord
from discord.ext import commands
from discord import app_commands
import traceback
import math
from datetime import datetime
from typing import List, Dict, Optional

from ban_history import ban_tracker

# --- New Pagination View for Ban History ---
class HistoryPaginationView(discord.ui.View):
    def __init__(self, history_entries: List[Dict], buid: str, player_name: str, items_per_page: int = 4):
        super().__init__(timeout=300) # View times out after 5 minutes of inactivity
        self.history_entries = history_entries
        self.buid = buid
        self.player_name = player_name
        self.items_per_page = items_per_page
        
        self.current_page = 0
        self.total_pages = math.ceil(len(self.history_entries) / self.items_per_page)
        
        self.message: Optional[discord.Message] = None

    async def create_page_embed(self) -> discord.Embed:
        """Creates an embed for the current page."""
        start_index = self.current_page * self.items_per_page
        end_index = start_index + self.items_per_page
        
        page_entries = self.history_entries[start_index:end_index]

        embed = discord.Embed(
            title=f"Ban History for {self.player_name}",
            description=f"BUID: `{self.buid}`",
            color=discord.Color.blue()
        )
        
        if not page_entries:
            embed.description += "\n\nNo records on this page."
        
        for ban in page_entries:
            unban_marker = "🔓 " if ban.get("is_unban", False) else "⚖️ "
            strike_marker = " (Strike Removed)" if ban.get("strike_removed", False) else ""
            
            ban_num = ban.get('ban_number', 'N/A')
            timestamp = ban.get('timestamp', 'N/A')[:10]
            offense = ban.get('offense', 'N/A')
            strike = ban.get('strike', 'N/A')
            sanction = ban.get('sanction', 'N/A')
            
            field_name = f"{unban_marker} {ban_num} on {timestamp}{strike_marker}"
            field_value = f"**Offense:** {offense}\n**Punishment:** ({strike}) {sanction}"
            
            embed.add_field(name=field_name, value=field_value, inline=False)
            
        embed.set_footer(text=f"Page {self.current_page + 1} of {self.total_pages}")
        return embed

    async def update_view(self, interaction: discord.Interaction):
        """Updates the buttons and edits the message with the new page."""
        # Update button states
        self.previous_page.disabled = self.current_page == 0
        self.next_page.disabled = self.current_page >= self.total_pages - 1

        embed = await self.create_page_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    async def on_timeout(self):
        # Disable all buttons when the view times out
        if self.message:
            for item in self.children:
                if isinstance(item, discord.ui.Button):
                    item.disabled = True
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass # Message might have been deleted

    @discord.ui.button(label="⬅️ Previous", style=discord.ButtonStyle.secondary, custom_id="history_prev")
    async def previous_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page > 0:
            self.current_page -= 1
            await self.update_view(interaction)
        else:
            await interaction.response.defer()

    @discord.ui.button(label="Next ➡️", style=discord.ButtonStyle.secondary, custom_id="history_next")
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page < self.total_pages - 1:
            self.current_page += 1
            await self.update_view(interaction)
        else:
            await interaction.response.defer()


class HistoryCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="banhistory", description="View ban history for a player")
    @app_commands.describe(buid="The Bohemia UID of the player to check.")
    async def banhistory_command(self, interaction: discord.Interaction, buid: str):
        await interaction.response.defer(ephemeral=True)
        
        try:
            history = await ban_tracker.get_player_history(buid)

            if not history:
                embed = discord.Embed(
                    title="No History Found",
                    description=f"No ban history found for BUID: `{buid}`",
                    color=discord.Color.yellow(),
                )
                await interaction.followup.send(embed=embed)
                return

            player_name = history[0].get('player_name', 'Unknown Player')
            
            # Create and send the initial paginated view
            view = HistoryPaginationView(history, buid, player_name)
            
            # Disable buttons if not needed (e.g., only one page)
            view.previous_page.disabled = True
            view.next_page.disabled = view.total_pages <= 1
            
            initial_embed = await view.create_page_embed()
            
            # Add final summary fields to the initial embed, they won't change between pages
            strike_count = await ban_tracker.get_player_strikes(buid)
            initial_embed.add_field(name="Active Strikes", value=str(strike_count), inline=True)
            initial_embed.add_field(name="Total Records", value=str(len(history)), inline=True)
            
            message = await interaction.followup.send(embed=initial_embed, view=view, ephemeral=True)
            view.message = message

        except Exception as e:
            print(f"--- ERROR in /banhistory command ---")
            traceback.print_exc()
            await interaction.followup.send(f"An error occurred while fetching the ban history: `{e}`", ephemeral=True)


    @app_commands.command(name="recentbans", description="View recent ban submissions")
    @app_commands.describe(limit="Number of recent bans to show (max 25).")
    async def recentbans_command(self, interaction: discord.Interaction, limit: int = 10):
        await interaction.response.defer(ephemeral=True)
        try:
            if not 1 <= limit <= 25:
                limit = 10

            recent = await ban_tracker.get_recent_bans(limit)

            if not recent:
                embed = discord.Embed(
                    title="No Recent Bans",
                    description="No recent ban submissions found in the database.",
                    color=discord.Color.yellow(),
                )
                await interaction.followup.send(embed=embed)
                return

            embed = discord.Embed(
                title=f"Recent Ban Submissions (Last {len(recent)})",
                color=discord.Color.purple(),
            )
            
            # Restored more detailed formatting for recent bans
            description_text = ""
            for ban in recent:
                unban_marker = "🔓 " if ban.get("is_unban", False) else ""
                player_name = ban.get('player_name', 'N/A')
                ban_num = ban.get('ban_number', 'N/A')
                offense = ban.get('offense', 'N/A')
                timestamp = ban.get('timestamp', 'N/A')[:10]
                
                entry = f"**{unban_marker}{ban_num}** | {timestamp} | **{player_name}**\nOffense: *{offense[:70]}...*\n"
                
                if len(description_text) + len(entry) > 4000: # Stay within embed description limits
                    description_text += "\n... (list truncated)"
                    break
                
                description_text += entry + "\n"
            
            embed.description = description_text
            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            print(f"--- ERROR in /recentbans command ---")
            traceback.print_exc()
            await interaction.followup.send(f"An error occurred while fetching recent bans: `{e}`", ephemeral=True)


    @app_commands.command(name="searchban", description="Search for a specific ban by ban number")
    @app_commands.describe(ban_number="The unique ban number (e.g., 0042 or UNBAN-0001).")
    async def searchban_command(self, interaction: discord.Interaction, ban_number: str):
        await interaction.response.defer(ephemeral=True)
        try:
            ban = await ban_tracker.get_ban_by_number(ban_number)

            if not ban:
                embed = discord.Embed(
                    title="Ban Not Found",
                    description=f"No ban found with number: `{ban_number}`",
                    color=discord.Color.red(),
                )
                await interaction.followup.send(embed=embed)
                return

            embed_color = discord.Color.orange() if ban.get("is_unban") else discord.Color.dark_red()
            embed = discord.Embed(
                title=f"Details for Ban/Unban: {ban.get('ban_number', 'N/A')}",
                color=embed_color,
                timestamp=datetime.fromisoformat(ban["timestamp"]) if ban.get("timestamp") else datetime.utcnow()
            )

            embed.add_field(name="Player", value=ban.get("player_name", "N/A"), inline=True)
            embed.add_field(name="BUID", value=f"`{ban.get('buid', 'N/A')}`", inline=True)
            
            submitted_by_text = f"ID: {ban.get('submitted_by', 'N/A')}"
            if ban.get("submitted_by", "").isdigit():
                try:
                    submitter = await self.bot.fetch_user(int(ban["submitted_by"]))
                    submitted_by_text = submitter.mention
                except (discord.NotFound, ValueError):
                    pass
            embed.add_field(name="Submitted By", value=submitted_by_text, inline=True)

            embed.add_field(name="Offense/Reason", value=ban.get("offense", "N/A"), inline=False)
            embed.add_field(name="Strike Level", value=ban.get("strike", "N/A"), inline=True)
            embed.add_field(name="Sanction/Action", value=ban.get("sanction", "N/A"), inline=True)
            
            transcript = ban.get("transcript")
            if transcript and transcript.lower() not in ["n/a", "none", "will add later / no transcript", "witness statement (no html)"]:
                 embed.add_field(name="Transcript", value=transcript, inline=False)
            else:
                 embed.add_field(name="Transcript", value="Not Provided", inline=True)

            if ban.get("is_unban"):
                embed.set_author(name="UNBAN Record")
            else:
                embed.set_author(name="BAN Record")

            if ban.get("strike_removed"):
                 embed.add_field(name="⚠️ Status", value="Strike Associated With This Ban Was Removed", inline=True)

            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            print(f"--- ERROR in /searchban command ---")
            traceback.print_exc()
            await interaction.followup.send(f"An error occurred while searching for the ban: `{e}`", ephemeral=True)

# This function must exist at the bottom of every cog file.
async def setup(bot: commands.Bot):
    await bot.add_cog(HistoryCog(bot))