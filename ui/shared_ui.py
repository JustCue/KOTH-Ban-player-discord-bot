# ui/shared_ui.py
import discord
from typing import List, Dict, Callable, Awaitable, Optional, Any 

async def search_channels_for_players_fallback(guild: discord.Guild, search_term: str) -> List[Dict]:
    """Fallback method to search channels for player data if DB fails or has no results."""
    players = []
    search_term_lower = search_term.lower()
    for channel in guild.text_channels:
        if not channel.permissions_for(guild.me).read_message_history:
            continue
        try:
            async for message in channel.history(limit=100):
                if "Name = " in message.content and "BohemiaUID = " in message.content:
                    lines = message.content.replace(",", "\n").splitlines()
                    for line_content in lines:
                        parts = line_content.strip().split(" | ")
                        player_data = {}
                        for part in parts:
                            if " = " in part:
                                k, v = part.split(" = ", 1)
                                player_data[k.strip()] = v.strip()
                        
                        if (all(k in player_data for k in ("Name", "Level", "Last Played", "BohemiaUID")) and
                                search_term_lower in player_data["Name"].lower()):
                            if not any(p["BohemiaUID"] == player_data["BohemiaUID"] for p in players):
                                players.append(player_data)
                            if len(players) >= 15: break
            if len(players) >= 15: break
        except (discord.Forbidden, discord.HTTPException) as e:
            print(f"Warning: Could not search channel {channel.name} due to {e}")
            continue
    return players


class PlayerSearchModal(discord.ui.Modal, title="Search for Player"):
    search_term_input = discord.ui.TextInput(
        label="Player Name",
        style=discord.TextStyle.short,
        placeholder="Enter player name or partial name...",
        required=True, min_length=2, max_length=50
    )

    def __init__(self,
                 player_db_instance: Any,
                 on_search_complete: Callable[[discord.Interaction, List[Dict], str], Awaitable[None]],
                 channel_search_func: Optional[Callable[[discord.Guild, str], Awaitable[List[Dict]]]] = search_channels_for_players_fallback):
        super().__init__(timeout=300)
        self.player_db = player_db_instance
        self.on_search_complete = on_search_complete
        self.channel_search_func = channel_search_func

    async def on_submit(self, interaction: discord.Interaction):
        search_val = self.search_term_input.value
        players = await self.player_db.find_players(search_val)

        if not players and self.channel_search_func and interaction.guild:
            print(f"PlayerSearchModal: No DB results for '{search_val}', trying channel fallback.")
            players = await self.channel_search_func(interaction.guild, search_val)
        
        await self.on_search_complete(interaction, players, search_val)


class PlayerSearchView(discord.ui.View):
    def __init__(self,
                 players: List[Dict],
                 search_term: str,
                 interaction_to_followup: discord.Interaction,
                 player_db_instance: Any,
                 on_search_again_callback: Callable[[discord.Interaction], Awaitable[None]],
                 channel_search_func: Optional[Callable[[discord.Guild, str], Awaitable[List[Dict]]]] = search_channels_for_players_fallback):
        super().__init__(timeout=300)
        self.players = players
        self.search_term = search_term
        self.interaction_to_followup = interaction_to_followup
        self.player_db = player_db_instance
        self.on_search_again_callback = on_search_again_callback
        self.channel_search_func = channel_search_func
        self.message: Optional[discord.Message] = None

        self.add_item(self.DetailedResultsButton(parent_view=self))
        self.add_item(self.SearchAgainPlayerSearchViewButton(parent_view=self))

    async def on_timeout(self):
        if self.message:
            try:
                await self.message.edit(content=f"Player search view for '{self.search_term}' timed out.", view=None)
            except discord.HTTPException: pass

    class DetailedResultsButton(discord.ui.Button):
        def __init__(self, parent_view: 'PlayerSearchView'):
            super().__init__(label="📋 Show Detailed Results", style=discord.ButtonStyle.primary)
            self.parent_view = parent_view
        
        async def callback(self, interaction: discord.Interaction):
            await interaction.response.defer(ephemeral=True)
            result_lines = []
            for player in self.parent_view.players:
                line = (f"Name = {player['Name']} | Level = {player['Level']} | "
                        f"Last Played = {player['Last Played']} | BohemiaUID = {player['BohemiaUID']}")
                result_lines.append(line)
            
            embed = discord.Embed(
                title=f"Detailed Search Results for '{self.parent_view.search_term}'",
                color=discord.Color.blue()
            )
            description_header = f"Found {len(self.parent_view.players)} player(s)."
            full_description = description_header + "\n\n```\n" + "\n".join(result_lines) + "\n```"

            if len(full_description) <= 4096:
                embed.description = full_description
            else:
                embed.description = description_header
                for i in range(0, len(result_lines), 5):
                    chunk = result_lines[i:i+5]
                    embed.add_field(name=f"Results Part {i//5 + 1}", value="```\n" + "\n".join(chunk) + "\n```", inline=False)
            
            await interaction.followup.send(embed=embed, ephemeral=True)

    class SearchAgainPlayerSearchViewButton(discord.ui.Button):
        def __init__(self, parent_view: 'PlayerSearchView'):
            super().__init__(label="🔍 Search Again", style=discord.ButtonStyle.secondary)
            self.parent_view = parent_view

        async def callback(self, interaction: discord.Interaction):
            await self.parent_view.on_search_again_callback(interaction)