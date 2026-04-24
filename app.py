import os

from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession

from routers.start import StartFeature
from routers.tiktok_r import TikTokRouter


class EndKonf:
    def __init__(self, config):
        self.config = config
        #session = AiohttpSession(proxy="http://127.0.0.1:2080")
        self.bot = Bot(token=config.bot.token)
        self.dp = Dispatcher()

        self._include_routers()

    def _include_routers(self):
        self.dp.include_router(
            StartFeature().router)
        self.dp.include_router(TikTokRouter().router)

    async def run(self):
        await self.dp.start_polling(self.bot)
