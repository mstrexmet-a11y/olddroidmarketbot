import logging
import os
import re
import requests
from threading import Thread
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
    ConversationHandler,
)
from telegram.error import TelegramError

BOT_TOKEN = "8918648428:AAGV9e1UFiH5c6y9Ggm-RiztEW0jBTysq-E"
ADMIN_IDS = [8285884336, 6011748459]

YANDEX_TOKEN = "y0__wgBEMrpquAFGLqxRiDavp28GDDzmNDsB4oiEFsiUYNKpYYSXyARIj2hc73I"
YANDEX_FOLDER = "OldDroidMarket"

PORT = int(os.environ.get("PORT", 10000))

WAITING_FOR_APP_NAME, WAITING_FOR_ANDROID_VERSION, WAITING_FOR_APP_FILE = range(3)

SAVE_DIR = "suggested_apps"
os.makedirs(SAVE_DIR, exist_ok=True)

MAX_FILE_SIZE = 20 * 1024 * 1024

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Хранилище заявок
suggestions = {}
processed_suggestions = {}

# --- Веб-сервер ---
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running!"

def run_web_server():
    app.run(host='0.0.0.0', port=PORT)

# --- Яндекс.Диск ---
def upload_to_yandex_disk(local_path, filename):
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


def check_android_version(version_str):
    try:
        version_str = version_str.strip()
        match = re.search(r'(\d+(?:\.\d+)*)', version_str)
        if not match:
            return True, ""
        
        version_num = match.group(1)
        parts = version_num.split(".")
        
        major = int(parts[0])
        minor = int(parts[1]) if len(parts) > 1 else 0
        micro = int(parts[2]) if len(parts) > 2 else 0
        
        if major > 4:
            return False, f"❌ Версия Android {version_num} слишком новая!\n📱 Наш магазин только для Android **до 4.4.4 включительно**.\n📝 Введи версию не выше 4.4.4 (например: 4.4.4, 2.3, 4.0)."
        elif major == 4:
            if minor > 4:
                return False, f"❌ Версия Android {version_num} слишком новая!\n📱 Наш магазин только для Android **до 4.4.4 включительно**.\n📝 Введи версию не выше 4.4.4 (например: 4.4.4, 2.3, 4.0)."
            elif minor == 4 and micro > 4:
                return False, f"❌ Версия Android {version_num} слишком новая!\n📱 Наш магазин только для Android **до 4.4.4 включительно**.\n📝 Введи версию не выше 4.4.4 (например: 4.4.4, 2.3, 4.0)."
        
        return True, ""
    except ValueError:
        return True, ""


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🕹️ Добро пожаловать в OldDroidMarketBot!\n\n"
        "Я помогу добавить приложение в наш магазин ретро-софта.\n"
        "Используй команду /suggest, чтобы предложить свой APK.\n\n"
        "📦 Файлы до 20 МБ — напрямую.\n"
        "📎 Большие файлы — присылай ссылкой на Яндекс.Диск.\n"
        "📱 Только Android до 4.4.4 включительно!"
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
        f"Теперь укажи **минимальную версию Android** (например: 4.4.4, 2.3, 4.0):\n"
        f"⚠️ Только версии **до 4.4.4 включительно!**\n"
        "Или отправь /cancel для отмены.",
        parse_mode="Markdown"
    )
    return WAITING_FOR_ANDROID_VERSION

async def receive_android_version(update: Update, context: ContextTypes.DEFAULT_TYPE):
    android_version = update.message.text.strip()
    
    is_valid, error_msg = check_android_version(android_version)
    if not is_valid:
        await update.message.reply_text(error_msg)
        return WAITING_FOR_ANDROID_VERSION

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

            loading_msg = await update.message.reply_text("⏳ Сохраняю файл... ░░░░░░░░ 0%")
            await new_file.download_to_drive(local_path)

            await loading_msg.edit_text("☁️ Загружаю на Яндекс.Диск... ████░░░░ 50%")
            yadisk_url = upload_to_yandex_disk(local_path, safe_filename)

            await loading_msg.edit_text("📦 Завершаю... ████████ 100%")
            await loading_msg.delete()

            size_mb = round(os.path.getsize(local_path) / (1024 * 1024), 1)

            suggestion_id = str(user_id)
            suggestions[suggestion_id] = {
                "user_id": user_id,
                "user_name": user_name,
                "username": username,
                "app_name": app_name,
                "android_version": android_version,
                "size_mb": size_mb,
                "file_path": local_path,
                "yadisk_url": yadisk_url,
                "status": "pending"
            }

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
                "❌ Это не похоже на ссылку. Отправь APK-файл или ссылку на Яндекс.Диск.\n"
                "Или /cancel для отмены."
            )
            return WAITING_FOR_APP_FILE

        suggestion_id = str(user_id)
        suggestions[suggestion_id] = {
            "user_id": user_id,
            "user_name": user_name,
            "username": username,
            "app_name": app_name,
            "android_version": android_version,
            "size_mb": None,
            "file_path": link,
            "yadisk_url": link,
            "is_link": True,
            "status": "pending"
        }

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
        await update.message.reply_text("❌ Это фото. Отправь APK-файл или ссылку. /cancel для отмены.")
        return WAITING_FOR_APP_FILE
    else:
        await update.message.reply_text("❌ Отправь APK-файл или ссылку. /cancel для отмены.")
        return WAITING_FOR_APP_FILE

    context.user_data.clear()
    return ConversationHandler.END


