import logging
from discord.ext import commands
import discord

from utils.logger import setup_logger
from database.db import init_db, get_connection
from discord_commands import activity, user

# Загружаем токен (лучше через .env)
import os
from dotenv import load_dotenv
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

# Логгер
logger = setup_logger()

# Настройка бота
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.voice_states = True

bot = commands.Bot(command_prefix="!", intents=intents)

# Инициализация базы
init_db()

# Подключаем команды
async def load_extensions():
    await bot.add_cog(activity.Activity(bot))
    await bot.add_cog(user.User(bot))

@bot.event
async def on_ready():
    for guild in bot.guilds:
        # Добавляем сервер
        conn = get_connection()
        cur = conn.cursor()
        # Добавляем сервер
        cur.execute("""
            INSERT INTO servers(server_id, name, created_at)
            VALUES (%s, %s, NOW())
            ON CONFLICT(server_id) DO NOTHING
        """, (guild.id, guild.name))

        # Добавляем пользователей
        for member in guild.members:
            if not member.bot:
                cur.execute("""
                    INSERT INTO users(user_id, server_id, join_date)
                    VALUES (%s, %s, NOW())
                    ON CONFLICT(user_id, server_id) DO NOTHING
                """, (member.id, guild.id))
        conn.commit()
        conn.close()
    await bot.tree.sync()
    logger.info(f"Бот запущен как {bot.user}")

@bot.event
async def on_member_join(member):
    if member.bot:
        return
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
            INSERT INTO users(user_id, server_id, join_date)
        VALUES (%s, %s, NOW())
        ON CONFLICT(user_id, server_id) DO NOTHING
    """, (member.id, member.guild.id))
    conn.commit()
    conn.close()

@bot.event
async def on_guild_join(guild):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
            INSERT INTO servers(server_id, name, created_at)
            VALUES (%s, %s, NOW())
            ON CONFLICT(server_id) DO NOTHING
        """, (guild.id, guild.name))
    for member in guild.members:
        if not member.bot:
            cur.execute("""
                INSERT INTO users(user_id, server_id, join_date)
                VALUES (%s, %s, NOW())
                ON CONFLICT(user_id, server_id) DO NOTHING
            """, (member.id, guild.id))
    conn.commit()
    conn.close()


async def main():
    async with bot:
        await load_extensions()
        await bot.start(TOKEN)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())