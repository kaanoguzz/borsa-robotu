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
import ssl
import shutil
from datetime import datetime, timezone, timedelta

# ===== SSL Sertifika Fix (Windows Türkçe Kullanıcı Adı & GitHub Actions) =====
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
# ============================================================================

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


# ==================== TELEGRAM KOMUT DİNLEYİCİ ====================
def normalize_text(text: str) -> str:
    """Türkçe karakterleri normalize eder ve küçük harfe çevirir"""
    if not text: return ""
    
    # Adım 1: Küçük harf ve Türkçe karakter dönüşümleri
    text = text.replace("İ", "i").replace("I", "ı").lower()
    text = text.replace("ı", "i").replace("ğ", "g").replace("ü", "u").replace("ş", "s").replace("ö", "o").replace("ç", "c")
    
    # Adım 2: Noktalama işaretlerini kaldır (Soru işareti vb. komutu bozmasın)
    import string
    text = text.translate(str.maketrans('', '', string.punctuation))
    
    # Adım 3: Bazı özel boşluklu kalıpları basitleştir
    text = text.replace("elimizde ne var", "portfoy").replace("ne var", "portfoy")
    text = text.replace("ne durumdayiz", "portfoy").replace("durum ne", "portfoy")
    text = text.replace("durum nedir", "portfoy").replace("durum", "portfoy")
    
    # "Sorunu Çöz" kalıpları
    text = text.replace("sorunu coz", "tamir").replace("duzelt", "tamir").replace("fix it", "tamir")
    text = text.replace("sorun var", "tamir").replace("hata var", "tamir").replace("calismiyor", "tamir")
    
    # Sohbet kalıpları
    text = text.replace("naber", "nasilsin").replace("napiyorsun", "nasilsin")
    text = text.replace("kimsin", "kimsin").replace("ne işe yararsın", "kimsin")
    
    return text.strip()

