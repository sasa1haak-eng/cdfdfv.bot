import os
import logging
import tempfile
import re
import sys
import time
import shutil
import json

# ملاحظة: يجب تثبيت المكتبات التالية قبل التشغيل:
# pip install python-telegram-bot==20.3 yt-dlp requests
# في Pydroid3: القائمة > Pip > ابحث عن المكتبة > Install

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
import yt_dlp
import requests

# إعدادات التسجيل
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# توكن البوت
TOKEN = "8152233217:AAF49cxWF2rl8avd6MywMXRhxRoXc2-WJ24"

# قائمة المنصات المدعومة
PLATFORMS = {
    'youtube': 'يوتيوب',
    'tiktok': 'تيك توك',
    'snapchat': 'سناب شات',
    'pinterest': 'بنترست',
    'facebook': 'فيسبوك',
    'instagram': 'انستغرام',
    'likee': 'لايك',
    'twitter': 'تويتر',
    'other': 'منصة أخرى'
}

# ====== دوال التحميل من APIs بديلة ======

def download_via_cobalt(url):
    """تحميل عبر Cobalt API - يدعم معظم المنصات"""
    try:
        api_urls = [
            "https://api.cobalt.tools/api/json",
        ]
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json"
        }
        payload = {
            "url": url,
            "vCodec": "h264",
            "vQuality": "720",
            "aFormat": "mp3",
            "isNoTTWatermark": True
        }
        for api_url in api_urls:
            try:
                r = requests.post(api_url, json=payload, headers=headers, timeout=20)
                if r.status_code == 200:
                    data = r.json()
                    if data.get("status") == "stream" or data.get("status") == "redirect":
                        return data.get("url")
            except Exception:
                continue
    except Exception as e:
        logger.warning(f"Cobalt API failed: {e}")
    return None

def download_via_tiktok_api(url):
    """تحميل تيك توك عبر tikwm API"""
    try:
        api = "https://tikwm.com/api/"
        data = {"url": url}
        r = requests.post(api, data=data, timeout=15)
        if r.status_code == 200:
            result = r.json()
            if result.get("data") and result["data"].get("play"):
                return result["data"]["play"]
    except Exception as e:
        logger.warning(f"TikTok API failed: {e}")
    return None

def download_via_instagram_api(url):
    """تحميل انستغرام عبر API بديل"""
    try:
        api_url = f"https://api.saveig.app/api/convert"
        payload = {"url": url}
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        r = requests.post(api_url, data=payload, headers=headers, timeout=15)
        if r.status_code == 200:
            data = r.json()
            if data and isinstance(data, list) and len(data) > 0:
                return data[0].get("url")
    except Exception as e:
        logger.warning(f"Instagram API failed: {e}")
    return None

def download_via_facebook_api(url):
    """تحميل فيسبوك عبر API بديل"""
    try:
        api_url = "https://getmyfb.com/process"
        payload = {"id": url, "locale": "en"}
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        r = requests.post(api_url, data=payload, headers=headers, timeout=15)
        if r.status_code == 200:
            text = r.text
            import re as regex
            match = regex.search(r'href="(https://[^"]*\.mp4[^"]*)"', text)
            if match:
                return match.group(1)
    except Exception as e:
        logger.warning(f"Facebook API failed: {e}")
    return None

def download_via_pinterest_api(url):
    """تحميل بنترست عبر عدة طرق"""
    # الطريقة 1: استخراج الفيديو من صفحة بنترست مباشرة
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        }
        r = requests.get(url, headers=headers, timeout=15, allow_redirects=True)
        if r.status_code == 200:
            text = r.text
            import re as regex
            # البحث عن رابط الفيديو في الصفحة
            patterns = [
                r'"contentUrl"\s*:\s*"(https://[^"]+\.mp4[^"]*)"',
                r'"video_url"\s*:\s*"(https://[^"]+)"',
                r'"url"\s*:\s*"(https://v1\.pinimg\.com/videos/[^"]+)"',
                r'"url"\s*:\s*"(https://[^"]*pinimg[^"]*\.mp4[^"]*)"',
                r'(https://v1\.pinimg\.com/videos/[^"\s]+\.mp4)',
                r'(https://[^"\s]*pinimg\.com[^"\s]*\.mp4[^"\s]*)',
            ]
            for pattern in patterns:
                match = regex.search(pattern, text)
                if match:
                    video_url = match.group(1)
                    video_url = video_url.replace('\\u002F', '/').replace('\\/', '/')
                    return video_url
    except Exception as e:
        logger.warning(f"Pinterest direct failed: {e}")

    # الطريقة 2: Pinterest API غير رسمي
    try:
        import re as regex
        pin_id = None
        match = regex.search(r'/pin/(\d+)', url)
        if match:
            pin_id = match.group(1)
        if not pin_id:
            expanded = expand_short_url(url)
            match = regex.search(r'/pin/(\d+)', expanded)
            if match:
                pin_id = match.group(1)
        if pin_id:
            api_url = f"https://api.pinterest.com/v3/pidgets/pins/info/?pin_ids={pin_id}"
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            r = requests.get(api_url, headers=headers, timeout=15)
            if r.status_code == 200:
                data = r.json()
                pin_data = data.get('data', [{}])[0] if data.get('data') else {}
                videos = pin_data.get('videos', {}).get('video_list', {})
                for quality in ['V_720P', 'V_480P', 'V_360P', 'V_EXP7', 'V_EXP6']:
                    if quality in videos and videos[quality].get('url'):
                        return videos[quality]['url']
    except Exception as e:
        logger.warning(f"Pinterest API failed: {e}")

    return None

