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
            request = await self.request_manager.advance_request_status(interaction.channel.id, acting_user_id=interaction.user.id)
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
            updated_request = await self.request_manager.assign_request(interaction.channel.id, user.id, acting_user_id=interaction.user.id)
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
            
            # Build the list of target members and add them via the manager,
            # which handles both the Discord role change and the audit log.
            targets = [user] if user else list(role.members)
            via = "user" if user else "role"
            members_added = await self.request_manager.add_additional_assignees(
                interaction.channel.id,
                additional_role,
                targets,
                acting_user_id=interaction.user.id,
                via=via,
            )

            # Send confirmation message
            if members_added:
                members_list = ", ".join(m.mention for m in members_added)
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
        name="remove",
        description="Remove a user or role from the additional assignees for this request"
    )
    @app_commands.describe(
        user="The user to remove from additional assignees (optional if role is provided)",
        role="The role whose members should be removed from additional assignees (optional if user is provided)"
    )
    async def remove_assignee(
        self,
        interaction: discord.Interaction,
        user: discord.Member = None,
        role: discord.Role = None
    ):
        """Remove a user or all members of a role from the additional assignees."""
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
                    "❌ You must specify either a user or a role to remove.",
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

            # Build the list of target members and remove them via the manager,
            # which handles both the Discord role change and the audit log.
            targets = [user] if user else list(role.members)
            via = "user" if user else "role"
            members_removed = await self.request_manager.remove_additional_assignees(
                interaction.channel.id,
                additional_role,
                targets,
                acting_user_id=interaction.user.id,
                via=via,
            )

            # Send confirmation message
            if members_removed:
                members_list = ", ".join(m.mention for m in members_removed)
                await interaction.response.send_message(
                    f"✅ Removed {len(members_removed)} member(s) from additional assignees: {members_list}",
                    ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    "⚠️ No members were removed. They may not have been additional assignees.",
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
            created_request = await self.request_manager.create_request(new_request, interaction.guild, acting_user_id=interaction.user.id)
            
            if created_request:
                # Record the split itself against the original request.
                await self.request_manager.log_channel_action(
                    "REQUEST_SPLIT",
                    original_request.channel_id,
                    f"Request split into new request (channel {created_request.channel_id})",
                    metadata={"newChannelId": str(created_request.channel_id)},
                    acting_user_id=interaction.user.id,
                )

                # Copy members from original additional assignee role to the new one.
                # The manager logs an ASSIGNEE_ADD against the new request for the copied members.
                if original_request.additional_assignee_id and created_request.additional_assignee_id:
                    original_role = interaction.guild.get_role(original_request.additional_assignee_id)
                    new_role = interaction.guild.get_role(created_request.additional_assignee_id)

                    if original_role and new_role:
                        await self.request_manager.add_additional_assignees(
                            created_request.channel_id,
                            new_role,
                            list(original_role.members),
                            acting_user_id=interaction.user.id,
                            via="split",
                        )

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

        # Figure out who dragged the channel from the guild audit log. If the bot
        # itself moved it (e.g. via /advance), the originating command already
        # logged the status change — skip here to avoid a duplicate, bot-attributed entry.
        actor_id = await self._resolve_channel_move_actor(after)
        if actor_id is not None and self.bot.user and actor_id == self.bot.user.id:
            return

        # Update request status based on new category, attributed to the dragging user
        # (falls back to bot attribution when the actor can't be resolved).
        await self.request_manager.sync_status_from_category(
            after.id, after.category_id, acting_user_id=actor_id
        )

    async def _resolve_channel_move_actor(self, channel: discord.TextChannel):
        """Return the user id that most recently moved ``channel`` between categories,
        read from the guild audit log. Returns ``None`` when it can't be determined
        (e.g. the bot lacks View Audit Log, or no recent matching entry)."""
        try:
            async for entry in channel.guild.audit_logs(
                limit=5, action=discord.AuditLogAction.channel_update
            ):
                target = entry.target
                if target is None or target.id != channel.id:
                    continue
                # Only trust a freshly created entry so we don't attribute an old edit.
                if (discord.utils.utcnow() - entry.created_at).total_seconds() > 10:
                    continue
                return entry.user.id if entry.user else None
        except discord.Forbidden:
            # Bot lacks View Audit Log permission — fall back to bot attribution.
            return None
        except Exception as e:
            print(f"⚠️ Could not resolve channel move actor for {channel.id}: {e}")
            return None
        return None

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