
import logging
import os
import re
import time
from threading import Thread
from datetime import datetime, timedelta
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

# ============================================
# НАСТРОЙКИ
# ============================================

BOT_TOKEN = "8918648428:AAGV9e1UFiH5c6y9Ggm-RiztEW0jBTysq-E"
ADMIN_IDS = [8285884336, 6011748459]

WORKER_URL = "https://billowing-mouse-b5eb.mstrexmet.workers.dev"

PORT = int(os.environ.get("PORT", 10000))

# Состояния
WAITING_FOR_APP_NAME, WAITING_FOR_ANDROID_VERSION, WAITING_FOR_APP_LINK, WAITING_FOR_IDEA = range(4)
WAITING_FOR_BROADCAST = 100

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Хранилища
suggestions = {}
processed_suggestions = {}
processed_ideas = {}
user_apps = {}
admin_messages = {}

AD_TEXT = (
    "━━━━━━━━━━━━━━━\n"
    "♟️ **CheckersNote** — шахматы и шашки в ретро-стиле!\n"
    "📱 Для Android 4.4.2\n"
    "🤖 Игра против ИИ или вдвоём\n"
    "🎨 Классический дизайн\n"
    "📦 Уже доступно в OldDroidMarket!\n"
    "━━━━━━━━━━━━━━━"
)

# ============================================
# ВЕБ-СЕРВЕР
# ============================================

app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running!"

def run_web_server():
    app.run(host='0.0.0.0', port=PORT)


def check_android_version(version_str):
    """Проверяет, что версия Android не выше 4.4.4."""
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
            return False, f"❌ Версия Android {version_num} слишком новая!\n📱 Только до **4.4.4**."
        elif major == 4:
            if minor > 4:
                return False, f"❌ Версия Android {version_num} слишком новая!\n📱 Только до **4.4.4**."
            elif minor == 4 and micro > 4:
                return False, f"❌ Версия Android {version_num} слишком новая!\n📱 Только до **4.4.4**."
        return True, ""
    except ValueError:
        return True, ""


# ============================================
# ОСНОВНЫЕ КОМАНДЫ
# ============================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Главное меню."""
    await update.message.reply_text(
        "🕹️ Добро пожаловать в OldDroidMarketBot!\n\n"
        "📋 **Команды:**\n"
        "/suggest — предложить приложение\n"
        "/idea — предложить идею\n"
        "/myapps — мои заявки\n"
        "/status ID — статус заявки\n"
        "/catalog — каталог приложений\n\n"
        "📱 Только Android до 4.4.4!",
        parse_mode="Markdown"
    )


async def suggest_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начинает процесс предложки."""
    await update.message.reply_text("📝 Введи **название приложения**:\nИли /cancel")
    return WAITING_FOR_APP_NAME


async def receive_app_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получает название приложения."""
    context.user_data["suggested_name"] = update.message.text
    await update.message.reply_text(
        f"✅ Название: *{update.message.text}*\n\n"
        f"Укажи **мин. версию Android** (до 4.4.4):\nИли /cancel",
        parse_mode="Markdown"
    )
    return WAITING_FOR_ANDROID_VERSION


