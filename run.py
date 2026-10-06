import sys
import logging
from bot.config import Config
from bot.client import TracgerBot

def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    # Silence overly verbose discord gateway logs
    logging.getLogger("discord.gateway").setLevel(logging.WARNING)

def main():
    setup_logging()
    logger = logging.getLogger("Tracger")

    try:
        config = Config.from_env()
    except Exception as e:
        logger.error(f"Configuration error: {e}")
        logger.error("Please create a .env file based on .env.example with your DISCORD_TOKEN.")
        sys.exit(1)

    logger.info("Initializing Tracger bot...")
    bot = TracgerBot(config)

    try:
        bot.run(config.token)
    except KeyboardInterrupt:
        logger.info("Shutdown signal received. Goodbye!")
    except Exception as e:
        logger.error(f"Fatal error while running bot: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
