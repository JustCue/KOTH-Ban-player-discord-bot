import discord
from discord.ext import commands
from discord import app_commands
from typing import Optional

class HelpView(discord.ui.View):
    def __init__(self, bot: commands.Bot):
        super().__init__(timeout=300) # View times out after 5 minutes
        self.bot = bot
        self.message: Optional[discord.Message] = None
        # Add the select menu to the view
        self.add_item(self.HelpSelect(bot=self.bot))

    async def on_timeout(self):
        if self.message:
            try:
                # Disable the view (e.g., grey out the select menu) when it times out
                for item in self.children:
                    item.disabled = True
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass # Message might have been deleted

    class HelpSelect(discord.ui.Select):
        def __init__(self, bot: commands.Bot):
            self.bot = bot
            options = [
                discord.SelectOption(label="Overview", description="Start here! A general overview of the bot.", emoji="ℹ️"),
                discord.SelectOption(label="Ban & Unban Process", description="How to use the main /ban_player command.", emoji="⚖️"),
                discord.SelectOption(label="History & Searching", description="How to look up player and ban history.", emoji="📜"),
                discord.SelectOption(label="Admin & Setup", description="Commands for server administrators.", emoji="⚙️"),
            ]
            super().__init__(placeholder="Choose a category to learn more...", options=options, min_values=1, max_values=1)

        async def callback(self, interaction: discord.Interaction):
            # Defer the interaction to prevent "Interaction failed"
            await interaction.response.defer()
            
            # Get the selected option's label
            selection = self.values[0]
            
            # Create a new embed based on the selection
            embed = self.create_help_embed(selection)
            
            # Edit the original message with the new embed content
            await interaction.edit_original_response(embed=embed)

        def create_help_embed(self, category: str) -> discord.Embed:
            """Creates an embed based on the selected help category."""
            embed = discord.Embed(color=discord.Color.blue())
            
            if category == "Overview":
                embed.title="ℹ️ Bot Overview"
                embed.description = (
                    "Welcome to the Ban Management Bot!\n\n"
                    "This bot is designed to streamline the process of banning players, tracking their history, and managing moderation actions in a fair and consistent way.\n\n"
                    "**Key Features:**\n"
                    "• Step-by-step ban form to ensure all information is captured.\n"
                    "• Moderation queue where all bans must be approved.\n"
                    "• Complete ban/unban history for every player.\n"
                    "• Interactive commands for searching and configuration.\n\n"
                    "Use the dropdown menu below to explore specific command categories."
                )

            elif category == "Ban & Unban Process":
                embed.title="⚖️ Ban & Unban Process"
                embed.description = "The main command for all bans, unbans, and custom punishments is `/ban_player`."
                
                # *** FIX IS HERE: Updated the value with more detail on transcripts ***
                embed.add_field(
                    name="`/ban_player` Workflow",
                    value=(
                        "This command starts an interactive form to create a ban/unban request.\n"
                        "1. **Search:** Provide a player's name.\n"
                        "2. **Select Player:** Choose the correct player from the list.\n"
                        "3. **Select Offense:** Choose a predefined offense, a custom one, or an unban option.\n"
                        "4. **Select Strike/Sanction:** Follow the prompts for punishment details.\n"
                        "5. **Link Transcript:** The bot will ask if this is from a 'Report' or a 'Ticket'. It automatically finds recent `.html` files in channels with 'report' or 'ticket' in their names. You can also select other options like 'Witness' or 'Add Later'.\n"
                        "6. **Submit:** Your request will be posted for moderator approval."
                    ),
                    inline=False
                )
                embed.add_field(
                    name="Special Cases",
                    value=(
                        "• **Custom Punishment:** Allows you to enter a free-form reason and ban length.\n"
                        "• **Unban:** Prompts you to select one of the player's existing bans to reverse."
                    ),
                    inline=False
                )

            elif category == "History & Searching":
                embed.title="📜 History & Searching Commands"
                embed.add_field(name="`/banhistory buid:<BohemiaUID>`", value="Shows the complete, paginated ban history for a specific player.", inline=False)
                embed.add_field(name="`/recentbans [limit]`", value="Displays the most recent ban submissions approved by moderators. Default is 10.", inline=False)
                embed.add_field(name="`/searchban ban_number:<ID>`", value="Looks up and displays the full details for a single ban by its unique Ban ID.", inline=False)
                embed.add_field(name="`/find_player`", value="A utility command to quickly search for a player's BUID by name.", inline=False)

            elif category == "Admin & Setup":
                embed.title="⚙️ Admin & Setup Commands"
                embed.description = "⚠️ **These commands require Administrator permissions.**"
                embed.add_field(name="`/setup roles [add_role] [remove_role]`", value="Manages which roles are considered 'Moderators' who can approve/deny bans.", inline=False)
                embed.add_field(name="`/setup channel channel:<#channel>`", value="Sets the specific channel where new ban requests are posted for review.", inline=False)
                embed.add_field(name="`/setup check`", value="Displays the current configuration and checks if the bot has the required permissions.", inline=False)
                embed.add_field(name="`/delete_ban ban_number:<ID>`", value="Permanently deletes a ban record from the database. This action is irreversible.", inline=False)
            
            embed.set_footer(text=f"Bot Help | Selected: {category}")
            return embed


class HelpCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="help", description="Explains how to use the bot and its commands.")
    async def help_command(self, interaction: discord.Interaction):
        # Create the initial view and embed
        view = HelpView(self.bot)
        # Get the select menu instance from the view to call its method
        select_menu = view.children[0]
        initial_embed = select_menu.create_help_embed("Overview")
        
        # Send the initial message
        await interaction.response.send_message(embed=initial_embed, view=view, ephemeral=True)
        # Store the message in the view for timeout handling
        view.message = await interaction.original_response()

async def setup(bot: commands.Bot):
    await bot.add_cog(HelpCog(bot))