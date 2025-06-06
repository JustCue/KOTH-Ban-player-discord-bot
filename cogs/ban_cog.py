# cogs/ban_cog.py
import discord
from discord.ext import commands
from discord import app_commands
import re
import traceback
from typing import List, Dict, Optional, Any
from datetime import datetime

from punishments import punishments
from ban_history import ban_tracker
from ui.shared_ui import PlayerSearchModal, search_channels_for_players_fallback

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
                        if len(transcripts) >= 5: break
                if len(transcripts) >= 5: break
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

    class PlayerView(discord.ui.View):
        def __init__(self, players: List[Dict], cog_ref: 'BanCog'):
            super().__init__(timeout=300)
            self.players = players
            self.cog_ref = cog_ref
            self.message: Optional[discord.Message] = None
            self.add_item(self.cog_ref.PlayerSelect(self.players, self.cog_ref))
            
            search_again_button = discord.ui.Button(label="🔍 Search Again", style=discord.ButtonStyle.secondary, row=1)
            search_again_button.callback = self.search_again
            self.add_item(search_again_button)

        async def search_again(self, interaction: discord.Interaction):
            modal = PlayerSearchModal(
                player_db_instance=self.cog_ref.bot.player_db,
                on_search_complete=self.cog_ref._handle_ban_player_search_results,
                channel_search_func=search_channels_for_players_fallback
            )
            await interaction.response.send_modal(modal)
            if self.message:
                try: await self.message.delete()
                except discord.HTTPException: pass
        
        async def on_timeout(self):
            if self.message:
                try: await self.message.edit(content="Player selection for ban timed out.", view=None)
                except discord.HTTPException: pass

    class PlayerSelect(discord.ui.Select):
        def __init__(self, players: List[Dict], cog_ref: 'BanCog'):
            self.players = players
            self.cog_ref = cog_ref
            options = []
            for p_data in players[:25]:
                label = p_data.get("Name", "Unknown Player")[:100]
                description = f"Lvl {p_data.get('Level','N/A')}, Last: {p_data.get('Last Played','N/A')}"[:100]
                options.append(discord.SelectOption(label=label, description=description, value=p_data.get("BohemiaUID", p_data.get("Name"))))
            super().__init__(placeholder="Choose a player to proceed...", options=options, min_values=1, max_values=1, row=0)

        async def callback(self, interaction: discord.Interaction):
            if not interaction.response.is_done():
                await interaction.response.defer(ephemeral=True)
            
            selected_value = self.values[0]
            player = next((p for p in self.players if p.get("BohemiaUID", p.get("Name")) == selected_value), None)

            if not player:
                await interaction.followup.send("Error: Selected player data not found. Please try searching again.", ephemeral=True)
                return

            self.cog_ref.bot.user_form_state[interaction.user.id]["player"] = player
            
            if interaction.message:
                try: await interaction.message.delete()
                except discord.HTTPException: pass

            embed = discord.Embed(title="Player Selected for Ban Form", color=discord.Color.green())
            embed.add_field(name="Name", value=player.get("Name", "N/A"), inline=True)
            embed.add_field(name="Level", value=str(player.get("Level", "N/A")), inline=True)
            embed.add_field(name="Last Played", value=player.get("Last Played", "N/A"), inline=True)
            embed.add_field(name="Bohemia UID", value=player.get("BohemiaUID", "N/A"), inline=False)
            
            view = self.cog_ref.OffenseView(player, self.cog_ref)
            message = await interaction.followup.send(embed=embed, view=view, ephemeral=True)
            if hasattr(view, 'message'): view.message = message


    class OffenseView(discord.ui.View):
        def __init__(self, player: Dict, cog_ref: 'BanCog'):
            super().__init__(timeout=300)
            self.player = player
            self.cog_ref = cog_ref
            self.message: Optional[discord.Message] = None
            self.add_item(self.cog_ref.OffenseSelect(player, self.cog_ref))
            self.add_item(self.cog_ref.BackButton("player", cog_ref=self.cog_ref, row=1))
        
        async def on_timeout(self):
            if self.message:
                try: await self.message.edit(content="Offense selection timed out.", view=None)
                except discord.HTTPException: pass

    class OffenseSelect(discord.ui.Select):
        def __init__(self, player: Dict, cog_ref: 'BanCog'):
            self.player = player
            self.cog_ref = cog_ref
            all_offenses_keys = list(punishments.keys()) + ["UNBAN (Strike Remains)", "UNBAN (Remove Strike)"]
            options = [discord.SelectOption(label=offense_key[:100]) for offense_key in all_offenses_keys[:25]]
            super().__init__(placeholder="Select offense...", options=options, min_values=1, max_values=1)

        async def callback(self, interaction: discord.Interaction):
            selected_offense = self.values[0]
            
            if selected_offense == "Custom Punishment":
                modal = self.cog_ref.CustomPunishmentModal(self.player, self.cog_ref)
                await interaction.response.send_modal(modal)
                return

            if not interaction.response.is_done():
                await interaction.response.defer(ephemeral=True)
            
            try:
                self.cog_ref.bot.user_form_state[interaction.user.id]["offense"] = selected_offense

                if interaction.message:
                    try: await interaction.message.delete()
                    except discord.HTTPException: pass
                
                next_view: Optional[discord.ui.View] = None
                followup_content = ""

                if selected_offense in ["UNBAN (Strike Remains)", "UNBAN (Remove Strike)"]:
                    followup_content = "Select which existing ban to unban:"
                    next_view = self.cog_ref.UnbanReportView(self.player.get("BohemiaUID",""), selected_offense, self.cog_ref)
                else:
                    followup_content = "Select the strike level:"
                    next_view = self.cog_ref.StrikeView(self.player, selected_offense, self.cog_ref)
                
                if next_view:
                    message = await interaction.followup.send(content=followup_content, view=next_view, ephemeral=True)
                    if hasattr(next_view, 'message'): 
                        next_view.message = message
                else:
                    await interaction.followup.send("Error: Could not determine the next step.", ephemeral=True)

            except Exception as e:
                print(f"--- ERROR in OffenseSelect callback ---")
                traceback.print_exc()
                await interaction.followup.send(f"An error occurred: {e}", ephemeral=True)


    class CustomPunishmentModal(discord.ui.Modal, title="Custom Punishment"):
        reason_input = discord.ui.TextInput(label="Reason for Custom Punishment", style=discord.TextStyle.long, placeholder="Enter custom reason...", required=True)
        length_input = discord.ui.TextInput(label="Ban Length", placeholder="e.g., 3 days, 1 week, Permanent", required=True)

        def __init__(self, player: Dict, cog_ref: 'BanCog'):
            super().__init__(timeout=300)
            self.player = player
            self.cog_ref = cog_ref

        async def on_submit(self, interaction: discord.Interaction):
            if not interaction.response.is_done():
                 await interaction.response.defer(ephemeral=True)

            user_id = interaction.user.id
            if user_id not in self.cog_ref.bot.user_form_state:
                self.cog_ref.bot.user_form_state[user_id] = {}
            
            self.cog_ref.bot.user_form_state[user_id]["offense_detail"] = self.reason_input.value
            self.cog_ref.bot.user_form_state[user_id]["strike"] = "Custom"
            self.cog_ref.bot.user_form_state[user_id]["sanction"] = self.length_input.value
            
            view = self.cog_ref.TranscriptTypeView(
                self.player, self.reason_input.value, "Custom", self.length_input.value, None, self.cog_ref
            )
            message = await interaction.followup.send("Select transcript type:", view=view, ephemeral=True)
            if hasattr(view, 'message'): view.message = message


    class StrikeView(discord.ui.View):
        def __init__(self, player: Dict, offense: str, cog_ref: 'BanCog'):
            super().__init__(timeout=300)
            self.player = player
            self.offense = offense
            self.cog_ref = cog_ref
            self.message: Optional[discord.Message] = None
            
            strikes_data = punishments.get(offense, {})
            if strikes_data:
                self.add_item(self.cog_ref.StrikeSelect(player, offense, strikes_data, self.cog_ref))
            else:
                print(f"Warning: No strikes defined for offense '{offense}' in StrikeView.")

            self.add_item(self.cog_ref.BackButton("offense", cog_ref=self.cog_ref, row=1))
        
        async def on_timeout(self):
            if self.message:
                try: await self.message.edit(content="Strike selection timed out.", view=None)
                except discord.HTTPException: pass

    class StrikeSelect(discord.ui.Select):
        def __init__(self, player: Dict, offense: str, strikes_data: Dict, cog_ref: 'BanCog'):
            self.player = player
            self.offense = offense
            self.strikes_data = strikes_data
            self.cog_ref = cog_ref
            options = [discord.SelectOption(label=s_level[:100]) for s_level in strikes_data.keys()][:25]
            super().__init__(placeholder="Select strike level...", options=options, min_values=1, max_values=1)

        async def callback(self, interaction: discord.Interaction):
            if not interaction.response.is_done():
                await interaction.response.defer(ephemeral=True)
            
            strike_level = self.values[0]
            sanction_options = self.strikes_data[strike_level]
            self.cog_ref.bot.user_form_state[interaction.user.id]["strike"] = strike_level

            if interaction.message:
                try: await interaction.message.delete()
                except discord.HTTPException: pass

            next_view: Optional[discord.ui.View] = None
            followup_content = ""

            if isinstance(sanction_options, list):
                followup_content = "Select a ban duration:"
                next_view = self.cog_ref.SanctionChooserView(self.player, self.offense, strike_level, sanction_options, self.cog_ref)
            else:
                self.cog_ref.bot.user_form_state[interaction.user.id]["sanction"] = sanction_options
                followup_content = "Select transcript type:"
                next_view = self.cog_ref.TranscriptTypeView(self.player, self.offense, strike_level, sanction_options, None, self.cog_ref)
            
            message = await interaction.followup.send(content=followup_content, view=next_view, ephemeral=True)
            if hasattr(next_view, 'message') and next_view:
                next_view.message = message

    class SanctionChooserView(discord.ui.View):
        def __init__(self, player: Dict, offense: str, strike_level: str, sanction_list: List[str], cog_ref: 'BanCog'):
            super().__init__(timeout=180)
            self.player = player
            self.offense = offense
            self.strike_level = strike_level
            self.cog_ref = cog_ref
            self.message: Optional[discord.Message] = None
            self.add_item(self.cog_ref.SanctionActualSelect(player, offense, strike_level, sanction_list, self.cog_ref))
            self.add_item(self.cog_ref.BackButton("strike", cog_ref=self.cog_ref, row=1))

        async def on_timeout(self):
            if self.message:
                try: await self.message.edit(content="Sanction choice timed out.", view=None)
                except discord.HTTPException: pass
                
    class SanctionActualSelect(discord.ui.Select):
        def __init__(self, player: Dict, offense: str, strike_level: str, sanction_list: List[str], cog_ref: 'BanCog'):
            self.player = player
            self.offense = offense
            self.strike_level = strike_level
            self.cog_ref = cog_ref
            options = [discord.SelectOption(label=sanc[:100]) for sanc in sanction_list[:25]]
            super().__init__(placeholder="Select ban duration...", options=options, min_values=1, max_values=1)

        async def callback(self, interaction: discord.Interaction):
            if not interaction.response.is_done():
                await interaction.response.defer(ephemeral=True)
            
            chosen_sanction = self.values[0]
            self.cog_ref.bot.user_form_state[interaction.user.id]["sanction"] = chosen_sanction
            
            if interaction.message:
                try: await interaction.message.delete()
                except discord.HTTPException: pass

            view = self.cog_ref.TranscriptTypeView(self.player, self.offense, self.strike_level, chosen_sanction, None, self.cog_ref)
            message = await interaction.followup.send("Select transcript type:", view=view, ephemeral=True)
            if hasattr(view, 'message'): view.message = message

    class UnbanReportView(discord.ui.View):
        def __init__(self, player_buid: str, unban_type: str, cog_ref: 'BanCog'):
            super().__init__(timeout=300)
            self.player_buid = player_buid
            self.unban_type = unban_type
            self.cog_ref = cog_ref
            self.message: Optional[discord.Message] = None
            self.add_item(self.cog_ref.UnbanReportSelect(player_buid, unban_type, self))
            self.add_item(self.cog_ref.BackButton("offense", cog_ref=self.cog_ref, row=1))
        
        async def on_timeout(self):
            if self.message:
                try: await self.message.edit(content="Unban report selection timed out.", view=None)
                except discord.HTTPException: pass

    class UnbanReportSelect(discord.ui.Select):
        def __init__(self, player_buid: str, unban_type: str, parent_view: discord.ui.View):
            self.player_buid = player_buid
            self.unban_type = unban_type
            self.remove_strike = unban_type == "UNBAN (Remove Strike)"
            self.parent_view = parent_view
            self.cog_ref = parent_view.cog_ref

            super().__init__(
                placeholder="Loading ban history...",
                min_values=1, max_values=1,
                options=[discord.SelectOption(label="Loading...", value="loading_placeholder", description="Please wait")]
            )
            discord.utils.create_task(self._load_options_and_update_view())


        async def _load_options_and_update_view(self):
            history = await ban_tracker.get_player_history(self.player_buid)
            options = []
            if history:
                for ban_record in sorted(history, key=lambda x: x['timestamp'], reverse=True):
                    if not ban_record.get("is_unban", False):
                        status_strike = " (Strike Removed)" if ban_record.get("strike_removed", False) else ""
                        label = f"{ban_record['ban_number']} - {ban_record['offense'][:40]}{'...' if len(ban_record['offense']) > 40 else ''}{status_strike}"
                        description = f"{ban_record['timestamp'][:10]} ({ban_record['strike']})"[:100]
                        options.append(discord.SelectOption(label=label, description=description, value=ban_record["ban_number"]))
                    if len(options) >= 24: break
            
            if not options:
                self.options = [discord.SelectOption(label="No active bans found for this player", value="none_found", description="Cannot proceed")]
                self.placeholder = "No active bans found."
            else:
                self.options = options
                self.placeholder = f"Select ban to {'remove strike from & unban' if self.remove_strike else 'unban (keep strike)'}..."
            
            if self.parent_view.message:
                try: await self.parent_view.message.edit(view=self.parent_view)
                except discord.HTTPException as e: print(f"Error editing message in UnbanReportSelect load: {e}")
            else:
                print("UnbanReportSelect: Parent view's message not available for update during load.")


        async def callback(self, interaction: discord.Interaction):
            selected_ban_number = self.values[0]

            if selected_ban_number == "loading_placeholder":
                await interaction.response.send_message("Still loading options, please wait a moment.", ephemeral=True); return
            
            if selected_ban_number == "none_found":
                await interaction.response.send_message("❌ No valid bans found to unban for this player.", ephemeral=True)
                if interaction.message:
                    try: await interaction.message.delete()
                    except discord.HTTPException: pass
                return

            if not interaction.response.is_done():
                await interaction.response.defer(ephemeral=True)

            if interaction.message:
                try: await interaction.message.delete()
                except discord.HTTPException: pass

            user_id = interaction.user.id
            state = self.cog_ref.bot.user_form_state.get(user_id)
            if not state or "player" not in state:
                await interaction.followup.send("❌ Error: Player context lost. Please start over.", ephemeral=True); return

            original_ban_details = await ban_tracker.get_ban_by_number(selected_ban_number)
            original_ban_db_id = original_ban_details.get('id') if original_ban_details else None

            unban_data = {
                "ban_number_to_unban": selected_ban_number, 
                "remove_strike": self.remove_strike,
                "related_ban_id": original_ban_db_id
            }
            self.cog_ref.bot.user_form_state[user_id]["unban_data"] = unban_data
            self.cog_ref.bot.user_form_state[user_id]["strike"] = "UNBAN"
            self.cog_ref.bot.user_form_state[user_id]["sanction"] = "Player Unbanned"

            view = self.cog_ref.TranscriptTypeView(
                state["player"], state["offense"], "UNBAN", "Player Unbanned", unban_data, self.cog_ref
            )
            message = await interaction.followup.send("Select transcript type for this unban:", view=view, ephemeral=True)
            if hasattr(view, 'message'): view.message = message

    class TranscriptTypeView(discord.ui.View):
        def __init__(self, player: Dict, offense: str, strike: str, sanction: str, unban_data: Optional[Dict], cog_ref: 'BanCog'):
            super().__init__(timeout=180)
            self.player, self.offense, self.strike, self.sanction, self.unban_data, self.cog_ref = \
                player, offense, strike, sanction, unban_data, cog_ref
            self.message: Optional[discord.Message] = None
            self.add_item(self.cog_ref.TranscriptTypeSelect(player, offense, strike, sanction, unban_data, cog_ref))
            
            back_target = "offense"
            if not unban_data:
                back_target = "strike" 
            
            self.add_item(self.cog_ref.BackButton(back_target, cog_ref=self.cog_ref, row=1))

        async def on_timeout(self):
            if self.message:
                try: await self.message.edit(content="Transcript type selection timed out.", view=None)
                except discord.HTTPException: pass


    class TranscriptTypeSelect(discord.ui.Select):
        def __init__(self, player: Dict, offense: str, strike: str, sanction: str, unban_data: Optional[Dict], cog_ref: 'BanCog'):
            self.player, self.offense, self.strike, self.sanction, self.unban_data, self.cog_ref = \
                player, offense, strike, sanction, unban_data, cog_ref
            options = [
                discord.SelectOption(label="Report Transcript", value="report", description="Transcripts from report investigations"),
                discord.SelectOption(label="Ticket Transcript", value="ticket", description="Transcripts from player appeals/tickets")
            ]
            super().__init__(placeholder="Select transcript type...", options=options, min_values=1, max_values=1)

        async def callback(self, interaction: discord.Interaction):
            if not interaction.response.is_done():
                await interaction.response.defer(ephemeral=True)
            
            try:
                transcript_type_keyword = self.values[0]
                
                if interaction.message:
                    try: await interaction.message.delete()
                    except discord.HTTPException: pass

                if not interaction.guild:
                    await interaction.followup.send("This action cannot be performed in DMs.", ephemeral=True)
                    return

                transcripts_found = await get_transcript_options(interaction.guild, transcript_type_keyword)
                
                next_view: Optional[discord.ui.View] = None
                followup_content = ""

                if transcripts_found:
                    followup_content = f"Select a transcript from '{transcript_type_keyword}' channels:"
                    next_view = self.cog_ref.TranscriptSelectView(transcripts_found, self.player, self.offense, self.strike, self.sanction, self.unban_data, self.cog_ref)
                else:
                    self.cog_ref.bot.user_form_state[interaction.user.id]["transcript_link"] = "N/A (No transcripts found)"
                    followup_content = f"No transcripts found in '{transcript_type_keyword}' channels.\n\n**Preview of Submission:**"
                    response_preview_text = self.cog_ref._build_confirmation_preview_text(
                        interaction.user.id, "N/A (No transcripts found)"
                    )
                    followup_content += f"\n{response_preview_text}"
                    next_view = self.cog_ref.ConfirmationView(
                        response_preview_text, self.player, self.offense, self.strike, self.sanction, 
                        "N/A (No transcripts found)", self.unban_data, self.cog_ref
                    )

                if next_view:
                    message = await interaction.followup.send(content=followup_content, view=next_view, ephemeral=True)
                    if hasattr(next_view, 'message'):
                        next_view.message = message
                else:
                    await interaction.followup.send("Error: Could not determine next step after transcript selection.", ephemeral=True)

            except Exception as e:
                print(f"--- ERROR in TranscriptTypeSelect callback ---")
                traceback.print_exc()
                await interaction.followup.send(f"An unexpected error occurred: {e}\nPlease try again or contact an admin.", ephemeral=True)


    class TranscriptSelectView(discord.ui.View):
        def __init__(self, transcripts: List[str], player: Dict, offense: str, strike: str, sanction: str, unban_data: Optional[Dict], cog_ref: 'BanCog'):
            super().__init__(timeout=180)
            self.player, self.offense, self.strike, self.sanction, self.unban_data, self.cog_ref = \
                player, offense, strike, sanction, unban_data, cog_ref
            self.message: Optional[discord.Message] = None
            self.add_item(self.cog_ref.TranscriptActualSelect(transcripts, player, offense, strike, sanction, unban_data, cog_ref))
            self.add_item(self.cog_ref.BackButton("transcript_type", cog_ref=self.cog_ref, row=1))
        async def on_timeout(self):
            if self.message:
                try: await self.message.edit(content="Transcript selection timed out.", view=None)
                except discord.HTTPException: pass


    class TranscriptActualSelect(discord.ui.Select):
        def __init__(self, transcripts: List[str], player: Dict, offense: str, strike: str, sanction: str, unban_data: Optional[Dict], cog_ref: 'BanCog'):
            self.player, self.offense, self.strike, self.sanction, self.unban_data, self.cog_ref = \
                player, offense, strike, sanction, unban_data, cog_ref
            
            self.transcript_map = {}
            options = [
                discord.SelectOption(label="Will add later/No Transcript", value="add_later", description="No transcript or manual add."),
                discord.SelectOption(label="Witness Statement (No HTML)", value="witness", description="Based on witness testimony only.")
            ]
            for link_md in transcripts[:23]:
                match = re.match(r"\[(.*?)\]\(<(.*?)>\)", link_md)
                if match:
                    label, url = match.groups()
                    if url not in self.transcript_map:
                        self.transcript_map[url] = label
                        options.append(discord.SelectOption(label=label[:100], value=url[:100], description=f"Link to {label}"[:100]))
            super().__init__(placeholder="Select a transcript or option...", options=options, min_values=1, max_values=1)

        async def callback(self, interaction: discord.Interaction):
            if not interaction.response.is_done():
                await interaction.response.defer(ephemeral=True)

            chosen_value = self.values[0]
            link_for_output = "N/A"

            if chosen_value == "add_later":
                link_for_output = "Will add later / No Transcript"
            elif chosen_value == "witness":
                link_for_output = "Witness Statement (No HTML)"
            elif chosen_value in self.transcript_map:
                label = self.transcript_map[chosen_value]
                link_for_output = f"[{label}](<{chosen_value}>)"
            elif chosen_value.startswith("http"):
                 link_for_output = f"[Transcript Link](<{chosen_value}>)"
            else:
                link_for_output = f"Selected: {chosen_value[:80]}"

            self.cog_ref.bot.user_form_state[interaction.user.id]["transcript_link"] = link_for_output
            
            if interaction.message:
                try: await interaction.message.delete()
                except discord.HTTPException: pass
            
            response_preview_text = self.cog_ref._build_confirmation_preview_text(
                interaction.user.id, link_for_output
            )
            view = self.cog_ref.ConfirmationView(
                response_preview_text, self.player, self.offense, self.strike, self.sanction, 
                link_for_output, self.unban_data, self.cog_ref
            )
            message = await interaction.followup.send(content=f"**Preview of Submission:**\n{response_preview_text}", view=view, ephemeral=True)
            if hasattr(view, 'message'): view.message = message

    class ConfirmationView(discord.ui.View):
        def __init__(self, response_text_preview: str, player_data: Dict, offense: str, strike: str,
                     sanction: str, transcript_link_md: str, unban_data: Optional[Dict], cog_ref: 'BanCog'):
            super().__init__(timeout=300)
            self.cog_ref = cog_ref
            self.message: Optional[discord.Message] = None
            self.add_item(self.cog_ref.InitialConfirmationButton(
                response_text_preview, player_data, offense, strike, sanction, transcript_link_md, unban_data, cog_ref
            ))
            self.add_item(self.cog_ref.BackButton("transcript_select", cog_ref=cog_ref, row=1)) 
            self.add_item(self.cog_ref.CancelButton(cog_ref=cog_ref, row=1))
        async def on_timeout(self):
            if self.message:
                try: await self.message.edit(content="Ban form confirmation timed out.", view=None)
                except discord.HTTPException: pass


    class InitialConfirmationButton(discord.ui.Button):
        def __init__(self, response_text_preview: str, player_data: Dict, offense: str, strike: str,
                     sanction: str, transcript_link_md: str, unban_data: Optional[Dict], cog_ref: 'BanCog'):
            super().__init__(label="Submit for Review", style=discord.ButtonStyle.primary)
            self.player_data = player_data
            self.offense = offense
            self.strike = strike
            self.sanction = sanction
            self.transcript_link_md = transcript_link_md
            self.unban_data = unban_data
            self.cog_ref = cog_ref

        async def callback(self, interaction: discord.Interaction):
            if not interaction.response.is_done():
                await interaction.response.defer(ephemeral=True)

            try:
                final_offense_text = self.offense
                if self.strike == "Custom":
                    final_offense_text = self.cog_ref.bot.user_form_state.get(interaction.user.id, {}).get("offense_detail", self.offense)
                
                full_ban_data_for_approval = {
                    "player_data": self.player_data, "offense": final_offense_text, "strike": self.strike,
                    "sanction": self.sanction, "transcript": self.transcript_link_md,
                    "unban_data": self.unban_data, "submitted_by_id": interaction.user.id
                }

                action_type_str = "Unban" if self.unban_data else "Ban"
                embed_title = f"New {action_type_str} Request: {self.player_data.get('Name', 'Unknown Player')}"
                
                embed = discord.Embed(title=embed_title, color=discord.Color.orange(), timestamp=datetime.utcnow())
                embed.set_author(name=f"Submitted by: {interaction.user.display_name}", icon_url=interaction.user.avatar.url if interaction.user.avatar else None)
                embed.add_field(name="Player", value=self.player_data.get('Name', 'N/A'), inline=True)
                embed.add_field(name="BUID", value=self.player_data.get('BohemiaUID', 'N/A'), inline=True)
                embed.add_field(name="Transcript", value=self.transcript_link_md if self.transcript_link_md else "N/A", inline=False)

                if self.unban_data:
                    embed.add_field(name="Unban Details", value=final_offense_text, inline=False)
                    embed.add_field(name="Original Ban #", value=self.unban_data.get("ban_number_to_unban", "N/A"), inline=True)
                    embed.add_field(name="Remove Original Strike?", value="Yes" if self.unban_data.get("remove_strike") else "No", inline=True)
                else:
                    embed.add_field(name="Offense", value=final_offense_text, inline=False)
                    embed.add_field(name="Strike Level", value=self.strike, inline=True)
                    embed.add_field(name="Sanction", value=self.sanction, inline=True)
                    previous_strikes = await ban_tracker.get_player_strikes(self.player_data.get('BohemiaUID', ''))
                    if previous_strikes > 0:
                        embed.add_field(name="⚠️ Previous Active Strikes", value=str(previous_strikes), inline=True)
                embed.set_footer(text=f"Submitter User ID: {interaction.user.id}")

                mod_view = self.cog_ref.ModerationActionView(
                    ban_data=full_ban_data_for_approval,
                    player_name=self.player_data.get('Name', 'Unknown Player'),
                    cog_ref=self.cog_ref
                )
                
                target_channel_id = self.cog_ref.bot.config.get("channels", {}).get("pending_bans")
                target_channel = interaction.guild.get_channel(target_channel_id) if target_channel_id and interaction.guild else interaction.channel

                if not target_channel:
                    await interaction.followup.send("Error: Moderation channel not found.", ephemeral=True); return
                
                mod_message = await target_channel.send(embed=embed, view=mod_view)
                
                await interaction.edit_original_response(
                    content=f"✅ Your {action_type_str.lower()} request for **{self.player_data.get('Name', 'N/A')}** has been submitted for review in {target_channel.mention}. Link: {mod_message.jump_url}",
                    view=None
                )

            except Exception as e:
                print(f"--- FATAL ERROR in InitialConfirmationButton callback ---")
                traceback.print_exc()
                await interaction.followup.send(f"An unexpected error occurred while submitting for review. Administrators have been notified.\n`Error: {e}`", ephemeral=True)

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
            self.ban_data = ban_data
            self.cog_ref = cog_ref

        async def callback(self, interaction: discord.Interaction):
            if not self.cog_ref.bot.is_moderator_check_func(interaction):
                await interaction.response.send_message("❌ You don't have permission.", ephemeral=True)
                return
            
            if not interaction.response.is_done():
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
                try: await interaction.message.edit(embed=error_embed, view=None)
                except discord.HTTPException: pass
                if not interaction.response.is_done():
                    await interaction.response.send_message(f"An error occurred during approval: {e}", ephemeral=True)
                else:
                    await interaction.followup.send(f"An error occurred during approval: {e}", ephemeral=True)


    class DenyBanButton(discord.ui.Button):
        def __init__(self, player_name: str, cog_ref: 'BanCog'):
            super().__init__(label="Deny", style=discord.ButtonStyle.danger)
            self.player_name = player_name
            self.cog_ref = cog_ref

        async def callback(self, interaction: discord.Interaction):
            if not self.cog_ref.bot.is_moderator_check_func(interaction):
                await interaction.response.send_message("❌ You don't have permission.", ephemeral=True)
                return
            if not interaction.response.is_done():
                 await interaction.response.defer()

            embed = interaction.message.embeds[0]
            embed.title = f"Request Denied: {self.player_name}"
            embed.color = discord.Color.red()
            embed.add_field(name="Denied By", value=interaction.user.mention, inline=False)
            
            await interaction.message.edit(embed=embed, view=None)
            await interaction.message.add_reaction("❌")


    class BackButton(discord.ui.Button):
        def __init__(self, back_to_step: str, cog_ref: 'BanCog', row: Optional[int] = None):
            super().__init__(label="← Back", style=discord.ButtonStyle.secondary, row=row)
            self.back_to_step = back_to_step
            self.cog_ref = cog_ref

        async def callback(self, interaction: discord.Interaction):
            if not interaction.response.is_done():
                await interaction.response.defer(ephemeral=True)

            user_id = interaction.user.id
            state = self.cog_ref.bot.user_form_state.get(user_id)

            if not state or not state.get("player"):
                await interaction.followup.send("❌ Form state lost. Please start over with `/ban_player`.", ephemeral=True)
                if interaction.message:
                    try: await interaction.message.delete()
                    except discord.HTTPException: pass
                return

            if interaction.message:
                try: await interaction.message.delete()
                except discord.HTTPException: pass
            
            next_view: Optional[discord.ui.View] = None
            content = "Going back..."
            player_data = state["player"]
            offense_data = state.get("offense")
            strike_data = state.get("strike")
            sanction_data = state.get("sanction")
            unban_data_val = state.get("unban_data")

            if self.back_to_step == "player":
                content = "Select a player:"
                players_list = state.get("players", [])
                if not players_list:
                     await interaction.followup.send("Error: Player search data lost.",ephemeral=True); return
                next_view = self.cog_ref.PlayerView(players_list, self.cog_ref)
            elif self.back_to_step == "offense":
                content = "Select offense:"
                next_view = self.cog_ref.OffenseView(player_data, self.cog_ref)
            elif self.back_to_step == "strike" and offense_data:
                content = "Select strike level:"
                next_view = self.cog_ref.StrikeView(player_data, offense_data, self.cog_ref)
            elif self.back_to_step == "transcript_type" and offense_data and strike_data and sanction_data:
                content = "Select transcript type:"
                next_view = self.cog_ref.TranscriptTypeView(player_data, offense_data, strike_data, sanction_data, unban_data_val, self.cog_ref)
            elif self.back_to_step == "transcript_select" and offense_data and strike_data and sanction_data:
                content = "Reselect transcript type (to get transcript options again):"
                next_view = self.cog_ref.TranscriptTypeView(player_data, offense_data, strike_data, sanction_data, unban_data_val, self.cog_ref)
            else:
                await interaction.followup.send(f"Cannot go back to step '{self.back_to_step}'. Restarting form.", ephemeral=True)
                return

            if next_view:
                message = await interaction.followup.send(content=content, view=view, ephemeral=True)
                if hasattr(next_view, 'message'):
                    next_view.message = message
            else:
                 await interaction.followup.send("Error: Could not determine previous step.", ephemeral=True)


    class CancelButton(discord.ui.Button):
        def __init__(self, cog_ref: 'BanCog', row: Optional[int] = None):
            super().__init__(label="Cancel Form", style=discord.ButtonStyle.danger, row=row)
            self.cog_ref = cog_ref

        async def callback(self, interaction: discord.Interaction):
            user_id = interaction.user.id
            if user_id in self.cog_ref.bot.user_form_state:
                del self.cog_ref.bot.user_form_state[user_id]
            
            if interaction.message:
                try: await interaction.message.delete()
                except discord.HTTPException: pass
            
            await interaction.response.send_message("❌ Ban form cancelled.", ephemeral=True)


    def _build_confirmation_preview_text(self, user_id: int, transcript_link_md: str) -> str:
        state = self.bot.user_form_state.get(user_id, {})
        player = state.get("player", {})
        offense = state.get("offense", "N/A")
        strike = state.get("strike", "N/A")
        sanction = state.get("sanction", "N/A")
        unban_data = state.get("unban_data")
        history_note = ""

        # For custom punishments, use the detailed reason
        if strike == "Custom":
            final_offense_text = state.get("offense_detail", offense)
        else:
            final_offense_text = offense

        if unban_data:
            reason_line = f"Unban Details: {final_offense_text}"
            length_line = f"Action: {sanction}"
            related_line = f"\nOriginal Ban #: {unban_data.get('ban_number_to_unban', 'N/A')}"
        else:
            reason_line = f"Verdict/Reason: {final_offense_text}"
            length_line = f"Ban Length: ({strike}) {sanction}"
            related_line = ""
        
        return (
            f"Transcript: {transcript_link_md}\n"
            f"Player: {player.get('Name', 'N/A')}\n"
            f"BUID: {player.get('BohemiaUID', 'N/A')}\n"
            f"{reason_line}\n"
            f"{length_line}{history_note}{related_line}"
        )

    async def _handle_ban_player_search_results(self, interaction: discord.Interaction, players: List[Dict], search_term: str):
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True)

        if not players:
            await interaction.followup.send(f"No players found matching '{search_term}'. Cannot start ban form.", ephemeral=True)
            return

        self.bot.user_form_state[interaction.user.id] = {"players": players, "search_term": search_term}
        embed = discord.Embed(
            title="Ban Process - Step 1: Select Player",
            description=f"Found {len(players)} player(s) matching '{search_term}'. Please select the player you want to process from the dropdown below.",
            color=discord.Color.blue()
        )
        view = self.PlayerView(players, self)
        message = await interaction.followup.send(embed=embed, view=view, ephemeral=True)
        view.message = message


    @app_commands.command(name="ban_player", description="Start the ban or unban process for a player.")
    @app_commands.guild_only()
    async def ban_player_command(self, interaction: discord.Interaction):
        if interaction.user.id in self.bot.user_form_state:
            del self.bot.user_form_state[interaction.user.id]
        self.bot.user_form_state[interaction.user.id] = {}

        modal = PlayerSearchModal(
            player_db_instance=self.bot.player_db,
            on_search_complete=self._handle_ban_player_search_results,
            channel_search_func=search_channels_for_players_fallback
        )
        await interaction.response.send_modal(modal)

async def setup(bot: commands.Bot):
    await bot.add_cog(BanCog(bot))