import os
import tempfile
import asyncio

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

from magic_hour import AsyncClient


TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
MAGIC_HOUR_API_KEY = os.environ["MAGIC_HOUR_API_KEY"]

client = AsyncClient(token=MAGIC_HOUR_API_KEY)


user_settings = {}


STYLES = {
    "realistic": "maximum photorealistic live-action cinematic realism, real human actors",
    "pixar": "high-quality stylized 3D animated movie look, expressive characters, cinematic lighting",
    "barbie": "luxury Barbie-inspired world, glossy pastel pink aesthetic, glamorous cinematic lighting",
    "cinematic": "cinematic film look, dramatic lighting, realistic camera movement, premium production quality",
    "funny": "funny cinematic visual style, expressive reactions, comedic timing",
}


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🎬 Создать видео", callback_data="create")],
        [InlineKeyboardButton("🖼 Видео из фото", callback_data="image")],
    ]

    await update.message.reply_text(
        "🎥 Добро пожаловать в AI Video Studio!\n\n"
        "Я помогу создать короткое AI-видео.\n\n"
        "Выбери способ создания:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id

    if query.data == "create":
        user_settings[user_id] = {
            "mode": "text",
            "style": "realistic",
            "ratio": "9:16",
            "duration": 5,
        }

        keyboard = [
            [
                InlineKeyboardButton("🎬 Realistic", callback_data="style_realistic"),
                InlineKeyboardButton("🧸 Pixar 3D", callback_data="style_pixar"),
            ],
            [
                InlineKeyboardButton("💗 Barbie", callback_data="style_barbie"),
                InlineKeyboardButton("🎞 Cinematic", callback_data="style_cinematic"),
            ],
            [
                InlineKeyboardButton("😂 Funny", callback_data="style_funny"),
            ],
        ]

        await query.edit_message_text(
            "Выбери стиль видео:",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    elif query.data == "image":
        user_settings[user_id] = {
            "mode": "image",
            "style": "realistic",
            "ratio": "9:16",
            "duration": 5,
        }

        await query.edit_message_text(
            "🖼 Отправь мне фотографию.\n\n"
            "После этого я попрошу описание движения для видео."
        )

    elif query.data.startswith("style_"):
        style = query.data.replace("style_", "")

        user_settings[user_id]["style"] = style

        keyboard = [
            [InlineKeyboardButton("9:16", callback_data="ratio_9:16")],
        ]

        await query.edit_message_text(
            f"Стиль выбран: {style}\n\n"
            "Теперь выбери формат:",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    elif query.data.startswith("ratio_"):
        ratio = query.data.replace("ratio_", "")

        user_settings[user_id]["ratio"] = ratio

        keyboard = [
            [
                InlineKeyboardButton("5 секунд", callback_data="duration_5"),
                InlineKeyboardButton("10 секунд", callback_data="duration_10"),
            ]
        ]

        await query.edit_message_text(
            "Выбери длительность:",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    elif query.data.startswith("duration_"):
        duration = int(query.data.replace("duration_", ""))

        user_settings[user_id]["duration"] = duration

        await query.edit_message_text(
            "✍️ Теперь отправь описание видео.\n\n"
            "Например:\n"
            "«Девушка идёт по улице под дождём, "
            "ветер развевает волосы, камера плавно приближается»"
        )


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id

    if user_id not in user_settings:
        await update.message.reply_text(
            "Сначала нажми /start и выбери «Видео из фото»."
        )
        return

    if user_settings[user_id].get("mode") != "image":
        return

    photo = update.message.photo[-1]

    file = await context.bot.get_file(photo.file_id)

    temp_dir = tempfile.mkdtemp()
    image_path = os.path.join(temp_dir, "input.jpg")

    await file.download_to_drive(image_path)

    user_settings[user_id]["image_path"] = image_path

    await update.message.reply_text(
        "Фото получено ✅\n\n"
        "Теперь напиши, что должно происходить в видео."
    )


async def generate_video(prompt, settings):
    temp_dir = tempfile.mkdtemp()

    style = STYLES.get(settings["style"], STYLES["realistic"])

    full_prompt = f"""
{style}.

{prompt}

Vertical {settings["ratio"]}.
Smooth natural motion.
Clear visible action.
Strong visual composition.
No subtitles.
No text on screen.
No watermark.
"""

    if settings["mode"] == "text":

        response = await client.v1.text_to_video.generate(
            prompt=full_prompt,
            aspect_ratio=settings["ratio"],
            duration_seconds=settings["duration"],
            name="Telegram AI Video",
            wait_for_completion=True,
            download_outputs=True,
            download_directory=temp_dir,
        )

    else:

        response = await client.v1.image_to_video.generate(
            prompt=full_prompt,
            assets={
                "image_file_path": settings["image_path"]
            },
            aspect_ratio=settings["ratio"],
            duration_seconds=settings["duration"],
            name="Telegram Image To Video",
            wait_for_completion=True,
            download_outputs=True,
            download_directory=temp_dir,
        )

    paths = getattr(response, "downloaded_paths", None)

    if not paths:
        raise RuntimeError(
            f"Видео не было скачано. Ответ Magic Hour: {response}"
        )

    return paths[0]


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id

    if user_id not in user_settings:
        await update.message.reply_text(
            "Нажми /start, чтобы начать."
        )
        return

    settings = user_settings[user_id]

    if settings.get("mode") == "image" and "image_path" not in settings:
        await update.message.reply_text(
            "Сначала отправь фотографию 🖼"
        )
        return

    prompt = update.message.text

    await update.message.reply_text(
        "🎬 Генерирую видео...\n\n"
        "Это может занять некоторое время."
    )

    try:
        video_path = await generate_video(prompt, settings)

        with open(video_path, "rb") as video:
            await update.message.reply_video(
                video=video,
                caption="✨ Готово!"
            )

    except Exception as e:
        print("MAGIC HOUR ERROR:", repr(e))

        await update.message.reply_text(
            "❌ Не удалось создать видео.\n\n"
            "Я уже записал ошибку в Railway Logs."
        )


def main():
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))

    app.add_handler(
        MessageHandler(filters.PHOTO, handle_photo)
    )

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_text
        )
    )

    print("Bot started")

    app.run_polling()


if __name__ == "__main__":
    main()
