"""
WhatsApp Bildirim Modülü
Twilio API üzerinden WhatsApp bildirimi gönderir.

Kurulum:
1. https://www.twilio.com adresinden ücretsiz hesap oluşturun
2. Console > Messaging > Try it out > Send a WhatsApp message
3. Sandbox'ı aktifleştirin (telefondan join komutu gönderin)
4. .env dosyasına TWILIO bilgilerini ekleyin
"""

import os
import logging
from datetime import datetime
from dotenv import load_dotenv

logger = logging.getLogger(__name__)
load_dotenv()

TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_WHATSAPP_FROM = os.getenv("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886")  # Twilio sandbox numarası
WHATSAPP_TO = os.getenv("WHATSAPP_TO", "")  # Senin numaranız: whatsapp:+905xxxxxxxxx


class WhatsAppNotifier:
    """Twilio üzerinden WhatsApp bildirimi gönderir"""

    def __init__(self):
        self.account_sid = TWILIO_ACCOUNT_SID
        self.auth_token = TWILIO_AUTH_TOKEN
        self.from_number = TWILIO_WHATSAPP_FROM
        self.to_number = WHATSAPP_TO
        self.client = None
        self._initialized = False

    def _ensure_initialized(self):
        """Twilio client'ı lazy-initialize eder"""
        if not self._initialized:
            if self.account_sid and self.auth_token and self.account_sid != "your_account_sid":
                try:
                    from twilio.rest import Client
                    self.client = Client(self.account_sid, self.auth_token)
                    self._initialized = True
                    logger.info("WhatsApp (Twilio) bağlantısı kuruldu")
                except ImportError:
                    logger.warning("twilio paketi yüklü değil. pip install twilio")
                except Exception as e:
                    logger.error(f"Twilio başlatma hatası: {e}")
            else:
                logger.warning("Twilio bilgileri ayarlanmamış. WhatsApp devre dışı.")

    def send_message(self, text: str) -> bool:
        """WhatsApp mesajı gönderir"""
        self._ensure_initialized()

        if not self.client:
            logger.info(f"[WHATSAPP MESAJ - Simüle]: {text[:100]}...")
            return False

        try:
            # WhatsApp HTML desteklemez, düz metin olarak gönder
            clean_text = self._strip_html(text)

            message = self.client.messages.create(
                from_=self.from_number,
                body=clean_text,
                to=self.to_number
            )

            logger.info(f"WhatsApp mesajı gönderildi (SID: {message.sid})")
            return True

        except Exception as e:
            logger.error(f"WhatsApp mesaj gönderme hatası: {e}")
            return False

    def send_event_alert(self, event: dict) -> bool:
        """Kritik olay bildirimi gönderir (Golden Cross, Hacim Patlaması vs.)"""
        text = (
            f"{event['emoji']} {event['title']}\n\n"
            f"📊 Hisse: {event['symbol']}\n"
            f"💰 Fiyat: {event['price']:.2f} TL\n"
            f"🎯 Aksiyon: {event['action']}\n\n"
            f"{event['description']}\n\n"
            f"⏰ {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}"
        )
        return self.send_message(text)

    def send_buy_signal(self, symbol: str, price: float, score: float, reason: str) -> bool:
        """AL sinyali gönderir"""
        text = (
            f"🟢🟢 GÜÇLÜ AL SİNYALİ\n\n"
            f"📊 Hisse: {symbol}\n"
            f"💰 Fiyat: {price:.2f} TL\n"
            f"📈 Skor: {score:.1f}/100\n\n"
            f"📝 {reason}\n\n"
            f"⏰ {datetime.now().strftime('%d.%m.%Y %H:%M')}"
        )
        return self.send_message(text)

    def send_sell_signal(self, symbol: str, price: float, score: float, reason: str,
                          in_portfolio: bool = False) -> bool:
        """SAT sinyali gönderir"""
        portfolio_warning = ""
        if in_portfolio:
            portfolio_warning = "\n⚠️ DİKKAT: Bu hisse portföyünüzde! Satış düşünün!\n"

        text = (
            f"🔴🔴 GÜÇLÜ SAT SİNYALİ\n\n"
            f"📊 Hisse: {symbol}\n"
            f"💰 Fiyat: {price:.2f} TL\n"
            f"📉 Skor: {score:.1f}/100\n"
            f"{portfolio_warning}\n"
            f"📝 {reason}\n\n"
            f"⏰ {datetime.now().strftime('%d.%m.%Y %H:%M')}"
        )
        return self.send_message(text)

    def send_portfolio_alert(self, symbol: str, message: str) -> bool:
        """Portföy uyarısı gönderir"""
        text = (
            f"⚠️ PORTFÖY UYARISI\n\n"
            f"📊 {symbol}\n"
            f"{message}\n\n"
            f"⏰ {datetime.now().strftime('%d.%m.%Y %H:%M')}"
        )
        return self.send_message(text)

    def _strip_html(self, text: str) -> str:
        """HTML etiketlerini temizler (WhatsApp düz metin kullanır)"""
        import re
        clean = re.sub(r'<[^>]+>', '', text)
        # Çoklu boşlukları temizle
        clean = re.sub(r'\n{3,}', '\n\n', clean)
        return clean.strip()
