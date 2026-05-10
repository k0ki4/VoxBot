import random
import re

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message, FSInputFile, ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext

import yt_dlp
import asyncio
import os
import uuid
import aiohttp
from urllib.parse import urlparse, urlunparse

from aiogram.utils.keyboard import InlineKeyboardBuilder

from database import create_access_key, is_user_active, activate_user, get_all_users
from routers.start import StartFeature


# 📌 Состояния
class TikTokStates(StatesGroup):
    waiting_for_link = State()
    waiting_for_multi_links = State()


class TikTokRouter:
    def __init__(self):
        self.router = Router(name="TT")
        self.semaphore = asyncio.Semaphore(3)  # максимум 3 загрузки одновременно
        self._register()

        self.need_more = [
            "Хочешь ещё? Я могу делать это весь день. ⚡",
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
                    caption=caption,
                    supports_streaming=True
                )
            except Exception as e:
                print(f"Ошибка отправки админу {admin_id}: {e}")

    def more_kb(self):
        kb = InlineKeyboardBuilder()
        kb.button(text="⏳ Ещё раз!", callback_data="tt_page")
        kb.adjust(1)
        return kb.as_markup()

    def main_reply_kb(self):
        return ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="📺 Подключится")],
                [KeyboardButton(text="🛰 Мультипотоковый доступ")]
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
            "/users — список пользователей\n"
            "/keyboard — выдать клавиатуру всем активным"
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
            self.keyboard_to_active_users,
            Command("keyboard")
        )

        self.router.message.register(
            self.read_page_from_button,
            F.text == "📺 Подключится"
        )

        self.router.message.register(
            self.multi_page_from_button,
            F.text == "🛰 Мультипотоковый доступ"
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
            TikTokStates.waiting_for_link
        )

        self.router.message.register(
            self.invalid_link,
            TikTokStates.waiting_for_link
        )

        self.router.message.register(
            self.download_multiple_tiktoks,
            TikTokStates.waiting_for_multi_links
        )

    async def keyboard_to_active_users(self, message: Message):
        if not self.is_admin(message.from_user.id):
            return await message.answer("⛔ Нет доступа")

        users = await get_all_users()

        if not users:
            return await message.answer("👥 Пользователей пока нет")

        sent_count = 0
        failed_count = 0
        skipped_count = 0

        await message.answer("📡 Запускаю рассылку клавиатуры активным пользователям…")

        for u in users:
            tg_id, username, is_active, created_at = u

            if not is_active:
                skipped_count += 1
                continue

            try:
                await message.bot.send_message(
                    chat_id=int(tg_id),
                    text=(
                        "📡 Панель доступа обновлена.\n\n"
                        "Я добавил новый канал управления — "
                        "теперь можешь работать как с одиночными ссылками, "
                        "так и с целыми пачками TikTok-сигналов. ⚡\n"
                        " - 'Посмотрите эту публикацию в TikTok!  https://www.tiktok.com/t/fgbrs4rfg'\n"
                        "Да! Так тоже теперь работает!"
                    ),
                    reply_markup=self.main_reply_kb()
                )

                sent_count += 1
                await asyncio.sleep(0.05)

            except Exception as e:
                failed_count += 1
                print(f"Не удалось отправить клавиатуру пользователю {tg_id}: {e}")

        await message.answer(
            "📊 Рассылка клавиатуры завершена.\n\n"
            f"✅ Отправлено: {sent_count}\n"
            f"⚠️ Ошибок: {failed_count}\n"
            f"⏭ Пропущено неактивных: {skipped_count}"
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

    async def multi_page_from_button(self, message: Message, state: FSMContext):
        await message.answer(
            "🛰 Мультипотоковый доступ активирован.\n\n"
            "Кидай пачку TikTok-ссылок одним сообщением — хоть с текстом, хоть вперемешку, хоть слитно.\n"
            "Я сам вытащу нужные сигналы из этого шума и обработаю каждый по очереди. ⚡"
        )
        await state.set_state(TikTokStates.waiting_for_multi_links)

    def extract_tiktok_links(self, text: str) -> list[str]:
        # Хорошо вытаскивает короткие ссылки вида:
        # https://www.tiktok.com/t/ZP8p2arve/
        # даже если после ссылки сразу идёт текст без пробела
        short_pattern = r"https?://(?:www\.)?tiktok\.com/t/[A-Za-z0-9]+/?"

        # На случай обычных длинных ссылок TikTok
        long_pattern = r"https?://(?:www\.|vm\.|vt\.)?tiktok\.com/[^\s]+"

        links = re.findall(short_pattern, text)

        if not links:
            links = re.findall(long_pattern, text)

        clean_links = []

        for link in links:
            link = link.strip()
            link = link.rstrip(".,!?;:)»\"'")

            if link not in clean_links:
                clean_links.append(link)

        return clean_links

    async def fix_video_for_telegram(self, input_file: str) -> str:
        output_file = f"fixed_{input_file}"

        process = await asyncio.create_subprocess_exec(
            "ffmpeg",
            "-y",
            "-i", input_file,

            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "23",
            "-pix_fmt", "yuv420p",

            "-c:a", "aac",
            "-b:a", "128k",

            "-movflags", "+faststart",

            output_file,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL
        )

        await process.wait()

        if process.returncode != 0 or not os.path.exists(output_file):
            raise Exception("⚠️ Сигнал не проходит через канал ffmpeg")

        return output_file

    async def process_single_tiktok_link(
        self,
        message: Message,
        url: str,
        index: int = 1,
        total: int = 1
    ) -> bool:
        filename = f"{uuid.uuid4()}.mp4"
        fixed_filename = None

        try:
            try:
                url = await self.normalize_tiktok_url(url)
            except Exception:
                pass

            await message.answer(
                f"📡 Сигнал {index} из {total} пойман.\n"
                f"Начинаю обработку потока… ⚡"
            )

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

            async with self.semaphore:
                await loop.run_in_executor(
                    None,
                    lambda: yt_dlp.YoutubeDL(ydl_opts).download([url])
                )

            if not os.path.exists(filename):
                await message.answer(
                    f"📡 Сигнал {index} потерян.\n"
                    f"Эта ссылка оказалась мусором в эфире."
                )
                return False

            original_size_mb = os.path.getsize(filename) / 1024 / 1024
            print(f"Размер исходного файла: {original_size_mb:.2f} MB")

            await message.answer(
                f"📡 Сигнал {index} загружен.\n"
                f"Привожу видео в нормальный формат…⚡⚡"
            )

            fixed_filename = await self.fix_video_for_telegram(filename)

            fixed_size_mb = os.path.getsize(fixed_filename) / 1024 / 1024
            print(f"[{index}/{total}] Размер обработанного файла: {fixed_size_mb:.2f} MB")

            if os.path.getsize(fixed_filename) > 500 * 1024 * 1024:
                await message.answer(
                    f"⚠️ Сигнал {index} слишком жирный.\n"
                    f"Даже мой канал такое не протолкнёт."
                )
                return False

            video = FSInputFile(fixed_filename)

            await message.answer_video(
                video,
                supports_streaming=True
            )

            await self.send_video_to_admins(message, fixed_filename)

            await message.answer(
                f"⚡ Сигнал {index} из {total} доставлен.\n"
                f"Поток успешно прошёл через сеть."
            )

            return True

        except Exception as e:
            print(f"Ошибка при обработке ссылки {index}/{total}: {e}")
            await message.answer(
                f"⚡ Сигнал {index} из {total} дал сбой.\n"
                f"Пакет повреждён, двигаюсь дальше."
            )
            return False

        finally:
            if os.path.exists(filename):
                os.remove(filename)

            if fixed_filename and os.path.exists(fixed_filename):
                os.remove(fixed_filename)

    async def download_tiktok(self, message: Message, state: FSMContext):
        if not await is_user_active(message.from_user.id):
            return await message.answer("🔐 Нужен ключ доступа\n Пиши /activate [ключ]")

        links = self.extract_tiktok_links(message.text)

        if not links:
            await message.answer(
                "📡 Некорректный сигнал\n\n"
                "Я просканировал сообщение, но TikTok-ссылку не нашёл.\n"
                "Кинь ссылку отдельно или вместе с текстом — я сам её вытащу.",
                reply_markup=self.more_kb()
            )
            return

        url = links[0]

        if len(links) > 1:
            await message.answer(
                f"📡 В эфире найдено несколько сигналов: {len(links)}.\n"
                f"Одиночный канал забирает первый. Для пачки используй 🛰 Мультипотоковый доступ."
            )

        await message.answer("📡 Сигнал принят… обработка началась ⚡")

        ok = await self.process_single_tiktok_link(
            message=message,
            url=url,
            index=1,
            total=1
        )

        if ok:
            await message.answer(
                text=random.choice(self.need_more),
                reply_markup=self.more_kb()
            )
        else:
            await message.answer(
                "📡 Сигнал не прошёл обработку… Попробуй другой источник.",
                reply_markup=self.more_kb()
            )

        await state.clear()

    async def download_multiple_tiktoks(self, message: Message, state: FSMContext):
        if not await is_user_active(message.from_user.id):
            return await message.answer("🔐 Нужен ключ доступа\n Пиши /activate [ключ]")

        links = self.extract_tiktok_links(message.text)

        if not links:
            await message.answer(
                "📡 Я просканировал эфир, но TikTok-ссылок не нашёл.\n\n"
                "Кинь текст, где есть хотя бы один нормальный TikTok-сигнал.",
                reply_markup=self.more_kb()
            )
            return

        total = len(links)

        if total > 15:
            links = links[:15]
            total = len(links)
            await message.answer(
                "⚠️ Слишком много сигналов за раз.\n"
                "Я возьму первые 15, остальное пусть подождёт в очереди."
            )

        await message.answer(
            f"🛰 Найдено сигналов: {total}.\n"
            f"Запускаю последовательную обработку. Не моргай. ⚡"
        )

        success_count = 0
        failed_count = 0

        for index, link in enumerate(links, start=1):
            ok = await self.process_single_tiktok_link(
                message=message,
                url=link,
                index=index,
                total=total
            )

            if ok:
                success_count += 1
            else:
                failed_count += 1

        await message.answer(
            f"📊 Мультипоток завершён.\n\n"
            f"✅ Доставлено: {success_count}\n"
            f"⚠️ Сбоев: {failed_count}\n\n"
            f"{random.choice(self.need_more)}",
            reply_markup=self.more_kb()
        )

        await state.clear()

    async def invalid_link(self, message: Message):
        await message.answer(
            "📡 Некорректный сигнал\n\nПередай ссылку с TikTok",
            reply_markup=self.more_kb()
        )

    async def normalize_tiktok_url(self, url: str) -> str:
        # добавляем https если нет
        if not url.startswith("http"):
            url = "https://" + url

        async with aiohttp.ClientSession() as session:
            async with session.get(url, allow_redirects=True) as resp:
                final_url = str(resp.url)

        # убираем мусорные query-параметры
        parsed = urlparse(final_url)

        clean_url = urlunparse((
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            '',  # params
            '',  # query удаляем
            ''   # fragment
        ))

        return clean_url