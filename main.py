import os
import re
import asyncio
import logging
import tempfile
import subprocess
from typing import Optional, Dict, Any
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, FSInputFile
from aiogram.filters import CommandStart
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from aiohttp import web
import yt_dlp

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не найден в .env файле")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
)
logger = logging.getLogger(__name__)

IG_URL_PATTERN = re.compile(
    r"((?:https?://)?(?:www\.)?instagram\.com/(?:p|reel|reels|tv)/[A-Za-z0-9_-]+/?.*)")

def get_video_resolution(filepath: str) -> str:
    try:
        cmd = [
            'ffprobe', '-v', 'error',
            '-select_streams', 'v:0',
            '-show_entries', 'stream=width,height',
            '-of', 'csv=s=x:p=0',
            filepath
        ]
        result = subprocess.run(cmd, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True, check=True)
        res = result.stdout.strip()
        return res if res else "Неизвестно"
    except Exception as e:
        logger.error(f"Ошибка ffprobe при чтении файла {filepath}: {e}")
        return "Неизвестно"

def extract_instagram_video(url: str, temp_dir: str) -> Optional[Dict[str, Any]]:
    ydl_opts = {
        'format': 'best',
        'outtmpl': os.path.join(temp_dir, '%(id)s.%(ext)s'),
        'quiet': True,
        'no_warnings': True,
        'geo_bypass': True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if not info:
                return None

            filepath = ydl.prepare_filename(info)
            width = info.get('width')
            height = info.get('height')

            if width and height:
                res_str = f"{width}x{height}"
            else:
                res_str = info.get('resolution')
                if not res_str or 'x' not in res_str:
                    res_str = get_video_resolution(filepath)

            return {
                "path": filepath,
                "resolution": res_str
            }
    except Exception as e:
        logger.error(f"Ошибка yt-dlp при скачивании {url}: {e}")
        return None

async def process_download(message: Message, url: str):
    if not url.startswith("http"):
        url = "https://" + url

    status_msg = await message.reply("⏳ Скачивание в максимальном качестве...")

    with tempfile.TemporaryDirectory() as temp_dir:
        data = await asyncio.to_thread(extract_instagram_video, url, temp_dir)

        if not data or not os.path.exists(data['path']):
            await status_msg.edit_text(
                "❌ Ошибка скачивания. Возможно, аккаунт закрыт или ссылка неверна")
            return

        video_path = data['path']
        resolution = data['resolution']

        file_size_bytes = os.path.getsize(video_path)

        if file_size_bytes > 50 * 1024 * 1024:
            await status_msg.edit_text(
                "❌ Файл видео слишком большой (>50 МБ)")
            return

        await status_msg.edit_text("📤 Отправление видео в чат...")

        try:
            video = FSInputFile(video_path)
            caption = f"✅ Скачано в максимальном качестве ({resolution})"

            await message.reply_video(
                video=video,
                caption=caption,
                show_caption_above_media=True,
                supports_streaming=True
            )
            await status_msg.delete()
        except Exception as e:
            logger.error(f"Ошибка отправки видео в Telegram: {e}")
            await status_msg.edit_text("❌ Ошибка при отправлении видео в чат")


dp = Dispatcher()

@dp.message(CommandStart())
async def cmd_start(message: Message):
    await message.answer(
        "Отправьте ссылку на видео из Instagram для скачивания"
    )

@dp.message(F.text)
async def handle_text(message: Message):
    match = IG_URL_PATTERN.search(message.text)

    if match:
        ig_url = match.group(1)
        asyncio.create_task(process_download(message, ig_url))

async def handle_ping(request):
    return web.Response(text="Bot is running")

async def main():
    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )

    # Инициализация фиктивного веб-сервера для прохождения проверок Render
    app = web.Application()
    app.router.add_get('/', handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    
    port = int(os.environ.get('PORT', 10000))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    
    logger.info(f"Слушатель портов запущен на порту {port}. Ожидание сообщений...")

    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    finally:
        await bot.session.close()
        await runner.cleanup()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Бот остановлен")