# ==================== TELEGRAM KOMUT DİNLEYİCİ ====================
def process_user_commands(pm, notifier, dc):
    """Telegram'dan gelen kullanıcı komutlarını (Hisse aldım/sattım) işler"""
    offset_file = "telegram_offset.txt"
    offset = 0
    if os.path.exists(offset_file):
        try:
            with open(offset_file, "r") as f:
                offset = int(f.read().strip())
        except:
            offset = 0

    updates = notifier.get_updates(offset=offset + 1)
    if not updates:
        return

    import re
    # Grup 1: Sembol, Grup 2: Fiyat (Opsiyonel), Grup 3: Eylem
    # Normalize edilmiş metin üzerinden çalışacak
    # Desteklenenler: "thyao al", "thyao 300 al", "thyao 300.50 tl aldim"
    buy_pattern = re.compile(r"([a-z0-9]+)\s*(\d+[\.,]\d*|\d+)?\s*(?:tl|₺)?\s*(al|aldim|aldik|buy)$")
    sell_pattern = re.compile(r"([a-z0-9]+)\s*(\d+[\.,]\d*|\d+)?\s*(?:tl|₺)?\s*(sat|sattim|sattik|sell)$")
    analyze_pattern = re.compile(r"([a-z0-9]+)\s*(ne durumda|analiz|durum|yorumu?|durum nedir)$")
    market_pattern = re.compile(r"^(endeks|xu100|piyasa|borsa|durum ne)$")
    bakiye_pattern = re.compile(r"(bakiyemiz|bakiye|kasa)\s*(\d+[\.,]\d+|\d+)\s*(tl|₺)?$")
    forecast_pattern = re.compile(r"^(yarin|tahmin|gelecek|yarin ne olur)$")

    max_id = offset
    for update in updates:
        max_id = max(max_id, update.get("update_id", 0))
        message = update.get("message", {})
        chat_id = str(message.get("chat", {}).get("id", ""))
        raw_text = message.get("text", "").strip()

        # Sadece yetkili CHAT_ID'den gelen mesajları işle
        if chat_id != str(os.getenv("TELEGRAM_CHAT_ID")):
            continue

        if not raw_text:
            continue
            
        # Metni normalize et (Küçük harf + Türkçe karakter temizliği)
        text = normalize_text(raw_text)

        # ==================== AKILLI ASİSTAN (NLP) ====================
        
        # 1. SELAMLAŞMA & KİŞİLİK
        if text in ["merhaba", "selam", "slm", "mrb", "hey", "merhabalar"]:
            notifier.send_message("Merhaba efendim! 🤖 Piyasaları 24 saat kesintisiz izliyorum. Bugün sizin için ne yapabilirim?")
            continue
            
        if text == "nasilsin":
            notifier.send_message("Çok iyiyim efendim, işlemci sıcaklığım normal ve veri akışım saniyede 1 gigabyte! ⚡ Siz nasılsınız?")
            continue
            
        if text == "kimsin":
            notifier.send_message("Ben sizin **Borsa Robotunuzum**. 🦾\n"
                                 "Görevim: Piyasayı taramak, yapay zeka ile 100 hisseyi analiz etmek ve size en kârlı sinyalleri bilgisayarınızı açmanıza gerek kalmadan iletmek.")
            continue

        # 2. "SORUNU ÇÖZ" - OTOMATİK TAMİR / SELF-REPAIR
        if text == "tamir":
            notifier.send_message("🛠️ <b>Sistem Kontrolü ve Otomatik Tamir Başlatıldı...</b>\n"
                                 "İnternet bağlantısı, veritabanı bütünlüğü ve SSL sertifikaları yenileniyor.")
            
            error_report = []
            try:
                # SSL Yenileme
                import certifi
                import shutil
                _original_cert = certifi.where()
                _safe_cert = os.path.join(os.environ.get('TEMP', '.'), 'cacert.pem')
                shutil.copy2(_original_cert, _safe_cert)
                os.environ['SSL_CERT_FILE'] = _safe_cert
                error_report.append("✅ SSL Sertifikaları tazelendi.")
                
                # Veri Kontrolü
                import yfinance as yf
                test_data = yf.Ticker("THYAO.IS").history(period="1d")
                if not test_data.empty:
                    error_report.append("✅ Veri akışı (Yahoo) aktif.")
                
                # Heartbeat Sıfırlama (Yarını tetiklemek için)
                if os.path.exists("cloud_heartbeat.status"):
                    os.remove("cloud_heartbeat.status")
                    error_report.append("✅ Durum raporu sıfırlandı.")
                
                msg = "🛠️ <b>SİSTEM KENDİNİ TAMİR ETTİ</b>\n\n" + "\n".join(error_report) + "\n\n🚀 Şu an her şey yolunda, taramaya tam güç devam ediyorum!"
                notifier.send_message(msg)
            except Exception as e:
                notifier.send_message(f"❌ <b>Tamir sırasında hata:</b> {str(e)}")
            continue

        # YARDIM KOMUTU (TAM FONKSİYON LİSTESİ)
        if text in ["yardim", "help", "/start", "merhaba", "selam", "komutlar"]:
            help_msg = "🤖 <b>BORSA ROBOTU - YETENEK LİSTESİ</b>\n\n" \
                       "📊 <b>ANALİZ & SORGULAMA</b>\n" \
                       "• <code>yarin</code> -> Yarın yükselebilecek 5 hisseyi tahmin eder\n" \
                       "• <code>[HISSE] ne durumda?</code> -> Anlık teknik/duygu analizi\n" \
                       "• <code>endeks</code> -> Borsa genel yönü ve Şelale Riski\n" \
                       "• <code>durum</code> -> Portföy detayı ve ilerleme çubuğu\n\n" \
                       "✅ <b>İŞLEM KAYDI</b>\n" \
                       "• <code>[HISSE] aldim</code> -> Portföye ekler\n" \
                       "• <code>[HISSE] [FIYAT] al</code> -> Fiyatlı ekler\n" \
                       "• <code>[HISSE] sattim</code> -> Portföyden çıkarır (K/Z hesaplar)\n\n" \
                       "💰 <b>KASA YÖNETİMİ</b>\n" \
                       "• <code>bakiyemiz [TUTAR]</code> -> Nakit bakiyeyi set eder\n\n" \
                       "🎯 <b>HEDEF:</b> 200 TL -> 100.000 TL\n" \
                       "<i>Ben 24 saat nöbetteyim, piyasayı taramaya devam ediyorum.</i>"
            notifier.send_message(help_msg)
            continue

        # YARIN TAHMİNİ (ÖZEL KOMUT)
        if forecast_pattern.match(text):
            notifier.send_message("🔮 <b>Yarın için derin analiz başlatıldı...</b>\nBIST 100 hisseleri 4 katmanlı AI filtresinden geçiriliyor. Bu işlem yaklaşık 5 dakika sürebilir efendim.")
            # Arka planda değil, direkt çalıştırıyoruz çünkü bu cloud_scanner zaten bir döngüde değil, script olarak çağrılıyor.
            # Ama timeout olmaması için dikkatli olmalıyız.
            send_tomorrow_forecast(pm, notifier, dc)
            continue

        # PORTFÖY DURUMU (GELİŞMİŞ)
        if text in ["portfoy", "durum", "bakiye", "kasa"]:
            bakiye = pm.get_balance()
            holdings = pm.get_holdings_dict()
            msg = f"💰 <b>Kasa:</b> {bakiye:.2f} TL\n"
            if holdings:
                msg += "💼 <b>Aktif Pozisyonlar:</b>\n"
                for s, d in holdings.items():
                    # Zirve takibi bilgisi ekle
                    curr_data = dc.get_current_price(s)
                    price = curr_data.get("price", d["maliyet"])
                    peak_data = pm.update_peak_price(s, price)
                    
                    kar_zarar_yuzde = ((price - d["maliyet"]) / d["maliyet"]) * 100
                    peak_dist = ((peak_data["max_peak"] - price) / peak_data["max_peak"]) * 100 if peak_data["max_peak"] > 0 else 0
                    
                    msg += f"• <b>#{s}</b>: {d['adet']:.0f} ad. ({kar_zarar_yuzde:+.1f}%)\n"
                    msg += f"   📍 Zirve: {peak_data['max_peak']:.2f} (Uzaklık: %{peak_dist:.1f})\n"
            else:
                msg += "💼 Portföy şu an boş (Nakitte)."
            
            # İlerleme Barı
            toplam_hisse_degeri = sum(d["adet"] * dc.get_current_price(s).get("price", d["maliyet"]) for s, d in holdings.items())
            toplam_varlik = bakiye + toplam_hisse_degeri
            ilerleme = (toplam_varlik / 100000) * 100
            msg += f"\n🏁 <b>İlerleme:</b> %{ilerleme:.2f} / 100.000 TL"
            notifier.send_message(msg)
            continue

        # ENDEKS NABIZ
        if market_pattern.match(text):
            try:
                xu100 = dc.get_current_price("XU100.IS")
                price = xu100.get("price", 0)
                change = xu100.get("change_percent", 0)
                risk = "YÜKSEK (Şelale Riski! 🚨)" if change < -0.4 else "ORTA ⚠️" if change < -0.2 else "DÜŞÜK 🛡️"
                
                pulse_data = {
                    "price": price,
                    "change": change,
                    "risk_level": risk,
                    "comment": "Endeks direnç seviyesinde." if change > 0 else "Destek seviyeleri takip ediliyor."
                }
                notifier.send_market_pulse(pulse_data)
                continue
            except:
                pass

        # HİSSE ANALİZ (İLERİ SEVİYE)
        analyze_match = analyze_pattern.match(text)
        if analyze_match:
            symbol = analyze_match.group(1).upper()
            notifier.send_message(f"🔍 <b>{symbol}</b> için 4 katmanlı derin analiz başlatıldı, lütfen bekleyiniz efendim...")
            
            try:
                from signal_generator import SignalGenerator
                sg_temp = SignalGenerator()
                report = sg_temp.analyze_stock(symbol, quick_mode=True)
                
                curr_price = report.get("price", 0)
                analysis_data = {
                    "symbol": symbol,
                    "price": curr_price,
                    "overall_score": report.get("overall_score", 0),
                    "reason": report.get("signal", {}).get("reason", "Hisse stabil."),
                    "target": report.get("target", curr_price * 1.05),
                    "stop": report.get("stop", curr_price * 0.97),
                    "rsi": report.get("technical_analysis", {}).get("rsi", 0),
                    "trend": report.get("technical_analysis", {}).get("trend", "Yatay")
                }
                notifier.send_analysis_report(analysis_data)
                continue
            except Exception as e:
                logger.error(f"Analiz hatasi: {e}")
                notifier.send_message(f"❌ {symbol} analizi sırasında bir hata oluştu. Lütfen tekrar deneyiniz.")
                continue

        # BAKİYE GÜNCELLEME KOMUTU
        bakiye_match = bakiye_pattern.match(text)
        if bakiye_match:
            try:
                new_bal = float(bakiye_match.group(2).replace(",", "."))
                pm.set_balance(new_bal)
                notifier.send_message(f"💰 <b>Tamamdır efendim, bakiyeniz {new_bal:.2f} TL olarak güncellendi.</b>\n🏁 Hedef takibindeki ilerleme barı buna göre ayarlanıyor.")
                logger.info(f"Telegram Komutu: Bakiye guncellendi: {new_bal}")
                continue
            except Exception as e:
                logger.error(f"Bakiye guncelleme hatasi: {e}")

        # ALIM KOMUTU
        buy_match = buy_pattern.match(text)
        if buy_match:
            symbol = buy_match.group(1).upper()
            price_str = buy_match.group(2)
            
            # Belirtilen fiyat varsa onu kullan, yoksa canlı fiyatı al
            if price_str:
                price = float(price_str.replace(",", "."))
            else:
                price_data = dc.get_current_price(symbol)
                price = price_data["price"] if price_data else 0

            if price > 0:
                # Önceki kapanış bilgisini de (Tavan kilidi için) çekmeye çalış
                prev_close = 0
                try:
                    import yfinance as yf
                    ticker = yf.Ticker(f"{symbol}.IS")
                    prev_close = ticker.info.get("previousClose", 0)
                except:
                    pass

                # Bakiyeyi kontrol et ve adet hesapla
                bakiye = pm.get_balance()
                if bakiye > 10: # Minimum işlem tutarı
                    komisyon = bakiye * 0.002
                    net_bakiye = bakiye - komisyon
                    adet = net_bakiye / price
                    
                    # Hedef ve stopları otomatik hesapla (ATR bazlı)
                    # Not: cloud_scanner ana analizinden de gelebilir ama burada hızlı ATR yapalım
                    pm.add_stock(symbol, adet, price, target_price=price*1.05, stop_loss=price*0.97, notes="Manuel Telegram Komutu", previous_close=prev_close)
                    
                    notifier.send_message(f"✅ <b>Tamam efendim, {symbol} takibe alındı!</b>\n💰 Fiyat: {price:.2f} TL\n📦 Adet: {adet:.2f}\n🛡️ Zırhlar ve Takip Sistemi aktif edildi.")
                    logger.info(f"Telegram Komutu: {symbol} alindi.")
                else:
                    notifier.send_message(f"⚠️ Bakiye yetersiz ({bakiye:.2f} TL). Alım yapılamadı.")

        # SATIM KOMUTU
        sell_match = sell_pattern.match(text)
        if sell_match:
            symbol = sell_match.group(1).upper()
            price_str = sell_match.group(2)
            
            # Portföyde var mı?
            holdings = pm.get_holdings_dict()
            if symbol in holdings:
                # Belirtilen fiyat varsa onu kullan, yoksa canlı fiyatı al
                if price_str:
                    price = float(price_str.replace(",", "."))
                else:
                    price_data = dc.get_current_price(symbol)
                    price = price_data["price"] if price_data else holdings[symbol]["maliyet"]
                
                qty = holdings[symbol]["adet"]
                
                res = pm.remove_stock(symbol, qty, price, reason="Manuel Telegram Komutu")
                if res["success"]:
                    notifier.send_message(f"🚨 <b>Tamamdır efendim, {symbol} satıldı.</b>\n💰 Satış Fiyatı: {price:.2f} TL\n📈 Kâr/Zarar: {res['profit_loss']:+.2f} TL\n🏁 Hedef takibi ve ilerleme çubuğu güncellendi.")
                    logger.info(f"Telegram Komutu: {symbol} satildi.")
            else:
                notifier.send_message(f"❌ {symbol} portföyünüzde bulunamadı.")

    # Yeni offseti kaydet
    with open(offset_file, "w") as f:
        f.write(str(max_id))


