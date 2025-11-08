"""
Request command cog for handling marketing request creation and management.
"""

from datetime import datetime
import discord
from discord.ext import commands
from discord import app_commands

from src.ui.modals import BaseRequestModal
from src.model.Models import Request
from src.services.request_manager import RequestManager

class RequestCog(commands.Cog):
    """Cog for handling marketing request commands."""
    
    def __init__(self, bot, request_manager: RequestManager = None):
        self.bot = bot
        self.request_manager = request_manager
    
    @app_commands.command(
        name="request",
        description="Create a new marketing request"
    )
    async def create_request(self, interaction: discord.Interaction):
        """
        Slash command to create a new marketing request.
        Opens the BaseRequestModal for the user to fill out.
        """
        modal = BaseRequestModal(
            title="Create Marketing Request", 
            request_manager=self.request_manager,
            guild=interaction.guild
        )

        await interaction.response.send_modal(modal)

    @app_commands.command(
        name="advance",
        description="Advance the status of a request to the next stage"
    )
    async def advance_request(self, interaction: discord.Interaction):
        try:
            request = await self.request_manager.get_request(interaction.channel.id)
            if not request:
                await interaction.response.send_message(
                    "❌ This channel is not associated with any request.",
                    ephemeral=True
                )
                return
            request = await self.request_manager.advance_request_status(interaction.channel.id)
            await interaction.response.send_message(
                f"✅ Request status advanced to {request.status.value}.",
                ephemeral=True
            )
        except Exception as e:
            await interaction.response.send_message(
                f"❌ An error occurred: {str(e)}",
                ephemeral=True
            )

    @app_commands.command(
        name="assign",
        description="Assign a request to a user"
    )
    @app_commands.describe(user="The user to assign this request to")
    async def assign_request(self, interaction: discord.Interaction, user: discord.Member):
        """Assign a request to a specific user."""
        try:
            # Check if this is a request channel
            request = await self.request_manager.get_request(interaction.channel.id)
            if not request:
                await interaction.response.send_message(
                    "❌ This channel is not associated with any request.",
                    ephemeral=True
                )
                return
            
            # Assign the request
            updated_request = await self.request_manager.assign_request(interaction.channel.id, user.id)
            if updated_request:
                await interaction.response.send_message(
                    f"✅ Request assigned to {user.mention}",
                    ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    "❌ Failed to assign request. Please try again.",
                    ephemeral=True
                )
        except Exception as e:
            await interaction.response.send_message(
                f"❌ An error occurred: {str(e)}",
                ephemeral=True
            )

    @commands.Cog.listener()
    async def on_guild_channel_update(self, before: discord.abc.GuildChannel, after: discord.abc.GuildChannel):
        """Listen for channel category changes and sync with database."""
        # Only process text channels
        if not isinstance(after, discord.TextChannel):
            return
        
        # Check if category changed
        if before.category_id == after.category_id:
            return
        
        # Check if this is a request channel
        request = await self.request_manager.get_request(after.id)
        if not request:
            return
        
        # Update request status based on new category
        await self.request_manager.sync_status_from_category(after.id, after.category_id)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        """Listen for channel deletion and remove from database."""
        # Only process text channels
        if not isinstance(channel, discord.TextChannel):
            return
        
        # Check if this is a request channel
        request = await self.request_manager.get_request(channel.id)
        if not request:
            return
        
        # Delete from database
        try:
            success = await self.request_manager.db.delete_request(channel.id)
            if success:
                print(f"✅ Removed deleted channel {channel.id} from database")
            else:
                print(f"⚠️ Failed to remove channel {channel.id} from database")
        except Exception as e:
            print(f"❌ Error removing channel {channel.id} from database: {e}")

    


async def setup(bot):
    """Setup function to add the cog to the bot."""
    await bot.add_cog(RequestCog(bot))