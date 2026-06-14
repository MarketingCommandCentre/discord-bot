"""
Request command cog for handling marketing request creation and management.
"""

from datetime import datetime
import discord
from discord.ext import commands
from discord import app_commands

from src.ui.modals import BaseRequestModal
from src.ui.views import RequestView
from src.model.Models import Request
from src.services.request_manager import RequestManager

class RequestCog(commands.Cog):
    """Cog for handling marketing request commands."""

    def __init__(self, bot, request_manager: RequestManager = None):
        self.bot = bot
        self.request_manager = request_manager

    @app_commands.command(
        name="setup-requests",
        description="Post the permanent Marketing Request Centre message with request buttons (admin only)"
    )
    @app_commands.describe(
        channel="The channel to post the request board in (defaults to the current channel)"
    )
    async def setup_requests(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel = None
    ):
        """Post a permanent message with buttons that let any user create a request."""
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message(
                "❌ You need the Manage Server permission to use this command.",
                ephemeral=True
            )
            return

        target_channel = channel or interaction.channel

        embed = discord.Embed(
            title="📢 Marketing Request Centre",
            description=(
                "Use the buttons below to create a marketing request. "
                "A dedicated channel will be created for your request where the "
                "team can collaborate with you.\n\n"
                "📸 **Create Post Request** — for static posts, graphics, and announcements.\n"
                "📽️ **Create Reel Request** — for short-form video / reels content."
            ),
            color=0x5865F2
        )
        embed.set_footer(text="Click a button to open the request form.")

        try:
            await target_channel.send(embed=embed, view=RequestView(self.request_manager))
            await interaction.response.send_message(
                f"✅ Marketing Request Centre posted in {target_channel.mention}.",
                ephemeral=True
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                f"❌ I don't have permission to send messages in {target_channel.mention}.",
                ephemeral=True
            )
        except Exception as e:
            await interaction.response.send_message(
                f"❌ An error occurred: {str(e)}",
                ephemeral=True
            )

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

    @app_commands.command(
        name="add",
        description="Add a user or role to the additional assignees for this request"
    )
    @app_commands.describe(
        user="The user to add as an additional assignee (optional if role is provided)",
        role="The role whose members should be added as additional assignees (optional if user is provided)"
    )
    async def add_assignee(
        self, 
        interaction: discord.Interaction, 
        user: discord.Member = None,
        role: discord.Role = None
    ):
        """Add a user or all members of a role to the additional assignees."""
        try:
            # Check if this is a request channel
            request = await self.request_manager.get_request(interaction.channel.id)
            if not request:
                await interaction.response.send_message(
                    "❌ This channel is not associated with any request.",
                    ephemeral=True
                )
                return
            
            # Validate input: either user or role must be provided
            if not user and not role:
                await interaction.response.send_message(
                    "❌ You must specify either a user or a role to add.",
                    ephemeral=True
                )
                return
            
            # Get the additional assignee role
            if not request.additional_assignee_id:
                await interaction.response.send_message(
                    "❌ This request does not have an additional assignee role configured.",
                    ephemeral=True
                )
                return
            
            additional_role = interaction.guild.get_role(request.additional_assignee_id)
            if not additional_role:
                await interaction.response.send_message(
                    "❌ Could not find the additional assignee role for this request.",
                    ephemeral=True
                )
                return
            
            # Add user(s) to the additional assignee role
            members_added = []
            
            if user:
                # Add the specific user
                await user.add_roles(additional_role, reason=f"Added as additional assignee by {interaction.user}")
                members_added.append(user.mention)
            
            if role:
                # Add all members of the role
                for member in role.members:
                    if additional_role not in member.roles:
                        await member.add_roles(additional_role, reason=f"Added as additional assignee by {interaction.user}")
                        members_added.append(member.mention)
            
            # Send confirmation message
            if members_added:
                members_list = ", ".join(members_added)
                await interaction.response.send_message(
                    f"✅ Added {len(members_added)} member(s) to additional assignees: {members_list}",
                    ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    "⚠️ No new members were added. They may already be additional assignees.",
                    ephemeral=True
                )
                
        except Exception as e:
            await interaction.response.send_message(
                f"❌ An error occurred: {str(e)}",
                ephemeral=True
            )

    @app_commands.command(
        name="split",
        description="Fork the current request into a new separate request"
    )
    async def split_task(self, interaction: discord.Interaction):
        """Create a fork/copy of the current request as a new request."""
        try:
            # Check if this is a request channel
            original_request = await self.request_manager.get_request(interaction.channel.id)
            if not original_request:
                await interaction.response.send_message(
                    "❌ This channel is not associated with any request.",
                    ephemeral=True
                )
                return
            
            # Defer the response as this operation might take time
            await interaction.response.defer(ephemeral=True)
            
            # Create a new request with the same properties
            from copy import deepcopy
            new_request = deepcopy(original_request)
            
            # Reset fields that should be unique
            new_request.channel_id = None
            new_request.main_message_id = None
            new_request.additional_assignee_id = None
            new_request.created_at = None
            new_request.updated_at = None
            
            # Append "(Split)" to the title to distinguish it
            new_request.title = f"{new_request.title} (Split)"
            
            # Create the new request
            created_request = await self.request_manager.create_request(new_request, interaction.guild)
            
            if created_request:
                # Copy members from original additional assignee role to the new one
                if original_request.additional_assignee_id and created_request.additional_assignee_id:
                    original_role = interaction.guild.get_role(original_request.additional_assignee_id)
                    new_role = interaction.guild.get_role(created_request.additional_assignee_id)
                    
                    if original_role and new_role:
                        for member in original_role.members:
                            await member.add_roles(new_role, reason=f"Copied from split request")
                
                await interaction.followup.send(
                    f"✅ Request successfully split! New request created: <#{created_request.channel_id}>",
                    ephemeral=True
                )
            else:
                await interaction.followup.send(
                    "❌ Failed to split request. Please try again.",
                    ephemeral=True
                )
                
        except Exception as e:
            await interaction.followup.send(
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