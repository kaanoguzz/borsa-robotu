"""
BIST 100 Bulut Tarayıcı — TAM ANALİZ MODU

2 yıllık geçmiş + Teknik Analiz (15 indikatör) + ML Tahmin + Haberler + Makro
Hedef fiyat + Stop Loss hesaplar.
AL sinyali bulursa Telegram'dan bildirim gönderir.

GitHub Actions üzerinde her 15 dk'da bir otomatik çalışır.
"""

import os
import sys
import logging
import requests
from datetime import datetime, timezone, timedelta

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
        logger.warning("Telegram token/chat_id yok")
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
    now = datetime.now(TZ_TR)
    if now.weekday() >= 5:
        return False
    if now.hour < 10 or now.hour >= 18:
        return False
    return True


# ==================== HEDEF FİYAT HESAPLA ====================
def calculate_targets(symbol: str, result: dict) -> dict:
    """Teknik verileri kullanarak hedef fiyat ve stop loss hesapla"""
    price = result.get("current_price", 0)
    if price == 0:
        return {"target": 0, "stop": 0, "risk_reward": 0}

    tech = result.get("technical_analysis", {})

    # 1. ATR bazlı target/stop (en güvenilir)
    atr_data = tech.get("atr", {})
    atr = atr_data.get("atr", price * 0.02)  # fallback %2

    # 2. Fibonacci direnci
    fib = tech.get("fibonacci", {})
    fib_resistance = None
    nearest_res = fib.get("nearest_resistance", {})
    if nearest_res:
        fib_resistance = nearest_res.get("price", 0)

    # 3. Pivot direnci
    sr = tech.get("support_resistance", {})
    r1 = sr.get("resistance_1", 0)
    r2 = sr.get("resistance_2", 0)
    s1 = sr.get("support_1", 0)

    # 4. Bollinger üst bant
    bb = tech.get("bollinger", {})
    bb_upper = bb.get("upper", 0)

    # Hedef fiyat: Fibonacci direnci, R1, Bollinger üst bandı arasından en mantıklısı
    targets = []
    if fib_resistance and fib_resistance > price * 1.01:
        targets.append(fib_resistance)
    if r1 and r1 > price * 1.01:
        targets.append(r1)
    if r2 and r2 > price * 1.02:
        targets.append(r2)
    if bb_upper and bb_upper > price * 1.01:
        targets.append(bb_upper)

    # ATR bazlı default target (2x ATR yukarı)
    atr_target = price + (atr * 2)
    targets.append(atr_target)

    # En muhafazakar hedefi seç (ilk direnç)
    target = min(targets) if targets else atr_target

    # Stop loss: S1 veya 1.5x ATR aşağı
    stops = []
    if s1 and s1 < price * 0.99:
        stops.append(s1)
    stops.append(price - (atr * 1.5))

    stop = max(stops) if stops else price - (atr * 1.5)

    # Risk/Reward
    risk = price - stop
    reward = target - price
    rr = round(reward / risk, 2) if risk > 0 else 0

    # Yüzde hesapla
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


