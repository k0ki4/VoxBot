import aiosqlite
from datetime import datetime
import secrets

DB_PATH = "bot.db"


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
        CREATE TABLE IF NOT EXISTS users (
            telegram_id INTEGER PRIMARY KEY,
            username TEXT,
            is_active INTEGER DEFAULT 0,
            created_at TEXT
        )
        """)

        await db.execute("""
        CREATE TABLE IF NOT EXISTS access_keys (
            key TEXT PRIMARY KEY,
            is_used INTEGER DEFAULT 0,
            used_by INTEGER,
            created_at TEXT
        )
        """)

        await db.execute("""
        CREATE TABLE IF NOT EXISTS admins (
            telegram_id INTEGER PRIMARY KEY,
            created_at TEXT
        )
        """)

        await db.commit()


async def create_access_key():
    key = secrets.token_urlsafe(12)

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO access_keys (key, created_at) VALUES (?, ?)",
            (key, datetime.utcnow().isoformat())
        )
        await db.commit()

    return key


async def activate_user(key: str, telegram_id: int, username: str | None):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT is_used FROM access_keys WHERE key = ?",
            (key,)
        )
        row = await cursor.fetchone()

        if not row:
            return False, "Пусто ❌ Найди новый, если сможешь"

        if row[0]:
            return False, "Повторно не получится 🚫 Система не настолько глупа"

        await db.execute("""
        INSERT OR REPLACE INTO users 
        (telegram_id, username, is_active, created_at)
        VALUES (?, ?, 1, ?)
        """, (telegram_id, username, datetime.utcnow().isoformat()))

        await db.execute("""
        UPDATE access_keys
        SET is_used = 1, used_by = ?
        WHERE key = ?
        """, (telegram_id, key))

        await db.commit()

    return True, "Доступ выдан 🔓 Не заставляй меня пожалеть об этом"


async def is_user_active(telegram_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT is_active FROM users WHERE telegram_id = ?",
            (telegram_id,)
        )
        row = await cursor.fetchone()

    return bool(row and row[0])

async def get_all_users():
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("""
        SELECT telegram_id, username, is_active, created_at
        FROM users
        ORDER BY created_at DESC
        """)
        rows = await cursor.fetchall()

    return rows