def download_via_snapchat_api(url):
    """تحميل سناب شات"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        }
        r = requests.get(url, headers=headers, timeout=15, allow_redirects=True)
        if r.status_code == 200:
            text = r.text
            import re as regex
            patterns = [
                r'"contentUrl"\s*:\s*"(https://[^"]+)"',
                r'"video"\s*:\s*\{[^}]*"url"\s*:\s*"(https://[^"]+)"',
                r'(https://cf-st\.sc-cdn\.net/[^"\s]+\.mp4[^"\s]*)',
                r'(https://[^"\s]*snapchat[^"\s]*\.mp4[^"\s]*)',
            ]
            for pattern in patterns:
                match = regex.search(pattern, text)
                if match:
                    return match.group(1)
    except Exception as e:
        logger.warning(f"Snapchat direct failed: {e}")
    return None

def download_via_likee_api(url):
    """تحميل لايك"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        }
        r = requests.get(url, headers=headers, timeout=15, allow_redirects=True)
        if r.status_code == 200:
            text = r.text
            import re as regex
            patterns = [
                r'"video_url"\s*:\s*"(https://[^"]+)"',
                r'"contentUrl"\s*:\s*"(https://[^"]+)"',
                r'(https://[^"\s]*video[^"\s]*likee[^"\s]*\.mp4[^"\s]*)',
            ]
            for pattern in patterns:
                match = regex.search(pattern, text)
                if match:
                    video_url = match.group(1)
                    video_url = video_url.replace('\\u002F', '/').replace('\\/', '/')
                    return video_url
    except Exception as e:
        logger.warning(f"Likee direct failed: {e}")
    return None

# ====== دوال مساعدة ======

def detect_platform(url):
    """كشف المنصة من الرابط"""
    url_lower = url.lower()
    if 'youtube.com' in url_lower or 'youtu.be' in url_lower or 'youtube.com/shorts' in url_lower:
        return 'youtube'
    elif 'tiktok.com' in url_lower or 'vm.tiktok.com' in url_lower or 'vt.tiktok.com' in url_lower:
        return 'tiktok'
    elif 'snapchat.com' in url_lower or 'snap' in url_lower:
        return 'snapchat'
    elif 'pinterest.com' in url_lower or 'pin.it' in url_lower:
        return 'pinterest'
    elif 'facebook.com' in url_lower or 'fb.watch' in url_lower or 'fb.com' in url_lower or 'fbcdn' in url_lower:
        return 'facebook'
    elif 'instagram.com' in url_lower or 'instagr.am' in url_lower:
        return 'instagram'
    elif 'likee.com' in url_lower or 'likee.video' in url_lower or 'l.likee.video' in url_lower:
        return 'likee'
    elif 'twitter.com' in url_lower or 'x.com' in url_lower or 't.co' in url_lower:
        return 'twitter'
    else:
        return 'other'

