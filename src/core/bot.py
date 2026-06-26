"""
Core functionality and MarketingBot class for the Marketing Command Center Discord Bot
"""

import discord
from discord.ext import commands
import asyncio
import logging
from typing import Optional
import traceback

from src.commands.snow_cog import SnowDayCog
from src.commands.request_cog import RequestCog
from src.services.request_manager import RequestManager
from src.client.database_client import DatabaseClient

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class MarketingBot(commands.Bot):
    """
    Main bot class for the Marketing Command Centre Discord Bot.
    """
    db: DatabaseClient
    
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        
        super().__init__(
            command_prefix='!',
            intents=intents,
            help_command=None
        )
        
        # Initialize database client
        self.db = DatabaseClient(bot_auth=False)
        self.request_manager = RequestManager(self, self.db)
    
    
    async def on_ready(self):
        """
        Called when the bot has successfully connected to Discord.
        Start background tasks and sync commands.
        """
        logger.info(f'{self.user} has connected to Discord!')
        logger.info(f'Bot is in {len(self.guilds)} server(s)')
        
        try:
            # Load the request cog
            await self.add_cog(RequestCog(self, request_manager=self.request_manager))

            await self.add_cog(SnowDayCog(self))

            logger.info("✅ Loaded request command cog")

            await self.load_extension('src.commands.cycle_cog')
            logger.info("✅ Loaded cycle command cog")
            
            # Load utils cog for daily reminders and VC forking
            try:
                from src.commands.utils_cog import UtilsCog
                await self.add_cog(UtilsCog(self, request_manager=self.request_manager))
                logger.info("✅ Loaded utils cog")
            except Exception as e:
                logger.error(f"Error loading utils cog: {e}")
            
            # Load content outline cog
            try:
                await self.load_extension('src.commands.content_outline_cog')
                logger.info("✅ Loaded content outline cog")
            except Exception as e:
                logger.error(f"Error loading content outline cog: {e}")

            # Load config management cog
            try:
                await self.load_extension('src.commands.config_cog')
                logger.info("✅ Loaded config command cog")
            except Exception as e:
                logger.error(f"Error loading config cog: {e}")
            
            # Register persistent views for edit buttons
            await self._setup_persistent_views()
            
            # Sync commands with Discord
            synced = await self.tree.sync()
            logger.info(f"Synced {len(synced)} slash command(s)")

            # Set the bots rich presence
            await self.change_presence(
                activity=discord.Activity(
                    type=discord.ActivityType.watching,
                    name="Marketing Requests"
                )
            )
            
        except Exception as e:
            logger.error(f"Error loading cogs or syncing commands: {e}")
    
    async def _setup_persistent_views(self):
        """Register persistent views for existing requests.
        Optimized to batch-register views without individual Discord API calls."""
        try:
            from src.ui.views import RequestEditView, RequestView

            # Register the request-board view globally. Because its buttons use
            # static custom_ids, this handler works for any message hosting it
            # (e.g. the one posted via /setup-requests) and survives restarts —
            # no need to track a specific message id.
            self.add_view(RequestView(self.request_manager))
            logger.info("✅ Registered persistent RequestView")

            # Get all requests from database in a single call
            all_requests = await self.db.get_all_requests()
            
            # Batch register views - this doesn't make API calls, just registers handlers
            registered_count = 0
            for request in all_requests:
                if request.channel_id and request.requester_id:
                    view = RequestEditView(
                        requester_id=request.requester_id,
                        request_type=request.type.value,
                        channel_id=request.channel_id,
                        request_manager=self.request_manager
                    )
                    self.add_view(view)
                    registered_count += 1
            
            logger.info(f"Registered {registered_count} request edit view(s)")
            
        except Exception as e:
            logger.error(f"Error setting up persistent views: {e}")
    
    async def close(self):
        """Clean shutdown of the bot"""
        logger.info("Shutting down...")
        
        # Close database client
        await self.db.close()
        
        await super().close()
        logger.info("Shutdown Complete. Bye!")