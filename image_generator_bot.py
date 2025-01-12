import os
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import requests
import urllib.parse
from datetime import datetime, timedelta
from collections import defaultdict

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

logger = logging.getLogger(__name__)

# Get the token from environment variable
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
if not TELEGRAM_TOKEN:
    raise ValueError("No TELEGRAM_TOKEN environment variable found!")

# Rate limiting
USER_RATES = defaultdict(list)
MAX_REQUESTS_PER_MINUTE = 3
MAX_PROMPT_LENGTH = 200

# API URLs
MUSIC_API_BASE = "https://jiosaavn-api-codyandersan.vercel.app/search/all"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a message when the command /start is issued."""
    try:
        user_name = update.message.from_user.first_name
        await update.message.reply_text(
            f'Merhaba {user_name}! 👋\n'
            f'Komutlar:\n'
            f'1. Resim oluşturmak için: /generate [açıklama]\n'
            f'2. Şarkı aramak için: /song [şarkı adı]\n\n'
            f'Örnekler:\n'
            f'- /generate bir adam denizde yüzüyor 🎨\n'
            f'- /song Hadise Aşk Kaç Beden Giyer 🎵\n\n'
            f'Limitler:\n'
            f'- Dakikada {MAX_REQUESTS_PER_MINUTE} resim oluşturabilirsiniz\n'
            f'- Maksimum {MAX_PROMPT_LENGTH} karakter uzunluğunda açıklama'
        )
    except Exception as e:
        logger.error(f"Start command error: {str(e)}")
        await update.message.reply_text("Bir hata oluştu. Lütfen tekrar deneyin.")

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

def main():
    """Start the bot."""
    try:
        # Create the Application and pass it your bot's token
        application = Application.builder().token(TELEGRAM_TOKEN).build()

        # Add handlers
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("generate", generate_image))
        application.add_handler(CommandHandler("song", search_song))

        # Start the Bot
        logger.info("Bot started successfully!")
        application.run_polling(allowed_updates=Update.ALL_TYPES)
    except Exception as e:
        logger.error(f"Main function error: {str(e)}")

if __name__ == '__main__':
    main() 