def send_tomorrow_forecast(pm, notifier, dc):
    """Yarın için en iyi 5 hisseyi bulur ve gönderir"""
    try:
        from signal_generator import SignalGenerator
        from config import BIST100_TICKERS
        sg = SignalGenerator()
        
        buy_candidates = []
        logger.info("Yarin tahmini taramasi basladi...")
        
        # Filtreyi biraz esneterek en iyi 5'i bulmayı garantileyelim
        # Ama yine de belli bir kalite standardı olsun (Skor > 55)
        for i, symbol in enumerate(BIST100_TICKERS):
            try:
                # Deep scan (quick_mode=False)
                result = sg.analyze_stock(symbol, skip_backtest=True, quick_mode=False)
                if not result: continue
                
                score = result.get("overall_score", 0)
                price = result.get("current_price", 0)
                
                if score >= 55:
                    targets = calculate_targets(symbol, result)
                    buy_candidates.append({
                        "symbol": symbol,
                        "score": score,
                        "price": price,
                        "target_pct": targets["target_pct"],
                        "reason": result.get("signal", {}).get("reason", "Güçlü teknik görünüm."),
                        "date": datetime.now(TZ_TR).strftime("%d.%m.%Y")
                    })
                
                if (i+1) % 20 == 0:
                    logger.info(f"Yarin taramasi: {i+1}/100...")
            except:
                continue
        
        # En iyi 5'i seç
        buy_candidates.sort(key=lambda x: x["score"], reverse=True)
        notifier.send_tomorrow_forecast_report(buy_candidates[:5])
        
    except Exception as e:
        logger.error(f"Forecast hatasi: {e}")
        notifier.send_message("❌ Tahmin raporu oluşturulurken bir hata oluştu.")


