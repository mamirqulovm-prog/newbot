# --- minecraft_bot.py ---
import os
import logging
import asyncio
from pathlib import Path
from typing import Optional
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    InputMediaPhoto
)
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes, ConversationHandler
)
from telegram.constants import ParseMode

logging.basicConfig(
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
    level=logging.INFO
)
logger = logging.getLogger("MinecraftBot")

BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
ADMIN_LOGIN = "limed"
ADMIN_PASSWORD = "albatiros"

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)
for sub in ("mods", "resourcepacks", "shaders"):
    (UPLOAD_DIR / sub).mkdir(exist_ok=True)

THUMBNAILS_DIR = Path("thumbnails")
THUMBNAILS_DIR.mkdir(exist_ok=True)

CATEGORIES = {
    "mods": {
        "label": "🔧 Modlar",
        "accept": [".zip", ".rar", ".jar"],
        "thumb_required": True,
        "description": "Minecraft modlari (ZIP, RAR, JAR)"
    },
    "resourcepacks": {
        "label": "🎨 Resurs Paklar",
        "accept": [".zip", ".rar"],
        "thumb_required": True,
        "description": "Tekstura va resurs paketlari (ZIP, RAR)"
    },
    "shaders": {
        "label": "✨ Shaderlar",
        "accept": [".zip", ".rar"],
        "thumb_required": True,
        "description": "Shader paketlari (ZIP, RAR)"
    }
}

# Conversation states
(
    ADMIN_WAITING_LOGIN,
    ADMIN_WAITING_PASSWORD,
    ADMIN_PANEL,
    CHOOSING_CATEGORY,
    WAITING_THUMBNAIL,
    WAITING_FILE,
    WAITING_FILE_NAME,
    VIEWING_CATEGORY,
) = range(8)

admin_sessions: set[int] = set()

item_db: dict[str, list[dict]] = {
    "mods": [],
    "resourcepacks": [],
    "shaders": []
}

upload_state: dict[int, dict] = {}


def is_admin(user_id: int) -> bool:
    return user_id in admin_sessions


def main_menu_keyboard(user_id: int) -> InlineKeyboardMarkup:
    buttons = []
    for key, cat in CATEGORIES.items():
        buttons.append([InlineKeyboardButton(cat["label"], callback_data=f"view_{key}")])
    if is_admin(user_id):
        buttons.append([InlineKeyboardButton("⚙️ Admin Panel", callback_data="admin_panel")])
    else:
        buttons.append([InlineKeyboardButton("🔐 Admin Kirish", callback_data="admin_login")])
    return InlineKeyboardMarkup(buttons)


def admin_panel_keyboard() -> InlineKeyboardMarkup:
    buttons = []
    for key, cat in CATEGORIES.items():
        buttons.append([InlineKeyboardButton(f"➕ {cat['label']} yuklash", callback_data=f"upload_{key}")])
    buttons.append([InlineKeyboardButton("📊 Statistika", callback_data="stats")])
    buttons.append([InlineKeyboardButton("🚪 Chiqish", callback_data="admin_logout")])
    buttons.append([InlineKeyboardButton("🏠 Bosh Menu", callback_data="main_menu")])
    return InlineKeyboardMarkup(buttons)


def category_view_keyboard(category: str, items: list[dict]) -> InlineKeyboardMarkup:
    buttons = []
    for i, item in enumerate(items):
        buttons.append([InlineKeyboardButton(f"📦 {item['name']}", callback_data=f"item_{category}_{i}")])
    buttons.append([InlineKeyboardButton("🔙 Orqaga", callback_data="main_menu")])
    return InlineKeyboardMarkup(buttons)


