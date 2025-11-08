"""
Cycle management cog for workload distribution and cycle information.
"""

import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime
from typing import Optional

from src.client.workload_client import WorkloadClient


class CycleCog(commands.Cog):
    """Cog for handling cycle and workload management commands."""
    
    def __init__(self, bot):
        self.bot = bot
        self.workload_client = WorkloadClient(bot_auth=True)
    
    async def cog_unload(self):
        """Clean up resources when cog is unloaded."""
        await self.workload_client.close()
    
    @app_commands.command(
        name="workload-designers",
        description="Show graphic designer workload for the upcoming posting cycle"
    )
    async def workload_designers(self, interaction: discord.Interaction):
        """Display graphic designer workload with assignment message."""
        await interaction.response.defer()
        
        try:
            workload = await self.workload_client.get_graphic_designer_workload()
            if not workload:
                await interaction.followup.send("❌ Failed to fetch graphic designer workload.")
                return
            
            message = self._format_workload_message(workload, interaction.guild)
            await interaction.followup.send(message)
            
        except Exception as e:
            await interaction.followup.send(f"❌ An error occurred: {str(e)}")
    
    @app_commands.command(
        name="workload-creators",
        description="Show content creator workload for the upcoming posting cycle"
    )
    async def workload_creators(self, interaction: discord.Interaction):
        """Display content creator workload with assignment message."""
        await interaction.response.defer()
        
        try:
            workload = await self.workload_client.get_content_creator_workload()
            if not workload:
                await interaction.followup.send("❌ Failed to fetch content creator workload.")
                return
            
            message = self._format_workload_message(workload, interaction.guild)
            await interaction.followup.send(message)
            
        except Exception as e:
            await interaction.followup.send(f"❌ An error occurred: {str(e)}")
    
    @app_commands.command(
        name="workload-managers",
        description="Show social media manager workload for the current posting cycle"
    )
    async def workload_managers(self, interaction: discord.Interaction):
        """Display social media manager workload with assignment message."""
        await interaction.response.defer()
        
        try:
            workload = await self.workload_client.get_social_media_manager_workload()
            if not workload:
                await interaction.followup.send("❌ Failed to fetch social media manager workload.")
                return
            
            message = self._format_workload_message(workload, interaction.guild)
            await interaction.followup.send(message)
            
        except Exception as e:
            await interaction.followup.send(f"❌ An error occurred: {str(e)}")
    
    @app_commands.command(
        name="cycle-info",
        description="Show information about current development and posting cycles"
    )
    async def cycle_info(self, interaction: discord.Interaction):
        """Display current cycle information."""
        await interaction.response.defer()
        
        try:
            cycle_info = await self.workload_client.get_cycle_info()
            if not cycle_info:
                await interaction.followup.send("❌ Failed to fetch cycle information.")
                return
            
            embed = self._format_cycle_info_embed(cycle_info)
            await interaction.followup.send(embed=embed)
            
        except Exception as e:
            await interaction.followup.send(f"❌ An error occurred: {str(e)}")
    
    def _format_workload_message(self, workload: dict, guild: discord.Guild) -> str:
        """
        Format workload data into a user-friendly message.
        
        Args:
            workload: Workload data from API
            guild: Discord guild for user mentions
            
        Returns:
            Formatted message string
        """
        cycle = workload.get("cycleInfo", {})
        requests = workload.get("requests", [])
        role = workload.get("role", "Team")
        
        # Parse cycle dates for Discord timestamps
        posting_start = cycle.get('postingStart')
        posting_end = cycle.get('postingEnd')
        
        try:
            start_dt = datetime.fromisoformat(posting_start.replace('Z', '+00:00'))
            end_dt = datetime.fromisoformat(posting_end.replace('Z', '+00:00'))
            posting_range = f"<t:{int(start_dt.timestamp())}:D> → <t:{int(end_dt.timestamp())}:D>"
        except:
            posting_range = f"{posting_start} to {posting_end}"
        
        # Build header with better formatting
        message = "# Assalamu Alaikum everyone! 🌙\n\n"
        message += f"## **{role} Workload** - Cycle {cycle.get('cycleNumber', 'N/A')}\n"
        message += f"📅 **Posting Period:** {posting_range}\n\n"
        
        if not requests:
            message += "✨ *No requests scheduled for this cycle! Enjoy the break.*\n"
            return message
        
        message += "> Bismillah Ar-Rahman Ar-Raheem"
        message += "\n\n"
        
        # Group by posting date and sort
        from collections import defaultdict
        by_date = defaultdict(list)
        for req in requests:
            posting_date = req.get("postingDate", "")
            by_date[posting_date].append(req)
        
        # Sort dates
        sorted_dates = sorted(by_date.keys())
        
        # Format each date's requests
        for date_str in sorted_dates:
            date_requests = by_date[date_str]
            
            # Parse date for Discord timestamp
            try:
                date_obj = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                timestamp = int(date_obj.timestamp())
                date_display = f"<t:{timestamp}:D> (<t:{timestamp}:R>)"
            except:
                date_display = date_str
            
            for req in date_requests:
                title = req.get("title", "Untitled")
                assigned_to = req.get("assignedToID")
                request_type = req.get("requestType", "").upper()
                channel_id = req.get("channelID")
                
                # Add emoji based on request type
                emoji = "📸" if request_type == "POST" else "📽️" if request_type == "REEL" else "📋"
                
                message += f"### {emoji} **{title}**\n"
                message += f"📅 {date_display}\n"
                
                if channel_id:
                    message += f"🔗 Channel: <#{channel_id}>\n"
                
                if assigned_to:
                    message += f"👤 Assigned to: <@{assigned_to}>\n"
                else:
                    message += f"⚠️ **Not assigned yet**\n"
                message += "\n"
        
        message += "\n\n"
        message += f"**📊 Total: {len(requests)} request(s)**\n\n"
        message += "> Barak Allahu feekum!"
        
        return message
    
    def _format_cycle_info_embed(self, cycle_info: dict) -> discord.Embed:
        """
        Format cycle information into a Discord embed.
        
        Args:
            cycle_info: Cycle data from API
            
        Returns:
            Discord embed with cycle information
        """
        embed = discord.Embed(
            title="📅 Cycle Information",
            description="Current development and posting cycle details",
            color=0x5865F2
        )
        
        # Helper to convert date string to Discord timestamp
        def to_timestamp(date_str: str) -> str:
            try:
                dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                return f"<t:{int(dt.timestamp())}:D>"
            except:
                return date_str
        
        # Development cycle
        dev_cycle = cycle_info.get("currentDevelopmentCycle", {})
        if dev_cycle:
            dev_start = to_timestamp(dev_cycle.get('developmentStart', ''))
            dev_end = to_timestamp(dev_cycle.get('developmentEnd', ''))
            post_start = to_timestamp(dev_cycle.get('postingStart', ''))
            post_end = to_timestamp(dev_cycle.get('postingEnd', ''))
            
            dev_value = (
                f"**Cycle #{dev_cycle.get('cycleNumber')}**\n\n"
                f"🔨 **Development Phase**\n"
                f"{dev_start} → {dev_end}\n\n"
                f"📤 **Posting Phase**\n"
                f"{post_start} → {post_end}"
            )
            embed.add_field(
                name="Current Development Cycle",
                value=dev_value,
                inline=False
            )
        
        # Posting cycle
        post_cycle = cycle_info.get("currentPostingCycle", {})
        if post_cycle:
            dev_start = to_timestamp(post_cycle.get('developmentStart', ''))
            dev_end = to_timestamp(post_cycle.get('developmentEnd', ''))
            post_start = to_timestamp(post_cycle.get('postingStart', ''))
            post_end = to_timestamp(post_cycle.get('postingEnd', ''))
            
            post_value = (
                f"**Cycle #{post_cycle.get('cycleNumber')}**\n\n"
                f"🔨 **Development Phase**\n"
                f"{dev_start} → {dev_end}\n\n"
                f"📤 **Posting Phase**\n"
                f"{post_start} → {post_end}"
            )
            embed.add_field(
                name="Current Posting Cycle",
                value=post_value,
                inline=False
            )
        
        embed.set_footer(text="Cycles are 2 weeks each • Development → Posting")
        
        return embed


async def setup(bot):
    """Setup function to add the cog to the bot."""
    await bot.add_cog(CycleCog(bot))
