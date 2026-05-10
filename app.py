import os

from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer

from routers.start import StartFeature
from routers.tiktok_r import TikTokRouter


class EndKonf:
    def __init__(self, config):
        self.config = config

        local_server = TelegramAPIServer.from_base(
            "http://127.0.0.1:8081"
        )

        session = AiohttpSession(api=local_server)

        self.bot = Bot(
            token=config.bot.token,
            session=session
        )

        self.dp = Dispatcher()

        self._include_routers()

    def _include_routers(self):
        self.dp.include_router(StartFeature().router)
        self.dp.include_router(TikTokRouter().router)

    async def run(self):
        await self.dp.start_polling(self.bot)