def item_detail_keyboard(category: str, idx: int, user_id: int) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton("⬇️ Yuklab olish", callback_data=f"download_{category}_{idx}")]
    ]
    if is_admin(user_id):
        buttons.append([InlineKeyboardButton("🗑️ O'chirish", callback_data=f"delete_{category}_{idx}")])
    buttons.append([InlineKeyboardButton("🔙 Orqaga", callback_data=f"view_{category}")])
    return InlineKeyboardMarkup(buttons)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    text = (
        f"👋 Salom, {user.first_name}!\n\n"
        f"🎮 *Minecraft O'zbekcha Launcher* botiga xush kelibsiz!\n\n"
        f"Bu yerda siz modlar, resurs paklar va shaderlarni topishingiz mumkin.\n"
        f"Kerakli bo'limni tanlang:"
    )
    await update.message.reply_text(
        text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=main_menu_keyboard(user.id)
    )


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Optional[int]:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data

    if data == "main_menu":
        await query.edit_message_text(
            "🏠 *Bosh Menu*\n\nQaysi bo'limni ko'rmoqchisiz?",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=main_menu_keyboard(user_id)
        )
        return

    if data == "admin_login":
        if is_admin(user_id):
            await query.edit_message_text(
                "⚙️ *Admin Panel*\n\nNima qilmoqchisiz?",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=admin_panel_keyboard()
            )
            return
        await query.edit_message_text(
            "🔐 *Admin Kirish*\n\nAdmin loginini kiriting:",
            parse_mode=ParseMode.MARKDOWN
        )
        context.user_data["auth_step"] = "login"
        return ADMIN_WAITING_LOGIN

    if data == "admin_panel":
        if not is_admin(user_id):
            await query.answer("❌ Ruxsat yo'q!", show_alert=True)
            return
        await query.edit_message_text(
            "⚙️ *Admin Panel*\n\nNima qilmoqchisiz?",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=admin_panel_keyboard()
        )
        return

    if data == "admin_logout":
        admin_sessions.discard(user_id)
        await query.edit_message_text(
            "✅ Admin sifatida chiqdingiz.\n\nBosh menuga qaytdingiz:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=main_menu_keyboard(user_id)
        )
        return

    if data == "stats":
        if not is_admin(user_id):
            await query.answer("❌ Ruxsat yo'q!", show_alert=True)
            return
        stats_text = "📊 *Statistika*\n\n"
        for key, cat in CATEGORIES.items():
            count = len(item_db.get(key, []))
            stats_text += f"{cat['label']}: *{count}* ta\n"
        await query.edit_message_text(
            stats_text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Admin Panel", callback_data="admin_panel")]
            ])
        )
        return

    if data.startswith("view_"):
        category = data[5:]
        if category not in CATEGORIES:
            return
        items = item_db.get(category, [])
        cat_info = CATEGORIES[category]
        if not items:
            text = f"{cat_info['label']}\n\nHali hech narsa yuklanmagan."
        else:
            text = f"{cat_info['label']}\n\n{len(items)} ta narsa mavjud. Tanlang:"
        await query.edit_message_text(
            text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=category_view_keyboard(category, items)
        )
        return

    if data.startswith("item_"):
        parts = data.split("_", 3)
        if len(parts) < 3:
            return
        category = parts[1]
        try:
            idx = int(parts[2])
        except ValueError:
            return
        items = item_db.get(category, [])
        if idx >= len(items):
            await query.answer("Bu element topilmadi.", show_alert=True)
            return
        item = items[idx]
        cat_info = CATEGORIES[category]
        text = (
            f"📦 *{item['name']}*\n\n"
            f"📁 Kategoriya: {cat_info['label']}\n"
            f"📝 Tavsif: {item.get('description', 'Tavsif yo\'q')}\n"
            f"📏 Hajm: {item.get('size', 'Noma\'lum')}\n"
        )
        thumbnail_path = item.get("thumbnail")
        if thumbnail_path and Path(thumbnail_path).exists():
            with open(thumbnail_path, "rb") as thumb:
                await query.message.reply_photo(
                    photo=thumb,
                    caption=text,
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=item_detail_keyboard(category, idx, user_id)
                )
            await query.delete_message()
        else:
            await query.edit_message_text(
                text,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=item_detail_keyboard(category, idx, user_id)
            )
        return

    if data.startswith("download_"):
        parts = data.split("_", 3)
        if len(parts) < 3:
            return
        category = parts[1]
        try:
            idx = int(parts[2])
        except ValueError:
            return
        items = item_db.get(category, [])
        if idx >= len(items):
            await query.answer("Bu element topilmadi.", show_alert=True)
            return
        item = items[idx]
        file_path = Path(item.get("file_path", ""))
        if not file_path.exists():
            await query.answer("❌ Fayl topilmadi!", show_alert=True)
            return
        await query.answer("📤 Fayl yuborilmoqda...")
        with open(file_path, "rb") as f:
            await query.message.reply_document(
                document=f,
                filename=file_path.name,
                caption=f"📦 *{item['name']}*",
                parse_mode=ParseMode.MARKDOWN
            )
        return

    if data.startswith("delete_"):
        if not is_admin(user_id):
            await query.answer("❌ Ruxsat yo'q!", show_alert=True)
            return
        parts = data.split("_", 3)
        if len(parts) < 3:
            return
        category = parts[1]
        try:
            idx = int(parts[2])
        except ValueError:
            return
        items = item_db.get(category, [])
        if idx >= len(items):
            await query.answer("Bu element topilmadi.", show_alert=True)
            return
        removed = items.pop(idx)
        file_path = Path(removed.get("file_path", ""))
        thumb_path = Path(removed.get("thumbnail", ""))
        if file_path.exists():
            file_path.unlink()
        if thumb_path.exists():
            thumb_path.unlink()
        await query.edit_message_text(
            f"✅ *{removed['name']}* o'chirildi.\n\nAdmin panel:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=admin_panel_keyboard()
        )
        return

    if data.startswith("upload_"):
        if not is_admin(user_id):
            await query.answer("❌ Ruxsat yo'q!", show_alert=True)
            return
        category = data[7:]
        if category not in CATEGORIES:
            return
        cat_info = CATEGORIES[category]
        upload_state[user_id] = {"category": category, "step": "thumbnail"}
        await query.edit_message_text(
            f"📤 *{cat_info['label']} yuklash*\n\n"
            f"1️⃣ Birinchi — PNG rasm (thumbnail) yuboring:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("❌ Bekor qilish", callback_data="admin_panel")]
            ])
        )
        return WAITING_THUMBNAIL