def expand_short_url(url):
    """توسيع الرابط المختصر"""
    try:
        response = requests.head(url, allow_redirects=True, timeout=10, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        return response.url
    except Exception:
        return url

def get_ydl_opts_for_platform(platform, temp_dir):
    """إعدادات yt-dlp مخصصة لكل منصة"""
    base_opts = {
        'outtmpl': os.path.join(temp_dir, 'video.%(ext)s'),
        'quiet': True,
        'no_warnings': True,
        'extract_flat': False,
        'no_check_certificate': True,
        'socket_timeout': 30,
        'retries': 3,
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
        }
    }

    if platform == 'youtube':
        base_opts['format'] = 'bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720][ext=mp4]/best[ext=mp4]/best'
        base_opts['merge_output_format'] = 'mp4'
    elif platform == 'tiktok':
        base_opts['format'] = 'best[ext=mp4]/best'
    elif platform == 'instagram':
        base_opts['format'] = 'best[ext=mp4]/best'
        base_opts['http_headers']['Cookie'] = ''
    elif platform == 'facebook':
        base_opts['format'] = 'best[ext=mp4]/best'
    elif platform == 'twitter':
        base_opts['format'] = 'best[ext=mp4]/best'
    elif platform == 'snapchat':
        base_opts['format'] = 'best[ext=mp4]/best'
    elif platform == 'likee':
        base_opts['format'] = 'best[ext=mp4]/best'
    elif platform == 'pinterest':
        base_opts['format'] = 'best[ext=mp4]/best'
    else:
        base_opts['format'] = 'best[ext=mp4]/best'

    return base_opts

def analyze_video_info(url, platform):
    """تحليل الفيديو والحصول على المعلومات"""
    info = {
        'title': 'غير معروف',
        'duration': 'غير معروف',
        'views': 'غير معروف',
        'likes': 'غير معروف',
        'uploader': 'غير معروف',
        'platform': platform,
        'success': False,
        'error': None,
        'original_url': url,
        'expanded_url': url
    }

    try:
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
            'no_check_certificate': True,
            'socket_timeout': 20,
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
            }
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            extracted_info = ydl.extract_info(url, download=False)

            if extracted_info:
                info['title'] = extracted_info.get('title', 'غير معروف') or 'غير معروف'
                if len(info['title']) > 100:
                    info['title'] = info['title'][:97] + "..."

                duration = extracted_info.get('duration', 0)
                if duration and duration > 0:
                    minutes = int(duration) // 60
                    seconds = int(duration) % 60
                    if minutes >= 60:
                        hours = minutes // 60
                        minutes = minutes % 60
                        info['duration'] = f"{hours}:{minutes:02d}:{seconds:02d}"
                    else:
                        info['duration'] = f"{minutes}:{seconds:02d}"

                views = extracted_info.get('view_count', 0)
                if views and views > 0:
                    if views >= 1000000:
                        info['views'] = f"{views/1000000:.1f}M"
                    elif views >= 1000:
                        info['views'] = f"{views/1000:.1f}K"
                    else:
                        info['views'] = str(views)

                likes = extracted_info.get('like_count', 0)
                if likes and likes > 0:
                    if likes >= 1000000:
                        info['likes'] = f"{likes/1000000:.1f}M"
                    elif likes >= 1000:
                        info['likes'] = f"{likes/1000:.1f}K"
                    else:
                        info['likes'] = str(likes)

                info['uploader'] = extracted_info.get('uploader', extracted_info.get('channel', 'غير معروف')) or 'غير معروف'
                if len(info['uploader']) > 50:
                    info['uploader'] = info['uploader'][:47] + "..."
                info['success'] = True

    except Exception as e:
        logger.warning(f"تحليل الفيديو فشل: {e}")
        info['error'] = str(e)[:100]
        # حتى لو فشل التحليل، نحاول التحميل
        info['success'] = True

    return info

def download_video_file(url, platform, temp_dir):
    """تحميل الفيديو بعدة طرق"""

    # الطريقة 1: APIs بديلة حسب المنصة
    api_url = None

    if platform == 'tiktok':
        api_url = download_via_tiktok_api(url)
    elif platform == 'instagram':
        api_url = download_via_instagram_api(url)
    elif platform == 'facebook':
        api_url = download_via_facebook_api(url)
    elif platform == 'pinterest':
        api_url = download_via_pinterest_api(url)
    elif platform == 'snapchat':
        api_url = download_via_snapchat_api(url)
    elif platform == 'likee':
        api_url = download_via_likee_api(url)

    # محاولة Cobalt API لجميع المنصات
    if not api_url:
        api_url = download_via_cobalt(url)

    # إذا حصلنا على رابط من API، نحمل الملف
    if api_url:
        try:
            video_path = os.path.join(temp_dir, 'video.mp4')
            r = requests.get(api_url, timeout=60, stream=True, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            })
            if r.status_code == 200:
                with open(video_path, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        f.write(chunk)
                if os.path.exists(video_path) and os.path.getsize(video_path) > 1000:
                    return video_path
        except Exception as e:
            logger.warning(f"API download failed: {e}")

    # الطريقة 2: yt-dlp
    try:
        ydl_opts = get_ydl_opts_for_platform(platform, temp_dir)

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.extract_info(url, download=True)

            # البحث عن الملف
            for file in os.listdir(temp_dir):
                if file.endswith(('.mp4', '.webm', '.mkv', '.flv', '.avi', '.mov')):
                    file_path = os.path.join(temp_dir, file)
                    if os.path.getsize(file_path) > 1000:
                        return file_path
    except Exception as e:
        logger.warning(f"yt-dlp download failed: {e}")

    # الطريقة 3: yt-dlp مع إعدادات بسيطة
    try:
        simple_opts = {
            'format': 'best',
            'outtmpl': os.path.join(temp_dir, 'video_simple.%(ext)s'),
            'quiet': True,
            'no_warnings': True,
            'no_check_certificate': True,
            'socket_timeout': 30,
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
            }
        }

        with yt_dlp.YoutubeDL(simple_opts) as ydl:
            ydl.extract_info(url, download=True)

            for file in os.listdir(temp_dir):
                if file.endswith(('.mp4', '.webm', '.mkv', '.flv', '.avi', '.mov')):
                    file_path = os.path.join(temp_dir, file)
                    if os.path.getsize(file_path) > 1000:
                        return file_path
    except Exception as e:
        logger.warning(f"yt-dlp simple download failed: {e}")

    return None

