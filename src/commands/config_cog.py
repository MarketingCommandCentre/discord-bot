"""
Configuration management cog: allows admins to create/remove departments and sub-departments.
"""

import discord
from discord.ext import commands
from discord import app_commands
from typing import Optional

from src.config.manager import (
    create_department,
    create_subdepartment,
    delete_department,
    delete_subdepartment,
    config
)

async def get_or_create_role(guild: discord.Guild, display_name: str) -> tuple[discord.Role, bool]:
    """Link an existing role by name or create a new one. Returns (role, created).

    Raises discord.Forbidden if the bot cannot create roles.
    """
    lowered = display_name.lower()
    for existing in guild.roles:
        if not existing.is_default() and existing.name.lower() == lowered:
            return existing, False
    role = await guild.create_role(name=display_name, reason="CommandCentre department setup")
    return role, True


class ConfigCog(commands.Cog):
    """Admin configuration commands for departments and sub-departments."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ---- Department Commands ----
    @app_commands.command(name="dept-add", description="Add a new department (admin only)")
    @app_commands.describe(key="Unique key (e.g. marketing)", display_name="Human readable name", role="Existing role to link or leave empty")
    async def dept_add(self, interaction: discord.Interaction, key: str, display_name: str, role: Optional[discord.Role] = None):
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("❌ You need Manage Server permission.", ephemeral=True)
            return
        if not create_department(key, display_name):
            await interaction.response.send_message(f"❌ Department key '{key}' already exists.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        # Link the role that was passed in, otherwise reuse a same-named role or create one.
        created_role = False
        if role is None:
            try:
                role, created_role = await get_or_create_role(interaction.guild, display_name)
            except discord.Forbidden:
                await interaction.followup.send(
                    f"⚠️ Department '{display_name}' created (key: {key}), but I lack the **Manage Roles** "
                    f"permission to create its role. Re-run `/dept-add` with a `role` argument to link one.",
                    ephemeral=True,
                )
                return

        config.set_nested("departments", key, "role_id", value=role.id)
        config.set_nested("departments", key, "role_name", value=role.name)
        config.save_config()

        action = "created" if created_role else "linked"
        await interaction.followup.send(
            f"✅ Department '{display_name}' created (key: {key}) — role <@&{role.id}> {action}.",
            ephemeral=True,
        )

    @app_commands.command(name="dept-remove", description="Remove a department (and its sub-departments)")
    @app_commands.describe(key="Department key to remove")
    async def dept_remove(self, interaction: discord.Interaction, key: str):
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("❌ You need Manage Server permission.", ephemeral=True)
            return
        if delete_department(key):
            await interaction.response.send_message(f"✅ Department '{key}' removed.", ephemeral=True)
        else:
            await interaction.response.send_message(f"❌ Department '{key}' not found.", ephemeral=True)

    @app_commands.command(name="dept-list", description="List departments")
    async def dept_list(self, interaction: discord.Interaction):
        departments = config.get("departments", {})
        if not departments:
            await interaction.response.send_message("No departments configured.", ephemeral=True)
            return
        lines = []
        for k, v in departments.items():
            role_id = v.get("role_id")
            role_str = f"<@&{role_id}>" if role_id else "(no role)"
            lines.append(f"• {k} — {v.get('name')} {role_str}")
        msg = "**Departments:**\n" + "\n".join(lines)
        await interaction.response.send_message(msg, ephemeral=True)

    # ---- Sub-department Commands ----
    @app_commands.command(name="subdept-add", description="Add a new sub-department under a department")
    @app_commands.describe(department_key="Parent department key", subgroup_key="Unique subgroup key", display_name="Human readable name", role="Existing role to link or leave empty")
    async def subdept_add(self, interaction: discord.Interaction, department_key: str, subgroup_key: str, display_name: str, role: Optional[discord.Role] = None):
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("❌ You need Manage Server permission.", ephemeral=True)
            return
        if not create_subdepartment(department_key, subgroup_key, display_name):
            await interaction.response.send_message("❌ Could not create sub-department (parent missing or key exists).", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        created_role = False
        if role is None:
            try:
                role, created_role = await get_or_create_role(interaction.guild, display_name)
            except discord.Forbidden:
                await interaction.followup.send(
                    f"⚠️ Sub-department '{display_name}' created under '{department_key}', but I lack the "
                    f"**Manage Roles** permission to create its role. Re-run `/subdept-add` with a `role` "
                    f"argument to link one.",
                    ephemeral=True,
                )
                return

        # Persist role id
        subgroups = config.get("department_subgroups", {})
        dept_subgroups = subgroups.get(department_key, {})
        if subgroup_key in dept_subgroups:
            dept_subgroups[subgroup_key]["role_id"] = role.id
            dept_subgroups[subgroup_key]["role_name"] = role.name
            config.set_nested("department_subgroups", department_key, value=dept_subgroups)
            config.save_config()

        action = "created" if created_role else "linked"
        await interaction.followup.send(
            f"✅ Sub-department '{display_name}' created under '{department_key}' — role <@&{role.id}> {action}.",
            ephemeral=True,
        )

    @app_commands.command(name="subdept-remove", description="Remove a sub-department")
    @app_commands.describe(department_key="Parent department key", subgroup_key="Sub-department key")
    async def subdept_remove(self, interaction: discord.Interaction, department_key: str, subgroup_key: str):
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("❌ You need Manage Server permission.", ephemeral=True)
            return
        if delete_subdepartment(department_key, subgroup_key):
            await interaction.response.send_message(f"✅ Sub-department '{subgroup_key}' removed from '{department_key}'.", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Sub-department not found.", ephemeral=True)

    @app_commands.command(name="subdept-list", description="List sub-departments for a department")
    @app_commands.describe(department_key="Parent department key")
    async def subdept_list(self, interaction: discord.Interaction, department_key: str):
        subgroups = config.get("department_subgroups", {})
        dept_subgroups = subgroups.get(department_key, {})
        if not dept_subgroups:
            await interaction.response.send_message(f"No sub-departments for '{department_key}'.", ephemeral=True)
            return
        lines = []
        for k, v in dept_subgroups.items():
            role_id = v.get("role_id")
            role_str = f"<@&{role_id}>" if role_id else "(no role)"
            lines.append(f"• {k} — {v.get('name')} {role_str}")
        msg = f"**Sub-departments of {department_key}:**\n" + "\n".join(lines)
        await interaction.response.send_message(msg, ephemeral=True)

async def setup(bot):
    await bot.add_cog(ConfigCog(bot))