async def receive_android_version(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получает версию Android."""
    android_version = update.message.text.strip()
    is_valid, error_msg = check_android_version(android_version)
    if not is_valid:
        await update.message.reply_text(error_msg)
        return WAITING_FOR_ANDROID_VERSION
    context.user_data["android_version"] = android_version
    await update.message.reply_text(
        f"✅ Android: *{android_version}*\n\n"
        f"Отправь **ссылку** на APK-файл (Google Диск, Яндекс.Диск, Dropbox и т.д.)\n"
        f"Или /cancel",
        parse_mode="Markdown"
    )
    return WAITING_FOR_APP_LINK


async def receive_app_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получает ссылку и создаёт заявку."""
    user_id = update.message.from_user.id
    user_name = update.message.from_user.full_name
    username = update.message.from_user.username
    app_name = context.user_data.get("suggested_name", "Без названия")
    android_version = context.user_data.get("android_version", "Не указана")
    link = update.message.text.strip()

    if not (link.startswith("http://") or link.startswith("https://")):
        await update.message.reply_text("❌ Это не ссылка. Отправь ссылку на файл.\nИли /cancel")
        return WAITING_FOR_APP_LINK

    suggestion_id = f"{user_id}_{int(time.time())}"
    suggestions[suggestion_id] = {
        "user_id": user_id,
        "user_name": user_name,
        "username": username,
        "app_name": app_name,
        "android_version": android_version,
        "link": link,
        "status": "pending",
        "date": datetime.now().strftime("%d.%m.%Y %H:%M")
    }

    if user_id not in user_apps:
        user_apps[user_id] = []
    user_apps[user_id].append(suggestion_id)

    await update.message.reply_text(
        f"🎉 Заявка на *{app_name}* принята!\n\n"
        f"📱 Android: *{android_version}*\n"
        f"🆔 `{suggestion_id}`\n"
        f"📎 Ссылка: {link}\n\n"
        f"Модераторы проверят её.\n\n{AD_TEXT}",
        parse_mode="Markdown",
        disable_web_page_preview=True
    )

    await notify_admins(context, user_name, username, app_name, android_version, user_id, link, suggestion_id=suggestion_id)

    context.user_data.clear()
    return ConversationHandler.END


# ============================================
# ИДЕИ
# ============================================

async def idea_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("💡 Напиши свою идею:\nИли /cancel")
    return WAITING_FOR_IDEA


async def receive_idea(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user_name = update.message.from_user.full_name
    username = update.message.from_user.username
    idea_text = update.message.text
    idea_id = f"idea_{user_id}_{int(time.time())}"

    text = f"💡 Новая идея!\n\n👤 {user_name}"
    if username:
        text += f" (@{username})"
    text += f"\n🆔 {idea_id}\n\n📝 {idea_text}"

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("👍 Принять", callback_data=f"accept_idea_{idea_id}"),
            InlineKeyboardButton("👎 Отклонить", callback_data=f"reject_idea_{idea_id}")
        ]
    ])

    for admin_id in ADMIN_IDS:
        try:
            await context.bot.send_message(chat_id=admin_id, text=text, reply_markup=keyboard)
        except:
            pass

    await update.message.reply_text("✅ Спасибо за идею!")
    return ConversationHandler.END


# ============================================
# УВЕДОМЛЕНИЯ АДМИНАМ
# ============================================

async def notify_admins(context, user_name, username, app_name, android_version, user_id, link, suggestion_id=None):
    text = f"📦 Новая заявка!\n\n👤 {user_name}"
    if username:
        text += f" (@{username})"
    text += f"\n📱 {app_name}\n📱 Android: {android_version}\n📎 {link}"
    text += f"\n🆔 `{suggestion_id}`\n📌 ⏳ На рассмотрении"

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Одобрить", callback_data=f"approve_{suggestion_id}"),
            InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_{suggestion_id}")
        ]
    ])

    admin_messages[suggestion_id] = {}
    suggestions[suggestion_id]["admin_text"] = text

    for admin_id in ADMIN_IDS:
        try:
            msg = await context.bot.send_message(
                chat_id=admin_id,
                text=text,
                disable_web_page_preview=True,
                reply_markup=keyboard
            )
            admin_messages[suggestion_id][admin_id] = msg.message_id
        except TelegramError as te:
            logger.error(f"❌ Ошибка админу {admin_id}: {te}")