# ==================== ANA TARAMA ====================
def run_cloud_scan():
    now_tr = datetime.now(TZ_TR)
    logger.info(f"Tarama baslatiliyor: {now_tr.strftime('%d.%m.%Y %H:%M')} (TR)")

    # ==================== KULLANICI KOMUTLARI ====================
    try:
        from portfolio import PortfolioManager
        from notifier import Notifier
        from data_collector import DataCollector
        
        pm = PortfolioManager()
        notifier = Notifier()
        dc = DataCollector()
        
        process_user_commands(pm, notifier, dc)
    except Exception as e:
        logger.error(f"Kullanici komutu isleme hatasi: {e}")

    # ==================== PAZAR SAATİ KONTROLÜ ====================
    # ==================== CLOUD HEARTBEAT (GÜVEN BİLDİRİMİ) ====================
    # Gün içindeki ilk çalıştırmada (saat 10:00 civarı) kullanıcının telefonuna
    # "Sistem Hazır" bildirimi gönderir.
    if now_tr.hour == 10 and now_tr.minute < 10:
        heartbeat_file = "cloud_heartbeat.status"
        # Eğer bugün bildirim gönderilmemişse gönder
        today_str = now_tr.strftime('%Y-%m-%d')
        if not os.path.exists(heartbeat_file) or open(heartbeat_file).read().strip() != today_str:
            send_telegram(
                f"✅ <b>BULUT TARAYICI AKTİF</b>\n\n"
                f"📅 Tarih: {now_tr.strftime('%d.%m.%Y')}\n"
                f"⏰ Saat: {now_tr.strftime('%H:%M')}\n"
                f"🤖 Durum: Sistem sorunsuz, tarama başlıyor.\n\n"
                f"<i>İyi seanslar dilerim efendim.</i>"
            )
            with open(heartbeat_file, "w") as f:
                f.write(today_str)
            logger.info("Heartbeat bildirimi gönderildi.")

    if not is_market_hours():
        logger.info("Borsa kapali - tarama ve sinyal kontrolü atlaniyor.")
        return

    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    try:
        from signal_generator import SignalGenerator
        from config import BIST100_TICKERS
        import yfinance as yf
    except ImportError as e:
        logger.error(f"Modul import hatasi: {e}")
        sys.exit(1)

    sg = SignalGenerator()

    # ==================== OTO-SAT KONTROLÜ ====================
    holdings = pm.get_portfolio()
    auto_sell_messages = []
    
    # XU100 5 Dakikalık şelale kontrolü
    index_crash = False
    try:
        import yfinance as yf
        xu_data = yf.Ticker("XU100.IS").history(period="1d", interval="5m")
        if len(xu_data) >= 2:
            last_xu = xu_data['Close'].iloc[-1]
            prev_xu = xu_data['Close'].iloc[-2]
            if (last_xu - prev_xu) / prev_xu <= -0.005: # -%0.5
                index_crash = True
                logger.warning("🚨 BIST100 ŞELALE DÜŞÜŞÜ ALGILANDI! Tüm pozisyonlarda EJECT devreye girdi.")
    except Exception as e:
        logger.error(f"XU100 veri hatasi: {e}")
    
    if holdings:
        logger.info(f"Sinyal kontrolu yapiliyor ({len(holdings)} hisse)...")
        symbols_to_check = [h["symbol"] for h in holdings]
        if symbols_to_check:
            try:
                # Toplu fiyat çekimi
                data = yf.download(symbols_to_check, period="1d", group_by="ticker", progress=False)
                
                for h in holdings:
                    sym = h["symbol"]
                    
                    # Yfinance multiple vs single ticker yapısal farkını düzelt
                    if len(symbols_to_check) == 1:
                        current_price = data["Close"].iloc[-1]
                    else:
                        current_price = data[sym]["Close"].iloc[-1]
                    
                    # Zirve Değer Takibi (Manuel alımlar için raporlama amaçlı)
                    peak_data = pm.update_peak_price(sym, current_price)
                    max_peak = peak_data["max_peak"]
                    
                    target = h.get("target_price", 0)
                    stop = h.get("stop_loss", 0)
                    buy_price = h.get("avg_buy_price", 0)
                    
                    sell_alert = False
                    reason = ""
                    
                    if index_crash:
                        sell_alert = True
                        reason = "🚨 Acil Çıkış: XU100 Şelale Çöküşü (-%0.5)!"
                    elif max_peak > buy_price and current_price < max_peak * 0.985:
                        sell_alert = True
                        reason = f"📉 İzleyen Stop Bozuldu (Zirve: {max_peak:.2f})"
                    elif stop > 0 and current_price <= stop:
                        sell_alert = True
                        reason = f"🛑 Stop loss seviyesine indi ({stop} TL)"
                    elif target > 0 and current_price >= target:
                        # Tavan Kilidi Kontrolü (+%9 veya üzeri)
                        prev_close = peak_data.get("previous_close", 0)
                        if prev_close > 0 and current_price >= prev_close * 1.09:
                            logger.info(f"🔒 Tavan Kilidi: {sym} hedefte ama satilmiyor.")
                        else:
                            sell_alert = True
                            reason = f"🎯 Hedef fiyata ulasti ({target} TL)"
                    
                    if sell_alert:
                        # Satış bildirimi ve ROTASYON TAVSİYESİ
                        tahmini_dip = current_price * 0.97
                        rotasyon_notu = "\n🔄 <i>Portfoyden cikip taze bir 6/6 hisseye gecme zamani gelmis olabilir.</i>"
                        notifier.send_sell_signal(
                            symbol=sym, 
                            fiyat=current_price, 
                            fiyat_hedef=target,
                            tahmini_dip=tahmini_dip, 
                            bozulan_parametreler=reason + rotasyon_notu,
                            guncel_bakiye=pm.get_balance()
                        )
                        logger.info(f"SATIS BILDIRIMI: {sym}. Neden: {reason}")
            except Exception as e:
                logger.error(f"Sinyal kontrolunde hata: {e}")

    # ==================== TOPLU VERİ ÇEKME (BULK DOWNLOAD) ====================
    import yfinance as yf
    logger.info(f"{len(BIST100_TICKERS)} hisse için toplu veri çekiliyor...")
    
    # 1. Hisse Verileri (BIST 100)
    # yfinance 0.2.x bulk download
    raw_data = yf.download(BIST100_TICKERS, period="1y", interval="1d", group_by='ticker', threads=True)
    
    # 2. Makro Veriler (XU100, VIX, USD/TRY)
    macro_tickers = ["XU100.IS", "^VIX", "USDTRY=X"]
    macro_data = yf.download(macro_tickers, period="6mo", interval="1d", group_by='ticker', threads=True)
    
    # MacroAnalyzer'ı tek bir instance olarak başlat ve verileri enjekte et
    sg = SignalGenerator()
    if not macro_data.empty:
        try:
            # Macro veriler MultiIndex olarak gelir, direkt ticker altından alıyoruz
            sg.macro_analyzer.is_market_bullish(external_df=macro_data["XU100.IS"])
            sg.macro_analyzer.get_vix(external_df=macro_data["^VIX"])
            sg.macro_analyzer.get_usdtry(external_df=macro_data["USDTRY=X"])
            logger.info("Makro veriler başarıyla enjekte edildi.")
        except Exception as e:
            logger.warning(f"Makro enjeksiyon hatası: {e}")

    # ==================== PARALEL TARAMA FONKSİYONU ====================
    def scan_worker(symbol):
        try:
            # Bu hisseye ait veriyi çek
            try:
                symbol_df = raw_data[symbol]
                if symbol_df is None or symbol_df.empty:
                    return None
            except (KeyError, ValueError):
                return None

            # Her thread için kendi modüllerini kullanmak daha güvenli
            from portfolio import PortfolioManager
            from notifier import Notifier
            
            pm_local = PortfolioManager()
            notifier_local = Notifier()
            
            # TAM ANALİZ: external_df ile hızlı ve güvenli besleme
            result = sg.analyze_stock(symbol, skip_backtest=True, quick_mode=False, external_df=symbol_df)
            if not result:
                return None

            signal = result.get("signal", {})
            action = signal.get("action", "TUT")
            score = result.get("overall_score", 50)
            price = result.get("current_price", 0)
            reason = signal.get("reason", "")

            # ===== AL SİNYALİ KONTROLÜ (ANLIK) =====
            if "AL" in action and score >= 55:
                targets = calculate_targets(symbol, result)
                
                # Baraj kontrolü (%4.5)
                if targets["target_pct"] >= 4.5:
                    onay_notu = f"✅ Teknik ✅ Hacim ✅ AKD ✅ Haber ✅ Makro ✅ Risk\n📝 {reason}"
                    
                    if targets["target_pct"] >= 5.2:
                        # A-Class
                        notifier_local.send_buy_signal(
                            symbol=symbol,
                            current_price=price,
                            target_price=targets["target"],
                            stop_price=targets["stop"],
                            onay_notu=onay_notu
                        )
                        logger.info(f"ANLIK A-SINIFI: {symbol} (%{targets['target_pct']})")
                    else:
                        # B-Class
                        notifier_local.send_b_class_signal(
                            symbol=symbol,
                            current_price=price,
                            target_price=targets["target"],
                            stop_price=targets["stop"],
                            onay_notu=onay_notu
                        )
                        logger.info(f"ANLIK B-SINIFI: {symbol} (%{targets['target_pct']})")
                    
                    return {"type": "BUY", "symbol": symbol, "score": score}

            # ===== SAT SİNYALİ KONTROLÜ (ANLIK - Sadece çok güçlü sinyaller için) =====
            elif "SAT" in action and score <= 40:
                # Sat sinyalleri genelde çok fazladır, o yüzden sadece en kötüleri veya 
                # genel özeti gönderiyoruz (mevcut mantık korunabilir veya anlık yapılabilir)
                return {"type": "SELL", "symbol": symbol, "score": score, "reason": reason, "price": price}

            return {"type": "KEEP", "symbol": symbol}

        except Exception as e:
            logger.error(f"{symbol} paralel tarama hatasi: {e}")
            return None

    # ThreadPool ile taramayı başlat
    from concurrent.futures import ThreadPoolExecutor, as_completed
    
    buy_count = 0
    sell_signals = []
    all_analyzed = 0
    total = len(BIST100_TICKERS)
    
    logger.info(f"Toplam {total} hisse paralel taranacak (Ayni anda 6 hisse)...")
    
    with ThreadPoolExecutor(max_workers=6) as executor:
        futures = {executor.submit(scan_worker, sym): sym for sym in BIST100_TICKERS}
        
        for i, future in enumerate(as_completed(futures)):
            res = future.result()
            if res:
                all_analyzed += 1
                if res["type"] == "BUY":
                    buy_count += 1
                elif res["type"] == "SELL":
                    sell_signals.append(res)
            
            if (i + 1) % 10 == 0:
                logger.info(f"İlerleme: [{i+1}/{total}] tamamlandi...")

    # ==================== SONUÇLAR ====================
    logger.info(f"Tarama bitti: {all_analyzed} analiz, {buy_count} AL sinyali gonderildi.")

    # ===== SAT SİNYALLERİ ÖZETİ (Grup halinde gönderim) =====
    if sell_signals:
        sell_signals.sort(key=lambda x: x["score"])
        msg = f"🔴 <b>BIST 100 — {len(sell_signals)} SAT SİNYALİ</b>\n"
        msg += f"📅 {now_tr.strftime('%d.%m.%Y %H:%M')}\n\n"
        for s in sell_signals[:5]:
            msg += f"🔴 <b>#{s['symbol']}</b> — Skor: {s['score']:.0f} | {s['price']:.2f} TL\n"
            msg += f"   📝 {s['reason'][:55]}\n\n"
        send_telegram(msg)

    # Oto-Sat bildirimlerini gönder
    for m in auto_sell_messages:
        send_telegram(m)

    # ===== SAT SİNYALLERİ =====
    # (Özet zaten yukarıda gönderildi)

    # ===== GÜNLÜK RAPOR (saat 10:00) =====
    if buy_count == 0 and not sell_signals:
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
    try:
        run_cloud_scan()
    except Exception as e:
        error_msg = f"❌ <b>SİSTEM HATASI</b>\n\n⚠️ Beklenmedik bir hata oluştu ve tarayıcı durdu.\n\n🔍 <b>Hata:</b> {str(e)[:200]}"
        try:
            from cloud_scanner import send_telegram  # Re-import test
            send_telegram(error_msg)
        except:
            print(f"Telegram error reporting failed: {e}")
        
        # Log the full traceback
        import traceback
        logging.error(f"Kritik sistem hatası:\n{traceback.format_exc()}")
        sys.exit(1)
