"""
Core functionality and MarketingBot class for the Marketing Command Center Discord Bot
"""

import discord
from discord.ext import commands
import asyncio
import logging
from typing import Optional
import os
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
    
    async def setup_hook(self):
        """
        Called once before the bot connects to Discord.
        Register handlers that must work regardless of later startup steps.
        """
        from src.ui.views import EditRequestButton

        # Handles the edit button on every request message via its custom_id
        # (edit_request:<channel_id>), so no per-request registration or API
        # call is needed at startup.
        self.add_dynamic_items(EditRequestButton)
        logger.info("✅ Registered request edit button handler")
    
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

            # Load story request cog (pings roles on new story-request threads)
            try:
                await self.load_extension('src.commands.story_request_cog')
                logger.info("✅ Loaded story request cog")
            except Exception as e:
                logger.error(f"Error loading story request cog: {e}")

            # Load mock request cog (Anthropic-backed mock data generation)
            try:
                from src.commands.mock_cog import MockCog
                await self.add_cog(MockCog(self, request_manager=self.request_manager))
                logger.info("✅ Loaded mock command cog")
            except Exception as e:
                logger.error(f"Error loading mock cog: {e}")
            
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
        """Register persistent views.
        Request edit buttons are handled by EditRequestButton (see setup_hook)."""
        try:
            from src.ui.views import RequestView

            REQUEST_VIEW_MESSAGE_ID = int(os.getenv("REQUEST_VIEW_MESSAGE_ID"))
            request_view = RequestView(self.request_manager)
            self.add_view(request_view, message_id=REQUEST_VIEW_MESSAGE_ID)
            logger.info(f"✅ Registered RequestView for message {REQUEST_VIEW_MESSAGE_ID}")
            
        except Exception as e:
            logger.error(f"Error setting up persistent views: {e}")
    
    async def close(self):
        """Clean shutdown of the bot"""
        logger.info("Shutting down...")
        
        # Close database client
        await self.db.close()
        
        await super().close()
        logger.info("Shutdown Complete. Bye!")