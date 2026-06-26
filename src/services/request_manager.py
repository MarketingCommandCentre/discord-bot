"""
Request management service that handles both database operations and Discord server state.
"""

from functools import lru_cache
import re
import discord
from discord.ext import commands
from typing import Optional, List, Dict, Iterable
import logging

from datetime import datetime, date

from src.client.database_client import DatabaseClient
from src.model.Models import Request, RequestStatus, RequestType
from src.config.manager import (
    config,
    get_category_id_for_status,
    get_category_name_for_status,
    set_category_id_for_status,
)

logger = logging.getLogger(__name__)


class RequestManager:
    """
    Service class that manages the complete lifecycle of marketing requests.
    Handles both database persistence and Discord server state synchronization.
    """

    # Discord caps the number of channels in a single category at 50. When a
    # status category (in practice, Done) hits this, we auto-rotate it.
    DISCORD_CATEGORY_CHANNEL_LIMIT = 50

    def __init__(self, bot: commands.Bot, db_client: DatabaseClient):
        self.bot = bot
        self.db = db_client
    
    async def create_request(self, request: Request, guild: discord.Guild, acting_user_id: Optional[int] = None) -> Optional[Request]:
        """
        Create a new request with full Discord integration.
        
        Args:
            request: The request object to create
            guild: The Discord guild where the request should be created
            
        Returns:
            The created request with updated channel_id, or None if failed
        """
        try:
            # 1. Create the request channel
            channel = await self._create_request_channel(request, guild)
            if not channel:
                logger.error("Failed to create Discord channel")
                return None
            
            # 2. Update request with channel ID
            request.channel_id = channel.id
            x = await self.get_requester_department(request.requester_id)
            request.requester_department_id = x[1]['role_id']
            
            
            # 2.5: Place it in the appropriate category based on status
            category = await self._get_category_for_status(request.status or RequestStatus.IN_QUEUE, guild)
            if category:
                await channel.edit(category=category)

            # 2.75: Create an additional assignee role and set the field accordingly

            role = await guild.create_role(
                name=f"{request.title[:20]} Assignees"
            )
            request.additional_assignee_id = role.id

            await self._create_request_message(request, channel)

            # 3. Save to database
            created_request = await self.db.create_request(request, acting_user_id=acting_user_id)
            if not created_request:
                # Cleanup: delete the channel if database save failed
                await channel.delete(reason="Database save failed")
                logger.error("Failed to save request to database")
                return None
                        
            # 5. Set appropriate permissions and notifications
            await self._calculate_permissions(created_request, channel, guild)

            await self.sort_status_category(created_request.status, guild)
            
            logger.info(f"✅ Successfully created request {created_request.channel_id}")
            return created_request
            
        except Exception as e:
            logger.error(f"Error creating request: {e}")
            return None
    
    async def update_request(self, request: Request, acting_user_id: Optional[int] = None) -> Optional[Request]:
        """
        Update an existing request in both database and Discord.
        
        Args:
            request: The updated request object
            
        Returns:
            The updated request, or None if failed
        """
        try:
            existing_request = await self.db.get_request_by_channel_id(request.channel_id)
            resort_needed = False
            if existing_request:
                resort_needed = (
                    existing_request.posting_date != request.posting_date
                    or existing_request.type != request.type
                )

            # 1. Update in database
            updated_request = await self.db.update_request(request.channel_id, request, acting_user_id=acting_user_id)
            if not updated_request:
                logger.error("Failed to update request in database")
                return None
            
            # 2. Update Discord channel and message
            channel = self.bot.get_channel(request.channel_id)
            if channel and isinstance(channel, discord.TextChannel):
                await self._update_request_message(updated_request, channel)
                await self._update_channel_metadata(updated_request, channel)
                if resort_needed:
                    await self.sort_status_category(updated_request.status, channel.guild)
            
            logger.info(f"Successfully updated request {updated_request.channel_id}")
            return updated_request
            
        except Exception as e:
            logger.error(f"Error updating request: {e}")
            return None
    
    async def advance_request_status(self, channel_id: int, acting_user_id: Optional[int] = None) -> Optional[Request]:
        """
        Advance a request to the next status and move channel accordingly.
        
        Args:
            channel_id: The channel ID of the request
            
        Returns:
            The updated request, or None if failed
        """
        try:
            # 1. Advance status in database
            updated_request = await self.db.advance_request_to_next_status(channel_id, acting_user_id=acting_user_id)
            if not updated_request:
                logger.error("Failed to advance request status in database")
                return None
            
            # 2. Move channel to appropriate category
            channel = self.bot.get_channel(channel_id)
            if channel and isinstance(channel, discord.TextChannel):
                await self._move_channel_to_category(updated_request, channel)
                await self._update_request_message(updated_request, channel)
                await self.sort_status_category(updated_request.status, channel.guild)
            
            # 3. Recalculate permissions
            await self._calculate_permissions(updated_request, channel, self.bot.guilds[0])

            logger.info(f"✅ Advanced request {channel_id} to {updated_request.status}")
            return updated_request
            
        except Exception as e:
            logger.error(f"Error advancing request status: {e}")
            return None
    
    async def sync_status_from_category(self, channel_id: int, category_id: int, acting_user_id: Optional[int] = None) -> Optional[Request]:
        """
        Sync request status based on category change (triggered by manual move).
        
        Args:
            channel_id: The channel ID of the request
            category_id: The new category ID
            
        Returns:
            The updated request, or None if failed
        """
        try:
            from src.config.manager import get_status_for_category_id
            from src.model.Models import RequestStatus
            
            # Get status for the new category
            status_str = get_status_for_category_id(category_id)
            if not status_str:
                logger.info(f"Category {category_id} is not mapped to any request status")
                return None
            
            # Update status in database
            status = RequestStatus(status_str)
            updated_request = await self.db.set_request_status(channel_id, status, acting_user_id=acting_user_id)
            if not updated_request:
                logger.error("Failed to update request status in database")
                return None
            
            # Update the request message
            channel = self.bot.get_channel(channel_id)
            if channel and isinstance(channel, discord.TextChannel):
                await self._update_request_message(updated_request, channel)
                await self._calculate_permissions(updated_request, channel, self.bot.guilds[0])
                await self._update_channel_metadata(updated_request, channel)
                await self.sort_status_category(updated_request.status, channel.guild)

                # A manual drag can't go through the move-time rotation path, and
                # Discord blocks dragging into an already-full category. So once a
                # drag fills the destination, proactively archive it and spin up a
                # fresh one here, keeping room for the next drag/move.
                dest_category = channel.guild.get_channel(category_id)
                if (
                    isinstance(dest_category, discord.CategoryChannel)
                    and len(dest_category.channels) >= self.DISCORD_CATEGORY_CHANNEL_LIMIT
                ):
                    await self._rotate_full_category(
                        updated_request.status, dest_category, channel.guild
                    )

            logger.info(f"✅ Synced request {channel_id} to status {status_str} from category move")
            return updated_request
            
        except Exception as e:
            logger.error(f"Error syncing status from category: {e}")
            return None
    
    async def assign_request(self, channel_id: int, assigned_to_id: int, acting_user_id: Optional[int] = None) -> Optional[Request]:
        """
        Assign a request to a user and update Discord permissions.
        
        Args:
            channel_id: The channel ID of the request
            assigned_to_id: The user ID to assign the request to
            
        Returns:
            The updated request, or None if failed
        """
        try:
            # 1. Assign in database
            updated_request = await self.db.assign_request(channel_id, assigned_to_id, acting_user_id=acting_user_id)
            if not updated_request:
                logger.error("Failed to assign request in database")
                return None
            
            # 2. Update Discord channel permissions
            channel = self.bot.get_channel(channel_id)
            await self._calculate_permissions(updated_request, channel, self.bot.guilds[0])
            
            await self._update_request_message(updated_request, channel)
            
            logger.info(f"✅ Assigned request {channel_id} to user {assigned_to_id}")
            return updated_request
            
        except Exception as e:
            logger.error(f"Error assigning request: {e}")
            return None
    
    async def delete_request(self, channel_id: int, acting_user_id: Optional[int] = None) -> bool:
        """
        Delete a request from both database and Discord.
        
        Args:
            channel_id: The channel ID of the request to delete
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # 1. Delete from database
            request = await self.get_request(channel_id)
            success = await self.db.delete_request(channel_id, acting_user_id=acting_user_id)
            if not success:
                logger.error("Failed to delete request from database")
                return False
            
            # 2. Delete Discord channel
            channel = self.bot.get_channel(channel_id)
            if channel:
                await channel.delete(reason="Request deleted")
            
            # Get the "additional assignees" role and delete it
            if request and request.additional_assignee_id:
                role = discord.utils.get(self.bot.guilds[0].roles, id=request.additional_assignee_id)
                if role:
                    await role.delete(reason="Request deleted")
            
            logger.info(f"✅ Successfully deleted request {channel_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error deleting request: {e}")
            return False

    async def set_request_status(self, channel_id: int, status: RequestStatus, acting_user_id: Optional[int] = None) -> Optional[Request]:
        """
        Set the status of a request and update Discord channel accordingly.
        
        Args:
            channel_id: The channel ID of the request
            status: The new status to set
            
        Returns:
            The updated request, or None if failed
        """
        try:
            # 1. Update status in database
            updated_request = await self.db.set_request_status(channel_id, status, acting_user_id=acting_user_id)
            if not updated_request:
                logger.error("Failed to set request status in database")
                return None
            
            # 2. Move channel to appropriate category
            channel = self.bot.get_channel(channel_id)
            if channel and isinstance(channel, discord.TextChannel):
                await self._move_channel_to_category(updated_request, channel)
                await self._update_request_message(updated_request, channel)
                await self.sort_status_category(updated_request.status, channel.guild)
            
            # 3. Recalculate permissions
            await self._calculate_permissions(updated_request, channel, self.bot.guilds[0])
            
            logger.info(f"✅ Set request {channel_id} status to {status.value}")
            return updated_request
            
        except Exception as e:
            logger.error(f"Error setting request status: {e}")
            return None
        
    async def get_request(self, channel_id: int) -> Optional[Request]:
        """
        Retrieve a request by its channel ID.
        
        Args:
            channel_id: The channel ID of the request
            
        Returns:
            The request object, or None if not found
        """
        try:
            request = await self.db.get_request_by_channel_id(channel_id)
            return request
        except Exception as e:
            logger.error(f"Error retrieving request: {e}")
            return None
    
    async def get_requester_department(self, requester_id: int) -> Optional[dict]:
        """
        Given a requester's user ID, retrieve their department info from the bot config.
        
        Returns:
            Dictionary with department info including 'name', 'role_id', etc., or None if not found
        """
        # Go through all the users roles until you find one in the departments config key
        for guild in self.bot.guilds:
            member = guild.get_member(requester_id)
            if not member:
                continue
            
            departments = config.get("departments", {})
            
            for role in member.roles:
                for dept_id, dept_info in departments.items():
                    if role.id == dept_info.get("role_id"):
                        return dept_id, dept_info
                    
        return None

    async def update_requester_department(self, channel_id: int, new_dept_id: int, acting_user_id: Optional[int] = None) -> Optional[Request]:
        """
        Update the department of the requester for a given request. This is useful for department subgroups
        
        Args:
            channel_id: The channel ID of the request
            new_dept_id: The new department ID to set for the requester
        """

        try:
            request = await self.get_request(channel_id)
            if not request:
                logger.error("Request not found for updating requester department")
                return None
            
            # Update the requester's department in the database
            updated_request = await self.db.update_requester_department(channel_id, new_dept_id, acting_user_id=acting_user_id)
            if not updated_request:
                logger.error("Failed to update requester department in database")
                return None
            
            await self._calculate_permissions(updated_request, self.bot.get_channel(channel_id), self.bot.guilds[0])
            
            logger.info(f"✅ Updated requester department for request {channel_id} to {new_dept_id}")
            return updated_request
            
        except Exception as e:
            logger.error(f"Error updating requester department: {e}")
            return None
    
    async def change_requester(self, channel_id: int, new_requester_id: int, acting_user_id: Optional[int] = None) -> Optional[Request]:
        """
        Change the requester for a given request.
        
        Args:
            channel_id: The channel ID of the request
            new_requester_id: The new requester's Discord user ID
        
        Returns:
            The updated request, or None if failed
        """
        try:
            request = await self.get_request(channel_id)
            if not request:
                logger.error("Request not found for changing requester")
                return None
            
            # Update the requester in the database using the new endpoint
            updated_request = await self.db.change_requester(channel_id, new_requester_id, acting_user_id=acting_user_id)
            if not updated_request:
                logger.error("Failed to change requester in database")
                return None
            
            # Recalculate permissions to reflect the new requester
            channel = self.bot.get_channel(channel_id)
            if channel:
                await self._calculate_permissions(updated_request, channel, self.bot.guilds[0])
            
            logger.info(f"✅ Changed requester for request {channel_id} to {new_requester_id}")
            return updated_request
            
        except Exception as e:
            logger.error(f"Error changing requester: {e}")
            return None

    async def resort_request_channel(self, channel_id: int) -> bool:
        """Resort the category containing the provided request channel."""
        request = await self.get_request(channel_id)
        if not request:
            return False
        channel = self.bot.get_channel(channel_id)
        if channel and isinstance(channel, discord.TextChannel):
            await self.sort_status_category(request.status, channel.guild)
            return True
        return False

    async def sort_status_category(self, status: RequestStatus, guild: discord.Guild) -> None:
        """Sort request channels in a status category by type and posting date."""
        try:
            category = await self._get_category_for_status(status, guild)
            if not category:
                return
            requests = await self.db.get_requests_by_status(status)
            request_map = {request.channel_id: request for request in requests}
            await self._sort_category_channels(category, request_map.values())
        except Exception as e:
            logger.error(f"Error sorting category for status {status.value}: {e}")

    async def sort_all_status_categories(self, guild: discord.Guild) -> None:
        """Sort all configured status categories in the guild."""
        for status in RequestStatus:
            await self.sort_status_category(status, guild)
        

    async def has_department_subgroups(self, requester_id: int) -> bool:
        """Check if the requester's department has subgroups."""
        dept = await self.get_requester_department(requester_id)
        if not dept:
            return False
        dept_id, dept_info = dept
        subdepartments = config.get("department_subgroups", {})
        return dept_id in subdepartments and len(subdepartments.get(dept_id, {})) > 0

    async def get_department_subgroups(self, requester_id: int) -> Optional[dict]:
        """Get the subgroups for the requester's department."""
        dept = await self.get_requester_department(requester_id)
        if not dept:
            return None
        dept_id, dept_info = dept
        subdepartments = config.get("department_subgroups", {})
        return subdepartments.get(dept_id, None)


    # Private helper methods for Discord operations
    
    async def _create_request_channel(self, request: Request, guild: discord.Guild) -> Optional[discord.TextChannel]:
        """Create a Discord channel for the request."""
        try:
            # Get the appropriate category based on request status
            category = await self._get_category_for_status(request.status or RequestStatus.IN_QUEUE, guild)
            emoji = "📸" if request.type == RequestType.POST else "🎥"
            # Create channel name
            channel_name = f"{request.title}"[:40]  # Discord limit
            channel_name = "".join(c if c.isalnum() or c in '-_' else '-' for c in channel_name.lower())
            channel_name = f"{emoji}-{channel_name}"
            # Create the channel
            channel = await guild.create_text_channel(
                name=channel_name,
                category=category,
            )
            
            return channel
            
        except Exception as e:
            logger.error(f"Error creating request channel: {e}")
            return None
    

    def to_timestamp(self, dt):
        """Convert date or datetime to a UNIX timestamp."""
        if isinstance(dt, date) and not isinstance(dt, datetime):
            dt = datetime.combine(dt, datetime.min.time())
        return int(dt.timestamp())


    async def _create_request_message(self, request: Request, channel: discord.TextChannel):
        """Create the initial request message in the channel."""
        try:
            from datetime import datetime
            from src.utils.cycle_helpers import is_valid_posting_date, get_cycle_warning_embed
            
            embed = discord.Embed(
                title=f"[{request.type.value.upper()}] {request.title}",
                description=request.description,
                color=0x3498db
            )

            if request.posting_date:
                ts = self.to_timestamp(request.posting_date)
                embed.add_field(
                    name="Posting Date",
                    value=f"<t:{ts}:D> (<t:{ts}:R>)",
                    inline=True
                )
            if request.room:
                embed.add_field(name="Location", value=request.room, inline=True)
            if request.signup_url:
                embed.add_field(name="Signup URL", value=request.signup_url, inline=False)
            
            embed.add_field(name="Status", value=request.status.value.replace('_', ' ').title(), inline=True)
            embed.add_field(name="Requester", value=f"<@{request.requester_id}>", inline=True)
            
            # Create the edit button view
            from src.ui.views import RequestEditView
            view = RequestEditView(
                requester_id=request.requester_id,
                request_type=request.type.value,
                channel_id=request.channel_id,
                request_manager=self
            )
            
            # Send the message with the view
            message = await channel.send(embed=embed, view=view)
            await message.pin()
            request.main_message_id = message.id
            request.created_at = datetime.now()
            # Check if posting date meets cycle criteria and send warning if not
            cycle_warnings_enabled = config.get_nested(
                "bot_config", "cycle_warnings_enabled", default=True)
            if cycle_warnings_enabled and request.posting_date and request.created_at:
                is_valid, reason = is_valid_posting_date(request.created_at, request.posting_date)
                if not is_valid:
                    warning_embed = get_cycle_warning_embed(
                        request.created_at,
                        request.posting_date,
                        is_valid,
                        reason
                    )
                    await channel.send(f"<@{request.requester_id}>", embed=warning_embed)
            
        except Exception as e:
            logger.error(f"Error creating request message: {e}")
    
    async def _update_request_message(self, request: Request, channel: discord.TextChannel):
        """Update the request message with latest information."""
        try:
            # Fetch and edit the original message
            if request.main_message_id:
                original_message = await channel.fetch_message(request.main_message_id)
                
                embed = discord.Embed(
                    title=f"{request.type.value.upper()} {request.title}",
                    description=request.description,
                    color=0x3498db
                )
                if request.posting_date:
                    ts = self.to_timestamp(request.posting_date)
                    embed.add_field(
                        name="Posting Date",
                        value=f"<t:{ts}:D> (<t:{ts}:R>)",
                        inline=True
                    )
                if request.room:
                    embed.add_field(name="Location", value=request.room, inline=True)
                if request.signup_url:
                    embed.add_field(name="Signup URL", value=request.signup_url, inline=False)
                
                if request.assigned_to_id:
                    assigned_user_mention = f"<@{request.assigned_to_id}>"
                    embed.add_field(name="Assigned To", value=assigned_user_mention, inline=True) 
                
                embed.add_field(name="Status", value=request.status.value.replace('_', ' ').title(), inline=True)
                embed.add_field(name="Requester", value=f"<@{request.requester_id}>", inline=True)
                
                # Recreate the view with the edit button
                from src.ui.views import RequestEditView
                view = RequestEditView(
                    requester_id=request.requester_id,
                    request_type=request.type.value,
                    channel_id=request.channel_id,
                    request_manager=self
                )
                
                # Edit the original message
                await original_message.edit(embed=embed, view=view)
            
        except Exception as e:
            logger.error(f"Error updating request message: {e}")
    
    async def _update_channel_metadata(self, request: Request, channel: discord.TextChannel):
        """Update channel name, topic, etc. based on request."""
        try:
            # Update channel topic
            new_topic = f"{request.type.value} Request - {request.title} | Status: {request.status.value.replace('_', ' ').title()}"
            await channel.edit(topic=new_topic)
            new_name = f"{'📸' if request.type == RequestType.POST else '🎥'}-{request.title}"[:40]
            await channel.edit(name=new_name)
            
        except Exception as e:
            logger.error(f"Error updating channel metadata: {e}")
    
    async def _calculate_permissions(self, request: Request, channel: discord.TextChannel, guild: discord.Guild):
        """Set up appropriate permissions for the request channel."""
        try:
            # Build overwrites dictionary
            overwrites = {}
            
            # Set @everyone to not see the channel by default
            overwrites[guild.default_role] = discord.PermissionOverwrite(
                read_messages=False
            )
            
            # 1. ALWAYS: Additional Assignees role (read/write)
            if request.additional_assignee_id:
                additional_assignees_role = guild.get_role(request.additional_assignee_id)
                if additional_assignees_role:
                    overwrites[additional_assignees_role] = discord.PermissionOverwrite(
                        read_messages=True,
                        send_messages=True
                    )
            
            # 2. ALWAYS: Requester's department (read/write)
            if request.requester_department_id:
                requester_dept_role = guild.get_role(request.requester_department_id)
                if requester_dept_role:
                    overwrites[requester_dept_role] = discord.PermissionOverwrite(
                        read_messages=True,
                        send_messages=True
                    )
            
            # 3. Assigned user OR Request type department
            if request.assigned_to_id:
                # If assigned to someone specific, only they can see it
                assigned_user = guild.get_member(request.assigned_to_id)
                if assigned_user:
                    overwrites[assigned_user] = discord.PermissionOverwrite(
                        read_messages=True,
                        send_messages=True,
                        manage_messages=True
                    )
            else:
                # Not assigned: entire department for request type can see it
                request_type_config = config.get("request_types", {}).get(request.type.value.lower(), {})
                role_key = request_type_config.get("role")
                
                if role_key:
                    role_id = config.get("roles", {}).get(role_key)
                    if role_id:
                        request_type_role = guild.get_role(role_id)
                        if request_type_role:
                            overwrites[request_type_role] = discord.PermissionOverwrite(
                                read_messages=True,
                                send_messages=True
                            )
            
            # 4. If status is "awaiting_posting" or "done", add Social Media Manager
            if request.status in [RequestStatus.AWAITING_POSTING, RequestStatus.DONE]:
                social_media_role_id = config.get("roles", {}).get("social_media_manager")
                if social_media_role_id:
                    social_media_role = guild.get_role(social_media_role_id)
                    if social_media_role:
                        overwrites[social_media_role] = discord.PermissionOverwrite(
                            read_messages=True,
                            send_messages=True
                        )
            
            # Apply all overwrites in a single API call
            await channel.edit(overwrites=overwrites)
            
            logger.info(f"✅ Updated permissions for request channel {request.channel_id}")
            
        except Exception as e:
            logger.error(f"Error setting up channel permissions: {e}")

    async def _get_category_for_status(self, status: RequestStatus, guild: discord.Guild) -> Optional[discord.CategoryChannel]:
        """Get the Discord category for a given request status."""
        try:
            # Direct lookup: get category ID from config based on status
            category_id = get_category_id_for_status(status.value)
            if not category_id:
                logger.error(f"No category ID configured for status {status.value}")
                return None
            
            # Get the category channel
            category = guild.get_channel(category_id)
            if not category or not isinstance(category, discord.CategoryChannel):
                logger.error(f"Category ID {category_id} for status {status.value} is not a valid category channel")
                return None
            
            return category
            
        except Exception as e:
            logger.error(f"Error getting category for status {status.value}: {e}")
            return None
    
    async def _move_channel_to_category(self, request: Request, channel: discord.TextChannel):
        """Move channel to the appropriate category based on status."""
        try:
            await self._assign_channel_to_category(request.status, channel, channel.guild)
        except Exception as e:
            logger.error(f"Error moving channel to category: {e}")

    async def _assign_channel_to_category(
        self,
        status: RequestStatus,
        channel: discord.TextChannel,
        guild: discord.Guild,
    ) -> None:
        """Move ``channel`` into the category for ``status``, rotating it first
        if it has hit Discord's per-category channel limit.

        Discord caps a category at 50 channels. When the target (most commonly
        Done) is full, we create a fresh category, repoint the config at it, and
        rename the old one to an archive — automating what used to be a manual
        create-config-rename dance. Both a proactive count check and a reactive
        exception catch are used, so we rotate even if the count is briefly off.
        """
        category = await self._get_category_for_status(status, guild)
        if not category:
            return

        # Proactive: rotate before we even attempt the move when already full.
        if len(category.channels) >= self.DISCORD_CATEGORY_CHANNEL_LIMIT:
            category = await self._rotate_full_category(status, category, guild) or category

        try:
            await channel.edit(category=category)
        except discord.HTTPException as e:
            if not self._is_category_full_error(e):
                raise
            # Reactive safety net: the category filled up between the check and
            # the move (e.g. a concurrent request landed first).
            logger.warning(
                f"Category for status {status.value} is full; rotating to a new one"
            )
            new_category = await self._rotate_full_category(status, category, guild)
            if not new_category:
                raise
            await channel.edit(category=new_category)

    async def _rotate_full_category(
        self,
        status: RequestStatus,
        full_category: discord.CategoryChannel,
        guild: discord.Guild,
    ) -> Optional[discord.CategoryChannel]:
        """Archive a full status category and create a fresh active one.

        Creates a new category in the old one's slot (same name and
        permissions), renames the old one to an archive, and repoints the
        config at the new category. Returns the new category, or None if the
        rotation failed (the caller then keeps using the old one).
        """
        try:
            # 1. New active category, same name/permissions, in the old slot.
            new_category = await guild.create_category(
                name=full_category.name,
                overwrites=full_category.overwrites,
                position=full_category.position,
                reason=f"Auto-rotation: {status.value} category reached the channel limit",
            )

            # 2. Rename the now-full category so it reads as an archive.
            archive_name = self._archive_name_for(full_category, guild)
            await full_category.edit(
                name=archive_name,
                reason=f"Auto-rotation: archived full {status.value} category",
            )

            # 3. Point the config (and its cache) at the new active category.
            set_category_id_for_status(status.value, new_category.id)

            logger.info(
                f"✅ Rotated {status.value} category: archived '{archive_name}' "
                f"({full_category.id}) and created new active category {new_category.id}"
            )
            return new_category
        except Exception as e:
            logger.error(f"Failed to rotate full category for status {status.value}: {e}")
            return None

    @staticmethod
    def _archive_name_for(full_category: discord.CategoryChannel, guild: discord.Guild) -> str:
        """Build a unique archive name from a category's current name.

        Strips any existing ``(Archive N)`` suffix so repeated rotations read as
        ``Done (Archive 1)``, ``Done (Archive 2)`` rather than nesting suffixes.
        """
        base = re.sub(r"\s*\(Archive(?:\s+\d+)?\)\s*$", "", full_category.name).strip()
        n = 1
        while True:
            candidate = f"{base} (Archive {n})"[:100]  # Discord category name limit
            if not discord.utils.get(guild.categories, name=candidate):
                return candidate
            n += 1

    @staticmethod
    def _is_category_full_error(error: discord.HTTPException) -> bool:
        """Heuristic check for Discord's "category is at capacity" error."""
        text = (getattr(error, "text", "") or str(error)).lower()
        return "category" in text and any(
            kw in text for kw in ("maximum", "limit", "reached")
        )

    async def _sort_category_channels(
        self,
        category: discord.CategoryChannel,
        requests: Iterable[Request],
    ) -> None:
        """Sort channels in the category using a bulk position update."""
        request_map: Dict[int, Request] = {request.channel_id: request for request in requests}
        if not request_map:
            return

        channels = list(category.channels)
        request_channels = [
            channel for channel in channels
            if isinstance(channel, discord.TextChannel) and channel.id in request_map
        ]
        if not request_channels:
            return

        def sort_key(channel: discord.TextChannel):
            request = request_map[channel.id]
            type_rank = 0 if request.type == RequestType.POST else 1
            posting_timestamp = request.posting_date.timestamp()
            return (type_rank, posting_timestamp)

        sorted_requests = sorted(request_channels, key=sort_key)
        non_request_channels = [
            channel for channel in channels
            if channel not in request_channels
        ]
        new_order = sorted_requests + non_request_channels
        current_order = channels

        if [channel.id for channel in new_order] == [channel.id for channel in current_order]:
            return

        updates = [
            {"id": channel.id, "position": position}
            for position, channel in enumerate(new_order)
        ]

        await self.bot.http.bulk_channel_update(
            category.guild.id,
            updates,
            reason="Auto-sort request channels",
        )
