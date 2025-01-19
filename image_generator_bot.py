import os
import logging
import sys
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
import requests
import urllib.parse
from datetime import datetime, timedelta
from collections import defaultdict
import base64
from pytube import YouTube
import re
from replicate.client import Client
import replicate
import json
from typing import Optional, Dict, Any, List
import speedtest
from requests_toolbelt.multipart.encoder import MultipartEncoder

# Enable logging with file output
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('bot.log')
    ]
)

logger = logging.getLogger(__name__)

# Get the tokens from environment variables
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
REPLICATE_API_TOKEN = os.getenv("REPLICATE_API_TOKEN")
AUDD_API_TOKEN = os.getenv("AUDD_API_TOKEN")
TMDB_API_KEY = os.getenv("TMDB_API_KEY")

# Check all required tokens
required_tokens = {
    "TELEGRAM_TOKEN": TELEGRAM_TOKEN,
    "REPLICATE_API_TOKEN": REPLICATE_API_TOKEN,
    "AUDD_API_TOKEN": AUDD_API_TOKEN,
    "TMDB_API_KEY": TMDB_API_KEY
}

missing_tokens = [name for name, token in required_tokens.items() if not token]
if missing_tokens:
    raise ValueError(f"Missing required environment variables: {', '.join(missing_tokens)}")

# Rate limiting
USER_RATES: Dict[int, list] = defaultdict(list)
MAX_REQUESTS_PER_MINUTE = 3
MAX_PROMPT_LENGTH = 200

# API URLs
MUSIC_API_BASE = "https://jiosaavn-api-codyandersan.vercel.app/search/all"
WHOIS_API_BASE = "https://rdap.org/domain/"
AUDD_API_URL = "https://api.audd.io/"
TMDB_API_BASE = "https://api.themoviedb.org/3"
GEMINI_API_BASE = "http://www.lastroom.ct.ws/gemini-pro"

# Film türleri
MOVIE_GENRES = {
    "aksiyon": 28,
    "macera": 12,
    "animasyon": 16,
    "komedi": 35,
    "suç": 80,
    "belgesel": 99,
    "dram": 18,
    "aile": 10751,
    "fantastik": 14,
    "tarih": 36,
    "korku": 27,
    "müzik": 10402,
    "gizem": 9648,
    "romantik": 10749,
    "bilim kurgu": 878,
    "gerilim": 53,
    "savaş": 10752,
    "western": 37
}

# YouTube video info cache
youtube_cache: Dict[str, Dict[str, Any]] = {}

