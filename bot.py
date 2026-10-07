import os
import asyncio
import tempfile
import urllib.request
import base64

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

from runwayml import RunwayML, TaskFailedError


TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
RUNWAY_API_SECRET = os.environ["RUNWAY_API_SECRET"]

client = RunwayML(api_key=RUNWAY_API_SECRET)

user_data = {}


STYLES = {
    "realistic": "maximum photorealistic cinematic live-action realism",
    "pixar": "high-quality polished 3D animated movie style",
    "barbie": "luxury Barbie-inspired pastel pink glamorous aesthetic",
    "cinematic": "cinematic movie look, dramatic lighting, realistic camera movement",
    "funny": "funny viral social media video, expressive reactions, comedic timing",
}


def main_menu():
    keyboard = [
        [InlineKeyboardButton("🎬 Создать видео", callback_data="create")],
        [InlineKeyboardButton("📷 Видео из фото", callback_data="photo")],
        [
            InlineKeyboardButton("🎨 Стиль", callback_data="style"),
            InlineKeyboardButton("📐 9:16", callback_data="ratio"),
        ],
        [InlineKeyboardButton("⏱ 10 секунд", callback_data="duration")],
    ]

    return InlineKeyboardMarkup(keyboard)


def style_menu():
    keyboard = [
        [InlineKeyboardButton("🎥 Реализм", callback_data="style_realistic")],
        [InlineKeyboardButton("✨ Pixar 3D", callback_data="style_pixar")],
        [InlineKeyboardButton("💗 Barbie", callback_data="style_barbie")],
        [InlineKeyboardButton("🎬 Кино", callback_data="style_cinematic")],
        [InlineKeyboardButton("😂 Вирусный юмор", callback_data="style_funny")],
        [InlineKeyboardButton("⬅️ Назад", callback_data="back")],
    ]

    return InlineKeyboardMarkup(keyboard)


def get_user(user_id):
    if user_id not in user_data:
        user_data[user_id] = {
            "style": "realistic",
            "photo": None,
            "waiting_prompt": False,
        }

    return user_data[user_id]


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    get_user(update.effective_user.id)

    await update.message.reply_text(
        "🎬 Добро пожаловать в AI Video Bot!\n\n"
        "Выбери действие:",
        reply_markup=main_menu(),
    )


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user = get_user(query.from_user.id)

    if query.data == "create":
        user["photo"] = None
        user["waiting_prompt"] = True

        await query.message.reply_text(
            "🎬 Напиши описание видео.\n\n"
            "Например: девушка идёт по улице, начинается дождь, "
            "она удивлённо смотрит на небо."
        )

    elif query.data == "photo":
        user["waiting_prompt"] = False

        await query.message.reply_text(
            "📷 Пришли фотографию.\n\n"
            "После неё я попрошу описание движения."
        )

    elif query.data == "style":
        await query.message.reply_text(
            "🎨 Выбери стиль:",
            reply_markup=style_menu(),
        )

    elif query.data.startswith("style_"):
        style = query.data.replace("style_", "")

        if style in STYLES:
            user["style"] = style

        await query.message.reply_text(
            "✅ Стиль выбран.",
            reply_markup=main_menu(),
        )

    elif query.data == "ratio":
        await query.message.reply_text(
            "📐 Формат: 9:16"
        )

    elif query.data == "duration":
        await query.message.reply_text(
            "⏱ Длительность: 10 секунд."
        )

    elif query.data == "back":
        await query.message.reply_text(
            "Главное меню:",
            reply_markup=main_menu(),
        )


async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = get_user(update.effective_user.id)

    photo = update.message.photo[-1]

    telegram_file = await context.bot.get_file(photo.file_id)

    file_bytes = await telegram_file.download_as_bytearray()

    user["photo"] = bytes(file_bytes)
    user["waiting_prompt"] = True

    await update.message.reply_text(
        "📷 Фото получено!\n\n"
        "Теперь напиши, что должно происходить в видео."
    )


async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = get_user(update.effective_user.id)

    if not user["waiting_prompt"]:
        await update.message.reply_text(
            "Выбери действие в меню 👇",
            reply_markup=main_menu(),
        )
        return

    prompt = update.message.text.strip()

    if not prompt:
        return

    style = STYLES.get(
        user["style"],
        STYLES["realistic"]
    )

    final_prompt = (
        f"{style}. "
        f"{prompt}. "
        "Vertical social media video, 9:16 composition, "
        "clear subject, natural movement, cinematic camera motion, "
        "high visual quality."
    )

    photo = user["photo"]

    user["waiting_prompt"] = False

    status_message = await update.message.reply_text(
        "🎬 Генерирую видео...\n\n"
        "Это может занять несколько минут ⏳"
    )

    try:
        video_url = await generate_video(
            prompt=final_prompt,
            photo=photo,
        )

        await status_message.edit_text(
            "⬇️ Видео готово! Загружаю..."
        )

        video_file = await download_video(video_url)

        with open(video_file, "rb") as video:
            await update.message.reply_video(
                video=video,
                caption="🎬 Готово!",
            )

        os.remove(video_file)

        await update.message.reply_text(
            "Что сделаем дальше?",
            reply_markup=main_menu(),
        )

    except TaskFailedError:
        await status_message.edit_text(
            "❌ Runway не смог создать видео.\n\n"
            "Попробуй другое описание."
        )

    except Exception as e:
        await status_message.edit_text(
            "❌ Ошибка при создании видео."
        )

        print("ERROR:", repr(e))


async def generate_video(prompt, photo=None):

    # ==========================================
    # РЕЖИМ 1 — ТЕКСТ → ВИДЕО
    # ==========================================

    if photo is None:

        task = await asyncio.to_thread(
            lambda: client.text_to_video.create(
                model="gen4.5",
                prompt_text=prompt,
                ratio="720:1280",
                duration=10,
            ).wait_for_task_output()
        )

    # ==========================================
    # РЕЖИМ 2 — ФОТО → ВИДЕО
    # ==========================================

    else:

        image_base64 = base64.b64encode(photo).decode("utf-8")

        prompt_image = (
            f"data:image/jpeg;base64,{image_base64}"
        )

        task = await asyncio.to_thread(
            lambda: client.image_to_video.create(
                model="gen4.5",
                prompt_image=prompt_image,
                prompt_text=prompt,
                ratio="720:1280",
                duration=10,
            ).wait_for_task_output()
        )

    return task.output[0]


async def download_video(url):

    temporary_file = tempfile.NamedTemporaryFile(
        delete=False,
        suffix=".mp4",
    )

    temporary_file.close()

    await asyncio.to_thread(
        urllib.request.urlretrieve,
        url,
        temporary_file.name,
    )

    return temporary_file.name


def main():

    application = (
        Application.builder()
        .token(TELEGRAM_BOT_TOKEN)
        .build()
    )

    application.add_handler(
        CommandHandler("start", start)
    )

    application.add_handler(
        CallbackQueryHandler(button_handler)
    )

    application.add_handler(
        MessageHandler(
            filters.PHOTO,
            photo_handler
        )
    )

    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            text_handler,
        )
    )

    print("AI Video Bot started!")

    application.run_polling()


if __name__ == "__main__":
    main()
