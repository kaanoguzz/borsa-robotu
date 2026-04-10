"""
TAM TARAMA TESTİ — Tüm BIST 100 hisselerini tarar ve Telegram'a gönderir.
Saat kontrolü yok, direkt çalışır.
"""

import shutil
import os
import sys
import ssl
import time
import logging

# ===== SSL Fix =====
try:
    import certifi
    _original_cert = certifi.where()
    _safe_cert = os.path.join(os.environ.get('TEMP', '.'), 'cacert.pem')
    shutil.copy2(_original_cert, _safe_cert)
    os.environ['CURL_CA_BUNDLE'] = _safe_cert
    os.environ['SSL_CERT_FILE'] = _safe_cert
    os.environ['REQUESTS_CA_BUNDLE'] = _safe_cert
    certifi.where = lambda: _safe_cert
except Exception:
    pass

try:
    ssl._create_default_https_context = ssl._create_unverified_context
except AttributeError:
    pass

# ===== .env yükle =====
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("test_scan")

import requests
import yfinance as yf
import pandas as pd
from datetime import datetime, timezone, timedelta
from config import BIST100_TICKERS

TZ_TR = timezone(timedelta(hours=3))

def send_telegram(text: str) -> bool:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        logger.warning("Telegram token/chat_id yok!")
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
            logger.error(f"Telegram hata: {resp.status_code} - {resp.text[:200]}")
            return False
    except Exception as e:
        logger.error(f"Telegram baglanti hatasi: {e}")
        return False


def calculate_targets(symbol, result):
    """Hedef fiyat ve stop loss hesapla"""
    price = result.get("current_price", 0)
    if price == 0:
        return {"target": 0, "stop": 0, "risk_reward": 0, "target_pct": 0, "stop_pct": 0, "atr": 0}

    tech = result.get("technical_analysis", {})
    atr_data = tech.get("atr", {})
    atr = atr_data.get("atr", price * 0.02)

    fib = tech.get("fibonacci", {})
    fib_resistance = None
    nearest_res = fib.get("nearest_resistance", {})
    if nearest_res:
        fib_resistance = nearest_res.get("price", 0)

    sr = tech.get("support_resistance", {})
    r1 = sr.get("resistance_1", 0)
    r2 = sr.get("resistance_2", 0)
    s1 = sr.get("support_1", 0)

    bb = tech.get("bollinger", {})
    bb_upper = bb.get("upper", 0)

    targets = []
    if fib_resistance and fib_resistance > price * 1.01:
        targets.append(fib_resistance)
    if r1 and r1 > price * 1.01:
        targets.append(r1)
    if r2 and r2 > price * 1.02:
        targets.append(r2)
    if bb_upper and bb_upper > price * 1.01:
        targets.append(bb_upper)

    atr_target = price + (atr * 2)
    targets.append(atr_target)

    target = min(targets) if targets else atr_target

    stops = []
    if s1 and s1 < price * 0.99:
        stops.append(s1)
    stops.append(price - (atr * 1.5))

    stop = max(stops) if stops else price - (atr * 1.5)

    risk = price - stop
    reward = target - price
    rr = round(reward / risk, 2) if risk > 0 else 0

    target_pct = round(((target - price) / price) * 100, 1)
    stop_pct = round(((stop - price) / price) * 100, 1)

    return {
        "target": round(target, 2),
        "target_pct": target_pct,
        "stop": round(stop, 2),
        "stop_pct": stop_pct,
        "risk_reward": rr,
        "atr": round(atr, 2),
    }


