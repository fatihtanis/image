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

    def _follow_all_redirects(self, url: str, max_redirects: int = 10) -> Optional[str]:
        """Tüm yönlendirmeleri takip et ve son URL'yi döndür"""
        try:
            current_url = url
            redirect_count = 0
            
            while redirect_count < max_redirects:
                logger.info(f"URL'ye istek gönderiliyor: {current_url}")
                
                response = self.session.get(
                    current_url,
                    headers=self.headers,
                    verify=False,
                    allow_redirects=False  # Manuel yönlendirme takibi için
                )
                
                logger.info(f"Yanıt kodu: {response.status_code}")
                logger.info(f"Yanıt başlıkları: {dict(response.headers)}")
                
                # Yönlendirme var mı kontrol et
                if response.status_code in [301, 302, 303, 307, 308]:
                    if 'Location' in response.headers:
                        new_url = response.headers['Location']
                        if not new_url.startswith('http'):
                            # Göreceli URL'yi mutlak URL'ye çevir
                            new_url = f"https://www.lastroom.ct.ws{new_url}"
                        logger.info(f"Yönlendirme bulundu: {new_url}")
                        current_url = new_url
                        redirect_count += 1
                        continue
                
                # JavaScript yönlendirmesi var mı kontrol et
                if response.status_code == 200:
                    soup = BeautifulSoup(response.text, 'html.parser')
                    
                    # Meta refresh kontrolü
                    meta_refresh = soup.find('meta', {'http-equiv': 'refresh'})
                    if meta_refresh and 'content' in meta_refresh.attrs:
                        content = meta_refresh['content']
                        if 'url=' in content.lower():
                            new_url = content.split('url=')[1].strip()
                            logger.info(f"Meta refresh yönlendirmesi bulundu: {new_url}")
                            current_url = new_url
                            redirect_count += 1
                            continue
                    
                    # JavaScript location.href kontrolü
                    scripts = soup.find_all('script')
                    for script in scripts:
                        if script.string and 'location.href' in script.string:
                            match = re.search(r'location\.href\s*=\s*["\']([^"\']+)["\']', script.string)
                            if match:
                                new_url = match.group(1)
                                if not new_url.startswith('http'):
                                    new_url = f"https://www.lastroom.ct.ws{new_url}"
                                logger.info(f"JavaScript yönlendirmesi bulundu: {new_url}")
                                current_url = new_url
                                redirect_count += 1
                                continue
                    
                    # Tmpfiles URL'i kontrolü
                    tmpfiles_match = re.search(r'tmpfiles\.org/[a-zA-Z0-9/\-_.]+', response.text)
                    if tmpfiles_match:
                        new_url = f"https://{tmpfiles_match.group(0)}"
                        logger.info(f"Tmpfiles URL'i bulundu: {new_url}")
                        current_url = new_url
                        redirect_count += 1
                        continue
                
                # Yönlendirme yoksa son URL'yi döndür
                return current_url
            
            logger.error(f"Maksimum yönlendirme sayısına ulaşıldı ({max_redirects})")
            return None
            
        except Exception as e:
            logger.error(f"Yönlendirme takip hatası: {str(e)}")
            return None

    def _get_final_image_url(self, url: str) -> Optional[str]:
        """Son URL'den resim URL'ini al"""
        try:
            response = self.session.get(url, headers=self.headers, verify=False)
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # Tmpfiles resmi kontrolü
                img = soup.find('img', {'id': 'img'})
                if img and img.get('src'):
                    image_url = img.get('src')
                    if not image_url.startswith('http'):
                        image_url = f"https://tmpfiles.org{image_url}"
                    logger.info(f"Tmpfiles resim URL'i bulundu: {image_url}")
                    return image_url
                
                # Diğer resim kontrolü
                for img in soup.find_all('img'):
                    src = img.get('src', '')
                    if src and ('result' in src.lower() or 'output' in src.lower() or 'generated' in src.lower()):
                        if not src.startswith('http'):
                            src = f"https://www.lastroom.ct.ws{src}"
                        logger.info(f"Resim URL'i bulundu: {src}")
                        return src
            
            return None
        except Exception as e:
            logger.error(f"Resim URL'i alma hatası: {str(e)}")
            return None

    def generate_image(self, prompt: str) -> Optional[str]:
        """Verilen prompt ile resim oluşturur"""
        try:
            # URL'yi hazırla
            url = f"{self.base_url}?prompt={prompt}"
            logger.info(f"Başlangıç URL'i: {url}")
            
            # Tüm yönlendirmeleri takip et
            final_url = self._follow_all_redirects(url)
            if final_url:
                logger.info(f"Son URL: {final_url}")
                # Son URL'den resim URL'ini al
                return self._get_final_image_url(final_url)
            
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