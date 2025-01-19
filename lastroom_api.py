import requests
import json
import base64
from typing import Optional
import logging
import sys
import urllib3

# SSL uyarılarını devre dışı bırak
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Logging ayarları
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('lastroom.log')
    ]
)

logger = logging.getLogger(__name__)

class LastroomAPI:
    def __init__(self):
        self.base_url = "https://www.lastroom.ct.ws/ai-image/"
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Connection': 'keep-alive',
        }

    def generate_image(self, prompt: str) -> Optional[str]:
        """
        Verilen prompt ile resim oluşturur.
        
        Args:
            prompt (str): Resim oluşturmak için metin
            
        Returns:
            Optional[str]: Oluşturulan resmin URL'i veya None
        """
        try:
            # API isteği için parametreler
            params = {
                'prompt': prompt
            }
            
            # API isteği gönder
            logger.info(f"API isteği gönderiliyor. Prompt: {prompt}")
            response = requests.get(
                self.base_url,
                params=params,
                headers=self.headers,
                timeout=30,
                verify=False  # SSL doğrulamasını devre dışı bırak
            )
            
            # Yanıt durumunu logla
            logger.info(f"API yanıt kodu: {response.status_code}")
            logger.info(f"API yanıtı: {response.text[:200]}...")  # İlk 200 karakteri logla
            
            if response.status_code == 200:
                logger.info("Başarılı yanıt alındı, HTML içeriği parse ediliyor...")
                # HTML içeriğini parse et
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # JavaScript içeriğini ve olası resim URL'lerini logla
                scripts = soup.find_all('script')
                for script in scripts:
                    logger.info(f"Script içeriği: {script.string if script.string else 'Boş script'}")
                
                images = soup.find_all('img')
                for img in images:
                    logger.info(f"Resim URL'i bulundu: {img.get('src', 'URL bulunamadı')}")
                
                return response.text
            else:
                logger.error(f"API hatası: {response.status_code}")
                return None
                
        except requests.Timeout:
            logger.error("API zaman aşımına uğradı")
            return None
        except requests.RequestException as e:
            logger.error(f"API isteği hatası: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"Beklenmeyen hata: {str(e)}")
            return None

def main():
    """Test fonksiyonu"""
    api = LastroomAPI()
    
    # Test promptları
    test_prompts = [
        "a beautiful sunset over mountains",
        "cute cat playing with yarn",
        "futuristic city at night"
    ]
    
    # Her prompt için test et
    for prompt in test_prompts:
        print(f"\nPrompt ile test ediliyor: {prompt}")
        result = api.generate_image(prompt)
        if result:
            print(f"Başarılı! Yanıt alındı.")
        else:
            print(f"Hata! Resim oluşturulamadı.")

if __name__ == "__main__":
    main() 