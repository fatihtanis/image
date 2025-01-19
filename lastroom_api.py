import requests
import json
import base64
from typing import Optional
import logging
import sys
import urllib3
from bs4 import BeautifulSoup
import re
import time

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
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-User': '?1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Ch-Ua': '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
            'Sec-Ch-Ua-Mobile': '?0',
            'Sec-Ch-Ua-Platform': '"Windows"',
            'Cache-Control': 'max-age=0'
        }
        self.session = requests.Session()

    def _get_image_url(self, html_content):
        """HTML içeriğinden resim URL'ini çıkar"""
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Tüm img etiketlerini kontrol et
            for img in soup.find_all('img'):
                src = img.get('src', '')
                if src and ('result' in src.lower() or 'output' in src.lower() or 'generated' in src.lower()):
                    if not src.startswith('http'):
                        src = f"https://www.lastroom.ct.ws{src}"
                    logger.info(f"Resim URL'i bulundu: {src}")
                    return src
            
            return None
        except Exception as e:
            logger.error(f"Resim URL'i çıkarma hatası: {str(e)}")
            return None

    def generate_image(self, prompt: str) -> Optional[str]:
        """Verilen prompt ile resim oluşturur"""
        try:
            # URL'yi hazırla
            url = f"{self.base_url}?prompt={prompt}"
            logger.info(f"İstek URL'i: {url}")
            
            # İlk istek - ana sayfa
            response = self.session.get(
                url,
                headers=self.headers,
                verify=False,
                allow_redirects=True
            )
            
            logger.info(f"İlk yanıt kodu: {response.status_code}")
            
            if response.status_code == 200:
                # Kısa bir bekleme
                time.sleep(2)
                
                # İkinci istek - resim sayfası
                response = self.session.get(
                    f"{url}&i=1",
                    headers=self.headers,
                    verify=False,
                    allow_redirects=True
                )
                
                if response.status_code == 200:
                    # Resim URL'ini bul
                    image_url = self._get_image_url(response.text)
                    if image_url:
                        return image_url
                    
                    logger.error("Resim URL'i bulunamadı")
                    logger.info(f"Sayfa içeriği: {response.text[:500]}...")
            
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