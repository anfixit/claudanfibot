# main.py - основной файл приложения
import os
import logging
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from database import Database
from app.api.claude_client import ClaudeClient
from session_manager import SessionManager

# Загрузка переменных окружения
load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CLAUDE_API_KEY = os.getenv("CLAUDE_API_KEY")

# Настройка логирования
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Инициализация компонентов
db = Database()
claude_client = ClaudeClient(api_key=CLAUDE_API_KEY)
session_manager = SessionManager(db)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /start."""
    user_id = update.effective_user.id
    username = update.effective_user.username

    # Регистрация пользователя в БД если он новый
    if not db.user_exists(user_id):
        db.register_user(user_id, username)

    await update.message.reply_text(
        "Привет! Я бот, который позволяет взаимодействовать с Claude API. "
        "Просто отправь мне сообщение, и я передам его Claude."
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /help."""
    help_text = """
    Доступные команды:
    /start - Запустить бота
    /help - Показать справку
    /clear - Очистить историю текущей сессии
    /settings - Настройки бота
    """
    await update.message.reply_text(help_text)


async def clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Очистка истории диалога."""
    user_id = update.effective_user.id
    session_manager.clear_session(user_id)
    await update.message.reply_text("История диалога очищена!")


async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Настройки бота."""
    user_id = update.effective_user.id
    settings = db.get_user_settings(user_id)

    settings_text = f"""
    Текущие настройки:
    - Модель: {settings.get('model', 'claude-3-7-sonnet-20250219')}
    - Temperature: {settings.get('temperature', 0.7)}
    - Max токенов: {settings.get('max_tokens', 4000)}

    Чтобы изменить настройки, используйте команды:
    /set_model <model_name>
    /set_temp <value>
    /set_max_tokens <value>
    """
    await update.message.reply_text(settings_text)


async def set_model_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Установка модели Claude."""
    user_id = update.effective_user.id
    if not context.args:
        await update.message.reply_text("Пожалуйста, укажите название модели.")
        return

    model = context.args[0]
    db.update_user_setting(user_id, "model", model)
    await update.message.reply_text(f"Модель изменена на {model}.")


async def set_temp_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Установка параметра temperature."""
    user_id = update.effective_user.id
    if not context.args:
        await update.message.reply_text("Пожалуйста, укажите значение temperature (0.0 - 1.0).")
        return

    try:
        temp = float(context.args[0])
        if 0.0 <= temp <= 1.0:
            db.update_user_setting(user_id, "temperature", temp)
            await update.message.reply_text(f"Temperature установлен на {temp}.")
        else:
            await update.message.reply_text("Temperature должен быть в диапазоне от 0.0 до 1.0.")
    except ValueError:
        await update.message.reply_text("Пожалуйста, укажите корректное числовое значение.")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик входящих сообщений."""
    user_id = update.effective_user.id
    user_message = update.message.text

    # Получаем настройки пользователя
    settings = db.get_user_settings(user_id)

    # Получаем историю диалога
    history = session_manager.get_session(user_id)

    # Добавляем сообщение пользователя в историю
    history.append({"role": "user", "content": user_message})

    # Индикатор печати
    await update.message.chat.send_action(action="typing")

    try:
        # Отправляем запрос к Claude API
        response = await claude_client.send_message(
            messages=history,
            model=settings.get("model", "claude-3-7-sonnet-20250219"),
            temperature=settings.get("temperature", 0.7),
            max_tokens=settings.get("max_tokens", 4000)
        )

        # Получаем ответ от Claude
        claude_response = response["content"][0]["text"]

        # Добавляем ответ в историю
        history.append({"role": "assistant", "content": claude_response})

        # Сохраняем обновленную историю
        session_manager.update_session(user_id, history)

        # Отправляем ответ пользователю
        await update.message.reply_text(claude_response)

        # Логируем диалог
        db.log_conversation(user_id, user_message, claude_response)

    excclaude_client.pyept Exception as e:
        logger.error(f"Ошибка при обработке запроса: {e}")
        await update.message.reply_text(
            "Произошла ошибка при обработке вашего запроса. Пожалуйста, попробуйте еще раз позже."
        )


def main() -> None:
    """Запуск бота."""
    # Создание приложения
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    # Регистрация обработчиков команд
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("clear", clear_command))
    application.add_handler(CommandHandler("settings", settings_command))
    application.add_handler(CommandHandler("set_model", set_model_command))
    application.add_handler(CommandHandler("set_temp", set_temp_command))

    # Регистрация обработчика сообщений
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Запуск бота
    application.run_polling()


if __name__ == "__main__":
    main()
