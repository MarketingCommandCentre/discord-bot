"""
Story request cog: pings a configured set of roles whenever a new thread is
opened in the story requests forum channel.

Configuration lives under the top-level "story_requests" key in settings.json
and can be managed at runtime with the /story-requests command group.
"""

import logging
from collections import OrderedDict
from typing import List

import discord
from discord import app_commands
from discord.ext import commands

from src.config.manager import (
    get_story_request_forum_channel_id,
    get_story_request_ping_role_ids,
    is_story_request_ping_enabled,
    set_story_request_forum_channel_id,
    set_story_request_ping_enabled,
    set_story_request_ping_role_ids,
)

logger = logging.getLogger(__name__)

# THREAD_CREATE is also dispatched when the bot merely gains access to a thread
# that already existed, so anything older than this is treated as "not new".
MAX_THREAD_AGE_SECONDS = 300

# Thread IDs remembered to make the ping idempotent if the gateway redelivers
# THREAD_CREATE. Bounded so a long-lived bot doesn't grow this without limit.
PINGED_THREAD_CACHE_SIZE = 500


class StoryRequestCog(commands.Cog):
    """Pings roles on new threads in the story requests forum, and exposes the
    admin commands that configure which channel and roles those are."""

    story_requests = app_commands.Group(
        name="story-requests",
        description="Configure the story requests forum ping",
        guild_only=True,
        default_permissions=discord.Permissions(manage_guild=True),
    )

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Used as an ordered set; the values are unused.
        self._pinged_threads: "OrderedDict[int, None]" = OrderedDict()

    # ---- Listener ----
    @commands.Cog.listener()
    async def on_thread_create(self, thread: discord.Thread):
        """Ping the configured roles once, in the thread, when a story request
        thread is opened."""
        try:
            if not is_story_request_ping_enabled():
                return

            forum_channel_id = get_story_request_forum_channel_id()
            if forum_channel_id is None or thread.parent_id != forum_channel_id:
                return

            age = (discord.utils.utcnow() - thread.created_at).total_seconds()
            if age > MAX_THREAD_AGE_SECONDS:
                logger.debug(
                    f"Skipping story request ping for thread {thread.id}: "
                    f"{age:.0f}s old, not a new thread"
                )
                return

            role_ids = get_story_request_ping_role_ids()
            if not role_ids:
                logger.warning(
                    f"New story request thread {thread.id} but no ping roles are "
                    f"configured - use /story-requests role-add"
                )
                return

            # Claim the thread before sending so a redelivered event can't double
            # ping. A failed send is not retried, which is the safer direction.
            if self._claim_thread(thread.id):
                return

            await self._send_ping(thread, role_ids)

        except Exception as e:
            logger.error(f"Error handling story request thread create: {e}", exc_info=True)

    def _claim_thread(self, thread_id: int) -> bool:
        """Record a thread as pinged. Returns True if it was already claimed."""
        if thread_id in self._pinged_threads:
            return True
        self._pinged_threads[thread_id] = None
        while len(self._pinged_threads) > PINGED_THREAD_CACHE_SIZE:
            self._pinged_threads.popitem(last=False)
        return False

    async def _send_ping(self, thread: discord.Thread, role_ids: List[int]):
        """Send the single, embed-less ping message into the thread."""
        content = " ".join(f"<@&{role_id}>" for role_id in role_ids)
        # Scope allowed mentions to exactly the configured roles so a future
        # change to the message body can't broaden who gets notified.
        allowed_mentions = discord.AllowedMentions(
            everyone=False,
            users=False,
            roles=[discord.Object(id=role_id) for role_id in role_ids],
        )

        try:
            await thread.send(content, allowed_mentions=allowed_mentions)
            logger.info(
                f"Pinged {len(role_ids)} role(s) in story request thread "
                f"'{thread.name}' ({thread.id})"
            )
        except discord.Forbidden:
            logger.error(
                f"Missing permissions to ping in story request thread {thread.id}. "
                f"The bot needs Send Messages in Threads, and either mentionable "
                f"roles or the Mention @everyone, @here and All Roles permission."
            )
        except discord.HTTPException as e:
            logger.error(f"Failed to send story request ping in thread {thread.id}: {e}")

    # ---- Commands ----
    @staticmethod
    async def _reject_without_manage_guild(interaction: discord.Interaction) -> bool:
        """Send an error and return True when the caller lacks Manage Server.
        default_permissions hides the commands, but server owners can re-grant
        them, so the check is repeated here."""
        if interaction.user.guild_permissions.manage_guild:
            return False
        await interaction.response.send_message(
            "❌ You need Manage Server permission.", ephemeral=True
        )
        return True

    @story_requests.command(name="channel", description="Set the story requests forum channel")
    @app_commands.describe(channel="Forum channel whose new threads trigger the ping")
    async def set_channel(self, interaction: discord.Interaction, channel: discord.ForumChannel):
        if await self._reject_without_manage_guild(interaction):
            return
        if not set_story_request_forum_channel_id(channel.id):
            await interaction.response.send_message(
                "❌ Failed to save configuration — check the bot logs.", ephemeral=True
            )
            return

        message = f"✅ Story requests forum set to {channel.mention}."
        if not get_story_request_ping_role_ids():
            message += "\n⚠️ No ping roles configured yet — add one with `/story-requests role-add`."
        await interaction.response.send_message(
            message, ephemeral=True, allowed_mentions=discord.AllowedMentions.none()
        )

    @story_requests.command(name="role-add", description="Add a role to ping on new story requests")
    @app_commands.describe(role="Role to ping when a story request thread is opened")
    async def role_add(self, interaction: discord.Interaction, role: discord.Role):
        if await self._reject_without_manage_guild(interaction):
            return

        role_ids = get_story_request_ping_role_ids()
        if role.id in role_ids:
            await interaction.response.send_message(
                f"ℹ️ **{role.name}** is already on the ping list.",
                ephemeral=True,
                allowed_mentions=discord.AllowedMentions.none(),
            )
            return

        role_ids.append(role.id)
        if not set_story_request_ping_role_ids(role_ids):
            await interaction.response.send_message(
                "❌ Failed to save configuration — check the bot logs.", ephemeral=True
            )
            return

        message = f"✅ Added **{role.name}** to the story request ping list."
        if not role.mentionable and not interaction.guild.me.guild_permissions.mention_everyone:
            message += (
                f"\n⚠️ **{role.name}** isn't mentionable and the bot lacks the "
                f"Mention @everyone, @here and All Roles permission, so the ping "
                f"won't notify anyone. Fix either one."
            )
        await interaction.response.send_message(
            message, ephemeral=True, allowed_mentions=discord.AllowedMentions.none()
        )

    @story_requests.command(name="role-remove", description="Remove a role from the story request ping")
    @app_commands.describe(role="Role to stop pinging")
    async def role_remove(self, interaction: discord.Interaction, role: discord.Role):
        if await self._reject_without_manage_guild(interaction):
            return

        role_ids = get_story_request_ping_role_ids()
        if role.id not in role_ids:
            await interaction.response.send_message(
                f"ℹ️ **{role.name}** isn't on the ping list.",
                ephemeral=True,
                allowed_mentions=discord.AllowedMentions.none(),
            )
            return

        role_ids.remove(role.id)
        if not set_story_request_ping_role_ids(role_ids):
            await interaction.response.send_message(
                "❌ Failed to save configuration — check the bot logs.", ephemeral=True
            )
            return

        await interaction.response.send_message(
            f"✅ Removed **{role.name}** from the story request ping list.",
            ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @story_requests.command(name="toggle", description="Turn story request pings on or off")
    @app_commands.describe(enabled="Whether new story request threads should be pinged")
    async def toggle(self, interaction: discord.Interaction, enabled: bool):
        if await self._reject_without_manage_guild(interaction):
            return
        if not set_story_request_ping_enabled(enabled):
            await interaction.response.send_message(
                "❌ Failed to save configuration — check the bot logs.", ephemeral=True
            )
            return
        state = "enabled" if enabled else "disabled"
        await interaction.response.send_message(
            f"✅ Story request pings **{state}**.", ephemeral=True
        )

    @story_requests.command(name="show", description="Show the current story request ping configuration")
    async def show(self, interaction: discord.Interaction):
        forum_channel_id = get_story_request_forum_channel_id()
        role_ids = get_story_request_ping_role_ids()

        if forum_channel_id is None:
            channel_line = "(not set)"
        else:
            channel = interaction.guild.get_channel(forum_channel_id)
            channel_line = (
                channel.mention if channel
                else f"`{forum_channel_id}` (not found in this server)"
            )

        roles_line = ", ".join(f"<@&{r}>" for r in role_ids) if role_ids else "(none)"
        status = "enabled" if is_story_request_ping_enabled() else "disabled"

        await interaction.response.send_message(
            f"**Story request pings** — {status}\n"
            f"• Forum: {channel_line}\n"
            f"• Roles: {roles_line}",
            ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none(),
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(StoryRequestCog(bot))
