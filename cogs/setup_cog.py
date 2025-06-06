import discord
from discord.ext import commands
from discord import app_commands
from typing import Optional

# Import our new config manager
from utils import config_manager

class SetupCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # Create a command group for /setup
    setup_group = app_commands.Group(name="setup", description="Configure bot settings (Admin only)")

    @setup_group.command(name="roles", description="Set or view roles that can manage bans.")
    @app_commands.describe(add_role="Admin role to Approve bans.", remove_role="Remove Admin Role.")
    @app_commands.checks.has_permissions(administrator=True)
    async def setup_roles(self, interaction: discord.Interaction, add_role: Optional[discord.Role] = None, remove_role: Optional[discord.Role] = None):
        """Adds or removes a moderator role."""
        if not add_role and not remove_role:
            # If no options given, show current config
            current_roles = [f"<@&{role_id}>" for role_id in self.bot.config.get("moderator_roles", [])]
            role_list = "\n".join(current_roles) if current_roles else "No moderator roles set."
            await interaction.response.send_message(f"**Current Moderator Roles:**\n{role_list}", ephemeral=True)
            return

        # Add a role
        if add_role:
            if add_role.id not in self.bot.config["moderator_roles"]:
                self.bot.config["moderator_roles"].append(add_role.id)
                config_manager.save_config(self.bot.config)
                await interaction.response.send_message(f"✅ Role {add_role.mention} has been added as a Moderator.", ephemeral=True)
            else:
                await interaction.response.send_message(f"⚠️ Role {add_role.mention} is already a Moderator.", ephemeral=True)
            return

        # Remove a role
        if remove_role:
            if remove_role.id in self.bot.config["moderator_roles"]:
                self.bot.config["moderator_roles"].remove(remove_role.id)
                config_manager.save_config(self.bot.config)
                await interaction.response.send_message(f"🗑️ Role {remove_role.mention} has been removed as a Moderator.", ephemeral=True)
            else:
                await interaction.response.send_message(f"⚠️ Role {remove_role.mention} was not a Moderator.", ephemeral=True)
            return

    @setup_group.command(name="channel", description="Set the channel for pending ban requests.")
    @app_commands.describe(channel="The text channel where new ban requests will be posted for review.")
    @app_commands.checks.has_permissions(administrator=True)
    async def setup_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        """Sets the channel for pending ban requests."""
        self.bot.config["channels"]["pending_bans"] = channel.id
        config_manager.save_config(self.bot.config)
        await interaction.response.send_message(f"✅ Pending ban requests will now be sent to {channel.mention}.", ephemeral=True)

    @setup_group.command(name="check", description="Check the current bot configuration and permissions.")
    @app_commands.checks.has_permissions(administrator=True)
    async def setup_check(self, interaction: discord.Interaction):
        """Checks and displays the current configuration."""
        await interaction.response.defer(ephemeral=True)

        # Moderator Roles
        current_roles = [f"<@&{role_id}>" for role_id in self.bot.config.get("moderator_roles", [])]
        role_list = "\n".join(current_roles) if current_roles else "None set. Use `/setup roles`."

        # Pending Bans Channel
        pending_channel_id = self.bot.config.get("channels", {}).get("pending_bans")
        pending_channel_text = f"<#{pending_channel_id}>" if pending_channel_id else "None set. Defaults to current channel."
        
        # Check permissions in the pending channel
        perms_status = "Not set."
        if pending_channel_id and interaction.guild:
            target_channel = interaction.guild.get_channel(pending_channel_id)
            if target_channel:
                perms = target_channel.permissions_for(interaction.guild.me)
                if perms.send_messages and perms.embed_links:
                    perms_status = "✅ OK"
                else:
                    perms_status = "❌ **Missing Permissions!** (Need Send Messages & Embed Links)"
            else:
                perms_status = "⚠️ Channel not found."
        
        embed = discord.Embed(title="Bot Configuration Status", color=discord.Color.blue())
        embed.add_field(name="Moderator Roles", value=role_list, inline=False)
        embed.add_field(name="Pending Bans Channel", value=pending_channel_text, inline=False)
        embed.add_field(name="Channel Permissions Check", value=perms_status, inline=False)

        await interaction.followup.send(embed=embed, ephemeral=True)

    @setup_check.error
    @setup_roles.error
    @setup_channel.error
    async def on_setup_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message("❌ You must be an Administrator to use setup commands.", ephemeral=True)
        else:
            await interaction.response.send_message(f"An unexpected error occurred: {error}", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(SetupCog(bot))