# User limits tracking
UPSCALE_DAILY_LIMIT = 3
FLUX_DAILY_LIMIT = 3
user_upscale_counts: Dict[int, Dict[str, int]] = defaultdict(lambda: {"count": 0, "reset_date": ""})
user_flux_counts: Dict[int, Dict[str, int]] = defaultdict(lambda: {"count": 0, "reset_date": ""})

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a message when the command /start is issued."""
    try:
        user_name = update.message.from_user.first_name
        await update.message.reply_text(
            f'Merhaba {user_name}! 👋\n\n'
            f'🎨 Resim Komutları:\n'
            f'1. DALL-E 3 ile resim: /dalle [açıklama]\n'
            f'2. Flux ile resim: /flux [açıklama]\n'
            f'3. Resim iyileştirme: /upscale (resmi yanıtlayarak)\n\n'
            f'🎬 Film Komutları:\n'
            f'1. Film türüne göre öneriler: /genre [tür]\n'
            f'2. Benzer film önerileri: /similar [film adı]\n\n'
            f'🎵 Müzik Komutları:\n'
            f'1. Şarkı aramak için: /song [şarkı adı]\n'
            f'2. Müzik tanımak için: Ses kaydı veya müzik dosyası gönderin\n\n'
            f'📥 İndirme Komutları:\n'
            f'1. YouTube indirmek için: /yt [video linki]\n\n'
            f'🤖 AI Sohbet:\n'
            f'1. Gemini Pro ile sohbet: /chat [mesaj]\n\n'
            f'🛠️ Diğer Komutlar:\n'
            f'1. Domain sorgulamak için: /whois [domain.com]\n'
            f'2. İnternet hız testi: /speedtest\n\n'
            f'📝 Örnekler:\n'
            f'• /dalle bir adam denizde yüzüyor 🎨\n'
            f'• /genre korku 🎬\n'
            f'• /similar Matrix 🎬\n'
            f'• /song Hadise Aşk Kaç Beden Giyer 🎵\n'
            f'• /chat Yapay zeka nedir? 🤖\n'
            f'• /whois google.com 🔍\n'
            f'• /yt https://youtube.com/watch?v=... ��\n\n'
            f'⚠️ Limitler:\n'
            f'• Dakikada {MAX_REQUESTS_PER_MINUTE} resim oluşturabilirsiniz\n'
            f'• Günlük {FLUX_DAILY_LIMIT} Flux resim hakkı\n'
            f'• Günlük {UPSCALE_DAILY_LIMIT} resim iyileştirme hakkı\n'
            f'• Maksimum {MAX_PROMPT_LENGTH} karakter uzunluğunda açıklama'
        )
    except Exception as e:
        logger.error(f"Start command error: {str(e)}")
        await update.message.reply_text("Bir hata oluştu. Lütfen tekrar deneyin.")

def extract_video_id(url):
    """Extract video ID from various YouTube URL formats."""
    try:
        # Clean the URL first
        url = url.strip().lstrip('@')  # Remove @ symbol if present
        
        # Parse the URL
        parsed_url = urllib.parse.urlparse(url)
        
        # Handle youtu.be links
        if 'youtu.be' in parsed_url.netloc:
            return parsed_url.path.strip('/')
        
        # Handle youtube.com links
        if 'youtube.com' in parsed_url.netloc:
            # Parse query parameters
            query_params = urllib.parse.parse_qs(parsed_url.query)
            
            # Get video ID from v parameter
            if 'v' in query_params:
                return query_params['v'][0]
            
            # Handle /embed/ and /shorts/ URLs
            path = parsed_url.path
            if '/embed/' in path or '/shorts/' in path:
                return path.split('/')[-1]
    
    except Exception as e:
        logger.error(f"URL parsing error: {str(e)}")
    
    return None

async def youtube_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle YouTube download command."""
    try:
        # Check if URL is provided
        if not context.args:
            await update.message.reply_text(
                "Lütfen bir YouTube linki girin.\n"
                "Örnek: /yt https://youtube.com/watch?v=..."
            )
            return
        
        # Get the URL
        url = context.args[0].strip()
        logger.info(f"Processing YouTube URL: {url}")  # Debug log
        
        # Extract video ID
        video_id = extract_video_id(url)
        logger.info(f"Extracted video ID: {video_id}")  # Debug log
        
        if not video_id:
            await update.message.reply_text(
                "❌ Geçersiz YouTube linki.\n"
                f"Girilen link: {url}\n"
                "Desteklenen formatlar:\n"
                "- https://youtube.com/watch?v=VIDEO_ID\n"
                "- https://youtu.be/VIDEO_ID\n"
                "- https://youtube.com/shorts/VIDEO_ID"
            )
            return
        
        # Send processing message
        processing_message = await update.message.reply_text(
            "🔍 Video bilgileri alınıyor..."
        )
        
        try:
            # Get video info from YouTube
            video_url = f"https://www.youtube.com/watch?v={video_id}"
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            response = requests.get(video_url, headers=headers, timeout=10)
            
            if response.status_code != 200:
                raise Exception("Video bilgilerine erişilemedi")
            
            # Extract video title using regex
            title_match = re.search(r'<title>(.*?) - YouTube</title>', response.text)
            if not title_match:
                raise Exception("Video başlığı alınamadı")
            
            title = title_match.group(1)
            
            # Extract channel name
            channel_match = re.search(r'"author":"([^"]+)"', response.text)
            author = channel_match.group(1) if channel_match else "Bilinmeyen Kanal"
            
            # Get video thumbnail
            thumbnail = f"https://i.ytimg.com/vi/{video_id}/maxresdefault.jpg"
            
            # Cache video info
            youtube_cache[video_id] = {
                'url': video_url,
                'title': title,
                'author': author,
                'thumbnail': thumbnail
            }
            
            # Create format selection buttons
            keyboard = [
                [
                    InlineKeyboardButton("🎵 MP3 (320kbps)", callback_data=f"yt_audio_{video_id}"),
                    InlineKeyboardButton("🎥 720p MP4", callback_data=f"yt_720_{video_id}")
                ],
                [
                    InlineKeyboardButton("🎥 1080p MP4", callback_data=f"yt_1080_{video_id}"),
                    InlineKeyboardButton("🎥 360p MP4", callback_data=f"yt_360_{video_id}")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            # Send video info with format selection
            await update.message.reply_photo(
                photo=thumbnail,
                caption=(
                    f"📹 Video Bilgileri:\n\n"
                    f"📝 Başlık: {title}\n"
                    f"👤 Kanal: {author}\n\n"
                    f"Lütfen indirme formatını seçin:"
                ),
                reply_markup=reply_markup
            )
            
        except Exception as e:
            logger.error(f"YouTube info error: {str(e)}")
            error_message = str(e)
            if "Video unavailable" in error_message:
                error_message = "Video kullanılamıyor veya özel"
            elif "bilgilerine erişilemedi" in error_message:
                error_message = "Video bilgilerine erişilemedi. Lütfen daha sonra tekrar deneyin"
            
            await update.message.reply_text(
                f"❌ {error_message}.\n"
                "Lütfen başka bir video deneyin veya daha sonra tekrar deneyin."
            )
        
        finally:
            await processing_message.delete()
            
    except Exception as e:
        logger.error(f"YouTube command error: {str(e)}")
        await update.message.reply_text("Bir hata oluştu. Lütfen tekrar deneyin.")

async def youtube_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle YouTube format selection buttons."""
    query = update.callback_query
    await query.answer()
    
    try:
        # Parse callback data
        action, format_type, video_id = query.data.split('_')
        video_info = youtube_cache.get(video_id)
        
        if not video_info:
            await query.message.reply_text(
                "❌ Video bilgileri zaman aşımına uğradı.\n"
                "Lütfen /yt komutunu tekrar kullanın."
            )
            return
        
        # Get video title
        title = video_info['title']
        
        # Create y2mate link based on format
        if format_type == 'audio':
            y2mate_url = f"https://www.y2mate.com/tr/youtube-mp3/{video_id}"
            format_text = "MP3"
        else:
            y2mate_url = f"https://www.y2mate.com/tr/youtube/{video_id}"
            format_text = f"{format_type}p MP4"
        
        # Create message with instructions
        message = (
            f"📥 {format_text} İndirme Linki:\n\n"
            f"🔗 {y2mate_url}\n\n"
            f"📝 Video: {title}\n\n"
            "📱 Nasıl İndirilir:\n"
            "1. Yukarıdaki linke tıklayın\n"
            "2. Açılan sayfada 'Convert' butonuna tıklayın\n"
            "3. 'Download' butonuna tıklayarak indirin\n\n"
            "⚠️ Not: Reklam engelleyici kullanmanız önerilir"
        )
        
        await query.message.reply_text(message)
            
    except Exception as e:
        logger.error(f"YouTube button error: {str(e)}")
        await query.message.reply_text("Bir hata oluştu. Lütfen tekrar deneyin.")

async def search_song(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Search for a song and return its details."""
    try:
        # Check if user provided text
        if not context.args:
            await update.message.reply_text(
                "Lütfen bir şarkı adı girin.\n"
                "Örnek: /song Hadise Aşk Kaç Beden Giyer"
            )
            return
        
        # Get the search query
        query = ' '.join(context.args)
        
        # Send a "searching" message
        processing_message = await update.message.reply_text(
            "🔍 Şarkı aranıyor..."
        )
        
        try:
            # Make request to the music API
            params = {
                'query': query,
                'page': 1,
                'limit': 5
            }
            response = requests.get(MUSIC_API_BASE, params=params, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                if data.get("status") == "SUCCESS":
                    songs = data.get("data", {}).get("songs", {}).get("results", [])
                    albums = data.get("data", {}).get("albums", {}).get("results", [])
                    
                    if not songs and not albums:
                        await update.message.reply_text(
                            "❌ Üzgünüm, aradığınız şarkı bulunamadı."
                        )
                        return
                    
                    # Create response message
                    message = "🎵 Arama Sonuçları:\n\n"
                    
                    # Add songs
                    if songs:
                        message += "📀 Şarkılar:\n"
                        for i, song in enumerate(songs[:3], 1):
                            message += f"{i}. {song['title']}\n"
                            message += f"   🎤 Sanatçı: {song['primaryArtists']}\n"
                            message += f"   💿 Albüm: {song['album']}\n"
                            message += f"   🔗 Link: {song['url']}\n\n"
                    
                    # Add albums if any
                    if albums:
                        message += "\n💽 Albümler:\n"
                        for i, album in enumerate(albums[:2], 1):
                            message += f"{i}. {album['title']}\n"
                            message += f"   👤 Sanatçı: {album['artist']}\n"
                            message += f"   📅 Yıl: {album.get('year', 'N/A')}\n"
                            message += f"   🔗 Link: {album['url']}\n\n"
                    
                    # Send the message with the first song's image if available
                    if songs and songs[0].get('image'):
                        image_url = songs[0]['image'][-1]['link']  # Get highest quality image
                        await update.message.reply_photo(
                            photo=image_url,
                            caption=message
                        )
                    else:
                        await update.message.reply_text(message)
                    
                else:
                    await update.message.reply_text(
                        "❌ Arama sonuçları alınırken bir hata oluştu."
                    )
            else:
                await update.message.reply_text(
                    "❌ Müzik API'sine erişilemiyor. Lütfen daha sonra tekrar deneyin."
                )
                
        except requests.Timeout:
            await update.message.reply_text(
                "⏰ API yanıt vermedi, lütfen tekrar deneyin."
            )
        except requests.RequestException as e:
            logger.error(f"Music API request error: {str(e)}")
            await update.message.reply_text(
                "🔌 Bağlantı hatası oluştu, lütfen tekrar deneyin."
            )
        except Exception as e:
            logger.error(f"Song search error: {str(e)}")
            await update.message.reply_text(
                "⚠️ Beklenmeyen bir hata oluştu, lütfen tekrar deneyin."
            )
        
        finally:
            # Delete the processing message
            await processing_message.delete()
            
    except Exception as e:
        logger.error(f"Song command error: {str(e)}")
        await update.message.reply_text("Bir hata oluştu. Lütfen tekrar deneyin.")

def check_rate_limit(user_id: int) -> bool:
    """Check if user has exceeded rate limit."""
    now = datetime.now()
    user_requests = USER_RATES[user_id]
    
    # Remove requests older than 1 minute
    user_requests = [req for req in user_requests if now - req < timedelta(minutes=1)]
    USER_RATES[user_id] = user_requests
    
    # Check if user has exceeded limit
    if len(user_requests) >= MAX_REQUESTS_PER_MINUTE:
        return False
    
    # Add new request
    user_requests.append(now)
    return True

async def generate_dalle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generate an image using DALL-E 3."""
    try:
        # Check if user provided text
        if not context.args:
            await update.message.reply_text(
                "Lütfen bir açıklama girin.\n"
                "Örnek: /dalle bir adam denizde yüzüyor"
            )
            return
        
        # Get user ID for rate limiting
        user_id = update.effective_user.id
        
        # Check rate limit
        if not check_rate_limit(user_id):
            remaining_time = 60 - (datetime.now() - USER_RATES[user_id][0]).seconds
            await update.message.reply_text(
                f"Çok fazla istek gönderdiniz. Lütfen {remaining_time} saniye bekleyin."
            )
            return
        
        # Get the text after the command
        user_text = ' '.join(context.args)
        
        # Check prompt length
        if len(user_text) > MAX_PROMPT_LENGTH:
            await update.message.reply_text(
                f"Açıklama çok uzun! Maksimum {MAX_PROMPT_LENGTH} karakter girebilirsiniz."
            )
            return
        
        # Send a "processing" message
        processing_message = await update.message.reply_text(
            "🎨 DALL-E 3 ile resim oluşturuluyor..."
        )
        
        try:
            # Encode the user's text for the URL
            encoded_text = urllib.parse.quote(user_text)
            
            # Make request to the DALL-E 3 API
            api_url = f"https://prompt.glitchy.workers.dev/gen?key={encoded_text}&t=0.2&f=dalle3&demo=true&count=1&nsfw=true"
            response = requests.get(api_url, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                if data.get("status") == 1 and "images" in data:
                    # Get the image URL from the response
                    image_url = data["images"][0]["imagedemo1"][0]
                    
                    # Send the image
                    await update.message.reply_photo(
                        photo=image_url,
                        caption=(
                            f"🎨 İşte DALL-E 3 ile oluşturduğum resim!\n\n"
                            f"📝 Prompt: {user_text}"
                        )
                    )
                else:
                    raise Exception("API yanıtı geçersiz")
            else:
                raise Exception(f"HTTP {response.status_code}")
                
        except Exception as e:
            logger.error(f"DALL-E generation error: {str(e)}")
            await update.message.reply_text(
                "❌ Resim oluşturulurken bir hata oluştu.\n"
                "Lütfen daha sonra tekrar deneyin."
            )
        
        finally:
            await processing_message.delete()
            
    except Exception as e:
        logger.error(f"DALL-E command error: {str(e)}")
        await update.message.reply_text("Bir hata oluştu. Lütfen tekrar deneyin.")

async def generate_flux(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Generate an image using Flux model with daily limits."""
    try:
        user_id = update.effective_user.id
        today = datetime.now().strftime("%Y-%m-%d")
        
        # Reset count if it's a new day
        if user_flux_counts[user_id]["reset_date"] != today:
            user_flux_counts[user_id] = {"count": 0, "reset_date": today}
            
        # Check if user has reached daily limit
        if user_flux_counts[user_id]["count"] >= FLUX_DAILY_LIMIT:
            remaining_time = datetime.now().replace(hour=0, minute=0, second=0) + timedelta(days=1)
            hours_left = int((remaining_time - datetime.now()).total_seconds() / 3600)
            await update.message.reply_text(
                f"⚠️ Günlük Flux resim limitinize ulaştınız (3/3)\n"
                f"🕒 Limitiniz {hours_left} saat sonra yenilenecek."
            )
            return

        # Get the prompt from message
        if not context.args:
            await update.message.reply_text("❌ Lütfen bir açıklama girin.\nÖrnek: /flux bir kedi ağaca tırmanıyor")
            return

        prompt = " ".join(context.args)
        
        if len(prompt) > MAX_PROMPT_LENGTH:
            await update.message.reply_text(f"❌ Açıklama çok uzun! Maksimum {MAX_PROMPT_LENGTH} karakter girebilirsiniz.")
            return

        # Send processing message
        processing_msg = await update.message.reply_text("🔄 Model: SDXL LCM\n⏳ Resim oluşturuluyor...")

        # Initialize Replicate client
        replicate = Client(api_token=os.getenv("REPLICATE_API_TOKEN"))
        
        # Generate image
        output = replicate.run(
            "lucataco/sdxl-lcm:fbbd475b1084de80c47c35bfe4ae64b964294aa7e237e6537eed938cfd24903d",
            input={
                "prompt": prompt,
                "width": 1024,
                "height": 1024,
                "num_inference_steps": 4,
                "guidance_scale": 1.5,
                "num_outputs": 1,
                "seed": 42
            }
        )

        if output and isinstance(output, list) and len(output) > 0:
            image_url = output[0]
            
            # Send the generated image
            await context.bot.send_photo(
                chat_id=update.effective_chat.id,
                photo=image_url,
                caption=f"🎨 Prompt: {prompt}"
            )
            
            # Update user count
            user_flux_counts[user_id]["count"] += 1
            remaining = FLUX_DAILY_LIMIT - user_flux_counts[user_id]["count"]
            
            await update.message.reply_text(
                f"ℹ️ Günlük kalan Flux resim hakkınız: {remaining}/3"
            )
        else:
            await update.message.reply_text("❌ Resim oluşturulamadı. Lütfen tekrar deneyin.")

        # Delete processing message
        await processing_msg.delete()

    except Exception as e:
        logger.error(f"Flux generation error: {str(e)}")
        await update.message.reply_text("❌ Bir hata oluştu. Lütfen tekrar deneyin.")

async def whois_lookup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Look up WHOIS information for a domain."""
    try:
        # Check if user provided a domain
        if not context.args:
            await update.message.reply_text(
                "Lütfen bir domain adı girin.\n"
                "Örnek: /whois google.com"
            )
            return
        
        # Get the domain
        domain = context.args[0].lower()
        
        # Basic domain validation
        if not '.' in domain or len(domain) < 4:
            await update.message.reply_text(
                "❌ Geçersiz domain formatı.\n"
                "Örnek format: domain.com"
            )
            return
        
        # Send a "searching" message
        processing_message = await update.message.reply_text(
            f"🔍 {domain} domain'i sorgulanıyor..."
        )
        
        try:
            # Make request to the RDAP API
            api_url = f"{WHOIS_API_BASE}{domain}"
            headers = {
                'Accept': 'application/rdap+json'
            }
            response = requests.get(api_url, headers=headers, timeout=30)
            
            if response.status_code == 200:
                try:
                    data = response.json()
                    
                    # Format the response
                    message = f"🌐 Domain Bilgileri: {domain}\n\n"
                    
                    # Domain Status
                    if data.get("status"):
                        statuses = {
                            "active": "✅ Aktif",
                            "client delete prohibited": "🔒 Silme Korumalı",
                            "client transfer prohibited": "🔒 Transfer Korumalı",
                            "client update prohibited": "🔒 Güncelleme Korumalı",
                            "server delete prohibited": "🔒 Sunucu Silme Korumalı",
                            "server transfer prohibited": "🔒 Sunucu Transfer Korumalı",
                            "server update prohibited": "🔒 Sunucu Güncelleme Korumalı",
                            "associated": "✅ İlişkili",
                            "reserved": "⚠️ Rezerve Edilmiş"
                        }
                        status_list = [statuses.get(s.lower(), s) for s in data["status"]]
                        message += f"📊 Durum: {', '.join(status_list)}\n"
                    
                    # Events (dates)
                    if data.get("events"):
                        for event in data["events"]:
                            if event.get("eventAction") == "registration":
                                message += f"📅 Kayıt Tarihi: {event['eventDate']}\n"
                            elif event.get("eventAction") == "expiration":
                                message += f"⌛ Bitiş Tarihi: {event['eventDate']}\n"
                            elif event.get("eventAction") == "last changed":
                                message += f"🔄 Son Güncelleme: {event['eventDate']}\n"
                    
                    # Name Servers
                    if data.get("nameservers"):
                        ns_list = [ns.get("ldhName", "") for ns in data["nameservers"]]
                        message += f"\n🖥️ Name Serverlar:\n"
                        for ns in ns_list[:3]:  # İlk 3 name server
                            message += f"  • {ns}\n"
                    
                    # Registrar info
                    if data.get("entities"):
                        for entity in data["entities"]:
                            if entity.get("roles"):
                                if "registrar" in entity["roles"]:
                                    if entity.get("vcardArray") and len(entity["vcardArray"]) > 1:
                                        for item in entity["vcardArray"][1]:
                                            if item[0] == "fn":
                                                message += f"\n🏢 Kayıt Şirketi: {item[3]}\n"
                                elif "registrant" in entity["roles"]:
                                    if entity.get("vcardArray") and len(entity["vcardArray"]) > 1:
                                        for item in entity["vcardArray"][1]:
                                            if item[0] == "org":
                                                message += f"👤 Domain Sahibi: {item[3]}\n"
                    
                    # Port43 (WHOIS server)
                    if data.get("port43"):
                        message += f"\n🔍 WHOIS Sunucusu: {data['port43']}\n"
                    
                    # Send the formatted message
                    await update.message.reply_text(message)
                    
                except ValueError as ve:
                    logger.error(f"JSON parsing error: {str(ve)}")
                    await update.message.reply_text(
                        "❌ API yanıtı geçersiz format içeriyor.\n"
                        "Lütfen tekrar deneyin."
                    )
                
            elif response.status_code == 404:
                await update.message.reply_text(
                    f"❌ Domain bulunamadı: {domain}\n"
                    "Domain kayıtlı değil veya yanlış yazılmış olabilir."
                )
            else:
                await update.message.reply_text(
                    f"❌ Domain bilgileri alınamadı (HTTP {response.status_code}).\n"
                    "Lütfen geçerli bir domain adı girin."
                )
                
        except requests.Timeout:
            await update.message.reply_text(
                "⏰ API yanıt vermedi, lütfen tekrar deneyin."
            )
        except requests.RequestException as e:
            logger.error(f"WHOIS API request error: {str(e)}")
            await update.message.reply_text(
                "🔌 Bağlantı hatası oluştu, lütfen tekrar deneyin."
            )
        except Exception as e:
            logger.error(f"WHOIS lookup error: {str(e)}")
            await update.message.reply_text(
                "⚠️ Beklenmeyen bir hata oluştu, lütfen tekrar deneyin."
            )
        
        finally:
            # Delete the processing message
            await processing_message.delete()
            
    except Exception as e:
        logger.error(f"WHOIS command error: {str(e)}")
        await update.message.reply_text("Bir hata oluştu. Lütfen tekrar deneyin.")

async def recognize_music(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Recognize music from voice message or audio file using Audd.io API."""
    try:
        # Get the file
        if update.message.voice:
            file = await update.message.voice.get_file()
        elif update.message.audio:
            file = await update.message.audio.get_file()
        else:
            return
        
        # Send processing message
        processing_message = await update.message.reply_text(
            "🎵 Müzik tanınıyor, lütfen bekleyin..."
        )
        
        try:
            # Download the file
            file_bytes = await file.download_as_bytearray()
            # Convert bytearray to bytes
            file_data = bytes(file_bytes)
            
            # Convert to base64
            encoded_file = base64.b64encode(file_data).decode('utf-8')
            
            # Prepare the request for Audd.io API
            url = "https://api.audd.io/recognize"
            
            payload = {
                "audio": encoded_file,
                "api_token": AUDD_API_TOKEN,
                "return": "apple_music,spotify"
            }
            
            headers = {
                'content-type': 'application/json'
            }
            
            # Make request to Audd.io API
            response = requests.post(url, json=payload, headers=headers, timeout=30)
            logger.info(f"Audd.io API Response Status: {response.status_code}")
            logger.info(f"Audd.io API Response: {response.text}")
            #a
            if response.status_code == 200:
                data = response.json()
                
                if data.get("status") == "success" and data.get("result"):
                    result = data["result"]
                    
                    # Create response message
                    message = "🎵 Müzik Bulundu!\n\n"
                    message += f"🎤 Sanatçı: {result.get('artist', 'Bilinmiyor')}\n"
                    message += f"🎼 Şarkı: {result.get('title', 'Bilinmiyor')}\n"
                    message += f"💿 Albüm: {result.get('album', 'Bilinmiyor')}\n"
                    
                    # Add release date if available
                    if result.get("release_date"):
                        message += f"📅 Yayın Tarihi: {result['release_date']}\n"
                    
                    # Add streaming links if available
                    message += "\n🎧 Dinleme Linkleri:\n"
                    if result.get("spotify"):
                        spotify = result["spotify"]
                        message += f"Spotify: {spotify.get('external_urls', {}).get('spotify', 'Bulunamadı')}\n"
                    if result.get("apple_music"):
                        apple = result["apple_music"]
                        message += f"Apple Music: {apple.get('url', 'Bulunamadı')}\n"
                    
                    # Add album art if available
                    if result.get("spotify", {}).get("album", {}).get("images"):
                        image_url = result["spotify"]["album"]["images"][0]["url"]
                        await update.message.reply_photo(
                            photo=image_url,
                            caption=message
                        )
                    else:
                        await update.message.reply_text(message)
                    
                else:
                    await update.message.reply_text(
                        "❌ Üzgünüm, bu müziği tanıyamadım.\n"
                        "Lütfen daha net bir kayıt göndermeyi deneyin.\n"
                        "İpuçları:\n"
                        "- En az 10 saniye uzunluğunda olmalı\n"
                        "- Arka planda gürültü olmamalı\n"
                        "- Ses kalitesi iyi olmalı"
                    )
            else:
                error_message = "❌ Müzik tanıma servisi şu anda çalışmıyor."
                if response.status_code == 429:
                    error_message = "⚠️ Günlük API limitine ulaşıldı. Lütfen yarın tekrar deneyin."
                elif response.status_code == 401:
                    error_message = "⚠️ API anahtarı geçersiz. Lütfen yöneticinize bildirin."
                elif response.status_code == 403:
                    error_message = "⚠️ Bu API'ye abone olmanız gerekiyor. Lütfen yöneticinize bildirin."
                await update.message.reply_text(
                    f"{error_message}\n"
                    "Lütfen daha sonra tekrar deneyin."
                )
                
        except requests.Timeout:
            await update.message.reply_text(
                "⏰ API yanıt vermedi, lütfen tekrar deneyin."
            )
        except requests.RequestException as e:
            logger.error(f"Audd.io API request error: {str(e)}")
            await update.message.reply_text(
                "🔌 Bağlantı hatası oluştu, lütfen tekrar deneyin."
            )
        except Exception as e:
            logger.error(f"Music recognition error: {str(e)}")
            await update.message.reply_text(
                "⚠️ Beklenmeyen bir hata oluştu, lütfen tekrar deneyin."
            )
        
        finally:
            # Delete the processing message
            await processing_message.delete()
            
    except Exception as e:
        logger.error(f"Music recognition command error: {str(e)}")
        await update.message.reply_text("Bir hata oluştu. Lütfen tekrar deneyin.")

async def speed_test(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Perform an internet speed test."""
    try:
        # Send initial message
        message = await update.message.reply_text(
            "🔍 İnternet sağlayıcınızın sunucusu bulunuyor..."
        )
        
        # Initialize speedtest
        st = speedtest.Speedtest()
        
        # Get servers from your ISP
        await message.edit_text("📡 Sunucular bulundu, test başlatılıyor...")
        servers = []
        try:
            servers = st.get_servers()
            # Try to find server from same ISP
            isp_servers = [s for s in servers if s['sponsor'] in st.config['client']['isp']]
            if isp_servers:
                best_server = st.get_best_server(isp_servers)
            else:
                best_server = st.get_best_server(servers)
        except:
            best_server = st.get_best_server()
        
        # Show selected server
        await message.edit_text(
            f"🎯 Test Sunucusu:\n"
            f"📍 {best_server['sponsor']}\n"
            f"🏢 {best_server['host']}\n"
            f"📌 {best_server['country']}\n\n"
            f"⏳ Test başlıyor, lütfen bekleyin..."
        )
        
        # Test download speed
        await message.edit_text("⬇️ İndirme hızı test ediliyor...")
        download_speed = st.download()
        
        # Test upload speed
        await message.edit_text("⬆️ Yükleme hızı test ediliyor...")
        upload_speed = st.upload()
        
        # Get results
        results = st.results.dict()
        
        # Format speeds
        download_mbps = download_speed / 1_000_000  # Convert to Mbps
        upload_mbps = upload_speed / 1_000_000  # Convert to Mbps
        
        # Format date (Turkish format)
        test_date = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
        
        # Format results
        results_text = (
            "🌐 İnternet Hız Testi Sonuçları:\n\n"
            f"⬇️ İndirme: {download_mbps:.2f} Mbps\n"
            f"⬆️ Yükleme: {upload_mbps:.2f} Mbps\n"
            f"📡 Ping: {results['ping']:.0f} ms\n\n"
            f"📍 Sunucu: {best_server['sponsor']}\n"
            f"🏢 Host: {best_server['host']}\n"
            f"🌍 Konum: {best_server['country']}\n"
            f"📍 Mesafe: {best_server['d']:.2f} km\n"
            f"🕒 Test Tarihi: {test_date}"
        )
        
        await message.edit_text(results_text)
        
    except Exception as e:
        logger.error(f"Speed test error: {str(e)}")
        await update.message.reply_text(
            "❌ Hız testi yapılırken bir hata oluştu.\n"
            "Lütfen daha sonra tekrar deneyin."
        )

async def upscale_image(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle image upscaling requests with daily limits."""
    try:
        user_id = update.effective_user.id
        today = datetime.now().strftime("%Y-%m-%d")
        
        # Reset count if it's a new day
        if user_upscale_counts[user_id]["reset_date"] != today:
            user_upscale_counts[user_id] = {"count": 0, "reset_date": today}
            
        # Check if user has reached daily limit
        if user_upscale_counts[user_id]["count"] >= UPSCALE_DAILY_LIMIT:
            remaining_time = datetime.now().replace(hour=0, minute=0, second=0) + timedelta(days=1)
            hours_left = int((remaining_time - datetime.now()).total_seconds() / 3600)
            await update.message.reply_text(
                f"⚠️ Günlük iyileştirme limitinize ulaştınız (3/3)\n"
                f"🕒 Limitiniz {hours_left} saat sonra yenilenecek."
            )
            return

        # Check if message has photo
        if not update.message.reply_to_message or not update.message.reply_to_message.photo:
            await update.message.reply_text(
                "❌ Lütfen iyileştirmek istediğiniz resmi gönderin ve yanıtına /upscale yazın."
            )
            return

        # Get the largest photo
        photo = update.message.reply_to_message.photo[-1]
        
        # Download photo
        processing_msg = await update.message.reply_text("🔄 Resim iyileştiriliyor...")
        
        file = await context.bot.get_file(photo.file_id)
        file_url = file.file_path

        # Initialize Replicate client
        replicate = Client(api_token=os.getenv("REPLICATE_API_TOKEN"))
        
        # Run Upscale model with verified parameters
        output = replicate.run(
            "nightmareai/real-esrgan:f121d640bd286e1fdc67f9799164c1d5be36ff74576ee11c803ae5b665dd46aa",
            input={
                "image": file_url,
                "scale": 2
            }
        )
        
        if output and isinstance(output, str):
            enhanced_url = output
        elif output and isinstance(output, list) and len(output) > 0:
            enhanced_url = output[0]
        else:
            raise Exception("Invalid output format from Replicate API")

        # Send enhanced image
        await context.bot.send_photo(
            chat_id=update.effective_chat.id,
            photo=enhanced_url,
            caption="✨ Resim iyileştirildi!\n🔍 4x daha yüksek kalite"
        )
        
        # Update user count
        user_upscale_counts[user_id]["count"] += 1
        remaining = UPSCALE_DAILY_LIMIT - user_upscale_counts[user_id]["count"]
        
        await update.message.reply_text(
            f"ℹ️ Günlük kalan iyileştirme hakkınız: {remaining}/3"
        )
        
        await processing_msg.delete()
        
    except Exception as e:
        logging.error(f"Upscale error: {str(e)}")
        await update.message.reply_text("❌ Bir hata oluştu. Lütfen daha sonra tekrar deneyin.")

async def genre_movies(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Get movie recommendations by genre."""
    try:
        if not context.args:
            # Create genre list message
            genres_text = "🎬 Film Türleri:\n\n"
            for genre in sorted(MOVIE_GENRES.keys()):
                genres_text += f"• {genre.title()}\n"
            
            await update.message.reply_text(
                f"{genres_text}\n"
                "Kullanım: /genre korku"
            )
            return
        
        # Get genre from args
        genre = ' '.join(context.args).lower()
        
        if genre not in MOVIE_GENRES:
            await update.message.reply_text(
                "❌ Geçersiz film türü!\n"
                "Doğru türleri görmek için /genre komutunu kullanın."
            )
            return
        
        # Send processing message
        processing_message = await update.message.reply_text(
            f"🔍 {genre.title()} türünde filmler aranıyor..."
        )
        
        try:
            # Make request to TMDB API
            url = f"{TMDB_API_BASE}/discover/movie"
            params = {
                'api_key': TMDB_API_KEY,
                'language': 'tr-TR',
                'sort_by': 'popularity.desc',
                'with_genres': MOVIE_GENRES[genre],
                'page': 1
            }
            
            response = requests.get(url, params=params, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                movies = data.get('results', [])[:5]  # Get top 5 movies
                
                if movies:
                    for movie in movies:
                        # Get movie details
                        title = movie.get('title', 'Bilinmiyor')
                        overview = movie.get('overview', 'Açıklama yok')
                        release_date = movie.get('release_date', 'Bilinmiyor')
                        vote_average = movie.get('vote_average', 0)
                        poster_path = movie.get('poster_path')
                        
                        # Create message
                        message = (
                            f"🎬 {title}\n\n"
                            f"📅 Yayın Tarihi: {release_date}\n"
                            f"⭐ TMDB Puanı: {vote_average}/10\n\n"
                            f"📝 Özet:\n{overview}\n\n"
                            f"🎯 Tür: {genre.title()}"
                        )
                        
                        # Send movie info with poster if available
                        if poster_path:
                            poster_url = f"https://image.tmdb.org/t/p/w500{poster_path}"
                            await update.message.reply_photo(
                                photo=poster_url,
                                caption=message
                            )
                        else:
                            await update.message.reply_text(message)
                else:
                    await update.message.reply_text(
                        f"❌ {genre.title()} türünde film bulunamadı."
                    )
            else:
                await update.message.reply_text(
                    "❌ Film bilgileri alınamadı.\n"
                    "Lütfen daha sonra tekrar deneyin."
                )
                
        except requests.Timeout:
            await update.message.reply_text(
                "⏰ API yanıt vermedi, lütfen tekrar deneyin."
            )
        except requests.RequestException as e:
            logger.error(f"TMDB API request error: {str(e)}")
            await update.message.reply_text(
                "🔌 Bağlantı hatası oluştu, lütfen tekrar deneyin."
            )
        
        finally:
            await processing_message.delete()
            
    except Exception as e:
        logger.error(f"Genre movies error: {str(e)}")
        await update.message.reply_text("Bir hata oluştu. Lütfen tekrar deneyin.")

async def similar_movies(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Get similar movie recommendations."""
    try:
        if not context.args:
            await update.message.reply_text(
                "Lütfen bir film adı girin.\n"
                "Örnek: /similar Matrix"
            )
            return
        
        # Get movie name from args
        movie_name = ' '.join(context.args)
        
        # Send processing message
        processing_message = await update.message.reply_text(
            f"🔍 '{movie_name}' filmine benzer filmler aranıyor..."
        )
        
        try:
            # First, search for the movie
            search_url = f"{TMDB_API_BASE}/search/movie"
            search_params = {
                'api_key': TMDB_API_KEY,
                'language': 'tr-TR',
                'query': movie_name
            }
            
            search_response = requests.get(search_url, params=search_params, timeout=30)
            
            if search_response.status_code == 200:
                search_data = search_response.json()
                movies = search_data.get('results', [])
                
                if movies:
                    # Get first movie's ID
                    movie_id = movies[0]['id']
                    
                    # Get similar movies
                    similar_url = f"{TMDB_API_BASE}/movie/{movie_id}/similar"
                    similar_params = {
                        'api_key': TMDB_API_KEY,
                        'language': 'tr-TR'
                    }
                    
                    similar_response = requests.get(similar_url, params=similar_params, timeout=30)
                    
                    if similar_response.status_code == 200:
                        similar_data = similar_response.json()
                        similar_movies = similar_data.get('results', [])[:5]  # Get top 5 similar movies
                        
                        if similar_movies:
                            # Send original movie info first
                            original_movie = movies[0]
                            await update.message.reply_text(
                                f"🎯 Aranan Film: {original_movie.get('title')}\n"
                                f"📅 Yayın Tarihi: {original_movie.get('release_date')}\n"
                                f"⭐ TMDB Puanı: {original_movie.get('vote_average')}/10\n\n"
                                "🎬 Benzer Filmler:"
                            )
                            
                            # Send similar movies
                            for movie in similar_movies:
                                title = movie.get('title', 'Bilinmiyor')
                                overview = movie.get('overview', 'Açıklama yok')
                                release_date = movie.get('release_date', 'Bilinmiyor')
                                vote_average = movie.get('vote_average', 0)
                                poster_path = movie.get('poster_path')
                                
                                message = (
                                    f"🎬 {title}\n\n"
                                    f"📅 Yayın Tarihi: {release_date}\n"
                                    f"⭐ TMDB Puanı: {vote_average}/10\n\n"
                                    f"📝 Özet:\n{overview}"
                                )
                                
                                if poster_path:
                                    poster_url = f"https://image.tmdb.org/t/p/w500{poster_path}"
                                    await update.message.reply_photo(
                                        photo=poster_url,
                                        caption=message
                                    )
                                else:
                                    await update.message.reply_text(message)
                        else:
                            await update.message.reply_text(
                                f"❌ '{movie_name}' filmine benzer film bulunamadı."
                            )
                    else:
                        await update.message.reply_text(
                            "❌ Benzer filmler alınamadı.\n"
                            "Lütfen daha sonra tekrar deneyin."
                        )
                else:
                    await update.message.reply_text(
                        f"❌ '{movie_name}' filmi bulunamadı.\n"
                        "Lütfen film adını kontrol edip tekrar deneyin."
                    )
            else:
                await update.message.reply_text(
                    "❌ Film araması yapılamadı.\n"
                    "Lütfen daha sonra tekrar deneyin."
                )
                
        except requests.Timeout:
            await update.message.reply_text(
                "⏰ API yanıt vermedi, lütfen tekrar deneyin."
            )
        except requests.RequestException as e:
            logger.error(f"TMDB API request error: {str(e)}")
            await update.message.reply_text(
                "🔌 Bağlantı hatası oluştu, lütfen tekrar deneyin."
            )
        
        finally:
            await processing_message.delete()
            
    except Exception as e:
        logger.error(f"Similar movies error: {str(e)}")
        await update.message.reply_text("Bir hata oluştu. Lütfen tekrar deneyin.")

async def chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Chat with Gemini Pro AI."""
    try:
        # Check if user provided text
        if not context.args:
            await update.message.reply_text(
                "Lütfen bir soru veya mesaj yazın.\n"
                "Örnek: /chat Yapay zeka nedir?"
            )
            return
        
        # Get the user's message
        user_message = ' '.join(context.args)
        
        # Send typing action
        await context.bot.send_chat_action(
            chat_id=update.effective_chat.id,
            action="typing"
        )
        
        try:
            # Prepare request parameters
            params = {
                'prompt': user_message,
                'language': 'tr',
                'model': 'gemini-1.5-flash',
                'temperature': 0.7
            }
            
            # Make request to Gemini API with SSL verification disabled
            response = requests.get(
                GEMINI_API_BASE, 
                params=params, 
                timeout=30,
                verify=False  # Disable SSL verification
            )
            
            if response.status_code == 200:
                data = response.json()
                
                if data and isinstance(data, str):
                    # Send the AI response
                    await update.message.reply_text(
                        f"🤖 Yanıt:\n\n{data}",
                        parse_mode='Markdown'
                    )
                else:
                    await update.message.reply_text(
                        "❌ API'den geçersiz yanıt alındı.\n"
                        "Lütfen daha sonra tekrar deneyin."
                    )
            else:
                await update.message.reply_text(
                    "❌ Şu anda yanıt veremiyorum.\n"
                    "Lütfen daha sonra tekrar deneyin."
                )
                
        except requests.Timeout:
            await update.message.reply_text(
                "⏰ API yanıt vermedi, lütfen tekrar deneyin."
            )
        except requests.RequestException as e:
            logger.error(f"Gemini API request error: {str(e)}")
            await update.message.reply_text(
                "🔌 Bağlantı hatası oluştu, lütfen tekrar deneyin."
            )
        except Exception as e:
            logger.error(f"Chat error: {str(e)}")
            await update.message.reply_text(
                "⚠️ Beklenmeyen bir hata oluştu, lütfen tekrar deneyin."
            )
            
    except Exception as e:
        logger.error(f"Chat command error: {str(e)}")
        await update.message.reply_text("Bir hata oluştu. Lütfen tekrar deneyin.")

def main():
    """Start the bot."""
    try:
        # Create the Application and pass it your bot's token
        application = Application.builder().token(TELEGRAM_TOKEN).build()

        # Add command handlers
        handlers = [
            CommandHandler("start", start),
            CommandHandler("dalle", generate_dalle),
            CommandHandler("flux", generate_flux),
            CommandHandler("song", search_song),
            CommandHandler("whois", whois_lookup),
            CommandHandler("yt", youtube_command),
            CommandHandler("speedtest", speed_test),
            CommandHandler("upscale", upscale_image),
            CommandHandler("genre", genre_movies),
            CommandHandler("similar", similar_movies),
            CommandHandler("chat", chat),
            CallbackQueryHandler(youtube_button),
            MessageHandler(filters.VOICE | filters.AUDIO, recognize_music)
        ]

        # Add all handlers to the application
        for handler in handlers:
            application.add_handler(handler)

        # Log startup information
        logger.info("Bot configuration:")
        logger.info(f"- Maximum requests per minute: {MAX_REQUESTS_PER_MINUTE}")
        logger.info(f"- Maximum prompt length: {MAX_PROMPT_LENGTH}")
        logger.info("- Available commands: start, dalle, flux, song, whois, yt, speedtest, upscale, genre, similar, chat")
        logger.info("- Music recognition enabled: Yes")
        logger.info("Bot started successfully!")

        # Start the Bot with error handling and increased timeouts
        application.run_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True,
            timeout=120,  # Increased timeout
            read_timeout=120,  # Added read timeout
            write_timeout=120,  # Added write timeout
            pool_timeout=120,  # Added pool timeout
            connect_timeout=120,  # Added connect timeout
            bootstrap_retries=-1  # Infinite retries on startup
        )
    except Exception as e:
        logger.error(f"Critical error in main function: {str(e)}", exc_info=True)
        sys.exit(1)

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Unhandled exception: {str(e)}", exc_info=True)
        sys.exit(1) 