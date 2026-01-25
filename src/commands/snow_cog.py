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
        self.monitoring_enabled = False  # Must be manually enabled
        self.daily_update_sent = False
        
        # Start the monitoring tasks (but they won't run unless enabled)
        self.check_campus_status.start()
        self.daily_campus_update.start()
    
    def cog_unload(self):
        """Clean up when the cog is unloaded."""
        self.check_campus_status.cancel()
        self.daily_campus_update.cancel()
    
    @tasks.loop(minutes=5)
    async def check_campus_status(self):
        """Check campus status every 5 minutes and send alerts if any campus is closed. Stops if closure detected."""
        try:
            if not self.alert_channel_id or not self.monitoring_enabled:
                return
            
            statuses = await self.campus_service.get_all_statuses()
            closed_campuses = [campus for campus in statuses if campus.is_closed]
            
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
                
                # Stop monitoring since a campus is closed
                self.monitoring_enabled = False
                logger.info("Campus status monitoring disabled - closure detected")
            
        except Exception as e:
            logger.error(f"Error checking campus status: {e}")
    
    @check_campus_status.before_loop
    async def before_check_campus_status(self):
        """Wait until the bot is ready before starting the loop."""
        await self.bot.wait_until_ready()
    
    @tasks.loop(time=time(hour=11, minute=30))  # 6 AM EST = 11 AM UTC
    async def daily_campus_update(self):
        """Send daily campus status update at 6:00 AM EST, then disable monitoring."""
        try:
            if not self.alert_channel_id or not self.monitoring_enabled:
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
                
                embed.set_footer(text="Monitoring disabled - use /snow-enable to re-enable")
                embed.timestamp = discord.utils.utcnow()
                
                await channel.send("@everyone", embed=embed)
                logger.info("Sent daily campus status update")
                
                # Disable monitoring after morning check
                self.monitoring_enabled = False
                logger.info("Campus monitoring disabled after morning update")
            
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
    
    @commands.command(name="snow-enable")
    @commands.has_permissions(manage_guild=True)
    async def enable_monitoring(self, ctx):
        """Enable snow day monitoring (admin only). Use this the night before you want checks."""
        if not self.alert_channel_id:
            await ctx.send("❌ Please set an alert channel first using `/snow-channel`")
            return
        
        self.monitoring_enabled = True
        await ctx.send(
            "✅ Snow day monitoring **enabled**!\n"
            "• Checking every 5 minutes for campus closures\n"
            "• Daily update will be sent at 6:00 AM EST\n"
            "• Monitoring will automatically disable after the morning update or if a closure is detected"
        )
        logger.info("Snow day monitoring enabled")
    
    @commands.command(name="snow-disable")
    @commands.has_permissions(manage_guild=True)
    async def disable_monitoring(self, ctx):
        """Disable snow day monitoring (admin only)."""
        self.monitoring_enabled = False
        await ctx.send("✅ Snow day monitoring **disabled**.")
        logger.info("Snow day monitoring disabled manually")
    
    @commands.command(name="snow-status")
    async def check_monitoring_status(self, ctx):
        """Check if snow day monitoring is currently enabled."""
        status = "✅ **ENABLED**" if self.monitoring_enabled else "❌ **DISABLED**"
        channel_info = f"<#{self.alert_channel_id}>" if self.alert_channel_id else "Not set"
        
        embed = discord.Embed(
            title="🌨️ Snow Day Monitoring Status",
            color=discord.Color.green() if self.monitoring_enabled else discord.Color.red()
        )
        embed.add_field(name="Monitoring Status", value=status, inline=False)
        embed.add_field(name="Alert Channel", value=channel_info, inline=False)
        embed.set_footer(text="Use /snow-enable to activate monitoring")
        
        await ctx.send(embed=embed)
    
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
