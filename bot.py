import os
import base64
import asyncio
import tempfile
import requests

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
        [
            InlineKeyboardButton("🎬 Создать видео", callback_data="create"),
        ],
        [
            InlineKeyboardButton("📷 Видео из фото", callback_data="photo"),
        ],
        [
            InlineKeyboardButton("🎨 Стиль", callback_data="style"),
            InlineKeyboardButton("📐 9:16", callback_data="ratio"),
        ],
        [
            InlineKeyboardButton("⏱ 10 секунд", callback_data="duration"),
        ],
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


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    user_data[user_id] = {
        "style": "realistic",
        "photo": None,
        "waiting_prompt": False,
    }

    await update.message.reply_text(
        "🎬 Добро пожаловать в AI Video Bot!\n\n"
        "Здесь ты сможешь создавать короткие AI-видео.\n\n"
        "Сейчас доступны:\n"
        "🎬 Видео по описанию\n"
        "📷 Видео из фотографии\n"
        "🎨 Несколько стилей\n"
        "📐 Формат 9:16\n"
        "⏱ Длительность 10 секунд\n\n"
        "Выбери действие:",
        reply_markup=main_menu(),
    )


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id

    if user_id not in user_data:
        user_data[user_id] = {
            "style": "realistic",
            "photo": None,
            "waiting_prompt": False,
        }

    if query.data == "create":
        user_data[user_id]["photo"] = None
        user_data[user_id]["waiting_prompt"] = True

        await query.message.reply_text(
            "🎬 Отлично!\n\n"
            "Напиши, какое видео хочешь создать.\n\n"
            "Например:\n"
            "«Девушка идёт по улице, начинается сильный дождь, "
            "она удивлённо смотрит на небо. Кинематографичная съёмка.»\n\n"
            "После сообщения я запущу генерацию."
        )

    elif query.data == "photo":
        user_data[user_id]["waiting_prompt"] = False

        await query.message.reply_text(
            "📷 Пришли мне фотографию, из которой нужно сделать видео.\n\n"
            "После фотографии я попрошу описание движения."
        )

    elif query.data == "style":
        await query.message.reply_text(
            "🎨 Выбери стиль:",
            reply_markup=style_menu(),
        )

    elif query.data.startswith("style_"):
        style = query.data.replace("style_", "")

        if style in STYLES:
            user_data[user_id]["style"] = style

        await query.message.reply_text(
            f"✅ Стиль выбран: {style}\n\n"
            "Теперь можно создавать видео.",
            reply_markup=main_menu(),
        )

    elif query.data == "ratio":
        await query.message.reply_text(
            "📐 Формат установлен: 9:16\n"
            "Итоговый формат: 720 × 1280"
        )

    elif query.data == "duration":
        await query.message.reply_text(
            "⏱ Длительность установлена: 10 секунд."
        )

    elif query.data == "back":
        await query.message.reply_text(
            "Главное меню:",
            reply_markup=main_menu(),
        )


async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if user_id not in user_data:
        user_data[user_id] = {
            "style": "realistic",
            "photo": None,
            "waiting_prompt": False,
        }

    photo = update.message.photo[-1]

    telegram_file = await context.bot.get_file(photo.file_id)

    file_bytes = await telegram_file.download_as_bytearray()

    encoded = base64.b64encode(file_bytes).decode("utf-8")

    user_data[user_id]["photo"] = f"data:image/jpeg;base64,{encoded}"
    user_data[user_id]["waiting_prompt"] = True

    await update.message.reply_text(
        "📷 Фото получено!\n\n"
        "Теперь напиши, что должно происходить в видео.\n\n"
        "Например:\n"
        "«Девушка улыбается, ветер красиво развевает волосы, "
        "она поворачивается к камере.»"
    )


async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if user_id not in user_data:
        user_data[user_id] = {
            "style": "realistic",
            "photo": None,
            "waiting_prompt": False,
        }

    if not user_data[user_id].get("waiting_prompt"):
        await update.message.reply_text(
            "Выбери действие в меню 👇",
            reply_markup=main_menu(),
        )
        return

    prompt = update.message.text.strip()

    if not prompt:
        return

    style_key = user_data[user_id].get("style", "realistic")
    style = STYLES.get(style_key, STYLES["realistic"])

    final_prompt = (
        f"{style}. "
        f"{prompt}. "
        "Vertical social media video, 9:16 composition, "
        "clear subject, natural movement, cinematic camera motion, "
        "high visual quality."
    )

    photo = user_data[user_id].get("photo")

    user_data[user_id]["waiting_prompt"] = False

    status_message = await update.message.reply_text(
        "🎬 Генерирую видео...\n\n"
        "Это может занять несколько минут ⏳"
    )

    try:
        video_url = await generate_video(
            prompt=final_prompt,
            photo=photo,
        )

        video_file = await download_video(video_url)

        await status_message.edit_text(
            "✅ Видео готово! Загружаю его сюда..."
        )

        with open(video_file, "rb") as video:
            await update.message.reply_video(
                video=video,
                caption="🎬 Готово!\n\nСоздано через AI Video Bot.",
            )

        try:
            os.remove(video_file)
        except Exception:
            pass

        await update.message.reply_text(
            "Что сделаем дальше?",
            reply_markup=main_menu(),
        )

    except TaskFailedError as e:
        await status_message.edit_text(
            "❌ Runway не смог создать видео.\n\n"
            "Попробуй изменить описание и повторить."
        )

        print("RUNWAY ERROR:", e)

    except Exception as e:
        await status_message.edit_text(
            "❌ Произошла ошибка при создании видео.\n\n"
            "Проверь настройки API и попробуй ещё раз."
        )

        print("ERROR:", e)


async def generate_video(prompt, photo=None):
    if photo:
        task = await asyncio.to_thread(
            lambda: client.image_to_video.create(
                model="gen4.5",
                prompt_image=photo,
                prompt_text=prompt,
                ratio="720:1280",
                duration=10,
            ).wait_for_task_output()
        )
    else:
        task = await asyncio.to_thread(
            lambda: client.image_to_video.create(
                model="gen4.5",
                prompt_text=prompt,
                ratio="720:1280",
                duration=10,
            ).wait_for_task_output()
        )

    return task.output[0]


async def download_video(url):
    response = await asyncio.to_thread(
        lambda: requests.get(url, timeout=180)
    )

    response.raise_for_status()

    temporary_file = tempfile.NamedTemporaryFile(
        delete=False,
        suffix=".mp4",
    )

    temporary_file.write(response.content)
    temporary_file.close()

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
            text_handler
        )
    )

    print("AI Video Bot started!")

    application.run_polling()


if __name__ == "__main__":
    main()
