import os
import psycopg
from dotenv import load_dotenv

load_dotenv()

def _get_dsn() -> str:
    dsn = os.getenv("DATABASE_URL")
    if not dsn or not dsn.strip():
        raise RuntimeError("DATABASE_URL не задан")
    return dsn

def init_db():
    conn = psycopg.connect(_get_dsn(), autocommit=False, sslmode="require")
    try:
        with conn.cursor() as cur:
            # Таблица серверов
            cur.execute("""
                CREATE TABLE IF NOT EXISTS servers (
                    server_id BIGINT PRIMARY KEY,
                    name TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """)

            # Пользователи
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id BIGINT,
                    server_id BIGINT REFERENCES servers(server_id) ON DELETE CASCADE,
                    join_date TIMESTAMP DEFAULT NOW(),
                    warns INTEGER DEFAULT 0,
                    level INTEGER DEFAULT 1,
                    xp REAL DEFAULT 0,
                    streak INTEGER DEFAULT 0,
                    points REAL DEFAULT 0,
                    PRIMARY KEY(user_id, server_id)
                )
            """)

            # Ежедневная активность
            cur.execute("""
                CREATE TABLE IF NOT EXISTS user_activity_daily (
                    user_id BIGINT,
                    server_id BIGINT,
                    date DATE NOT NULL,
                    messages INTEGER DEFAULT 0,
                    voice_minutes INTEGER DEFAULT 0,
                    points REAL DEFAULT 0,
                    PRIMARY KEY(user_id, server_id, date),
                    FOREIGN KEY(user_id, server_id) REFERENCES users(user_id, server_id) ON DELETE CASCADE
                )
            """)

            # Общая активность (итоги)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS user_activity_totals (
                    user_id BIGINT,
                    server_id BIGINT,
                    messages INTEGER DEFAULT 0,
                    voice_minutes INTEGER DEFAULT 0,
                    points REAL DEFAULT 0,
                    streak INTEGER DEFAULT 0,
                    last_activity_date DATE,
                    PRIMARY KEY(user_id, server_id),
                    FOREIGN KEY(user_id, server_id) REFERENCES users(user_id, server_id) ON DELETE CASCADE
                )
            """)

            # Логи активности
            cur.execute("""
                CREATE TABLE IF NOT EXISTS activity_logs (
                    log_id SERIAL PRIMARY KEY,
                    user_id BIGINT,
                    server_id BIGINT,
                    type TEXT,
                    context TEXT,
                    value REAL,
                    created_at TIMESTAMP DEFAULT NOW(),
                    FOREIGN KEY(user_id, server_id) REFERENCES users(user_id, server_id) ON DELETE CASCADE
                )
            """)

            # Варны/муты/баны
            cur.execute("""
                CREATE TABLE IF NOT EXISTS user_warnings (
                    warning_id SERIAL PRIMARY KEY,
                    user_id BIGINT,
                    server_id BIGINT,
                    reason TEXT,
                    moderator BIGINT,
                    created_at TIMESTAMP DEFAULT NOW(),
                    FOREIGN KEY(user_id, server_id) REFERENCES users(user_id, server_id) ON DELETE CASCADE
                )
            """)

            # Ачивки
            cur.execute("""
                CREATE TABLE IF NOT EXISTS achievements (
                    achievement_id SERIAL PRIMARY KEY,
                    name TEXT,
                    description TEXT,
                    xp_reward REAL DEFAULT 0
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS user_achievements (
                    user_id BIGINT,
                    server_id BIGINT,
                    achievement_id INT REFERENCES achievements(achievement_id) ON DELETE CASCADE,
                    date_unlocked TIMESTAMP DEFAULT NOW(),
                    PRIMARY KEY(user_id, server_id, achievement_id),
                    FOREIGN KEY(user_id, server_id) REFERENCES users(user_id, server_id) ON DELETE CASCADE
                )
            """)

            # Роли сервера
            cur.execute("""
                CREATE TABLE IF NOT EXISTS server_roles (
                    server_id BIGINT REFERENCES servers(server_id) ON DELETE CASCADE,
                    role_id BIGINT,
                    required_points REAL DEFAULT 0,
                    required_level INTEGER DEFAULT 0,
                    PRIMARY KEY(server_id, role_id)
                )
            """)

            conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def get_connection():
    return psycopg.connect(_get_dsn(), autocommit=False, sslmode="require")