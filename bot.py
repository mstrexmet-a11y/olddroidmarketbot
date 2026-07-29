import logging
import os
import requests
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
ADMIN_IDS = [8285884336, 6011748459]

# Яндекс.Диск
YANDEX_TOKEN = "y0__wgBEMrpquAFGLqxRiDavp28GDDzmNDsB4oiEFsiUYNKpYYSXyARIj2hc73I"
YANDEX_FOLDER = "OldDroidMarket"

WAITING_FOR_APP_NAME, WAITING_FOR_ANDROID_VERSION, WAITING_FOR_APP_FILE = range(3)

SAVE_DIR = "suggested_apps"
os.makedirs(SAVE_DIR, exist_ok=True)

MAX_FILE_SIZE = 20 * 1024 * 1024

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)


def upload_to_yandex_disk(local_path, filename):
    """Загружает файл на Яндекс.Диск и возвращает публичную ссылку."""
    try:
        headers = {"Authorization": f"OAuth {YANDEX_TOKEN}"}
        params = {"path": f"/{YANDEX_FOLDER}"}
        requests.put("https://cloud-api.yandex.net/v1/disk/resources", headers=headers, params=params)

        upload_path = f"/{YANDEX_FOLDER}/{filename}"
        params = {"path": upload_path, "overwrite": "true"}
        resp = requests.get("https://cloud-api.yandex.net/v1/disk/resources/upload", headers=headers, params=params)
        upload_url = resp.json().get("href")

        if not upload_url:
            logger.error(f"Не удалось получить ссылку: {resp.json()}")
            return None

        with open(local_path, "rb") as f:
            upload_resp = requests.put(upload_url, files={"file": f})

        if upload_resp.status_code == 201:
            params = {"path": upload_path}
            requests.put("https://cloud-api.yandex.net/v1/disk/resources/publish", headers=headers, params=params)

            info_resp = requests.get("https://cloud-api.yandex.net/v1/disk/resources", headers=headers, params={"path": upload_path})
            public_url = info_resp.json().get("public_url")

            logger.info(f"✅ Загружено на Яндекс.Диск: {public_url}")
            return public_url
        else:
            logger.error(f"Ошибка загрузки: {upload_resp.status_code}")
            return None

    except Exception as e:
        logger.error(f"Ошибка Яндекс.Диск: {e}")
        return None


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отвечает на команду /start"""
    await update.message.reply_text(
        "🕹️ Добро пожаловать в OldDroidMarketBot!\n\n"
        "Я помогу добавить приложение в наш магазин ретро-софта.\n"
        "Используй команду /suggest, чтобы предложить свой APK.\n\n"
        "📦 Файлы до 20 МБ — напрямую.\n"
        "📎 Большие файлы — присылай ссылкой на Яндекс.Диск."
    )

async def suggest_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начинает процесс предложки: запрашивает название приложения."""
    await update.message.reply_text(
        "📝 Давай оформим заявку.\n\n"
        "Для начала введи **название приложения** (например, 'Opera Mini 4.2'):\n"
        "Или отправь /cancel для отмены."
    )
    return WAITING_FOR_APP_NAME

