"""
Utilities cog for background tasks and VC forking functionality.
"""

import discord
from discord.ext import commands, tasks
from datetime import datetime, time, date
import logging
import asyncio
from typing import Optional

from model.Models import RequestStatus
from src.services.request_manager import RequestManager
from src.config.manager import config

logger = logging.getLogger(__name__)


class UtilsCog(commands.Cog):
    """Cog for utility functions including daily reminders and VC forking."""
    
    def __init__(self, bot, request_manager: RequestManager = None):
        self.bot = bot
        self.request_manager = request_manager
        self.forked_vcs = {}  # Track forked VCs: {user_id: channel_id}
        
        # Start the daily reminder task
        self.daily_reminder.start()
    
    def cog_unload(self):
        """Clean up when the cog is unloaded."""
        self.daily_reminder.cancel()
    
    @tasks.loop(time=time(hour=6, minute=0))  # Run at 6:00 AM
    async def daily_reminder(self):
        """Check for requests due today and send reminders."""
        try:
            logger.info("Running daily reminder task...")
            logger.info(f"Current time: {datetime.now()}")
            
            # Get all requests from the database
            all_requests = await self.request_manager.db.get_all_requests()
            
            today = datetime.now().date()
            logger.info(f"Today's date: {today}")
            
            marketing_role_id = config.get("server_config", {}).get("marketing_role_id")
            
            if not marketing_role_id:
                logger.warning("Marketing role ID not configured, skipping reminders")
                return
            
            logger.info(f"Checking {len(all_requests)} requests for reminders...")
            reminders_sent = 0
            
            for request in all_requests:
                # Check if the posting date is today
                # Handle both datetime and date objects
                posting_date = request.posting_date
                if posting_date:
                    # Convert to date if it's a datetime object
                    if isinstance(posting_date, datetime):
                        posting_date = posting_date.date()
                    
                    logger.debug(f"Checking request '{request.title}': posting_date={posting_date}, today={today}")
                    
                    if posting_date == today and request.status != RequestStatus.BLOCKED:
                        # Get the channel
                        channel = self.bot.get_channel(request.channel_id)
                        
                        if channel and isinstance(channel, discord.TextChannel):
                            # Get the marketing role
                            marketing_role = channel.guild.get_role(marketing_role_id)
                            
                            if marketing_role:
                                # Create reminder embed
                                embed = discord.Embed(
                                    title="📅 Posting Reminder",
                                    description=f"This {request.type.value} is scheduled to be posted **TODAY**!",
                                    color=0xFF9900  # Orange color for urgency
                                )
                                embed.add_field(
                                    name="Title",
                                    value=request.title,
                                    inline=False
                                )
                                embed.add_field(
                                    name="Status",
                                    value=request.status.value.replace('_', ' ').title(),
                                    inline=True
                                )
                                if request.assigned_to_id:
                                    embed.add_field(
                                        name="Assigned To",
                                        value=f"<@{request.assigned_to_id}>",
                                        inline=True
                                    )
                                
                                embed.set_footer(text="Don't forget to post this content today!")
                                embed.timestamp = datetime.now()
                                
                                # Send the reminder
                                await channel.send(
                                    f"{marketing_role.mention} Reminder!",
                                    embed=embed
                                )
                                
                                reminders_sent += 1
                                logger.info(f"Sent reminder for request '{request.title}' in channel {request.channel_id}")
                            else:
                                logger.warning(f"Marketing role {marketing_role_id} not found in guild")
                        else:
                            logger.warning(f"Channel {request.channel_id} not found or is not a text channel")
            
            logger.info(f"Daily reminder task complete. Sent {reminders_sent} reminder(s).")
            
        except Exception as e:
            logger.error(f"Error in daily reminder task: {e}", exc_info=True)
    
    @daily_reminder.before_loop
    async def before_daily_reminder(self):
        """Wait for the bot to be ready before starting the task."""
        await self.bot.wait_until_ready()
        logger.info("Daily reminder task is ready to start")
    
    @commands.command(name="test_reminders")
    @commands.has_permissions(administrator=True)
    async def test_reminders(self, ctx):
        """Manually trigger the daily reminder task for testing."""
        await ctx.send("🔄 Running daily reminder task manually...")
        await self.daily_reminder()
        await ctx.send("✅ Daily reminder task completed!")
    
    @commands.Cog.listener()
    async def on_voice_state_update(
        self, 
        member: discord.Member, 
        before: discord.VoiceState, 
        after: discord.VoiceState
    ):
        """Handle voice channel state changes for VC forking."""
        try:
            # Check if VC forking is enabled
            if not config.get("bot_config", {}).get("fork_enabled", False):
                return
            
            # Get the list of fork trigger channels
            fork_channels = config.get("bot_config", {}).get("fork_trigger_channels", [])
            
            # User joined a voice channel
            if after.channel and not before.channel:
                await self._handle_vc_join(member, after.channel, fork_channels)
            
            # User left a voice channel
            elif before.channel and not after.channel:
                await self._handle_vc_leave(member, before.channel)
            
            # User moved between channels
            elif before.channel != after.channel:
                # Handle leaving the old channel
                if before.channel:
                    await self._handle_vc_leave(member, before.channel)
                
                # Handle joining the new channel
                if after.channel:
                    await self._handle_vc_join(member, after.channel, fork_channels)
        
        except Exception as e:
            logger.error(f"Error in voice state update handler: {e}")
    
    async def _handle_vc_join(
        self, 
        member: discord.Member, 
        channel: discord.VoiceChannel,
        fork_channels: list
    ):
        """Handle a user joining a voice channel."""
        # Check if the channel is a fork trigger channel
        if channel.name.lower() not in [name.lower() for name in fork_channels]:
            return
        
        # Check if user already has a forked VC
        if member.id in self.forked_vcs:
            existing_vc = member.guild.get_channel(self.forked_vcs[member.id])
            if existing_vc:
                # Move user to their existing forked VC
                await member.move_to(existing_vc)
                logger.info(f"Moved {member.name} to existing forked VC: {existing_vc.name}")
                return
        
        # Create a forked VC for the user
        forked_vc = await self._create_forked_vc(member, channel)
        
        if forked_vc:
            # Track the forked VC
            self.forked_vcs[member.id] = forked_vc.id
            
            # Move the user to the forked VC
            await member.move_to(forked_vc)
            logger.info(f"Created and moved {member.name} to forked VC: {forked_vc.name}")
            
            # Schedule cleanup after the configured time
            cleanup_minutes = config.get("bot_config", {}).get("fork_auto_cleanup_minutes", 5)
            asyncio.create_task(self._schedule_vc_cleanup(forked_vc, member.id, cleanup_minutes))
    
    async def _handle_vc_leave(self, member: discord.Member, channel: discord.VoiceChannel):
        """Handle a user leaving a voice channel."""
        # Check if the channel is a forked VC belonging to this user
        if member.id in self.forked_vcs and self.forked_vcs[member.id] == channel.id:
            # Check if the VC is empty
            if len(channel.members) == 0:
                # Delete the forked VC
                await channel.delete(reason=f"Forked VC cleanup for {member.name}")
                del self.forked_vcs[member.id]
                logger.info(f"Deleted empty forked VC: {channel.name}")
    
    async def _create_forked_vc(
        self, 
        member: discord.Member, 
        original_channel: discord.VoiceChannel
    ) -> Optional[discord.VoiceChannel]:
        """Create a forked voice channel with the same permissions as the original."""
        try:
            # Generate a name for the forked VC
            forked_name = f"{member.display_name}'s VC"
            
            # Copy the permissions from the original channel
            overwrites = original_channel.overwrites.copy()
            
            # Give the member manage channel permissions for their forked VC
            overwrites[member] = discord.PermissionOverwrite(
                connect=True,
                speak=True,
                manage_channels=True,
                move_members=True,
                mute_members=True,
                deafen_members=True
            )
            
            # Create the forked VC in the same category as the original
            forked_vc = await original_channel.category.create_voice_channel(
                name=forked_name,
                overwrites=overwrites,
                bitrate=original_channel.bitrate,
                user_limit=original_channel.user_limit,
                reason=f"Forked VC for {member.name}"
            )
            
            logger.info(f"Created forked VC '{forked_name}' for {member.name}")
            return forked_vc
            
        except Exception as e:
            logger.error(f"Error creating forked VC: {e}")
            return None
    
    async def _schedule_vc_cleanup(
        self, 
        channel: discord.VoiceChannel, 
        user_id: int, 
        minutes: int
    ):
        """Schedule cleanup of an empty forked VC after a delay."""
        try:
            # Wait for the specified time
            await asyncio.sleep(minutes * 60)
            
            # Check if the channel still exists and is empty
            channel = self.bot.get_channel(channel.id)
            if channel and len(channel.members) == 0:
                await channel.delete(reason="Auto-cleanup of empty forked VC")
                
                # Remove from tracking
                if user_id in self.forked_vcs and self.forked_vcs[user_id] == channel.id:
                    del self.forked_vcs[user_id]
                
                logger.info(f"Auto-deleted empty forked VC after {minutes} minutes")
        
        except Exception as e:
            logger.error(f"Error in VC cleanup task: {e}")


async def setup(bot):
    """Setup function to add the cog to the bot."""
    await bot.add_cog(UtilsCog(bot))
