
import os
import logging
import asyncio
import aiohttp
from aiogram import Bot, Dispatcher, types
from aiogram.contrib.middlewares.logging import LoggingMiddleware
from aiogram.utils.executor import start_webhook
from yt_dlp import YoutubeDL

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Bot token (Hardcoded as requested)
BOT_TOKEN = '8850260949:AAFi6v3p_W7jwDyDsABZZ_q9hKXSgANsbog'

# Webhook settings
WEBHOOK_HOST = os.getenv('WEBHOOK_HOST')
WEBHOOK_PATH = f'/webhook/{BOT_TOKEN}'
WEBAPP_HOST = '0.0.0.0'
WEBAPP_PORT = int(os.getenv('PORT', 8080))

if not WEBHOOK_HOST:
    # Fallback for local testing or if not provided
    WEBHOOK_HOST = "https://your-app-name.onrender.com"

WEBHOOK_URL = f'{WEBHOOK_HOST}{WEBHOOK_PATH}'

# Initialize bot and dispatcher
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)
dp.middleware.setup(LoggingMiddleware())

# Common yt-dlp options
COMMON_OPTS = {
    'noplaylist': True,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'ytsearch',
    'source_address': '0.0.0.0', # help with ipv6 issues
}

# Keep-alive mechanism for Render Free Tier
async def keep_alive():
    """Pings the webhook URL every 5 minutes to prevent the service from sleeping."""
    # Wait a bit before starting pings
    await asyncio.sleep(30)
    while True:
        try:
            # We ping the root URL or webhook path to keep the server active
            async with aiohttp.ClientSession() as session:
                async with session.get(WEBHOOK_HOST) as response:
                    logger.info(f"Keep-alive ping sent to {WEBHOOK_HOST}, status: {response.status}")
        except Exception as e:
            logger.error(f"Keep-alive ping failed: {e}")
        # Render Free Tier sleeps after 15 mins of inactivity, so 5-10 mins is safe
        await asyncio.sleep(300) 


@dp.message_handler(commands=['start', 'help'])
async def send_welcome(message: types.Message):
    welcome_text = (
        "👋 سلام! به ربات پیشرفته دانلود موسیقی و ویدیو خوش آمدید.\n\n"
        "🔹 **نحوه استفاده:**\n"
        "1️⃣ اسم آهنگ یا خواننده را بفرستید (MP3 دریافت کنید).\n"
        "2️⃣ برای دانلود **ویدیو**، قبل از اسم آهنگ کلمه 'video' یا 'ویدیو' را بنویسید.\n"
        "3️⃣ می‌توانید **ویس (Voice)** بفرستید (در حال حاضر نام آهنگ را از ویس تشخیص نمی‌دهم اما زیرساخت آماده است).\n\n"
        "🚀 این ربات برای پایداری در Render بهینه‌سازی شده است."
    )
    await message.reply(welcome_text, parse_mode='Markdown')

async def download_and_send(message, query, is_video=False):
    status_msg = await message.reply("🔍 در حال جستجو...")
    
    try:
        # Define search query
        search_query = f"ytsearch1: {query}"
        if not is_video:
            search_query += " audio"

        ydl_opts = COMMON_OPTS.copy()
        if is_video:
            ydl_opts.update({
                'format': 'best[ext=mp4]/best',
                'outtmpl': '%(id)s.mp4',
            })
        else:
            ydl_opts.update({
                'format': 'bestaudio/best',
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
                'outtmpl': '%(id)s.mp3',
            })

        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(search_query, download=True)
            if 'entries' in info:
                video_info = info['entries'][0]
            else:
                video_info = info
            
            file_ext = 'mp4' if is_video else 'mp3'
            file_path = f"{video_info['id']}.{file_ext}"
            title = video_info.get('title', 'Unknown')

            await status_msg.edit_text("✅ فایل آماده شد! در حال ارسال...")

            if os.path.exists(file_path):
                with open(file_path, 'rb') as f:
                    if is_video:
                        await bot.send_video(message.chat.id, f, caption=f"🎬 {title}")
                    else:
                        await bot.send_audio(message.chat.id, f, caption=f"🎵 {title}")
                os.remove(file_path)
            else:
                await status_msg.edit_text("❌ خطا در دانلود فایل.")

    except Exception as e:
        logger.error(f"Error: {e}")
        await status_msg.edit_text("❌ متاسفانه مشکلی پیش آمد. شاید آهنگ پیدا نشد یا محدودیت یوتیوب اعمال شده است.")

@dp.message_handler(content_types=['text'])
async def handle_text(message: types.Message):
    text = message.text.lower()
    is_video = False
    query = text

    if text.startswith(('video', 'ویدیو')):
        is_video = True
        query = text.replace('video', '').replace('ویدیو', '').strip()
    
    if not query:
        await message.reply("لطفا نام آهنگ را بعد از کلمه 'ویدیو' وارد کنید.")
        return

    await download_and_send(message, query, is_video)

@dp.message_handler(content_types=['voice'])
async def handle_voice(message: types.Message):
    await message.reply("🎙 من ویس شما را دریافت کردم. در نسخه‌های آینده قابلیت تشخیص نام آهنگ از روی صدا (Shazam-like) اضافه خواهد شد. فعلاً لطفاً نام آهنگ را تایپ کنید.")

async def on_startup(dp):
    logger.info('Starting up..')
    await bot.set_webhook(WEBHOOK_URL)
    # Start keep-alive in background
    asyncio.create_task(keep_alive())

async def on_shutdown(dp):
    logger.info('Shutting down..')
    await bot.delete_webhook()

from aiohttp import web

async def handle_root(request):
    return web.Response(text="Bot is alive and running!")

if __name__ == '__main__':
    # Create the web app for webhook
    from aiogram.utils.executor import _setup_webapp
    
    loop = asyncio.get_event_loop()
    app = web.Application()
    app.router.add_get('/', handle_root) # Health check endpoint
    
    # Setup aiogram webhook on the same app
    _setup_webapp(dp, WEBHOOK_PATH, app)
    
    app.on_startup.append(lambda _: on_startup(dp))
    app.on_shutdown.append(lambda _: on_shutdown(dp))
    
    web.run_app(app, host=WEBAPP_HOST, port=WEBAPP_PORT)
