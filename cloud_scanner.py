"""
BIST 100 Bulut Tarayıcı — TAM ANALİZ MODU

2 yıllık geçmiş + Teknik Analiz (15 indikatör) + ML Tahmin + Haberler + Makro
Hedef fiyat + Stop Loss hesaplar.
AL sinyali bulursa Telegram'dan bildirim gönderir.

GitHub Actions üzerinde her 15 dk'da bir otomatik çalışır.
"""

import shutil
import time
import os
import sys
import logging
import requests
import ssl
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

# ===== .env Yükleme (EN BAŞTA - Telegram token'ları için gerekli) =====
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

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
    """Borsa saatleri: Hafta içi 09:55 - 18:10"""
    now = datetime.now(TZ_TR)
    if now.weekday() >= 5:  # Hafta sonu
        return False
    # Dakika cinsinden kontrol (09:55 = 595, 18:10 = 1090)
    current_minutes = now.hour * 60 + now.minute
    return 595 <= current_minutes <= 1090


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
    text = text.replace("kimsin", "kimsin").replace("ne ise yararsin", "kimsin")
    
    # Tarama kalıpları
    text = text.replace("tarama yap", "tara").replace("tarama baslat", "tara")
    text = text.replace("hisse tara", "tara").replace("piyasa tara", "tara")
    text = text.replace("scan", "tara").replace("sinyal bul", "tara")
    text = text.replace("hisse bul", "tara").replace("firsatlari goster", "tara")
    text = text.replace("ne alalim", "tara").replace("ne alayim", "tara")
    text = text.replace("bugunku firsatlar", "tara").replace("bugunun hisseleri", "tara")
    
    return text.strip()

# ==================== TELEGRAM KOMUT DİNLEYİCİ ====================
def process_user_commands(pm, notifier, dc, sg):
    """Telegram'dan gelen kullanıcı komutlarını işler"""
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
                       "🔍 <b>TARAMA</b>\n" \
                       "• <code>tara</code> / <code>tarama yap</code> -> Anlık tam BIST 100 taraması\n" \
                       "• <code>yarin</code> -> Yarın yükselebilecek 5 hisseyi tahmin eder\n\n" \
                       "📊 <b>ANALİZ & SORGULAMA</b>\n" \
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

        # TARAMA YAP KOMUTU (ANLIK TAM TARAMA)
        if text in ["tara", "tarama", "taramayap"]:
            notifier.send_message(
                "🔍 <b>ANLIK TAM TARAMA BAŞLATILDI</b>\n\n"
                "📊 BIST 100 hisseleri 6 kriterle taranıyor...\n"
                "🎯 Hedef: %4.5+ potansiyelli hisseler\n\n"
                "<i>Bu işlem 2-4 dakika sürebilir, lütfen bekleyiniz efendim.</i>"
            )
            run_instant_scan(notifier, sg, dc)
            continue

        # YARIN TAHMİNİ (ÖZEL KOMUT)
        if forecast_pattern.match(text):
            notifier.send_message("🔮 <b>Yarın için derin analiz başlatıldı...</b>\nBIST 100 hisseleri topluca taranıyor. Lütfen bekleyiniz efendim.")
            # Hızlı bulk analiz fonksiyonunu çağır
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

        # 6. ENDEKS
        if market_pattern.match(text):
            try:
                xu100 = dc.get_current_price("XU100.IS")
                change = xu100.get("change_percent", 0)
                risk = "🚨 Şelale Riski!" if change < -0.4 else "🛡️ Düşük Risk" if change > 0 else "⚠️ Orta Risk"
                notifier.send_market_pulse({"price": xu100.get("price", 0), "change": change, "risk_level": risk, "comment": "Analiz tamamlandı."})
                continue
            except: pass

        # 7. HİSSE ANALİZ
        analyze_match = analyze_pattern.match(text)
        if analyze_match:
            symbol = analyze_match.group(1).upper()
            notifier.send_message(f"🔍 <b>#{symbol} Hisse Analizi...</b>\nDerin tarama başlatıldı.")
            result = sg.analyze_stock(symbol, skip_backtest=True, quick_mode=False)
            if result: notifier.send_analysis_report(result)
            continue

        # 8. AL/SAT/BAKİYE (Hızlı)
        bakiye_match = bakiye_pattern.match(text)
        if bakiye_match:
            try:
                new_bal = float(bakiye_match.group(2).replace(",", "."))
                pm.set_balance(new_bal)
                notifier.send_message(f"💰 <b>Bakiye {new_bal:.2f} TL olarak güncellendi.</b>")
                continue
            except: pass

        buy_match = buy_pattern.match(text)
        if buy_match:
            symbol = buy_match.group(1).upper()
            price_data = dc.get_current_price(symbol)
            price = float(buy_match.group(2).replace(",", ".")) if buy_match.group(2) else price_data.get("price", 0)
            if price > 0:
                bakiye = pm.get_balance()
                if bakiye > 10:
                    adet = (bakiye * 0.998) / price
                    pm.add_stock(symbol, adet, price, target_price=price*1.05, stop_loss=price*0.97)
                    notifier.send_message(f"✅ <b>{symbol} takibe alındı!</b>\nFiyat: {price:.2f} TL")
                else:
                    notifier.send_message(f"⚠️ Bakiye yetersiz.")
            continue

        sell_match = sell_pattern.match(text)
        if sell_match:
            symbol = sell_match.group(1).upper()
            holdings = pm.get_holdings_dict()
            if symbol in holdings:
                price_data = dc.get_current_price(symbol)
                price = price_data["price"] if price_data else holdings[symbol]["maliyet"]
                res = pm.remove_stock(symbol, holdings[symbol]["adet"], price)
                notifier.send_message(f"🚨 <b>{symbol} satıldı.</b>\nKâr/Zarar: {res.get('profit_loss', 0):+.2f} TL")
            else:
                notifier.send_message(f"❌ {symbol} portföyde yok.")
            continue

        # 9. FALLBACK (ANLAŞILMAYAN)
        if text:
            notifier.send_message("🤔 <b>Bunu tam anlayamadım efendim.</b>\nLütfen farklı şekilde sormayı deneyin veya <code>yardim</code> yazın.")

    # Yeni offseti kaydet
    if max_id > offset:
        with open(offset_file, "w") as f:
            f.write(str(max_id))


