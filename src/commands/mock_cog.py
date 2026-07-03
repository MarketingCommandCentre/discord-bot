"""
Mock request command cog.

Provides an admin-only /mock command that uses Claude Haiku to invent realistic
form content and then creates each request end-to-end through RequestManager —
the exact same path a real form submission takes (Discord channel, assignee role,
pinned message, and backend persistence). Intended for populating a training
environment with believable data.
"""

import os
import logging

import discord
from discord.ext import commands
from discord import app_commands

from src.model.Models import RequestStatus
from src.services.request_manager import RequestManager
from src.services.mock_request_generator import MockRequestGenerator

logger = logging.getLogger(__name__)


class MockCog(commands.Cog):
    """Cog for generating mock marketing requests via the Anthropic API."""

    def __init__(self, bot, request_manager: RequestManager = None):
        self.bot = bot
        self.request_manager = request_manager

    @app_commands.command(
        name="mock",
        description="Generate mock marketing requests with Claude Haiku and create them end-to-end",
    )
    @app_commands.describe(
        count="How many mock requests to create (1-10)",
        theme="Optional theme/context to focus the mock data around",
    )
    async def mock(
        self,
        interaction: discord.Interaction,
        count: app_commands.Range[int, 1, 10] = 3,
        theme: str = None,
    ):
        """Create ``count`` mock requests, one at a time, as if submitted via the form."""
        # Admin gate, consistent with the other management commands.
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message(
                "❌ You need Manage Server permission.", ephemeral=True
            )
            return

        if not os.getenv("ANTHROPIC_API_KEY"):
            await interaction.response.send_message(
                "❌ ANTHROPIC_API_KEY is not configured in the environment.",
                ephemeral=True,
            )
            return

        # Generation + sequential channel creation can take a while — defer.
        await interaction.response.defer(ephemeral=True, thinking=True)

        try:
            generator = MockRequestGenerator()
            requests = await generator.generate_requests(count, theme=theme)
        except Exception as e:
            logger.error(f"Error generating mock requests: {e}")
            await interaction.followup.send(
                f"❌ Failed to generate mock requests: {str(e)}", ephemeral=True
            )
            return

        created_links = []
        failed = 0

        # Create each request end-to-end, one at a time, mirroring a form submit:
        # requester is the invoking user, status stays IN_QUEUE, no assignee.
        for request in requests:
            request.requester_id = interaction.user.id
            request.status = RequestStatus.IN_QUEUE
            request.assigned_to_id = None
            try:
                created_request = await self.request_manager.create_request(
                    request, interaction.guild, acting_user_id=interaction.user.id
                )
                if created_request and created_request.channel_id:
                    created_links.append(f"<#{created_request.channel_id}>")
                else:
                    failed += 1
            except Exception as e:
                failed += 1
                logger.error(f"Error creating mock request '{request.title}': {e}")

        # Report the outcome.
        lines = [f"✅ Created {len(created_links)} mock request(s)."]
        if created_links:
            lines.append(" ".join(created_links))
        if failed:
            lines.append(
                f"⚠️ {failed} request(s) failed to create — check that you have a "
                "department role and that the bot is configured correctly (see logs)."
            )
        await interaction.followup.send("\n".join(lines), ephemeral=True)


async def setup(bot):
    """Setup function to add the cog to the bot."""
    await bot.add_cog(MockCog(bot, request_manager=bot.request_manager))