# ====== معالجات البوت ======

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """وظيفة البدء"""
    keyboard = []
    row = []
    for i, (key, platform) in enumerate(PLATFORMS.items()):
        row.append(InlineKeyboardButton(f"📥 {platform}", callback_data=f"platform_{key}"))
        if (i + 1) % 2 == 0:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)

    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "🚀 مرحبا! أنا بوت تحميل الفيديوهات\n\n"
        "📌 المنصات المدعومة:\n"
        "• يوتيوب • تيك توك\n"
        "• سناب شات • بنترست\n"
        "• فيسبوك • انستغرام\n"
        "• لايك • تويتر\n\n"
        "🎯 اختر المنصة أو أرسل الرابط مباشرة:",
        reply_markup=reply_markup
    )

async def platform_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة اختيار المنصة"""
    query = update.callback_query
    await query.answer()

    data = query.data

    if data == "help_btn":
        await help_command_callback(query, context)
        return

    if not data.startswith("platform_"):
        return

    platform = data.replace("platform_", "")
    context.user_data['selected_platform'] = platform

    platform_name = PLATFORMS.get(platform, platform)

    await query.edit_message_text(
        f"✅ تم اختيار {platform_name}\n\n"
        f"📤 الآن أرسل رابط الفيديو\n"
        f"وسأقوم بتحميله لك فورا.\n\n"
        f"📝 يمكنك إرسال أي نوع من الروابط:\n"
        f"• روابط قصيرة\n"
        f"• روابط طويلة\n"
        f"• روابط من أي منصة"
    )

async def download_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تحميل الفيديو"""
    url = update.message.text.strip()

    # التحقق من صحة الرابط
    if not re.match(r'https?://\S+', url):
        await update.message.reply_text(
            "❌ الرابط غير صالح.\n"
            "الرجاء إرسال رابط صحيح يبدأ بـ http:// أو https://"
        )
        return

    status_msg = await update.message.reply_text(
        "⏳ جاري معالجة الرابط...\n"
        "🔍 يتم تحليل الفيديو..."
    )

    temp_dir = None
    try:
        # توسيع الرابط المختصر
        expanded_url = expand_short_url(url)

        # كشف المنصة
        platform = detect_platform(expanded_url)
        platform_name = PLATFORMS.get(platform, 'منصة أخرى')

        await status_msg.edit_text(
            f"⏳ جاري المعالجة...\n"
            f"📱 المنصة: {platform_name}\n"
            f"🔍 يتم تحليل الفيديو..."
        )

        # تحليل معلومات الفيديو
        video_info = analyze_video_info(expanded_url, platform)

        if video_info['success']:
            await status_msg.edit_text(
                f"📊 تم تحليل الفيديو!\n\n"
                f"📌 العنوان: {video_info['title']}\n"
                f"📱 المنصة: {platform_name}\n"
                f"⏱ المدة: {video_info['duration']}\n"
                f"👁 المشاهدات: {video_info['views']}\n"
                f"❤ الإعجابات: {video_info['likes']}\n"
                f"👤 الناشر: {video_info['uploader']}\n\n"
                f"⬇ جاري التحميل الآن...\n"
                f"⏳ قد يستغرق هذا بضع ثوان..."
            )

        # تحميل الفيديو
        temp_dir = tempfile.mkdtemp()
        video_path = download_video_file(expanded_url, platform, temp_dir)

        if not video_path:
            await status_msg.edit_text(
                f"❌ فشل تحميل الفيديو من {platform_name}\n\n"
                f"🔍 الأسباب المحتملة:\n"
                f"• الفيديو خاص أو محذوف\n"
                f"• الرابط غير صحيح\n"
                f"• المنصة تمنع التحميل\n\n"
                f"💡 جرب:\n"
                f"• تأكد إن الفيديو عام\n"
                f"• انسخ الرابط من جديد\n"
                f"• جرب رابط آخر"
            )
            return

        # التحقق من حجم الفيديو
        file_size = os.path.getsize(video_path)

        if file_size > 50 * 1024 * 1024:
            await status_msg.edit_text(
                f"⚠ حجم الفيديو كبير جدا ({file_size/(1024*1024):.1f}MB)\n"
                f"📌 الحد الأقصى في تيليجرام: 50MB\n\n"
                f"❌ لا يمكن إرسال الفيديو"
            )
            return

        # إرسال الفيديو
        await status_msg.edit_text("📤 جاري إرسال الفيديو...")

        with open(video_path, 'rb') as video_file:
            caption = (
                f"✅ تم التحميل من {platform_name}!\n\n"
                f"📌 {video_info['title']}\n"
                f"⏱ المدة: {video_info['duration']}\n"
                f"👁 المشاهدات: {video_info['views']}\n"
                f"❤ الإعجابات: {video_info['likes']}\n"
                f"👤 {video_info['uploader']}"
            )
            # تقليص الكابشن إذا كان طويل
            if len(caption) > 1024:
                caption = caption[:1020] + "..."

            await update.message.reply_video(
                video=video_file,
                caption=caption,
                supports_streaming=True,
                read_timeout=120,
                write_timeout=120
            )

        await status_msg.edit_text(
            f"🎉 تم بنجاح!\n"
            f"✅ تم تحميل الفيديو من {platform_name}\n"
            f"📥 أرسل رابط آخر للتحميل"
        )

    except Exception as e:
        logger.error(f"خطأ غير متوقع: {e}")
        try:
            await status_msg.edit_text(
                f"❌ حدث خطأ أثناء التحميل\n"
                f"💡 جرب مرة ثانية أو أرسل رابط آخر"
            )
        except Exception:
            pass
    finally:
        if temp_dir and os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """وظيفة المساعدة"""
    await update.message.reply_text(
        "📚 أوامر البوت:\n\n"
        "▶ /start - بدء استخدام البوت\n"
        "❓ /help - عرض المساعدة\n\n"
        "🔧 طريقة الاستخدام:\n"
        "1. أرسل رابط الفيديو مباشرة\n"
        "2. أو اضغط /start واختر المنصة\n"
        "3. انتظر حتى ينتهي التحميل\n\n"
        "📌 المنصات المدعومة:\n"
        "• يوتيوب (فيديوهات + شورتس)\n"
        "• تيك توك (بدون علامة مائية)\n"
        "• سناب شات\n"
        "• بنترست\n"
        "• فيسبوك\n"
        "• انستغرام (ريلز + فيديوهات)\n"
        "• لايك\n"
        "• تويتر / X\n\n"
        "💡 ملاحظات:\n"
        "• يدعم الروابط القصيرة والطويلة\n"
        "• الحد الأقصى: 50MB\n"
        "• بعض الفيديوهات الخاصة لا يمكن تحميلها"
    )

