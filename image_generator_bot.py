import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
import requests
import urllib.parse
from datetime import datetime, timedelta
from collections import defaultdict
import base64
from pytube import YouTube
import re

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

logger = logging.getLogger(__name__)

# Get the token from environment variable
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
AUDD_API_TOKEN = os.getenv("AUDD_API_TOKEN")
if not TELEGRAM_TOKEN:
    raise ValueError("No TELEGRAM_TOKEN environment variable found!")

# Rate limiting
USER_RATES = defaultdict(list)
MAX_REQUESTS_PER_MINUTE = 3
MAX_PROMPT_LENGTH = 200

# API URLs
MUSIC_API_BASE = "https://jiosaavn-api-codyandersan.vercel.app/search/all"
WHOIS_API_BASE = "https://rdap.org/domain/"
AUDD_API_URL = "https://api.audd.io/"

# YouTube video info cache
youtube_cache = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a message when the command /start is issued."""
    try:
        user_name = update.message.from_user.first_name
        await update.message.reply_text(
            f'Merhaba {user_name}! 👋\n'
            f'Komutlar:\n'
            f'1. Resim oluşturmak için: /generate [açıklama]\n'
            f'2. Şarkı aramak için: /song [şarkı adı]\n'
            f'3. Domain sorgulamak için: /whois [domain.com]\n'
            f'4. Müzik tanımak için: Ses kaydı veya müzik dosyası gönderin 🎵\n'
            f'5. YouTube indirmek için: /yt [video linki]\n\n'
            f'Örnekler:\n'
            f'- /generate bir adam denizde yüzüyor 🎨\n'
            f'- /song Hadise Aşk Kaç Beden Giyer 🎵\n'
            f'- /whois google.com 🔍\n'
            f'- Müzik tanıma için ses kaydı veya müzik dosyası gönderin 🎧\n'
            f'- /yt https://youtube.com/watch?v=... 📥\n\n'
            f'Limitler:\n'
            f'- Dakikada {MAX_REQUESTS_PER_MINUTE} resim oluşturabilirsiniz\n'
            f'- Maksimum {MAX_PROMPT_LENGTH} karakter uzunluğunda açıklama'
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
        
        # Get the URL and clean it
        url = context.args[0]
        # Remove timestamp and other parameters
        if '?' in url:
            base_url = url.split('?')[0]
            video_id = extract_video_id(base_url)
        else:
            video_id = extract_video_id(url)
        
        if not video_id:
            await update.message.reply_text(
                "❌ Geçersiz YouTube linki.\n"
                "Lütfen geçerli bir YouTube linki girin."
            )
            return
        
        # Send processing message
        processing_message = await update.message.reply_text(
            "🔍 Video bilgileri alınıyor..."
        )
        
        try:
            # Reconstruct clean URL
            clean_url = f"https://youtube.com/watch?v={video_id}"
            # Get video info
            yt = YouTube(clean_url)
            
            # Cache video info
            youtube_cache[video_id] = {
                'url': clean_url,
                'title': yt.title,
                'author': yt.author,
                'length': yt.length,
                'views': yt.views,
                'thumbnail': yt.thumbnail_url
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
            
            # Format duration
            duration_min = yt.length // 60
            duration_sec = yt.length % 60
            duration_str = f"{duration_min}:{duration_sec:02d}"
            
            # Send video info with format selection
            await update.message.reply_photo(
                photo=yt.thumbnail_url,
                caption=(
                    f"📹 Video Bilgileri:\n\n"
                    f"📝 Başlık: {yt.title}\n"
                    f"👤 Kanal: {yt.author}\n"
                    f"⏱️ Süre: {duration_str}\n"
                    f"👁️ İzlenme: {yt.views:,}\n\n"
                    f"Lütfen indirme formatını seçin:"
                ),
                reply_markup=reply_markup
            )
            
        except Exception as e:
            logger.error(f"YouTube info error: {str(e)}")
            await update.message.reply_text(
                "❌ Video bilgileri alınamadı.\n"
                "Lütfen geçerli bir YouTube linki girdiğinizden emin olun veya daha sonra tekrar deneyin."
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
        
        # Send processing message
        processing_message = await query.message.reply_text(
            "📥 İndirme hazırlanıyor..."
        )
        
        try:
            yt = YouTube(video_info['url'])
            
            if format_type == 'audio':
                # Download as MP3
                stream = yt.streams.filter(only_audio=True).first()
                if not stream:
                    raise Exception("Ses akışı bulunamadı")
                
                await query.message.reply_text(
                    f"🎵 MP3 indirme linki hazır:\n{stream.url}\n\n"
                    "Not: Link 6 saat geçerlidir."
                )
                
            else:
                # Download as MP4
                resolution = format_type + 'p'
                stream = yt.streams.filter(res=resolution, progressive=True).first()
                if not stream:
                    raise Exception(f"{resolution} çözünürlükte video bulunamadı")
                
                await query.message.reply_text(
                    f"🎥 {resolution} MP4 indirme linki hazır:\n{stream.url}\n\n"
                    "Not: Link 6 saat geçerlidir."
                )
            
        except Exception as e:
            logger.error(f"YouTube download error: {str(e)}")
            await query.message.reply_text(
                f"❌ İndirme hazırlanırken hata oluştu: {str(e)}\n"
                "Lütfen başka bir format seçin veya daha sonra tekrar deneyin."
            )
        
        finally:
            await processing_message.delete()
            
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

async def generate_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generate an image based on the user's text input."""
    try:
        # Check if user provided text
        if not context.args:
            await update.message.reply_text(
                "Lütfen bir açıklama girin.\n"
                "Örnek: /generate bir adam denizde yüzüyor"
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
        
        # Get the text after the /generate command
        user_text = ' '.join(context.args)
        
        # Check prompt length
        if len(user_text) > MAX_PROMPT_LENGTH:
            await update.message.reply_text(
                f"Açıklama çok uzun! Maksimum {MAX_PROMPT_LENGTH} karakter girebilirsiniz."
            )
            return
        
        # Send a "processing" message
        processing_message = await update.message.reply_text(
            "Resim oluşturuluyor, lütfen bekleyin... 🎨"
        )
        
        try:
            # Encode the user's text for the URL
            encoded_text = urllib.parse.quote(user_text)
            
            # Make request to the image generation API
            api_url = f"https://prompt.glitchy.workers.dev/gen?key={encoded_text}&t=0.2&f=dalle3&demo=true&count=1"
            response = requests.get(api_url, timeout=30)  # 30 second timeout
            
            if response.status_code == 200:
                data = response.json()
                if data.get("status") == 1 and "images" in data:
                    # Get the image URL from the response
                    image_url = data["images"][0]["imagedemo1"][0]
                    
                    # Send the image
                    await update.message.reply_photo(
                        photo=image_url,
                        caption=f"İşte senin için oluşturduğum resim! 🎨\nPrompt: {user_text}"
                    )
                else:
                    error_msg = "API yanıtı geçersiz"
                    logger.error(f"API response error: {data}")
                    await update.message.reply_text(
                        f"Üzgünüm, resim oluşturulamadı: {error_msg}\n"
                        "Lütfen tekrar deneyin."
                    )
            else:
                error_msg = f"HTTP {response.status_code}"
                logger.error(f"API status code error: {response.status_code}")
                await update.message.reply_text(
                    f"API'ye erişirken bir hata oluştu: {error_msg}\n"
                    "Lütfen tekrar deneyin."
                )
                
        except requests.Timeout:
            await update.message.reply_text(
                "API yanıt vermedi, lütfen tekrar deneyin."
            )
        except requests.RequestException as e:
            logger.error(f"Request error: {str(e)}")
            await update.message.reply_text(
                "Bağlantı hatası oluştu, lütfen tekrar deneyin."
            )
        except Exception as e:
            logger.error(f"Generate image error: {str(e)}")
            await update.message.reply_text(
                "Beklenmeyen bir hata oluştu, lütfen tekrar deneyin."
            )
        
        finally:
            # Delete the processing message
            await processing_message.delete()
            
    except Exception as e:
        logger.error(f"Generate command error: {str(e)}")
        await update.message.reply_text("Bir hata oluştu. Lütfen tekrar deneyin.")

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
    """Recognize music from voice message or audio file."""
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
            
            # Prepare the request
            files = {
                'file': ('audio.ogg', file_bytes),
                'api_token': (None, AUDD_API_TOKEN),
                'return': (None, 'spotify,apple_music,deezer')
            }
            
            # Make request to AudD API
            response = requests.post(AUDD_API_URL, files=files, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                
                if data.get("status") == "success" and data.get("result"):
                    result = data["result"]
                    
                    # Create response message
                    message = "🎵 Müzik Bulundu!\n\n"
                    message += f"🎤 Sanatçı: {result.get('artist', 'Bilinmiyor')}\n"
                    message += f"🎼 Şarkı: {result.get('title', 'Bilinmiyor')}\n"
                    message += f"💿 Albüm: {result.get('album', 'Bilinmiyor')}\n"
                    message += f"📅 Yıl: {result.get('release_date', 'Bilinmiyor')}\n\n"
                    
                    # Add streaming links if available
                    if result.get("spotify"):
                        message += f"Spotify: {result['spotify']['external_urls']['spotify']}\n"
                    if result.get("apple_music"):
                        message += f"Apple Music: {result['apple_music']['url']}\n"
                    if result.get("deezer"):
                        message += f"Deezer: {result['deezer']['link']}\n"
                    
                    await update.message.reply_text(message)
                    
                else:
                    await update.message.reply_text(
                        "❌ Üzgünüm, bu müziği tanıyamadım.\n"
                        "Lütfen daha net bir kayıt göndermeyi deneyin."
                    )
            else:
                await update.message.reply_text(
                    "❌ Müzik tanıma servisi şu anda çalışmıyor.\n"
                    "Lütfen daha sonra tekrar deneyin."
                )
                
        except requests.Timeout:
            await update.message.reply_text(
                "⏰ API yanıt vermedi, lütfen tekrar deneyin."
            )
        except requests.RequestException as e:
            logger.error(f"Music recognition API error: {str(e)}")
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

def main():
    """Start the bot."""
    try:
        # Create the Application and pass it your bot's token
        application = Application.builder().token(TELEGRAM_TOKEN).build()

        # Add handlers
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("generate", generate_image))
        application.add_handler(CommandHandler("song", search_song))
        application.add_handler(CommandHandler("whois", whois_lookup))
        application.add_handler(CommandHandler("yt", youtube_command))
        application.add_handler(CallbackQueryHandler(youtube_button))
        application.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, recognize_music))

        # Start the Bot
        logger.info("Bot started successfully!")
        application.run_polling(allowed_updates=Update.ALL_TYPES)
    except Exception as e:
        logger.error(f"Main function error: {str(e)}")

if __name__ == '__main__':
    main() 