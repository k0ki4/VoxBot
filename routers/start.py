from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from textwrap import dedent

class StartFeature:
    def __init__(self):
        self.router = Router(name="start")
        self._register()

    def _register(self):
        self.router.message.register(self.start, CommandStart())

    async def start(self, message: Message):
        kb = InlineKeyboardBuilder()
        kb.button(text="📺 Обработать сигнал", callback_data="tt_page")

        kb.adjust(1)

        await message.answer(
            dedent("⚡ Ты подключился к моему каналу. Здесь нет шума — только чистый контент."),
            reply_markup=kb.as_markup(),
        )

