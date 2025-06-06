# utils/permissions_utils.py
import discord
from typing import List, Union

def is_moderator(interaction: discord.Interaction, moderator_roles_config: List[Union[str, int]]) -> bool:
    """
    Checks if the interacting user has one of the moderator roles.
    moderator_roles_config can be a list of role names (str) or role IDs (int).
    """
    if not interaction.guild or not hasattr(interaction, 'user') or not hasattr(interaction.user, 'roles'):
        # This case handles scenarios where interaction might not be fully formed,
        # or user is not part of a guild (e.g., DM interaction if that were possible here).
        return False

    user_roles = interaction.user.roles
    for config_role_identifier in moderator_roles_config:
        if isinstance(config_role_identifier, str): # Check by name (case-sensitive)
            if any(user_role.name == config_role_identifier for user_role in user_roles):
                return True
        elif isinstance(config_role_identifier, int): # Check by ID
            if any(user_role.id == config_role_identifier for user_role in user_roles):
                return True
    return False