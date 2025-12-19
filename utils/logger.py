import logging
from database.db import get_connection

def setup_logger():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        handlers=[logging.StreamHandler()]
    )
    return logging.getLogger("PlayPal")

def log_user_activity(user, server_id: int, action: str, points: float = 0.0, context: str = None):
    """
    user: discord.User или discord.Member
    server_id: ID сервера
    action: тип активности ("сообщение", "голос", "реакция", "команда")
    points: начисленные поинты
    context: текст сообщения, эмоджи и т.д.
    """
    username = f"{user.name}#{user.discriminator}" if hasattr(user, "discriminator") else str(user)
    logger = logging.getLogger("PlayPal")
    msg = f"Активность: {username} | {action} | +{points:.2f} pts"
    if context:
        truncated = (context[:100] + "...") if len(context) > 100 else context
        msg += f" | context: {truncated}"
    logger.info(msg)

    # Сохранение в БД
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO activity_logs(user_id, server_id, type, context, value)
        VALUES (%s, %s, %s, %s, %s)
    """, (user.id, server_id, action, context, points))
    conn.commit()
    conn.close()