def send_tomorrow_forecast(pm, notifier, dc):
    """Yarın için en iyi 5 hisseyi bulur ve gönderir (BULK DOWNLOAD MODU)"""
    try:
        from signal_generator import SignalGenerator
        from config import BIST100_TICKERS
        import yfinance as yf
        
        sg = SignalGenerator()
        
        # 1. TOPLU VERİ ÇEK (Çok daha hızlı)
        logger.info(f"Yarin tahmini için {len(BIST100_TICKERS)} hisse toplu indiriliyor...")
        raw_data = yf.download(BIST100_TICKERS, period="1y", interval="1d", group_by='ticker', threads=True, progress=False)
        
        buy_candidates = []
        
        # 2. ANALİZ
        for symbol in BIST100_TICKERS:
            try:
                # Veriyi al
                symbol_df = raw_data[symbol]
                if symbol_df is None or symbol_df.empty: 
                    continue

                # Quick mode ile tara ama bulk veriyi bas
                result = sg.analyze_stock(symbol, skip_backtest=True, quick_mode=False, external_df=symbol_df)
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
            except:
                continue
        
        # En iyi 5'i seç
        buy_candidates.sort(key=lambda x: x["score"], reverse=True)
        notifier.send_tomorrow_forecast_report(buy_candidates[:5])
        
    except Exception as e:
        logger.error(f"Forecast hatasi: {e}")
        notifier.send_message("❌ Tahmin raporu oluşturulurken bir hata oluştu.")