# ==================== ANA TARAMA ====================
def run_cloud_scan():
    now_tr = datetime.now(TZ_TR)
    logger.info(f"Tarama baslatiliyor: {now_tr.strftime('%d.%m.%Y %H:%M')} (TR)")

    if not is_market_hours():
        logger.info("Borsa kapali - tarama atlaniyor")
        return

    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    try:
        from signal_generator import SignalGenerator
        from data_collector import DataCollector
        from config import BIST100_TICKERS
        from portfolio import PortfolioManager
        import yfinance as yf
    except ImportError as e:
        logger.error(f"Modul import hatasi: {e}")
        sys.exit(1)

    sg = SignalGenerator()
    dc = DataCollector()
    pm = PortfolioManager()

    # ==================== OTO-SAT KONTROLÜ ====================
    holdings = pm.get_portfolio()
    auto_sell_messages = []
    
    if holdings:
        logger.info(f"Oto-Sat kontrolu yapiliyor ({len(holdings)} hisse)...")
        symbols_to_check = [h["symbol"] for h in holdings]
        if symbols_to_check:
            try:
                # Toplu fiyat çekimi
                data = yf.download(symbols_to_check, period="1d", group_by="ticker", progress=False)
                
                for h in holdings:
                    sym = h["symbol"]
                    qty = h["quantity"]
                    
                    if qty <= 0:
                        continue
                        
                    # Yfinance multiple vs single ticker yapısal farkını düzelt
                    if len(symbols_to_check) == 1:
                        current_price = data["Close"].iloc[-1]
                    else:
                        current_price = data[sym]["Close"].iloc[-1]
                        
                    target = h.get("target_price", 0)
                    stop = h.get("stop_loss", 0)
                    buy_price = h.get("avg_buy_price", 0)
                    
                    sell_reason = ""
                    if target > 0 and current_price >= target:
                        sell_reason = f"🎯 Hedef fiyata ulasti ({target} TL)"
                    elif stop > 0 and current_price <= stop:
                        sell_reason = f"🛑 Stop loss seviyesine indi ({stop} TL)"
                    else:
                        from scanner import Scanner
                        sc = Scanner()
                        tech_sell_signal, tech_sell_reason = sc.check_sell_condition(sym)
                        if tech_sell_signal:
                            sell_reason = f"📉 Aktif Defans Sinyali: {tech_sell_reason}"
                        
                    if sell_reason:
                        # Satış işlemi
                        result = pm.remove_stock(sym, qty, current_price, reason=sell_reason)
                        if result["success"]:
                            # Parayı bakiyeye ekle
                            pm.update_balance(result["sell_value"])
                            profit = result["profit_loss"]
                            emoji = "📈" if profit > 0 else "📉"
                            msg = (
                                f"🤖 <b>OTO-SAT GERÇEKLEŞTİ</b>\n\n"
                                f"📦 #{sym} — {qty} adet satildi.\n"
                                f"💰 Fiyat: {current_price:.2f} TL\n"
                                f"📝 Neden: {sell_reason}\n"
                                f"{emoji} Kâr/Zarar: {profit:+.2f} TL"
                            )
                            auto_sell_messages.append(msg)
                            logger.info(f"OTO-SAT: {sym} satildi. Neden: {sell_reason}")
            except Exception as e:
                logger.error(f"Oto-sat kontrolunde hata: {e}")

    buy_signals = []
    sell_signals = []
    all_analyzed = 0

    total = len(BIST100_TICKERS)
    logger.info(f"Toplam {total} hisse taranacak (TAM ANALİZ MODU - 2 yil gecmis)")

    for i, symbol in enumerate(BIST100_TICKERS):
        try:
            # TAM ANALİZ: quick_mode=False → ML + Sosyal + Temel analiz dahil
            # skip_backtest=True → hız için (zaten bulutta veri yeterli olmayabilir)
            result = sg.analyze_stock(symbol, skip_backtest=True, quick_mode=False)
            if not result:
                continue

            all_analyzed += 1
            signal = result.get("signal", {})
            action = signal.get("action", "TUT")
            score = result.get("overall_score", 50)
            price = result.get("current_price", 0)
            reason = signal.get("reason", "")

            if "AL" in action and score >= 55:
                # Hedef fiyat hesapla
                targets = calculate_targets(symbol, result)

                buy_signals.append({
                    "symbol": symbol,
                    "action": action,
                    "score": score,
                    "price": price,
                    "reason": reason,
                    "target": targets["target"],
                    "target_pct": targets["target_pct"],
                    "stop": targets["stop"],
                    "stop_pct": targets["stop_pct"],
                    "risk_reward": targets["risk_reward"],
                    "technical_score": result.get("technical_score", 0),
                    "ml_score": result.get("ml_score", 0),
                    "news_score": result.get("news_score", 0),
                    "social_score": result.get("social_score", 0),
                    "macro_score": result.get("macro_score", 0),
                    "fundamental_score": result.get("fundamental_score", 0),
                })
                logger.info(f"[{i+1}/{total}] {symbol}: {action} Skor:{score:.0f} Hedef:{targets['target']:.2f}")

            elif "SAT" in action and score <= 40:
                sell_signals.append({
                    "symbol": symbol, "action": action, "score": score,
                    "price": price, "reason": reason,
                })
                logger.info(f"[{i+1}/{total}] {symbol}: {action} Skor:{score:.0f}")
            else:
                if (i + 1) % 20 == 0:
                    logger.info(f"[{i+1}/{total}] ilerleme...")

        except Exception as e:
            logger.error(f"{symbol} hatasi: {e}")

    # ==================== SONUÇLAR ====================
    logger.info(f"Tarama bitti: {all_analyzed} analiz, {len(buy_signals)} AL, {len(sell_signals)} SAT")

    # ===== AL SİNYALLERİ =====
    if buy_signals:
        buy_signals.sort(key=lambda x: x["score"], reverse=True)

        msg = f"🚀 <b>BIST 100 — {len(buy_signals)} AL SİNYALİ</b>\n"
        msg += f"📅 {now_tr.strftime('%d.%m.%Y %H:%M')}\n"
        msg += f"📊 {all_analyzed} hisse analiz edildi (2 yıl geçmiş + ML + Teknik)\n"
        msg += "━━━━━━━━━━━━━━━━━━━━\n\n"

        for s in buy_signals[:8]:
            rr_emoji = "🟢" if s["risk_reward"] >= 2 else ("🟡" if s["risk_reward"] >= 1 else "🔴")

            msg += f"🟢 <b>#{s['symbol']} — {s['action']}</b>\n"
            msg += f"   💰 Giriş: <b>{s['price']:.2f} TL</b>\n"
            msg += f"   🎯 Hedef: <b>{s['target']:.2f} TL</b> (+%{s['target_pct']})\n"
            msg += f"   🛑 Stop: {s['stop']:.2f} TL ({s['stop_pct']}%)\n"
            msg += f"   {rr_emoji} Risk/Ödül: {s['risk_reward']}x\n"
            msg += f"   📊 Skor: {s['score']:.0f} (Tek:{s['technical_score']:.0f} ML:{s['ml_score']:.0f} Haber:{s['news_score']:.0f})\n"
            msg += f"   📝 {s['reason'][:55]}\n\n"

        if len(buy_signals) > 8:
            msg += f"... ve {len(buy_signals) - 8} hisse daha.\n\n"

        msg += "⚡ <i>Bulut Tarayıcı — Bilgisayar kapalıyken çalışır</i>"
        send_telegram(msg)

        # ==================== OTO-AL İŞLEMİ ====================
        balance = pm.get_balance()
        if balance > 0:
            # En iyi hisseyi seç (Skor'a göre ilk sıradaki, çünkü yukarıda sort edildi)
            best = buy_signals[0]
            price = best["price"]
            
            # Alınabilecek maksimum adet
            qty = int(balance / price)
            
            if qty > 0:
                cost = qty * price
                # Bakiyeden düş ve portföye ekle
                pm.update_balance(-cost)
                pm.add_stock(best["symbol"], qty, price, 
                             target_price=best["target"], 
                             stop_loss=best["stop"], 
                             notes="Otomatik Alım")
                
                oto_al_msg = (
                    f"🤖 <b>OTO-ALIM GERÇEKLEŞTİ</b>\n\n"
                    f"📦 #{best['symbol']} — {qty} adet alindi.\n"
                    f"💰 Fiyat: {price:.2f} TL\n"
                    f"💵 Odenen: {cost:.2f} TL\n"
                    f"🎯 Hedef: {best['target']:.2f} TL | 🛑 Stop: {best['stop']:.2f} TL\n"
                    f"💼 Kalan Bakiye: {pm.get_balance():.2f} TL"
                )
                send_telegram(oto_al_msg)
            else:
                logger.info(f"OTO-AL yapilamadi. Bakiye ({balance:.2f} TL), {best['symbol']} ({price:.2f} TL) almaya yetmiyor.")

    # Oto-Sat bildirimlerini gönder
    for m in auto_sell_messages:
        send_telegram(m)

    # ===== SAT SİNYALLERİ =====
    if sell_signals:
        sell_signals.sort(key=lambda x: x["score"])
        msg = f"🔴 <b>BIST 100 — {len(sell_signals)} SAT SİNYALİ</b>\n"
        msg += f"📅 {now_tr.strftime('%d.%m.%Y %H:%M')}\n\n"
        for s in sell_signals[:5]:
            msg += f"🔴 <b>#{s['symbol']}</b> — Skor: {s['score']:.0f} | {s['price']:.2f} TL\n"
            msg += f"   📝 {s['reason'][:55]}\n\n"
        send_telegram(msg)

    # ===== GÜNLÜK RAPOR (saat 10:00) =====
    if not buy_signals and not sell_signals:
        if now_tr.hour == 10 and now_tr.minute < 20:
            send_telegram(
                f"🛡️ <b>NAKİTTE KAL</b>\n\n"
                f"📅 {now_tr.strftime('%d.%m.%Y %H:%M')}\n"
                f"🔍 {all_analyzed} hisse tarandı (Tam Analiz)\n"
                f"Güvenli AL sinyali veren hisse bulunamadı.\n\n"
                f"<i>Tarayıcı aktif — sinyal gelince otomatik bildirim alacaksın.</i>"
            )
        else:
            logger.info("Sinyal yok, sessiz kaliniyor")


if __name__ == "__main__":
    run_cloud_scan()