async def receive_login(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if text == ADMIN_LOGIN:
        context.user_data["login_ok"] = True
        await update.message.reply_text("✅ Login to'g'ri!\n\n🔑 Endi parolni kiriting:")
        return ADMIN_WAITING_PASSWORD
    else:
        await update.message.reply_text(
            "❌ Noto'g'ri login. Qayta urinib ko'ring:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Orqaga", callback_data="main_menu")]
            ])
        )
        return ADMIN_WAITING_LOGIN


async def receive_password(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    user_id = update.effective_user.id
    if context.user_data.get("login_ok") and text == ADMIN_PASSWORD:
        admin_sessions.add(user_id)
        context.user_data.clear()
        await update.message.reply_text(
            "✅ *Admin sifatida kirdingiz!*\n\nAdmin panel:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=admin_panel_keyboard()
        )
        return ConversationHandler.END
    else:
        await update.message.reply_text(
            "❌ Noto'g'ri parol. Qaytadan urinib ko'ring:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Orqaga", callback_data="main_menu")]
            ])
        )
        return ADMIN_WAITING_PASSWORD


async def receive_thumbnail(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Optional[int]:
    user_id = update.effective_user.id
    if not is_admin(user_id):
        return ConversationHandler.END

    state = upload_state.get(user_id)
    if not state or state.get("step") != "thumbnail":
        return ConversationHandler.END

    if not update.message.photo:
        await update.message.reply_text(
            "❌ PNG rasm yuboring! Fayl emas, rasm.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("❌ Bekor qilish", callback_data="admin_panel")]
            ])
        )
        return WAITING_THUMBNAIL

    photo = update.message.photo[-1]
    file = await photo.get_file()
    thumb_path = THUMBNAILS_DIR / f"{user_id}_{photo.file_id}.jpg"
    await file.download_to_drive(str(thumb_path))

    upload_state[user_id]["thumbnail"] = str(thumb_path)
    upload_state[user_id]["step"] = "file"

    category = state["category"]
    cat_info = CATEGORIES[category]

    await update.message.reply_text(
        f"✅ Rasm qabul qilindi!\n\n"
        f"2️⃣ Endi *{cat_info['label']}* faylini yuboring\n"
        f"📎 Qabul qilinadigan formatlar: {', '.join(cat_info['accept'])}",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ Bekor qilish", callback_data="admin_panel")]
        ])
    )
    return WAITING_FILE


