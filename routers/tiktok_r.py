from aiogram import Router, F
from aiogram.types import CallbackQuery, Message, FSInputFile
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext

import yt_dlp
import asyncio
import os
import uuid


# 📌 Состояния
class TikTokStates(StatesGroup):
    waiting_for_link = State()


class TikTokRouter:
    def __init__(self):
        self.router = Router(name="TT")
        self.semaphore = asyncio.Semaphore(3)  # максимум 3 загрузки одновременно
        self._register()

    def _register(self):
        self.router.callback_query.register(
            self.read_page,
            F.data == "tt_page"
        )

        self.router.message.register(
            self.download_tiktok,
            TikTokStates.waiting_for_link,
            F.text.regexp(r"(https?://)?(www\.)?tiktok\.com/")
        )

        self.router.message.register(
            self.invalid_link,
            TikTokStates.waiting_for_link
        )

    async def read_page(self, callback: CallbackQuery, state: FSMContext):
        await callback.message.edit_text(
            "📡 Сигнал установлен\n\nПередай ссылку — я обработаю поток 🎥"
        )
        await state.set_state(TikTokStates.waiting_for_link)
        await callback.answer()

    async def download_tiktok(self, message: Message, state: FSMContext):
        url = message.text

        await message.answer("📡 Сигнал принят… обработка началась ⚡")

        filename = f"{uuid.uuid4()}.mp4"

        ydl_opts = {
            'format': 'mp4',
            'outtmpl': filename,
            'quiet': True,

            # ❗ ВСТАВЬ СВОЙ ПРОКСИ
            'proxy': 'socks5://timeweb:timeweb@95.140.152.151:25344',

            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36',
                'Accept-Language': 'en-US,en;q=0.9',
            },

            'retries': 3,
            'fragment_retries': 3,
            'noplaylist': True,
        }

        loop = asyncio.get_running_loop()

        try:
            async with self.semaphore:
                await loop.run_in_executor(
                    None,
                    lambda: yt_dlp.YoutubeDL(ydl_opts).download([url])
                )

            if not os.path.exists(filename):
                await message.answer("📡 Сигнал потерян… попробуй снова")
                return

            # 📏 Ограничение размера (50MB)
            if os.path.getsize(filename) > 50 * 1024 * 1024:
                os.remove(filename)
                await message.answer("⚠️ Сигнал слишком большой… не проходит через канал")
                return

            video = FSInputFile(filename)
            await message.answer_video(video)

            os.remove(filename)

        except Exception as e:
            await message.answer("⚡ Ошибка в эфире… попробуй ещё раз")

        await state.clear()

    async def invalid_link(self, message: Message):
        await message.answer(
            "📡 Некорректный сигнал\n\nПередай ссылку с TikTok"
        )