def run_full_test():
    now_tr = datetime.now(TZ_TR)
    
    send_telegram(
        f"🔍 <b>TAM TARAMA TESTİ BAŞLADI</b>\n\n"
        f"📅 {now_tr.strftime('%d.%m.%Y %H:%M')}\n"
        f"🎯 Hedef: %4.5+ potansiyelli, 6/6 kriterli hisseler\n"
        f"📊 Toplam: {len(BIST100_TICKERS)} hisse taranacak\n\n"
        f"<i>Lütfen bekleyiniz efendim...</i>"
    )
    
    logger.info(f"=== TAM TARAMA BAŞLADI: {len(BIST100_TICKERS)} hisse ===")
    
    # 1. TOPLU VERİ ÇEK
    logger.info("Toplu veri indiriliyor (1 yıllık)...")
    yahoo_tickers = [f"{t}.IS" for t in BIST100_TICKERS]
    raw_data = yf.download(yahoo_tickers, period="1y", interval="1d", group_by='ticker', threads=True, progress=False)
    logger.info("Veri indirme tamamlandı.")
    
    # 2. SignalGenerator ile analiz
    from signal_generator import SignalGenerator
    sg = SignalGenerator()
    
    buy_a_class = []  # TKS >= 7
    buy_b_class = []  # TKS < 7
    total_analyzed = 0
    errors = 0
    
    for i, symbol in enumerate(BIST100_TICKERS):
        try:
            yahoo_sym = f"{symbol}.IS"
            try:
                symbol_df = raw_data[yahoo_sym]
                if symbol_df is None or symbol_df.empty:
                    continue
            except (KeyError, TypeError):
                continue
            
            result = sg.analyze_stock(symbol, skip_backtest=True, quick_mode=False, external_df=symbol_df)
            if not result:
                continue
            
            total_analyzed += 1
            
            v2_signal = result.get("v2_signal", {})
            v1_signal = result.get("v1_signal", {})
            score = result.get("overall_score", 50)
            tks = v2_signal.get("quality_score", 0)
            price = result.get("current_price", 0)
            reason = v2_signal.get("reason", "")
            
            # AL SİNYALİ KONTROLÜ
            if (v2_signal.get("passed") or v1_signal.get("passed")) and score >= 55:
                targets = calculate_targets(symbol, result)
                
                if targets["target_pct"] >= 4.5:
                    entry = {
                        "symbol": symbol,
                        "price": price,
                        "score": score,
                        "tks": tks,
                        "target": targets["target"],
                        "target_pct": targets["target_pct"],
                        "stop": targets["stop"],
                        "stop_pct": targets["stop_pct"],
                        "rr": targets["risk_reward"],
                        "reason": reason,
                        "v1": v1_signal.get("passed", False),
                        "v2": v2_signal.get("passed", False),
                        "checklist": result.get("checklist", {}),
                    }
                    
                    if tks >= 7:
                        buy_a_class.append(entry)
                        logger.info(f"🚀 A-SINIFI: {symbol} | TKS: {tks} | Hedef: %{targets['target_pct']}")
                    else:
                        buy_b_class.append(entry)
                        logger.info(f"🥈 B-SINIFI: {symbol} | TKS: {tks} | Hedef: %{targets['target_pct']}")
            
            if (i + 1) % 10 == 0:
                logger.info(f"İlerleme: [{i+1}/{len(BIST100_TICKERS)}] | A: {len(buy_a_class)} | B: {len(buy_b_class)}")
                
        except Exception as e:
            errors += 1
            logger.error(f"{symbol} hata: {e}")
            continue
    
    # 3. SONUÇLARI TELEGRAM'A GÖNDER
    logger.info(f"=== TARAMA BİTTİ: {total_analyzed} analiz, {len(buy_a_class)} A-sınıfı, {len(buy_b_class)} B-sınıfı ===")
    
    # A-Sınıfı Sinyaller
    if buy_a_class:
        buy_a_class.sort(key=lambda x: x["tks"], reverse=True)
        msg = f"🚀🚀 <b>A-SINIFI SİNYALLER (GÜÇLÜ AL)</b>\n"
        msg += f"📅 {now_tr.strftime('%d.%m.%Y %H:%M')}\n\n"
        
        for s in buy_a_class[:5]:
            v_tag = "💎v1+v2" if s["v1"] else "🚀v2"
            msg += f"{'='*30}\n"
            msg += f"<b>#{s['symbol']}</b> — {v_tag}\n"
            msg += f"💰 Fiyat: {s['price']:.2f} TL\n"
            msg += f"🎯 Hedef: {s['target']:.2f} TL (<b>%{s['target_pct']:+.1f}</b>)\n"
            msg += f"🛑 Stop: {s['stop']:.2f} TL (%{s['stop_pct']:.1f})\n"
            msg += f"📊 TKS: <b>{s['tks']}/10</b> | Skor: %{s['score']:.0f}\n"
            msg += f"⚖️ Risk/Ödül: {s['rr']}x\n"
            msg += f"📝 <i>{s['reason']}</i>\n\n"
        
        msg += f"💪 <b>Bu sinyaller FULL GİRİLEBİLİR kalitededir.</b>"
        send_telegram(msg)
    
    # B-Sınıfı Sinyaller
    if buy_b_class:
        buy_b_class.sort(key=lambda x: x["target_pct"], reverse=True)
        msg = f"🥈 <b>B-SINIFI FIRSATLAR (DİKKATLİ AL)</b>\n"
        msg += f"📅 {now_tr.strftime('%d.%m.%Y %H:%M')}\n\n"
        
        for s in buy_b_class[:5]:
            v_tag = "💎v1+v2" if s["v1"] else "🚀v2"
            msg += f"<b>#{s['symbol']}</b> — {v_tag}\n"
            msg += f"💰 {s['price']:.2f} TL → 🎯 {s['target']:.2f} TL (<b>%{s['target_pct']:+.1f}</b>)\n"
            msg += f"📊 TKS: {s['tks']}/10 | Stop: {s['stop']:.2f} TL\n\n"
        
        msg += f"⚠️ <i>Küçük lotlarla denenebilir.</i>"
        send_telegram(msg)
    
    # Hiç sinyal yoksa
    if not buy_a_class and not buy_b_class:
        send_telegram(
            f"🛡️ <b>NAKİTTE KAL</b>\n\n"
            f"📅 {now_tr.strftime('%d.%m.%Y %H:%M')}\n"
            f"🔍 {total_analyzed} hisse 6 faktörle tarandı\n"
            f"❌ %4.5+ hedefli güvenli AL sinyali bulunamadı.\n\n"
            f"<i>Piyasa şartları uygun değil — sabırlı ol efendim.</i>"
        )
    
    # ÖZET RAPOR
    summary = (
        f"📊 <b>TARAMA ÖZETİ</b>\n\n"
        f"📈 Toplam Taranan: {total_analyzed}\n"
        f"🚀 A-Sınıfı (TKS≥7): {len(buy_a_class)}\n"
        f"🥈 B-Sınıfı (TKS<7): {len(buy_b_class)}\n"
        f"❌ Hata: {errors}\n"
        f"⏱ Süre: {time.time():.0f}s\n\n"
        f"<i>6 Kriter: Hacim ✓ Teknik ✓ Makro ✓ AKD ✓ Haber ✓ Duygu ✓</i>"
    )
    send_telegram(summary)
    
    logger.info("Test tamamlandı!")


if __name__ == "__main__":
    start = time.time()
    try:
        run_full_test()
    except Exception as e:
        import traceback
        error_msg = f"❌ <b>TEST HATASI</b>\n\n{str(e)[:300]}"
        send_telegram(error_msg)
        logger.error(f"Kritik hata:\n{traceback.format_exc()}")
    
    elapsed = time.time() - start
    logger.info(f"Toplam süre: {elapsed:.0f} saniye")