async def receive_file(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Optional[int]:
    user_id = update.effective_user.id
    if not is_admin(user_id):
        return ConversationHandler.END

    state = upload_state.get(user_id)
    if not state or state.get("step") != "file":
        return ConversationHandler.END

    if not update.message.document:
        await update.message.reply_text(
            "❌ Fayl yuboring! (ZIP, RAR yoki JAR)",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("❌ Bekor qilish", callback_data="admin_panel")]
            ])
        )
        return WAITING_FILE

    doc = update.message.document
    filename = doc.file_name or "unknown"
    ext = Path(filename).suffix.lower()
    category = state["category"]
    cat_info = CATEGORIES[category]

    if ext not in cat_info["accept"]:
        allowed = ", ".join(cat_info["accept"])
        await update.message.reply_text(
            f"❌ Bu format qabul qilinmaydi!\n"
            f"Faqat: {allowed}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("❌ Bekor qilish", callback_data="admin_panel")]
            ])
        )
        return WAITING_FILE

    file_obj = await doc.get_file()
    dest_path = UPLOAD_DIR / category / filename
    counter = 1
    while dest_path.exists():
        dest_path = UPLOAD_DIR / category / f"{Path(filename).stem}_{counter}{ext}"
        counter += 1

    await file_obj.download_to_drive(str(dest_path))

    size_bytes = dest_path.stat().st_size
    if size_bytes < 1024 * 1024:
        size_str = f"{size_bytes / 1024:.1f} KB"
    else:
        size_str = f"{size_bytes / (1024 * 1024):.1f} MB"

    upload_state[user_id]["file_path"] = str(dest_path)
    upload_state[user_id]["original_name"] = Path(filename).stem
    upload_state[user_id]["size"] = size_str
    upload_state[user_id]["step"] = "name"

    await update.message.reply_text(
        f"✅ Fayl qabul qilindi! ({size_str})\n\n"
        f"3️⃣ Bu *{cat_info['label']}* uchun nom kiriting:\n"
        f"(Ko'rsatiladigan nom — masalan: 'Optifine 1.20.1')",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ Bekor qilish", callback_data="admin_panel")]
        ])
    )
    return WAITING_FILE_NAME


async def receive_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    if not is_admin(user_id):
        return ConversationHandler.END

    state = upload_state.get(user_id)
    if not state or state.get("step") != "name":
        return ConversationHandler.END

    item_name = update.message.text.strip()
    if not item_name:
        await update.message.reply_text("❌ Nom bo'sh bo'lmasin. Qayta kiriting:")
        return WAITING_FILE_NAME

    category = state["category"]
    cat_info = CATEGORIES[category]

    new_item = {
        "name": item_name,
        "file_path": state["file_path"],
        "thumbnail": state["thumbnail"],
        "size": state["size"],
        "description": f"{cat_info['label']} - {item_name}",
        "uploader_id": user_id,
    }
    item_db[category].append(new_item)
    del upload_state[user_id]

    await update.message.reply_text(
        f"🎉 *{item_name}* muvaffaqiyatli yuklandi!\n\n"
        f"📁 Kategoriya: {cat_info['label']}\n"
        f"📏 Hajm: {new_item['size']}\n\n"
        f"Admin panel:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=admin_panel_keyboard()
    )
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    upload_state.pop(user_id, None)
    if update.callback_query:
        await update.callback_query.edit_message_text(
            "❌ Bekor qilindi.\n\nAdmin panel:",
            reply_markup=admin_panel_keyboard() if is_admin(user_id) else main_menu_keyboard(user_id)
        )
    else:
        await update.message.reply_text(
            "❌ Bekor qilindi.",
            reply_markup=main_menu_keyboard(user_id)
        )
    return ConversationHandler.END


def main() -> None:
    app = Application.builder().token(BOT_TOKEN).build()

    auth_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(button_handler, pattern="^admin_login$")],
        states={
            ADMIN_WAITING_LOGIN: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_login)
            ],
            ADMIN_WAITING_PASSWORD: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_password)
            ],
        },
        fallbacks=[
            CommandHandler("start", start),
            CallbackQueryHandler(cancel, pattern="^main_menu$")
        ],
        per_message=False
    )

    upload_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(button_handler, pattern="^upload_")],
        states={
            WAITING_THUMBNAIL: [
                MessageHandler(filters.PHOTO, receive_thumbnail),
                CallbackQueryHandler(cancel, pattern="^admin_panel$")
            ],
            WAITING_FILE: [
                MessageHandler(filters.Document.ALL, receive_file),
                CallbackQueryHandler(cancel, pattern="^admin_panel$")
            ],
            WAITING_FILE_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_name),
                CallbackQueryHandler(cancel, pattern="^admin_panel$")
            ],
        },
        fallbacks=[
            CommandHandler("start", start),
            CallbackQueryHandler(cancel, pattern="^admin_panel$")
        ],
        per_message=False
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(auth_conv)
    app.add_handler(upload_conv)
    app.add_handler(CallbackQueryHandler(button_handler))

    logger.info("Bot ishga tushmoqda...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
