"""
BIST 100 Bulut Tarayıcı — Bilgisayar Kapalıyken Çalışır

GitHub Actions üzerinde her 15 dakikada bir çalışır.
AL sinyali bulursa Telegram'dan bildirim gönderir.
Hiçbir şey bulamazsa sessiz kalır (spam yapmaz).

Kullanım (local test):
  python cloud_scanner.py

Gerekli env variables:
  TELEGRAM_BOT_TOKEN
  TELEGRAM_CHAT_ID
"""

import os
import sys
import logging
import requests
from datetime import datetime, timezone, timedelta

# Türkiye saati
TZ_TR = timezone(timedelta(hours=3))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("cloud_scanner")


# ==================== TELEGRAM ====================
def send_telegram(text: str) -> bool:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        logger.warning("Telegram token/chat_id yok, mesaj yazdiriliyor:")
        print(text)
        return False
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        resp = requests.post(url, json={
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML"
        }, timeout=15)
        if resp.status_code == 200:
            logger.info("Telegram mesaji gonderildi")
            return True
        else:
            logger.error(f"Telegram hata: {resp.text}")
            return False
    except Exception as e:
        logger.error(f"Telegram baglanti hatasi: {e}")
        return False


# ==================== BORSA SAATİ KONTROLÜ ====================
def is_market_hours() -> bool:
    """Borsa İstanbul açık mı? (Hafta içi 10:00-18:00 TR saati)"""
    now = datetime.now(TZ_TR)
    if now.weekday() >= 5:  # Cumartesi-Pazar
        return False
    hour = now.hour
    if hour < 10 or hour >= 18:
        return False
    return True


# ==================== ANA TARAMA ====================
def run_cloud_scan():
    """BIST 100 taraması yap, AL sinyali varsa Telegram'a gönder"""

    now_tr = datetime.now(TZ_TR)
    logger.info(f"Tarama baslatiliyor: {now_tr.strftime('%d.%m.%Y %H:%M')} (TR)")

    # Borsa saati dışındaysa çalışma
    if not is_market_hours():
        logger.info("Borsa kapali - tarama atlanıyor")
        return

    # .env dosyasından yükle (local test için)
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    # Modülleri import et
    try:
        from signal_generator import SignalGenerator
        from config import BIST100_TICKERS
    except ImportError as e:
        logger.error(f"Modul import hatasi: {e}")
        sys.exit(1)

    sg = SignalGenerator()
    buy_signals = []
    sell_signals = []
    errors = []

    total = len(BIST100_TICKERS)
    logger.info(f"Toplam {total} hisse taranacak")

    for i, symbol in enumerate(BIST100_TICKERS):
        try:
            result = sg.analyze_stock(symbol, skip_backtest=True, quick_mode=True)
            if not result:
                continue

            signal = result.get("signal", {})
            action = signal.get("action", "TUT")
            score = result.get("overall_score", 50)
            price = result.get("current_price", 0)
            reason = signal.get("reason", "")

            if "AL" in action:
                buy_signals.append({
                    "symbol": symbol,
                    "action": action,
                    "score": score,
                    "price": price,
                    "reason": reason,
                })
                logger.info(f"[{i+1}/{total}] {symbol}: {action} (Skor: {score:.0f})")
            elif "SAT" in action:
                sell_signals.append({
                    "symbol": symbol,
                    "action": action,
                    "score": score,
                    "price": price,
                    "reason": reason,
                })
                logger.info(f"[{i+1}/{total}] {symbol}: {action} (Skor: {score:.0f})")
            else:
                if (i + 1) % 20 == 0:
                    logger.info(f"[{i+1}/{total}] ilerleme...")

        except Exception as e:
            errors.append(f"{symbol}: {e}")

    # ==================== SONUÇLAR ====================
    logger.info(f"Tarama tamamlandi: {len(buy_signals)} AL, {len(sell_signals)} SAT, {len(errors)} hata")

    # AL sinyali varsa Telegram gönder
    if buy_signals:
        # En yüksek skorlulara göre sırala
        buy_signals.sort(key=lambda x: x["score"], reverse=True)

        header = f"🚀 <b>BIST 100 — {len(buy_signals)} AL SİNYALİ BULUNDU!</b>\n"
        header += f"📅 {now_tr.strftime('%d.%m.%Y %H:%M')}\n\n"

        for s in buy_signals[:10]:  # En fazla 10 tane gönder
            header += (
                f"🟢 <b>#{s['symbol']}</b> — {s['action']}\n"
                f"   💰 {s['price']:.2f} TL | 📊 Skor: {s['score']:.0f}\n"
                f"   📝 {s['reason'][:60]}\n\n"
            )

        if len(buy_signals) > 10:
            header += f"... ve {len(buy_signals) - 10} hisse daha.\n"

        header += "\n⚡ <i>Otomatik Bulut Tarayıcı — Bilgisayar kapalıyken çalışır</i>"
        send_telegram(header)

    # SAT sinyali varsa ayrı mesaj
    if sell_signals:
        sell_signals.sort(key=lambda x: x["score"])
        msg = f"🔴 <b>BIST 100 — {len(sell_signals)} SAT SİNYALİ</b>\n"
        msg += f"📅 {now_tr.strftime('%d.%m.%Y %H:%M')}\n\n"
        for s in sell_signals[:5]:
            msg += f"🔴 <b>#{s['symbol']}</b> — Skor: {s['score']:.0f} | {s['price']:.2f} TL\n"
        send_telegram(msg)

    # Hiçbir şey bulamadıysa günde 1 kere bilgi ver (sadece saat 10:00'da)
    if not buy_signals and not sell_signals:
        if now_tr.hour == 10 and now_tr.minute < 20:
            send_telegram(
                f"🛡️ <b>NAKİTTE KAL</b>\n\n"
                f"📅 {now_tr.strftime('%d.%m.%Y %H:%M')}\n"
                f"BIST 100 tarandı, AL sinyali veren hisse bulunamadı.\n"
                f"Piyasa düşüş trendinde olabilir.\n\n"
                f"<i>Otomatik Bulut Tarayıcı aktif — yeni sinyal gelince bildirim alacaksın.</i>"
            )
        else:
            logger.info("Sinyal yok, sessiz kaliniyor (spam yok)")


if __name__ == "__main__":
    run_cloud_scan()