# ============================================
# ОБРАБОТКА КНОПОК
# ============================================

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    admin_id = query.from_user.id
    admin_name = query.from_user.full_name

    if admin_id not in ADMIN_IDS:
        await query.answer("❌ Нет прав!", show_alert=True)
        return

    data = query.data

    # Идеи
    if data.startswith("accept_idea_") or data.startswith("reject_idea_"):
        action = "accept" if data.startswith("accept_idea_") else "reject"
        idea_id = data.replace(f"{action}_idea_", "")

        if idea_id in processed_ideas:
            who = processed_ideas[idea_id]["admin_name"]
            what = "принята" if processed_ideas[idea_id]["action"] == "accept" else "отклонена"
            await query.answer(f"⚠️ Уже {what} админом {who}!", show_alert=True)
            return

        processed_ideas[idea_id] = {"action": action, "admin_name": admin_name, "admin_id": admin_id}
        parts = idea_id.replace("idea_", "").split("_")
        user_id = parts[0]

        idea_status = "👍 Принята" if action == "accept" else "👎 Отклонена"
        new_text = query.message.text + f"\n\n📌 {idea_status} ({admin_name})"
        await query.edit_message_text(text=new_text, reply_markup=None)

        try:
            if action == "accept":
                await context.bot.send_message(chat_id=int(user_id), text=f"🎉 Твоя идея **принята!**\nАдминистратор: {admin_name}", parse_mode="Markdown")
            else:
                await context.bot.send_message(chat_id=int(user_id), text=f"😔 Твоя идея **отклонена.**\nАдминистратор: {admin_name}", parse_mode="Markdown")
        except:
            pass

        for other_id in ADMIN_IDS:
            if other_id != admin_id:
                try:
                    await context.bot.send_message(chat_id=other_id, text=f"📢 Идея {idea_id} обработана!\n{idea_status} админом {admin_name}")
                except:
                    pass
        return

    # Заявки
    if data.startswith("approve_") or data.startswith("reject_"):
        action = "approve" if data.startswith("approve_") else "reject"
        suggestion_id = data.replace(f"{action}_", "")

        if suggestion_id in processed_suggestions:
            who = processed_suggestions[suggestion_id]["admin_name"]
            what = "одобрена" if processed_suggestions[suggestion_id]["action"] == "approve" else "отклонена"
            await query.answer(f"⚠️ Уже {what} админом {who}!", show_alert=True)
            return

        if suggestion_id in suggestions:
            processed_suggestions[suggestion_id] = {"action": action, "admin_name": admin_name, "admin_id": admin_id}
            suggestions[suggestion_id]["status"] = "approved" if action == "approve" else "rejected"
            app_name = suggestions[suggestion_id]["app_name"]
            user_id = suggestions[suggestion_id]["user_id"]

            emoji = "✅" if action == "approve" else "❌"
            text_full = "одобрена" if action == "approve" else "отклонена"

            try:
                await context.bot.send_message(chat_id=int(user_id), text=f"{emoji} Заявка на *{app_name}* **{text_full}!**\nАдминистратор: {admin_name}", parse_mode="Markdown")
            except:
                pass

            status_emoji = "✅ Одобрено" if action == "approve" else "❌ Отклонено"
            new_text = query.message.text.replace("⏳ На рассмотрении", f"{status_emoji} ({admin_name})")
            await query.edit_message_text(text=new_text, reply_markup=None)

            if suggestion_id in admin_messages:
                for other_admin_id, msg_id in admin_messages[suggestion_id].items():
                    if other_admin_id != admin_id:
                        try:
                            await context.bot.edit_message_text(chat_id=other_admin_id, message_id=msg_id, text=new_text, reply_markup=None)
                        except:
                            pass


# ============================================
# КОМАНДЫ МОДЕРАЦИИ
# ============================================

async def approve_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    admin_id = update.message.from_user.id
    admin_name = update.message.from_user.full_name
    if admin_id not in ADMIN_IDS:
        await update.message.reply_text("❌ Нет прав.")
        return
    if not update.message.reply_to_message:
        await update.message.reply_text("📝 Ответьте на заявку командой /approve")
        return
    reply_text = update.message.reply_to_message.text or ""
    match = re.search(r'🆔 `(\d+_\d+)`', reply_text) or re.search(r'🆔 (\d+_\d+)', reply_text)
    if not match:
        await update.message.reply_text("❌ Не нашёл ID заявки.")
        return
    suggestion_id = match.group(1)
    if suggestion_id in processed_suggestions:
        who = processed_suggestions[suggestion_id]["admin_name"]
        what = "одобрена" if processed_suggestions[suggestion_id]["action"] == "approve" else "отклонена"
        await update.message.reply_text(f"⚠️ Уже {what} админом {who}!")
        return
    if suggestion_id not in suggestions:
        await update.message.reply_text("❌ Заявка не найдена.")
        return
    processed_suggestions[suggestion_id] = {"action": "approve", "admin_name": admin_name, "admin_id": admin_id}
    suggestions[suggestion_id]["status"] = "approved"
    app_name = suggestions[suggestion_id]["app_name"]
    user_id = suggestions[suggestion_id]["user_id"]
    try:
        await context.bot.send_message(chat_id=int(user_id), text=f"✅ Заявка на *{app_name}* **одобрена!**\nАдминистратор: {admin_name}", parse_mode="Markdown")
    except:
        pass
    await update.message.reply_text(f"✅ Заявка *{app_name}* ({suggestion_id}) одобрена!", parse_mode="Markdown")
    if suggestion_id in admin_messages:
        for aid, msg_id in admin_messages[suggestion_id].items():
            try:
                old_text = suggestions[suggestion_id].get("admin_text", "")
                new_text = old_text.replace("⏳ На рассмотрении", f"✅ Одобрено ({admin_name})")
                await context.bot.edit_message_text(chat_id=aid, message_id=msg_id, text=new_text, reply_markup=None)
            except:
                pass