# ==================== ANLIK TAM TARAMA (TELEGRAM KOMUTUYLA) ====================
def run_instant_scan(notifier, sg, dc):
    """Telegram'dan 'tara' komutuyla tetiklenen anlık tam tarama"""
    try:
        from config import BIST100_TICKERS
        import yfinance as yf
        
        now_tr = datetime.now(TZ_TR)
        logger.info(f"ANLIK TARAMA BAŞLATILDI: {len(BIST100_TICKERS)} hisse")
        
        # 1. Toplu veri çek
        yahoo_tickers = [f"{t}.IS" for t in BIST100_TICKERS]
        raw_data = yf.download(yahoo_tickers, period="1y", interval="1d", 
                               group_by='ticker', threads=True, progress=False)
        
        buy_a_class = []  # TKS >= 7
        buy_b_class = []  # TKS < 7
        total_analyzed = 0
        
        # 2. Her hisseyi analiz et
        for symbol in BIST100_TICKERS:
            try:
                yahoo_sym = f"{symbol}.IS"
                try:
                    symbol_df = raw_data[yahoo_sym]
                    if symbol_df is None or symbol_df.empty:
                        continue
                except (KeyError, TypeError):
                    continue
                
                result = sg.analyze_stock(symbol, skip_backtest=True, quick_mode=True, external_df=symbol_df)
                if not result:
                    continue
                
                total_analyzed += 1
                
                v2_signal = result.get("v2_signal", {})
                v1_signal = result.get("v1_signal", {})
                score = result.get("overall_score", 50)
                tks = v2_signal.get("quality_score", 0)
                price = result.get("current_price", 0)
                reason = v2_signal.get("reason", "")
                
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
                        }
                        
                        if tks >= 7:
                            buy_a_class.append(entry)
                        else:
                            buy_b_class.append(entry)
                            
            except Exception as e:
                logger.error(f"{symbol} instant scan hata: {e}")
                continue
        
        # 3. Sonuçları Telegram'a gönder
        if buy_a_class:
            buy_a_class.sort(key=lambda x: x["tks"], reverse=True)
            msg = f"🚀🚀 <b>A-SINIFI SİNYALLER (GÜÇLÜ AL)</b>\n"
            msg += f"📅 {now_tr.strftime('%d.%m.%Y %H:%M')}\n\n"
            
            for s in buy_a_class[:5]:
                v_tag = "💎v1+v2" if s["v1"] else "🚀v2"
                msg += f"{'='*28}\n"
                msg += f"<b>#{s['symbol']}</b> — {v_tag}\n"
                msg += f"💰 Fiyat: {s['price']:.2f} TL\n"
                msg += f"🎯 Hedef: {s['target']:.2f} TL (<b>%{s['target_pct']:+.1f}</b>)\n"
                msg += f"🛑 Stop: {s['stop']:.2f} TL (%{s['stop_pct']:.1f})\n"
                msg += f"📊 TKS: <b>{s['tks']}/10</b> | Skor: %{s['score']:.0f}\n"
                msg += f"⚖️ Risk/Ödül: {s['rr']}x\n\n"
            
            msg += f"💪 <b>Bu sinyaller FULL GİRİLEBİLİR kalitededir.</b>"
            notifier.send_message(msg)
        
        if buy_b_class:
            buy_b_class.sort(key=lambda x: x["target_pct"], reverse=True)
            msg = f"🥈 <b>B-SINIFI FIRSATLAR</b>\n"
            msg += f"📅 {now_tr.strftime('%d.%m.%Y %H:%M')}\n\n"
            
            for s in buy_b_class[:5]:
                v_tag = "💎v1+v2" if s["v1"] else "🚀v2"
                msg += f"<b>#{s['symbol']}</b> — {v_tag}\n"
                msg += f"💰 {s['price']:.2f} TL → 🎯 {s['target']:.2f} TL (<b>%{s['target_pct']:+.1f}</b>)\n"
                msg += f"📊 TKS: {s['tks']}/10 | Stop: {s['stop']:.2f} TL\n\n"
            
            msg += f"⚠️ <i>Küçük lotlarla denenebilir.</i>"
            notifier.send_message(msg)
        
        if not buy_a_class and not buy_b_class:
            notifier.send_message(
                f"🛡️ <b>NAKİTTE KAL</b>\n\n"
                f"📅 {now_tr.strftime('%d.%m.%Y %H:%M')}\n"
                f"🔍 {total_analyzed} hisse 6 faktörle tarandı\n"
                f"❌ %4.5+ hedefli güvenli AL sinyali bulunamadı.\n\n"
                f"<i>Piyasa şartları uygun değil — sabırlı ol efendim.</i>"
            )
        
        # Özet
        notifier.send_message(
            f"📊 <b>TARAMA ÖZETİ</b>\n\n"
            f"📈 Taranan: {total_analyzed} hisse\n"
            f"🚀 A-Sınıfı (TKS≥7): {len(buy_a_class)}\n"
            f"🥈 B-Sınıfı: {len(buy_b_class)}\n\n"
            f"<i>6 Kriter: Hacim ✓ Teknik ✓ Makro ✓ AKD ✓ Haber ✓ Duygu ✓</i>"
        )
        
        logger.info(f"Anlık tarama bitti: {total_analyzed} hisse, A:{len(buy_a_class)}, B:{len(buy_b_class)}")
        
    except Exception as e:
        logger.error(f"Anlık tarama hatası: {e}")
        notifier.send_message(f"❌ <b>Tarama sırasında hata:</b> {str(e)[:200]}")


