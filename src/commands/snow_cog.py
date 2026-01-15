"""
Snow Day Monitor Cog - Checks campus status every 5 minutes and alerts if any campus is closed.
"""

import discord
from discord.ext import commands, tasks
from datetime import time
import logging
from typing import Optional

from src.services.snow_day_detector import CampusStatusService

logger = logging.getLogger(__name__)


class SnowDayCog(commands.Cog):
    """Cog for monitoring campus status and sending alerts when campuses close."""
    
    def __init__(self, bot):
        self.bot = bot
        self.campus_service = CampusStatusService()
        self.alert_channel_id: Optional[int] = None
        self.daily_update_sent = False
        
        # Start the monitoring tasks
        self.check_campus_status.start()
        self.daily_campus_update.start()
    
    def cog_unload(self):
        """Clean up when the cog is unloaded."""
        self.check_campus_status.cancel()
        self.daily_campus_update.cancel()
    
    @tasks.loop(minutes=1)
    async def check_campus_status(self):
        """Check campus status every 5 minutes and send alerts if any campus is closed. Stops if closure detected."""
        try:
            if not self.alert_channel_id:
                return
            
            statuses = await self.campus_service.get_all_statuses()
            closed_campuses = [campus for campus in statuses if not campus.is_closed]
            
            if closed_campuses:
                # Send alert for closed campuses
                channel = self.bot.get_channel(self.alert_channel_id)
                if channel:
                    embed = discord.Embed(
                        title="🚨 Campus Closure Alert",
                        description=f"**{len(closed_campuses)}** campus(es) currently closed!",
                        color=discord.Color.red()
                    )
                    
                    for campus in closed_campuses:
                        embed.add_field(
                            name=campus.name,
                            value=f"Status: **{campus.status.upper()}**",
                            inline=False
                        )
                    
                    embed.set_footer(text=f"Monitoring stopped - campus closure detected")
                    embed.timestamp = discord.utils.utcnow()
                    
                    await channel.send("@everyone", embed=embed)
                    logger.info(f"Sent campus closure alert for {len(closed_campuses)} campus(es)")
                
                # Stop the task since a campus is closed
                self.check_campus_status.cancel()
                logger.info("Campus status monitoring stopped - closure detected")
            
        except Exception as e:
            logger.error(f"Error checking campus status: {e}")
    
    @check_campus_status.before_loop
    async def before_check_campus_status(self):
        """Wait until the bot is ready before starting the loop."""
        await self.bot.wait_until_ready()
    
    @tasks.loop(time=time(hour=6, minute=10))
    async def daily_campus_update(self):
        """Send daily campus status update at 6:10 AM, then stop."""
        try:
            if not self.alert_channel_id or self.daily_update_sent:
                return
            
            statuses = await self.campus_service.get_all_statuses()
            
            channel = self.bot.get_channel(self.alert_channel_id)
            if channel:
                embed = discord.Embed(
                    title="🌨️ Daily Campus Status Update",
                    description="Good morning! Here's the status of all campuses:",
                    color=discord.Color.blue()
                )
                
                for campus in statuses:
                    status_emoji = "✅" if campus.is_open else "🚨"
                    embed.add_field(
                        name=f"{status_emoji} {campus.name}",
                        value=f"Status: **{campus.status}**",
                        inline=False
                    )
                
                embed.set_footer(text="Daily update - monitoring continues")
                embed.timestamp = discord.utils.utcnow()
                
                await channel.send("@everyone", embed=embed)
                logger.info("Sent daily campus status update")
                
                # Mark as sent and stop the task
                self.daily_update_sent = True
                self.daily_campus_update.cancel()
                logger.info("Daily campus update task stopped after sending")
            
        except Exception as e:
            logger.error(f"Error sending daily campus update: {e}")
    
    @daily_campus_update.before_loop
    async def before_daily_campus_update(self):
        """Wait until the bot is ready before starting the loop."""
        await self.bot.wait_until_ready()
    
    @commands.command(name="snow-channel")
    @commands.has_permissions(manage_guild=True)
    async def set_snow_channel(self, ctx, channel: discord.TextChannel):
        """Set the channel for snow day alerts (admin only)."""
        self.alert_channel_id = channel.id
        await ctx.send(f"✅ Snow day alerts will be sent to {channel.mention}")
        logger.info(f"Snow alert channel set to {channel.name} ({channel.id})")
    
    @commands.command(name="snow-check")
    async def manual_check(self, ctx):
        """Manually check campus status."""
        try:
            statuses = await self.campus_service.get_all_statuses()
            
            embed = discord.Embed(
                title="🌨️ Campus Status Check",
                description="Current status of all campuses:",
                color=discord.Color.blue()
            )
            
            for campus in statuses:
                status_emoji = "✅" if campus.is_open else "🚨"
                embed.add_field(
                    name=f"{status_emoji} {campus.name}",
                    value=f"Status: **{campus.status}**",
                    inline=False
                )
            
            embed.set_footer(text="Updates every 5 minutes")
            embed.timestamp = discord.utils.utcnow()
            
            await ctx.send(embed=embed)
            
        except Exception as e:
            await ctx.send(f"❌ Error checking campus status: {e}")
            logger.error(f"Error in manual campus check: {e}")


async def setup(bot):
    """Setup function to load the cog."""
    await bot.add_cog(SnowDayCog(bot))
