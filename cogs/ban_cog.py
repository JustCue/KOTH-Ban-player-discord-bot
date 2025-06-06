# cogs/ban_cog.py
import discord
from discord.ext import commands
from discord import app_commands
import re
import traceback
from typing import List, Dict, Optional, Any
from datetime import datetime
import math

from punishments import punishments
from ban_history import ban_tracker
from ui.shared_ui import search_channels_for_players_fallback

async def get_transcript_options(guild: discord.Guild, channel_name_contains: str) -> List[str]:
    transcript_channel = next((c for c in guild.text_channels if channel_name_contains.lower() in c.name.lower()), None)
    if not transcript_channel or not transcript_channel.permissions_for(guild.me).read_message_history:
        return []
    transcripts = []
    try:
        async for message in transcript_channel.history(limit=30):
            if message.attachments:
                for att in message.attachments:
                    if att.filename.endswith(".html"):
                        transcripts.append(generate_transcript_link(message, transcript_channel.name))
                        if len(transcripts) >= 20: break
                if len(transcripts) >= 20: break
    except discord.Forbidden:
        print(f"No permission to read history in {transcript_channel.name}")
    except Exception as e:
        print(f"Error fetching transcripts from {transcript_channel.name}: {e}")
    return transcripts

def generate_transcript_link(message: discord.Message, channel_name: str) -> str:
    for attachment in message.attachments:
        if attachment.filename.endswith(".html"):
            match = re.search(r"(\d+)", attachment.filename)
            label = f"File: {attachment.filename[:80]}"
            if match:
                number = int(match.group(1))
                label_prefix = "Ticket" if "ticket" in channel_name.lower() else "Report"
                label = f"{label_prefix}-{number:04d}"
            return f"[{label}](<{message.jump_url}>)"
    return f"[Attachment Link](<{message.jump_url}>)"


class BanCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _update_interaction_message(self, interaction: discord.Interaction, **kwargs):
        """Helper function to reliably edit the original interaction message."""
        if not interaction.response.is_done():
            await interaction.response.edit_message(**kwargs)
        else:
            await interaction.edit_original_response(**kwargs)

        if "view" in kwargs and (view := kwargs.get("view")) and hasattr(view, 'message'):
            try:
                view.message = await interaction.original_response()
            except discord.NotFound:
                view.message = None

    class PlayerView(discord.ui.View):
        def __init__(self, players: List[Dict], search_term: str, cog_ref: 'BanCog'):
            super().__init__(timeout=300)
            self.players = players
            self.search_term = search_term
            self.cog_ref = cog_ref
            self.message: Optional[discord.Message] = None
            self.current_page = 0
            self.items_per_page = 5
            self.total_pages = math.ceil(len(self.players) / self.items_per_page)
            self.create_components()
            self.update_components()

        def create_components(self):
            self.prev_button = discord.ui.Button(label="⬅️ Previous", style=discord.ButtonStyle.secondary, row=1)
            self.prev_button.callback = self.prev_page
            self.add_item(self.prev_button)
            self.next_button = discord.ui.Button(label="Next ➡️", style=discord.ButtonStyle.secondary, row=1)
            self.next_button.callback = self.next_page
            self.add_item(self.next_button)
            search_again_button = discord.ui.Button(label="🔍 Search Again", style=discord.ButtonStyle.danger, row=1)
            search_again_button.callback = self.search_again
            self.add_item(search_again_button)
            self.player_select_menu: Optional[BanCog.PlayerSelect] = None

        def update_components(self):
            self.prev_button.disabled = self.current_page == 0
            self.next_button.disabled = self.current_page >= self.total_pages - 1
            if self.player_select_menu:
                self.remove_item(self.player_select_menu)
            start_index = self.current_page * self.items_per_page
            end_index = start_index + self.items_per_page
            page_players = self.players[start_index:end_index]
            self.player_select_menu = self.cog_ref.PlayerSelect(page_players, self.players, self.cog_ref)
            self.add_item(self.player_select_menu)
            
        def create_embed(self) -> discord.Embed:
            embed = discord.Embed(
                title=f"Ban Process - Step 1: Select Player",
                description=f"Found {len(self.players)} player(s) matching '{self.search_term}'. Please select a player.",
                color=discord.Color.blue()
            )
            start_index = self.current_page * self.items_per_page
            end_index = start_index + self.items_per_page
            page_players = self.players[start_index:end_index]
            player_list_text = ""
            if not page_players:
                player_list_text = "No players on this page."
            else:
                for p in page_players:
                    player_list_text += f"**{p.get('Name', 'Unknown')}** (Lvl: {p.get('Level', 'N/A')}, Last Played: {p.get('Last Played', 'N/A')})\n"
            embed.add_field(name="Players on this Page", value=player_list_text, inline=False)
            embed.set_footer(text=f"Page {self.current_page + 1} of {self.total_pages}")
            return embed

        async def search_again(self, interaction: discord.Interaction):
            from ui.shared_ui import PlayerSearchModal
            modal = PlayerSearchModal(
                player_db_instance=self.cog_ref.bot.player_db,
                on_search_complete=self.cog_ref._handle_ban_player_search_results,
                channel_search_func=search_channels_for_players_fallback
            )
            await interaction.response.send_modal(modal)

        async def prev_page(self, interaction: discord.Interaction):
            self.current_page -= 1
            self.update_components()
            embed = self.create_embed()
            await interaction.response.edit_message(embed=embed, view=self)

        async def next_page(self, interaction: discord.Interaction):
            self.current_page += 1
            self.update_components()
            embed = self.create_embed()
            await interaction.response.edit_message(embed=embed, view=self)

        async def on_timeout(self):
            if self.message:
                try: 
                    await self.message.edit(content="Player selection for ban timed out.", embed=None, view=None)
                except discord.HTTPException: pass

    class PlayerSelect(discord.ui.Select):
        def __init__(self, page_players: List[Dict], all_players: List[Dict], cog_ref: 'BanCog'):
            self.page_players = page_players
            self.all_players = all_players
            self.cog_ref = cog_ref
            options = []
            for p_data in page_players:
                label = p_data.get("Name", "Unknown Player")[:100]
                description = f"Lvl {p_data.get('Level','N/A')}, Last: {p_data.get('Last Played','N/A')}"[:100]
                options.append(discord.SelectOption(label=label, description=description, value=p_data.get("BohemiaUID", p_data.get("Name"))))
            if not options:
                options.append(discord.SelectOption(label="No players on this page", value="disabled"))
            super().__init__(placeholder="Choose a player to proceed...", options=options, min_values=1, max_values=1, row=0)
            if not self.page_players: self.disabled = True

        async def callback(self, interaction: discord.Interaction):
            selected_value = self.values[0]
            if selected_value == "disabled":
                await interaction.response.defer()
                return

            player = next((p for p in self.all_players if p.get("BohemiaUID", p.get("Name")) == selected_value), None)
            if not player:
                await interaction.response.edit_message(content="Error: Selected player data not found. Please try again.", view=None, embed=None)
                return
            
            self.cog_ref.bot.user_form_state[interaction.user.id]["player"] = player
            
            embed = discord.Embed(title="Player Selected", description="Please choose the offense.", color=discord.Color.green())
            embed.add_field(name="Name", value=player.get("Name", "N/A"), inline=True)
            embed.add_field(name="Level", value=str(player.get("Level", "N/A")), inline=True)
            embed.add_field(name="Last Played", value=player.get("Last Played", "N/A"), inline=True)
            embed.add_field(name="Bohemia UID", value=player.get("BohemiaUID", "N/A"), inline=False)
            
            view = self.cog_ref.OffenseView(player, self.cog_ref)
            await self.cog_ref._update_interaction_message(interaction, content="", embed=embed, view=view)

    class OffenseView(discord.ui.View):
        def __init__(self, player: Dict, cog_ref: 'BanCog'):
            super().__init__(timeout=300)
            self.player = player
            self.cog_ref = cog_ref
            self.message: Optional[discord.Message] = None
            self.add_item(self.cog_ref.OffenseSelect(self))
            self.add_item(self.cog_ref.BackButton("player", cog_ref=self.cog_ref, row=1))
        
        async def on_timeout(self):
            if self.message:
                try: await self.message.edit(content="Offense selection timed out.", view=None, embed=None)
                except discord.HTTPException: pass

    class OffenseSelect(discord.ui.Select):
        def __init__(self, parent_view: 'OffenseView'):
            self.parent_view = parent_view
            self.player = parent_view.player
            self.cog_ref = parent_view.cog_ref
            
            all_offenses_keys = list(punishments.keys())
            all_offenses_keys.extend(["UNBAN (Strike Remains)", "UNBAN (Remove Strike)"])
            all_offenses_keys = sorted(list(set(all_offenses_keys)))

            options = [discord.SelectOption(label=offense_key[:100]) for offense_key in all_offenses_keys if offense_key != "Custom Punishment"]
            options.append(discord.SelectOption(label="Custom Punishment", value="Custom Punishment")) # Ensure it's always an option

            super().__init__(placeholder="Select offense...", options=options, min_values=1, max_values=1)

        async def callback(self, interaction: discord.Interaction):
            selected_offense = self.values[0]
            self.cog_ref.bot.user_form_state[interaction.user.id]["offense"] = selected_offense
            
            if selected_offense == "Custom Punishment":
                modal = self.cog_ref.CustomPunishmentModal(self.player, self.cog_ref)
                await interaction.response.send_modal(modal)
                return

            embed = interaction.message.embeds[0]
            
            if selected_offense in ["UNBAN (Strike Remains)", "UNBAN (Remove Strike)"]:
                embed.title="Select Ban to Reverse"
                embed.description="Choose the original ban you wish to unban."
                next_view = self.cog_ref.UnbanReportView(self.player.get("BohemiaUID",""), selected_offense, self.cog_ref)
            else:
                embed.title="Select Strike Level"
                embed.description="Choose the appropriate strike for this offense."
                next_view = self.cog_ref.StrikeView(self.player, selected_offense, self.cog_ref)
            
            await self.cog_ref._update_interaction_message(interaction, embed=embed, view=next_view)

    class CustomPunishmentModal(discord.ui.Modal, title="Custom Punishment"):
        reason_input = discord.ui.TextInput(label="Reason for Custom Punishment", style=discord.TextStyle.long, required=True)
        length_input = discord.ui.TextInput(label="Ban Length", placeholder="e.g., 3 days, 1 week, Permanent", required=True)

        def __init__(self, player: Dict, cog_ref: 'BanCog'):
            super().__init__(timeout=300)
            self.player = player
            self.cog_ref = cog_ref

        async def on_submit(self, interaction: discord.Interaction):
            user_id = interaction.user.id
            if user_id not in self.cog_ref.bot.user_form_state:
                self.cog_ref.bot.user_form_state[user_id] = {}
            self.cog_ref.bot.user_form_state[user_id]["offense_detail"] = self.reason_input.value
            self.cog_ref.bot.user_form_state[user_id]["strike"] = "Custom"
            self.cog_ref.bot.user_form_state[user_id]["sanction"] = self.length_input.value
            
            view = self.cog_ref.TranscriptTypeView(
                player=self.player, 
                offense=self.reason_input.value, 
                strike="Custom", 
                sanction=self.length_input.value, 
                unban_data=None, 
                cog_ref=self.cog_ref
            )
            embed = discord.Embed(title="Select Transcript Type", description="Link a report or ticket transcript to this ban.")
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    class StrikeView(discord.ui.View):
        def __init__(self, player: Dict, offense: str, cog_ref: 'BanCog'):
            super().__init__(timeout=300)
            self.player = player
            self.offense = offense
            self.cog_ref = cog_ref
            self.message: Optional[discord.Message] = None
            
            strikes_data = punishments.get(offense, {})
            
            if strikes_data:
                self.add_item(self.cog_ref.StrikeSelect(self))
            else:
                no_strikes_button = discord.ui.Button(
                    label="❌ No strikes defined for this offense",
                    style=discord.ButtonStyle.secondary,
                    disabled=True
                )
                self.add_item(no_strikes_button)
            
            self.add_item(self.cog_ref.BackButton("offense", cog_ref=self.cog_ref, row=1))
        
        async def on_timeout(self):
            if self.message:
                try: await self.message.edit(content="Strike selection timed out.", view=None, embed=None)
                except discord.HTTPException: pass

    class StrikeSelect(discord.ui.Select):
        def __init__(self, parent_view: 'StrikeView'):
            self.parent_view = parent_view
            self.player = parent_view.player
            self.offense = parent_view.offense
            self.cog_ref = parent_view.cog_ref
            self.strikes_data = punishments.get(self.offense, {})
            
            options = [discord.SelectOption(label=s_level) for s_level in self.strikes_data.keys()]
            super().__init__(placeholder="Select strike level...", options=options)

        async def callback(self, interaction: discord.Interaction):
            strike_level = self.values[0]
            sanction_options = self.strikes_data[strike_level]
            self.cog_ref.bot.user_form_state[interaction.user.id]["strike"] = strike_level

            embed = interaction.message.embeds[0]
            next_view: Optional[discord.ui.View]

            if isinstance(sanction_options, list):
                embed.title = "Select Ban Duration"
                embed.description = "This offense has multiple possible sanction lengths."
                next_view = self.cog_ref.SanctionChooserView(self.player, self.offense, strike_level, sanction_options, self.cog_ref)
            else:
                self.cog_ref.bot.user_form_state[interaction.user.id]["sanction"] = sanction_options
                embed.title = "Select Transcript Type"
                embed.description = "Link a report or ticket transcript to this ban."
                next_view = self.cog_ref.TranscriptTypeView(self.player, self.offense, strike_level, sanction_options, None, self.cog_ref)
            
            await self.cog_ref._update_interaction_message(interaction, embed=embed, view=next_view)

    class SanctionChooserView(discord.ui.View):
        def __init__(self, player: Dict, offense: str, strike_level: str, sanction_list: List[str], cog_ref: 'BanCog'):
            super().__init__(timeout=180)
            self.player, self.offense, self.strike_level, self.cog_ref, self.sanction_list = \
                player, offense, strike_level, cog_ref, sanction_list
            self.message: Optional[discord.Message] = None
            self.add_item(self.cog_ref.SanctionActualSelect(self))
            self.add_item(self.cog_ref.BackButton("strike", cog_ref=self.cog_ref, row=1))

        async def on_timeout(self):
            if self.message:
                try: await self.message.edit(content="Sanction choice timed out.", view=None, embed=None)
                except discord.HTTPException: pass
                
    class SanctionActualSelect(discord.ui.Select):
        def __init__(self, parent_view: 'SanctionChooserView'):
            self.parent_view = parent_view
            self.player = parent_view.player
            self.offense = parent_view.offense
            self.strike_level = parent_view.strike_level
            self.cog_ref = parent_view.cog_ref
            
            options = [discord.SelectOption(label=sanc) for sanc in parent_view.sanction_list]
            super().__init__(placeholder="Select ban duration...", options=options)

        async def callback(self, interaction: discord.Interaction):
            chosen_sanction = self.values[0]
            self.cog_ref.bot.user_form_state[interaction.user.id]["sanction"] = chosen_sanction
            
            embed = interaction.message.embeds[0]
            embed.title = "Select Transcript Type"
            embed.description = "Link a report or ticket transcript to this ban."
            view = self.cog_ref.TranscriptTypeView(self.player, self.offense, self.strike_level, chosen_sanction, None, self.cog_ref)
            await self.cog_ref._update_interaction_message(interaction, embed=embed, view=view)

    class UnbanReportView(discord.ui.View):
        def __init__(self, player_buid: str, unban_type: str, cog_ref: 'BanCog'):
            super().__init__(timeout=300)
            self.player_buid, self.unban_type, self.cog_ref = player_buid, unban_type, cog_ref
            self.message: Optional[discord.Message] = None
            self.add_item(self.cog_ref.UnbanReportSelect(self))
            self.add_item(self.cog_ref.BackButton("offense", cog_ref=self.cog_ref, row=1))
        
        async def on_timeout(self):
            if self.message:
                try: await self.message.edit(content="Unban report selection timed out.", view=None, embed=None)
                except discord.HTTPException: pass

    class UnbanReportSelect(discord.ui.Select):
        def __init__(self, parent_view: 'UnbanReportView'):
            self.parent_view = parent_view
            self.player_buid = parent_view.player_buid
            self.unban_type = parent_view.unban_type
            self.cog_ref = parent_view.cog_ref
            self.remove_strike = self.unban_type == "UNBAN (Remove Strike)"
            
            super().__init__(placeholder="Loading ban history...", options=[discord.SelectOption(label="Loading...", value="loading")])
            discord.utils.create_task(self._load_options_and_update_view())

        async def _load_options_and_update_view(self):
            history = await ban_tracker.get_player_history(self.player_buid)
            options = []
            if history:
                for ban_record in sorted(history, key=lambda x: x['timestamp'], reverse=True):
                    if not ban_record.get("is_unban", False):
                        strike_removed = " (Strike Removed)" if ban_record.get("strike_removed") else ""
                        label = f"{ban_record['ban_number']} - {ban_record['offense'][:40]}{strike_removed}"
                        desc = f"{ban_record['timestamp'][:10]} ({ban_record['strike']})"
                        options.append(discord.SelectOption(label=label, description=desc, value=ban_record["ban_number"]))
                    if len(options) >= 24: break
            
            if not options:
                self.options = [discord.SelectOption(label="No active bans found", value="none_found")]
                self.placeholder = "No active bans found."
            else:
                self.options = options
                self.placeholder = "Select which ban to reverse..."
            
            if self.parent_view.message:
                try: await self.parent_view.message.edit(view=self.parent_view)
                except discord.HTTPException: pass

        async def callback(self, interaction: discord.Interaction):
            selected_ban_number = self.values[0]
            if selected_ban_number in ["loading", "none_found"]:
                await interaction.response.defer()
                return

            user_id = interaction.user.id
            state = self.cog_ref.bot.user_form_state.get(user_id)
            if not state or "player" not in state:
                await self.cog_ref._update_interaction_message(interaction, content="Error: Player context lost.", view=None, embed=None); return

            original_ban_details = await ban_tracker.get_ban_by_number(selected_ban_number)
            state["unban_data"] = {
                "ban_number_to_unban": selected_ban_number, 
                "remove_strike": self.remove_strike,
                "related_ban_id": original_ban_details.get('id') if original_ban_details else None
            }
            state["strike"] = "UNBAN"
            state["sanction"] = "Player Unbanned"

            embed = interaction.message.embeds[0]
            embed.title = "Select Transcript Type"
            embed.description = "Link a report or ticket transcript for this unban action."
            view = self.cog_ref.TranscriptTypeView(state["player"], state["offense"], "UNBAN", "Player Unbanned", state.get("unban_data"), self.cog_ref)
            await self.cog_ref._update_interaction_message(interaction, embed=embed, view=view)

    class TranscriptTypeView(discord.ui.View):
        def __init__(self, player: Dict, offense: str, strike: str, sanction: str, unban_data: Optional[Dict], cog_ref: 'BanCog'):
            super().__init__(timeout=180)
            self.player, self.offense, self.strike, self.sanction, self.unban_data, self.cog_ref = \
                player, offense, strike, sanction, unban_data, cog_ref
            self.message: Optional[discord.Message] = None
            self.add_item(self.cog_ref.TranscriptTypeSelect(self))
            back_target = "offense" if unban_data else "strike" 
            self.add_item(self.cog_ref.BackButton(back_target, cog_ref=self.cog_ref, row=1))
        async def on_timeout(self):
            if self.message:
                try: await self.message.edit(content="Transcript type selection timed out.", view=None, embed=None)
                except discord.HTTPException: pass

    class TranscriptTypeSelect(discord.ui.Select):
        def __init__(self, parent_view: 'TranscriptTypeView'):
            self.parent_view = parent_view
            self.cog_ref = parent_view.cog_ref
            options = [
                discord.SelectOption(label="Report Transcript", value="report", description="From report investigations"),
                discord.SelectOption(label="Ticket Transcript", value="ticket", description="From player appeals/tickets")
            ]
            super().__init__(placeholder="Select transcript type...", options=options)

        async def callback(self, interaction: discord.Interaction):
            transcript_type_keyword = self.values[0]
            if not interaction.guild:
                await interaction.response.edit_message(content="This can't be used in DMs.", embed=None, view=None)
                return

            await interaction.response.defer()
            transcripts_found = await get_transcript_options(interaction.guild, transcript_type_keyword)
            
            state = self.cog_ref.bot.user_form_state[interaction.user.id]
            embed = interaction.message.embeds[0]

            if transcripts_found:
                embed.title = f"Select Transcript"
                embed.description = f"Select a transcript from '{transcript_type_keyword}' channels."
                next_view = self.cog_ref.TranscriptSelectView(transcripts_found, self.parent_view)
            else:
                state["transcript_link"] = "N/A (No transcripts found)"
                embed.title = "Confirm Submission"
                response_preview = self.cog_ref._build_confirmation_preview_text(interaction.user.id)
                embed.description = f"No transcripts found.\n\n**Preview:**\n{response_preview}"
                next_view = self.cog_ref.ConfirmationView(state["player"], state["offense"], state["strike"], state["sanction"], state.get("unban_data"), self.cog_ref)

            await self.cog_ref._update_interaction_message(interaction, embed=embed, view=next_view)

    class TranscriptSelectView(discord.ui.View):
        def __init__(self, transcripts: List[str], parent_view: 'TranscriptTypeView'):
            super().__init__(timeout=180)
            self.message: Optional[discord.Message] = None
            self.cog_ref = parent_view.cog_ref
            self.add_item(self.cog_ref.TranscriptActualSelect(transcripts, self.cog_ref))
            self.add_item(self.cog_ref.BackButton("transcript_type", cog_ref=self.cog_ref, row=1))
        async def on_timeout(self):
            if self.message:
                try: await self.message.edit(content="Transcript selection timed out.", view=None, embed=None)
                except discord.HTTPException: pass

    class TranscriptActualSelect(discord.ui.Select):
        def __init__(self, transcripts: List[str], cog_ref: 'BanCog'):
            self.cog_ref = cog_ref
            self.transcript_map = {}
            options = [
                discord.SelectOption(label="Will add later/No Transcript", value="add_later"),
                discord.SelectOption(label="Witness Statement (No HTML)", value="witness")
            ]
            for link_md in transcripts[:23]:
                match = re.match(r"\[(.*?)\]\(<(.*?)>\)", link_md)
                if match:
                    label, url = match.groups()
                    if url not in self.transcript_map:
                        self.transcript_map[url] = label
                        options.append(discord.SelectOption(label=label[:100], value=url[:100]))
            super().__init__(placeholder="Select a transcript or option...", options=options)

        async def callback(self, interaction: discord.Interaction):
            chosen_value = self.values[0]
            link_for_output = "N/A"
            if chosen_value == "add_later": link_for_output = "Will add later / No Transcript"
            elif chosen_value == "witness": link_for_output = "Witness Statement (No HTML)"
            elif chosen_value in self.transcript_map: link_for_output = f"[{self.transcript_map[chosen_value]}](<{chosen_value}>)"
            elif chosen_value.startswith("http"): link_for_output = f"[Transcript Link](<{chosen_value}>)"
            
            user_id = interaction.user.id
            self.cog_ref.bot.user_form_state[user_id]["transcript_link"] = link_for_output
            state = self.cog_ref.bot.user_form_state[user_id]
            
            embed = interaction.message.embeds[0]
            embed.title = "Confirm Submission"
            embed.description = f"**Preview of Submission:**\n{self.cog_ref._build_confirmation_preview_text(user_id)}"
            view = self.cog_ref.ConfirmationView(state["player"], state["offense"], state["strike"], state["sanction"], state.get("unban_data"), self.cog_ref)
            await self.cog_ref._update_interaction_message(interaction, embed=embed, view=view)

    class ConfirmationView(discord.ui.View):
        def __init__(self, player_data: Dict, offense: str, strike: str, sanction: str, unban_data: Optional[Dict], cog_ref: 'BanCog'):
            super().__init__(timeout=300)
            self.message: Optional[discord.Message] = None
            self.add_item(cog_ref.InitialConfirmationButton(self, cog_ref))
            self.add_item(cog_ref.BackButton("transcript_select", cog_ref=cog_ref, row=1)) 
            self.add_item(cog_ref.CancelButton(cog_ref=cog_ref, row=1))
        async def on_timeout(self):
            if self.message:
                try: await self.message.edit(content="Ban form confirmation timed out.", view=None, embed=None)
                except discord.HTTPException: pass

    class InitialConfirmationButton(discord.ui.Button):
        def __init__(self, parent_view: 'ConfirmationView', cog_ref: 'BanCog'):
            super().__init__(label="Submit for Review", style=discord.ButtonStyle.primary)
            self.parent_view = parent_view
            self.cog_ref = cog_ref

        async def callback(self, interaction: discord.Interaction):
            try:
                state = self.cog_ref.bot.user_form_state.get(interaction.user.id, {})
                if not state:
                    await interaction.response.edit_message(content="Error: Form state expired or not found. Please start over.", view=None, embed=None)
                    return
                
                player_data = state.get("player", {})
                final_offense = state.get("offense_detail", state.get("offense"))
                
                full_ban_data = {
                    "player_data": player_data, "offense": final_offense, "strike": state.get("strike"),
                    "sanction": state.get("sanction"), "transcript": state.get("transcript_link"),
                    "unban_data": state.get("unban_data"), "submitted_by_id": interaction.user.id
                }

                player_name = player_data.get('Name', 'Unknown')
                action_type = "Unban" if full_ban_data["unban_data"] else "Ban"
                embed = discord.Embed(title=f"New {action_type} Request: {player_name}", color=discord.Color.orange(), timestamp=datetime.utcnow())
                
                author_icon_url = interaction.user.avatar.url if interaction.user.avatar else None
                embed.set_author(name=f"Submitted by: {interaction.user.display_name}", icon_url=author_icon_url)
                
                embed.add_field(name="Player", value=player_name, inline=True)
                embed.add_field(name="BUID", value=player_data.get('BohemiaUID', 'N/A'), inline=True)
                embed.add_field(name="Transcript", value=full_ban_data["transcript"], inline=False)

                if full_ban_data["unban_data"]:
                    unban_data = full_ban_data["unban_data"]
                    embed.add_field(name="Unban Details", value=final_offense, inline=False)
                    embed.add_field(name="Original Ban #", value=unban_data.get("ban_number_to_unban", "N/A"), inline=True)
                    embed.add_field(name="Remove Original Strike?", value="Yes" if unban_data.get("remove_strike") else "No", inline=True)
                else:
                    embed.add_field(name="Offense", value=final_offense, inline=False)
                    embed.add_field(name="Strike Level", value=full_ban_data["strike"], inline=True)
                    embed.add_field(name="Sanction", value=full_ban_data["sanction"], inline=True)
                    previous_strikes = await ban_tracker.get_player_strikes(player_data.get('BohemiaUID', ''))
                    if previous_strikes > 0:
                        embed.add_field(name="⚠️ Previous Active Strikes", value=str(previous_strikes), inline=True)
                
                embed.set_footer(text=f"Submitter User ID: {interaction.user.id}")

                mod_view = self.cog_ref.ModerationActionView(full_ban_data, player_name, self.cog_ref)
                
                target_channel_id = self.cog_ref.bot.config.get("channels", {}).get("pending_bans")
                if not (interaction.guild and target_channel_id and (target_channel := interaction.guild.get_channel(target_channel_id))):
                    await self.cog_ref._update_interaction_message(interaction, content="Error: Moderation channel not found.", embed=None, view=None); return

                mod_message = await target_channel.send(embed=embed, view=mod_view)
                await self.cog_ref._update_interaction_message(
                    interaction,
                    content=f"✅ Your request for **{player_name}** has been submitted: {mod_message.jump_url}",
                    embed=None, view=None
                )
            except Exception as e:
                print(f"--- FATAL ERROR in InitialConfirmationButton callback ---"); traceback.print_exc()
                try:
                    await interaction.followup.send(f"An error occurred during submission: {e}", ephemeral=True)
                except discord.HTTPException:
                    pass
            finally:
                if interaction.user.id in self.cog_ref.bot.user_form_state:
                    del self.cog_ref.bot.user_form_state[interaction.user.id]

    class ModerationActionView(discord.ui.View):
        def __init__(self, ban_data: Dict, player_name: str, cog_ref: 'BanCog'):
            super().__init__(timeout=None)
            self.add_item(cog_ref.ApproveBanButton(ban_data, cog_ref))
            self.add_item(cog_ref.DenyBanButton(player_name, cog_ref))

    class ApproveBanButton(discord.ui.Button):
        def __init__(self, ban_data: Dict, cog_ref: 'BanCog'):
            super().__init__(label="Approve", style=discord.ButtonStyle.success)
            self.ban_data, self.cog_ref = ban_data, cog_ref

        async def callback(self, interaction: discord.Interaction):
            if not self.cog_ref.bot.is_moderator_check_func(interaction):
                await interaction.response.send_message("❌ You don't have permission.", ephemeral=True)
                return
            
            await interaction.response.defer()
            pd = self.ban_data["player_data"]
            unban_info = self.ban_data.get("unban_data")
            is_unban_req = bool(unban_info)
            final_offense_text = self.ban_data["offense"]

            try:
                if is_unban_req and unban_info:
                    original_ban_to_unban = unban_info["ban_number_to_unban"]
                    if unban_info["remove_strike"]:
                        removed = await ban_tracker.remove_strike(original_ban_to_unban)
                        final_offense_text += f" (Strike {'Removed' if removed else 'NOT Removed'} from {original_ban_to_unban})"
                    else:
                        final_offense_text += f" (Strike Kept on {original_ban_to_unban})"
                    ban_number = await ban_tracker.add_ban(
                        player_name=pd.get("Name","N/A"), buid=pd.get("BohemiaUID","N/A"), offense=final_offense_text,
                        strike="UNBAN", sanction=self.ban_data.get("sanction","Player Unbanned"),
                        transcript=self.ban_data.get("transcript","N/A"), submitted_by=str(self.ban_data.get("submitted_by_id","Unknown")),
                        is_unban=True, related_ban_id=unban_info.get("related_ban_id")
                    )
                    action_verb = "Unban"
                else:
                    ban_number = await ban_tracker.add_ban(
                        player_name=pd.get("Name","N/A"), buid=pd.get("BohemiaUID","N/A"), offense=self.ban_data.get("offense","N/A"),
                        strike=self.ban_data.get("strike","N/A"), sanction=self.ban_data.get("sanction","N/A"),
                        transcript=self.ban_data.get("transcript","N/A"), submitted_by=str(self.ban_data.get("submitted_by_id","Unknown"))
                    )
                    action_verb = "Ban"

                original_embed = interaction.message.embeds[0]
                original_embed.title = f"{action_verb} Approved: {pd.get('Name', 'N/A')}"
                original_embed.color = discord.Color.green()
                original_embed.add_field(name=f"{action_verb} ID", value=ban_number, inline=False)
                original_embed.add_field(name="Approved By", value=interaction.user.mention, inline=False)
                
                await interaction.message.edit(embed=original_embed, view=None)
                await interaction.message.add_reaction("✅")

            except Exception as e:
                print(f"Error during ban approval process: {e}")
                traceback.print_exc()
                error_embed = interaction.message.embeds[0]
                error_embed.add_field(name="Approval Error", value=f"An error occurred: {e}", inline=False)
                error_embed.color = discord.Color.dark_red()
                await interaction.message.edit(embed=error_embed, view=None)
                await interaction.followup.send(f"An error occurred during approval: {e}", ephemeral=True)

    class DenyBanButton(discord.ui.Button):
        def __init__(self, player_name: str, cog_ref: 'BanCog'):
            super().__init__(label="Deny", style=discord.ButtonStyle.danger)
            self.player_name, self.cog_ref = player_name, cog_ref

        async def callback(self, interaction: discord.Interaction):
            if not self.cog_ref.bot.is_moderator_check_func(interaction):
                await interaction.response.send_message("❌ You don't have permission.", ephemeral=True)
                return
            
            embed = interaction.message.embeds[0]
            embed.title = f"Request Denied: {self.player_name}"
            embed.color = discord.Color.red()
            embed.add_field(name="Denied By", value=interaction.user.mention, inline=False)
            await interaction.response.edit_message(embed=embed, view=None)
            await interaction.message.add_reaction("❌")

    class BackButton(discord.ui.Button):
        def __init__(self, back_to_step: str, cog_ref: 'BanCog', row: Optional[int] = None):
            super().__init__(label="← Back", style=discord.ButtonStyle.secondary, row=row)
            self.back_to_step, self.cog_ref = back_to_step, cog_ref

        async def callback(self, interaction: discord.Interaction):
            user_id = interaction.user.id
            state = self.cog_ref.bot.user_form_state.get(user_id)
            if not state or not state.get("player"):
                await interaction.response.edit_message(content="❌ Form state lost. Please start over.", embed=None, view=None)
                return

            embed = interaction.message.embeds[0] if interaction.message.embeds else discord.Embed()
            next_view: Optional[discord.ui.View] = None
            player_data = state["player"]
            
            if self.back_to_step == "player":
                players_list = state.get("players", [])
                search_term = state.get("search_term", "")
                if not players_list:
                     await interaction.response.edit_message(content="Error: Player search data lost.", embed=None, view=None); return
                next_view = self.cog_ref.PlayerView(players_list, search_term, self.cog_ref)
                embed = next_view.create_embed()

            elif self.back_to_step == "offense":
                embed.title = "Player Selected"
                embed.description = "Please choose the offense."
                embed.clear_fields()
                embed.add_field(name="Name", value=player_data.get("Name", "N/A"), inline=True)
                embed.add_field(name="Level", value=str(player_data.get("Level", "N/A")), inline=True)
                embed.add_field(name="Last Played", value=player_data.get("Last Played", "N/A"), inline=True)
                embed.add_field(name="Bohemia UID", value=player_data.get("BohemiaUID", "N/A"), inline=False)
                next_view = self.cog_ref.OffenseView(player_data, self.cog_ref)

            elif self.back_to_step == "strike" and (offense_data := state.get("offense")):
                embed.title = "Select Strike Level"
                embed.description = "Choose the appropriate strike for this offense."
                next_view = self.cog_ref.StrikeView(player_data, offense_data, self.cog_ref)

            elif self.back_to_step in ["transcript_type", "transcript_select"]:
                embed.title = "Select Transcript Type"
                embed.description = "Link a report or ticket transcript."
                next_view = self.cog_ref.TranscriptTypeView(
                    player_data, state["offense"], state["strike"], state["sanction"], state.get("unban_data"), self.cog_ref
                )
            else:
                await interaction.response.edit_message(content=f"Cannot go back to step '{self.back_to_step}'.", embed=None, view=None)
                return

            if next_view:
                await self.cog_ref._update_interaction_message(interaction, embed=embed, view=next_view)

    class CancelButton(discord.ui.Button):
        def __init__(self, cog_ref: 'BanCog', row: Optional[int] = None):
            super().__init__(label="Cancel Form", style=discord.ButtonStyle.danger, row=row)
            self.cog_ref = cog_ref

        async def callback(self, interaction: discord.Interaction):
            if interaction.user.id in self.cog_ref.bot.user_form_state:
                del self.cog_ref.bot.user_form_state[interaction.user.id]
            await interaction.response.edit_message(content="❌ Ban form cancelled.", view=None, embed=None)

    def _build_confirmation_preview_text(self, user_id: int) -> str:
        state = self.bot.user_form_state.get(user_id, {})
        player = state.get("player", {})
        offense = state.get("offense", "N/A")
        strike = state.get("strike", "N/A")
        sanction = state.get("sanction", "N/A")
        unban_data = state.get("unban_data")
        transcript = state.get("transcript_link", "N/A")

        if strike == "Custom":
            final_offense_text = state.get("offense_detail", offense)
        else:
            final_offense_text = offense

        if unban_data:
            return (
                f"**Player:** {player.get('Name', 'N/A')} (`{player.get('BohemiaUID', 'N/A')}`)\n"
                f"**Action:** Unban\n"
                f"**Details:** {final_offense_text}\n"
                f"**Original Ban #:** {unban_data.get('ban_number_to_unban', 'N/A')}\n"
                f"**Transcript:** {transcript}"
            )
        else:
            return (
                f"**Player:** {player.get('Name', 'N/A')} (`{player.get('BohemiaUID', 'N/A')}`)\n"
                f"**Reason:** {final_offense_text}\n"
                f"**Punishment:** ({strike}) {sanction}\n"
                f"**Transcript:** {transcript}"
            )

    @app_commands.command(name="ban_player", description="Start the ban or unban process for a player.")
    @app_commands.guild_only()
    async def ban_player_command(self, interaction: discord.Interaction):
        from ui.shared_ui import PlayerSearchModal
        if interaction.user.id in self.bot.user_form_state:
            del self.bot.user_form_state[interaction.user.id]
        self.bot.user_form_state[interaction.user.id] = {}
        modal = PlayerSearchModal(
            player_db_instance=self.bot.player_db,
            on_search_complete=self._handle_ban_player_search_results,
            channel_search_func=search_channels_for_players_fallback
        )
        await interaction.response.send_modal(modal)

    async def _handle_ban_player_search_results(self, interaction: discord.Interaction, players: List[Dict], search_term: str):
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True)
        
        if not players:
            await interaction.followup.send(f"No players found matching '{search_term}'.", ephemeral=True)
            return

        self.bot.user_form_state[interaction.user.id] = {"players": players, "search_term": search_term}
        view = self.PlayerView(players, search_term, self)
        embed = view.create_embed()
        message = await interaction.followup.send(embed=embed, view=view, ephemeral=True)
        view.message = message

async def setup(bot: commands.Bot):
    await bot.add_cog(BanCog(bot))