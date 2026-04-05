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

    def send_buy_signal(self, symbol, current_price, target_price, stop_price, onay_notu):
        mesaj = f"""🟢 <b>ALIM SİNYALİ (Sadece 6/6 Tam Onayda Gönderilir)</b>
<b>{symbol}</b> - AL
💰 <b>Anlık Fiyat:</b> {current_price:.2f} TL
🎯 <b>Hedef Fiyat:</b> {target_price:.2f} TL
🛑 <b>Zarar Kes:</b> {stop_price:.2f} TL

{onay_notu}
(Not: Bu mesaj sadece tüm parametreler onaylandığında düşer.)"""
        return self.send_message(mesaj)

    def send_sell_signal(self, symbol, fiyat, tahmini_dip, bozulan_parametreler, guncel_bakiye=200, kar_zarar=0):
        ilerleme = min(100, (guncel_bakiye / 100000) * 100)
        mesaj = f"""🔴 <b>SATIŞ SİNYALİ (Düşüş Tahmini ve Bozulma Raporu)</b>
<b>{symbol}</b> - SAT
📉 <b>Satış Fiyatı:</b> {fiyat:.2f} TL
🔻 <b>Tahmini Dip:</b> {tahmini_dip:.2f} TL
📈 <b>Kâr/Zarar:</b> {kar_zarar:+.2f} TL

❌ <b>Bozulan Parametreler:</b>
{bozulan_parametreler}

🏁 <b>HEDEF TAKİBİ:</b>
200 TL -> 100.000 TL yolunda bakiye: <b>{guncel_bakiye:.2f} TL</b> (<b>%{ilerleme:.2f}</b> tamamlandı)"""
        return self.send_message(mesaj)

    def send_analysis_report(self, data: dict):
        """Hisse analiz raporunu gönderir"""
        symbol = data.get("symbol", "N/A")
        price = data.get("price", 0)
        score = data.get("overall_score", 0)
        reason = data.get("reason", "Veri yok")
        
        emoji = "🟢" if score > 70 else "🟡" if score > 50 else "🔴"
        
        mesaj = f"""{emoji} <b>{symbol} - ANLIK ANALİZ RAPORU</b>
💰 <b>Fiyat:</b> {price:.2f} TL
📊 <b>Güven Skoru:</b> %{score:.1f}

🧠 <b>Botun Yorumu:</b>
<i>{reason}</i>

📈 <b>Teknik Detaylar:</b>
• Hedef: {data.get('target', 0):.2f} TL
• Stop: {data.get('stop', 0):.2f} TL
• RSI: {data.get('rsi', 0):.1f}
• Trend: {data.get('trend', 'Belirsiz')}

🔍 <i>Bu analiz 15 indikatör ve güncel haberler taranarak oluşturulmuştur.</i>"""
        return self.send_message(mesaj)

    def send_market_pulse(self, data: dict):
        """Borsa genel durum (Endeks Nabız) raporu"""
        price = data.get("price", 0)
        change = data.get("change", 0)
        risk = data.get("risk_level", "DÜŞÜK")
        
        emoji = "🛡️" if "DÜŞÜK" in risk else "⚠️" if "ORTA" in risk else "🚨"
        
        mesaj = f"""{emoji} <b>BIST 100 - ENDEKS NABIZ RAPORU</b>
📈 <b>XU100 Değeri:</b> {price:.2f}
📉 <b>Günlük Değişim:</b> {change:+.2f}%
📊 <b>Şelale Riski:</b> {risk}

📝 <b>Durum Analizi:</b>
{data.get('comment', 'Piyasada normal seyir devam ediyor.')}

🔍 <i>Haftalık %70 kâr hedefi için piyasa yönü takibindedir.</i>"""
        return self.send_message(mesaj)

    def get_updates(self, offset=None):
        """Yeni mesajları getirir"""
        url = f"https://api.telegram.org/bot{self.token}/getUpdates"
        params = {"timeout": 10, "offset": offset}
        try:
            response = requests.get(url, params=params, timeout=15)
            if response.status_code == 200:
                return response.json().get("result", [])
            return []
        except Exception as e:
            logger.error(f"Telegram update hatası: {e}")
            return []
