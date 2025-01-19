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

    def _extract_tmpfiles_url(self, content):
        """Şifrelenmiş içerikten tmpfiles URL'ini çıkar"""
        try:
            # Tmpfiles URL'ini bulmak için regex
            pattern = r'tmpfiles\.org/[a-zA-Z0-9/\-_.]+'
            match = re.search(pattern, content)
            if match:
                url = f"https://{match.group(0)}"
                logger.info(f"Tmpfiles URL'i bulundu: {url}")
                return url
            return None
        except Exception as e:
            logger.error(f"Tmpfiles URL çıkarma hatası: {str(e)}")
            return None

    def _get_image_from_tmpfiles(self, tmpfiles_url):
        """Tmpfiles sayfasından resim URL'ini al"""
        try:
            response = self.session.get(tmpfiles_url, headers=self.headers, verify=False)
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # Resim URL'ini bul
                img = soup.find('img', {'id': 'img'})
                if img and img.get('src'):
                    image_url = img.get('src')
                    if not image_url.startswith('http'):
                        image_url = f"https://tmpfiles.org{image_url}"
                    logger.info(f"Resim URL'i bulundu: {image_url}")
                    return image_url
            
            return None
        except Exception as e:
            logger.error(f"Tmpfiles resim alma hatası: {str(e)}")
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
            logger.info(f"İlk yanıt içeriği: {response.text[:200]}")
            
            if response.status_code == 200:
                # Tmpfiles URL'ini bul
                tmpfiles_url = self._extract_tmpfiles_url(response.text)
                if tmpfiles_url:
                    # Tmpfiles'dan resmi al
                    return self._get_image_from_tmpfiles(tmpfiles_url)
                
                logger.error("Tmpfiles URL'i bulunamadı")
            
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