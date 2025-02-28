# claude_client.py - клиент для взаимодействия с Claude API
import json
import aiohttp
from typing import List, Dict, Any, Optional


class ClaudeClient:
    """Клиент для работы с Claude API."""

    def __init__(self, api_key: str, base_url: str = "https://api.anthropic.com/v1/messages"):
        self.api_key = api_key
        self.base_url = base_url
        self.headers = {
            "Content-Type": "application/json",
            "X-API-Key": api_key,
            "anthropic-version": "2023-06-01"
        }

    async def send_message(
        self,
        messages: List[Dict[str, str]],
        model: str = "claude-3-7-sonnet-20250219",
        temperature: float = 0.7,
        max_tokens: int = 4000,
        system: Optional[str] = None
    ) -> Dict[str, Any]:
        """Отправка запроса к Claude API."""

        payload = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

        if system:
            payload["system"] = system

        async with aiohttp.ClientSession() as session:
            async with session.post(
                self.base_url,
                headers=self.headers,
                json=payload
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"API error: {response.status}, {error_text}")

                return await response.json()


# database.py - работа с базой данных
import sqlite3
from typing import Dict, Any, List, Optional
import json
import os


class Database:
    """Класс для работы с базой данных SQLite."""

    def __init__(self, db_name: str = "claude_bot.db"):
        self.db_name = db_name
        self._initialize_db()

    def _initialize_db(self):
        """Инициализация базы данных."""
        if not os.path.exists(self.db_name):
            conn = sqlite3.connect(self.db_name)
            cursor = conn.cursor()

            # Таблица пользователей
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                settings TEXT DEFAULT '{}'
            )
            ''')

            # Таблица диалогов
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                user_message TEXT,
                bot_response TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
            ''')

            # Таблица сессий
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS sessions (
                user_id INTEGER PRIMARY KEY,
                history TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
            ''')

            conn.commit()
            conn.close()

    def user_exists(self, user_id: int) -> bool:
        """Проверка существования пользователя."""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()

        cursor.execute("SELECT 1 FROM users WHERE user_id = ?", (user_id,))
        result = cursor.fetchone() is not None

        conn.close()
        return result

    def register_user(self, user_id: int, username: str) -> None:
        """Регистрация нового пользователя."""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()

        default_settings = json.dumps({
            "model": "claude-3-7-sonnet-20250219",
            "temperature": 0.7,
            "max_tokens": 4000
        })

        cursor.execute(
            "INSERT INTO users (user_id, username, settings) VALUES (?, ?, ?)",
            (user_id, username, default_settings)
        )

        conn.commit()
        conn.close()

    def get_user_settings(self, user_id: int) -> Dict[str, Any]:
        """Получение настроек пользователя."""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()

        cursor.execute("SELECT settings FROM users WHERE user_id = ?", (user_id,))
        result = cursor.fetchone()

        conn.close()

        if result:
            return json.loads(result[0])

        return {}

    def update_user_setting(self, user_id: int, key: str, value: Any) -> None:
        """Обновление настройки пользователя."""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()

        settings = self.get_user_settings(user_id)
        settings[key] = value

        cursor.execute(
            "UPDATE users SET settings = ? WHERE user_id = ?",
            (json.dumps(settings), user_id)
        )

        conn.commit()
        conn.close()

    def log_conversation(self, user_id: int, user_message: str, bot_response: str) -> None:
        """Логирование диалога."""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()

        cursor.execute(
            "INSERT INTO conversations (user_id, user_message, bot_response) VALUES (?, ?, ?)",
            (user_id, user_message, bot_response)
        )

        conn.commit()
        conn.close()


# session_manager.py - управление сессиями диалога
import json
from typing import List, Dict, Any
from database import Database


class SessionManager:
    """Менеджер сессий для управления историей диалогов."""

    def __init__(self, db: Database):
        self.db = db

    def get_session(self, user_id: int) -> List[Dict[str, str]]:
        """Получение истории диалога для пользователя."""
        conn = sqlite3.connect(self.db.db_name)
        cursor = conn.cursor()

        cursor.execute("SELECT history FROM sessions WHERE user_id = ?", (user_id,))
        result = cursor.fetchone()

        conn.close()

        if result:
            return json.loads(result[0])

        return []

    def update_session(self, user_id: int, history: List[Dict[str, str]]) -> None:
        """Обновление истории диалога для пользователя."""
        conn = sqlite3.connect(self.db.db_name)
        cursor = conn.cursor()

        # Ограничиваем историю для экономии токенов
        # Оставляем последние N сообщений, чтобы не превысить лимит контекста
        max_messages = 10  # Можно настроить в зависимости от потребностей
        if len(history) > max_messages * 2:  # *2 потому что каждое сообщение - это пара реплик
            history = history[-max_messages * 2:]

        history_json = json.dumps(history)

        cursor.execute(
            "INSERT OR REPLACE INTO sessions (user_id, history, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)",
            (user_id, history_json)
        )

        conn.commit()
        conn.close()

    def clear_session(self, user_id: int) -> None:
        """Очистка истории диалога для пользователя."""
        conn = sqlite3.connect(self.db.db_name)
        cursor = conn.cursor()

        cursor.execute(
            "UPDATE sessions SET history = '[]', updated_at = CURRENT_TIMESTAMP WHERE user_id = ?",
            (user_id,)
        )

        conn.commit()
        conn.close()