async def reject_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    admin_id = update.message.from_user.id
    admin_name = update.message.from_user.full_name
    if admin_id not in ADMIN_IDS:
        await update.message.reply_text("❌ Нет прав.")
        return
    if not update.message.reply_to_message:
        await update.message.reply_text("📝 Ответьте на заявку командой /reject")
        return
    reply_text = update.message.reply_to_message.text or ""
    match = re.search(r'🆔 `(\d+_\d+)`', reply_text) or re.search(r'🆔 (\d+_\d+)', reply_text)
    if not match:
        await update.message.reply_text("❌ Не нашёл ID заявки.")
        return
    suggestion_id = match.group(1)
    if suggestion_id in processed_suggestions:
        who = processed_suggestions[suggestion_id]["admin_name"]
        what = "одобрена" if processed_suggestions[suggestion_id]["action"] == "approve" else "отклонена"
        await update.message.reply_text(f"⚠️ Уже {what} админом {who}!")
        return
    if suggestion_id not in suggestions:
        await update.message.reply_text("❌ Заявка не найдена.")
        return
    reason = "Не указана"
    if update.message.text:
        parts = update.message.text.strip().split(maxsplit=1)
        if len(parts) > 1:
            reason = parts[1]
    processed_suggestions[suggestion_id] = {"action": "reject", "admin_name": admin_name, "admin_id": admin_id, "reason": reason}
    suggestions[suggestion_id]["status"] = "rejected"
    app_name = suggestions[suggestion_id]["app_name"]
    user_id = suggestions[suggestion_id]["user_id"]
    try:
        await context.bot.send_message(chat_id=int(user_id), text=f"❌ Заявка на *{app_name}* **отклонена.**\nАдминистратор: {admin_name}\n📝 Причина: {reason}", parse_mode="Markdown")
    except:
        pass
    await update.message.reply_text(f"❌ Заявка *{app_name}* ({suggestion_id}) отклонена.\nПричина: {reason}", parse_mode="Markdown")
    if suggestion_id in admin_messages:
        for aid, msg_id in admin_messages[suggestion_id].items():
            try:
                old_text = suggestions[suggestion_id].get("admin_text", "")
                new_text = old_text.replace("⏳ На рассмотрении", f"❌ Отклонено ({admin_name})")
                await context.bot.edit_message_text(chat_id=aid, message_id=msg_id, text=new_text, reply_markup=None)
            except:
                pass


# ============================================
# ДОПОЛНИТЕЛЬНЫЕ КОМАНДЫ
# ============================================

async def myapps_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id not in user_apps or not user_apps[user_id]:
        await update.message.reply_text("📭 У вас нет заявок.")
        return
    text = "📋 *Ваши заявки:*\n\n"
    for sid in user_apps[user_id][-10:]:
        if sid in suggestions:
            s = suggestions[sid]
            status_map = {"pending": "⏳ На рассмотрении", "approved": "✅ Одобрена", "rejected": "❌ Отклонена"}
            text += f"📱 *{s['app_name']}*\n🆔 `{sid}`\n📌 {status_map.get(s['status'], s['status'])}\n\n"
    await update.message.reply_text(text, parse_mode="Markdown")


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("📝 /status ID_заявки")
        return
    sid = context.args[0]
    if sid in suggestions:
        s = suggestions[sid]
        status_map = {"pending": "⏳ На рассмотрении", "approved": "✅ Одобрена", "rejected": "❌ Отклонена"}
        await update.message.reply_text(f"📱 *{s['app_name']}*\n🆔 `{sid}`\n📌 {status_map.get(s['status'], s['status'])}", parse_mode="Markdown")
    else:
        await update.message.reply_text("❌ Заявка не найдена.")