async def notify_admins(context, user_name, username, app_name, android_version, size_mb, user_id, file_or_link, yadisk_url=None, is_link=False):
    """Отправляет уведомления админам с кнопками."""
    if is_link:
        text = f"📦 Новая заявка!\n\n👤 От: {user_name}"
        if username:
            text += f" (@{username})"
        text += f"\n📱 Приложение: {app_name}\n📱 Мин. Android: {android_version}\n📎 Ссылка: {file_or_link}\n🆔 ID: {user_id}\n📌 Статус: ⏳ На рассмотрении"
    else:
        text = f"📦 Новая заявка!\n\n👤 От: {user_name}"
        if username:
            text += f" (@{username})"
        text += f"\n📱 Приложение: {app_name}\n📱 Мин. Android: {android_version}\n📦 Размер: {size_mb} МБ\n🆔 ID: {user_id}\n📌 Статус: ⏳ На рассмотрении"
        if yadisk_url:
            text += f"\n☁️ Яндекс.Диск: {yadisk_url}"

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Одобрить", callback_data=f"approve_{user_id}"),
            InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_{user_id}")
        ]
    ])

    for admin_id in ADMIN_IDS:
        try:
            if not is_link and file_or_link and os.path.exists(file_or_link):
                await context.bot.send_message(chat_id=admin_id, text=text, disable_web_page_preview=True, reply_markup=keyboard)
                with open(file_or_link, "rb") as f:
                    await context.bot.send_document(chat_id=admin_id, document=f, filename=os.path.basename(file_or_link))
            else:
                await context.bot.send_message(chat_id=admin_id, text=text, disable_web_page_preview=True, reply_markup=keyboard)
        except TelegramError as te:
            logger.error(f"Ошибка отправки админу {admin_id}: {te}")


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает нажатия кнопок."""
    query = update.callback_query
    await query.answer()
    
    admin_id = query.from_user.id
    admin_name = query.from_user.full_name
    
    if admin_id not in ADMIN_IDS:
        await query.answer("❌ У вас нет прав!", show_alert=True)
        return
    
    data = query.data
    
    if data.startswith("approve_") or data.startswith("reject_"):
        action = "approve" if data.startswith("approve_") else "reject"
        user_id = data.replace(f"{action}_", "")
        
        # Проверяем, не обработана ли уже заявка
        if user_id in processed_suggestions:
            who = processed_suggestions[user_id]["admin_name"]
            what = "одобрена" if processed_suggestions[user_id]["action"] == "approve" else "отклонена"
            await query.answer(f"⚠️ Эта заявка уже {what} админом {who}!", show_alert=True)
            return
        
        if user_id in suggestions:
            # Сохраняем обработку
            processed_suggestions[user_id] = {
                "action": action,
                "admin_name": admin_name,
                "admin_id": admin_id
            }
            
            suggestions[user_id]["status"] = "approved" if action == "approve" else "rejected"
            app_name = suggestions[user_id]["app_name"]
            
            # Уведомляем пользователя
            emoji_status = "✅" if action == "approve" else "❌"
            status_text_full = "одобрена" if action == "approve" else "отклонена"
            
            try:
                await context.bot.send_message(
                    chat_id=int(user_id),
                    text=f"{emoji_status} Ваша заявка на *{app_name}* **{status_text_full}!**\n\n"
                         f"Администратор: {admin_name}\n"
                         f"{'🎉 Приложение будет добавлено в магазин OldDroidMarket!' if action == 'approve' else '😔 Возможно, приложение не соответствует требованиям.'}",
                    parse_mode="Markdown"
                )
            except Exception as e:
                logger.error(f"Не удалось уведомить пользователя {user_id}: {e}")
            
            # Обновляем сообщение у текущего админа
            status_emoji = "✅ Одобрено" if action == "approve" else "❌ Отклонено"
            new_text = query.message.text.replace("⏳ На рассмотрении", f"{status_emoji} ({admin_name})")
            
            await query.edit_message_text(
                text=new_text,
                reply_markup=None
            )
            
            # Уведомляем второго админа
            for other_admin_id in ADMIN_IDS:
                if other_admin_id != admin_id:
                    try:
                        await context.bot.send_message(
                            chat_id=other_admin_id,
                            text=f"📢 Заявка на *{app_name}* (ID: {user_id}) уже обработана!\n"
                                 f"{status_emoji} админом {admin_name}",
                            parse_mode="Markdown"
                        )
                    except:
                        pass


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🚫 Предложение отменено. Если передумаешь, просто нажми /suggest.")
    context.user_data.clear()
    return ConversationHandler.END


def main():
    web_thread = Thread(target=run_web_server)
    web_thread.daemon = True
    web_thread.start()
    
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
    application.add_handler(CallbackQueryHandler(button_handler))

    print("🤖 OldDroidMarketBot запущен с кнопками модерации!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()