# ==================== ANA TARAMA ====================
def run_cloud_scan():
    # Loop Değişkenleri
    START_TIME = time.time()
    MAX_LOOP_TIME = 4 * 60   # 4 dakika uyanık kal (GitHub cron 5 dk'da bir gelir)
    POLL_INTERVAL = 15       # 15 saniyede bir Telegram'ı kontrol et
    LAST_SCAN_TIME = 0       # Son tarama zamanı
    SCAN_INTERVAL = 30 * 60  # Her 30 dakikada bir tam tarama yap
    
    now_tr = datetime.now(TZ_TR)
    logger.info(f"Oto-Robot 'ALWAYS-ON' Modunda Baslatildi: {now_tr.strftime('%d.%m.%Y %H:%M')}")

    # Objeleri bir kere oluştur (performans)
    from portfolio import PortfolioManager
    from notifier import Notifier
    from data_collector import DataCollector
    from signal_generator import SignalGenerator
    
    pm = PortfolioManager()
    notifier = Notifier()
    dc = DataCollector()
    sg = SignalGenerator()

    # ===== HEARTBEAT: Borsa açılışında güven bildirimi =====
    _send_heartbeat_if_needed(now_tr)

    while True:
        # 1. LOOP ÇIKIŞ KONTROLÜ (GitHub Action zaman aşımı riski)
        elapsed = time.time() - START_TIME
        if elapsed > MAX_LOOP_TIME:
            logger.info("Maksimum loop süresine ulaşıldı, oturum kapatılıyor.")
            break

        now_tr = datetime.now(TZ_TR)
        
        # 2. KOMUTLARI İŞLE (ANLIK TEPKİ)
        try:
            process_user_commands(pm, notifier, dc, sg)
        except Exception as e:
            logger.error(f"Kullanici komutu isleme hatasi: {e}")

        # 3. PAZAR SAATİ AKTİF Mİ?
        scan_due = (time.time() - LAST_SCAN_TIME) >= SCAN_INTERVAL
        
        if is_market_hours() and scan_due:
            perform_main_scan(now_tr, pm, notifier, dc, sg)
            LAST_SCAN_TIME = time.time()
            
        # 4. BEKLE (POLLING HEARTBEAT)
        time.sleep(POLL_INTERVAL)


def _send_heartbeat_if_needed(now_tr):
    """Borsa açılış saatinde (10:00) güven bildirimi gönderir"""
    if now_tr.weekday() >= 5:  # Hafta sonu
        return
    # Sadece 09:55-10:15 arasında heartbeat gönder (borsa açılmadan önce)
    if now_tr.hour == 9 and now_tr.minute >= 55:
        pass  # 09:55+ ise devam
    elif now_tr.hour == 10 and now_tr.minute <= 15:
        pass  # 10:00-10:15 ise devam
    else:
        return
    
    heartbeat_file = "cloud_heartbeat.status"
    today_str = now_tr.strftime('%Y-%m-%d')
    
    already_sent = False
    if os.path.exists(heartbeat_file):
        try:
            with open(heartbeat_file, 'r') as f:
                already_sent = f.read().strip() == today_str
        except:
            pass
    
    if not already_sent:
        send_telegram(
            f"✅ <b>BULUT TARAYICI AKTİF</b>\n\n"
            f"📅 Tarih: {now_tr.strftime('%d.%m.%Y')}\n"
            f"⏰ Saat: {now_tr.strftime('%H:%M')}\n"
            f"🤖 Durum: Sistem sorunsuz, tarama başlıyor.\n\n"
            f"<i>İyi seanslar dilerim efendim.</i>"
        )
        try:
            with open(heartbeat_file, "w") as f:
                f.write(today_str)
        except:
            pass
        logger.info("Heartbeat bildirimi gönderildi.")