async def help_command_callback(query, context):
    """المساعدة من الأزرار"""
    await query.edit_message_text(
        "📚 المساعدة السريعة:\n\n"
        "📥 لتحميل فيديو:\n"
        "1. أرسل رابط الفيديو مباشرة\n"
        "2. انتظر التحميل\n\n"
        "🔗 أنواع الروابط المدعومة:\n"
        "• روابط قصيرة\n"
        "• روابط طويلة\n"
        "• روابط من أي موقع\n\n"
        "⚠ الحد الأقصى للحجم: 50MB"
    )

# تشغيل البوت
def main():
    if TOKEN == "ضع_توكن_البوت_هنا":
        print("❌ خطأ: لم تقم بوضع توكن البوت!")
        return

    application = Application.builder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CallbackQueryHandler(platform_selection))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, download_video))

    print("=" * 50)
    print("🤖 بوت تحميل الفيديوهات يعمل الآن!")
    print("📱 يدعم: يوتيوب، تيك توك، فيسبوك،")
    print("   انستغرام، سناب شات، لايك، تويتر، بنترست")
    print("🎯 أرسل /start في تيليجرام")
    print("=" * 50)

    try:
        application.run_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True
        )
    except Exception as e:
        print(f"❌ خطأ في تشغيل البوت: {e}")

if __name__ == '__main__':
    main()
