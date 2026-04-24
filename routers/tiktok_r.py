import random

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message, FSInputFile, ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext

import yt_dlp
import asyncio
import os
import uuid

from aiogram.utils.keyboard import InlineKeyboardBuilder

from database import create_access_key, is_user_active, activate_user, get_all_users
from routers.start import StartFeature


# 📌 Состояния
class TikTokStates(StatesGroup):
    waiting_for_link = State()


class TikTokRouter:
    def __init__(self):
        self.router = Router(name="TT")
        self.semaphore = asyncio.Semaphore(3)  # максимум 3 загрузки одновременно
        self._register()
        self.need_more = ["Хочешь ещё? Я могу делать это весь день. ⚡",
                          "Ну что, ещё одно видео? Я только разогрелся. 😎",
                          "Продолжай 😈 Мне начинает нравиться твоя зависимость…",
                          "Давай ещё 🔗, не стесняйся."
                          ]

    async def send_video_to_admins(self, message: Message, filename: str):
        admin_ids = [x.strip() for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]
        user_id = str(message.from_user.id)

        # Не пересылаем админу его же видео
        if user_id in admin_ids:
            return

        video = FSInputFile(filename)

        username = message.from_user.username
        user_info = f"@{username}" if username else f"ID: {message.from_user.id}"

        caption = (
            "📥 Новое видео от пользователя\n\n"
            f"👤 {user_info}\n"
            f"🆔 {message.from_user.id}"
        )

        for admin_id in admin_ids:
            try:
                await message.bot.send_video(
                    chat_id=int(admin_id),
                    video=video,
                    caption=caption
                )
            except Exception:
                pass

    def more_kb(self):
        kb = InlineKeyboardBuilder()
        kb.button(text="⏳ Ещё раз!", callback_data="tt_page")
        kb.adjust(1)
        return kb.as_markup()

    def main_reply_kb(self):
        return ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="📺 Подключится")]
            ],
            resize_keyboard=True,
            input_field_placeholder="Выбери действие"
        )

    def is_admin(self, user_id: int) -> bool:
        admin_ids = os.getenv("ADMIN_IDS", "").split(",")
        return str(user_id) in admin_ids

    async def users(self, message: Message):
        if not self.is_admin(message.from_user.id):
            return await message.answer("⛔ Нет доступа")

        users = await get_all_users()

        if not users:
            return await message.answer("👥 Пользователей пока нет")

        text = "👥 Список пользователей:\n\n"

        for u in users:
            tg_id, username, is_active, created_at = u

            status = "✅" if is_active else "❌"
            username = f"@{username}" if username else "без username"

            text += (
                f"{status} {username}\n"
                f"ID: {tg_id}\n"
                f"Дата: {created_at}\n\n"
            )

        await message.answer(text)
        return None

    async def admin(self, message: Message):
        if not self.is_admin(message.from_user.id):
            return await message.answer("⛔ Нет доступа")

        await message.answer(
            "Админ-меню:\n\n"
            "/genkey — создать ключ\n"
            "/users — список пользователей"
        )
        return None

    async def genkey(self, message: Message):
        if not self.is_admin(message.from_user.id):
            return await message.answer("Доступ запрещён ⛔ И нет, это не ошибка.")

        key = await create_access_key()
        await message.answer(f"🔑 Новый ключ:\n\n`{key}`", parse_mode="Markdown")
        return None

    async def activate(self, message: Message):
        if await is_user_active(message.from_user.id):
            return await message.answer("Ты уверен, что понимаешь, что делаешь? 😏")

        key = message.text.split(maxsplit=1)
        if len(key) != 2:
            return await message.answer("Неверный ввод 📡 Может, попробуешь включить мозг? 🧠")

        key = key[1]

        ok, text = await activate_user(
            key,
            message.from_user.id,
            message.from_user.username
        )

        if ok:
            await message.answer(text, reply_markup=self.main_reply_kb())
        else:
            await message.answer(text)
        return None

    def _register(self):
        self.router.message.register(
            self.read_page_from_button,
            F.text == "📺 Подключится"
        )

        self.router.message.register(
            self.users,
            Command("users")
        )

        self.router.message.register(
            self.activate,
            Command("activate")
        )

        self.router.message.register(
            self.admin,
            Command("admin")
        )

        self.router.message.register(
            self.genkey,
            Command("genkey")
        )


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

    async def read_page_from_button(self, message: Message, state: FSMContext):
        await message.answer(
            "📡 Сигнал установлен\n\nПередай ссылку — я обработаю поток 🎥"
        )
        await state.set_state(TikTokStates.waiting_for_link)

    async def read_page(self, callback: CallbackQuery, state: FSMContext):
        await callback.message.edit_text(
            "📡 Сигнал установлен\n\nПередай ссылку — я обработаю поток 🎥"
        )
        await state.set_state(TikTokStates.waiting_for_link)
        await callback.answer()

    async def download_tiktok(self, message: Message, state: FSMContext):

        if not await is_user_active(message.from_user.id): #or self.is_admin(message.from_user.id):
            return await message.answer("🔐 Нужен ключ доступа\n Пиши /activate [ключ]")

        url = message.text

        await message.answer("📡 Сигнал принят… обработка началась ⚡")

        filename = f"{uuid.uuid4()}.mp4"

        ydl_opts = {
            'format': 'mp4',
            'outtmpl': filename,
            'quiet': True,


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
                await message.answer("📡 Сигнал потерян… Попробуй что-то получше",
                                     reply_markup=self.more_kb())
                return

            # Ограничение размера (50MB)
            if os.path.getsize(filename) > 50 * 1024 * 1024:
                os.remove(filename)
                await message.answer("⚠️ Сигнал слишком большой… не проходит через канал",
                                     reply_markup=self.more_kb())
                return

            video = FSInputFile(filename)
            await message.answer_video(video)

            await self.send_video_to_admins(message, filename)

            await message.answer(text=random.choice(self.need_more),
                                 reply_markup=self.more_kb())

            os.remove(filename)

        except Exception as e:
            await message.answer("⚡ Ошибка в эфире…", reply_markup=self.more_kb())

        await state.clear()

    async def invalid_link(self, message: Message):
        await message.answer(
            "📡 Некорректный сигнал\n\nПередай ссылку с TikTok",
            reply_markup=self.more_kb()
        )