async def receive_app_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получает название приложения и просит версию Android."""
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
    """Получает версию Android и просит файл или ссылку."""
    android_version = update.message.text
    context.user_data["android_version"] = android_version

    await update.message.reply_text(
        f"✅ Мин. Android: *{android_version}*\n\n"
        f"Теперь отправь мне APK-файл или ссылку на Яндекс.Диск.\n\n"
        "📦 Если файл **до 20 МБ** — пришли его как документ.\n"
        "📎 Если файл **больше 20 МБ** — загрузи на Яндекс.Диск и пришли ссылку.\n\n"
        "Или отправь /cancel для отмены.",
        parse_mode="Markdown"
    )
    return WAITING_FOR_APP_FILE

async def receive_app_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получает APK-файл или ссылку, сохраняет и загружает на Яндекс.Диск."""
    user_id = update.message.from_user.id
    user_name = update.message.from_user.full_name
    username = update.message.from_user.username
    app_name = context.user_data.get("suggested_name", "Без названия")
    android_version = context.user_data.get("android_version", "Не указана")

    if update.message.document:
        file = update.message.document
        file_name = file.file_name or ""

        if not file_name.lower().endswith(".apk"):
            await update.message.reply_text(
                f"❌ Бот принимает только файлы .apk! Ты отправил: {file_name}\n"
                f"Или отправь ссылку на Яндекс.Диск.\n"
                f"Или /cancel для отмены."
            )
            return WAITING_FOR_APP_FILE

        if file.file_size and file.file_size > MAX_FILE_SIZE:
            size_mb = round(file.file_size / (1024 * 1024), 1)
            await update.message.reply_text(
                f"❌ Файл слишком большой: *{size_mb} МБ*\n"
                f"Максимальный размер для прямой загрузки: **20 МБ**.\n\n"
                f"📎 Загрузи файл на **Яндекс.Диск** и пришли мне ссылку.\n"
                f"Или отправь /cancel для отмены.",
                parse_mode="Markdown"
            )
            return WAITING_FOR_APP_FILE

        try:
            new_file = await context.bot.get_file(file.file_id)
            safe_filename = f"{user_id}_{app_name.replace(' ', '_')}.apk"
            local_path = os.path.join(SAVE_DIR, safe_filename)

            loading_msg = await update.message.reply_text("⏳ Сохраняю файл...")
            await new_file.download_to_drive(local_path)

            await loading_msg.edit_text("☁️ Загружаю на Яндекс.Диск...")
            yadisk_url = upload_to_yandex_disk(local_path, safe_filename)

            await loading_msg.delete()

            size_mb = round(os.path.getsize(local_path) / (1024 * 1024), 1)

            if yadisk_url:
                await update.message.reply_text(
                    f"🎉 Отлично! Твоя заявка на *{app_name}* принята.\n\n"
                    f"📱 Мин. Android: *{android_version}*\n"
                    f"📦 Размер: *{size_mb} МБ*\n"
                    f"☁️ [Ссылка на Яндекс.Диск]({yadisk_url})\n\n"
                    f"Модераторы OldDroidMarket проверят её в ближайшее время.",
                    parse_mode="Markdown",
                    disable_web_page_preview=True
                )
            else:
                await update.message.reply_text(
                    f"✅ Файл сохранён локально (загрузка на Диск не удалась).\n"
                    f"📱 *{app_name}* | Android: *{android_version}* | {size_mb} МБ",
                    parse_mode="Markdown"
                )

            await notify_admins(context, user_name, username, app_name, android_version, size_mb, user_id, local_path, yadisk_url)

        except Exception as e:
            logger.error(f"Ошибка: {e}")
            await update.message.reply_text(f"❌ Произошла ошибка: {e}")

    elif update.message.text:
        link = update.message.text.strip()
        if not (link.startswith("http://") or link.startswith("https://")):
            await update.message.reply_text(
                "❌ Это не похоже на ссылку. Отправь APK-файл (до 20 МБ) или ссылку на Яндекс.Диск.\n"
                "Или /cancel для отмены."
            )
            return WAITING_FOR_APP_FILE

        await update.message.reply_text(
            f"🎉 Отлично! Твоя заявка на *{app_name}* принята.\n\n"
            f"📱 Мин. Android: *{android_version}*\n"
            f"📎 Ссылка: {link}\n\n"
            f"Модераторы OldDroidMarket проверят её в ближайшее время.",
            parse_mode="Markdown",
            disable_web_page_preview=True
        )
        await notify_admins(context, user_name, username, app_name, android_version, None, user_id, link, is_link=True)

    elif update.message.photo:
        await update.message.reply_text(
            "❌ Это фото, а не APK. Отправь APK-файл (до 20 МБ) или ссылку на Яндекс.Диск.\n"
            "Или /cancel для отмены."
        )
        return WAITING_FOR_APP_FILE
    else:
        await update.message.reply_text(
            "❌ Отправь APK-файл (до 20 МБ) или ссылку на Яндекс.Диск.\n"
            "Или /cancel для отмены."
        )
        return WAITING_FOR_APP_FILE

    context.user_data.clear()
    return ConversationHandler.END

async def notify_admins(context, user_name, username, app_name, android_version, size_mb, user_id, file_or_link, yadisk_url=None, is_link=False):
    """Отправляет уведомления всем админам."""
    if is_link:
        text = f"📦 Новая заявка!\n\n👤 От: {user_name}"
        if username:
            text += f" (@{username})"
        text += f"\n📱 Приложение: {app_name}\n📱 Мин. Android: {android_version}\n📎 Ссылка: {file_or_link}\n🆔 ID: {user_id}"
    else:
        text = f"📦 Новая заявка!\n\n👤 От: {user_name}"
        if username:
            text += f" (@{username})"
        text += f"\n📱 Приложение: {app_name}\n📱 Мин. Android: {android_version}\n📦 Размер: {size_mb} МБ\n🆔 ID: {user_id}"
        if yadisk_url:
            text += f"\n☁️ Яндекс.Диск: {yadisk_url}"

    for admin_id in ADMIN_IDS:
        try:
            if not is_link and file_or_link and os.path.exists(file_or_link):
                await context.bot.send_message(chat_id=admin_id, text=text, disable_web_page_preview=True)
                with open(file_or_link, "rb") as f:
                    await context.bot.send_document(chat_id=admin_id, document=f, filename=os.path.basename(file_or_link))
            else:
                await context.bot.send_message(chat_id=admin_id, text=text, disable_web_page_preview=True)
        except TelegramError as te:
            logger.error(f"Ошибка отправки админу {admin_id}: {te}")

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отменяет процесс предложки."""
    await update.message.reply_text("🚫 Предложение отменено. Если передумаешь, просто нажми /suggest.")
    context.user_data.clear()
    return ConversationHandler.END

def main():
    application = Application.builder().token(BOT_TOKEN).build()

    suggest_conversation = ConversationHandler(
        entry_points=[CommandHandler("suggest", suggest_start)],
        states={
            WAITING_FOR_APP_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_app_name), CommandHandler("cancel", cancel)],
            WAITING_FOR_ANDROID_VERSION: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_android_version), CommandHandler("cancel", cancel)],
            WAITING_FOR_APP_FILE: [
                MessageHandler(filters.Document.ALL, receive_app_file),
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_app_file),
                MessageHandler(filters.PHOTO, receive_app_file),
                CommandHandler("cancel", cancel),
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