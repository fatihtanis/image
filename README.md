# Lastroom API Client

Bu proje, Lastroom AI Image Generation API'si ile etkileşim kurmak için bir Python istemcisi içerir.

## Özellikler

- Metin tabanlı resim oluşturma
- Hata yönetimi ve loglama
- Timeout ve yeniden deneme mekanizmaları
- Detaylı debug bilgileri

## Kurulum

1. Gereksinimleri yükleyin:
```bash
pip install -r requirements.txt
```

2. Kodu çalıştırın:
```bash
python lastroom_api.py
```

## Kullanım

```python
from lastroom_api import LastroomAPI

# API istemcisini oluştur
api = LastroomAPI()

# Resim oluştur
result = api.generate_image("a beautiful sunset over mountains")
if result:
    print("Resim başarıyla oluşturuldu!")
```

## Loglama

Tüm API istekleri ve yanıtları `lastroom.log` dosyasına kaydedilir. Hata ayıklama için bu dosyayı kontrol edin.

## Hata Yönetimi

- Timeout kontrolleri
- Yeniden deneme mekanizması
- Detaylı hata mesajları
- Exception handling

## Güvenlik

- User-Agent doğrulama
- Rate limiting kontrolü
- Timeout ayarları
- Güvenli HTTP istekleri 