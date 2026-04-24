import asyncio
import logging

from app import EndKonf
from config import load_config


async def main():
    config = load_config()

    logging.basicConfig(level=config.app.log_level)

    app = EndKonf(config)
    await app.run()


if __name__ == "__main__":
    asyncio.run(main())