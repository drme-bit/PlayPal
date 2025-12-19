from discord import app_commands
from discord.ext import commands, tasks
from discord.ui import View, button, Button
import discord
import time
from datetime import date
from database.db import get_connection
from utils.logger import setup_logger, log_user_activity

logger = setup_logger()

# --------------------------------------
# VIEW ДЛЯ ЛИДЕРБОРДА
# --------------------------------------
class LeaderboardView(View):
    def __init__(self, bot, server_id):
        super().__init__(timeout=None)
        self.bot = bot
        self.server_id = server_id
        self.current_scope = "streak"

    async def update_leaderboard(self, interaction: discord.Interaction):
        embed = await Activity.generate_leaderboard_embed(self.bot, self.server_id, self.current_scope)
        await interaction.response.edit_message(embed=embed, view=self)

    @button(label="Стрики", style=discord.ButtonStyle.primary)
    async def streak_button(self, interaction: discord.Interaction, button: Button):
        self.current_scope = "streak"
        await self.update_leaderboard(interaction)

    @button(label="Поинты", style=discord.ButtonStyle.secondary)
    async def points_button(self, interaction: discord.Interaction, button: Button):
        self.current_scope = "points"
        await self.update_leaderboard(interaction)

# --------------------------------------
# КОГ ДЛЯ АКТИВНОСТИ
# --------------------------------------
class Activity(commands.Cog):
    DAILY_MAX_POINTS = 50  # максимум валюты в день
    MSG_POINTS = 0.1
    VOICE_POINTS_PER_MIN = 0.05  # 0.5 за 10 минут

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.voice_sessions = {}  # server_id -> {user_id: start_time}
        self.update_voice_activity.start()

    def cog_unload(self):
        self.update_voice_activity.cancel()

    def _today_str(self) -> str:
        return date.today().isoformat()

    # --------------------------------------
    # Добавление пользователя
    # --------------------------------------
    def add_user(self, user_id: int, server_id: int):
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO users(user_id, server_id, join_date)
            VALUES (%s, %s, NOW())
            ON CONFLICT(user_id, server_id) DO NOTHING
        """, (user_id, server_id))
        conn.commit()
        conn.close()

    # --------------------------------------
    # Подготовка для сегодняшней активности
    # --------------------------------------
    def _rollover_and_prepare_today(self, user_id: int, server_id: int, conn):
        cur = conn.cursor()
        today = self._today_str()
        cur.execute("""
            INSERT INTO user_activity_daily(user_id, server_id, date)
            VALUES (%s, %s, %s)
            ON CONFLICT(user_id, server_id, date) DO NOTHING
        """, (user_id, server_id, today))

    # --------------------------------------
    # Начисление очков
    # --------------------------------------
    # --------------------------------------
    # Универсальная функция начисления активности
    # --------------------------------------

    def _add_activity(self, user_id: int, server_id: int, msg_inc: int = 0, voice_minutes_inc: int = 0):
        """
        Начисляет:
        - activity points (user_activity_totals/daily)
        - streak
        - ограниченные points (валюта) в таблице users
        """
        self.add_user(user_id, server_id)
        today = self._today_str()

        # базовые коэффициенты
        ACTIVITY_PER_MSG = 0.1
        ACTIVITY_PER_VOICE_MIN = 0.05
        XP_PER_MSG = 5
        XP_PER_VOICE_MIN = 1
        CURRENCY_RATIO = 1.0  # 1 активность = 1 валюта (до лимита)

        # начисления
        activity_points = msg_inc * ACTIVITY_PER_MSG + voice_minutes_inc * ACTIVITY_PER_VOICE_MIN
        xp = msg_inc * XP_PER_MSG + voice_minutes_inc * XP_PER_VOICE_MIN

        conn = get_connection()
        cur = conn.cursor()

        # --- totals (активность) ---
        cur.execute("""
            INSERT INTO user_activity_totals(user_id, server_id, messages, voice_minutes, points, xp, last_activity_date)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT(user_id, server_id) DO UPDATE SET
                messages = user_activity_totals.messages + EXCLUDED.messages,
                voice_minutes = user_activity_totals.voice_minutes + EXCLUDED.voice_minutes,
                points = user_activity_totals.points + EXCLUDED.points,
                xp = user_activity_totals.xp + EXCLUDED.xp,
                last_activity_date = EXCLUDED.last_activity_date
        """, (user_id, server_id, msg_inc, voice_minutes_inc, activity_points, xp, today))

        # --- daily (активность) ---
        cur.execute("""
            INSERT INTO user_activity_daily(user_id, server_id, date, messages, voice_minutes, points, xp)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT(user_id, server_id, date) DO UPDATE SET
                messages = user_activity_daily.messages + EXCLUDED.messages,
                voice_minutes = user_activity_daily.voice_minutes + EXCLUDED.voice_minutes,
                points = user_activity_daily.points + EXCLUDED.points,
                xp = user_activity_daily.xp + EXCLUDED.xp
        """, (user_id, server_id, today, msg_inc, voice_minutes_inc, activity_points, xp))

        # --- ограниченное начисление валюты ---
        cur.execute("""
            SELECT COALESCE(SUM(points), 0)
            FROM user_activity_daily
            WHERE user_id = %s AND server_id = %s AND date = %s
        """, (user_id, server_id, today))
        today_activity = cur.fetchone()[0]

        # сколько валюты можно начислить (лимит в день)
        if today_activity <= self.DAILY_MAX_POINTS:
            allowed_points = min(activity_points, self.DAILY_MAX_POINTS - today_activity)
            if allowed_points > 0:
                cur.execute("""
                    UPDATE users
                    SET points = points + %s
                    WHERE user_id = %s AND server_id = %s
                """, (allowed_points * CURRENCY_RATIO, user_id, server_id))

        # --- стрики ---
        cur.execute("""
            SELECT last_activity_date, streak FROM user_activity_totals
            WHERE user_id = %s AND server_id = %s
        """, (user_id, server_id))
        row = cur.fetchone()
        streak = 1
        if row and row[0]:
            last_date = row[0]
            streak = row[1] or 0
            if (date.fromisoformat(today) - last_date).days == 1:
                streak += 1
            elif (date.fromisoformat(today) - last_date).days > 1:
                streak = 1
        cur.execute("""
            UPDATE user_activity_totals
            SET streak = %s
            WHERE user_id = %s AND server_id = %s
        """, (streak, user_id, server_id))

        conn.commit()
        conn.close()
        return activity_points, xp, streak

    # --------------------------------------
    # Слушатели сообщений
    # --------------------------------------

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        points, xp, streak = self._add_activity(message.author.id, message.guild.id, msg_inc=1)
        log_user_activity(message.author, message.guild.id, "Message", points, context=message.content)
        logger.info(f"{message.author}: +{points:.2f} pts | +{xp} XP | стрик {streak}")

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if not member.guild:
            return
        server_id = member.guild.id
        if server_id not in self.voice_sessions:
            self.voice_sessions[server_id] = {}
        user_sessions = self.voice_sessions[server_id]

        # пользователь зашел
        if before.channel is None and after.channel is not None:
            user_sessions[member.id] = time.time()

        # пользователь вышел
        elif before.channel is not None and after.channel is None and member.id in user_sessions:
            start = user_sessions.pop(member.id)
            minutes = int((time.time() - start) / 60)
            if minutes > 0:
                points, xp, streak = self._add_activity(member.id, server_id, voice_minutes_inc=minutes)
                log_user_activity(member, server_id, "VoiceCall", points, context=f"{minutes} мин")
                logger.info(f"{member}: +{points:.2f} pts | +{xp} XP | стрик {streak}")

    @tasks.loop(minutes=1)
    async def update_voice_activity(self):
        now = time.time()
        for server_id, sessions in self.voice_sessions.items():
            for user_id, start in list(sessions.items()):
                minutes = int((now - start) / 60)
                if minutes > 0:
                    points, xp, streak = self._add_activity(user_id, server_id, voice_minutes_inc=minutes)
                    log_user_activity(user_id, server_id, "VoiceCall", points, context=f"{minutes} мин")
                    sessions[user_id] = now
                    logger.info(f"user_id={user_id} | server_id={server_id} | +{points:.2f} pts | +{xp} XP | стрик {streak}")

        # --------------------------------------
        # Команды
        # --------------------------------------
    @app_commands.command(name="leaderboard", description="Лидерборд сервера")
    async def leaderboard(self, interaction: discord.Interaction):
        view = LeaderboardView(self.bot, interaction.guild.id)
        embed = await self.generate_leaderboard_embed(self.bot, interaction.guild.id, "streak")
        await interaction.response.send_message(embed=embed, view=view)

    @staticmethod
    async def generate_leaderboard_embed(bot, server_id: int, scope: str):
        conn = get_connection()
        cur = conn.cursor()
        if scope == "streak":
            cur.execute("""
                SELECT user_id, streak, points
                FROM user_activity_totals
                WHERE server_id = %s
                ORDER BY streak DESC
                LIMIT 10
            """, (server_id,))
        elif scope == "points":
            cur.execute("""
                SELECT user_id, points, streak
                FROM users
                WHERE server_id = %s
                ORDER BY points DESC
                LIMIT 10
            """, (server_id,))
        rows = cur.fetchall()
        conn.close()

        embed = discord.Embed(title=f"🏆 Лидерборд сервера ({scope})", color=discord.Color.gold())
        for i, row in enumerate(rows, start=1):
            user = await bot.fetch_user(row[0])
            streak, points = (row[1], row[2]) if scope == "streak" else (row[2], row[1])
            embed.add_field(name=f"{i}. {user.display_name}", value=f"Стрик: {streak} — Поинты: {points:.2f}", inline=False)
        return embed