async def catalog_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    approved = [(sid, s) for sid, s in suggestions.items() if s.get("status") == "approved"]
    if not approved:
        await update.message.reply_text("📭 Нет одобренных приложений.")
        return
    text = "📦 *Каталог:*\n\n"
    for sid, s in approved[:20]:
        text += f"📱 *{s['app_name']}* | Android {s.get('android_version','?')}\n📥 [Скачать]({s.get('link','')})\n\n"
    await update.message.reply_text(text, parse_mode="Markdown", disable_web_page_preview=True)


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    admin_id = update.message.from_user.id
    if admin_id not in ADMIN_IDS:
        await update.message.reply_text("❌ Нет прав.")
        return
    total = len(suggestions)
    approved = len([s for s in suggestions.values() if s["status"] == "approved"])
    rejected = len([s for s in suggestions.values() if s["status"] == "rejected"])
    pending = len([s for s in suggestions.values() if s["status"] == "pending"])
    text = f"📊 *Статистика:*\n\n📦 Всего: {total}\n⏳ На рассмотрении: {pending}\n✅ Одобрено: {approved}\n❌ Отклонено: {rejected}"
    await update.message.reply_text(text, parse_mode="Markdown")


async def broadcast_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    admin_id = update.message.from_user.id
    if admin_id not in ADMIN_IDS:
        await update.message.reply_text("❌ Нет прав.")
        return ConversationHandler.END
    await update.message.reply_text("📢 Напишите сообщение для рассылки:\nИли /cancel")
    return WAITING_FOR_BROADCAST


async def broadcast_send(update: Update, context: ContextTypes.DEFAULT_TYPE):
    broadcast_text = update.message.text
    all_users = set()
    for sid, s in suggestions.items():
        all_users.add(s["user_id"])
    sent = 0
    failed = 0
    await update.message.reply_text(f"📤 Рассылка на {len(all_users)} пользователей...")
    for uid in all_users:
        try:
            await context.bot.send_message(chat_id=int(uid), text=f"📢 *OldDroidMarket:*\n\n{broadcast_text}", parse_mode="Markdown")
            sent += 1
        except:
            failed += 1
    await update.message.reply_text(f"✅ Рассылка завершена!\n📤 Отправлено: {sent}\n❌ Не доставлено: {failed}")
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🚫 Отменено.")
    context.user_data.clear()
    return ConversationHandler.END


def main():
    web_thread = Thread(target=run_web_server)
    web_thread.daemon = True
    web_thread.start()

    application = Application.builder().token(BOT_TOKEN).base_url(f"{WORKER_URL}/bot").build()

    suggest_conversation = ConversationHandler(
        entry_points=[CommandHandler("suggest", suggest_start)],
        states={
            WAITING_FOR_APP_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_app_name), CommandHandler("cancel", cancel)],
            WAITING_FOR_ANDROID_VERSION: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_android_version), CommandHandler("cancel", cancel)],
            WAITING_FOR_APP_LINK: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_app_link), CommandHandler("cancel", cancel)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    idea_conversation = ConversationHandler(
        entry_points=[CommandHandler("idea", idea_start)],
        states={WAITING_FOR_IDEA: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_idea), CommandHandler("cancel", cancel)]},
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    broadcast_conversation = ConversationHandler(
        entry_points=[CommandHandler("broadcast", broadcast_start)],
        states={WAITING_FOR_BROADCAST: [MessageHandler(filters.TEXT & ~filters.COMMAND, broadcast_send), CommandHandler("cancel", cancel)]},
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    application.add_handler(broadcast_conversation)
    application.add_handler(idea_conversation)
    application.add_handler(CommandHandler("start", start))
    application.add_handler(suggest_conversation)
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(CommandHandler("approve", approve_command))
    application.add_handler(CommandHandler("reject", reject_command))
    application.add_handler(CommandHandler("myapps", myapps_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("catalog", catalog_command))
    application.add_handler(CommandHandler("stats", stats_command))

    print("🤖 OldDroidMarketBot запущен!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
