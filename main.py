"""
Main entry point for the Marketing Command Centre Discord Bot.
"""

import os
import asyncio
import logging
from dotenv import load_dotenv

from src.core.bot import MarketingBot


def setup_logging():
    """Configure logging for the application."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler('bot.log', encoding='utf-8')
        ],
        force=True  # Override any handlers configured during module imports
    )


def load_environment():
    """Load environment variables from .env file."""
    load_dotenv()
    
    token = os.getenv('DISCORD_TOKEN')
    if not token:
        raise ValueError("DISCORD_TOKEN not found in environment variables!")
    
    return token


async def main():
    """Main function to run the bot."""
    # Setup logging
    setup_logging()
    logger = logging.getLogger(__name__)
    
    try:
        # Load environment variables
        token = load_environment()
        logger.info("✅ Environment variables loaded successfully")
        
        # Create and run the bot
        bot = MarketingBot()
        logger.info("🤖 Starting Marketing Command Centre Bot...")
        
        await bot.start(token)
        
    except KeyboardInterrupt:
        logger.info("🛑 Bot shutdown requested by user")
    except Exception as e:
        logger.error(f"❌ Critical error: {e}")
        raise
    finally:
        if 'bot' in locals():
            await bot.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Bot shutdown complete")
    except Exception as e:
        print(f"❌ Failed to start bot: {e}")
        exit(1)