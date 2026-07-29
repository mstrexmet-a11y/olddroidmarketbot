import logging
import os
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler,
)
from telegram.error import TelegramError

BOT_TOKEN = "8918648428:AAGV9e1UFiH5c6y9Ggm-RiztEW0jBTysq-E"
ADMIN_IDS = [8285884336, 6011748459]  # Ты и второй админ

WAITING_FOR_APP_NAME, WAITING_FOR_ANDROID_VERSION, WAITING_FOR_APP_FILE = range(3)

user_suggestions = {}

SAVE_DIR = "suggested_apps"
os.makedirs(SAVE_DIR, exist_ok=True)

MAX_FILE_SIZE = 150 * 1024 * 1024  # 150 МБ

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🕹️ Добро пожаловать в OldDroidMarketBot!\n\n"
        "Я помогу добавить приложение в наш магазин ретро-софта.\n"
        "Используй команду /suggest, чтобы предложить свой APK."
    )

async def suggest_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📝 Давай оформим заявку.\n\n"
        "Для начала введи **название приложения** (например, 'Opera Mini 4.2'):\n"
        "Или отправь /cancel для отмены."
    )
    return WAITING_FOR_APP_NAME

async def receive_app_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    app_name = update.message.text
    context.user_data["suggested_name"] = app_name

    await update.message.reply_text(
        f"✅ Название: *{app_name}*\n\n"
        f"Теперь укажи **минимальную версию Android** (например: 4.4.4, 5.0, 2.3 и т.д.):\n"
        "Или отправь /cancel для отмены.",
        parse_mode="Markdown"
    )
    return WAITING_FOR_ANDROID_VERSION

async def receive_android_version(update: Update, context: ContextTypes.DEFAULT_TYPE):
    android_version = update.message.text
    context.user_data["android_version"] = android_version

    await update.message.reply_text(
        f"✅ Мин. Android: *{android_version}*\n\n"
        f"Теперь отправь мне сам APK-файл этого приложения.\n"
        "📦 Максимальный размер файла: **150 МБ**.\n"
        "Важно: файл должен быть в формате .apk.",
        parse_mode="Markdown"
    )
    return WAITING_FOR_APP_FILE

async def receive_app_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user_name = update.message.from_user.full_name
    username = update.message.from_user.username
    app_name = context.user_data.get("suggested_name", "Без названия")
    android_version = context.user_data.get("android_version", "Не указана")

    file = None
    file_name = ""

    if update.message.document:
        file = update.message.document
        file_name = file.file_name or ""
    elif update.message.photo:
        await update.message.reply_text("❌ Это фото, а не файл. Отправь APK-файл как документ (не сжимая).")
        return WAITING_FOR_APP_FILE
    else:
        await update.message.reply_text("❌ Я не вижу файла. Отправь APK как документ (файл).")
        return WAITING_FOR_APP_FILE

    if not file:
        await update.message.reply_text("❌ Не могу получить файл. Попробуй ещё раз.")
        return WAITING_FOR_APP_FILE

    # Проверка размера файла
    if file.file_size and file.file_size > MAX_FILE_SIZE:
        size_mb = round(file.file_size / (1024 * 1024), 1)
        await update.message.reply_text(
            f"❌ Файл слишком большой: *{size_mb} МБ*\n"
            f"Максимальный размер: **150 МБ**.\n"
            f"Пожалуйста, сожми файл или отправь другой.",
            parse_mode="Markdown"
        )
        return WAITING_FOR_APP_FILE

    if not file_name.lower().endswith(".apk"):
        await update.message.reply_text(f"❌ Бот принимает только файлы .apk! Ты отправил: {file_name}")
        return WAITING_FOR_APP_FILE

    try:
        new_file = await context.bot.get_file(file.file_id)
        safe_filename = f"{user_id}_{app_name.replace(' ', '_')}.apk"
        file_path = os.path.join(SAVE_DIR, safe_filename)

        # Отправляем сообщение о загрузке
        loading_msg = await update.message.reply_text("⏳ Загружаю файл на сервер, подожди...")
        
        await new_file.download_to_drive(file_path)

        await loading_msg.delete()

        logger.info(f"✅ Файл сохранён: {file_path}")

        user_suggestions[user_id] = {
            "username": user_name,
            "app_name": app_name,
            "android_version": android_version,
            "file_path": file_path
        }

        size_mb = round(os.path.getsize(file_path) / (1024 * 1024), 1)

        await update.message.reply_text(
            f"🎉 Отлично! Твоя заявка на *{app_name}* принята.\n\n"
            f"📱 Мин. Android: *{android_version}*\n"
            f"📦 Размер: *{size_mb} МБ*\n\n"
            f"Модераторы OldDroidMarket проверят её в ближайшее время.",
            parse_mode="Markdown"
        )

        # --- Отправка уведомления всем админам ---
        admin_message = (
            f"📦 Новая заявка!\n\n"
            f"👤 От: {user_name}"
        )
        if username:
            admin_message += f" (@{username})"
        admin_message += (
            f"\n📱 Приложение: {app_name}"
            f"\n📱 Мин. Android: {android_version}"
            f"\n📦 Размер: {size_mb} МБ"
            f"\n🆔 ID пользователя: {user_id}"
        )

        for admin_id in ADMIN_IDS:
            try:
                await context.bot.send_message(chat_id=admin_id, text=admin_message)
                logger.info(f"📨 Уведомление отправлено админу {admin_id} (текст)")
                
                with open(file_path, "rb") as f:
                    await context.bot.send_document(
                        chat_id=admin_id, 
                        document=f, 
                        filename=safe_filename,
                        caption=f"{app_name} (Android {android_version})"
                    )
                logger.info(f"📨 APK-файл отправлен админу {admin_id}")
                
            except TelegramError as te:
                logger.error(f"❌ Ошибка отправки админу {admin_id}: {te}")
                try:
                    await context.bot.send_message(
                        chat_id=admin_id,
                        text=f"{admin_message}\n\n⚠️ Не смог отправить файл автоматически. Файл сохранён: {file_path}"
                    )
                except:
                    logger.error(f"❌ Админ {admin_id} не написал /start боту!")

    except Exception as e:
        logger.error(f"Ошибка при сохранении файла: {e}")
        await update.message.reply_text(f"❌ Произошла ошибка при сохранении: {e}")

    context.user_data.clear()
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🚫 Предложение отменено. Если передумаешь, просто нажми /suggest.")
    context.user_data.clear()
    return ConversationHandler.END

def main():
    application = Application.builder().token(BOT_TOKEN).build()

    suggest_conversation = ConversationHandler(
        entry_points=[CommandHandler("suggest", suggest_start)],
        states={
            WAITING_FOR_APP_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_app_name)],
            WAITING_FOR_ANDROID_VERSION: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_android_version)],
            WAITING_FOR_APP_FILE: [
                MessageHandler(filters.Document.ALL, receive_app_file),
                MessageHandler(filters.PHOTO, receive_app_file),
                MessageHandler(filters.ALL, receive_app_file),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(suggest_conversation)

    print("🤖 OldDroidMarketBot запущен и ждет заявок...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()