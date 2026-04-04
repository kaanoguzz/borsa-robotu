import os
import requests
import logging
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

logger = logging.getLogger(__name__)

class Notifier:
    def __init__(self):
        self.token = TELEGRAM_TOKEN
        self.chat_id = CHAT_ID
        self.base_url = f"https://api.telegram.org/bot{self.token}/sendMessage"

    def send_message(self, text: str):
        if not self.token or not self.chat_id:
            logger.warning("Telegram token veya chat ID bulunamadı.")
            return False
            
        try:
            payload = {
                "chat_id": self.chat_id,
                "text": text,
                "parse_mode": "HTML"
            }
            response = requests.post(self.base_url, json=payload, timeout=10)
            if response.status_code == 200:
                logger.info("Telegram bildirimi gönderildi.")
                return True
            else:
                logger.error(f"Telegram hatası: {response.text}")
                return False
        except Exception as e:
            logger.error(f"Telegram bağlantı hatası: {e}")
            return False

    def send_buy_signal(self, symbol, guven_skoru, risk_seviyesi, fiyat, hedef_fiyat, stop_fiyat, teknik_ozet, hacim_durumu, duygu_skoru):
        mesaj = f"""🚀 <b>#{symbol} - GÜÇLÜ AL SİNYALİ</b>

📊 <b>Güven Skoru:</b> %{guven_skoru} (AI Onayı)
🛡️ <b>Risk Oranı:</b> {risk_seviyesi}
💰 <b>Giriş:</b> {fiyat:.2f} TL | 🎯 <b>Hedef:</b> {hedef_fiyat:.2f} TL | 🛑 <b>Stop:</b> {stop_fiyat:.2f} TL

🧠 <b>Neden:</b> {teknik_ozet}
• Hacim: {hacim_durumu}
• Duygu: Sosyal Medyada %{duygu_skoru:.0f} pozitif hava.

🏦 <b>Aksiyon:</b> Yapı Kredi'den alımı yap!"""
        return self.send_message(mesaj)

    def send_sell_signal(self, symbol, fiyat, satis_nedeni, kar_zarar_orani, ilerleme_yuzdesi):
        mesaj = f"""⚠️ <b>#{symbol} - ACİL SAT SİNYALİ</b>

💰 <b>Satış Fiyatı:</b> {fiyat:.2f} TL
📉 <b>Neden:</b> {satis_nedeni}
📈 <b>Gerçekleşen Kâr/Zarar:</b> %{kar_zarar_orani:+.2f}

🏁 <b>HEDEF TAKİBİ:</b>
200 TL -> 100.000 TL yolunda <b>%{ilerleme_yuzdesi:.2f}</b> tamamlandı! 
Nakit gücünü koru, yeni sinyali bekle."""
        return self.send_message(mesaj)
