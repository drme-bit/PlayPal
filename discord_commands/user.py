import discord
from discord.ext import commands
from discord import app_commands, ui
from database.db import get_connection


class ShopView(ui.View):
    def __init__(self, items, page=0):
        super().__init__(timeout=60)
        self.items = items
        self.page = page
        self.update_buttons()

    def update_buttons(self):
        self.clear_items()
        if self.page > 0:
            self.add_item(ui.Button(label="⬅️ Назад", style=discord.ButtonStyle.secondary, custom_id="prev"))
        if (self.page + 1) * 5 < len(self.items):
            self.add_item(ui.Button(label="➡️ Вперёд", style=discord.ButtonStyle.secondary, custom_id="next"))

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True


class User(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # --- ПРОФИЛЬ ---
    @app_commands.command(name="me", description="Показать твой профиль")
    async def profile(self, interaction: discord.Interaction):
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT u.points, COALESCE(t.streak, 0), COALESCE(t.xp, 0)
            FROM users u
            LEFT JOIN user_activity_totals t
                ON u.user_id = t.user_id AND u.server_id = t.server_id
            WHERE u.user_id = %s AND u.server_id = %s
        """, (interaction.user.id, interaction.guild.id))
        row = cur.fetchone()
        conn.close()

        points = row[0] if row else 0
        streak = row[1] if row else 0
        xp = row[2] if row else 0

        embed = discord.Embed(
            title=f"👤 Профиль {interaction.user.display_name}",
            color=discord.Color.blurple()
        )
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        embed.add_field(name="🔥 Стрик", value=str(streak), inline=True)
        embed.add_field(name="💰 Поинты", value=str(points), inline=True)
        embed.add_field(name="⭐ Опыт", value=str(xp), inline=True)

        await interaction.response.send_message(embed=embed)

    # --- МАГАЗИН ---
    @app_commands.command(name="shop", description="Открыть магазин")
    async def shop(self, interaction: discord.Interaction):
        items = [
            {"name": "Роль VIP", "price": 100},
            {"name": "Цветной ник", "price": 50},
            {"name": "Эксклюзивный смайлик", "price": 200},
            {"name": "Медаль «Активист»", "price": 300},
            {"name": "Фон профиля", "price": 150},
            {"name": "Фон: Галактика", "price": 500},
            {"name": "Фон: Киберпанк", "price": 500},
        ]

        page = 0
        embed = self.get_shop_page(items, page)
        view = ShopView(items, page)
        await interaction.response.send_message(embed=embed, view=view)

    def get_shop_page(self, items, page):
        embed = discord.Embed(
            title="🛒 Магазин",
            description=f"Страница {page + 1}",
            color=discord.Color.green()
        )
        start = page * 5
        end = start + 5
        for item in items[start:end]:
            embed.add_field(
                name=item["name"],
                value=f"💰 {item['price']} поинтов",
                inline=False
            )
        return embed

    # --- АЧИВКИ ---
    @app_commands.command(name="achievements", description="Показать твои ачивки")
    async def achievements(self, interaction: discord.Interaction):
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT a.name, a.description, ua.date_unlocked
            FROM achievements a
            LEFT JOIN user_achievements ua
                ON a.achievement_id = ua.achievement_id
                AND ua.user_id = %s
                AND ua.server_id = %s
        """, (interaction.user.id, interaction.guild.id))
        rows = cur.fetchall()
        conn.close()

        embed = discord.Embed(
            title=f"🏆 Ачивки {interaction.user.display_name}",
            color=discord.Color.gold()
        )

        if not rows:
            embed.description = "У тебя пока нет ачивок 😔"
        else:
            for name, description, date_unlocked in rows:
                status = "✅" if date_unlocked else "❌"
                embed.add_field(
                    name=f"{status} {name}",
                    value=description,
                    inline=False
                )

        await interaction.response.send_message(embed=embed)


async def setup(bot):
    await bot.add_cog(User(bot))