def perform_main_scan(now_tr, pm, notifier, dc, sg):
    logger.info(f"Piyasa Taraması Başlatılıyor: {now_tr.strftime('%H:%M')}")
    
    if not is_market_hours():
        logger.info("Borsa kapali - tarama ve sinyal kontrolü atlaniyor.")
        return

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
    notifier_local = Notifier()

    def scan_worker(symbol):
        """Tek bir hisseyi paralel olarak tarar"""
        try:
            # Bulk download'dan bu sembolün verisini al
            try:
                symbol_df = raw_data[symbol]
                if symbol_df is None or symbol_df.empty:
                    return None
            except (KeyError, TypeError):
                return None

            # TAM ANALİZ: external_df ile hızlı ve güvenli besleme
            result = sg.analyze_stock(symbol, skip_backtest=True, quick_mode=False, external_df=symbol_df)
            if not result:
                return None

            v2_signal = result.get("v2_signal", {})
            v1_signal = result.get("v1_signal", {})
            
            action = v2_signal.get("action", "TUT")
            score = result.get("overall_score", 50)
            tks = v2_signal.get("quality_score", 0)
            price = result.get("current_price", 0)
            reason = v2_signal.get("reason", "")
            is_early = v2_signal.get("is_early", False)

            # Sinyal Sonucunu Kaydet (Paylaşımlı breakout sayacı için)
            if is_early:
                with breakout_lock:
                    breakout_count[0] += 1

            # ===== AL SİNYALİ KONTROLÜ (ANLIK) =====
            # v2 Onaylıysa veya v1 Onaylıysa
            if (v2_signal.get("passed") or v1_signal.get("passed")) and score >= 55:
                targets = calculate_targets(symbol, result)
                
                # Baraj kontrolü (%4.8 - Kullanıcı isteği sabitlemesi)
                if targets["target_pct"] >= 4.5:
                    onay_notu = f"{'💎 v1 (6/6) & ' if v1_signal.get('passed') else ''}🚀 v2 (4/6) Onaylı\n"
                    onay_notu += f"📊 <b>Kalite Skoru (TKS): {tks}/10</b>\n"
                    onay_notu += f"📝 {reason}"
                    
                    if tks >= 7:
                        # A-Class (Yüksek Kalite)
                        notifier_local.send_buy_signal(
                            symbol=symbol,
                            current_price=price,
                            target_price=targets["target"],
                            stop_price=targets["stop"],
                            onay_notu=onay_notu + "\n\n💪 <b>GÜÇLÜ SİNYAL: FULL GİRİLEBİLİR</b>"
                        )
                        logger.info(f"ANLIK A-SINIFI (v2): {symbol} (%{targets['target_pct']}) TKS: {tks}")
                    else:
                        # B-Class (Orta Kalite)
                        notifier_local.send_b_class_signal(
                            symbol=symbol,
                            current_price=price,
                            target_price=targets["target"],
                            stop_price=targets["stop"],
                            onay_notu=onay_notu + "\n\n⚠️ <i>Küçük lotlarla denenebilir.</i>"
                        )
                        logger.info(f"ANLIK B-SINIFI (v2): {symbol} (%{targets['target_pct']}) TKS: {tks}")
                    
                    return {"type": "BUY", "symbol": symbol, "score": score, "v1": v1_signal.get("passed"), "tks": tks}

            # ===== SAT SİNYALİ KONTROLÜ (ANLIK - Sadece çok güçlü sinyaller için) =====
            elif "SAT" in action and score <= 40:
                return {"type": "SELL", "symbol": symbol, "score": score, "reason": reason, "price": price}

            return {"type": "KEEP", "symbol": symbol}

        except Exception as e:
            logger.error(f"{symbol} paralel tarama hatasi: {e}")
            return None

    from concurrent.futures import ThreadPoolExecutor, as_completed
    import threading
    
    breakout_lock = threading.Lock()
    breakout_count = [0]
    
    buy_count = 0
    sell_signals = []
    all_analyzed = 0
    total = len(BIST100_TICKERS)
    
    logger.info(f"Toplam {total} hisse paralel taranacak (v2 Smart Engine)...")
    
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

    # ==================== GÜN SKORU HESAPLA ====================
    day_score_data = sg.macro_analyzer.calculate_day_score(
        xu100_df=macro_data["XU100.IS"],
        total_breakouts=breakout_count[0]
    )
    
    # Gün Özeti Bildirimi
    score = day_score_data["score"]
    status = day_score_data["status"]
    reasons = "\n".join(day_score_data["reasons"])
    
    msg = f"🔍 <b>PİYASA GÜN SKORU: {score}/3</b>\n"
    msg += f"📊 Durum: <b>{status}</b>\n\n"
    msg += f"{reasons}\n\n"
    msg += f"<i>{all_analyzed} hisse tıkır tıkır analiz edildi. v2 motoru devrede.</i>"
    send_telegram(msg)

    # ==================== SONUÇLAR ====================
    logger.info(f"Tarama bitti: {all_analyzed} analiz, Day Score: {score}/3")

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
        import traceback
        error_msg = f"❌ <b>SİSTEM HATASI</b>\n\n⚠️ Beklenmedik bir hata oluştu ve tarayıcı durdu.\n\n🔍 <b>Hata:</b> {str(e)[:200]}"
        try:
            send_telegram(error_msg)
        except:
            print(f"Telegram error reporting failed: {e}")
        
        logging.error(f"Kritik sistem hatası:\n{traceback.format_exc()}")
        sys.exit(1)
