import requests
import json
import base64
from typing import Optional
import logging
import sys
import urllib3
from bs4 import BeautifulSoup
import re

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
        self.session = requests.Session()

    def _follow_redirect(self, html_content, prompt):
        """JavaScript yönlendirmesini takip et"""
        try:
            # Direkt olarak i=1 parametresi eklenmiş URL'yi dene
            redirect_url = f"{self.base_url}?prompt={prompt}&i=1"
            logger.info(f"Yönlendirme URL'i: {redirect_url}")
            
            # Cookie'leri kullanarak yönlendirmeyi takip et
            response = self.session.get(redirect_url, headers=self.headers, verify=False)
            return response
            
        except Exception as e:
            logger.error(f"Yönlendirme hatası: {str(e)}")
            return None

    def generate_image(self, prompt: str) -> Optional[str]:
        """Verilen prompt ile resim oluşturur"""
        try:
            # İlk istek
            params = {'prompt': prompt}
            response = self.session.get(
                self.base_url,
                params=params,
                headers=self.headers,
                verify=False
            )
            
            logger.info(f"İlk yanıt kodu: {response.status_code}")
            
            if response.status_code == 200:
                # Yönlendirmeyi takip et
                redirect_response = self._follow_redirect(response.text, prompt)
                
                if redirect_response and redirect_response.status_code == 200:
                    logger.info("Yönlendirme başarılı")
                    logger.info(f"Yanıt içeriği: {redirect_response.text[:200]}...")
                    
                    # Resim URL'ini bul
                    soup = BeautifulSoup(redirect_response.text, 'html.parser')
                    img_tag = soup.find('img', {'class': 'result-image'})
                    
                    if img_tag and img_tag.get('src'):
                        image_url = img_tag.get('src')
                        if not image_url.startswith('http'):
                            image_url = f"https://www.lastroom.ct.ws{image_url}"
                        logger.info(f"Resim URL'i bulundu: {image_url}")
                        return image_url
                    
                    logger.error("Resim URL'i bulunamadı")
                    return None
            
            return None
                
        except Exception as e:
            logger.error(f"API hatası: {str(e)}")
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