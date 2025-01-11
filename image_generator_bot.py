import os
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import requests
import urllib.parse

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

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a message when the command /start is issued."""
    try:
        user_name = update.message.from_user.first_name
        await update.message.reply_text(f'Merhaba {user_name}! 👋\nResim oluşturmak için /generate komutunu kullanın.\nÖrnek: /generate bir adam denizde yüzüyor 🎨')
    except Exception as e:
        logger.error(f"Start command error: {str(e)}")
        await update.message.reply_text("Bir hata oluştu. Lütfen tekrar deneyin.")

async def generate_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generate an image based on the user's text input."""
    if not context.args:
        await update.message.reply_text("Lütfen bir açıklama girin.\nÖrnek: /generate bir adam denizde yüzüyor")
        return
    
    # Get the text after the /generate command
    user_text = ' '.join(context.args)
    
    # Send a "processing" message
    processing_message = await update.message.reply_text("Resim oluşturuluyor, lütfen bekleyin... 🎨")
    
    try:
        # Encode the user's text for the URL
        encoded_text = urllib.parse.quote(user_text)
        
        # Make request to the image generation API
        api_url = f"https://prompt.glitchy.workers.dev/gen?key={encoded_text}&t=0.2&f=dalle3&demo=true&count=1"
        response = requests.get(api_url)
        
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
                await update.message.reply_text("Üzgünüm, resim oluşturulamadı. Lütfen tekrar deneyin.")
                logger.error(f"API response error: {data}")
        else:
            await update.message.reply_text("API'ye erişirken bir hata oluştu. Lütfen tekrar deneyin.")
            logger.error(f"API status code error: {response.status_code}")
            
    except Exception as e:
        logger.error(f"Generate image error: {str(e)}")
        await update.message.reply_text("Bir hata oluştu. Lütfen tekrar deneyin.")
    
    finally:
        # Delete the processing message
        await processing_message.delete()

def main():
    """Start the bot."""
    try:
        # Create the Application and pass it your bot's token
        application = Application.builder().token(TELEGRAM_TOKEN).build()

        # Add handlers
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("generate", generate_image))

        # Start the Bot
        logger.info("Bot started successfully!")
        application.run_polling(allowed_updates=Update.ALL_TYPES)
    except Exception as e:
        logger.error(f"Main function error: {str(e)}")

if __name__ == '__main__':
    main() 